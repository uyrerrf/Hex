"""
Servidor de Redirecionamento Automático na Porta 80 para a Porta 5000.
Garante que qualquer pessoa acessando http://179.0.179.195 (sem digitar :5000)
seja automaticamente redirecionada para a porta 5000 do painel.
"""
import http.server
import socketserver
import sys

class RedirectHandler(http.server.BaseHTTPRequestHandler):
    def respond_redirect(self):
        try:
            host_header = self.headers.get('Host', '179.0.179.195')
            host = host_header.split(':')[0] if host_header else '179.0.179.195'
            target_url = f"http://{host}:5000{self.path}"
            self.send_response(302)
            self.send_header('Location', target_url)
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
        except Exception:
            pass

    def do_GET(self):
        self.respond_redirect()

    def do_POST(self):
        self.respond_redirect()

    def do_HEAD(self):
        self.respond_redirect()

    def do_OPTIONS(self):
        self.respond_redirect()

    def log_message(self, format, *args):
        pass

if __name__ == '__main__':
    PORT = 80
    socketserver.TCPServer.allow_reuse_address = True
    try:
        with socketserver.TCPServer(("0.0.0.0", PORT), RedirectHandler) as httpd:
            print(f"[*] Redirecionador da Porta 80 -> Porta 5000 rodando na porta {PORT}...")
            httpd.serve_forever()
    except Exception as e:
        print(f"[-] Erro ao iniciar redirecionador na porta 80: {e}")
