// JARVIS - logique de l'interface (chat en streaming + voix + etats du reacteur).

// --- Securite : acces prive (mot de passe + session) ---
const lockScreen = document.getElementById("lock-screen");
const lockPass = document.getElementById("lock-pass");
const lockPass2 = document.getElementById("lock-pass2");
const lockErr = document.getElementById("lock-err");
const lockBtn = document.getElementById("lock-btn");
let lockModeSetup = true;

function getSession() { return sessionStorage.getItem("jarvis_session"); }
function setSession(t) { sessionStorage.setItem("jarvis_session", t); }
function clearSession() { sessionStorage.removeItem("jarvis_session"); }

async function apiFetch(url, opts = {}) {
  const token = getSession();
  opts.headers = { ...(opts.headers || {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) };
  const r = await fetch(url, opts);
  if (r.status === 401 && !url.includes("/api/auth/status") && !url.includes("/api/auth/setup") && !url.includes("/api/auth/login")) {
    clearSession();
    afficherVerrou(true);
  }
  return r;
}

function afficherVerrou(configure) {
  if (!lockScreen) return;
  lockModeSetup = !configure;
  lockScreen.classList.remove("hidden");
  document.querySelector(".app")?.classList.add("locked");
  if (lockPass2) lockPass2.classList.toggle("lock-hidden", configure);
  const desc = document.getElementById("lock-desc");
  if (desc) {
    desc.textContent = configure
      ? "Entrez votre mot de passe pour déverrouiller JARVIS."
      : "Choisissez un mot de passe (min. 6 caractères). Vos données seront chiffrées sur ce PC.";
  }
  if (lockBtn) lockBtn.textContent = configure ? "Déverrouiller" : "Créer mon accès privé";
  const hint = document.getElementById("lock-hint");
  if (hint) hint.textContent = configure ? "" : "Notez-le bien : sans ce mot de passe, vos données restent illisibles.";
  if (lockErr) lockErr.textContent = "";
  if (lockPass) lockPass.value = "";
  if (lockPass2) lockPass2.value = "";
}

function masquerVerrou() {
  lockScreen?.classList.add("hidden");
  document.querySelector(".app")?.classList.remove("locked");
  // Acces direct au chat : on retire l'animation de boot.
  const boot = document.getElementById("boot");
  if (boot) {
    boot.classList.add("hidden");
    sessionStorage.setItem("jarvis_boot", "ok");
    setTimeout(() => boot.remove(), 100);
  }
  inputEl?.focus();
}

function afficherBandeauDemo() {
  if (document.getElementById("demo-banner")) return;
  const b = document.createElement("div");
  b.id = "demo-banner";
  b.className = "demo-banner";
  b.textContent = "🌐 Démo publique — données temporaires, sans mot de passe. Version locale = privée sur votre PC.";
  document.querySelector(".app")?.prepend(b);
}

async function initSecurite() {
  const r0 = await fetch("/api/auth/status");
  if (r0.ok) {
    const s0 = await r0.json();
    if (s0.demo) {
      isDemo = true;
      cloudAutorise = s0.cloud_autorise;
      cloudConfigured = !!s0.cloud_configure;
      setSession("demo-public");
      masquerVerrou();
      afficherBandeauDemo();
      applyDemoUI();
      return;
    }
  }
  const token = getSession();
  if (token) {
    const r = await fetch("/api/auth/check", { headers: { Authorization: `Bearer ${token}` } });
    if (r.ok) {
      const d = await r.json();
      if (d.authenticated) {
        cloudAutorise = d.cloud_autorise;
        masquerVerrou();
        return;
      }
    }
    clearSession();
  }
  const r = await fetch("/api/auth/status");
  if (!r.ok) {
    afficherVerrou(false);
    if (lockErr) {
      lockErr.textContent = r.status === 404
        ? "Mauvaise adresse. Lancez Demarrer-JARVIS.bat (http://127.0.0.1:8765)."
        : "Serveur indisponible. Lancez Demarrer-JARVIS.bat.";
    }
    await new Promise((resolve) => { window._onAuthOk = resolve; });
    return;
  }
  const s = await r.json();
  cloudAutorise = s.cloud_autorise;
  afficherVerrou(s.configure);
  await new Promise((resolve) => { window._onAuthOk = resolve; });
}

async function lireErreurApi(r) {
  try {
    const d = await r.json();
    if (typeof d.detail === "string") return d.detail;
    if (Array.isArray(d.detail)) return d.detail.map((x) => x.msg || x).join(", ");
    return d.message || d.detail || null;
  } catch {
    return null;
  }
}

async function soumettreVerrou() {
  const pass = lockPass?.value || "";
  if (lockErr) lockErr.textContent = "";
  if (pass.length < 6) {
    if (lockErr) lockErr.textContent = "Minimum 6 caractères.";
    return;
  }
  if (lockBtn) { lockBtn.disabled = true; lockBtn.textContent = "Patientez…"; }
  try {
    if (lockModeSetup) {
      const pass2 = lockPass2?.value || "";
      if (pass !== pass2) {
        if (lockErr) lockErr.textContent = "Les mots de passe ne correspondent pas.";
        return;
      }
      const r = await fetch("/api/auth/setup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mot_de_passe: pass, confirmation: pass2 }),
      });
      if (r.status === 404 || r.status === 405) {
        throw new Error("Serveur non à jour. Fermez JARVIS et relancez Demarrer-JARVIS.bat.");
      }
      if (!r.ok) throw new Error((await lireErreurApi(r)) || "Erreur");
      const d = await r.json();
      setSession(d.token);
    } else {
      const r = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mot_de_passe: pass }),
      });
      if (r.status === 404 || r.status === 405) {
        throw new Error("Serveur non à jour. Fermez JARVIS et relancez Demarrer-JARVIS.bat.");
      }
      if (!r.ok) throw new Error((await lireErreurApi(r)) || "Mot de passe incorrect");
      const d = await r.json();
      setSession(d.token);
    }
    masquerVerrou();
    const chk = await apiFetch("/api/auth/check", { headers: { Authorization: `Bearer ${getSession()}` } });
    const info = await chk.json();
    cloudAutorise = info.cloud_autorise;
    if (window._onAuthOk) { window._onAuthOk(); window._onAuthOk = null; }
    checkHealth();
  } catch (e) {
    if (lockErr) lockErr.textContent = e.message || "Erreur";
  } finally {
    if (lockBtn) {
      lockBtn.disabled = false;
      lockBtn.textContent = lockModeSetup ? "Créer mon accès privé" : "Déverrouiller";
    }
  }
}

lockBtn?.addEventListener("click", soumettreVerrou);
lockPass?.addEventListener("keydown", (e) => { if (e.key === "Enter") soumettreVerrou(); });
lockPass2?.addEventListener("keydown", (e) => { if (e.key === "Enter") soumettreVerrou(); });

const chatEl = document.getElementById("chat");
const inputEl = document.getElementById("input");
const sendBtn = document.getElementById("send-btn");
const micBtn = document.getElementById("mic-btn");
const ttsToggle = document.getElementById("tts-toggle");
const statusDot = document.getElementById("status-dot");
const statusText = document.getElementById("status-text");
const welcome = document.getElementById("welcome");
const reactor = document.getElementById("reactor");
const hudState = document.getElementById("hud-state");
const modelSelect = document.getElementById("model-select");
const modeBadge = document.getElementById("mode-badge");
// Panneau de personnalisation de la voix
const voiceModal = document.getElementById("voice-modal");
const voiceSettingsBtn = document.getElementById("voice-settings-btn");
const voiceList = document.getElementById("voice-list");
const rateRange = document.getElementById("rate-range");
const pitchRange = document.getElementById("pitch-range");
const rateVal = document.getElementById("rate-val");
const pitchVal = document.getElementById("pitch-val");
const ttsEnabled = document.getElementById("tts-enabled");
const testVoiceBtn = document.getElementById("test-voice-btn");
const saveVoiceBtn = document.getElementById("save-voice-btn");

// Historique de la conversation envoye au modele.
const history = [];

// Indicateur de mode (cloud rapide / local hors-ligne).
function setModeBadge(mode, modele) {
  const teleMode = document.getElementById("tele-mode");
  if (mode === "cloud") {
    modeBadge.className = "mode-badge cloud";
    modeBadge.textContent = "⚡ Rapide (en ligne)";
    modeBadge.title = "IA cloud : " + (modele || "");
    if (teleMode) teleMode.textContent = "EN LIGNE";
  } else if (mode === "local") {
    modeBadge.className = "mode-badge local";
    modeBadge.textContent = "💻 Local (hors-ligne)";
    modeBadge.title = "Modèle local : " + (modele || "");
    if (teleMode) teleMode.textContent = "LOCAL";
  }
}

// Modele IA actuellement selectionne (null = modele par defaut du serveur).
let currentModel = null;
let modelsLoaded = false;
let cloudConfigured = false;
let cloudAutorise = false;
let isDemo = false;

function applyDemoUI() {
  if (!isDemo) return;
  if (micBtn) {
    micBtn.disabled = false;
    micBtn.title = "Note vocale";
    micBtn.style.opacity = "";
  }
  const lockUrl = document.querySelector(".lock-url");
  if (lockUrl) lockUrl.style.display = "none";
}

function speechRecognitionDisponible() {
  return !!(window.SpeechRecognition || window.webkitSpeechRecognition);
}

async function transcrireNavigateur() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) throw new Error("Navigateur non compatible (utilisez Chrome ou Edge).");
  return new Promise((resolve, reject) => {
    const rec = new SR();
    rec.lang = "fr-FR";
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    rec.onresult = (e) => resolve((e.results[0][0].transcript || "").trim());
    rec.onerror = (e) => reject(new Error(e.error || "echec reconnaissance"));
    rec.onend = () => {};
    rec.start();
    window._jarvisRec = rec;
  });
}

