"""Securite JARVIS : authentification, chiffrement local, sessions privees.

Seul le proprietaire (mot de passe) peut acceder aux donnees.
Les fichiers sensibles dans donnees/ sont chiffres au repos.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from . import config

_RACINE = Path(__file__).resolve().parent.parent
_AUTH_FILE = _RACINE / ".jarvis_auth"
_DONNEES = _RACINE / "donnees"
_VERROU = threading.Lock()

_sessions: dict[str, float] = {}
_fernet: Optional[Fernet] = None
_config_cache: Optional[dict] = None

SESSION_DUREE = 24 * 3600
PBKDF2_ITERATIONS = 480_000
MIN_MOT_DE_PASSE = 6

_DEMO_TOKEN = "demo-public"

_ORIGINES_AUTORISEES = {
    "http://127.0.0.1:8765",
    "http://localhost:8765",
}


def mode_demo() -> bool:
    """True en ligne : acces public sans mot de passe, sans chiffrement perso."""
    return config.DEMO_MODE


def token_demo() -> str:
    return _DEMO_TOKEN


def _hash_mot_de_passe(mot_de_passe: str, sel: bytes) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        mot_de_passe.encode("utf-8"),
        sel,
        PBKDF2_ITERATIONS,
    )
    return base64.b64encode(digest).decode("ascii")


def _derive_cle_chiffrement(mot_de_passe: str, sel: bytes) -> Fernet:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=sel,
        iterations=PBKDF2_ITERATIONS,
    )
    cle = base64.urlsafe_b64encode(kdf.derive(mot_de_passe.encode("utf-8")))
    return Fernet(cle)


def _charger_config() -> dict:
    global _config_cache
    if not _AUTH_FILE.exists():
        _config_cache = {}
        return _config_cache
    if _config_cache is not None:
        return _config_cache
    try:
        _config_cache = json.loads(_AUTH_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        _config_cache = {}
    return _config_cache


def _sauver_config(data: dict) -> None:
    global _config_cache
    with _VERROU:
        _AUTH_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _config_cache = data


def est_configure() -> bool:
    if mode_demo():
        return False
    cfg = _charger_config()
    return bool(cfg.get("password_hash"))


def cloud_autorise() -> bool:
    if mode_demo():
        return bool(config.CLOUD_API_KEY)
    cfg = _charger_config()
    if not cfg:
        return True
    return bool(cfg.get("cloud_autorise", True))


def configurer(mot_de_passe: str) -> str:
    """Premiere configuration : mot de passe + chiffrement."""
    if est_configure():
        raise ValueError("deja configure")
    if len(mot_de_passe) < MIN_MOT_DE_PASSE:
        raise ValueError(f"mot de passe trop court (min {MIN_MOT_DE_PASSE} caracteres)")

    sel_auth = secrets.token_bytes(16)
    sel_data = secrets.token_bytes(16)
    data = {
        "password_hash": _hash_mot_de_passe(mot_de_passe, sel_auth),
        "salt": base64.b64encode(sel_auth).decode("ascii"),
        "data_salt": base64.b64encode(sel_data).decode("ascii"),
        "cloud_autorise": True,
        "version": 1,
    }
    _sauver_config(data)
    return connecter(mot_de_passe)


def connecter(mot_de_passe: str) -> str:
    """Verifie le mot de passe et ouvre une session."""
    cfg = _charger_config()
    if not cfg.get("password_hash"):
        raise ValueError("non configure")

    sel = base64.b64decode(cfg["salt"])
    if not secrets.compare_digest(_hash_mot_de_passe(mot_de_passe, sel), cfg["password_hash"]):
        raise ValueError("mot de passe incorrect")

    sel_data = base64.b64decode(cfg["data_salt"])
    global _fernet
    _fernet = _derive_cle_chiffrement(mot_de_passe, sel_data)

    token = secrets.token_urlsafe(32)
    _sessions[token] = time.time() + SESSION_DUREE
    _migrer_fichiers_en_clair()
    return token


def deconnecter(token: str) -> None:
    _sessions.pop(token, None)
    if not _sessions:
        global _fernet
        _fernet = None


def session_valide(token: Optional[str]) -> bool:
    if mode_demo():
        return True
    if not token:
        return False
    expiry = _sessions.get(token)
    if not expiry:
        return False
    if time.time() > expiry:
        _sessions.pop(token, None)
        return False
    _sessions[token] = time.time() + SESSION_DUREE
    return True


def extraire_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None


def chemin_autorise(origin: Optional[str], host: Optional[str]) -> bool:
    if mode_demo():
        return True
    if origin:
        base = origin.rstrip("/")
        port = _port_depuis_host(host)
        for o in _ORIGINES_AUTORISEES:
            if base == o.rstrip("/"):
                return True
            if port and base == f"http://127.0.0.1:{port}":
                return True
            if port and base == f"http://localhost:{port}":
                return True
    if host and (host.startswith("127.0.0.1") or host.startswith("localhost")):
        return True
    return False


def _port_depuis_host(host: Optional[str]) -> Optional[str]:
    if not host or ":" not in host:
        return None
    return host.rsplit(":", 1)[-1]


def mettre_a_jour_origines(port: int) -> None:
    global _ORIGINES_AUTORISEES
    _ORIGINES_AUTORISEES = {
        f"http://127.0.0.1:{port}",
        f"http://localhost:{port}",
    }


def nom_fichier_sur(fichier: str) -> str:
    """Nettoie un nom de fichier (anti path traversal)."""
    nom = Path(fichier or "document").name.strip()
    nom = re.sub(r'[<>:"|?*\x00-\x1f]', "_", nom)
    return nom or "document"


def lire_json_protege(chemin: Path, defaut: Any) -> Any:
    """Lit un JSON chiffre ou en clair (migration automatique)."""
    if not chemin.exists():
        return defaut
    brut = chemin.read_bytes()
    if not brut:
        return defaut
    if mode_demo() or (not _fernet and not brut.startswith(b"gAAAA")):
        try:
            return json.loads(brut.decode("utf-8"))
        except Exception:  # noqa: BLE001
            return defaut
    if _fernet and brut.startswith(b"gAAAA"):
        try:
            dechiffre = _fernet.decrypt(brut)
            return json.loads(dechiffre.decode("utf-8"))
        except InvalidToken:
            pass
    try:
        return json.loads(brut.decode("utf-8"))
    except Exception:  # noqa: BLE001
        return defaut


def ecrire_json_protege(chemin: Path, data: Any) -> None:
    """Ecrit un JSON chiffre si session active, sinon refus (sauf mode demo)."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    if mode_demo():
        with _VERROU:
            chemin.write_bytes(payload)
        return
    if not _fernet:
        raise PermissionError("session verrouillee")
    chiffre = _fernet.encrypt(payload)
    with _VERROU:
        chemin.write_bytes(chiffre)


