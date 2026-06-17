"""Analyse d'images pour JARVIS (vision multimodale).

Cloud : Groq Llama 4 Scout / Maverick (gratuit avec cle API).
Local : Ollama moondream / llava si installes.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path

_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
_MAX_PX = 1280
_MAX_OCTETS = 3_500_000


def est_image(nom: str) -> bool:
    return Path(nom).suffix.lower() in _EXTENSIONS


def preparer_image(donnees: bytes, nom: str) -> dict:
    """Redimensionne et compresse une image pour l'analyse vision."""
    from PIL import Image

    if len(donnees) > 8_000_000:
        raise ValueError("image trop volumineuse (max 8 Mo)")
    try:
        img = Image.open(io.BytesIO(donnees))
        img.load()
    except Exception as exc:  # noqa: BLE001
        raise ValueError("fichier image illisible") from exc

    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    w, h = img.size
    if max(w, h) > _MAX_PX:
        ratio = _MAX_PX / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.Resampling.LANCZOS)
        w, h = img.size

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85, optimize=True)
    jpeg = buf.getvalue()
    if len(jpeg) > _MAX_OCTETS:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70, optimize=True)
        jpeg = buf.getvalue()

    b64 = base64.b64encode(jpeg).decode("ascii")
    return {
        "nom": nom,
        "mime": "image/jpeg",
        "base64": b64,
        "largeur": w,
        "hauteur": h,
        "taille_ko": round(len(jpeg) / 1024, 1),
    }


def texte_question(question: str) -> str:
    q = (question or "").strip()
    return q or "Analyse cette image en detail. Decris ce que tu vois et reponds en francais."


def messages_cloud(systeme: str, historique: list, base64_img: str, mime: str, question: str) -> list:
    """Format OpenAI/Groq vision."""
    data_url = f"data:{mime};base64,{base64_img}"
    msgs = [{"role": "system", "content": systeme}]
    for m in historique[:-1]:
        msgs.append({"role": m.role, "content": m.content})
    msgs.append({
        "role": "user",
        "content": [
            {"type": "text", "text": texte_question(question)},
            {"type": "image_url", "image_url": {"url": data_url}},
        ],
    })
    return msgs


def messages_ollama(systeme: str, historique: list, base64_img: str, question: str) -> list:
    """Format Ollama vision (champ images sur le message user)."""
    msgs = [{"role": "system", "content": systeme}]
    for m in historique[:-1]:
        msgs.append({"role": m.role, "content": m.content})
    msgs.append({
        "role": "user",
        "content": texte_question(question),
        "images": [base64_img],
    })
    return msgs
