"""JARVIS - Assistant IA local, gratuit et open source.

Backend FastAPI qui relie :
- le modele de langage local (via Ollama)
- la reconnaissance vocale offline (faster-whisper)
- l'interface web (servie en statique)
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import tempfile
import urllib.parse
from pathlib import Path
from typing import List, Optional

import httpx
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, diagnostic, documents, memoire, outils, rag, securite, vision

app = FastAPI(title="JARVIS - Assistant IA local")

_origines = ["*"] if config.DEMO_MODE else [
    f"http://127.0.0.1:{config.PORT}",
    f"http://localhost:{config.PORT}",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origines,
    allow_credentials=not config.DEMO_MODE,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Le modele Whisper est charge une seule fois (paresseusement).
_whisper_model = None


def get_whisper_model():
    """Charge le modele de reconnaissance vocale au premier usage."""
    if config.DISABLE_WHISPER:
        raise RuntimeError("transcription vocale indisponible en mode demo")
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel

        _whisper_model = WhisperModel(
            config.WHISPER_MODEL,
            device="cpu",
            compute_type="int8",
            # Utilise tous les coeurs logiques du CPU pour aller plus vite.
            cpu_threads=os.cpu_count() or 4,
            num_workers=1,
        )
    return _whisper_model


@app.on_event("startup")
async def _prechauffe():
    """Precharge les modeles des le demarrage (en arriere-plan)."""
    if not config.DEMO_MODE:
        securite.mettre_a_jour_origines(config.PORT)
    import threading

    if not config.DISABLE_WHISPER:
        threading.Thread(target=get_whisper_model, daemon=True).start()

    if config.DEMO_MODE:
        return

    def _warm_llm():
        try:
            httpx.post(
                f"{config.OLLAMA_HOST}/api/chat",
                json={
                    "model": config.MODEL_NAME,
                    "messages": [{"role": "user", "content": "ok"}],
                    "stream": False,
                    "keep_alive": config.KEEP_ALIVE,
                    "options": config.GEN_OPTIONS,
                },
                timeout=120,
            )
        except Exception:  # noqa: BLE001
            pass

    threading.Thread(target=_warm_llm, daemon=True).start()


# --------------------------------------------------------------------------
# Modeles de donnees
# --------------------------------------------------------------------------
class Message(BaseModel):
    role: str
    content: str


class PieceJointe(BaseModel):
    nom: str
    texte: str


class ImageJointe(BaseModel):
    nom: str
    base64: str
    mime: str = "image/jpeg"


class ChatRequest(BaseModel):
    messages: List[Message]
    model: Optional[str] = None
    # "auto" (cloud si dispo, sinon local) | "cloud" | "local"
    mode: Optional[str] = "auto"
    # Fichier joint directement au message (pour le traiter : resumer, traduire...).
    piece_jointe: Optional[PieceJointe] = None
    # Image jointe (analyse vision : decrire, lire, repondre sur l'image).
    image_jointe: Optional[ImageJointe] = None


class TTSRequest(BaseModel):
    text: str
    gender: Optional[str] = "femme"
    rate: Optional[float] = 1.0
    pitch: Optional[float] = 1.0


class AuthSetupRequest(BaseModel):
    mot_de_passe: str
    confirmation: str


class AuthLoginRequest(BaseModel):
    mot_de_passe: str


class AuthCloudRequest(BaseModel):
    autorise: bool


class AuthPasswordRequest(BaseModel):
    ancien: str
    nouveau: str
    confirmation: str


# --------------------------------------------------------------------------
# Protection : authentification + en-tetes de securite
# --------------------------------------------------------------------------
from starlette.responses import JSONResponse  # noqa: E402


_ROUTES_API_PUBLIQUES = {
    "/api/auth/status",
    "/api/auth/setup",
    "/api/auth/login",
    "/api/auth/check",
    "/api/health",
}


def _erreur_stream(message: str):
    """Reponse SSE immediate avec un message d'erreur."""

    async def gen():
        yield _sse({"erreur": message})

    return StreamingResponse(gen(), media_type="text/event-stream")


def _message_cle_manquante() -> str:
    return (
        "Cle API Groq manquante sur le serveur. "
        "Sur Render : Environment → GROQ_API_KEY → votre cle Groq."
    )


@app.middleware("http")
async def protection_globale(request, call_next):
    path = request.url.path
    if path.startswith("/api/") and path not in _ROUTES_API_PUBLIQUES:
        token = securite.extraire_token(request.headers.get("authorization"))
        if not securite.session_valide(token):
            return JSONResponse({"detail": "Acces refuse. Connectez-vous."}, status_code=401)
        origin = request.headers.get("origin")
        if origin and not securite.chemin_autorise(origin, request.headers.get("host")):
            return JSONResponse({"detail": "Origine non autorisee."}, status_code=403)

    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "microphone=(self), camera=(self)"
    if path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return response


async def _lire_upload(fichier: UploadFile) -> bytes:
    """Lit un upload avec limite de taille (protection memoire)."""
    donnees = await fichier.read()
    if len(donnees) > config.MAX_UPLOAD_OCTETS:
        max_mo = config.MAX_UPLOAD_OCTETS // (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=f"Fichier trop volumineux (max {max_mo} Mo).",
        )
    return donnees


def _cloud_autorise() -> bool:
    """True si l'utilisateur a explicitement autorise le mode cloud."""
    return bool(config.CLOUD_API_KEY) and securite.cloud_autorise()


class ImageRequest(BaseModel):
    prompt: str
    largeur: Optional[int] = 1024
    hauteur: Optional[int] = 1024
    # Style visuel : photographic | artistic | anime | oil-painting | 3d-render | cartoon
    style: Optional[str] = "photographic"


# --------------------------------------------------------------------------
# Authentification (acces prive — seul le proprietaire)
# --------------------------------------------------------------------------
@app.get("/api/auth/status")
async def auth_status():
    """Etat de la securite (routes publiques, sans donnees sensibles)."""
    return {
        "configure": securite.est_configure(),
        "demo": securite.mode_demo(),
        "cloud_configure": bool(config.CLOUD_API_KEY),
        "cloud_autorise": securite.cloud_autorise(),
        "chiffrement": not securite.mode_demo(),
        "acces_local": not securite.mode_demo(),
    }


@app.get("/api/auth/check")
async def auth_check(authorization: Optional[str] = Header(None)):
    """Verifie si la session est active."""
    if securite.mode_demo():
        return {
            "configure": False,
            "authenticated": True,
            "demo": True,
            "cloud_autorise": securite.cloud_autorise(),
        }
    token = securite.extraire_token(authorization)
    return {
        "configure": securite.est_configure(),
        "authenticated": securite.session_valide(token),
        "cloud_autorise": securite.cloud_autorise(),
    }