function arreterTranscrireNavigateur() {
  try { window._jarvisRec?.stop(); } catch {}
  window._jarvisRec = null;
}

// ----------------------------------------------------------------------
// Etats du reacteur Arc : idle / listening / thinking / speaking
// ----------------------------------------------------------------------
const STATE_LABELS = {
  idle: "En veille",
  listening: "Je t'écoute…",
  thinking: "…",
  speaking: "JARVIS parle…",
};
function setState(state) {
  reactor.dataset.state = state;
  hudState.textContent = STATE_LABELS[state] || "";
}

// ----------------------------------------------------------------------
// Etat de connexion (Ollama / cloud)
// ----------------------------------------------------------------------
async function checkHealth() {
  try {
    const r = await apiFetch("/api/health");
    const data = await r.json();
    isDemo = !!data.demo;
    if (isDemo) {
      applyDemoUI();
      if (data.cloud_configure && data.cloud_autorise) {
        statusDot.className = "dot ok";
        statusText.textContent = "Démo en ligne";
        setModeBadge("cloud", data.cloud_modele || "Groq");
      } else {
        statusDot.className = "dot ko";
        statusText.textContent = "Clé Groq manquante";
        setModeBadge("cloud", "—");
      }
      cloudConfigured = !!data.cloud_configure;
      cloudAutorise = !!data.cloud_autorise;
      return;
    }
    if (data.ollama) {
      statusDot.className = "dot ok";
      statusText.textContent = "Prêt";
      populateModels(data.models, data.model_par_defaut);
    } else {
      statusDot.className = "dot ko";
      statusText.textContent = "Ollama non démarré";
    }
    // Indication du mode attendu (avant meme d'envoyer un message).
    if (modeBadge.textContent === "—") {
      if (data.cloud_configure) setModeBadge("cloud", data.cloud_modele);
      else setModeBadge("local", data.model_par_defaut);
    }
    cloudConfigured = !!data.cloud_configure;
    cloudAutorise = !!data.cloud_autorise;
  } catch {
    statusDot.className = "dot ko";
    statusText.textContent = "Serveur injoignable";
  }
}
// Remplit le menu de choix du modele (sans ecraser le choix de l'utilisateur).
function populateModels(models, defaut) {
  if (!models || !models.length) return;
  const previous = currentModel || defaut;
  // On ne reconstruit la liste que si elle a change.
  const existing = Array.from(modelSelect.options).map((o) => o.value);
  const changed = existing.length !== models.length || models.some((m) => !existing.includes(m));
  if (changed) {
    modelSelect.innerHTML = "";
    models.forEach((m) => {
      const opt = document.createElement("option");
      opt.value = m;
      // Repere clair selon la taille (RAM) du modele local.
      let suffixe = "";
      if (m.includes(":3b") || m.includes(":2b") || m.includes(":1")) suffixe = " — léger ✅";
      else if (m.includes(":7b") || m.includes(":8b")) suffixe = " — lourd ⚠️ (beaucoup de RAM)";
      opt.textContent = m + suffixe;
      modelSelect.appendChild(opt);
    });
  }
  if (!modelsLoaded) {
    currentModel = models.includes(previous) ? previous : models[0];
    modelSelect.value = currentModel;
    modelsLoaded = true;
  }
}

modelSelect.addEventListener("change", () => {
  currentModel = modelSelect.value;
});

// Demarrage apres authentification (voir fin du fichier).
// ----------------------------------------------------------------------
// Affichage des messages
// ----------------------------------------------------------------------
function addMessage(role, text, extraClass = "") {
  if (welcome) welcome.style.display = "none";
  const div = document.createElement("div");
  div.className = `msg ${role} ${extraClass}`.trim();
  div.textContent = text;
  chatEl.appendChild(div);
  chatEl.scrollTop = chatEl.scrollHeight;
  return div;
}

// ----------------------------------------------------------------------
// Voix de JARVIS (synthese vocale du navigateur) + personnalisation
// ----------------------------------------------------------------------
const VOICE_DEFAULTS = { voiceURI: "", rate: 1.0, pitch: 1.0, enabled: true, gender: "femme" };
const avatarImg = document.getElementById("avatar");
const avatarOpts = document.querySelectorAll(".avatar-opt");

function applyAvatar() {
  if (avatarImg) avatarImg.src = voiceSettings.gender === "homme" ? "/avatar-homme.png" : "/avatar-femme.png";
  avatarOpts.forEach((b) => b.classList.toggle("selected", b.dataset.gender === voiceSettings.gender));
}
let voiceSettings = loadVoiceSettings();

function loadVoiceSettings() {
  try {
    return { ...VOICE_DEFAULTS, ...JSON.parse(localStorage.getItem("jarvis_voice") || "{}") };
  } catch {
    return { ...VOICE_DEFAULTS };
  }
}
function saveVoiceSettings() {
  localStorage.setItem("jarvis_voice", JSON.stringify(voiceSettings));
}

function getVoices() {
  return ("speechSynthesis" in window) ? speechSynthesis.getVoices() : [];
}

// Remplit la liste des voix (les voix francaises en premier).
function populateVoiceList() {
  const voices = getVoices();
  if (!voices.length) return;
  const fr = voices.filter((v) => v.lang.toLowerCase().startsWith("fr"));
  const autres = voices.filter((v) => !v.lang.toLowerCase().startsWith("fr"));
  const ordered = [...fr, ...autres];

  voiceList.innerHTML = "";
  ordered.forEach((v) => {
    const opt = document.createElement("option");
    opt.value = v.voiceURI;
    const fiable = v.localService ? "✓ hors-ligne" : "⚠ en ligne";
    opt.textContent = `${v.name} (${v.lang}) · ${fiable}`;
    voiceList.appendChild(opt);
  });

  // Voix par defaut : une voix francaise FIABLE (locale) pour garantir le son.
  if (!voiceSettings.voiceURI) {
    const def = fiableLocalVoice();
    if (def) voiceSettings.voiceURI = def.voiceURI;
  }
  if (voiceSettings.voiceURI) voiceList.value = voiceSettings.voiceURI;
}

function pickVoice() {
  const voices = getVoices();
  return (
    voices.find((v) => v.voiceURI === voiceSettings.voiceURI) ||
    voices.find((v) => v.lang.toLowerCase().startsWith("fr")) ||
    voices[0]
  );
}

// Trouve une voix FIABLE (locale) pour le repli si la voix choisie reste muette.
function fiableLocalVoice() {
  const voices = getVoices();
  return (
    voices.find((v) => v.localService && v.lang.toLowerCase().startsWith("fr")) ||
    voices.find((v) => v.localService) ||
    voices.find((v) => v.lang.toLowerCase().startsWith("fr")) ||
    voices[0]
  );
}

function _utterance(text, voice) {
  const u = new SpeechSynthesisUtterance(text);
  if (voice) { u.voice = voice; u.lang = voice.lang; } else { u.lang = "fr-FR"; }
  u.rate = voiceSettings.rate;
  u.pitch = voiceSettings.pitch;
  return u;
}

let currentAudio = null;
let audioUnlocked = false;

function isMobileDevice() {
  return /Android|iPhone|iPad|iPod/i.test(navigator.userAgent)
    || (navigator.maxTouchPoints > 1 && window.matchMedia("(max-width: 900px)").matches);
}

/** Debloque l'audio sur mobile (iOS bloque sans geste utilisateur). */
function unlockAudio() {
  if (audioUnlocked) return;
  audioUnlocked = true;
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (Ctx) {
      const ctx = new Ctx();
      ctx.resume().catch(() => {});
    }
  } catch {}
  if ("speechSynthesis" in window) {
    try { speechSynthesis.resume(); } catch {}
    speechSynthesis.getVoices();
  }
}

function preferBrowserTTS() {
  return isMobileDevice();
}

document.addEventListener("touchstart", unlockAudio, { once: true, passive: true });
document.addEventListener("click", unlockAudio, { once: true });

// ----------------------------------------------------------------------
// Voix EN FLUX : JARVIS parle phrase par phrase PENDANT qu'il ecrit.
// Chaque phrase terminee est mise en file et lue dans l'ordre, sans
// chevauchement. L'audio de la phrase suivante est prepare a l'avance
// pour un enchainement quasi sans coupure (effet "vivant").
// ----------------------------------------------------------------------
let ttsQueue = [];          // phrases en attente de lecture { text, audioPromise }
let ttsBusy = false;        // une phrase est-elle en cours de lecture ?
let spokenIndex = 0;        // nb de caracteres deja envoyes a la voix
let streamingTTS = false;   // sommes-nous en train de lire un flux ?

function stopSpeaking() {
  streamingTTS = false;
  ttsBusy = false;
  spokenIndex = 0;
  // On libere les URLs audio deja preparees.
  ttsQueue.forEach((it) => { if (it.audioPromise) it.audioPromise.then((u) => u && URL.revokeObjectURL(u)).catch(() => {}); });
  ttsQueue = [];
  if ("speechSynthesis" in window) speechSynthesis.cancel();
  if (currentAudio) { try { currentAudio.pause(); } catch {} currentAudio = null; }
}

// Prepare l'audio naturel (serveur) d'une phrase ; null si echec (-> repli).
async function fetchTTS(text) {
  if (preferBrowserTTS()) return null;
  try {
    const r = await apiFetch("/api/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, gender: voiceSettings.gender, rate: voiceSettings.rate, pitch: voiceSettings.pitch }),
    });
    if (!r.ok) throw new Error("tts");
    return URL.createObjectURL(await r.blob());
  } catch {
    return null;
  }
}

// Lit une seule phrase avec la voix du navigateur (repli hors-ligne).
function speakBrowserOnce(text, done) {
  if (!("speechSynthesis" in window)) { done(); return; }
  const u = _utterance(text, pickVoice() || fiableLocalVoice());
  u.onstart = () => setState("speaking");
  u.onend = () => done();
  u.onerror = () => done();
  speechSynthesis.cancel();
  speechSynthesis.speak(u);
  setTimeout(() => { try { speechSynthesis.resume(); } catch {} }, 80);
  if (isMobileDevice()) {
    setTimeout(() => { try { speechSynthesis.resume(); } catch {} }, 300);
  }
}

