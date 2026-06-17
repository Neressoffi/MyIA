"""Test bout en bout : generation CV/PDF via l'API JARVIS."""
from __future__ import annotations

import json
import sys

import httpx

BASE = "http://127.0.0.1:8765"
MOT_DE_PASSE = sys.argv[1] if len(sys.argv) > 1 else "test1234"


def auth_headers() -> dict[str, str]:
    r = httpx.post(f"{BASE}/api/auth/login", json={"mot_de_passe": MOT_DE_PASSE}, timeout=15)
    if r.status_code != 200:
        print(f"ECHEC login ({r.status_code}) : {r.text}")
        print("Indiquez le bon mot de passe : python backend/test_cv_pdf.py VOTRE_MOT_DE_PASSE")
        sys.exit(1)
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_chat_cv(h: dict) -> bool:
    phrase = "Crée un CV pour développeur Python junior en PDF"
    r = httpx.post(
        f"{BASE}/api/chat",
        json={"messages": [{"role": "user", "content": phrase}], "mode": "auto"},
        headers=h,
        timeout=180,
    )
    if r.status_code != 200:
        print(f"  chat HTTP {r.status_code}")
        return False
    for line in r.text.split("\n"):
        if not line.startswith("data:"):
            continue
        ev = json.loads(line[5:].strip())
        if ev.get("erreur"):
            print(f"  erreur chat : {ev['erreur']}")
            return False
        if ev.get("document"):
            b64 = ev["document"].get("base64", "")
            print(f"  chat PDF OK ({len(b64)} chars base64)")
            return len(b64) > 100
    print("  chat : pas de document dans le flux")
    return False


def test_api_document(h: dict) -> bool:
    r = httpx.post(
        f"{BASE}/api/document",
        json={"instruction": "CV data scientist", "type_doc": "cv"},
        headers=h,
        timeout=180,
    )
    if r.status_code != 200:
        print(f"  /api/document HTTP {r.status_code} : {r.text[:120]}")
        return False
    data = r.json()
    r2 = httpx.post(
        f"{BASE}/api/document/fichier",
        json={
            "texte": data["texte"],
            "format": "pdf",
            "titre": data["titre"],
            "type_doc": "cv",
        },
        headers=h,
        timeout=60,
    )
    ok = r2.status_code == 200 and len(r2.content) > 500
    print(f"  api/document + fichier : {'OK' if ok else 'ECHEC'} ({len(r2.content)} octets)")
    return ok


def main() -> None:
    print("=== Test CV/PDF JARVIS ===")
    print(f"Serveur : {BASE}")
    try:
        httpx.get(f"{BASE}/api/auth/status", timeout=5).raise_for_status()
    except Exception as exc:
        print(f"Serveur inaccessible : {exc}")
        sys.exit(1)

    h = auth_headers()
    print("Auth OK")
    ok1 = test_api_document(h)
    ok2 = test_chat_cv(h)
    if ok1 and ok2:
        print("RESULTAT : TOUT OK")
        sys.exit(0)
    print("RESULTAT : ECHEC")
    sys.exit(1)


if __name__ == "__main__":
    main()
