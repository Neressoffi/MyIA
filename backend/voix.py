"""Stylisation de la parole JARVIS (effet science-fiction / Iron Man).

Transforme le texte brut (markdown, code, listes) en prose claire, calme
et rythmee pour edge-tts — comme un assistant holographique de film.
"""
from __future__ import annotations

import re


def styliser_pour_tts(texte: str, gender: str = "femme") -> str:
    """Prepare un texte pour une diction naturelle style JARVIS."""
    t = (texte or "").strip()
    if not t:
        return ""

    # Blocs de code -> mention courte (ne lit pas le code ligne a ligne).
    t = re.sub(
        r"```[\w+-]*\n.*?```",
        " Voici le code correspondant. ",
        t,
        flags=re.DOTALL,
    )
    t = re.sub(r"`([^`]+)`", r"\1", t)

    # Markdown : titres, gras, listes.
    t = re.sub(r"^#{1,6}\s*", "", t, flags=re.MULTILINE)
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"__([^_]+)__", r"\1", t)
    t = re.sub(r"\*([^*]+)\*", r"\1", t)
    t = re.sub(r"^[\-\*•]\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"^\d+\.\s+", "", t, flags=re.MULTILINE)

    # URLs et chemins : ne pas epeler.
    t = re.sub(r"https?://\S+", " ce lien ", t)
    t = re.sub(r"\b[\w.-]+\.(png|jpg|jpeg|pdf|docx?|txt|py|js)\b", " ce fichier ", t, flags=re.I)

    # Emojis / symboles techniques bruyants.
    t = re.sub(r"[⚠️✅❌🔴🟢🔵★☆•▪︎►▶︎◀︎]+", " ", t)
    t = t.replace("→", " vers ").replace("↔", " et ").replace("≈", " environ ")
    t = t.replace("&", " et ")

    # Compacte les espaces / sauts de ligne en pauses orales.
    t = re.sub(r"\n{2,}", ". ", t)
    t = re.sub(r"\n", ". ", t)
    t = re.sub(r"\s{2,}", " ", t)

    # Rythme cinema : pause legere apres les phrases.
    t = re.sub(r"([.!?])\s+", r"\1 … ", t)
    t = re.sub(r"\s*,\s*", ", ", t)
    t = re.sub(r"(…\s*){2,}", "… ", t)
    t = re.sub(r"\s{2,}", " ", t).strip()

    # Limite de securite pour edge-tts.
    if len(t) > 2800:
        t = t[:2790].rsplit(" ", 1)[0] + "."

    return t


def reglages_cinematiques(gender: str, rate: float, pitch: float) -> tuple[float, float]:
    """Ajuste vitesse/tonalite pour un rendu sci-fi calme et autoritaire."""
    # Base cinema : un peu plus lent, ton legerement plus grave.
    base_rate = 0.92 if gender == "homme" else 0.94
    base_pitch = 0.88 if gender == "homme" else 0.95
    # Respecte le reglage utilisateur autour de la base cinema.
    rate_final = max(0.55, min(1.35, base_rate * float(rate or 1.0)))
    pitch_final = max(0.55, min(1.35, base_pitch * float(pitch or 1.0)))
    return rate_final, pitch_final