@app.post("/api/auth/setup")
async def auth_setup(req: AuthSetupRequest):
    """Premiere configuration : choisir un mot de passe prive."""
    if securite.mode_demo():
        raise HTTPException(status_code=403, detail="Mode demo : pas de mot de passe requis.")
    if req.mot_de_passe != req.confirmation:
        raise HTTPException(status_code=400, detail="Les mots de passe ne correspondent pas.")
    if len(req.mot_de_passe) < securite.MIN_MOT_DE_PASSE:
        raise HTTPException(
            status_code=400,
            detail=f"Minimum {securite.MIN_MOT_DE_PASSE} caracteres.",
        )
    try:
        token = securite.configurer(req.mot_de_passe)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "token": token, "message": "JARVIS securise. Gardez ce mot de passe."}


@app.post("/api/auth/login")
async def auth_login(req: AuthLoginRequest):
    """Deverrouille JARVIS avec le mot de passe."""
    try:
        token = securite.connecter(req.mot_de_passe)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return {"ok": True, "token": token}


@app.post("/api/auth/logout")
async def auth_logout(authorization: Optional[str] = Header(None)):
    token = securite.extraire_token(authorization)
    if token:
        securite.deconnecter(token)
    return {"ok": True}


@app.post("/api/auth/cloud")
async def auth_cloud(req: AuthCloudRequest):
    """Autorise ou bloque l'envoi de donnees vers le cloud (Groq, etc.)."""
    try:
        return securite.definir_cloud_autorise(req.autorise)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/auth/password")
async def auth_password(req: AuthPasswordRequest):
    """Change le mot de passe (re-chiffre les donnees)."""
    if req.nouveau != req.confirmation:
        raise HTTPException(status_code=400, detail="Confirmation incorrecte.")
    try:
        securite.changer_mot_de_passe(req.ancien, req.nouveau)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


# --------------------------------------------------------------------------
# Endpoints API
# --------------------------------------------------------------------------
@app.get("/api/health")
async def health():
    """Verifie que Ollama est joignable et liste les modeles disponibles."""
    info = {
        "ollama": False,
        "models": [],
        "model_par_defaut": config.MODEL_NAME,
        "cloud_configure": bool(config.CLOUD_API_KEY),
        "cloud_autorise": securite.cloud_autorise(),
        "cloud_modele": config.CLOUD_MODEL if securite.cloud_autorise() else "",
        "vision_cloud": config.VISION_CLOUD_MODELS[0] if config.VISION_CLOUD_MODELS and securite.cloud_autorise() else "",
        "vision_local": config.VISION_LOCAL_MODELS,
        "securise": not securite.mode_demo(),
        "demo": securite.mode_demo(),
        "micro_disponible": (not config.DISABLE_WHISPER) or bool(config.CLOUD_API_KEY),
        "whisper_cloud": config.DISABLE_WHISPER and bool(config.CLOUD_API_KEY),
    }
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{config.OLLAMA_HOST}/api/tags")
            if r.status_code == 200:
                info["ollama"] = True
                info["models"] = [m["name"] for m in r.json().get("models", [])]
    except Exception as exc:  # noqa: BLE001
        info["erreur"] = str(exc)
    return info


@app.get("/api/diagnostic")
async def get_diagnostic():
    """Rapport de sante et de puissance de JARVIS (score, capacites, conseils)."""
    health_data = await health()
    return diagnostic.executer(health_data)


def _fichier_prompts() -> Path:
    """Bibliotheque de prompts versionnee (pas de donnees perso)."""
    racine = Path(__file__).resolve().parent
    candidats = (
        racine / "data" / "prompts_bibliotheque.json",
        racine.parent / "donnees" / "prompts_bibliotheque.json",
    )
    for chemin in candidats:
        if chemin.exists():
            return chemin
    return candidats[0]


@app.get("/api/prompts")
async def get_prompts():
    """Bibliotheque de 100+ prompts couvrant tous les sujets."""
    fichier = _fichier_prompts()
    if not fichier.exists():
        return {"total": 0, "categories": [], "prompts": []}
    return json.loads(fichier.read_text(encoding="utf-8"))


_internet_cache: dict = {"ok": False, "ts": 0.0}


async def _internet_disponible() -> bool:
    """Verifie rapidement si Internet est actif (cache 45 s pour eviter l'attente)."""
    import time

    now = time.time()
    if now - _internet_cache["ts"] < 45:
        return _internet_cache["ok"]
    ok = False
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            r = await client.get(f"{config.CLOUD_API_BASE}/models")
            ok = r.status_code < 500
    except Exception:  # noqa: BLE001
        ok = False
    _internet_cache["ok"] = ok
    _internet_cache["ts"] = now
    return ok


async def _stream_cloud_un_modele(messages, modele):
    """Streame la reponse d'UN modele cloud (format compatible OpenAI).

    Verifie le statut AVANT d'emettre le moindre token, pour pouvoir basculer
    proprement sur un autre modele en cas de quota atteint.
    """
    payload = {
        "model": modele,
        "messages": messages,
        "stream": True,
        "temperature": config.GEN_OPTIONS["temperature"],
        "top_p": config.GEN_OPTIONS["top_p"],
        "max_tokens": config.CLOUD_MAX_TOKENS,
    }
    headers = {"Authorization": f"Bearer {config.CLOUD_API_KEY}"}
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream(
            "POST",
            f"{config.CLOUD_API_BASE}/chat/completions",
            json=payload,
            headers=headers,
        ) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                raise RuntimeError(body.decode("utf-8", "ignore"))
            # 200 confirme : on annonce le modele puis on streame.
            yield _sse({"mode": "cloud", "modele": modele})
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line or not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    yield _sse({"done": True})
                    return
                obj = json.loads(data)
                token = obj.get("choices", [{}])[0].get("delta", {}).get("content", "")
                if token:
                    yield _sse({"token": token})
    yield _sse({"done": True})


def _est_quota_atteint(message: str) -> bool:
    """Detecte une erreur de quota / limite de debit (pour basculer de modele)."""
    m = message.lower()
    return "rate limit" in m or "rate_limit" in m or "429" in m or "quota" in m


def _essayer_modele_cloud_suivant(message: str) -> bool:
    """True si on peut tenter le modele cloud suivant (quota, deprecie, indisponible)."""
    m = message.lower()
    if _est_quota_atteint(m):
        return True
    return (
        "model_decommissioned" in m
        or "decommissioned" in m
        or "no longer supported" in m
        or "model_not_found" in m
        or "does not exist" in m
        or "not found" in m
    )


async def _stream_cloud(messages, rapide: bool = False):
    """Cascade des modeles cloud gratuits : on bascule si un quota est atteint."""
    modeles = list(config.CLOUD_MODELS)
    if rapide and config.CLOUD_MODEL_RAPIDE in modeles:
        modeles = [config.CLOUD_MODEL_RAPIDE] + [
            m for m in modeles if m != config.CLOUD_MODEL_RAPIDE
        ]
    derniere_erreur = None
    for modele in modeles:
        try:
            async for chunk in _stream_cloud_un_modele(messages, modele):
                yield chunk
            return  # succes
        except Exception as exc:  # noqa: BLE001
            derniere_erreur = exc
            # Quota atteint -> on tente le modele cloud suivant.
            if _essayer_modele_cloud_suivant(str(exc)):
                continue
            raise  # autre erreur -> on laisse le repli local gerer
    # Tous les modeles cloud ont echoue.
    raise RuntimeError(str(derniere_erreur) if derniere_erreur else "cloud indisponible")