function enqueueTTS(text) {
  if (!text) return;
  // On lance la preparation de l'audio TOUT DE SUITE (en parallele).
  ttsQueue.push({ text, audioPromise: fetchTTS(text) });
  if (!ttsBusy) playNextTTS();
}

async function playNextTTS() {
  if (!ttsQueue.length) {
    ttsBusy = false;
    if (!streamingTTS) setState("idle"); // flux fini + file vide -> repos
    return;
  }
  ttsBusy = true;
  const item = ttsQueue.shift();
  const url = await item.audioPromise;
  if (!url) { speakBrowserOnce(item.text, playNextTTS); return; }
  const audio = new Audio(url);
  currentAudio = audio;
  audio.onplay = () => setState("speaking");
  audio.onended = () => { URL.revokeObjectURL(url); currentAudio = null; playNextTTS(); };
  audio.onerror = () => { URL.revokeObjectURL(url); speakBrowserOnce(item.text, playNextTTS); };
  try {
    await audio.play();
  } catch {
    URL.revokeObjectURL(url);
    currentAudio = null;
    speakBrowserOnce(item.text, playNextTTS);
  }
}

// Demarre une nouvelle lecture en flux (a appeler avant de streamer).
function resetStreamingTTS() {
  stopSpeaking();
  if (voiceSettings.enabled) streamingTTS = true;
}

// Alimente la voix au fil de l'eau : parle des que possible (phrases ou segments courts).
function feedStreamingTTS(full) {
  if (!streamingTTS || !voiceSettings.enabled) return;
  const pending = full.slice(spokenIndex);
  // Frontieres rapides : fin de phrase, virgule, ou segment >= 40 caracteres.
  const bornes = [...pending.matchAll(/[.!?…]+\s|\n+|,\s+/g)];
  let cut = -1;
  if (bornes.length) {
    const last = bornes[bornes.length - 1];
    cut = last.index + last[0].length;
  } else if (pending.length >= 40 && /\s/.test(pending)) {
    const m = pending.match(/^.{25,40}\s/);
    if (m) cut = m[0].length;
  }
  if (cut <= 0) return;
  const chunk = pending.slice(0, cut).trim();
  if (chunk) enqueueTTS(chunk);
  spokenIndex += cut;
}

// Termine la lecture en flux : on prononce le reste (derniere phrase).
function endStreamingTTS(full) {
  if (!voiceSettings.enabled) { if (!ttsBusy) setState("idle"); return; }
  const reste = full.slice(spokenIndex).trim();
  if (reste) enqueueTTS(reste);
  streamingTTS = false;
  if (!ttsBusy && !ttsQueue.length) setState("idle");
}

// Voix de JARVIS : 1) voix naturelle du serveur (Henri/Denise),
//                  2) repli sur la voix du navigateur si hors-ligne.
async function speak(text) {
  if (!voiceSettings.enabled) { setState("idle"); return; }
  stopSpeaking();

  try {
    const r = await apiFetch("/api/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        gender: voiceSettings.gender,
        rate: voiceSettings.rate,
        pitch: voiceSettings.pitch,
      }),
    });
    if (!r.ok) throw new Error("voix serveur indisponible");
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    currentAudio = audio;
    audio.onplay = () => setState("speaking");
    audio.onended = () => { setState("idle"); URL.revokeObjectURL(url); currentAudio = null; };
    audio.onerror = () => { URL.revokeObjectURL(url); speakBrowser(text); };
    try {
      await audio.play();
    } catch {
      URL.revokeObjectURL(url);
      currentAudio = null;
      speakBrowser(text);
    }
  } catch {
    // Hors-ligne ou erreur : on utilise la voix locale du navigateur.
    speakBrowser(text);
  }
}

// Repli : synthese vocale locale du navigateur (fonctionne hors-ligne).
function speakBrowser(text) {
  if (!("speechSynthesis" in window)) { setState("idle"); return; }
  speechSynthesis.cancel();
  const chosen = pickVoice();
  let started = false;
  let usedFallback = false;
  const u = _utterance(text, chosen);
  u.onstart = () => { started = true; setState("speaking"); };
  u.onend = () => setState("idle");
  u.onerror = () => tryFallback();

  function tryFallback() {
    if (usedFallback || started) { if (!started) setState("idle"); return; }
    usedFallback = true;
    const local = fiableLocalVoice();
    if (!local || (chosen && local.voiceURI === chosen.voiceURI)) { setState("idle"); return; }
    speechSynthesis.cancel();
    const u2 = _utterance(text, local);
    u2.onstart = () => { started = true; setState("speaking"); };
    u2.onend = () => setState("idle");
    u2.onerror = () => setState("idle");
    speechSynthesis.speak(u2);
  }

  speechSynthesis.speak(u);
  setTimeout(() => { try { speechSynthesis.resume(); } catch {} }, 100);
  setTimeout(() => { if (!started) tryFallback(); }, 1400);
}

// ----------------------------------------------------------------------
// Envoi d'un message et reception en streaming
//   opts.display = false  ->  on n'affiche PAS le message (cas des notes vocales)
// ----------------------------------------------------------------------
// Detecte une demande de creation d'image et renvoie la description, sinon null.
function detectImageRequest(text) {
  const t = text.trim();
  const re = /^(?:peux-tu\s+|pourrais-tu\s+|tu\s+peux\s+)?(?:me\s+)?(?:dessine[rz]?|g[ée]n[èe]re[rz]?|cr[ée]e[rz]?|fai[ts]|montre[rz]?)\b.*?\b(?:une?\s+)?(?:image|photo|dessin|illustration|logo|portrait|paysage|sc[èe]ne|visuel)\b\s*(?:de|d'|du|des|avec|montrant|repr[ée]sentant|:)?\s*(.*)$/i;
  const m = t.match(re);
  if (m) {
    const sujet = (m[1] || "").trim();
    return sujet.length >= 2 ? sujet : t; // si rien apres, on prend tout le texte
  }
  return null;
}

async function sendMessage(text, opts = {}) {
  unlockAudio();
  text = (text || "").trim();
  if (!text && imageJointe) text = "Analyse cette image et décris ce que tu vois.";
  if (!text && pieceJointe) text = "Analyse ce fichier et résume-le clairement.";
  if (!text) return;

  // Demande de CREATION d'image (pas d'image jointe).
  if (!imageJointe) {
    const imgPrompt = !pieceJointe ? detectImageRequest(text) : null;
    if (imgPrompt) {
      addMessage("user", text);
      inputEl.value = "";
      inputEl.style.height = "auto";
      genererImageDansChat(imgPrompt);
      return;
    }
    const docReq = detectDocumentRequest(text);
    if (docReq && !imageJointe) {
      const jointeDoc = pieceJointe;
      if (jointeDoc) clearAttachment();
      addMessage("user", (jointeDoc ? `📎 ${jointeDoc.nom}\n` : "") + text);
      inputEl.value = "";
      inputEl.style.height = "auto";
      genererDocumentDansChat(docReq.instruction, docReq.type, jointeDoc);
      return;
    }
  }

  const display = opts.display !== false;
  const jointe = pieceJointe;
  const jointeImg = imageJointe;
  const labelJointe = jointe ? `📎 ${jointe.nom}\n` : jointeImg ? `🖼️ ${jointeImg.nom}\n` : "";
  if (jointe || jointeImg) clearAttachment();

  if (display) {
    const userEl = addMessage("user", labelJointe + text);
    if (jointeImg?.preview) {
      const thumb = document.createElement("img");
      thumb.src = jointeImg.preview;
      thumb.alt = jointeImg.nom;
      thumb.className = "msg-thumb";
      userEl.insertBefore(thumb, userEl.firstChild);
    }
    inputEl.value = "";
    inputEl.style.height = "auto";
  }
  history.push({ role: "user", content: text });
  if (history.length > 24) history.splice(0, history.length - 24);

  setState("thinking");
  const botEl = addMessage("bot", jointeImg ? "👁️ J'analyse ton image…" : "…", "thinking");
  let full = "";
  resetStreamingTTS();

  try {
    const corps = { messages: history, model: currentModel, mode: "auto" };
    if (jointe) corps.piece_jointe = { nom: jointe.nom, texte: jointe.texte };
    if (jointeImg) {
      corps.image_jointe = {
        nom: jointeImg.nom,
        base64: jointeImg.base64,
        mime: jointeImg.mime,
      };
    }
    const resp = await apiFetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corps),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || `Erreur serveur (${resp.status})`);
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop();

      for (const part of parts) {
        const line = part.replace(/^data:\s*/, "").trim();
        if (!line) continue;
        const evt = JSON.parse(line);
        if (evt.mode) {
          setModeBadge(evt.mode, evt.modele);
        } else if (evt.sources) {
          showSources(botEl, evt.sources);
        } else if (evt.info) {
          if (botEl.classList.contains("thinking")) botEl.textContent = "ℹ️ " + evt.info + "…";
        } else if (evt.token) {
          if (botEl.classList.contains("thinking")) {
            botEl.classList.remove("thinking");
          }
          full += evt.token;
          botEl.textContent = full;
          chatEl.scrollTop = chatEl.scrollHeight;
          feedStreamingTTS(full); // parle les phrases completes deja ecrites
        } else if (evt.erreur) {
          botEl.classList.remove("thinking");
          botEl.textContent = "⚠️ Erreur : " + evt.erreur;
        } else if (evt.document) {
          afficherDocumentChat(botEl, evt.document, text);
          full = evt.document.apercu || "";
        }
      }
    }

    if (full) {
      history.push({ role: "assistant", content: full });
      endStreamingTTS(full); // prononce la derniere phrase restante
    } else {
      setState("idle");
    }
  } catch (e) {
    botEl.classList.remove("thinking");
    botEl.textContent = "⚠️ Impossible de joindre le serveur : " + e.message;
    setState("idle");
  }
}

