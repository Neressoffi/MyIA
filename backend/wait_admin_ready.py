"""Attend que le serveur dashboard admin soit pret."""
import os
import sys
import time
import urllib.error
import urllib.request

PORT = int(os.environ.get("JARVIS_ADMIN_PORT", "8767"))
URL = f"http://127.0.0.1:{PORT}/api/admin/status"
MAX = 30

for _ in range(MAX):
    try:
        with urllib.request.urlopen(URL, timeout=2) as resp:
            if resp.status == 200:
                print(f"Dashboard admin pret sur le port {PORT}.")
                sys.exit(0)
    except (urllib.error.URLError, TimeoutError, OSError):
        pass
    time.sleep(1)

print(f"ERREUR: pas de reponse sur http://127.0.0.1:{PORT}", file=sys.stderr)
sys.exit(1)
