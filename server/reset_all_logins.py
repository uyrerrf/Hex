"""
Script para limpar:
  1. Todos os logins (sessões/tentativas de login em memória serão resetadas ao reiniciar)
  2. Todos os IPs bloqueados (LOGIN_ATTEMPTS em memória)
  3. Todos os HWIDs de todos os operadores
  4. Todos os registros de trial_claims (IPs/HWIDs bloqueados para trial)
"""

import sys
import os

# Garante encoding UTF-8
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Adiciona o diretório atual ao path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gangstar_env  # noqa: bootstrap env

from database import SessionLocal
from models import Operator, TrialClaim


def reset_all():
    db = SessionLocal()
    try:
        # ==========================================
        # 1. REMOVER TODOS OS HWIDs dos operadores
        # ==========================================
        operators = db.query(Operator).all()
        hwid_count = 0
        for op in operators:
            if op.hwid is not None:
                op.hwid = None
                op.hwid_activated_at = None
                hwid_count += 1

        print(f"[+] HWIDs removidos de {hwid_count} operadores")

        # ==========================================
        # 2. LIMPAR last_login e last_ip (logins)
        # ==========================================
        login_count = 0
        for op in operators:
            if op.last_login is not None or op.last_ip is not None:
                op.last_login = None
                op.last_ip = None
                op.created_ip = None
                login_count += 1

        print(f"[+] Dados de login/IP removidos de {login_count} operadores")

        # ==========================================
        # 3. DESBANIR todos os operadores (IPs bloqueados via ban)
        # ==========================================
        ban_count = 0
        for op in operators:
            if op.is_banned:
                op.is_banned = False
                ban_count += 1

        print(f"[+] {ban_count} operadores desbanidos")

        # ==========================================
        # 4. LIMPAR tabela trial_claims (bloqueia IPs/HWIDs de trial)
        # ==========================================
        trial_count = db.query(TrialClaim).count()
        if trial_count > 0:
            db.query(TrialClaim).delete()
            print(f"[+] {trial_count} registros de trial_claims removidos")
        else:
            print("[+] Nenhum registro de trial_claims para remover")

        # ==========================================
        # 5. COMMIT de todas as alterações
        # ==========================================
        db.commit()
        print()
        print("=" * 50)
        print("  TUDO LIMPO COM SUCESSO!")
        print("=" * 50)
        print()
        print("  - Todos os HWIDs foram removidos")
        print("  - Todos os dados de login foram limpos")
        print("  - Todos os bans foram removidos")
        print("  - Todos os trial_claims foram limpos")
        print()
        print("  NOTA: Os IPs bloqueados em memória (LOGIN_ATTEMPTS)")
        print("  serão resetados automaticamente ao reiniciar o servidor.")
        print()

    except Exception as e:
        db.rollback()
        print(f"[-] ERRO: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    print()
    print("=" * 50)
    print("  RESET TOTAL - LOGINS / IPs / HWIDs")
    print("=" * 50)
    print()
    reset_all()