def _migrer_fichiers_en_clair() -> None:
    """Chiffre les anciens fichiers JSON en clair au premier deverrouillage."""
    if not _fernet:
        return
    for nom in ("memoire.json", "index_documents.json"):
        chemin = _DONNEES / nom
        if not chemin.exists():
            continue
        brut = chemin.read_bytes()
        if brut.startswith(b"gAAAA"):
            continue
        try:
            data = json.loads(brut.decode("utf-8"))
            ecrire_json_protege(chemin, data)
        except Exception:  # noqa: BLE001
            pass


def definir_cloud_autorise(autorise: bool) -> dict:
    cfg = _charger_config()
    if not cfg:
        raise ValueError("non configure")
    cfg["cloud_autorise"] = bool(autorise)
    _sauver_config(cfg)
    return {"cloud_autorise": cfg["cloud_autorise"]}


def changer_mot_de_passe(ancien: str, nouveau: str) -> None:
    if len(nouveau) < MIN_MOT_DE_PASSE:
        raise ValueError(f"mot de passe trop court (min {MIN_MOT_DE_PASSE} caracteres)")
    cfg = _charger_config()
    sel = base64.b64decode(cfg["salt"])
    if not secrets.compare_digest(_hash_mot_de_passe(ancien, sel), cfg["password_hash"]):
        raise ValueError("ancien mot de passe incorrect")

    sel_auth = secrets.token_bytes(16)
    sel_data = secrets.token_bytes(16)
    cfg["password_hash"] = _hash_mot_de_passe(nouveau, sel_auth)
    cfg["salt"] = base64.b64encode(sel_auth).decode("ascii")
    cfg["data_salt"] = base64.b64encode(sel_data).decode("ascii")
    _sauver_config(cfg)

    global _fernet
    _fernet = _derive_cle_chiffrement(nouveau, sel_data)
    for nom in ("memoire.json", "index_documents.json"):
        chemin = _DONNEES / nom
        if chemin.exists():
            data = lire_json_protege(chemin, None)
            if data is not None:
                ecrire_json_protege(chemin, data)
