"""Outils d'agent pour JARVIS.

Donne a l'assistant des capacites concretes :
- calculer() : calculs fiables (sans se tromper comme un LLM).
- rechercher_web() : informations a jour depuis Internet (gratuit, sans cle).

L'idee : avant de repondre, on detecte si un outil est utile, on l'execute,
puis on injecte le resultat dans le contexte. Le modele s'appuie dessus pour
donner une reponse fiable. Fonctionne aussi bien avec le cloud que le local.
"""
from __future__ import annotations

import ast
import html
import operator
import re
from typing import List

import httpx

# --------------------------------------------------------------------------
# 1) Calculatrice fiable (evaluation arithmetique securisee, sans eval brut)
# --------------------------------------------------------------------------
_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _evaluer(noeud):
    if isinstance(noeud, ast.Constant):
        if isinstance(noeud.value, (int, float)):
            return noeud.value
        raise ValueError("valeur non numerique")
    if isinstance(noeud, ast.BinOp) and type(noeud.op) in _OPS:
        return _OPS[type(noeud.op)](_evaluer(noeud.left), _evaluer(noeud.right))
    if isinstance(noeud, ast.UnaryOp) and type(noeud.op) in _OPS:
        return _OPS[type(noeud.op)](_evaluer(noeud.operand))
    raise ValueError("expression non autorisee")


def calculer(expression: str) -> str:
    """Evalue une expression arithmetique de maniere sure."""
    expr = expression.strip()
    # On accepte les ecritures courantes en francais.
    expr = expr.replace("x", "*").replace("×", "*").replace("÷", "/").replace(",", ".")
    expr = re.sub(r"[^0-9+\-*/().%\s]", "", expr)
    if not expr:
        raise ValueError("expression vide")
    arbre = ast.parse(expr, mode="eval")
    resultat = _evaluer(arbre.body)
    # Affichage propre (entier si possible).
    if isinstance(resultat, float) and resultat.is_integer():
        resultat = int(resultat)
    return str(resultat)


def ressemble_a_un_calcul(texte: str) -> str | None:
    """Detecte une expression purement arithmetique a calculer."""
    t = texte.strip().lower()
    t = re.sub(r"^(combien font|combien fait|calcule[rz]?|resultat de|que vaut)\s*", "", t)
    t = t.rstrip("?=. ")
    # Doit contenir un operateur et essentiellement des chiffres/operateurs.
    if re.search(r"[\d)]\s*[-+*/x×÷]\s*[\d(]", t) and re.fullmatch(
        r"[0-9+\-*/().%\s x×÷,]+", t
    ):
        return t
    return None


# --------------------------------------------------------------------------
# 2) Recherche web (DuckDuckGo, gratuit et sans cle)
# --------------------------------------------------------------------------
_ENTETES = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


async def rechercher_web(requete: str, n: int = 4) -> List[dict]:
    """Recherche sur le web via DuckDuckGo (version HTML legere, sans cle)."""
    url = "https://html.duckduckgo.com/html/"
    async with httpx.AsyncClient(timeout=5, headers=_ENTETES) as client:
        r = await client.post(url, data={"q": requete})
        r.raise_for_status()
        page = r.text

    resultats: List[dict] = []
    # Titres + liens.
    for m in re.finditer(
        r'<a[^>]*class="result__a"[^>]*>(.*?)</a>', page, re.DOTALL
    ):
        titre = html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
        if titre:
            resultats.append({"titre": titre, "extrait": ""})
        if len(resultats) >= n:
            break

    # Extraits (snippets) associes.
    extraits = re.findall(
        r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>', page, re.DOTALL
    )
    for i, ex in enumerate(extraits[:n]):
        texte = html.unescape(re.sub(r"<[^>]+>", "", ex)).strip()
        if i < len(resultats):
            resultats[i]["extrait"] = texte

    return resultats


# Declencheurs STRICTS : recherche web seulement si demande explicite (lente).
_MOTS_WEB = (
    "cherche sur internet", "recherche sur internet", "cherche sur le web",
    "recherche sur le web", "google ", "actualites du jour", "actualité du jour",
    "meteo a", "météo à", "cours du bitcoin", "cours de l'euro",
    "quoi de neuf dans le monde", "dernieres nouvelles", "dernières nouvelles",
)


def a_besoin_du_web(texte: str) -> bool:
    """Heuristique : la question necessite-t-elle une recherche en ligne ?"""
    t = texte.lower()
    return any(mot in t for mot in _MOTS_WEB)


async def contexte_outils(question: str) -> str:
    """Prepare un bloc de contexte issu des outils, vide si aucun n'est utile."""
    blocs: List[str] = []

    # Calcul fiable.
    calc = ressemble_a_un_calcul(question)
    if calc:
        try:
            res = calculer(calc)
            blocs.append(
                f"== RESULTAT DE CALCUL (fiable) ==\n{calc} = {res}\n"
                "Donne ce resultat exact a l'utilisateur."
            )
        except Exception:  # noqa: BLE001
            pass

    # Recherche web.
    if a_besoin_du_web(question):
        try:
            res = await rechercher_web(question, n=4)
            if res:
                lignes = ["== RESULTATS WEB (informations a jour) =="]
                for r in res:
                    extrait = f" — {r['extrait']}" if r["extrait"] else ""
                    lignes.append(f"• {r['titre']}{extrait}")
                lignes.append(
                    "Resume ces informations pour repondre clairement. "
                    "Precise que cela vient d'une recherche web."
                )
                blocs.append("\n".join(lignes))
        except Exception:  # noqa: BLE001
            blocs.append(
                "== RECHERCHE WEB ==\nLa recherche en ligne a echoue "
                "(hors-ligne ?). Reponds avec tes connaissances et signale-le."
            )

    return "\n\n".join(blocs)
