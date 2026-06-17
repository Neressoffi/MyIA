"""Attend que le serveur JARVIS securise soit pret."""
import os
import sys
import time
import urllib.error
import urllib.request

PORT = int(os.environ.get("JARVIS_SERVER_PORT", "8765"))
URL = f"http://127.0.0.1:{PORT}/api/auth/status"
MAX = 30

for _ in range(MAX):
    try:
        with urllib.request.urlopen(URL, timeout=2) as resp:
            if resp.status == 200:
                print(f"Serveur securise pret sur le port {PORT}.")
                sys.exit(0)
    except (urllib.error.URLError, TimeoutError, OSError):
        pass
    time.sleep(1)

print(f"ERREUR: pas de reponse sur http://127.0.0.1:{PORT}", file=sys.stderr)
sys.exit(1)