// ----------------------------------------------------------------------
// Enregistrement vocal -> transcription (Whisper, offline)
// Les notes vocales NE sont PAS affichees : JARVIS ecoute et repond.
// ----------------------------------------------------------------------
let mediaRecorder = null;
let audioChunks = [];
let audioCtx = null;
let silenceTimer = null;
let vadRaf = null;
let isStopping = false;

function chooseMime() {
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/mp4",
  ];
  for (const c of candidates) {
    if (window.MediaRecorder && MediaRecorder.isTypeSupported(c)) return c;
  }
  return "";
}

function startSilenceDetection(stream) {
  audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  const source = audioCtx.createMediaStreamSource(stream);
  const analyser = audioCtx.createAnalyser();
  analyser.fftSize = 512;
  source.connect(analyser);
  const data = new Uint8Array(analyser.frequencyBinCount);

  let hasSpoken = false;
  const SILENCE_LIMIT_MS = 1500;
  const VOICE_LEVEL = 0.015;

  function check() {
    analyser.getByteTimeDomainData(data);
    let sum = 0;
    for (let i = 0; i < data.length; i++) {
      const v = (data[i] - 128) / 128;
      sum += v * v;
    }
    const level = Math.sqrt(sum / data.length);

    if (level > VOICE_LEVEL) {
      hasSpoken = true;
      if (silenceTimer) { clearTimeout(silenceTimer); silenceTimer = null; }
    } else if (hasSpoken && !silenceTimer) {
      silenceTimer = setTimeout(() => stopRecording(), SILENCE_LIMIT_MS);
    }
    vadRaf = requestAnimationFrame(check);
  }
  check();
}

function cleanupAudio(stream) {
  if (vadRaf) cancelAnimationFrame(vadRaf);
  if (silenceTimer) clearTimeout(silenceTimer);
  vadRaf = null; silenceTimer = null;
  if (audioCtx) { audioCtx.close().catch(() => {}); audioCtx = null; }
  if (stream) stream.getTracks().forEach((t) => t.stop());
}

function stopRecording() {
  if (mediaRecorder && mediaRecorder.state === "recording" && !isStopping) {
    isStopping = true;
    mediaRecorder.stop();
  }
}

async function toggleRecording() {
  unlockAudio();
  if (mediaRecorder && mediaRecorder.state === "recording") {
    stopRecording();
    return;
  }

  // On coupe la voix de JARVIS s'il etait en train de parler.
  stopSpeaking();

  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        channelCount: 1,
      },
    });
  } catch (e) {
    addMessage("bot", "⚠️ Micro inaccessible : " + e.message + " — autorise le micro dans le navigateur.");
    setState("idle");
    return;
  }

  try {
    const mime = chooseMime();
    mediaRecorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
    audioChunks = [];
    isStopping = false;

    mediaRecorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) audioChunks.push(e.data);
    };

    mediaRecorder.onstop = async () => {
      micBtn.classList.remove("recording");
      cleanupAudio(stream);

      if (audioChunks.length === 0) { setState("idle"); return; }
      const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType || "audio/webm" });
      const fd = new FormData();
      fd.append("audio", blob, "note.webm");

      setState("thinking");
      try {
        const r = await apiFetch("/api/transcribe", { method: "POST", body: fd });
        if (!r.ok) {
          const err = await r.json().catch(() => ({}));
          throw new Error(err.detail || `Erreur ${r.status}`);
        }
        const data = await r.json();
        if (data.texte && data.texte.trim()) {
          sendMessage(data.texte, { display: false });
        } else {
          setState("idle");
          addMessage("bot", "🤔 Je n'ai rien entendu de clair. Réessaie un peu plus près du micro.");
        }
      } catch (e) {
        if (speechRecognitionDisponible()) {
          try {
            setState("listening");
            const texte = await transcrireNavigateur();
            arreterTranscrireNavigateur();
            micBtn.classList.remove("recording");
            if (texte) sendMessage(texte, { display: false });
            else {
              setState("idle");
              addMessage("bot", "🤔 Je n'ai rien entendu de clair. Réessaie.");
            }
            return;
          } catch (e2) {
            arreterTranscrireNavigateur();
          }
        }
        setState("idle");
        addMessage("bot", "⚠️ Transcription impossible : " + e.message);
      }
    };

    mediaRecorder.start(250);
    micBtn.classList.add("recording");
    setState("listening");
    startSilenceDetection(stream);
  } catch (e) {
    cleanupAudio(stream);
    setState("idle");
    addMessage("bot", "⚠️ Enregistrement impossible : " + e.message);
  }
}

// ----------------------------------------------------------------------
// Evenements
// ----------------------------------------------------------------------
sendBtn.addEventListener("click", () => sendMessage(inputEl.value));
micBtn.addEventListener("click", toggleRecording);

inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage(inputEl.value);
  }
});

inputEl.addEventListener("input", () => {
  inputEl.style.height = "auto";
  inputEl.style.height = Math.min(inputEl.scrollHeight, 140) + "px";
});

// ----------------------------------------------------------------------
// Gestion du panneau de personnalisation de la voix
// ----------------------------------------------------------------------
function openVoiceModal() {
  populateVoiceList();
  rateRange.value = voiceSettings.rate;
  pitchRange.value = voiceSettings.pitch;
  rateVal.textContent = Number(voiceSettings.rate).toFixed(2);
  pitchVal.textContent = Number(voiceSettings.pitch).toFixed(2);
  ttsEnabled.checked = voiceSettings.enabled;
  applyAvatar();
  voiceModal.classList.add("show");
}
function closeVoiceModal() {
  voiceModal.classList.remove("show");
}

// Met a jour les reglages depuis le panneau (sans encore enregistrer).
voiceList.addEventListener("change", () => { voiceSettings.voiceURI = voiceList.value; });
rateRange.addEventListener("input", () => {
  voiceSettings.rate = parseFloat(rateRange.value);
  rateVal.textContent = voiceSettings.rate.toFixed(2);
});
pitchRange.addEventListener("input", () => {
  voiceSettings.pitch = parseFloat(pitchRange.value);
  pitchVal.textContent = voiceSettings.pitch.toFixed(2);
});
ttsEnabled.addEventListener("change", () => {
  voiceSettings.enabled = ttsEnabled.checked;
  if (ttsToggle) ttsToggle.checked = ttsEnabled.checked;
});

testVoiceBtn.addEventListener("click", () => {
  voiceSettings.voiceURI = voiceList.value;
  speak("Bonjour, je suis JARVIS. Voici ma voix, dis-moi si elle te convient.");
});

saveVoiceBtn.addEventListener("click", () => {
  voiceSettings.voiceURI = voiceList.value;
  voiceSettings.enabled = ttsEnabled.checked;
  saveVoiceSettings();
  localStorage.setItem("jarvis_voice_done", "1");
  if (ttsToggle) ttsToggle.checked = voiceSettings.enabled;
  closeVoiceModal();
});

avatarOpts.forEach((btn) => {
  btn.addEventListener("click", () => {
    voiceSettings.gender = btn.dataset.gender;
    applyAvatar();
  });
});

voiceSettingsBtn.addEventListener("click", openVoiceModal);

// Bouton mute rapide (🔊) synchronise avec les reglages.
if (ttsToggle) {
  ttsToggle.checked = voiceSettings.enabled;
  ttsToggle.addEventListener("change", () => {
    voiceSettings.enabled = ttsToggle.checked;
    saveVoiceSettings();
  });
}

// Chargement des voix (asynchrone selon les navigateurs).
function onVoicesReady() {
  populateVoiceList();
  // Au tout premier lancement, on propose la configuration de la voix.
  if (!localStorage.getItem("jarvis_voice_done")) openVoiceModal();
}
if ("speechSynthesis" in window) {
  if (getVoices().length) onVoicesReady();
  speechSynthesis.onvoiceschanged = onVoicesReady;
}

// ----------------------------------------------------------------------
// Panneau "Progression du projet" (schema d'architecture + frise)
// ----------------------------------------------------------------------
const PROJECT_STEPS = [
  { t: "Moteur IA (Ollama)", d: "Installation du moteur qui fait tourner l'IA en local." },
  { t: "Modèles locaux (3B + 7B)", d: "Téléchargement de qwen2.5 pour le mode hors-ligne." },
  { t: "Cerveau / serveur (FastAPI)", d: "Le serveur Python qui relie tout ensemble." },
  { t: "Assistant texte", d: "Discussion en français, en streaming, cohérente." },
  { t: "Reconnaissance vocale (Whisper)", d: "Tes notes vocales transcrites hors-ligne." },
  { t: "Voix de JARVIS + personnalisation", d: "Réponses à voix haute, voix réglable." },
  { t: "Interface + visage holographique", d: "Réacteur Arc et visage Homme/Femme." },
  { t: "Mode hybride (Cloud rapide + Local)", d: "Rapide en ligne, bascule locale hors-ligne." },
  { t: "Cascade cloud multi-modèles", d: "70B → 120B → 32B : plus d'autonomie gratuite." },
  { t: "Mémoire persistante", d: "Se souvient de ton prénom, ton profil, tes faits." },
  { t: "Documents (RAG)", d: "Répond à partir de tes propres fichiers." },
  { t: "Outils d'agent", d: "Recherche web, calculs fiables." },
  { t: "Bibliothèque de prompts", d: "Idées prêtes à l'emploi en un clic." },
];

