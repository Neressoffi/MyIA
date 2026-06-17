"""RAG : memoire documentaire de JARVIS.

Permet de deposer des documents (texte, markdown, PDF) et de retrouver, pour
chaque question, les passages les plus pertinents pour repondre avec TES
connaissances. Tout est local, leger (sans GPU) et fonctionne hors-ligne.

La recherche utilise un score TF-IDF maison (pondere par la rarete des mots),
suffisant et rapide pour un usage personnel, sans grosse dependance.
"""
from __future__ import annotations

import json
import math
import re
import threading
from pathlib import Path
from typing import List

from . import securite

_DOSSIER = Path(__file__).resolve().parent.parent / "donnees"
_INDEX = _DOSSIER / "index_documents.json"
_VERROU = threading.Lock()
_CACHE_INDEX: dict | None = None
_CACHE_MTIME: float = 0.0

# Taille des morceaux (en caracteres) et chevauchement pour garder le contexte.
_TAILLE_CHUNK = 900
_CHEVAUCHEMENT = 150
_MOTS_VIDES = set(
    "le la les un une des de du au aux et ou a o y en dans sur sous pour par "
    "avec sans ce cet cette ces mon ma mes ton ta tes son sa ses notre nos votre "
    "vos leur leurs je tu il elle on nous vous ils elles que qui quoi dont ou est "
    "sont ete etre avoir as ai a ont avons avez suis es sera seront c s d l m n t "
    "ne pas plus moins tres si non oui aussi mais donc car comme tout tous toute".split()
)


def _charger_index() -> dict:
    global _CACHE_INDEX, _CACHE_MTIME
    if not _INDEX.exists():
        return {"documents": {}, "chunks": []}
    try:
        mtime = _INDEX.stat().st_mtime
        if _CACHE_INDEX is not None and mtime == _CACHE_MTIME:
            return _CACHE_INDEX
        data = securite.lire_json_protege(_INDEX, {"documents": {}, "chunks": []})
        _CACHE_INDEX = data
        _CACHE_MTIME = mtime
        return data
    except Exception:  # noqa: BLE001
        return {"documents": {}, "chunks": []}


def a_des_documents() -> bool:
    """True si au moins un document est indexe (evite une recherche inutile)."""
    return bool(_charger_index().get("chunks"))


def _sauver_index(idx: dict) -> None:
    global _CACHE_INDEX, _CACHE_MTIME
    with _VERROU:
        securite.ecrire_json_protege(_INDEX, idx)
        _CACHE_INDEX = idx
        _CACHE_MTIME = _INDEX.stat().st_mtime


def _tokeniser(texte: str) -> List[str]:
    mots = re.findall(r"[a-zA-Z0-9\u00C0-\u017F]+", texte.lower())
    return [m for m in mots if len(m) > 2 and m not in _MOTS_VIDES]


def _decouper(texte: str) -> List[str]:
    """Decoupe un texte en morceaux qui se chevauchent."""
    texte = re.sub(r"\s+", " ", texte).strip()
    if not texte:
        return []
    morceaux = []
    debut = 0
    while debut < len(texte):
        fin = debut + _TAILLE_CHUNK
        morceaux.append(texte[debut:fin])
        debut = fin - _CHEVAUCHEMENT
        if debut < 0:
            debut = 0
    return morceaux


def extraire_texte(nom: str, donnees: bytes) -> str:
    """Extrait le texte brut d'un fichier (txt, md, pdf)."""
    suffixe = Path(nom).suffix.lower()
    if suffixe == ".docx":
        try:
            from docx import Document
            import io

            doc = Document(io.BytesIO(donnees))
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Lecture Word impossible : {exc}") from exc
    if suffixe == ".pdf":
        try:
            from pypdf import PdfReader
            import io

            lecteur = PdfReader(io.BytesIO(donnees))
            return "\n".join((page.extract_text() or "") for page in lecteur.pages)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Lecture PDF impossible : {exc}") from exc
    # Fichiers texte (txt, md, csv, log, code...).
    for enc in ("utf-8", "latin-1"):
        try:
            return donnees.decode(enc)
        except Exception:  # noqa: BLE001
            continue
    return donnees.decode("utf-8", "ignore")


def ajouter_document(nom: str, texte: str) -> dict:
    """Indexe un document (le remplace s'il existe deja)."""
    idx = _charger_index()
    # On retire l'ancienne version eventuelle.
    idx["chunks"] = [c for c in idx["chunks"] if c["doc"] != nom]
    morceaux = _decouper(texte)
    for i, m in enumerate(morceaux):
        idx["chunks"].append({"doc": nom, "i": i, "texte": m, "tokens": _tokeniser(m)})
    idx["documents"][nom] = {"morceaux": len(morceaux), "caracteres": len(texte)}
    _sauver_index(idx)
    return {"nom": nom, "morceaux": len(morceaux)}


def lister() -> List[dict]:
    idx = _charger_index()
    return [
        {"nom": nom, **infos} for nom, infos in idx.get("documents", {}).items()
    ]


def supprimer(nom: str) -> bool:
    idx = _charger_index()
    if nom not in idx.get("documents", {}):
        return False
    idx["chunks"] = [c for c in idx["chunks"] if c["doc"] != nom]
    idx["documents"].pop(nom, None)
    _sauver_index(idx)
    return True


def rechercher(question: str, k: int = 4) -> List[dict]:
    """Renvoie les k morceaux les plus pertinents pour la question (TF-IDF)."""
    idx = _charger_index()
    chunks = idx.get("chunks", [])
    if not chunks:
        return []

    mots_q = _tokeniser(question)
    if not mots_q:
        return []

    # IDF : rarete de chaque mot dans l'ensemble des morceaux.
    n = len(chunks)
    presence: dict[str, int] = {}
    for c in chunks:
        for mot in set(c["tokens"]):
            presence[mot] = presence.get(mot, 0) + 1
    idf = {m: math.log(1 + n / (1 + presence.get(m, 0))) for m in set(mots_q)}

    resultats = []
    for c in chunks:
        compte = {}
        for t in c["tokens"]:
            compte[t] = compte.get(t, 0) + 1
        score = sum(compte.get(m, 0) * idf.get(m, 0) for m in mots_q)
        if score > 0:
            # Normalisation legere par la longueur du morceau.
            score /= math.sqrt(len(c["tokens"]) + 1)
            resultats.append((score, c))

    resultats.sort(key=lambda x: x[0], reverse=True)
    return [
        {"doc": c["doc"], "texte": c["texte"], "score": round(s, 3)}
        for s, c in resultats[:k]
    ]


def contexte_pour_prompt(question: str, k: int = 4) -> str:
    """Construit un bloc a injecter dans le prompt, vide si rien de pertinent."""
    trouves = rechercher(question, k=k)
    if not trouves:
        return ""
    lignes = [
        "== EXTRAITS DE TES DOCUMENTS (utilise-les en priorite pour repondre) =="
    ]
    for t in trouves:
        lignes.append(f"[Source : {t['doc']}]\n{t['texte'].strip()}")
    lignes.append(
        "Reponds en t'appuyant sur ces extraits, de facon coherente et structuree. "
        "Si la reponse ne s'y trouve pas, dis-le et reponds avec tes connaissances."
    )
    return "\n\n".join(lignes)
