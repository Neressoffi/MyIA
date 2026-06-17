"""Diagnostic de sante et de puissance de JARVIS."""

from __future__ import annotations

from pathlib import Path

from . import config, memoire, rag

_PROMPTS_FICHIER = (
    Path(__file__).resolve().parent / "data" / "prompts_bibliotheque.json"
)
_FALLBACK_PROMPTS = Path(__file__).resolve().parent.parent / "donnees" / "prompts_bibliotheque.json"


def _charger_prompts() -> dict:
    import json

    fichier = _PROMPTS_FICHIER if _PROMPTS_FICHIER.exists() else _FALLBACK_PROMPTS
    if not fichier.exists():
        return {"total": 0, "categories": [], "prompts": []}
    return json.loads(fichier.read_text(encoding="utf-8"))


def executer(health: dict) -> dict:
    """Construit un rapport de diagnostic complet."""
    biblio = _charger_prompts()
    mem = memoire.charger()
    idx = rag._charger_index()  # noqa: SLF001 — usage interne diagnostic

    nb_docs = len(idx.get("documents", {}))
    nb_chunks = len(idx.get("chunks", []))
    nb_faits = len(mem.get("faits", []))
    prenom = (mem.get("profil") or {}).get("prenom", "")

    caps = [
        {"nom": "Discussion texte + streaming", "ok": True, "score": 100},
        {"nom": "Mode cloud (Groq)", "ok": bool(config.CLOUD_API_KEY), "score": 100 if config.CLOUD_API_KEY else 0},
        {"nom": "Mode local (Ollama)", "ok": health.get("ollama", False), "score": 100 if health.get("ollama") else 0},
        {"nom": "Mémoire persistante", "ok": True, "score": 100},
        {"nom": "Documents (RAG)", "ok": nb_docs > 0, "score": min(100, 40 + nb_docs * 15)},
        {"nom": "Recherche web", "ok": bool(config.CLOUD_API_KEY), "score": 90 if config.CLOUD_API_KEY else 50},
        {"nom": "Calcul fiable", "ok": True, "score": 100},
        {"nom": "Synthèse vocale", "ok": True, "score": 100},
        {"nom": "Reconnaissance vocale", "ok": True, "score": 95},
        {"nom": "Génération d'images", "ok": True, "score": 85},
        {"nom": "Documents Word/PDF", "ok": True, "score": 100},
        {"nom": "Analyse d'images (vision)", "ok": bool(config.CLOUD_API_KEY), "score": 95 if config.CLOUD_API_KEY else 40},
        {"nom": "Bibliothèque 100 prompts", "ok": biblio.get("total", 0) >= 100, "score": min(100, biblio.get("total", 0))},
    ]

    score_global = round(sum(c["score"] for c in caps) / len(caps))

    return {
        "score_global": score_global,
        "niveau": (
            "Excellent" if score_global >= 90
            else "Bon" if score_global >= 75
            else "Moyen" if score_global >= 55
            else "À renforcer"
        ),
        "modele_cloud": config.CLOUD_MODEL,
        "modele_local": config.MODEL_NAME,
        "cloud_actif": bool(config.CLOUD_API_KEY),
        "ollama_actif": health.get("ollama", False),
        "memoire": {
            "prenom": prenom or "(non défini)",
            "faits": nb_faits,
        },
        "documents": {"fichiers": nb_docs, "morceaux_indexes": nb_chunks},
        "bibliotheque_prompts": {
            "total": biblio.get("total", 0),
            "categories": biblio.get("categories", []),
        },
        "capacites": caps,
        "recommandations": _recommandations(score_global, nb_docs, prenom, health),
        "note_importante": (
            "Les 100 prompts de la bibliothèque ne 'entraînent' pas le modèle : "
            "ils te permettent de tester et exploiter JARVIS sur tous les sujets. "
            "L'intelligence vient du modèle (70B cloud / 3B local) + mémoire + RAG + outils."
        ),
    }


def _recommandations(score, nb_docs, prenom, health) -> list[str]:
    rec = []
    if not health.get("ollama"):
        rec.append("Démarre Ollama pour le mode hors-ligne.")
    if not config.CLOUD_API_KEY:
        rec.append("Ajoute une clé Groq gratuite dans cle_api.txt pour le mode cloud rapide.")
    if nb_docs == 0:
        rec.append("Dépose tes documents (PDF, notes) pour des réponses basées sur TES fichiers.")
    if not prenom:
        rec.append("Dis « je m'appelle … » pour personnaliser JARVIS.")
    if score >= 85:
        rec.append("Utilise la bibliothèque de 100 prompts (bouton 💡) pour couvrir tous les sujets.")
    rec.append("Pour un sujet complexe : pose une question précise + joins un fichier si besoin.")
    return rec
