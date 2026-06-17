"""Journalisation des visites et conversations (dashboard administrateur)."""

from __future__ import annotations

import json
import secrets
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from . import config

_RACINE = Path(__file__).resolve().parent.parent
_DOSSIER = _RACINE / "donnees"
_FICHIER = _DOSSIER / "analytics.json"
_VERROU = threading.Lock()
_MAX_VISITES = 2000
_MAX_CONVERSATIONS = 500

_admin_sessions: dict[str, float] = {}
_ADMIN_DUREE = 12 * 3600


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mot_de_passe_admin() -> str:
    env = (getattr(config, "ADMIN_PASSWORD", None) or "").strip()
    if env:
        return env
    fichier = _RACINE / "admin_password.txt"
    if fichier.exists():
        for ligne in fichier.read_text(encoding="utf-8").splitlines():
            ligne = ligne.strip()
            if ligne and not ligne.startswith("#"):
                return ligne
    return ""


def admin_configure() -> bool:
    return bool(_mot_de_passe_admin())


def admin_connecter(mot_de_passe: str) -> str:
    attendu = _mot_de_passe_admin()
    if not attendu:
        raise ValueError("dashboard non configure (JARVIS_ADMIN_PASSWORD)")
    if mot_de_passe != attendu:
        raise ValueError("mot de passe admin incorrect")
    token = secrets.token_urlsafe(32)
    _admin_sessions[token] = time.time() + _ADMIN_DUREE
    return token


def admin_session_valide(token: Optional[str]) -> bool:
    if not token:
        return False
    expiry = _admin_sessions.get(token)
    if not expiry:
        return False
    if time.time() > expiry:
        _admin_sessions.pop(token, None)
        return False
    _admin_sessions[token] = time.time() + _ADMIN_DUREE
    return True


def extraire_token_admin(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None


def client_ip(request) -> str:
    """IP reelle (Render/proxy : X-Forwarded-For)."""
    forwarded = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "inconnue"


def _charger() -> dict:
    _DOSSIER.mkdir(parents=True, exist_ok=True)
    if not _FICHIER.exists():
        return {"visites": [], "conversations": []}
    try:
        return json.loads(_FICHIER.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"visites": [], "conversations": []}


def _sauver(data: dict) -> None:
    _DOSSIER.mkdir(parents=True, exist_ok=True)
    _FICHIER.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def enregistrer_visite(ip: str, chemin: str, user_agent: str = "") -> None:
    if not getattr(config, "ANALYTICS_ENABLED", True):
        return
    entree = {
        "ip": ip,
        "chemin": chemin,
        "user_agent": (user_agent or "")[:300],
        "ts": _now(),
    }
    with _VERROU:
        data = _charger()
        data.setdefault("visites", []).append(entree)
        if len(data["visites"]) > _MAX_VISITES:
            data["visites"] = data["visites"][-_MAX_VISITES:]
        _sauver(data)


def debut_conversation(
    ip: str,
    question: str,
    user_agent: str = "",
    piece_jointe: Optional[str] = None,
    type_action: str = "chat",
) -> str:
    """Cree une entree de conversation et renvoie son id."""
    conv_id = str(uuid.uuid4())
    if not getattr(config, "ANALYTICS_ENABLED", True):
        return conv_id
    entree = {
        "id": conv_id,
        "ip": ip,
        "user_agent": (user_agent or "")[:300],
        "type": type_action,
        "debut": _now(),
        "fin": None,
        "piece_jointe": piece_jointe,
        "messages": [],
    }
    if question.strip():
        entree["messages"].append({
            "role": "user",
            "content": question.strip()[:8000],
            "ts": _now(),
        })
    with _VERROU:
        data = _charger()
        data.setdefault("conversations", []).append(entree)
        if len(data["conversations"]) > _MAX_CONVERSATIONS:
            data["conversations"] = data["conversations"][-_MAX_CONVERSATIONS:]
        _sauver(data)
    return conv_id


def fin_conversation(
    conv_id: str,
    reponse: str,
    erreur: str = "",
    meta: Optional[dict] = None,
) -> None:
    if not getattr(config, "ANALYTICS_ENABLED", True) or not conv_id:
        return
    with _VERROU:
        data = _charger()
        for conv in reversed(data.get("conversations", [])):
            if conv.get("id") == conv_id:
                conv["fin"] = _now()
                if reponse.strip():
                    conv["messages"].append({
                        "role": "assistant",
                        "content": reponse.strip()[:12000],
                        "ts": _now(),
                    })
                if erreur:
                    conv["erreur"] = erreur[:500]
                if meta:
                    conv["meta"] = meta
                break
        _sauver(data)


def rapport() -> dict:
    data = _charger()
    visites = data.get("visites", [])
    convs = data.get("conversations", [])

    ips: dict[str, dict] = {}
    for v in visites:
        ip = v.get("ip", "?")
        if ip not in ips:
            ips[ip] = {"ip": ip, "visites": 0, "derniere": v.get("ts"), "user_agent": v.get("user_agent", "")}
        ips[ip]["visites"] += 1
        ips[ip]["derniere"] = v.get("ts")

    for c in convs:
        ip = c.get("ip", "?")
        if ip not in ips:
            ips[ip] = {"ip": ip, "visites": 0, "derniere": c.get("debut"), "user_agent": c.get("user_agent", "")}
        ips[ip]["conversations"] = ips[ip].get("conversations", 0) + 1
        ips[ip]["derniere"] = c.get("fin") or c.get("debut")

    liste_ips = sorted(ips.values(), key=lambda x: x.get("derniere") or "", reverse=True)

    return {
        "total_visites": len(visites),
        "total_conversations": len(convs),
        "ips_uniques": len(liste_ips),
        "visiteurs": liste_ips,
        "conversations": sorted(convs, key=lambda x: x.get("debut") or "", reverse=True),
        "admin_configure": admin_configure(),
    }


def conversation_par_id(conv_id: str) -> Optional[dict]:
    for c in _charger().get("conversations", []):
        if c.get("id") == conv_id:
            return c
    return None