async def _stream_vision_cloud_un(messages, modele):
    """Streame l'analyse vision via un modele cloud Groq."""
    payload = {
        "model": modele,
        "messages": messages,
        "stream": True,
        "temperature": 0.2,
        "top_p": 0.9,
        "max_tokens": config.CLOUD_MAX_TOKENS,
    }
    headers = {"Authorization": f"Bearer {config.CLOUD_API_KEY}"}
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream(
            "POST",
            f"{config.CLOUD_API_BASE}/chat/completions",
            json=payload,
            headers=headers,
        ) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                raise RuntimeError(body.decode("utf-8", "ignore"))
            yield _sse({"mode": "cloud", "modele": modele})
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line or not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    yield _sse({"done": True})
                    return
                obj = json.loads(data)
                token = obj.get("choices", [{}])[0].get("delta", {}).get("content", "")
                if token:
                    yield _sse({"token": token})
    yield _sse({"done": True})


async def _stream_vision_cloud(messages):
    """Cascade des modeles vision cloud."""
    derniere = None
    for modele in config.VISION_CLOUD_MODELS:
        try:
            async for chunk in _stream_vision_cloud_un(messages, modele):
                yield chunk
            return
        except Exception as exc:  # noqa: BLE001
            derniere = exc
            if _essayer_modele_cloud_suivant(str(exc)):
                continue
            raise
    raise RuntimeError(str(derniere) if derniere else "vision cloud indisponible")


async def _modeles_ollama() -> set[str]:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{config.OLLAMA_HOST}/api/tags")
            if r.status_code == 200:
                return {m["name"] for m in r.json().get("models", [])}
    except Exception:  # noqa: BLE001
        pass
    return set()


async def _stream_vision_local(messages, modele):
    """Streame l'analyse vision via Ollama (moondream, llava...)."""
    payload = {
        "model": modele,
        "messages": messages,
        "stream": True,
        "keep_alive": config.KEEP_ALIVE,
        "options": {"temperature": 0.2, "num_predict": 320},
    }
    yield _sse({"mode": "local", "modele": modele})
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream(
            "POST", f"{config.OLLAMA_HOST}/api/chat", json=payload
        ) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                raise RuntimeError(body.decode("utf-8", "ignore"))
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                data = json.loads(line)
                token = data.get("message", {}).get("content", "")
                if token:
                    yield _sse({"token": token})
                if data.get("done"):
                    yield _sse({"done": True})
                    return
    yield _sse({"done": True})


async def _stream_vision_local_cascade(messages):
    """Essaie les modeles vision locaux disponibles."""
    dispo = await _modeles_ollama()
    derniere = None
    for nom in config.VISION_LOCAL_MODELS:
        # Ollama peut avoir "moondream:latest" ou "moondream".
        candidats = [m for m in dispo if m == nom or m.startswith(nom + ":")]
        if not candidats:
            continue
        try:
            async for chunk in _stream_vision_local(messages, candidats[0]):
                yield chunk
            return
        except Exception as exc:  # noqa: BLE001
            derniere = exc
            continue
    raise RuntimeError(
        str(derniere)
        if derniere
        else "Aucun modele vision local (installe moondream ou llava via Ollama)."
    )


async def _stream_local(messages, model):
    """Streame la reponse depuis le modele local via Ollama (hors-ligne)."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "keep_alive": config.KEEP_ALIVE,
        "options": config.GEN_OPTIONS,
    }
    yield _sse({"mode": "local", "modele": model})
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream(
            "POST", f"{config.OLLAMA_HOST}/api/chat", json=payload
        ) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                raise RuntimeError(body.decode("utf-8", "ignore"))
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                data = json.loads(line)
                token = data.get("message", {}).get("content", "")
                if token:
                    yield _sse({"token": token})
                if data.get("done"):
                    yield _sse({"done": True})


import re as _re


def _capter_memoire(question: str) -> None:
    """Detecte et enregistre ce que l'utilisateur demande de retenir."""
    q = question.strip()
    # Prenom : "je m'appelle X" / "mon prenom est X"
    m = _re.search(r"\b(?:je m'appelle|mon pr[ée]nom est|appelle[ -]moi)\s+([A-Za-zÀ-ÿ'\-]{2,30})", q, _re.I)
    if m:
        memoire.definir_profil(prenom=m.group(1).strip(" .,"))
    # Faits explicites : "souviens-toi que ...", "retiens que ...", etc.
    m = _re.search(
        r"\b(?:souviens[- ]toi(?:\s+que)?|retiens(?:\s+que)?|rappelle[- ]toi(?:\s+que)?|"
        r"n'oublie pas(?:\s+que)?|note que)\s+(.{3,200})",
        q, _re.I,
    )
    if m:
        memoire.ajouter_fait(m.group(1).strip(" .!"))


_MOTS_DOC = (
    "document", "documents", "fichier", "pdf", "dans mes docs",
    "selon le", "selon la", "d'apres", "dans le fichier", "que dit",
    "extrait", "source", "indexe", "indexé",
)
_SALUTS = (
    "bonjour", "salut", "coucou", "hey", "hello", "merci", "ok", "oui", "non",
    "ca va", "ça va", "comment vas", "qui es-tu", "tu es la",
)


def _question_rapide(question: str, piece_jointe: Optional[PieceJointe]) -> bool:
    """True = discussion simple : on saute RAG et outils lourds."""
    if piece_jointe and piece_jointe.texte.strip():
        return False
    q = question.strip().lower()
    if not q:
        return True
    if len(q) < 20:
        return any(q.startswith(s) or q == s for s in _SALUTS)
    # Chat courant sans document ni web explicite : chemin rapide.
    if not _besoin_rag(question) and not outils.a_besoin_du_web(question):
        if len(q) < 180 and not any(m in q for m in _MOTS_DOC):
            return True
    return False


def _besoin_rag(question: str) -> bool:
    """RAG seulement si des documents existent ET la question le suggere."""
    if not rag.a_des_documents():
        return False
    t = question.lower()
    return any(m in t for m in _MOTS_DOC) or len(question.strip()) > 55


_REGLE_RAPIDE = (
    "Francais, concis, direct. Pas d'intro vide. Reponds tout de suite."
)


# Place en fin de prompt : le modele accorde plus d'importance aux dernieres consignes.
_REGLE_FINALE = (
    "REGLES ABSOLUES (prioritaires sur tout le reste) :\n"
    "1. LANGUE : reponds ENTIEREMENT en francais correct. Ne melange JAMAIS les langues "
    "au milieu d'une reponse (pas d'anglais, espagnol, etc.) sauf traduction demandee.\n"
    "2. COHERENCE : reste logique du debut a la fin. Ne te contredis pas. Chaque phrase "
    "doit suivre naturellement la precedente.\n"
    "3. FIDELITE : reponds a la question posee en tenant compte de l'historique de "
    "la conversation et des infos fournies (memoire, fichier, documents).\n"
    "4. FIABILITE : n'invente pas de faits, de noms ou de details. Si tu n'es pas sur, "
    "dis-le clairement.\n"
    "5. CLARTE : structure ta reponse (une idee a la fois). Pas de radotage ni de "
    "phrases sans sens."
)


