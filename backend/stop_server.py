"""Arrete proprement tout processus qui ecoute sur le port JARVIS."""
from __future__ import annotations

import os
import subprocess
import sys
import time

PORT = int(os.environ.get("JARVIS_SERVER_PORT", "8765"))
MAX_ESSAIS = 8


def _processus_existe(pid: int) -> bool:
    r = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}"],
        capture_output=True,
        text=True,
        errors="ignore",
    )
    return str(pid) in r.stdout


def _pids_sur_port(port: int) -> set[int]:
    pids: set[int] = set()
    try:
        out = subprocess.check_output(
            ["netstat", "-ano"], text=True, errors="ignore"
        )
    except Exception:  # noqa: BLE001
        return pids
    for line in out.splitlines():
        if f":{port}" not in line or "LISTENING" not in line:
            continue
        parts = line.split()
        if not parts:
            continue
        try:
            pids.add(int(parts[-1]))
        except ValueError:
            continue
    return pids


def arreter(port: int = PORT) -> bool:
    for _ in range(MAX_ESSAIS):
        pids = _pids_sur_port(port)
        vivants = {p for p in pids if _processus_existe(p)}
        if not pids:
            print(f"Port {port} libre.")
            return True
        if not vivants and pids:
            print(f"Port {port} bloque par un processus fantome {pids}.")
            print("Utilisez le port alternatif ou redemarrez le PC.")
            return False
        for pid in vivants:
            print(f"Arret du processus {pid}...")
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
            )
        time.sleep(1.5)
    reste = _pids_sur_port(port)
    if reste:
        print(f"ERREUR: port {port} encore occupe par {reste}", file=sys.stderr)
        return False
    return True


if __name__ == "__main__":
    sys.exit(0 if arreter() else 1)
