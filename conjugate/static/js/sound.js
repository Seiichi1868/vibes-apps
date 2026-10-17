/**
 * サウンドエフェクト（ElevenLabs MP3を事前デコードして即再生）
 */
const SoundFX = (() => {
  const MUTE_KEY = "sfx_muted";
  const SFX_BASE = "/static/audio/conjugate/";
  const SFX_VERSION = "20261017e";
  const VOLUME = 0.5;
  const TAP_SELECTOR = [
    ".vsc-btn-primary",
    ".vsc-btn-secondary",
    ".vsc-btn-record",
    ".vsc-btn-stop",
    ".vsc-promo-btn",
    ".vsc-vocab-btn",
    ".vsc-vocab-master",
    ".vsc-filter-chip",
    ".vsc-category-card",
    ".celebrate-button",
  ].join(",");
  const NAV_SELECTOR = [
    "#start-btn",
    "[data-start]",
    ".vsc-nav-item",
    "a.vsc-btn-primary",
    "a.vsc-btn-secondary",
    "a.vsc-filter-chip",
    "a.vsc-menu-item",
    "a.vsc-guide-index-card",
    "a.vsc-coin-row",
    "#next-btn",
  ].join(",");
  const TAP_SKIP_SELECTOR = `#type-submit-btn, .vsc-choice-btn, ${NAV_SELECTOR}`;

  const FILES = {
    correct: "sfx-correct.mp3",
    incorrect: "sfx-incorrect.mp3",
    tap: "sfx-nav.mp3",
    coin: "sfx-coin.mp3",
    streak: "sfx-streak.mp3",
    guardian: "sfx-guardian.mp3",
    opening: "sfx-opening.mp3",
    nav: "sfx-nav.mp3",
  };

  // ファイル末尾の余韻が次の場面に食い込まないよう、再生長を場面に合わせる
  const CUES = {
    tap: { duration: 0.32, fade: 0.05, volume: 0.32 },
    incorrect: { duration: 0.36, fade: 0.05, volume: 0.45 },
    coin: { duration: 0.5, fade: 0.06, volume: 0.5 },
    correct: { duration: 0.58, fade: 0.06, volume: 0.5 },
    opening: { duration: 0.86, fade: 0, volume: 0.45 },
    nav: { duration: 0.32, fade: 0.05, volume: 0.32 },
    guardian: { duration: 0.85, fade: 0.1, volume: 0.5 },
    streak: { duration: 1.35, fade: 0.12, volume: 0.5 },
  };

  let audioCtx = null;
  let unlocked = false;
  let muted = readMuted();
  const rawBuffers = {};
  const decoded = {};
  const htmlSounds = {};
  const active = {};
  let loading = false;

  function readMuted() {
    try {
      return localStorage.getItem(MUTE_KEY) === "true";
    } catch (_) {
      return false;
    }
  }

  function persistMuted(value) {
    try {
      localStorage.setItem(MUTE_KEY, value ? "true" : "false");
    } catch (_) {
      /* ignore */
    }
  }

  function getContext() {
    if (!audioCtx) {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    return audioCtx;
  }

  function decodeAudioDataCompat(ctx, data) {
    return new Promise((resolve, reject) => {
      let settled = false;
      const done = (fn) => (value) => {
        if (settled) return;
        settled = true;
        fn(value);
      };
      const ret = ctx.decodeAudioData(data, done(resolve), done(reject));
      if (ret && typeof ret.then === "function") {
        ret.then(done(resolve), done(reject));
      }
    });
  }

  function preload() {
    Object.keys(FILES).forEach((key) => {
      const url = `${SFX_BASE}${FILES[key]}?v=${SFX_VERSION}`;
      const audio = new Audio(url);
      audio.preload = "auto";
      audio.volume = 0;
      htmlSounds[key] = audio;
      try {
        audio.load();
      } catch (_) {
        /* ignore */
      }
      fetch(url)
        .then((res) => (res.ok ? res.arrayBuffer() : Promise.reject()))
        .then((buf) => {
          rawBuffers[key] = buf;
          if (audioCtx) decodeKey(key);
        })
        .catch(() => {});
    });
  }

  function decodeKey(key) {
    if (decoded[key] || !rawBuffers[key] || !audioCtx) return Promise.resolve();
    const copy = rawBuffers[key].slice(0);
    return decodeAudioDataCompat(audioCtx, copy)
      .then((buffer) => {
        decoded[key] = buffer;
      })
      .catch(() => {});
  }

  function decodeReady() {
    if (loading || !audioCtx) return;
    loading = true;
    Promise.all(Object.keys(FILES).map(decodeKey)).finally(() => {
      loading = false;
    });
  }

  function stopHtml(key) {
    const audio = htmlSounds[key];
    if (!audio) return;
    window.clearTimeout(audio._cutTimer);
    try {
      audio.pause();
      audio.currentTime = 0;
    } catch (_) {
      /* ignore */
    }
  }

  function stopChannel(channel) {
    const node = active[channel];
    if (node && audioCtx) {
      try {
        node.gain.gain.cancelScheduledValues(audioCtx.currentTime);
        node.gain.gain.setValueAtTime(node.gain.gain.value, audioCtx.currentTime);
        node.gain.gain.linearRampToValueAtTime(0.0001, audioCtx.currentTime + 0.02);
        node.source.stop(audioCtx.currentTime + 0.03);
      } catch (_) {
        /* already stopped */
      }
    }
    delete active[channel];
    Object.keys(htmlSounds).forEach((key) => {
      const cueChannel = key === "correct" || key === "incorrect" ? "result" : key;
      if (cueChannel === channel) stopHtml(key);
    });
  }

  function startBuffer(key, opts) {
    const buffer = decoded[key];
    const cue = CUES[key] || {};
    if (!buffer || !audioCtx) return;
    const channel = (opts && opts.channel) || key;
    const delay = (opts && opts.delay) || 0;
    (opts && opts.stops ? opts.stops : []).forEach(stopChannel);
    stopChannel(channel);
    stopHtml(key);

    const source = audioCtx.createBufferSource();
    const gain = audioCtx.createGain();
    source.buffer = buffer;
    const volume = cue.volume != null ? cue.volume : VOLUME;
    const duration = Math.min(cue.duration || buffer.duration, buffer.duration);
    const fade = Math.min(cue.fade != null ? cue.fade : 0.04, duration / 2);
    const when = audioCtx.currentTime + delay;
    gain.gain.setValueAtTime(volume, when);
    if (fade > 0) {
      gain.gain.setValueAtTime(volume, when + Math.max(0, duration - fade));
      gain.gain.linearRampToValueAtTime(0.0001, when + duration);
    }
    source.connect(gain);
    gain.connect(audioCtx.destination);
    source.start(when, 0, duration);
    active[channel] = { source, gain };
    source.onended = () => {
      if (active[channel] && active[channel].source === source) delete active[channel];
    };
  }

  function playHtmlFallback(key, opts) {
    const audio = htmlSounds[key];
    const cue = CUES[key] || {};
    if (!audio) return false;
    const channel = (opts && opts.channel) || key;
    (opts && opts.stops ? opts.stops : []).forEach(stopChannel);
    stopChannel(channel);
    try {
      audio.pause();
      audio.currentTime = 0;
    } catch (_) {
      /* ignore */
    }
    audio.volume = cue.volume != null ? cue.volume : VOLUME;
    const playRet = audio.play();
    if (playRet && playRet.catch) playRet.catch(() => {});
    const durationMs = Math.max(80, (cue.duration || 0.4) * 1000);
    window.clearTimeout(audio._cutTimer);
    audio._cutTimer = window.setTimeout(() => stopHtml(key), durationMs);
    return true;
  }

  function play(key, opts) {
    if (muted || !unlocked) return;
    const options = opts || {};
    if (decoded[key] && audioCtx) {
      startBuffer(key, options);
      return;
    }
    playHtmlFallback(key, options);
    decodeReady();
  }

  function unlock() {
    try {
      const ctx = getContext();
      if (ctx.state === "suspended") ctx.resume();
    } catch (_) {
      return;
    }
    if (unlocked) return;
    unlocked = true;
    decodeReady();
  }

  function bindUnlock() {
    const once = { once: true, capture: true };
    document.addEventListener("pointerdown", unlock, { ...once, passive: true });
    document.addEventListener("touchstart", unlock, { ...once, passive: true });
    document.addEventListener("click", unlock, once);
  }

  let lastNavAt = 0;

  function playNav() {
    const now = performance.now();
    if (now - lastNavAt < 400) return;
    lastNavAt = now;
    play("nav", { channel: "nav", stops: ["tap"] });
  }

  function bindNavSounds() {
    document.addEventListener(
      "pointerdown",
      (event) => {
        if (event.button != null && event.button !== 0) return;
        const target = event.target && event.target.closest ? event.target.closest(NAV_SELECTOR) : null;
        if (!target || target.disabled || target.getAttribute("aria-disabled") === "true") return;
        playNav();
      },
      { capture: true, passive: true }
    );
    document.addEventListener(
      "submit",
      (event) => {
        if (event.target && event.target.id === "start-form") playNav();
      },
      true
    );
  }

  function bindTapSounds() {
    document.addEventListener(
      "pointerdown",
      (event) => {
        if (event.button != null && event.button !== 0) return;
        const target = event.target && event.target.closest ? event.target.closest(TAP_SELECTOR) : null;
        if (!target || target.disabled || target.getAttribute("aria-disabled") === "true") return;
        if (target.closest(TAP_SKIP_SELECTOR)) return;
        api.tap();
      },
      { capture: true, passive: true }
    );
  }

  function bindMuteToggle() {
    const sfxToggle = document.getElementById("sfx-toggle");
    if (!sfxToggle) return;
    sfxToggle.checked = !muted;
    sfxToggle.addEventListener("change", (e) => {
      api.setMuted(!e.target.checked);
      if (!muted) {
        unlock();
        api.tap();
      }
    });
  }

  const api = {
    unlock,
    stop(channel) {
      if (channel) stopChannel(channel);
      else Object.keys(active).forEach(stopChannel);
    },
    setMuted(value) {
      muted = Boolean(value);
      persistMuted(muted);
      if (muted) {
        Object.keys(active).forEach(stopChannel);
        Object.keys(htmlSounds).forEach(stopHtml);
      }
    },
    isMuted() {
      return muted;
    },
    tap: () => play("tap", { channel: "tap" }),
    correct: () => play("correct", { channel: "result", stops: ["tap"] }),
    incorrect: () => play("incorrect", { channel: "result", stops: ["tap"] }),
    coin: () => play("coin", { channel: "coin", delay: 0.08, stops: ["tap"] }),
    streakUpdate: () => play("streak", { channel: "streak", stops: ["tap", "result", "coin"] }),
    guardian: () => play("guardian", { channel: "guardian", stops: ["tap"] }),
    navigate: () => playNav(),
    opening() {
      const start = () => play("opening", { channel: "opening" });
      unlock();
      if (decoded.opening && audioCtx && audioCtx.state === "running") {
        start();
        return;
      }
      const audio = htmlSounds.opening;
      if (!audio) return;
      audio.volume = (CUES.opening && CUES.opening.volume) || VOLUME;
      const attempt = audio.play();
      if (attempt && attempt.then) {
        attempt.then(() => {
          const durationMs = Math.max(80, ((CUES.opening && CUES.opening.duration) || 0.85) * 1000);
          window.clearTimeout(audio._cutTimer);
          audio._cutTimer = window.setTimeout(() => stopHtml("opening"), durationMs);
        }).catch(() => {
          document.addEventListener("pointerdown", () => {
            unlock();
            start();
          }, { once: true, capture: true });
        });
      }
    },
  };

  preload();
  bindUnlock();
  bindTapSounds();
  bindNavSounds();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindMuteToggle);
  } else {
    bindMuteToggle();
  }

  return api;
})();

window.SoundFX = SoundFX;