async def _construire_systeme(
    question: str,
    piece_jointe: Optional[PieceJointe] = None,
    image_jointe: Optional[ImageJointe] = None,
) -> tuple[str, list[str]]:
    """Assemble le prompt systeme enrichi (fichier, image, memoire, docs, outils)."""
    rapide = _question_rapide(question, piece_jointe) and not image_jointe
    parties = [
        "Tu es JARVIS, assistant IA vif et fiable. Francais, tutoiement, concis."
        if rapide
        else config.SYSTEM_PROMPT
    ]
    sources: list[str] = []

    if image_jointe and image_jointe.base64.strip():
        parties.append(
            "L'utilisateur a joint une IMAGE. Tu la vois directement.\n"
            "Analyse-la avec precision : objets, texte visible (OCR), couleurs, "
            "contexte. Reponds a sa demande en francais, de facon coherente."
        )
        sources.append("image")

    # Fichier joint au message : priorite haute (tronque pour analyse rapide).
    if piece_jointe and piece_jointe.texte.strip():
        extrait = piece_jointe.texte.strip()[: config.CHAT_PIECE_MAX]
        parties.append(
            f"FICHIER JOINT ({piece_jointe.nom}) :\n{extrait}\n"
            "Traite ce fichier selon la demande. Reponds de facon coherente et "
            "structuree en t'appuyant sur son contenu."
        )
        sources.append("fichier")

    bloc_mem = memoire.texte_pour_prompt()
    if bloc_mem:
        parties.append(bloc_mem)
        sources.append("mémoire")

    # Chemin rapide : pas de RAG ni outils lourds pour les messages simples.
    if _question_rapide(question, piece_jointe) and not image_jointe:
        parties.append(_REGLE_RAPIDE)
        return "\n\n".join(parties), sources

    async def _rag_ctx() -> str:
        if not _besoin_rag(question):
            return ""
        return await asyncio.to_thread(rag.contexte_pour_prompt, question, 2)

    bloc_rag, bloc_outils = await asyncio.gather(
        _rag_ctx(),
        outils.contexte_outils(question),
    )
    if bloc_rag:
        parties.append(bloc_rag)
        sources.append("documents")

    if bloc_outils:
        parties.append(bloc_outils)
        if "RESULTATS WEB" in bloc_outils or "RECHERCHE WEB" in bloc_outils:
            sources.append("web")
        if "CALCUL" in bloc_outils:
            sources.append("calcul")

    # VERROU final : langue + coherence (position recente = forte priorite).
    parties.append(_REGLE_FINALE)

    return "\n\n".join(parties), sources


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """Discussion en streaming : IA cloud rapide si possible, sinon modele local.

    Enrichie par la memoire persistante, les documents (RAG) et les outils
    (calcul fiable, recherche web).
    """
    model = req.model or config.MODEL_NAME
    mode = (req.mode or "auto").lower()

    # Derniere question de l'utilisateur (pour memoire / RAG / outils).
    question = ""
    for m in reversed(req.messages):
        if m.role == "user":
            question = m.content
            break

    _capter_memoire(question)

    # --- Branche document : CV, PDF, lettre (creation ou modification) ---
    type_doc_demande = _demande_document(question, req.piece_jointe)
    if type_doc_demande and not req.image_jointe:

        async def stream_document():
            yield _sse({"info": "Rédaction du document en cours"})
            source = ""
            if req.piece_jointe and req.piece_jointe.texte.strip():
                source = req.piece_jointe.texte.strip()[:12000]

            if source:
                systeme_doc = _PROMPT_MODIFIER_DOC
                if type_doc_demande == "cv":
                    systeme_doc += "\nC'est un CV : conserve les sections ##."
                contenu_user = f"INSTRUCTION : {question}\n\nDOCUMENT ACTUEL :\n\n{source}"
            elif type_doc_demande == "cv":
                systeme_doc = _PROMPT_CV
                contenu_user = question
            else:
                systeme_doc = _PROMPT_DOCUMENT
                contenu_user = question

            msgs_doc = [
                {"role": "system", "content": systeme_doc},
                {"role": "user", "content": contenu_user},
            ]
            try:
                texte, mode = await _completion(msgs_doc)
                texte = _nettoyer_sortie(texte).strip()
                if not texte:
                    yield _sse({"erreur": "Document vide"})
                    return
                titre = _titre_auto(texte, "")
                fmt = "pdf"
                fichier = documents.generer(texte, fmt, titre, type_doc=type_doc_demande)
                import base64

                nom = documents.nom_fichier(titre, fmt)
                yield _sse({"mode": "cloud" if "cloud" in mode else "local", "modele": mode})
                yield _sse({
                    "document": {
                        "titre": titre,
                        "nom": nom,
                        "format": fmt,
                        "base64": base64.b64encode(fichier).decode("ascii"),
                        "apercu": texte[:1000],
                    }
                })
                yield _sse({"done": True})
            except Exception as exc:  # noqa: BLE001
                yield _sse({"erreur": str(exc)})

        return StreamingResponse(stream_document(), media_type="text/event-stream")

    systeme, sources = await _construire_systeme(
        question, req.piece_jointe, req.image_jointe
    )

    # Rappel de la question courante pour garder le fil coherent.
    if question and len(req.messages) >= 2:
        systeme += (
            f"\n\nQUESTION ACTUELLE : « {question} »\n"
            "Reponds en restant coherent avec tout l'historique ci-dessus."
        )

    historique = req.messages[-config.HISTORY_MAX :]

    rapide = _question_rapide(question, req.piece_jointe) and not req.image_jointe
    if securite.mode_demo():
        if not config.CLOUD_API_KEY:
            return _erreur_stream(_message_cle_manquante())
        utiliser_cloud = True
    else:
        utiliser_cloud = _cloud_autorise() and (
            mode == "cloud" or mode == "auto"
        )

    # --- Branche vision : image jointe ---
    if req.image_jointe and req.image_jointe.base64.strip():
        if securite.mode_demo() and not config.CLOUD_API_KEY:
            return _erreur_stream(_message_cle_manquante())
        if securite.mode_demo():
            utiliser_cloud = True
        if utiliser_cloud:
            vmsgs = vision.messages_cloud(
                systeme,
                historique,
                req.image_jointe.base64,
                req.image_jointe.mime,
                question,
            )
        else:
            vmsgs = vision.messages_ollama(
                systeme, historique, req.image_jointe.base64, question
            )

        async def stream_vision():
            yield _sse({"sources": sources})
            erreur_cloud = None
            if utiliser_cloud:
                try:
                    async for chunk in _stream_vision_cloud(vmsgs):
                        yield chunk
                    return
                except Exception as exc:  # noqa: BLE001
                    erreur_cloud = str(exc)
                    if mode == "cloud" or securite.mode_demo():
                        yield _sse({"erreur": f"Vision cloud : {erreur_cloud}"})
                        return
                    yield _sse({"info": "Bascule vision locale"})
            if securite.mode_demo():
                yield _sse({"erreur": "Vision indisponible en mode demo."})
                return
            try:
                async for chunk in _stream_vision_local_cascade(vmsgs):
                    yield chunk
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                if erreur_cloud:
                    msg = (
                        f"Vision cloud indisponible ({erreur_cloud[:100]}). "
                        f"Local : {msg}"
                    )
                yield _sse({"erreur": msg})

        return StreamingResponse(stream_vision(), media_type="text/event-stream")

    messages = [{"role": "system", "content": systeme}]
    messages += [{"role": m.role, "content": m.content} for m in historique]

    # Cloud : on tente directement si une cle existe (pas d'attente reseau).

    async def stream_tokens():
        # On demarre l'IA tout de suite ; les sources arrivent en parallele.
        if utiliser_cloud:
            try:
                async for chunk in _stream_cloud(messages, rapide=rapide):
                    yield chunk
                if sources:
                    yield _sse({"sources": sources})
                return
            except Exception as exc:  # noqa: BLE001
                if mode == "cloud" or securite.mode_demo():
                    yield _sse({"erreur": f"Cloud indisponible : {exc}"})
                    return
                yield _sse({"info": "Bascule en local"})

        if securite.mode_demo():
            yield _sse({"erreur": "Service cloud indisponible. Reessayez dans quelques secondes."})
            return

        if sources:
            yield _sse({"sources": sources})

        # 2. Modele local (hors-ligne).
        try:
            async for chunk in _stream_local(messages, model):
                yield chunk
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            # Memoire insuffisante (souvent le 7B) -> repli sur le petit modele.
            manque_ram = any(
                k in msg.lower()
                for k in ("allocate", "buffer", "terminated", "out of memory", "oom")
            )
            if manque_ram and model != config.MODEL_NAME:
                yield _sse({
                    "info": f"Mémoire insuffisante pour {model}, "
                            f"bascule sur {config.MODEL_NAME}"
                })
                try:
                    async for chunk in _stream_local(messages, config.MODEL_NAME):
                        yield chunk
                except Exception as exc2:  # noqa: BLE001
                    yield _sse({"erreur": str(exc2)})
            else:
                yield _sse({"erreur": msg})

    return StreamingResponse(stream_tokens(), media_type="text/event-stream")


