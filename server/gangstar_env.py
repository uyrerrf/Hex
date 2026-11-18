"""Configuracao central Gangastar Remote — VPS (PostgreSQL + URLs publicas)."""
from __future__ import annotations

import os
import socket
from pathlib import Path

_SERVER_DIR = Path(__file__).resolve().parent


def get_local_ip() -> str:
    """Obtém o IP local primário da máquina na rede Wi-Fi/Ethernet."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


LOCAL_IP = get_local_ip()
PUBLIC_IP = os.environ.get("PUBLIC_IP", LOCAL_IP)
GANGSTAR_PORT = os.environ.get("GANGSTAR_PORT", "5000")
DEFAULT_PUBLIC_URL = f"http://{PUBLIC_IP}:{GANGSTAR_PORT}"
DEFAULT_DATABASE_URL = f"sqlite:///{(_SERVER_DIR / 'gangstar_active.db').as_posix()}"


def _load_env_file(path: Path, overwrite: bool = True) -> None:
    """Carrega .env — insere valores no ambiente."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        k = key.strip()
        v = val.strip().strip('"').strip("'")
        if overwrite or k not in os.environ:
            os.environ[k] = v


def bootstrap() -> None:
    """Carrega .env.vps como fallback primeiro, e depois .env para que .env prevaleça."""
    _load_env_file(_SERVER_DIR / ".env.vps", overwrite=False)
    _load_env_file(_SERVER_DIR / ".env", overwrite=True)
    os.environ.setdefault("DATABASE_URL", DEFAULT_DATABASE_URL)
    
    pub_ip = os.environ.get("PUBLIC_IP", PUBLIC_IP)
    port = os.environ.get("GANGSTAR_PORT", "5000")
    def_url = f"http://{pub_ip}:{port}"
    def_ws = f"ws://{pub_ip}:{port}/ws"

    current_server_url = os.environ.get("SERVER_URL", "")
    if not current_server_url or ("192.168." in current_server_url and LOCAL_IP not in current_server_url):
        os.environ["SERVER_URL"] = def_url
        os.environ["SERVER_WS_URL"] = def_ws

    os.environ.setdefault("SERVER_URL", def_url)
    os.environ.setdefault("SERVER_WS_URL", def_ws)
    os.environ.setdefault("GANGSTAR_PROFILE", "vps")


bootstrap()


def public_base_url() -> str:
    url = os.environ.get("SERVER_URL", DEFAULT_PUBLIC_URL).rstrip("/")
    if "192.168." in url and LOCAL_IP not in url:
        import re
        url = re.sub(r'192\.168\.\d+\.\d+', LOCAL_IP, url)
    return url


def public_http_url() -> str:
    url = public_base_url()
    if url.startswith("ws://"):
        return "http://" + url[5:].split("/")[0]
    if url.startswith("wss://"):
        return "https://" + url[6:].split("/")[0]
    return url


def public_ws_url(extra_query: str = "") -> str:
    raw = os.environ.get("SERVER_WS_URL", "").strip()
    if raw and not ("192.168." in raw and LOCAL_IP not in raw):
        base = raw.rstrip("/")
        if not base.endswith("/ws"):
            base += "/ws"
    else:
        http = public_http_url()
        if http.startswith("https://"):
            base = http.replace("https://", "wss://", 1) + "/ws"
        else:
            base = http.replace("http://", "ws://", 1) + "/ws"

    if extra_query:
        sep = "&" if "?" in base else "?"
        return f"{base}{sep}{extra_query.lstrip('?')}"
    return base


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)

