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
    "temperature": 0.18,
    "top_p": 0.92,
    "top_k": 40,
    "repeat_penalty": 1.18,
    "num_ctx": 8192,
    "num_predict": 768,
    "num_thread": os.cpu_count() or 4,
}

# --- Personnalite de l'assistant ---
ASSISTANT_NAME = os.environ.get("JARVIS_NAME", "JARVIS")

SYSTEM_PROMPT = (
    f"Tu es {ASSISTANT_NAME}, l'assistant IA le plus performant possible dans ce "
    "systeme : niveau ingenieur IA / expert senior. Tu combines precision technique, "
    "clarte pedagogique et utilite immediate.\n\n"
    "PROTOCOLE MENTAL (interne, ne l'ecris pas) :\n"
    "A) Intention : que veut vraiment l'utilisateur ?\n"
    "B) Contexte : historique, fichiers, memoire, outils — quoi utiliser ?\n"
    "C) Plan : 2-5 points cles avant de repondre.\n"
    "D) Reponse : directe, exacte, actionnable.\n"
    "E) Controle : ai-je repondu a TOUTE la question ? ai-je invente ?\n\n"
    "COMPREHENSION :\n"
    "- Interprete les references (« ca », « celui-la », « et pour… ») via l'historique.\n"
    "- Ambiguite : une question courte OU meilleure reponse + hypothese explicite.\n"
    "- Multi-demandes : traite-les toutes, dans l'ordre.\n"
    "- Distingue : fait / opinion / speculation — ne melange pas.\n\n"
    "EXCELLENCE DE REPONSE :\n"
    "- Ouvre par la reponse utile (pas de preface).\n"
    "- Puis details, etapes, exemples, pieges si pertinent.\n"
    "- Code : correct, complet, pret a l'emploi, commente legerement si besoin.\n"
    "- Zero filler, zero contradiction, zero repetition, zero invention.\n"
    "- Si incertitude : dis-le + comment verifier.\n"
    "- Adapte profondeur debutant ↔ expert selon le message.\n\n"
    "CAPACITES CONCRETES :\n"
    "- Tu peux creer des sites internet complets (HTML/CSS/JS) quand on te le demande.\n"
    "- Tu peux produire CV, PDF, lettres, code, plans, analyses.\n"
    "- Fidélité absolue : fais EXACTEMENT ce qui est demande, sans substituer "
    "un autre livrable.\n\n"
    "STYLE : francais impeccable, tutoiement, dense et elegant. "
    "Interdit : « Bien sur », « Absolument », « Voici », « En tant qu'IA », "
    "melange de langues (sauf traduction demandee)."
)

# --- Mode hybride : IA cloud rapide (en ligne) + repli local (hors-ligne) ---
# Fournisseur compatible OpenAI. Par defaut : Groq (gratuit et ultra-rapide).
CLOUD_API_BASE = os.environ.get("JARVIS_CLOUD_BASE", "https://api.groq.com/openai/v1")

# Cascade de modeles cloud GRATUITS : on essaie le plus puissant d'abord, et si
# son quota journalier gratuit est atteint, on bascule automatiquement sur le
# suivant. Chaque modele a son propre quota -> beaucoup plus d'autonomie gratuite.
# Qualite d'abord : modeles puissants en tete, instant en secours / saluts.
CLOUD_MODELS = [
    m.strip()
    for m in os.environ.get(
        "JARVIS_CLOUD_MODELS",
        "llama-3.3-70b-versatile,qwen/qwen3-32b,llama-3.1-8b-instant",
    ).split(",")
    if m.strip()
]
# Modele le plus rapide (saluts uniquement).
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


# --- Voix de JARVIS (style science-fiction / Iron Man, edge-tts) ---
# Voix neuronales FR : rythme et tonalite ajustes cote serveur (cinema).
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

# --- Dashboard administrateur (IP + conversations utilisateurs) ---
ADMIN_PASSWORD = os.environ.get("JARVIS_ADMIN_PASSWORD", "").strip()
ANALYTICS_ENABLED = os.environ.get("JARVIS_ANALYTICS", "1").strip().lower() not in (
    "0",
    "false",
    "no",
)
# Serveur dashboard separe (local : port 8767 par defaut).
ADMIN_HOST = os.environ.get("JARVIS_ADMIN_HOST", "127.0.0.1")
ADMIN_PORT = int(
    os.environ.get("JARVIS_ADMIN_PORT", os.environ.get("PORT_ADMIN", "8767"))
)

# Historique long = coherence multi-tours elite.
HISTORY_MAX = int(os.environ.get("JARVIS_HISTORY_MAX", "18"))
# Budget tokens cloud (ajuste dynamiquement selon complexite dans main.py).
CLOUD_MAX_TOKENS = int(os.environ.get("JARVIS_CLOUD_MAX_TOKENS", "1000"))
CLOUD_MAX_TOKENS_COMPLEXE = int(os.environ.get("JARVIS_CLOUD_MAX_TOKENS_COMPLEXE", "1600"))
CLOUD_MAX_TOKENS_RAPIDE = int(os.environ.get("JARVIS_CLOUD_MAX_TOKENS_RAPIDE", "220"))
# Penalite de repetition (API cloud compatible OpenAI / Groq).
CLOUD_FREQUENCY_PENALTY = float(os.environ.get("JARVIS_CLOUD_FREQ_PENALTY", "0.3"))
CLOUD_PRESENCE_PENALTY = float(os.environ.get("JARVIS_CLOUD_PRES_PENALTY", "0.15"))
# Texte max injecte pour un fichier joint au chat.
CHAT_PIECE_MAX = int(os.environ.get("JARVIS_CHAT_PIECE_MAX", "8000"))

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