@app.post("/api/tts")
async def tts(req: TTSRequest):
    """Genere une voix naturelle (neuronale) selon le visage choisi.

    Voix d'homme (Henri) ou de femme (Denise). Necessite Internet.
    En cas d'echec (hors-ligne), le navigateur utilisera sa voix locale.
    """
    import edge_tts

    voix = config.VOIX_NATURELLES.get(req.gender, config.VOIX_NATURELLES["femme"])
    # Conversion vitesse/tonalite au format attendu par edge-tts.
    pct = int(round((float(req.rate or 1.0) - 1.0) * 100))
    rate_str = f"{'+' if pct >= 0 else ''}{pct}%"
    hz = int(round((float(req.pitch or 1.0) - 1.0) * 50))
    pitch_str = f"{'+' if hz >= 0 else ''}{hz}Hz"

    try:
        com = edge_tts.Communicate(req.text, voix, rate=rate_str, pitch=pitch_str)
        audio = bytearray()
        async for chunk in com.stream():
            if chunk["type"] == "audio":
                audio.extend(chunk["data"])
        if not audio:
            raise RuntimeError("audio vide")
        return Response(content=bytes(audio), media_type="audio/mpeg")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# Verrou : on serialise les generations d'images (services gratuits limites).
_image_lock = asyncio.Lock()

_STYLES_VALIDES = {
    "photographic", "artistic", "anime", "oil-painting", "3d-render", "cartoon",
}


async def _image_placeholdr(client, prompt, largeur, hauteur, style):
    """Service principal SANS COMPTE : placeholdr.dev (modele Flux, gratuit).

    Le rendu est asynchrone : on recoit d'abord un SVG '202 en cours', puis on
    re-interroge la meme URL jusqu'a obtenir la vraie image (PNG).
    """
    desc = urllib.parse.quote(prompt)
    seed = random.randint(1, 3)  # placeholdr.dev : seed entre 1 et 3
    url = f"https://placeholdr.dev/{largeur}x{hauteur}/{desc}?style={style}&seed={seed}"
    for _ in range(18):  # ~ jusqu'a 55 s
        r = await client.get(url)
        ctype = r.headers.get("content-type", "")
        if r.status_code == 200 and ctype.startswith("image") and "svg" not in ctype:
            return r.content, ctype
        # 202 (ou SVG placeholder) : generation en cours -> on patiente.
        if r.status_code in (200, 202):
            await asyncio.sleep(3)
            continue
        raise RuntimeError(f"placeholdr.dev code {r.status_code}")
    raise RuntimeError("placeholdr.dev : delai depasse")


async def _image_pollinations(client, prompt, largeur, hauteur):
    """Secours : Pollinations (gratuit ; sans token l'acces anonyme est limite)."""
    seed = random.randint(1, 10_000_000)
    enc = urllib.parse.quote(prompt)
    url = (
        f"https://image.pollinations.ai/prompt/{enc}"
        f"?width={largeur}&height={hauteur}&nologo=true&seed={seed}"
    )
    headers = {}
    if config.IMAGE_API_KEY:
        headers["Authorization"] = f"Bearer {config.IMAGE_API_KEY}"
        url += f"&token={urllib.parse.quote(config.IMAGE_API_KEY)}"
    for _ in range(3):
        r = await client.get(url, headers=headers)
        ctype = r.headers.get("content-type", "")
        if r.status_code == 200 and ctype.startswith("image"):
            return r.content, ctype
        if r.status_code == 402:  # file pleine -> on patiente (1 req / 15 s)
            await asyncio.sleep(8)
            continue
        raise RuntimeError(f"pollinations code {r.status_code}")
    raise RuntimeError("pollinations : file pleine")


