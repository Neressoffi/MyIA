"""Generation de sites web a partir d'une demande utilisateur.

Le modele produit un HTML autonome (CSS + JS integres). On extrait le code,
on le valide legerement, puis on le renvoie pour telechargement / apercu.
"""
from __future__ import annotations

import re
import unicodedata


PROMPT_SITE = (
    "Tu es un developpeur web senior (HTML/CSS/JS). Tu crees des sites internet "
    "complets, beaux et fonctionnels, en respectant EXACTEMENT la demande.\n\n"
    "REGLES STRICTES :\n"
    "1. Reponds UNIQUEMENT avec un seul fichier HTML complet, rien d'autre "
    "(pas d'explication avant/apres).\n"
    "2. Le fichier doit commencer par <!DOCTYPE html> et contenir <html>, <head>, <body>.\n"
    "3. CSS dans <style> et JS dans <script> (tout autonome, aucun fichier externe "
    "obligatoire). Polices Google Fonts autorisees via <link>.\n"
    "4. Design moderne, responsive (mobile + desktop), accessible, contraste lisible.\n"
    "5. Contenu en FRANCAIS sauf si l'utilisateur demande une autre langue.\n"
    "6. Inclus : navigation, hero, sections utiles, footer. Ajoute interactions JS "
    "simples si pertinent (menu mobile, formulaire, animations legeres).\n"
    "7. Respecte le brief : couleurs, ton, pages/sections, CTA, nom de marque.\n"
    "8. Pas de placeholders vagues ('lorem ipsum' minimal uniquement si vraiment necessaire).\n"
    "9. Si la demande est incomplete, fais des choix design coherents et professionels "
    "en restant fidele a l'intention.\n"
)


def demande_site(question: str) -> bool:
    """True si l'utilisateur veut un site / page web."""
    t = (question or "").lower().strip()
    if not t:
        return False
    signaux = (
        "site web", "site internet", "page web", "landing page", "landing-page",
        "page d'accueil", "page d accueil", "website", "webapp", "web app",
        "maquette web", "page html", "creer un site", "crée un site", "cree un site",
        "fais un site", "faire un site", "génère un site", "genere un site",
        "portfolio en ligne", "boutique en ligne", "vitrine",
    )
    if any(s in t for s in signaux):
        return True
    # "site" + verbe d'action
    actions = (
        "crée", "cree", "créer", "creer", "fais", "faire", "génère", "genere",
        "construis", "développe", "developpe", "code", "monte", "fabrique",
        "peux-tu", "pourrais-tu", "veux", "voudrais", "besoin",
    )
    if "site" in t and any(a in t for a in actions):
        return True
    if re.search(r"\bhtml\b", t) and any(a in t for a in actions) and len(t) < 220:
        return True
    return False


def extraire_html(texte: str) -> str:
    """Recupere le document HTML depuis la sortie modele."""
    t = (texte or "").strip()
    if not t:
        return ""

    # Bloc markdown ```html ... ```
    m = re.search(r"```(?:html|HTML)?\s*\n(.*?)```", t, flags=re.DOTALL)
    if m:
        t = m.group(1).strip()

    # Coupe avant/apres le doctype / html
    low = t.lower()
    start = low.find("<!doctype html")
    if start < 0:
        start = low.find("<html")
    if start >= 0:
        t = t[start:]
    end = t.lower().rfind("</html>")
    if end >= 0:
        t = t[: end + len("</html>")]

    t = t.strip()
    if "<html" not in t.lower():
        return ""
    if "<!doctype" not in t.lower():
        t = "<!DOCTYPE html>\n" + t
    return t


def titre_depuis_html(html: str, fallback: str = "Mon site") -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html or "", flags=re.I | re.DOTALL)
    if m:
        titre = re.sub(r"\s+", " ", m.group(1)).strip()
        if titre:
            return titre[:80]
    m2 = re.search(r"<h1[^>]*>(.*?)</h1>", html or "", flags=re.I | re.DOTALL)
    if m2:
        brut = re.sub(r"<[^>]+>", "", m2.group(1))
        brut = re.sub(r"\s+", " ", brut).strip()
        if brut:
            return brut[:80]
    return fallback[:80]


def nom_fichier(titre: str) -> str:
    base = (titre or "site").strip().lower()
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "_", base).strip("_")[:50] or "site"
    return f"{base}.html"


def apercu_texte(html: str, max_len: int = 700) -> str:
    """Resume textuel pour le chat (sans balises)."""
    t = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html or "")
    t = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", t)
    t = re.sub(r"(?is)<[^>]+>", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > max_len:
        return t[: max_len - 1] + "…"
    return t
