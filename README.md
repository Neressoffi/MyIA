# JARVIS — Assistant IA local, gratuit et 100% open source

Un assistant personnel inspiré de JARVIS (Iron Man) qui tourne **entièrement sur ta
machine**, **sans connexion internet** une fois installé. Tu discutes avec lui **par
écrit** ou **par note vocale**, et il te répond à voix haute.

Tout est gratuit et open source : aucun abonnement, aucune donnée envoyée sur internet.

---

## Ce dont tu as besoin (déjà vérifié sur ta machine)

- **Python 3.13** ✔
- **Node.js** (pas obligatoire pour cette version) ✔
- **Ollama** — le moteur qui fait tourner le modèle IA en local
- Ta machine : Intel i5-8365U, 16 Go RAM, SSD → on utilise un modèle léger (3B).

---

## Installation en 3 étapes

### 1. Installer Ollama (le moteur de l'IA)
Si ce n'est pas déjà fait, télécharge-le sur https://ollama.com puis installe-le.

### 2. Télécharger le modèle IA (une seule fois, ~2 Go)
Ouvre un terminal et tape :

```powershell
ollama pull qwen2.5:3b
```

> `qwen2.5:3b` est rapide et adapté à ton PC. Tu peux aussi essayer `llama3.2:3b`.

### 3. Lancer JARVIS
Double-clique sur **`Demarrer-JARVIS.bat`**.

La première fois, il installe automatiquement les dépendances Python (quelques
minutes). Ensuite, ton navigateur s'ouvre sur l'assistant.

---

## Comment l'utiliser

- **Écrire** : tape ton message et appuie sur Entrée.
- **Note vocale** : clique sur le micro 🎤, parle, reclique pour arrêter. JARVIS
  transcrit ta voix (hors-ligne) et répond.
- **Voix de JARVIS** : active/désactive le haut-parleur 🔊 à côté du champ de saisie.

---

## Personnalisation

Tout se règle dans `backend/config.py` :

- `MODEL_NAME` : le modèle IA utilisé (ex. `qwen2.5:3b`, `llama3.2:3b`, `mistral`).
- `ASSISTANT_NAME` : le nom de ton assistant.
- `SYSTEM_PROMPT` : sa personnalité (ton, style, règles).
- `WHISPER_MODEL` : qualité de la reconnaissance vocale (`tiny`, `base`, `small`).

---

## Les technologies utilisées (et pourquoi)

| Composant | Techno | Langage |
|-----------|--------|---------|
| Moteur du modèle IA | **Ollama** (basé sur llama.cpp) | C/C++ |
| Cerveau / serveur | **FastAPI** | Python |
| Reconnaissance vocale (offline) | **faster-whisper** | Python |
| Voix de l'assistant (offline) | **Web Speech API** du navigateur | JavaScript |
| Interface JARVIS | **HTML / CSS / JS** | JavaScript |

---

## Fonctionne sans internet ?

Oui. Une fois Ollama, le modèle et les dépendances installés, **tout fonctionne
hors-ligne**. Aucune donnée ne quitte ta machine.
