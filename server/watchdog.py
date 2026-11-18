"""
Watchdog Autônomo e Ultra-Resiliente do Servidor Gangstar C&C (Porta 5000), Redirecionador (Porta 80) e Bypass (Porta 8088/8080).
Monitora constantemente as portas 5000, 80 e 8080.
"""
import time
import os
import subprocess
import sys
import socket
from datetime import datetime

PORT_MAIN = int(os.environ.get("GANGSTAR_PORT", "5000"))
PORT_HTTP80 = 80
PORT_BYPASS = 8088
SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
BYPASS_DIR = os.path.join(SERVER_DIR, "projeto_bypass")

print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [WATCHDOG] Guardião Autônomo iniciado (Portas {PORT_MAIN}, {PORT_HTTP80} e {PORT_BYPASS})...")

def is_port_open(port: int, timeout: float = 4.0) -> bool:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        res = s.connect_ex(("127.0.0.1", port))
        s.close()
        return res == 0
    except Exception:
        return False

def free_port(port: int):
    try:
        ps_cmd = f"Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }}"
        subprocess.run(["powershell", "-Command", ps_cmd], cwd=SERVER_DIR, timeout=8)
    except Exception:
        pass

def ensure_adb_reverse():
    try:
        adb_paths = [
            "adb",
            r"C:\Android\Sdk\platform-tools\adb.exe",
            os.path.expanduser(r"~\AppData\Local\Android\Sdk\platform-tools\adb.exe")
        ]
        adb_bin = None
        for p in adb_paths:
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
                if f"tcp:{PORT_MAIN} tcp:{PORT_MAIN}" not in rev_res.stdout:
                    subprocess.run([adb_bin, "reverse", f"tcp:{PORT_MAIN}", f"tcp:{PORT_MAIN}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3)
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] [WATCHDOG] Ponte reversa USB restabelecida: tcp:{PORT_MAIN} -> tcp:{PORT_MAIN}")
    except Exception:
        pass

main_fail_count = 0
http80_fail_count = 0
bypass_fail_count = 0

while True:
    try:
        ensure_adb_reverse()

        # 1. Verifica Servidor Principal C&C (Porta 5000)
        if not is_port_open(PORT_MAIN, timeout=4.0):
            main_fail_count += 1
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [WATCHDOG ⚠️] Aviso: porta {PORT_MAIN} respondeu com lentidão ou falha ({main_fail_count}/3)...")
            if main_fail_count >= 3:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] [WATCHDOG 🚨] Servidor C&C (Porta {PORT_MAIN}) indisponível após 3 tentativas! Reiniciando...")
                free_port(PORT_MAIN)
                time.sleep(2)
                subprocess.Popen([sys.executable, "main.py"], cwd=SERVER_DIR)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] [WATCHDOG ✅] Servidor main.py reiniciado com sucesso!")
                main_fail_count = 0
                time.sleep(6)
        else:
            main_fail_count = 0

        # 2. Verifica Redirecionador da Porta 80
        if not is_port_open(PORT_HTTP80, timeout=3.0):
            http80_fail_count += 1
            if http80_fail_count >= 3:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] [WATCHDOG 🚨] Redirecionador Porta 80 indisponível! Reiniciando...")
                free_port(PORT_HTTP80)
                time.sleep(1)
                redirect_py = os.path.join(SERVER_DIR, "redirect_port80.py")
                if os.path.exists(redirect_py):
                    subprocess.Popen([sys.executable, redirect_py], cwd=SERVER_DIR)
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] [WATCHDOG ✅] Redirecionador Porta 80 reiniciado!")
                http80_fail_count = 0
        else:
            http80_fail_count = 0

        # 3. Verifica Servidor Bypass / Dropper (Porta 8088/8080)
        if os.path.exists(BYPASS_DIR):
            if not is_port_open(PORT_BYPASS, timeout=3.0) and not is_port_open(8080, timeout=3.0):
                bypass_fail_count += 1
                if bypass_fail_count >= 3:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] [WATCHDOG 🚨] Servidor Bypass indisponível! Reiniciando...")
                    free_port(PORT_BYPASS)
                    free_port(8080)
                    time.sleep(1)
                    if os.path.exists(os.path.join(BYPASS_DIR, "launch_8080.py")):
                        subprocess.Popen([sys.executable, os.path.join(BYPASS_DIR, "launch_8080.py")], cwd=BYPASS_DIR)
                    elif os.path.exists(os.path.join(BYPASS_DIR, "app.py")):
                        subprocess.Popen([sys.executable, os.path.join(BYPASS_DIR, "app.py")], cwd=BYPASS_DIR)
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] [WATCHDOG ✅] Servidor Bypass reiniciado com sucesso!")
                    bypass_fail_count = 0
            else:
                bypass_fail_count = 0

        time.sleep(6)

    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [WATCHDOG ❌] Erro no loop do watchdog: {e}")
        time.sleep(6)
