"""
Supervisor / Watchdog para Gangstar Remote.
Monitora e garante que main.py (porta 5000) e app.py (porta 8088) permaneçam online 24/7.
Se algum serviço travar ou fechar, o supervisor o reinicia imediatamente.
"""
import os
import sys
import time
import subprocess
import urllib.request
from pathlib import Path

# Configura UTF-8 na saída padrão do Python no Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SERVER_DIR = Path(__file__).resolve().parent
BYPASS_DIR = SERVER_DIR / "projeto_bypass"

def check_http(url: str, timeout: int = 5) -> bool:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'GangstarSupervisor/1.0'})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status in (200, 302, 301, 307)
    except Exception:
        return False

def kill_process_on_port(port: int):
    try:
        cmd = f'powershell -Command "Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }}"'
        subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def start_main():
    print("[SUPERVISOR] Iniciando main.py (Porta 5000)...")
    kill_process_on_port(5000)
    return subprocess.Popen([sys.executable, "-u", "main.py"], cwd=str(SERVER_DIR))

def start_bypass():
    print("[SUPERVISOR] Iniciando app.py (Porta 8088)...")
    kill_process_on_port(8088)
    return subprocess.Popen([sys.executable, "-u", "app.py"], cwd=str(BYPASS_DIR))

def main():
    print("=" * 60)
    print("   GANGSTAR REMOTE - SUPERVISOR DE SERVICOS 24/7")
    print("=" * 60)

    p_main = start_main()
    time.sleep(3)
    p_bypass = start_bypass()

    consecutive_main_failures = 0
    consecutive_bypass_failures = 0

    while True:
        time.sleep(10)
        
        # Checa main.py (porta 5000)
        if p_main.poll() is not None or not check_http("http://127.0.0.1:5000/login"):
            consecutive_main_failures += 1
            print(f"[SUPERVISOR] AVISO: Falha na resposta da porta 5000 ({consecutive_main_failures}/3)")
            if consecutive_main_failures >= 3:
                print("[SUPERVISOR] REINICIANDO main.py (Porta 5000)...")
                try:
                    p_main.terminate()
                except Exception:
                    pass
                p_main = start_main()
                consecutive_main_failures = 0
        else:
            consecutive_main_failures = 0

        # Checa app.py (porta 8088)
        if p_bypass.poll() is not None or not check_http("http://127.0.0.1:8088/login"):
            consecutive_bypass_failures += 1
            print(f"[SUPERVISOR] AVISO: Falha na resposta da porta 8088 ({consecutive_bypass_failures}/3)")
            if consecutive_bypass_failures >= 3:
                print("[SUPERVISOR] REINICIANDO app.py (Porta 8088)...")
                try:
                    p_bypass.terminate()
                except Exception:
                    pass
                p_bypass = start_bypass()
                consecutive_bypass_failures = 0
        else:
            consecutive_bypass_failures = 0

if __name__ == "__main__":
    main()