@app.post("/api/image")
async def image(req: ImageRequest):
    """Genere une image a partir d'une description, gratuitement et SANS COMPTE.

    Principal : placeholdr.dev (Flux). Secours : Pollinations.
    Necessite Internet (la generation tourne sur des serveurs distants ;
    impossible en local sans carte graphique).
    """
    p = (req.prompt or "").strip()
    if not p:
        raise HTTPException(status_code=400, detail="description manquante")

    largeur = max(128, min(int(req.largeur or 1024), 2048))
    hauteur = max(128, min(int(req.hauteur or 1024), 2048))
    style = req.style if req.style in _STYLES_VALIDES else "photographic"

    async with _image_lock:
        async with httpx.AsyncClient(timeout=90, follow_redirects=True) as client:
            # 1) placeholdr.dev (sans compte).
            try:
                contenu, ctype = await _image_placeholdr(
                    client, p, largeur, hauteur, style
                )
                return Response(content=contenu, media_type=ctype)
            except Exception as e1:  # noqa: BLE001
                erreur1 = str(e1)
            # 2) Secours : Pollinations.
            try:
                contenu, ctype = await _image_pollinations(client, p, largeur, hauteur)
                return Response(content=contenu, media_type=ctype)
            except Exception as e2:  # noqa: BLE001
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "Les services d'images gratuits sont momentanement "
                        f"surcharges. Reessaie dans un instant. ({erreur1} / {e2})"
                    ),
                ) from e2


async def _transcrire_groq(donnees: bytes, suffix: str) -> str:
    """Transcription vocale via Groq Whisper (leger, pour la version en ligne)."""
    nom = f"audio{suffix if suffix.startswith('.') else '.' + suffix}"
    mime = "audio/webm"
    if suffix.lower() in (".wav",):
        mime = "audio/wav"
    elif suffix.lower() in (".mp3", ".mpeg", ".mpga"):
        mime = "audio/mpeg"
    elif suffix.lower() == ".m4a":
        mime = "audio/mp4"
    headers = {"Authorization": f"Bearer {config.CLOUD_API_KEY}"}
    async with httpx.AsyncClient(timeout=90) as client:
        r = await client.post(
            f"{config.CLOUD_API_BASE}/audio/transcriptions",
            headers=headers,
            files={"file": (nom, donnees, mime)},
            data={
                "model": "whisper-large-v3",
                "language": config.WHISPER_LANGUAGE,
                "response_format": "json",
                "temperature": "0",
            },
        )
        if r.status_code != 200:
            raise RuntimeError(r.text[:300])
        return (r.json().get("text") or "").strip()


@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    """Transcrit une note vocale : Whisper local ou Groq Whisper (en ligne)."""
    donnees = await _lire_upload(audio)
    suffix = Path(audio.filename or "audio.webm").suffix or ".webm"

    if config.DISABLE_WHISPER:
        if not config.CLOUD_API_KEY:
            raise HTTPException(status_code=503, detail=_message_cle_manquante())
        try:
            texte = await _transcrire_groq(donnees, suffix)
            return {"texte": texte}
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(donnees)
            tmp_path = tmp.name

        def _transcrire(chemin: str) -> str:
            model = get_whisper_model()
            segments, _ = model.transcribe(
                chemin,
                language=config.WHISPER_LANGUAGE,
                beam_size=1,
                vad_filter=True,
                vad_parameters={
                    "threshold": 0.45,
                    "min_silence_duration_ms": 350,
                    "speech_pad_ms": 120,
                },
                condition_on_previous_text=False,
                no_speech_threshold=0.55,
                temperature=0.0,
                initial_prompt="Francais.",
            )
            return " ".join(seg.text.strip() for seg in segments).strip()

        texte = await asyncio.to_thread(_transcrire, tmp_path)
        return {"texte": texte}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


def _sse(obj: dict) -> str:
    """Formate un objet en evenement Server-Sent Events."""
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


# --------------------------------------------------------------------------
# Memoire persistante
# --------------------------------------------------------------------------
class ProfilRequest(BaseModel):
    prenom: Optional[str] = None
    a_propos: Optional[str] = None


class FaitRequest(BaseModel):
    fait: str


@app.get("/api/memoire")
async def get_memoire():
    """Renvoie tout ce que JARVIS sait sur l'utilisateur."""
    return memoire.charger()


@app.post("/api/memoire/profil")
async def set_profil(req: ProfilRequest):
    """Met a jour le prenom et/ou le contexte de l'utilisateur."""
    return memoire.definir_profil(prenom=req.prenom, a_propos=req.a_propos)


@app.post("/api/memoire/fait")
async def add_fait(req: FaitRequest):
    """Ajoute un fait a retenir."""
    return memoire.ajouter_fait(req.fait)


@app.delete("/api/memoire")
async def reset_memoire():
    """Efface toute la memoire (repart de zero)."""
    return memoire.oublier_tout()


# --------------------------------------------------------------------------
# Documents (RAG)
# --------------------------------------------------------------------------
@app.get("/api/documents")
async def get_documents():
    """Liste les documents indexes."""
    return {"documents": rag.lister()}


@app.post("/api/documents")
async def upload_document(fichier: UploadFile = File(...)):
    """Ajoute (indexe) un document : txt, md, csv, code ou PDF."""
    try:
        donnees = await _lire_upload(fichier)
        nom = securite.nom_fichier_sur(fichier.filename or "document")
        texte = rag.extraire_texte(nom, donnees)
        if not texte.strip():
            raise RuntimeError("aucun texte exploitable dans ce fichier")
        return rag.ajouter_document(nom, texte)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/documents/{nom}")
async def delete_document(nom: str):
    """Supprime un document de l'index."""
    nom = securite.nom_fichier_sur(nom)
    if rag.supprimer(nom):
        return {"supprime": nom}
    raise HTTPException(status_code=404, detail="document introuvable")


# --------------------------------------------------------------------------
# Atelier fichier : transformer un fichier selon une instruction
# --------------------------------------------------------------------------
_PROMPT_TRANSFORMATION = (
    "Tu es un outil de transformation de fichiers. On te donne le contenu d'un "
    "fichier et une instruction. Tu renvoies UNIQUEMENT le contenu modifie du "
    "fichier, tel qu'il doit etre enregistre.\n"
    "REGLES STRICTES :\n"
    "- Aucune phrase d'introduction ni de conclusion (pas de 'Voici...').\n"
    "- Aucune explication, aucun commentaire sur ce que tu as fait.\n"
    "- N'entoure pas le resultat de balises Markdown ``` sauf si le fichier "
    "d'origine en contenait.\n"
    "- Conserve la structure, la mise en forme et la langue d'origine, sauf si "
    "l'instruction demande explicitement de les changer.\n"
    "- Applique l'instruction sur la TOTALITE du contenu fourni."
)

# Limite de taille pour le traitement complet (securite tokens/contexte).
_MAX_TRAITEMENT = 24000


async def _completion_cloud(messages, modele) -> str:
    """Reponse complete (non-streaming) d'un modele cloud."""
    payload = {
        "model": modele,
        "messages": messages,
        "stream": False,
        "temperature": 0.3,
        "top_p": 0.9,
    }
    headers = {"Authorization": f"Bearer {config.CLOUD_API_KEY}"}
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            f"{config.CLOUD_API_BASE}/chat/completions", json=payload, headers=headers
        )
        if r.status_code != 200:
            raise RuntimeError(r.text)
        return r.json()["choices"][0]["message"]["content"]