const SCHEMA = [
  [{ b: "Toi", s: "voix ou texte", cls: "accent" }],
  [{ b: "Interface JARVIS", s: "réacteur + visage", cls: "accent" }],
  [{ b: "Serveur (FastAPI)", s: "le cerveau", cls: "" }],
  [
    { b: "IA Cloud", s: "70B→120B · rapide", cls: "accent" },
    { b: "IA Locale", s: "qwen2.5 · hors-ligne", cls: "gold" },
    { b: "Voix (Whisper)", s: "écoute + parole", cls: "" },
  ],
  [
    { b: "Mémoire", s: "te connaît", cls: "gold" },
    { b: "Documents", s: "RAG · tes fichiers", cls: "accent" },
    { b: "Outils", s: "web + calculs", cls: "" },
  ],
];

const SVGNS = "http://www.w3.org/2000/svg";

// Dessine une jauge circulaire (pourcentage).
function renderGauge(id, percent, color) {
  const svg = document.getElementById(id);
  if (!svg) return;
  svg.innerHTML = "";
  const r = 48, c = 60, circ = 2 * Math.PI * r;

  const track = document.createElementNS(SVGNS, "circle");
  track.setAttribute("class", "gauge-track");
  track.setAttribute("cx", c); track.setAttribute("cy", c); track.setAttribute("r", r);
  svg.appendChild(track);

  const arc = document.createElementNS(SVGNS, "circle");
  arc.setAttribute("class", "gauge-arc");
  arc.setAttribute("cx", c); arc.setAttribute("cy", c); arc.setAttribute("r", r);
  arc.setAttribute("stroke", color);
  arc.setAttribute("transform", `rotate(-90 ${c} ${c})`);
  arc.style.strokeDasharray = circ;
  arc.style.strokeDashoffset = circ; // vide au depart
  svg.appendChild(arc);

  const txt = document.createElementNS(SVGNS, "text");
  txt.setAttribute("class", "gauge-text");
  txt.setAttribute("x", c); txt.setAttribute("y", c);
  txt.textContent = Math.round(percent) + "%";
  svg.appendChild(txt);

  // Animation a l'ouverture.
  requestAnimationFrame(() => {
    arc.style.strokeDashoffset = circ * (1 - percent / 100);
  });
}

// Graphique en barres horizontales.
function renderBars(containerId, data) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = "";
  const max = Math.max(...data.map((d) => d.value));
  data.forEach((d) => {
    const row = document.createElement("div");
    row.className = "bar-row";
    row.innerHTML = `
      <span class="bar-name">${d.name}</span>
      <span class="bar-track"><span class="bar-fill" style="background:${d.color}"></span></span>
      <span class="bar-val">${d.label}</span>`;
    el.appendChild(row);
    const fill = row.querySelector(".bar-fill");
    requestAnimationFrame(() => { fill.style.width = (d.value / max) * 100 + "%"; });
  });
}

const CAPS = [
  { n: "Discussion par écrit", on: true },
  { n: "Écoute vocale (notes)", on: true },
  { n: "Voix naturelle (parole)", on: true },
  { n: "Visage Homme / Femme", on: true },
  { n: "Mode rapide en ligne", on: true },
  { n: "Mode local hors-ligne", on: true },
  { n: "Mémoire longue durée", on: true },
  { n: "Documents (RAG)", on: true },
  { n: "Recherche web", on: true },
  { n: "Calcul fiable", on: true },
  { n: "Bibliothèque 100+ prompts", on: true },
  { n: "Génération d'images", on: true },
  { n: "Analyse d'images (vision)", on: true },
  { n: "Documents (Word, PDF…)", on: true },
  { n: "Mot d'activation vocal", on: false },
];

function renderCaps() {
  const el = document.getElementById("bars-caps");
  if (!el) return;
  el.innerHTML = "";
  CAPS.forEach((c) => {
    const d = document.createElement("div");
    d.className = "cap " + (c.on ? "on" : "off");
    d.innerHTML = `<span class="pip"></span><span>${c.n}${c.on ? "" : " (à venir)"}</span>`;
    el.appendChild(d);
  });
}

function renderCharts() {
  renderGauge("gauge", 100, "#28d6ff");
  renderGauge("gauge-tests", 100, "#28e6a8"); // 14/14
  renderBars("bars-speed", [
    { name: "En ligne (rapide)", value: 2, label: "~2 s", color: "linear-gradient(90deg,#28d6ff,#0a72ff)" },
    { name: "Local 3B", value: 6, label: "~6 s", color: "linear-gradient(90deg,#ffb648,#d6730a)" },
    { name: "Local 7B", value: 15, label: "~15 s", color: "linear-gradient(90deg,#ff8f6b,#d63a3a)" },
  ]);
  renderCaps();
}

function renderProgress() {
  const schema = document.getElementById("schema");
  const timeline = document.getElementById("timeline");
  renderCharts(); // graphiques (re-animes a chaque ouverture)
  if (!schema || schema.childElementCount) return; // schema/frise rendus une fois

  SCHEMA.forEach((row, i) => {
    const r = document.createElement("div");
    r.className = "schema-row";
    row.forEach((box) => {
      const el = document.createElement("div");
      el.className = "schema-box " + (box.cls || "");
      el.innerHTML = `<b>${box.b}</b><span>${box.s}</span>`;
      r.appendChild(el);
    });
    schema.appendChild(r);
    if (i < SCHEMA.length - 1) {
      const arr = document.createElement("div");
      arr.className = "schema-arrow";
      arr.textContent = "▼";
      schema.appendChild(arr);
    }
  });

  PROJECT_STEPS.forEach((step, i) => {
    const el = document.createElement("div");
    el.className = "tl-step";
    el.innerHTML = `
      <div class="tl-num">${i + 1}</div>
      <div class="tl-body">
        <b>${step.t}</b>
        <p>${step.d}</p>
        <div class="tl-badges">
          <span class="tl-badge done">✅ Terminé</span>
          <span class="tl-badge tested">🧪 Testé</span>
          <span class="tl-badge verified">✔️ Vérifié</span>
        </div>
      </div>`;
    timeline.appendChild(el);
  });
}

const progressModal = document.getElementById("progress-modal");
document.getElementById("progress-btn").addEventListener("click", async () => {
  renderProgress();
  progressModal.classList.add("show");
  setTimeout(() => { document.getElementById("progress-fill").style.width = "100%"; }, 80);
  const diagEl = document.getElementById("diagnostic-status");
  if (diagEl) {
    diagEl.textContent = "Diagnostic en cours…";
    try {
      const r = await apiFetch("/api/diagnostic");
      const d = await r.json();
      diagEl.textContent = `Diagnostic : ${d.score_global}/100 (${d.niveau}) — ${d.bibliotheque_prompts.total} prompts · Cloud ${d.modele_cloud} · Local ${d.modele_local}`;
    } catch {
      diagEl.textContent = "";
    }
  }
});
document.getElementById("progress-close").addEventListener("click", () => {
  progressModal.classList.remove("show");
});
progressModal.addEventListener("click", (e) => {
  if (e.target === progressModal) progressModal.classList.remove("show");
});

// ----------------------------------------------------------------------
// Affichage des sources utilisees par JARVIS (memoire, web, documents...)
// ----------------------------------------------------------------------
const SOURCE_LABELS = {
  "fichier": "📎 Fichier joint",
  "mémoire": "🧠 Mémoire",
  "documents": "📚 Tes documents",
  "web": "🌐 Recherche web",
  "calcul": "🧮 Calcul fiable",
  "image": "👁️ Analyse d'image",
};
function showSources(botEl, sources) {
  if (!sources || !sources.length) return;
  const bar = document.createElement("div");
  bar.className = "sources";
  sources.forEach((s) => {
    const b = document.createElement("span");
    b.className = "src-badge";
    b.textContent = SOURCE_LABELS[s] || s;
    bar.appendChild(b);
  });
  botEl.parentNode.insertBefore(bar, botEl);
  chatEl.scrollTop = chatEl.scrollHeight;
}

// ----------------------------------------------------------------------
// Panneau Mémoire
// ----------------------------------------------------------------------
const memoryModal = document.getElementById("memory-modal");
const memPrenom = document.getElementById("mem-prenom");
const memApropos = document.getElementById("mem-apropos");
const memFaits = document.getElementById("mem-faits");
const memFaitNew = document.getElementById("mem-fait-new");
let memData = { profil: { prenom: "", a_propos: "" }, faits: [] };

function renderFaits() {
  memFaits.innerHTML = "";
  (memData.faits || []).forEach((f, i) => {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.innerHTML = `<span>${f}</span>`;
    const x = document.createElement("button");
    x.textContent = "✕";
    x.title = "Oublier ce fait";
    x.addEventListener("click", () => { memData.faits.splice(i, 1); renderFaits(); });
    chip.appendChild(x);
    memFaits.appendChild(chip);
  });
}

async function openMemoryModal() {
  try {
    const r = await apiFetch("/api/memoire");
    memData = await r.json();
  } catch {}
  memPrenom.value = memData.profil?.prenom || "";
  memApropos.value = memData.profil?.a_propos || "";
  renderFaits();
  memoryModal.classList.add("show");
}

document.getElementById("memory-btn").addEventListener("click", openMemoryModal);
document.getElementById("memory-close").addEventListener("click", () => memoryModal.classList.remove("show"));
memoryModal.addEventListener("click", (e) => { if (e.target === memoryModal) memoryModal.classList.remove("show"); });

document.getElementById("mem-fait-add").addEventListener("click", () => {
  const v = memFaitNew.value.trim();
  if (v) { memData.faits = memData.faits || []; memData.faits.push(v); memFaitNew.value = ""; renderFaits(); }
});
memFaitNew.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); document.getElementById("mem-fait-add").click(); } });

document.getElementById("mem-save").addEventListener("click", async () => {
  await apiFetch("/api/memoire/profil", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prenom: memPrenom.value, a_propos: memApropos.value }),
  });
  // On resynchronise les faits : on efface puis on reajoute (simple et fiable).
  await apiFetch("/api/memoire", { method: "DELETE" });
  await apiFetch("/api/memoire/profil", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prenom: memPrenom.value, a_propos: memApropos.value }),
  });
  for (const f of (memData.faits || [])) {
    await apiFetch("/api/memoire/fait", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fait: f }),
    });
  }
  memoryModal.classList.remove("show");
  addMessage("bot", "🧠 C'est noté, je m'en souviendrai.");
});

