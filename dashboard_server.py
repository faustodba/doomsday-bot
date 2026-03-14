# ==============================================================================
#  DOOMSDAY BOT V5 - dashboard_server.py
#  Mini server HTTP per servire dashboard.html + status.json
#
#  Avvio manuale:   python dashboard_server.py
#  Avvio da main:   import dashboard_server (si avvia da solo in thread daemon)
#
#  URL dashboard:   http://localhost:8080/dashboard.html
# ==============================================================================

import http.server
import threading
import os
import sys

PORT = 8080

def _run():
    # Serve i file dalla cartella dove si trova questo script
    cartella = os.path.dirname(os.path.abspath(__file__))
    os.chdir(cartella)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass  # Silenzia i log HTTP per non sporcare la console

    server = http.server.HTTPServer(("", PORT), Handler)
    print(f"[dashboard] Server avviato → http://localhost:{PORT}/dashboard.html")
    server.serve_forever()

def avvia():
    """Avvia il server in background (thread daemon). Chiamare da main.py."""
    t = threading.Thread(target=_run, daemon=True)
    t.start()

# Se lanciato direttamente (python dashboard_server.py) gira in foreground
if __name__ == "__main__":
    print(f"[dashboard] Avvio server su porta {PORT}...")
    print(f"[dashboard] Apri → http://localhost:{PORT}/dashboard.html")
    print(f"[dashboard] Ctrl+C per fermare")
    _run()
