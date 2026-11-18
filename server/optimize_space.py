"""
Script de Otimização e Limpeza Extrema do Projeto Gangstar
Reduz o tamanho do repositório ao mínimo absoluto de MB.
"""

import os
import sys
import shutil
import sqlite3
from pathlib import Path

# Fix encoding for Windows console
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

ROOT_DIR = Path(__file__).parent.parent.resolve()

def get_dir_size_mb(path: Path) -> float:
    if not path.exists():
        return 0.0
    total_bytes = 0
    if path.is_file():
        return path.stat().st_size / (1024 * 1024)
    for p in path.glob("**/*"):
        if p.is_file():
            try:
                total_bytes += p.stat().st_size
            except Exception:
                pass
    return total_bytes / (1024 * 1024)

def optimize():
    print("=" * 60)
    print("🚀 INICIANDO LIMPEZA EXTREMA E OTIMIZAÇÃO DE ESPAÇO (MB)")
    print("=" * 60)
    
    initial_size = get_dir_size_mb(ROOT_DIR)
    print(f"📦 Tamanho inicial do projeto: {initial_size:.2f} MB\n")

    # 1. Truncar tabela de logs, WAL e fazer VACUUM no SQLite (gangstar_active.db)
    db_file = ROOT_DIR / "server" / "gangstar_active.db"
    if db_file.exists():
        print("[1/7] Otimizando banco de dados SQLite (Limpando logs antigos & VACUUM)...")
        try:
            conn = sqlite3.connect(str(db_file), timeout=30)
            cur = conn.cursor()
            cur.execute("DELETE FROM device_logs;")
            cur.execute("DELETE FROM captured_data;")
            conn.commit()
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            conn.execute("VACUUM;")
            conn.close()
            print("  ✅ Logs antigos removidos, WAL limpo e VACUUM concluído!")
        except Exception as e:
            print(f"  ⚠️ Erro ao otimizar SQLite: {e}")

    # 2. Deletar pasta duplicada NOVO
    novo_dir = ROOT_DIR / "NOVO"
    if novo_dir.exists():
        s = get_dir_size_mb(novo_dir)
        print(f"[2/7] Removendo pasta duplicada 'NOVO' ({s:.2f} MB)...")
        try:
            shutil.rmtree(novo_dir, ignore_errors=True)
            print("  ✅ Pasta 'NOVO' removida!")
        except Exception as e:
            print(f"  ⚠️ Erro ao deletar 'NOVO': {e}")

    # 3. Remover uploads e outputs antigos do projeto_bypass
    bypass_dir = ROOT_DIR / "server" / "projeto_bypass"
    if bypass_dir.exists():
        for folder_name in ["uploads", "outputs", "output"]:
            target_dir = bypass_dir / folder_name
            if target_dir.exists():
                s = get_dir_size_mb(target_dir)
                if s > 0:
                    print(f"[3/7] Limpando pasta temporária '{folder_name}' ({s:.2f} MB)...")
                    for item in target_dir.iterdir():
                        if item.name == "tutorials":
                            continue
                        try:
                            if item.is_file():
                                item.unlink()
                            elif item.is_dir():
                                shutil.rmtree(item, ignore_errors=True)
                        except Exception:
                            pass

    # 4. Remover jar duplicado de apktool
    duplicate_jar = bypass_dir / "tools" / "apktool.jar"
    if duplicate_jar.exists() and (bypass_dir / "apktool.jar").exists():
        s = get_dir_size_mb(duplicate_jar)
        print(f"[4/7] Removendo apktool.jar duplicado ({s:.2f} MB)...")
        try:
            duplicate_jar.unlink()
            print("  ✅ Duplicata de apktool.jar removida!")
        except Exception as e:
            print(f"  ⚠️ Erro ao remover duplicata: {e}")

    # 5. Remover arquivos de backup (.bak*, .tmp)
    print("[5/7] Removendo arquivos de backup (.bak*, .tmp)...")
    for p in ROOT_DIR.rglob("*.bak*"):
        if p.is_file():
            try:
                p.unlink()
            except Exception:
                pass

    # 6. Remover venv/node_modules locais de dev
    for dev_dir_name in [
        ROOT_DIR / "server" / "projeto_bypass" / "venv",
        ROOT_DIR / "server" / "web-app" / "node_modules",
    ]:
        if dev_dir_name.exists():
            s = get_dir_size_mb(dev_dir_name)
            print(f"[6/7] Removendo pasta dev '{dev_dir_name.name}' ({s:.2f} MB)...")
            try:
                shutil.rmtree(dev_dir_name, ignore_errors=True)
                print(f"  ✅ '{dev_dir_name.name}' removido!")
            except Exception as e:
                print(f"  ⚠️ Erro ao remover {dev_dir_name.name}: {e}")

    # 7. Limpar __pycache__, .pyc e caches temporários
    print("[7/7] Limpando __pycache__, arquivos .pyc e caches temporários...")
    for p in ROOT_DIR.rglob("__pycache__"):
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
    for p in ROOT_DIR.rglob("*.pyc"):
        try:
            p.unlink()
        except Exception:
            pass

    for temp_path in [
        ROOT_DIR / "server" / "cache",
        ROOT_DIR / "server" / "downloads",
        ROOT_DIR / "server" / "uploads",
        ROOT_DIR / "server" / "scratch",
        ROOT_DIR / "server" / "projeto_bypass" / "temp",
        ROOT_DIR / "server" / "projeto_bypass" / "dropper_rebuild" / "temp",
        ROOT_DIR / "server" / "projeto_bypass" / "dropper_new" / "temp",
    ]:
        if temp_path.exists():
            for child in temp_path.iterdir():
                try:
                    if child.is_file():
                        child.unlink()
                    elif child.is_dir():
                        shutil.rmtree(child, ignore_errors=True)
                except Exception:
                    pass

    print("  ✅ Caches e temporários limpos com sucesso!")

    final_size = get_dir_size_mb(ROOT_DIR)
    saved_size = initial_size - final_size

    print("\n" + "=" * 60)
    print("🎉 OTIMIZAÇÃO CONCLUÍDA COM SUCESSO!")
    print("=" * 60)
    print(f"📊 Tamanho Anterior:  {initial_size:.2f} MB")
    print(f"📊 Tamanho Atual:     {final_size:.2f} MB")
    print(f"⚡ Espaço Economizado: {saved_size:.2f} MB ({ (saved_size / initial_size * 100 if initial_size > 0 else 0):.1f}% de redução)")
    print("=" * 60)

if __name__ == "__main__":
    optimize()