document.getElementById("mem-forget").addEventListener("click", async () => {
  await apiFetch("/api/memoire", { method: "DELETE" });
  memData = { profil: { prenom: "", a_propos: "" }, faits: [] };
  memPrenom.value = ""; memApropos.value = ""; renderFaits();
});

// ----------------------------------------------------------------------
// Panneau Documents (RAG)
// ----------------------------------------------------------------------
const docsModal = document.getElementById("docs-modal");
const docsInput = document.getElementById("docs-input");
const dropzone = document.getElementById("dropzone");
const docsStatus = document.getElementById("docs-status");
const docsListEl = document.getElementById("docs-list");

async function refreshDocs() {
  try {
    const r = await apiFetch("/api/documents");
    const data = await r.json();
    docsListEl.innerHTML = "";
    if (!data.documents.length) { docsListEl.innerHTML = '<div class="docs-status">Aucun document pour l\'instant.</div>'; return; }
    data.documents.forEach((d) => {
      const item = document.createElement("div");
      item.className = "doc-item";
      item.innerHTML = `<span>📄 ${d.nom} <span class="doc-meta">· ${d.morceaux} extrait(s)</span></span>`;
      const del = document.createElement("button");
      del.textContent = "🗑️"; del.title = "Supprimer";
      del.addEventListener("click", async () => {
        await apiFetch("/api/documents/" + encodeURIComponent(d.nom), { method: "DELETE" });
        refreshDocs();
      });
      item.appendChild(del);
      docsListEl.appendChild(item);
    });
  } catch {}
}

async function uploadDoc(file) {
  docsStatus.textContent = "⏳ Lecture de « " + file.name + " »…";
  const fd = new FormData();
  fd.append("fichier", file);
  try {
    // /api/joindre indexe ET renvoie le texte : on peut enchainer sur une instruction.
    const r = await apiFetch("/api/joindre", { method: "POST", body: fd });
    if (!r.ok) { const e = await r.json(); throw new Error(e.detail || "erreur"); }
    const data = await r.json();
    refreshDocs();
    // Message de succes + bouton pour donner tout de suite une instruction.
    docsStatus.innerHTML = "";
    const ok = document.createElement("span");
    ok.textContent = "✅ « " + data.nom + " » ajouté. ";
    docsStatus.appendChild(ok);
    const cta = document.createElement("button");
    cta.className = "btn-ghost";
    cta.textContent = "✍️ Donner une instruction dessus";
    cta.addEventListener("click", () => {
      pieceJointe = { nom: data.nom, texte: data.texte };
      renderAttachChip(data.nom, data.tronque ? "fichier long" : "prêt", false);
      docsModal.classList.remove("show");
      inputEl.placeholder = "Ton instruction : résume, traduis, explique…";
      inputEl.focus();
    });
    docsStatus.appendChild(cta);
  } catch (e) {
    docsStatus.textContent = "⚠️ " + e.message;
  }
}

document.getElementById("docs-btn").addEventListener("click", () => { docsModal.classList.add("show"); refreshDocs(); docsStatus.textContent = ""; });
document.getElementById("docs-close").addEventListener("click", () => docsModal.classList.remove("show"));
docsModal.addEventListener("click", (e) => { if (e.target === docsModal) docsModal.classList.remove("show"); });
dropzone.addEventListener("click", () => docsInput.click());
docsInput.addEventListener("change", () => { if (docsInput.files[0]) uploadDoc(docsInput.files[0]); });
["dragover", "dragenter"].forEach((ev) => dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.add("over"); }));
["dragleave", "drop"].forEach((ev) => dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.remove("over"); }));
dropzone.addEventListener("drop", (e) => { if (e.dataTransfer.files[0]) uploadDoc(e.dataTransfer.files[0]); });

// ----------------------------------------------------------------------
// Bibliothèque de 100+ prompts (tous sujets)
// ----------------------------------------------------------------------
const promptsModal = document.getElementById("prompts-modal");
const promptsListEl = document.getElementById("prompts-list");
const promptsSearch = document.getElementById("prompts-search");
const promptsFilter = document.getElementById("prompts-filter");
let promptsCache = [];

async function loadPrompts() {
  if (promptsCache.length) return promptsCache;
  try {
    const r = await apiFetch("/api/prompts");
    const data = await r.json();
    promptsCache = data.prompts || [];
    if (promptsFilter && data.categories) {
      promptsFilter.innerHTML = '<option value="">Toutes les catégories</option>';
      data.categories.forEach((c) => {
        const o = document.createElement("option");
        o.value = c; o.textContent = c;
        promptsFilter.appendChild(o);
      });
    }
  } catch {
    promptsCache = [];
  }
  return promptsCache;
}

function renderPrompts() {
  const q = (promptsSearch?.value || "").toLowerCase().trim();
  const cat = promptsFilter?.value || "";
  const list = promptsCache.filter((pr) => {
    if (cat && pr.c !== cat) return false;
    if (!q) return true;
    return (pr.t + pr.p + pr.c).toLowerCase().includes(q);
  });
  promptsListEl.innerHTML = "";
  if (!list.length) {
    promptsListEl.innerHTML = '<p class="docs-status">Aucun prompt trouvé.</p>';
    return;
  }
  list.forEach((pr) => {
    const card = document.createElement("button");
    card.className = "prompt-card";
    card.innerHTML = `<span class="prompt-cat">${pr.c}</span><b>${pr.t}</b><span>${pr.p.trim().slice(0, 50)}…</span>`;
    card.addEventListener("click", () => {
      promptsModal.classList.remove("show");
      inputEl.value = pr.p;
      inputEl.focus();
      inputEl.style.height = "auto";
      inputEl.style.height = Math.min(inputEl.scrollHeight, 140) + "px";
    });
    promptsListEl.appendChild(card);
  });
}

document.getElementById("prompts-btn").addEventListener("click", async () => {
  await loadPrompts();
  if (promptsSearch) promptsSearch.value = "";
  if (promptsFilter) promptsFilter.value = "";
  renderPrompts();
  promptsModal.classList.add("show");
});
document.getElementById("prompts-close").addEventListener("click", () => promptsModal.classList.remove("show"));
promptsModal.addEventListener("click", (e) => { if (e.target === promptsModal) promptsModal.classList.remove("show"); });
if (promptsSearch) promptsSearch.addEventListener("input", renderPrompts);
if (promptsFilter) promptsFilter.addEventListener("change", renderPrompts);

// ----------------------------------------------------------------------
// Pièce jointe : fichier texte OU image à analyser
// ----------------------------------------------------------------------
const attachBtn = document.getElementById("attach-btn");
const attachInput = document.getElementById("attach-input");
const imageAttachBtn = document.getElementById("image-attach-btn");
const imageAttachInput = document.getElementById("image-attach-input");
const attachBar = document.getElementById("attach-bar");
let pieceJointe = null;
let imageJointe = null;

function clearAttachment() {
  pieceJointe = null;
  imageJointe = null;
  attachBar.innerHTML = "";
  attachInput.value = "";
  if (imageAttachInput) imageAttachInput.value = "";
  inputEl.placeholder = "Écris ton message…";
}

function renderAttachChip(nom, meta, loading, thumbSrc) {
  attachBar.innerHTML = "";
  const chip = document.createElement("div");
  chip.className = "attach-chip" + (loading ? " loading" : "");
  if (thumbSrc) {
    const img = document.createElement("img");
    img.src = thumbSrc;
    img.alt = nom;
    img.className = "chip-thumb";
    chip.appendChild(img);
  }
  const label = document.createElement("span");
  label.textContent = (thumbSrc ? "🖼️ " : "📎 ") + nom;
  chip.appendChild(label);
  if (meta) {
    const m = document.createElement("span");
    m.className = "meta";
    m.textContent = meta;
    chip.appendChild(m);
  }
  if (!loading) {
    const x = document.createElement("button");
    x.textContent = "✕"; x.title = "Retirer";
    x.addEventListener("click", clearAttachment);
    chip.appendChild(x);
  }
  attachBar.appendChild(chip);
}

async function attachFile(file) {
  if (!file) return;
  imageJointe = null;
  renderAttachChip(file.name, "lecture…", true, null);
  const fd = new FormData();
  fd.append("fichier", file);
  try {
    const r = await apiFetch("/api/joindre", { method: "POST", body: fd });
    if (!r.ok) { const e = await r.json(); throw new Error(e.detail || "erreur"); }
    const data = await r.json();
    pieceJointe = { nom: data.nom, texte: data.texte };
    const meta = data.tronque ? "fichier long (début pris en compte)" : "prêt";
    renderAttachChip(data.nom, meta, false, null);
    inputEl.placeholder = "Donne ton instruction : résume, traduis, explique…";
    inputEl.focus();
  } catch (e) {
    clearAttachment();
    addMessage("bot", "⚠️ Impossible de lire ce fichier : " + e.message);
  }
}

async function attachImage(file) {
  if (!file) return;
  pieceJointe = null;
  renderAttachChip(file.name, "préparation…", true, null);
  const fd = new FormData();
  fd.append("fichier", file);
  try {
    const r = await apiFetch("/api/joindre-image", { method: "POST", body: fd });
    if (!r.ok) { const e = await r.json(); throw new Error(e.detail || "erreur"); }
    const data = await r.json();
    const preview = `data:${data.mime};base64,${data.base64}`;
    imageJointe = { nom: data.nom, mime: data.mime, base64: data.base64, preview };
    renderAttachChip(data.nom, `${data.largeur}×${data.hauteur} · vision`, false, preview);
    inputEl.placeholder = "Que veux-tu savoir sur cette image ?";
    inputEl.focus();
  } catch (e) {
    clearAttachment();
    addMessage("bot", "⚠️ Image illisible : " + e.message);
  }
}

