"""Configuration centrale de l'assistant JARVIS."""
import os
from pathlib import Path

# --- Modele de langage (via Ollama) ---
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
# Modele par defaut adapte a un PC sans GPU (i5 + 16 Go RAM).
MODEL_NAME = os.environ.get("JARVIS_MODEL", "qwen2.5:3b")

# Duree pendant laquelle le modele reste charge en RAM (reponses rapides).
KEEP_ALIVE = os.environ.get("JARVIS_KEEP_ALIVE", "30m")

# Reglages de generation : coherence, focus, pas de repetition.
# IMPORTANT : utilises a l'identique au prechauffage ET au chat, pour eviter
# qu'Ollama recharge le modele (ce qui ralentirait la 1ere reponse).
GEN_OPTIONS = {
    "temperature": 0.25,
    "top_p": 0.88,
    "top_k": 35,
    "repeat_penalty": 1.12,
    "num_ctx": 1536,
    "num_predict": 240,
    "num_thread": os.cpu_count() or 4,
}

# --- Personnalite de l'assistant ---
ASSISTANT_NAME = os.environ.get("JARVIS_NAME", "JARVIS")

SYSTEM_PROMPT = (
    f"Tu es {ASSISTANT_NAME}, compagnon IA inspire d'Iron Man : chaleureux, vif, "
    "fiable, comme un ami brillant.\n\n"
    "COHERENCE (prioritaire) :\n"
    "- Reponds precisement a la question, en restant strictement sur le sujet.\n"
    "- Tes phrases s'enchainent logiquement : une idee mene a la suivante.\n"
    "- Tiens compte de TOUT l'historique : ne contredis pas ce qui a deja ete dit.\n"
    "- Ne te repetes pas, ne radotes pas, n'invente pas de mots ou d'infos.\n"
    "- Si tu n'es pas sur, dis-le honnetement au lieu d'improviser.\n\n"
    "POLYVALENCE : tu maitrises tous les sujets (code, redaction, sciences, business, "
    "creativite, sante, droit, finance, langues, analyse, productivite). Adapte ton "
    "niveau et ton format a la demande.\n\n"
    "STYLE : francais naturel et correct, tu tutoies. Concis mais complet. "
    "Pas d'intro vide ('Bien sur', 'Voici'). Pas de 'En tant qu'IA'."
)

# --- Mode hybride : IA cloud rapide (en ligne) + repli local (hors-ligne) ---
# Fournisseur compatible OpenAI. Par defaut : Groq (gratuit et ultra-rapide).
CLOUD_API_BASE = os.environ.get("JARVIS_CLOUD_BASE", "https://api.groq.com/openai/v1")

# Cascade de modeles cloud GRATUITS : on essaie le plus puissant d'abord, et si
# son quota journalier gratuit est atteint, on bascule automatiquement sur le
# suivant. Chaque modele a son propre quota -> beaucoup plus d'autonomie gratuite.
CLOUD_MODELS = [
    m.strip()
    for m in os.environ.get(
        "JARVIS_CLOUD_MODELS",
        "llama-3.1-8b-instant,llama-3.3-70b-versatile,qwen/qwen3-32b",
    ).split(",")
    if m.strip()
]
# Modele le plus rapide (prioritaire pour le chat courant).
CLOUD_MODEL_RAPIDE = os.environ.get("JARVIS_CLOUD_RAPIDE", "llama-3.1-8b-instant")
# Modele principal (affiche dans l'interface).
CLOUD_MODEL = CLOUD_MODELS[0] if CLOUD_MODELS else "llama-3.3-70b-versatile"


def _charge_cle_cloud() -> str:
    """Recupere la cle API gratuite depuis l'environnement ou un fichier local."""
    cle = os.environ.get("JARVIS_CLOUD_KEY") or os.environ.get("GROQ_API_KEY")
    if cle:
        return cle.strip()
    fichier = Path(__file__).resolve().parent.parent / "cle_api.txt"
    if fichier.exists():
        contenu = fichier.read_text(encoding="utf-8").strip()
        # On ignore les lignes de commentaire eventuelles.
        for ligne in contenu.splitlines():
            ligne = ligne.strip()
            if ligne and not ligne.startswith("#"):
                return ligne
    return ""


