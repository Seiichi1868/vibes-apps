"use strict";

const HIDE_TEXT_KEY = "debate_watch_hide_text";
const HIGHLIGHT_KEY = "debate_watch_highlight";
const SHOW_JA_KEY = "debate_watch_show_ja";

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

function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function applySignposts(on) {
  document.querySelectorAll(".watch-text").forEach((el) => {
    const raw = el.dataset.raw || el.textContent || "";
    el.dataset.raw = raw;
    if (!on) {
      el.textContent = raw;
      return;
    }
    let phrases = [];
    try {
      phrases = JSON.parse(el.dataset.phrases || "[]");
    } catch (_) {
      phrases = [];
    }
    let html = escapeHtml(raw);
    phrases
      .filter((phrase) => phrase)
      .sort((a, b) => b.length - a.length)
      .forEach((phrase) => {
        const safe = escapeHtml(phrase);
        html = html.split(safe).join(`<mark class="watch-signpost">${safe}</mark>`);
      });
    el.innerHTML = html;
  });
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
  applySignposts(highlight);
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

bindWatchToggles();
bindWatchFilter();