attachBtn.addEventListener("click", () => attachInput.click());
attachInput.addEventListener("change", () => { if (attachInput.files[0]) attachFile(attachInput.files[0]); });
if (imageAttachBtn) imageAttachBtn.addEventListener("click", () => imageAttachInput.click());
if (imageAttachInput) {
  imageAttachInput.addEventListener("change", () => {
    if (imageAttachInput.files[0]) attachImage(imageAttachInput.files[0]);
  });
}

// ----------------------------------------------------------------------
// Atelier fichier : modifier un fichier selon une instruction et le télécharger
// ----------------------------------------------------------------------
const atelierModal = document.getElementById("atelier-modal");
const atelierDrop = document.getElementById("atelier-drop");
const atelierInput = document.getElementById("atelier-input");
const atelierDropLabel = document.getElementById("atelier-drop-label");
const atelierInstruction = document.getElementById("atelier-instruction");
const atelierStatus = document.getElementById("atelier-status");
const atelierRun = document.getElementById("atelier-run");
const atelierResult = document.getElementById("atelier-result");
const atelierOutput = document.getElementById("atelier-output");
const atelierResultName = document.getElementById("atelier-result-name");
let atelierFichier = null;
const atelierFormat = document.getElementById("atelier-format");
let atelierFichierB64 = null;
let atelierMime = "text/plain";

function resetAtelier() {
  atelierFichier = null;
  atelierFichierB64 = null;
  atelierInput.value = "";
  atelierInstruction.value = "";
  atelierDropLabel.textContent = "📎 Clique ou dépose le fichier à modifier";
  atelierStatus.textContent = "";
  atelierResult.style.display = "none";
  atelierOutput.value = "";
}

function setAtelierFichier(file) {
  atelierFichier = file;
  atelierDropLabel.textContent = "📄 " + file.name + " — prêt";
  atelierStatus.textContent = "";
}

async function lancerAtelier() {
  if (!atelierFichier) { atelierStatus.textContent = "⚠️ Choisis d'abord un fichier."; return; }
  const instruction = atelierInstruction.value.trim();
  if (!instruction) { atelierStatus.textContent = "⚠️ Dis-moi ce que je dois faire avec le fichier."; return; }

  atelierRun.disabled = true;
  atelierStatus.textContent = "🛠️ Traitement en cours…";
  atelierResult.style.display = "none";

  const fd = new FormData();
  fd.append("fichier", atelierFichier);
  fd.append("instruction", instruction);
  if (atelierFormat) fd.append("format_sortie", atelierFormat.value || "auto");
  try {
    const r = await apiFetch("/api/traiter-fichier", { method: "POST", body: fd });
    if (!r.ok) { const e = await r.json(); throw new Error(e.detail || "erreur"); }
    const data = await r.json();
    atelierNomSortie = data.nom_sortie;
    atelierResultName.textContent = "📄 " + data.nom_sortie;
    atelierOutput.value = data.contenu;
    atelierFichierB64 = data.fichier_base64 || null;
    atelierMime = data.mime || "text/plain";
    atelierResult.style.display = "block";
    const fmtInfo = data.format ? " · " + data.format.toUpperCase() : "";
    atelierStatus.textContent = "✅ Terminé via " + data.mode + fmtInfo + (data.tronque ? " · (début traité)" : "");
  } catch (e) {
    atelierStatus.textContent = "⚠️ " + e.message;
  } finally {
    atelierRun.disabled = false;
  }
}

function telechargerResultat() {
  let blob;
  if (atelierFichierB64) {
    const bin = atob(atelierFichierB64);
    const arr = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
    blob = new Blob([arr], { type: atelierMime });
  } else {
    blob = new Blob([atelierOutput.value], { type: "text/plain;charset=utf-8" });
  }
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = atelierNomSortie;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

document.getElementById("atelier-btn").addEventListener("click", () => { resetAtelier(); atelierModal.classList.add("show"); });
document.getElementById("atelier-close").addEventListener("click", () => atelierModal.classList.remove("show"));
atelierModal.addEventListener("click", (e) => { if (e.target === atelierModal) atelierModal.classList.remove("show"); });
atelierDrop.addEventListener("click", () => atelierInput.click());
atelierInput.addEventListener("change", () => { if (atelierInput.files[0]) setAtelierFichier(atelierInput.files[0]); });
["dragover", "dragenter"].forEach((ev) => atelierDrop.addEventListener(ev, (e) => { e.preventDefault(); atelierDrop.classList.add("over"); }));
["dragleave", "drop"].forEach((ev) => atelierDrop.addEventListener(ev, (e) => { e.preventDefault(); atelierDrop.classList.remove("over"); }));
atelierDrop.addEventListener("drop", (e) => { if (e.dataTransfer.files[0]) setAtelierFichier(e.dataTransfer.files[0]); });
atelierRun.addEventListener("click", lancerAtelier);
document.getElementById("atelier-download").addEventListener("click", telechargerResultat);
document.getElementById("atelier-copy").addEventListener("click", () => {
  navigator.clipboard.writeText(atelierOutput.value).then(() => { atelierStatus.textContent = "📋 Copié dans le presse-papiers."; });
});

// ----------------------------------------------------------------------
// Génération d'images (placeholdr.dev → Flux, gratuit et sans compte)
// ----------------------------------------------------------------------
function detectDocumentRequest(text) {
  const t = text.trim();
  const tl = t.toLowerCase();
  const cv = /\b(cv|curriculum\s*vitae|curriculum|resume\s*professionnel|résumé\s*professionnel)\b/i.test(t);
  const doc = /\b(pdf|document|lettre\s+de\s+motivation|rapport|contrat|word|docx)\b/i.test(t);
  const action = /\b(cr[ée]e|cr[ée]er|fais|fait|faire|g[ée]n[èe]re|g[ée]n[èe]rer|r[ée]dige|r[ée]diger|pr[ée]pare|pr[ée]parer|reproduis|refais|modifie|modifier|mets?\s+[àa]\s+jour|transforme|exporte|t[ée]l[ée]charge|veux|voudrais|besoin|donne|fabrique|[ée]cris|produis|montre|imprime|construis|mets|convertis)\b/i.test(tl)
    || /^(peux-tu|pourrais-tu|tu\s+peux)\b/i.test(tl);
  if (cv && (action || /\bpdf\b/i.test(tl) || tl.length < 140)) return { type: "cv", instruction: t };
  if (doc && action) return { type: "generic", instruction: t };
  if (/\b(en\s+)?pdf\b/i.test(tl) && action && tl.length < 160) return { type: "generic", instruction: t };
  return null;
}

function afficherDocumentChat(botEl, doc, instruction) {
  botEl.classList.remove("thinking");
  botEl.innerHTML = "";
  const p = document.createElement("p");
  p.textContent = `✅ Document prêt : ${doc.titre || "document"} (${(doc.format || "pdf").toUpperCase()})`;
  botEl.appendChild(p);
  if (doc.blob) {
    const url = URL.createObjectURL(doc.blob);
    const actions = document.createElement("div");
    actions.className = "image-result-actions";
    const dl = document.createElement("a");
    dl.href = url;
    dl.download = doc.nom || "document.pdf";
    dl.className = "btn-primary";
    dl.textContent = "⬇️ Télécharger le PDF";
    actions.appendChild(dl);
    botEl.appendChild(actions);
  } else if (doc.base64) {
    const bin = atob(doc.base64);
    const arr = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
    const mime = doc.format === "pdf" ? "application/pdf" : "application/octet-stream";
    const url = URL.createObjectURL(new Blob([arr], { type: mime }));
    const actions = document.createElement("div");
    actions.className = "image-result-actions";
    const dl = document.createElement("a");
    dl.href = url;
    dl.download = doc.nom || "document.pdf";
    dl.className = "btn-primary";
    dl.textContent = "⬇️ Télécharger le PDF";
    actions.appendChild(dl);
    botEl.appendChild(actions);
  }
  if (doc.apercu) {
    const pre = document.createElement("pre");
    pre.className = "doc-apercu";
    pre.style.cssText = "white-space:pre-wrap;font-size:12px;max-height:200px;overflow:auto;margin-top:8px;opacity:0.85";
    pre.textContent = doc.apercu;
    botEl.appendChild(pre);
  }
  if (doc.apercu) history.push({ role: "assistant", content: doc.apercu.slice(0, 500) });
  setState("idle");
}

async function genererDocumentDansChat(instruction, typeDoc = "auto", source = null) {
  const botEl = addMessage("bot", "📝 Je rédige ton document…", "thinking");
  setState("thinking");
  try {
    const body = { instruction, type_doc: typeDoc };
    if (source?.texte) body.source_texte = source.texte;
    const r = await apiFetch("/api/document", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.detail || `Erreur serveur (${r.status})`);
    }
    const data = await r.json();
    const fmt = "pdf";
    const td = data.type_doc || (/\bcv\b/i.test(instruction) ? "cv" : typeDoc);
    const r2 = await apiFetch("/api/document/fichier", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ texte: data.texte, format: fmt, titre: data.titre, type_doc: td }),
    });
    if (!r2.ok) {
      const err = await r2.json().catch(() => ({}));
      throw new Error(err.detail || "Échec export PDF");
    }
    const blob = await r2.blob();
    let nom = (data.titre || "document") + ".pdf";
    const cd = r2.headers.get("Content-Disposition") || "";
    const m = cd.match(/filename="([^"]+)"/);
    if (m) nom = m[1];
    afficherDocumentChat(botEl, {
      titre: data.titre,
      nom,
      format: fmt,
      blob,
      apercu: data.texte?.slice(0, 1000),
    }, instruction);
  } catch (e) {
    botEl.className = "msg bot";
    botEl.textContent = "⚠️ " + e.message;
  }
  setState("idle");
}

