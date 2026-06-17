# Mettre JARVIS sur Git et en ligne (démo publique)

## Ce qui est privé vs public

| Élément | Sur votre PC (local) | En ligne (démo) |
|---------|----------------------|-----------------|
| Mot de passe | Oui, chiffré | Non (accès libre) |
| Mémoire / documents | Vos données dans `donnees/` | Temporaire, vide au départ |
| Ollama / Whisper | Oui | Non (cloud Groq uniquement) |
| Clé API | `cle_api.txt` (jamais sur Git) | Variable `GROQ_API_KEY` sur Render |

Les fichiers **personnels** sont exclus par `.gitignore` :
`donnees/`, `.jarvis_auth`, `cle_api.txt`, `.venv/`

---

## Étape 1 — Git sur votre PC

```powershell
cd "C:\Users\Ariel Ngoualem Pro\Desktop\MyIA"
git init
git branch -M main
git add .
git status
git commit -m "JARVIS : assistant IA open source (local + démo publique)"
```

Vérifiez que `git status` ne liste **pas** `cle_api.txt`, `donnees/`, `.jarvis_auth`.

---

## Étape 2 — Créer le dépôt GitHub

1. Allez sur https://github.com/new
2. Nom : `jarvis-assistant` (ou autre)
3. **Public** si vous voulez que tout le monde voie le code
4. Ne cochez pas « Add README »
5. Créez le dépôt

```powershell
git remote add origin https://github.com/VOTRE_PSEUDO/jarvis-assistant.git
git push -u origin main
```

---

## Étape 3 — Mettre en ligne sur Render (gratuit, simple)

> Vercel n'est pas adapté à ce projet (Python + API longue). **Render** convient mieux.

1. Compte sur https://render.com
2. **New +** → **Blueprint** (ou **Web Service**)
3. Connectez votre repo GitHub
4. Render lit `render.yaml` automatiquement
5. Dans **Environment**, ajoutez :
   - `GROQ_API_KEY` = votre clé gratuite https://console.groq.com/keys
6. Déployez → URL du type `https://jarvis-demo.onrender.com`

La variable `JARVIS_DEMO=1` active :
- pas de mot de passe
- pas de données personnelles
- IA via Groq (cloud)

---

## Étape 4 — Clé API Groq (obligatoire en ligne)

Sans clé, le chat en ligne ne fonctionnera pas.

1. https://console.groq.com → créer un compte gratuit
2. **API Keys** → Create
3. Sur Render : **Environment** → `GROQ_API_KEY` = la clé

---

## Tester en local (version privée)

Double-cliquez `Demarrer-JARVIS.bat` — mot de passe, chiffrement, Ollama, tout reste actif.

## Tester la démo en local

```powershell
$env:JARVIS_DEMO="1"
$env:GROQ_API_KEY="votre_cle"
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8765
```

Ouvrez http://127.0.0.1:8765 — pas de mot de passe, bandeau « Démo publique ».
