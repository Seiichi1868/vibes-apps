"use strict";

const HIDE_TEXT_KEY = "debate_watch_hide_text";
const HIGHLIGHT_KEY = "debate_watch_highlight";
const SHOW_JA_KEY = "debate_watch_show_ja";
const RATE_KEY = "debate_watch_rate";
const CONTINUOUS_KEY = "debate_watch_continuous";
const WORDS_PER_MIN = 140;
const RATES = [0.5, 0.75, 1, 1.25, 1.5];

const player = document.getElementById("watch-player");
const audio = document.getElementById("watch-audio");
const playback = {
  index: -1,
  engine: null,
  rate: 1,
  continuous: true,
  ratio: 0,
  speechTimer: null,
};

function readFlag(key, fallback) {
  try {
    const value = localStorage.getItem(key);
    if (value === null) return fallback;
    return value === "1";
  } catch (_) {
    return fallback;
  }
}

function writeFlag(key, on) {
  try {
    localStorage.setItem(key, on ? "1" : "0");
  } catch (_) {}
}

function readStored(key) {
  try {
    return localStorage.getItem(key);
  } catch (_) {
    return null;
  }
}

function writeStored(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch (_) {}
}

function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function partCards() {
  return [...document.querySelectorAll(".watch-part")];
}

function defaultRate() {
  return player?.dataset.level === "easy" ? 0.75 : 1;
}

function loadRate() {
  const stored = Number(readStored(RATE_KEY));
  if (RATES.includes(stored)) return stored;
  return defaultRate();
}

function formatClock(sec) {
  if (!Number.isFinite(sec) || sec < 0) return "0:00";
  const rounded = Math.round(sec);
  return `${Math.floor(rounded / 60)}:${String(rounded % 60).padStart(2, "0")}`;
}

function estimateSeconds(words, rate) {
  const count = Number(words) || 0;
  if (count <= 0) return 0;
  return (count / WORDS_PER_MIN) * 60 / (rate || 1);
}

function splitSentences(text) {
  const sentences = [];
  let start = 0;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (ch === "." || ch === "!" || ch === "?") {
      sentences.push({ start, end: i + 1 });
      start = i + 1;
    }
  }
  if (start < text.length) sentences.push({ start, end: text.length });
  if (!sentences.length && text) sentences.push({ start: 0, end: text.length });
  return sentences.filter((item) => text.slice(item.start, item.end).trim());
}

function highlightPhrase(html, phrases) {
  let next = html;
  phrases
    .filter((phrase) => phrase)
    .sort((a, b) => b.length - a.length)
    .forEach((phrase) => {
      const safe = escapeHtml(phrase);
      next = next.split(safe).join(`<mark class="watch-signpost">${safe}</mark>`);
    });
  return next;
}

function renderWatchTexts() {
  const highlight = readFlag(HIGHLIGHT_KEY, true);
  document.querySelectorAll(".watch-text").forEach((el) => {
    const raw = el.dataset.raw || el.textContent || "";
    el.dataset.raw = raw;
    let phrases = [];
    try {
      phrases = JSON.parse(el.dataset.phrases || "[]");
    } catch (_) {
      phrases = [];
    }
    const sentences = splitSentences(raw);
    el.innerHTML = sentences
      .map((sentence) => {
        const slice = raw.slice(sentence.start, sentence.end);
        const body = highlight ? highlightPhrase(escapeHtml(slice), phrases) : escapeHtml(slice);
        return `<span class="watch-sentence" data-start="${sentence.start}" data-end="${sentence.end}">${body}</span>`;
      })
      .join("");
  });
  refreshSentenceHighlight();
}

function applyWatchToggles() {
  const hideText = readFlag(HIDE_TEXT_KEY, false);
  const highlight = readFlag(HIGHLIGHT_KEY, true);
  const showJa = readFlag(SHOW_JA_KEY, true);
  document.querySelectorAll(".watch-part").forEach((card) => {
    card.classList.toggle("is-hidden-text", hideText);
  });
  document.querySelectorAll(".watch-key-point").forEach((el) => {
    el.classList.toggle("hidden", !showJa);
  });
  const hideBtn = document.getElementById("watch-hide-text");
  const highlightBtn = document.getElementById("watch-highlight");
  const jaBtn = document.getElementById("watch-show-ja");
  hideBtn?.setAttribute("aria-pressed", hideText ? "true" : "false");
  highlightBtn?.setAttribute("aria-pressed", highlight ? "true" : "false");
  jaBtn?.setAttribute("aria-pressed", showJa ? "true" : "false");
  hideBtn?.classList.toggle("bg-brand", hideText);
  hideBtn?.classList.toggle("text-white", hideText);
  highlightBtn?.classList.toggle("bg-brand", highlight);
  highlightBtn?.classList.toggle("text-white", highlight);
  jaBtn?.classList.toggle("bg-brand", showJa);
  jaBtn?.classList.toggle("text-white", showJa);
  renderWatchTexts();
}