CLOUD_API_KEY = _charge_cle_cloud()


# --- Generation d'images (Pollinations, gratuit) ---
# Un token gratuit (compte GitHub sur https://auth.pollinations.ai) debloque
# l'acces sans file d'attente. Sans token, on tente l'acces anonyme (limite).
def _charge_cle_image() -> str:
    cle = os.environ.get("JARVIS_IMAGE_KEY") or os.environ.get("POLLINATIONS_TOKEN")
    if cle:
        return cle.strip()
    fichier = Path(__file__).resolve().parent.parent / "cle_image.txt"
    if fichier.exists():
        for ligne in fichier.read_text(encoding="utf-8").splitlines():
            ligne = ligne.strip()
            if ligne and not ligne.startswith("#"):
                return ligne
    return ""


IMAGE_API_KEY = _charge_cle_image()


# --- Voix de JARVIS (synthese vocale naturelle, edge-tts, gratuit) ---
# Voix neuronales francaises quasi humaines, choisies selon le visage.
VOIX_NATURELLES = {
    "homme": os.environ.get("JARVIS_VOIX_HOMME", "fr-FR-HenriNeural"),
    "femme": os.environ.get("JARVIS_VOIX_FEMME", "fr-FR-DeniseNeural"),
}


# --- Reconnaissance vocale (Whisper) ---
# tiny / base / small / medium : plus grand = plus precis mais plus lent sur CPU.
# 'small' offre le meilleur compromis precision/vitesse pour comprendre le francais.
WHISPER_MODEL = os.environ.get("JARVIS_WHISPER", "tiny")
WHISPER_LANGUAGE = os.environ.get("JARVIS_WHISPER_LANG", "fr")

# --- Serveur ---
HOST = os.environ.get("JARVIS_SERVER_HOST", "127.0.0.1")
# Render/Railway imposent PORT ; en local on garde 8765 par defaut.
PORT = int(os.environ.get("PORT", os.environ.get("JARVIS_SERVER_PORT", "8765")))

# --- Mode demo public (en ligne, sans mot de passe ni donnees perso) ---
_ON_RENDER = os.environ.get("RENDER", "").strip().lower() in ("1", "true", "yes")
DEMO_MODE = (
    os.environ.get("JARVIS_DEMO", "").strip().lower() in ("1", "true", "yes")
    or _ON_RENDER
)
DISABLE_WHISPER = DEMO_MODE or os.environ.get(
    "JARVIS_DISABLE_WHISPER", ""
).strip().lower() in ("1", "true", "yes")

# Limite l'historique envoye au modele (moins de tokens = reponse plus rapide).
HISTORY_MAX = int(os.environ.get("JARVIS_HISTORY_MAX", "8"))
CLOUD_MAX_TOKENS = int(os.environ.get("JARVIS_CLOUD_MAX_TOKENS", "400"))
# Texte max injecte pour un fichier joint au chat (moins = analyse plus rapide).
CHAT_PIECE_MAX = int(os.environ.get("JARVIS_CHAT_PIECE_MAX", "6000"))

# --- Securite et confidentialite ---
# Taille max des fichiers uploades (Mo).
MAX_UPLOAD_OCTETS = int(os.environ.get("JARVIS_MAX_UPLOAD", str(15 * 1024 * 1024)))
# Mode strict : aucune donnee envoyee au cloud sans autorisation explicite.
PRIVACY_STRICT = os.environ.get("JARVIS_PRIVACY_STRICT", "1") == "1"

# --- Vision (analyse d'images envoyees par l'utilisateur) ---
VISION_CLOUD_MODELS = [
    m.strip()
    for m in os.environ.get(
        "JARVIS_VISION_CLOUD",
        "meta-llama/llama-4-scout-17b-16e-instruct,meta-llama/llama-4-maverick-17b-128e-instruct",
    ).split(",")
    if m.strip()
]
VISION_LOCAL_MODELS = [
    m.strip()
    for m in os.environ.get(
        "JARVIS_VISION_LOCAL",
        "moondream,llava,llama3.2-vision",
    ).split(",")
    if m.strip()
]