async def _completion_local(messages, modele) -> str:
    """Reponse complete (non-streaming) du modele local via Ollama."""
    payload = {
        "model": modele,
        "messages": messages,
        "stream": False,
        "keep_alive": config.KEEP_ALIVE,
        "options": config.GEN_OPTIONS,
    }
    async with httpx.AsyncClient(timeout=300) as client:
        r = await client.post(f"{config.OLLAMA_HOST}/api/chat", json=payload)
        if r.status_code != 200:
            raise RuntimeError(r.text)
        return r.json().get("message", {}).get("content", "")


async def _completion(messages) -> tuple[str, str]:
    """Reponse complete : cloud (cascade) si autorise, sinon local. Renvoie (texte, mode)."""
    if securite.mode_demo() and not config.CLOUD_API_KEY:
        raise RuntimeError(_message_cle_manquante())
    if _cloud_autorise() and await _internet_disponible():
        derniere = None
        for modele in config.CLOUD_MODELS:
            try:
                return await _completion_cloud(messages, modele), f"cloud ({modele})"
            except Exception as exc:  # noqa: BLE001
                derniere = exc
                if _est_quota_atteint(str(exc)):
                    continue
                break
        if securite.mode_demo():
            raise RuntimeError(f"Cloud indisponible : {derniere}") from derniere
    if securite.mode_demo():
        raise RuntimeError("Service cloud indisponible en mode demo.")
    texte = await _completion_local(messages, config.MODEL_NAME)
    return texte, f"local ({config.MODEL_NAME})"


def _nettoyer_sortie(texte: str) -> str:
    """Retire un eventuel bloc Markdown ``` que le modele aurait ajoute."""
    t = texte.strip()
    if t.startswith("```"):
        lignes = t.split("\n")
        # On enleve la 1ere ligne (```lang) et la derniere si c'est ```.
        if len(lignes) >= 2:
            lignes = lignes[1:]
            if lignes and lignes[-1].strip().startswith("```"):
                lignes = lignes[:-1]
            t = "\n".join(lignes).strip()
    return t


def _nom_sortie(nom: str, fmt: str = "txt") -> str:
    """Construit un nom de fichier de sortie."""
    p = Path(nom)
    base = p.stem or "fichier"
    ext = fmt if fmt in documents.FORMATS else ".txt"
    if not ext.startswith("."):
        ext = f".{ext}"
    return f"{base}_modifie{ext}"


@app.post("/api/traiter-fichier")
async def traiter_fichier(
    fichier: UploadFile = File(...),
    instruction: str = Form(...),
    format_sortie: str = Form("auto"),
):
    """Traite un fichier (PDF, Word, txt...) et renvoie le resultat modifie."""
    instruction = (instruction or "").strip()
    if not instruction:
        raise HTTPException(status_code=400, detail="instruction manquante")
    try:
        donnees = await _lire_upload(fichier)
        nom = securite.nom_fichier_sur(fichier.filename or "fichier.txt")
        texte = rag.extraire_texte(nom, donnees)
        if not texte.strip():
            raise RuntimeError("aucun texte exploitable dans ce fichier")

        tronque = len(texte) > _MAX_TRAITEMENT
        extrait = texte[:_MAX_TRAITEMENT]
        est_cv = any(m in instruction.lower() for m in ("cv", "curriculum"))
        systeme = _PROMPT_MODIFIER_DOC
        if est_cv or nom.lower().endswith(".pdf") and "cv" in nom.lower():
            systeme += "\nC'est un CV : conserve le format Markdown avec sections ##."
            est_cv = True

        messages = [
            {"role": "system", "content": systeme},
            {
                "role": "user",
                "content": (
                    f"INSTRUCTION : {instruction}\n\n"
                    f"CONTENU DU FICHIER ({nom}) :\n\n{extrait}"
                ),
            },
        ]
        resultat, mode = await _completion(messages)
        resultat = _nettoyer_sortie(resultat)

        fmt = (format_sortie or "auto").lower()
        if fmt == "auto":
            if nom.lower().endswith(".pdf") or est_cv:
                fmt = "pdf"
            elif nom.lower().endswith((".docx", ".doc")):
                fmt = "docx"
            else:
                fmt = "txt"

        type_doc = "cv" if est_cv else "generic"
        titre = _titre_auto(resultat, Path(nom).stem)

        if fmt in ("pdf", "docx"):
            fichier_bytes = documents.generer(resultat, fmt, titre, type_doc=type_doc)
            import base64
            return {
                "nom_sortie": _nom_sortie(nom, fmt),
                "contenu": resultat,
                "fichier_base64": base64.b64encode(fichier_bytes).decode("ascii"),
                "mime": documents.FORMATS[fmt][1].split(";")[0],
                "format": fmt,
                "mode": mode,
                "tronque": tronque,
                "type_doc": type_doc,
            }

        return {
            "nom_sortie": _nom_sortie(nom, fmt),
            "contenu": resultat,
            "mode": mode,
            "tronque": tronque,
            "format": fmt,
        }
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# Taille max du texte injecte directement dans un message (securite contexte).
_MAX_PIECE_JOINTE = 8000


@app.post("/api/joindre-image")
async def joindre_image(fichier: UploadFile = File(...)):
    """Prepare une image pour analyse vision dans le chat."""
    try:
        nom = securite.nom_fichier_sur(fichier.filename or "image.jpg")
        if not vision.est_image(nom):
            raise ValueError("format non supporte (jpg, png, webp, gif, bmp)")
        donnees = await _lire_upload(fichier)
        info = await asyncio.to_thread(vision.preparer_image, donnees, nom)
        return info
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/joindre")
async def joindre(fichier: UploadFile = File(...)):
    """Extrait le texte d'un fichier joint a un message (indexation en arriere-plan)."""
    try:
        donnees = await _lire_upload(fichier)
        nom = securite.nom_fichier_sur(fichier.filename or "fichier")
        texte = await asyncio.to_thread(rag.extraire_texte, nom, donnees)
        if not texte.strip():
            raise RuntimeError("aucun texte exploitable dans ce fichier")
        # Indexation non bloquante : reponse immediate a l'utilisateur.
        asyncio.create_task(asyncio.to_thread(rag.ajouter_document, nom, texte))
        limite = min(_MAX_PIECE_JOINTE, config.CHAT_PIECE_MAX)
        tronque = len(texte) > limite
        return {
            "nom": nom,
            "texte": texte[:limite],
            "tronque": tronque,
            "caracteres": len(texte),
        }
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# --------------------------------------------------------------------------
# Generation de documents (rapport, lettre, CV...) -> txt / md / docx / pdf
# --------------------------------------------------------------------------
_PROMPT_DOCUMENT = (
    "Tu es un redacteur professionnel. Tu produis un document complet, clair et "
    "bien structure a partir de la demande de l'utilisateur.\n"
    "REGLES STRICTES :\n"
    "- Reponds UNIQUEMENT avec le contenu du document, rien d'autre.\n"
    "- Aucune phrase d'introduction ('Voici...') ni de conclusion sur ton travail.\n"
    "- Utilise du Markdown simple : '# Titre', '## Sous-titre', '- puce', "
    "'**gras**'. N'utilise PAS de blocs de code ```.\n"
    "- Ecris en francais correct et naturel (sauf si une autre langue est "
    "explicitement demandee).\n"
    "- Sois complet et professionnel, adapte au type de document demande."
)