function bindWatchToggles() {
  const hideBtn = document.getElementById("watch-hide-text");
  const highlightBtn = document.getElementById("watch-highlight");
  const jaBtn = document.getElementById("watch-show-ja");
  if (!hideBtn && !highlightBtn && !jaBtn) return;
  hideBtn?.addEventListener("click", () => {
    writeFlag(HIDE_TEXT_KEY, !readFlag(HIDE_TEXT_KEY, false));
    applyWatchToggles();
  });
  highlightBtn?.addEventListener("click", () => {
    writeFlag(HIGHLIGHT_KEY, !readFlag(HIGHLIGHT_KEY, true));
    applyWatchToggles();
  });
  jaBtn?.addEventListener("click", () => {
    writeFlag(SHOW_JA_KEY, !readFlag(SHOW_JA_KEY, true));
    applyWatchToggles();
  });
  applyWatchToggles();
}

function bindWatchFilter() {
  const bar = document.getElementById("watch-level-filter");
  const cards = document.querySelectorAll("[data-watch-level]");
  const empty = document.getElementById("watch-filter-empty");
  if (!bar || !cards.length) return;
  bar.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-level]");
    if (!btn) return;
    const level = btn.dataset.level || "";
    bar.querySelectorAll("[data-level]").forEach((item) => {
      item.classList.toggle("is-active", item === btn);
    });
    let shown = 0;
    cards.forEach((card) => {
      const match = !level || card.dataset.watchLevel === level;
      card.classList.toggle("hidden", !match);
      if (match) shown += 1;
    });
    empty?.classList.toggle("hidden", shown > 0);
  });
}

function usesFile(card) {
  if (!card) return false;
  return card.dataset.audioReady === "1" && Boolean(card.dataset.audioUrl);
}

function currentCard() {
  return partCards()[playback.index] || null;
}

function rawText(card) {
  const el = card?.querySelector(".watch-text");
  return el?.dataset.raw || el?.textContent || "";
}

function refreshEtas() {
  document.querySelectorAll(".watch-eta").forEach((el) => {
    const seconds = estimateSeconds(el.dataset.words, playback.rate);
    el.textContent = seconds ? `目安 ${formatClock(seconds)}` : "";
  });
}

function refreshRateButtons() {
  document.querySelectorAll("#watch-rates [data-rate]").forEach((btn) => {
    btn.classList.toggle("is-active", Number(btn.dataset.rate) === playback.rate);
  });
}

function applyAudioRate() {
  if (!audio) return;
  audio.playbackRate = playback.rate;
  audio.preservesPitch = true;
  try {
    audio.webkitPreservesPitch = true;
  } catch (_) {}
}

function stopSpeech() {
  if (playback.speechTimer) {
    clearInterval(playback.speechTimer);
    playback.speechTimer = null;
  }
  window.speechSynthesis?.cancel();
}

function stopPlayback() {
  stopSpeech();
  if (audio && !audio.paused) audio.pause();
  playback.engine = null;
  setPlayingUi(false);
}

function setPlayingUi(playing) {
  const toggle = document.getElementById("watch-toggle");
  if (toggle) toggle.textContent = playing ? "一時停止" : "再生";
  partCards().forEach((card, index) => {
    const active = index === playback.index;
    card.classList.toggle("is-active", active);
    const btn = card.querySelector("[data-part-play]");
    if (btn) btn.textContent = active && playing ? "一時停止" : "再生";
  });
  const card = currentCard();
  const now = document.getElementById("watch-now");
  if (now) now.textContent = card ? `${card.dataset.part} · ${card.dataset.side}` : "—";
  const seek = document.getElementById("watch-seek");

}

function markSentence(card, ratio) {
  if (!card) return;
  const text = rawText(card);
  const pos = Math.min(text.length, Math.max(0, ratio * text.length));
  card.querySelectorAll(".watch-sentence").forEach((span) => {
    const start = Number(span.dataset.start);
    const end = Number(span.dataset.end);
    span.classList.toggle("is-current", pos >= start && pos < end);
  });
}

function refreshSentenceHighlight() {
  partCards().forEach((card, index) => {
    if (index !== playback.index) {
      card.querySelectorAll(".watch-sentence.is-current").forEach((span) => span.classList.remove("is-current"));
      return;
    }
    markSentence(card, playback.ratio);
  });
}

function updateClock(current, duration) {
  const clock = document.getElementById("watch-clock");
  const seek = document.getElementById("watch-seek");
  if (clock) clock.textContent = `${formatClock(current)} / ${formatClock(duration)}`;
  if (seek && duration > 0 && document.activeElement !== seek) {
    seek.value = String(Math.round((current / duration) * 1000));
  }
}

function showNoAudio(index) {
  const card = partCards()[index];
  const el = document.getElementById("watch-now");
  stopPlayback();
  if (card) {
    card.classList.add("is-active");
    playback.index = index;
  }
  if (el) el.textContent = "音声がありません";
  let note = card?.querySelector(".watch-no-audio");
  if (card && !note) {
    note = document.createElement("p");
    note.className = "watch-no-audio text-xs text-rose-600 font-medium mt-2";
    note.textContent = "音声がありません";
    card.appendChild(note);
  }
  if (note) setTimeout(() => note.remove(), 3000);
}