async function demanderImage(prompt, largeur, hauteur, style) {
  const r = await apiFetch("/api/image", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, largeur, hauteur, style: style || "photographic" }),
  });
  if (!r.ok) {
    let detail = "service indisponible";
    try { detail = (await r.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return URL.createObjectURL(await r.blob());
}

// Affiche une image directement dans la conversation.
async function genererImageDansChat(prompt) {
  setState("thinking");
  const botEl = addMessage("bot", "🎨 Je crée ton image… (environ 30 secondes)", "thinking");
  try {
    const url = await demanderImage(prompt, 1024, 1024, "photographic");
    botEl.classList.remove("thinking");
    botEl.classList.add("image-msg");
    botEl.textContent = "";
    const img = document.createElement("img");
    img.src = url; img.alt = prompt;
    botEl.appendChild(img);
    const actions = document.createElement("div");
    actions.className = "img-actions";
    const dl = document.createElement("a");
    dl.href = url; dl.download = "jarvis_image.jpg"; dl.textContent = "⬇️ Télécharger";
    const re = document.createElement("button");
    re.textContent = "🔄 Une autre version";
    re.addEventListener("click", () => genererImageDansChat(prompt));
    actions.appendChild(dl); actions.appendChild(re);
    botEl.appendChild(actions);
    chatEl.scrollTop = chatEl.scrollHeight;
    history.push({ role: "assistant", content: "[image générée : " + prompt + "]" });
  } catch (e) {
    botEl.classList.remove("thinking");
    botEl.textContent = "⚠️ Impossible de générer l'image : " + e.message;
  } finally {
    setState("idle");
  }
}

// Studio d'images (panneau dédié).
const imageModal = document.getElementById("image-modal");
const imagePrompt = document.getElementById("image-prompt");
const imageStyle = document.getElementById("image-style");
const imageFormat = document.getElementById("image-format");
const imageStatus = document.getElementById("image-status");
const imageRun = document.getElementById("image-run");
const imageResult = document.getElementById("image-result");
const imageOutput = document.getElementById("image-output");
let imageUrlActuelle = null;

async function lancerStudioImage() {
  const prompt = imagePrompt.value.trim();
  if (!prompt) { imageStatus.textContent = "⚠️ Décris d'abord ton image."; return; }
  const [w, h] = imageFormat.value.split("x").map(Number);
  const style = imageStyle ? imageStyle.value : "photographic";
  imageRun.disabled = true;
  imageStatus.textContent = "🎨 Création en cours… (environ 30 secondes)";
  imageResult.style.display = "none";
  try {
    if (imageUrlActuelle) URL.revokeObjectURL(imageUrlActuelle);
    imageUrlActuelle = await demanderImage(prompt, w, h, style);
    imageOutput.src = imageUrlActuelle;
    imageResult.style.display = "block";
    imageStatus.textContent = "✅ Image prête.";
  } catch (e) {
    imageStatus.textContent = "⚠️ " + e.message;
  } finally {
    imageRun.disabled = false;
  }
}

document.getElementById("image-btn").addEventListener("click", () => {
  imageStatus.textContent = ""; imageResult.style.display = "none";
  imageModal.classList.add("show");
});
document.getElementById("image-close").addEventListener("click", () => imageModal.classList.remove("show"));
imageModal.addEventListener("click", (e) => { if (e.target === imageModal) imageModal.classList.remove("show"); });
imageRun.addEventListener("click", lancerStudioImage);
document.getElementById("image-regen").addEventListener("click", lancerStudioImage);
document.getElementById("image-download").addEventListener("click", () => {
  if (!imageUrlActuelle) return;
  const a = document.createElement("a");
  a.href = imageUrlActuelle; a.download = "jarvis_image.jpg";
  document.body.appendChild(a); a.click(); a.remove();
});

// ----------------------------------------------------------------------
// Studio de documents (rédaction + export txt/md/docx/pdf)
// ----------------------------------------------------------------------
const docModal = document.getElementById("doc-modal");
const docPrompt = document.getElementById("doc-prompt");
const docTitre = document.getElementById("doc-titre");
const docFormat = document.getElementById("doc-format");
const docStatus = document.getElementById("doc-status");
const docRun = document.getElementById("doc-run");
const docResult = document.getElementById("doc-result");
const docPreview = document.getElementById("doc-preview");
const docModifier = document.getElementById("doc-modifier");
let docTexte = "";
let docTypeDoc = "generic";

document.querySelectorAll(".doc-quick").forEach((btn) => {
  btn.addEventListener("click", () => {
    docPrompt.value = btn.dataset.prompt || "";
    docFormat.value = btn.dataset.prompt?.includes("CV") || btn.dataset.prompt?.includes("cv") ? "pdf" : docFormat.value;
  });
});

async function redigerDocument(isModification = false) {
  const instruction = isModification
    ? (docModifier?.value.trim() || docPrompt.value.trim())
    : docPrompt.value.trim();
  if (!instruction) { docStatus.textContent = "⚠️ Décris d'abord le document à rédiger."; return; }
  docRun.disabled = true;
  docStatus.textContent = isModification ? "✏️ Modification en cours…" : "✍️ Rédaction en cours…";
  docResult.style.display = "none";
  try {
    const body = {
      instruction,
      titre: docTitre.value.trim(),
      type_doc: "auto",
    };
    if (isModification || docTexte) body.source_texte = docPreview.value.trim() || docTexte;
    const r = await apiFetch("/api/document", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      let detail = "service indisponible";
      try { detail = (await r.json()).detail || detail; } catch {}
      throw new Error(detail);
    }
    const data = await r.json();
    docTexte = data.texte || "";
    docTypeDoc = data.type_doc || "generic";
    if (!docTitre.value.trim() && data.titre) docTitre.value = data.titre;
    docPreview.value = docTexte;
    if (docModifier) docModifier.value = "";
    docResult.style.display = "block";
    docStatus.textContent = "✅ Document prêt. Modifie l'aperçu ou télécharge en PDF/Word.";
  } catch (e) {
    docStatus.textContent = "⚠️ " + e.message;
  } finally {
    docRun.disabled = false;
  }
}

async function telechargerDocument() {
  if (!docTexte) return;
  const fmt = docFormat.value;
  docStatus.textContent = "📦 Préparation du fichier…";
  try {
    const r = await apiFetch("/api/document/fichier", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        texte: docPreview.value.trim() || docTexte,
        format: fmt,
        titre: docTitre.value.trim(),
        type_doc: docTypeDoc,
      }),
    });
    if (!r.ok) {
      let detail = "échec de la conversion";
      try { detail = (await r.json()).detail || detail; } catch {}
      throw new Error(detail);
    }
    let nom = "document." + fmt;
    const cd = r.headers.get("Content-Disposition") || "";
    const m = cd.match(/filename="([^"]+)"/);
    if (m) nom = m[1];
    const url = URL.createObjectURL(await r.blob());
    const a = document.createElement("a");
    a.href = url; a.download = nom;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
    docStatus.textContent = "⬇️ Téléchargé : " + nom;
  } catch (e) {
    docStatus.textContent = "⚠️ " + e.message;
  }
}

document.getElementById("doc-btn").addEventListener("click", () => {
  docStatus.textContent = ""; docResult.style.display = "none";
  docModal.classList.add("show");
});
document.getElementById("doc-close").addEventListener("click", () => docModal.classList.remove("show"));
docModal.addEventListener("click", (e) => { if (e.target === docModal) docModal.classList.remove("show"); });
docRun.addEventListener("click", () => redigerDocument());
document.getElementById("doc-regen").addEventListener("click", () => redigerDocument());
document.getElementById("doc-apply-edit")?.addEventListener("click", () => {
  if (!docModifier?.value.trim()) {
    docStatus.textContent = "⚠️ Décris la modification souhaitée.";
    return;
  }
  redigerDocument(true);
});
document.getElementById("doc-download").addEventListener("click", telechargerDocument);

applyAvatar();
setState("idle");

// --- Modal securite ---
const securityModal = document.getElementById("security-modal");
const cloudToggle = document.getElementById("cloud-toggle");
document.getElementById("security-btn")?.addEventListener("click", () => {
  if (cloudToggle) cloudToggle.checked = cloudAutorise;
  securityModal?.classList.add("show");
});
document.getElementById("security-close")?.addEventListener("click", () => securityModal?.classList.remove("show"));
securityModal?.addEventListener("click", (e) => { if (e.target === securityModal) securityModal.classList.remove("show"); });
document.getElementById("security-save-btn")?.addEventListener("click", async () => {
  const autorise = !!cloudToggle?.checked;
  const r = await apiFetch("/api/auth/cloud", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ autorise }),
  });
  if (r.ok) {
    cloudAutorise = autorise;
    cloudConfigured = autorise;
    checkHealth();
    securityModal?.classList.remove("show");
  }
});
document.getElementById("security-lock-btn")?.addEventListener("click", async () => {
  await apiFetch("/api/auth/logout", { method: "POST" });
  clearSession();
  securityModal?.classList.remove("show");
  afficherVerrou(true);
  window._onAuthOk = null;
  initSecurite();
});

function demarrerApp() {
  checkHealth();
  setInterval(checkHealth, 20000);
}
initSecurite().then(() => demarrerApp());

// ----------------------------------------------------------------------
// HUD : horloge temps réel + séquence de démarrage façon Iron Man
// ----------------------------------------------------------------------
const teleClock = document.getElementById("tele-clock");
function tickClock() {
  if (!teleClock) return;
  teleClock.textContent = new Date().toLocaleTimeString("fr-FR");
}
tickClock();
setInterval(tickClock, 1000);

// Boot desactive pour acces immediat au chat (apres deverrouillage).
(function sequenceDemarrage() {
  const boot = document.getElementById("boot");
  if (boot) boot.remove();
})();
