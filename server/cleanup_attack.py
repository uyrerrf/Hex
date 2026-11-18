"""
Script de limpeza pós-ataque.
Remove todos os usuários trial falsos, limpa trial_claims,
faz checkpoint WAL e VACUUM para recuperar espaço.

USO: python cleanup_attack.py
ATENÇÃO: Execute com o servidor PARADO!
"""

import sys
import os

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gangstar_env  # noqa: bootstrap env
import sqlite3
from database import SessionLocal, DATABASE_URL
from models import Operator, TrialClaim


def cleanup():
    db = SessionLocal()
    try:
        # ==========================================
        # 1. Contar usuários antes da limpeza
        # ==========================================
        total_before = db.query(Operator).count()
        trial_count = db.query(Operator).filter(Operator.is_trial == True).count()
        legit_count = total_before - trial_count
        trial_claims_count = db.query(TrialClaim).count()

        print(f"[*] Estado atual do banco:")
        print(f"    - Total de operadores: {total_before}")
        print(f"    - Operadores TRIAL (serão removidos): {trial_count}")
        print(f"    - Operadores LEGÍTIMOS (serão mantidos): {legit_count}")
        print(f"    - Registros trial_claims: {trial_claims_count}")
        print()

        # ==========================================
        # 2. Remover TODOS os usuários trial
        # ==========================================
        if trial_count > 0:
            deleted = db.query(Operator).filter(Operator.is_trial == True).delete()
            print(f"[+] {deleted} usuários trial REMOVIDOS com sucesso!")
        else:
            print("[+] Nenhum usuário trial para remover")

        # ==========================================
        # 3. Limpar tabela trial_claims
        # ==========================================
        if trial_claims_count > 0:
            db.query(TrialClaim).delete()
            print(f"[+] {trial_claims_count} registros de trial_claims REMOVIDOS!")
        else:
            print("[+] Nenhum registro de trial_claims para remover")

        # ==========================================
        # 4. Limpar HWIDs, IPs e desbanir todos
        # ==========================================
        operators = db.query(Operator).all()
        hwid_cleared = 0
        ip_cleared = 0
        unbanned = 0
        for op in operators:
            if op.hwid is not None:
                op.hwid = None
                op.hwid_activated_at = None
                hwid_cleared += 1
            if op.last_ip is not None or op.created_ip is not None:
                op.last_ip = None
                op.created_ip = None
                ip_cleared += 1
            if op.is_banned:
                op.is_banned = False
                unbanned += 1

        print(f"[+] HWIDs limpos: {hwid_cleared}")
        print(f"[+] IPs limpos: {ip_cleared}")
        print(f"[+] Operadores desbanidos: {unbanned}")

        # ==========================================
        # 5. Commit
        # ==========================================
        db.commit()

        total_after = db.query(Operator).count()
        print()
        print(f"[*] Estado após limpeza:")
        print(f"    - Total de operadores restantes: {total_after}")

    except Exception as e:
        db.rollback()
        print(f"[-] ERRO na limpeza: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

    # ==========================================
    # 6. Checkpoint WAL e VACUUM (SQLite)
    # ==========================================
    if DATABASE_URL.startswith("sqlite"):
        db_file = DATABASE_URL.replace("sqlite:///", "").split("?")[0]
        print()
        print(f"[*] Otimizando banco SQLite: {db_file}")

        try:
            # Verificar tamanhos antes
            main_size = os.path.getsize(db_file) if os.path.exists(db_file) else 0
            wal_file = db_file + "-wal"
            wal_size = os.path.getsize(wal_file) if os.path.exists(wal_file) else 0
            shm_file = db_file + "-shm"
            shm_size = os.path.getsize(shm_file) if os.path.exists(shm_file) else 0

            print(f"    Tamanho DB antes: {main_size / (1024*1024):.1f} MB")
            print(f"    Tamanho WAL antes: {wal_size / (1024*1024):.1f} MB")
            print(f"    Tamanho SHM antes: {shm_size / (1024*1024):.1f} MB")

            conn = sqlite3.connect(db_file, timeout=120)

            # Checkpoint WAL
            print("[*] Executando WAL checkpoint (TRUNCATE)...")
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")

            # VACUUM
            print("[*] Executando VACUUM (pode demorar alguns minutos)...")
            conn.execute("VACUUM;")

            conn.close()

            # Verificar tamanhos depois
            main_size_after = os.path.getsize(db_file) if os.path.exists(db_file) else 0
            wal_size_after = os.path.getsize(wal_file) if os.path.exists(wal_file) else 0

            print(f"    Tamanho DB depois: {main_size_after / (1024*1024):.1f} MB")
            print(f"    Tamanho WAL depois: {wal_size_after / (1024*1024):.1f} MB")

            saved = (main_size + wal_size) - (main_size_after + wal_size_after)
            print(f"    Espaço recuperado: {saved / (1024*1024):.1f} MB")

        except Exception as e:
            print(f"[-] Erro na otimização SQLite: {e}")
            import traceback
            traceback.print_exc()

    print()
    print("=" * 55)
    print("  LIMPEZA PÓS-ATAQUE CONCLUÍDA COM SUCESSO!")
    print("=" * 55)
    print()
    return True


if __name__ == "__main__":
    print()
    print("=" * 55)
    print("  LIMPEZA PÓS-ATAQUE - GANGSTAR REMOTE")
    print("  Remove trials falsos + otimiza banco")
    print("=" * 55)
    print()
    cleanup()