function playFile(index, ratio) {
  const card = partCards()[index];
  if (!audio || !usesFile(card)) {
    showNoAudio(index);
    return;
  }
  playback.index = index;
  playback.engine = "file";
  playback.ratio = ratio;
  const nextSrc = card.dataset.audioUrl;
  const applyPosition = () => {
    applyAudioRate();
    if (audio.duration) audio.currentTime = (ratio || 0) * audio.duration;
  };
  if (audio.dataset.loadedSrc !== nextSrc) {
    audio.dataset.loadedSrc = nextSrc;
    audio.src = nextSrc;
    audio.addEventListener("loadedmetadata", function once() {
      audio.removeEventListener("loadedmetadata", once);
      if (playback.engine === "file" && playback.index === index) applyPosition();
    });
  } else {
    applyPosition();
  }
  applyAudioRate();
  audio.play().then(() => {
    setPlayingUi(true);
    card.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }).catch(() => showNoAudio(index));
}

function playPart(index, ratio) {
  const cards = partCards();
  if (index < 0 || index >= cards.length) return;
  playFile(index, ratio || 0);
}

function toggleCurrent() {
  const cards = partCards();
  if (!cards.length) return;
  if (playback.engine === "file" && audio && !audio.paused) {
    audio.pause();
    setPlayingUi(false);
    return;
  }
  if (playback.engine === "file" && audio && audio.paused && audio.src && playback.index >= 0) {
    audio.play().catch(() => showNoAudio(playback.index));
    setPlayingUi(true);
    return;
  }
  const index = playback.index >= 0 ? playback.index : 0;
  const ratio = 0;
  playPart(index, ratio);
}

function bindPlayer() {
  if (!player || !audio) return;
  playback.rate = loadRate();
  playback.continuous = readFlag(CONTINUOUS_KEY, true);
  refreshRateButtons();
  refreshEtas();
  const continuousBtn = document.getElementById("watch-continuous");
  const syncContinuous = () => {
    if (!continuousBtn) return;
    continuousBtn.setAttribute("aria-pressed", playback.continuous ? "true" : "false");
    continuousBtn.textContent = playback.continuous ? "通し再生: ON" : "通し再生: OFF";
  };
  syncContinuous();

  document.getElementById("watch-toggle")?.addEventListener("click", toggleCurrent);
  document.getElementById("watch-prev")?.addEventListener("click", () => {
    if (playback.index > 0) playPart(playback.index - 1, 0);
  });
  document.getElementById("watch-next")?.addEventListener("click", () => {
    if (playback.index + 1 < partCards().length) playPart(playback.index + 1, 0);
    else if (playback.index < 0) playPart(0, 0);
  });
  document.getElementById("watch-rates")?.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-rate]");
    if (!btn) return;
    playback.rate = Number(btn.dataset.rate) || 1;
    writeStored(RATE_KEY, String(playback.rate));
    refreshRateButtons();
    refreshEtas();
    applyAudioRate();
  });
  continuousBtn?.addEventListener("click", () => {
    playback.continuous = !playback.continuous;
    writeFlag(CONTINUOUS_KEY, playback.continuous);
    syncContinuous();
  });
  document.getElementById("watch-seek")?.addEventListener("input", (event) => {
    if (!audio.duration) return;
    const ratio = Number(event.target.value) / 1000;
    audio.currentTime = ratio * audio.duration;
    playback.ratio = ratio;
    markSentence(currentCard(), ratio);
  });
  document.getElementById("watch-parts")?.addEventListener("click", (event) => {
    const sentence = event.target.closest(".watch-sentence");
    const card = event.target.closest(".watch-part");
    if (!card) return;
    const index = partCards().indexOf(card);
    if (sentence) {
      if (!usesFile(card)) { showNoAudio(index); return; }
      const text = rawText(card);
      const ratio = text.length ? Number(sentence.dataset.start) / text.length : 0;
      playPart(index, ratio);
      return;
    }
    const btn = event.target.closest("[data-part-play]");
    if (!btn) return;
    if (playback.index === index) {
      toggleCurrent();
      return;
    }
    playPart(index, 0);
  });
  audio.addEventListener("timeupdate", () => {
    if (playback.engine !== "file" || !audio.duration) return;
    playback.ratio = audio.currentTime / audio.duration;
    markSentence(currentCard(), playback.ratio);
    updateClock(audio.currentTime, audio.duration);
  });
  audio.addEventListener("loadedmetadata", applyAudioRate);
  audio.addEventListener("play", applyAudioRate);
  audio.addEventListener("ended", () => {
    if (playback.engine !== "file") return;
    playback.ratio = 0;
    if (playback.continuous && playback.index + 1 < partCards().length) {
      playback.engine = null;
      playPart(playback.index + 1, 0);
    } else {
      playback.engine = null;
      setPlayingUi(false);
    }
  });
  audio.addEventListener("error", () => {
    if (playback.engine !== "file") return;
    showNoAudio(playback.index);
  });
}

bindWatchToggles();
bindWatchFilter();
bindPlayer();