_PROMPT_CV = (
    "Tu es un expert en redaction de CV professionnels. Produis un CV complet "
    "en Markdown STRICTEMENT selon ce modele :\n\n"
    "# Prenom Nom\n"
    "email@exemple.com | 06 12 34 56 78 | Ville\n\n"
    "## Profil\n"
    "Resume professionnel en 3-4 lignes percutantes.\n\n"
    "## Competences\n"
    "- Competence 1\n"
    "- Competence 2\n\n"
    "## Experience professionnelle\n"
    "### Poste — Entreprise (annee debut – annee fin)\n"
    "- Realisation concrete 1\n"
    "- Realisation concrete 2\n\n"
    "## Formation\n"
    "### Diplome — Etablissement (annees)\n\n"
    "## Langues\n"
    "- Langue : niveau\n\n"
    "REGLES : reponds UNIQUEMENT avec le CV en Markdown. Pas d'intro. "
    "Adapte le contenu a la demande. Invente des details plausibles seulement "
    "si l'utilisateur n'en donne pas."
)

_PROMPT_MODIFIER_DOC = (
    "Tu modifies un document existant selon l'instruction de l'utilisateur.\n"
    "REGLES :\n"
    "- Reponds UNIQUEMENT avec le document modifie en Markdown.\n"
    "- Conserve la structure et le format Markdown (# ## ### - **).\n"
    "- Applique precisement les changements demandes.\n"
    "- Pas de commentaire sur ton travail."
)


def _detecte_type_document(instruction: str) -> str:
    t = instruction.lower()
    if any(m in t for m in ("cv", "curriculum", "resume professionnel", "résumé professionnel")):
        return "cv"
    if any(m in t for m in ("lettre de motivation", "lettre de recommandation")):
        return "lettre"
    return "generic"


def _demande_document(question: str, piece_jointe: Optional[PieceJointe]) -> Optional[str]:
    """Detecte si l'utilisateur demande la creation/modification d'un document."""
    t = question.lower().strip()
    if not t:
        return None
    mots_action = (
        "crée", "cree", "créer", "creer", "fais", "faire", "fait", "génère", "genere",
        "générer", "generer", "rédige", "redige", "rédiger", "rediger", "prépare",
        "prepare", "reproduis", "refais", "modifie", "modifier", "mets à jour",
        "mets a jour", "transforme", "exporte", "télécharge", "telecharge", "veux",
        "voudrais", "besoin", "donne", "donne-moi", "fabrique", "écris", "ecris", "produis",
        "montre", "imprime", "construis", "convertis",
    )
    cv = bool(_re.search(
        r"\b(cv|curriculum\s*vitae|curriculum|resume\s*professionnel|résumé\s*professionnel)\b", t
    ))
    doc = bool(_re.search(
        r"\b(pdf|document|lettre de motivation|rapport|contrat|word|docx)\b", t
    ))
    action = any(m in t for m in mots_action) or bool(
        _re.match(r"^(peux-tu|pourrais-tu|tu peux)\b", t)
    )
    if cv and (action or "pdf" in t or len(t) < 140):
        return "cv"
    if doc and action:
        return "generic"
    if "pdf" in t and action and len(t) < 160:
        return "generic"
    if piece_jointe and piece_jointe.texte.strip() and action:
        nom = (piece_jointe.nom or "").lower()
        if cv or doc or nom.endswith((".pdf", ".docx", ".doc")):
            return "cv" if cv or "cv" in nom else "generic"
    return None


class DocumentRequest(BaseModel):
    instruction: str
    titre: Optional[str] = ""
    type_doc: Optional[str] = "auto"
    source_texte: Optional[str] = ""


class DocumentFichierRequest(BaseModel):
    texte: str
    format: Optional[str] = "pdf"
    titre: Optional[str] = ""
    type_doc: Optional[str] = "generic"


def _titre_auto(texte: str, titre: str) -> str:
    """Renvoie le titre fourni, sinon le premier titre/ligne du contenu."""
    titre = (titre or "").strip()
    if titre:
        return titre[:80]
    for ligne in texte.split("\n"):
        ligne = ligne.strip()
        if ligne:
            return (ligne.lstrip("#").strip()[:80]) or "Document"
    return "Document"


@app.post("/api/document")
async def document(req: DocumentRequest):
    """Redige ou modifie un document (CV, lettre, rapport...) en Markdown."""
    instruction = (req.instruction or "").strip()
    if not instruction:
        raise HTTPException(status_code=400, detail="demande manquante")

    source = (req.source_texte or "").strip()
    type_doc = (req.type_doc or "auto").lower()
    if type_doc == "auto":
        type_doc = _detecte_type_document(instruction)

    if source:
        systeme = _PROMPT_MODIFIER_DOC
        if type_doc == "cv":
            systeme += "\nC'est un CV : conserve les sections Profil, Competences, Experience, Formation."
        user_content = f"INSTRUCTION : {instruction}\n\nDOCUMENT ACTUEL :\n\n{source[:12000]}"
    elif type_doc == "cv":
        systeme = _PROMPT_CV
        user_content = instruction
    else:
        systeme = _PROMPT_DOCUMENT
        user_content = instruction

    messages = [
        {"role": "system", "content": systeme},
        {"role": "user", "content": user_content},
    ]
    try:
        texte, mode = await _completion(messages)
        texte = _nettoyer_sortie(texte).strip()
        if not texte:
            raise RuntimeError("le document genere est vide")
        return {
            "texte": texte,
            "titre": _titre_auto(texte, req.titre or ""),
            "mode": mode,
            "type_doc": type_doc,
        }
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/document/fichier")
async def document_fichier(req: DocumentFichierRequest):
    """Transforme un texte Markdown en fichier telechargeable (txt/md/docx/pdf)."""
    texte = (req.texte or "").strip()
    if not texte:
        raise HTTPException(status_code=400, detail="contenu manquant")
    fmt = (req.format or "pdf").lower()
    type_doc = (req.type_doc or "generic").lower()
    if fmt not in documents.FORMATS:
        raise HTTPException(status_code=400, detail=f"format inconnu : {fmt}")
    try:
        titre = _titre_auto(texte, req.titre or "")
        contenu = documents.generer(texte, fmt, titre, type_doc=type_doc)
        nom = documents.nom_fichier(titre, fmt)
        _, mime = documents.FORMATS[fmt]
        entetes = {"Content-Disposition": f'attachment; filename="{nom}"'}
        return Response(content=contenu, media_type=mime, headers=entetes)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# --------------------------------------------------------------------------
# Interface web (servie en statique). Doit etre montee en dernier.
# --------------------------------------------------------------------------
_frontend = Path(__file__).resolve().parent.parent / "frontend"
if _frontend.exists():
    app.mount("/", StaticFiles(directory=str(_frontend), html=True), name="frontend")
