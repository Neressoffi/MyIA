"""Memoire persistante de JARVIS.

Stocke, entre deux sessions, ce qui rend l'assistant vraiment "le tien" :
- ton profil (prenom, ce que tu aimes, ton contexte),
- des faits importants a retenir,
- de courts resumes des conversations passees.

Tout est garde en local dans un simple fichier JSON (aucun cloud, prive).
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import List

from . import securite

# Fichier de memoire (cree automatiquement au premier usage).
_DOSSIER = Path(__file__).resolve().parent.parent / "donnees"
_FICHIER = _DOSSIER / "memoire.json"
_VERROU = threading.Lock()

_DEFAUT = {
    "profil": {
        "prenom": "",
        "a_propos": "",          # contexte libre (metier, gouts, objectifs...)
    },
    "faits": [],                 # liste de faits a retenir ("aime le foot", ...)
    "resumes": [],               # courts resumes des conversations passees
}

# Limites pour ne pas faire exploser le contexte envoye au modele.
_MAX_FAITS = 40
_MAX_RESUMES = 20


def charger() -> dict:
    """Lit la memoire depuis le disque (renvoie une structure complete)."""
    data = securite.lire_json_protege(_FICHIER, None)
    if data is None:
        return json.loads(json.dumps(_DEFAUT))
    # On complete les cles manquantes (compatibilite ascendante).
    fusion = json.loads(json.dumps(_DEFAUT))
    fusion.update({k: data.get(k, v) for k, v in fusion.items()})
    fusion["profil"] = {**_DEFAUT["profil"], **(data.get("profil") or {})}
    return fusion


def sauver(data: dict) -> None:
    """Ecrit la memoire sur le disque (chiffree si session active)."""
    with _VERROU:
        securite.ecrire_json_protege(_FICHIER, data)


def definir_profil(prenom: str | None = None, a_propos: str | None = None) -> dict:
    """Met a jour le profil (prenom et/ou contexte libre)."""
    data = charger()
    if prenom is not None:
        data["profil"]["prenom"] = prenom.strip()
    if a_propos is not None:
        data["profil"]["a_propos"] = a_propos.strip()
    sauver(data)
    return data


def ajouter_fait(fait: str) -> dict:
    """Ajoute un fait a retenir (sans doublon)."""
    fait = (fait or "").strip()
    data = charger()
    if fait and fait.lower() not in [f.lower() for f in data["faits"]]:
        data["faits"].append(fait)
        data["faits"] = data["faits"][-_MAX_FAITS:]
        sauver(data)
    return data


def ajouter_resume(resume: str) -> dict:
    """Ajoute un court resume de conversation."""
    resume = (resume or "").strip()
    data = charger()
    if resume:
        data["resumes"].append(resume)
        data["resumes"] = data["resumes"][-_MAX_RESUMES:]
        sauver(data)
    return data


def oublier_tout() -> dict:
    """Efface toute la memoire (repart de zero)."""
    data = json.loads(json.dumps(_DEFAUT))
    sauver(data)
    return data


def texte_pour_prompt() -> str:
    """Construit un bloc texte a injecter dans le prompt systeme.

    Renvoie une chaine vide si la memoire est totalement vide.
    """
    data = charger()
    prenom = data["profil"].get("prenom", "").strip()
    a_propos = data["profil"].get("a_propos", "").strip()
    faits: List[str] = data.get("faits", [])
    resumes: List[str] = data.get("resumes", [])

    if not (prenom or a_propos or faits or resumes):
        return ""

    lignes = ["== CE QUE TU SAIS DEJA SUR L'UTILISATEUR (memoire) =="]
    if prenom:
        lignes.append(f"- Son prenom : {prenom}. Utilise-le naturellement.")
    if a_propos:
        lignes.append(f"- A son sujet : {a_propos}")
    if faits:
        lignes.append("- Faits a retenir :")
        lignes += [f"   • {f}" for f in faits]
    if resumes:
        lignes.append("- Resume des echanges precedents :")
        lignes += [f"   • {r}" for r in resumes[-5:]]
    lignes.append(
        "Sers-toi de ces informations pour etre personnel et coherent, "
        "sans les reciter betement."
    )
    return "\n".join(lignes)
