(() => {
  const SESSION_ID = window.DEBATE_SESSION_ID;
  const PART_ORDER = window.DEBATE_PART_ORDER || ["PM", "LO", "MG", "MO", "LOR", "PMR"];
  const TEXT_KEY = "debate_solo_text_visible";
  const DEFAULT_TEXT_VISIBLE = window.DEBATE_AI_TEXT_VISIBLE_DEFAULT !== false;

  if (window.DEBATE_MODE !== "solo") return;

  const cards = Array.from(document.querySelectorAll(".part-card"));
  /** @type {HTMLAudioElement|null} */
  let activeAudio = null;

  const PROGRESS_STEPS = [
    { atMs: 0, text: "相手が直前の発言を読み返しています…" },
    { atMs: 4000, text: "反論の組み立てを考えています…" },
    { atMs: 10000, text: "スピーチを書いています…" },
    { atMs: 20000, text: "論点の流れを整えています…" },
    { atMs: 32000, text: "読み上げ用の音声を準備しています…" },
    { atMs: 48000, text: "もうしばらくお待ちください…" },
  ];

  function loadTextVisible() {
    try {
      const stored = localStorage.getItem(TEXT_KEY);
      if (stored === "0") return false;
      if (stored === "1") return true;
    } catch (_) {
      /* ignore */
    }
    return DEFAULT_TEXT_VISIBLE;
  }

  function saveTextVisible(visible) {
    try {
      localStorage.setItem(TEXT_KEY, visible ? "1" : "0");
    } catch (_) {
      /* ignore */
    }
  }

  let textVisible = loadTextVisible();

  function precedingConfirmed(part) {
    const index = PART_ORDER.indexOf(part);
    if (index <= 0) return true;
    return PART_ORDER.slice(0, index).every((name) => {
      const card = cards.find((item) => item.dataset.part === name);
      return card?.dataset.status === "confirmed";
    });
  }

  function isPartLocked(part) {
    const card = cards.find((item) => item.dataset.part === part);
    if (!card || card.dataset.speaker === "ai") return true;
    return !precedingConfirmed(part);
  }

  function formatTime(seconds) {
    const sec = Math.max(0, Math.floor(seconds || 0));
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }

  function stopOtherAudio(except) {
    cards.forEach((card) => {
      const audio = card.querySelector("[data-ai-audio]");
      if (!audio || audio === except) return;
      audio.pause();
      const playBtn = card.querySelector("[data-ai-play]");
      if (playBtn && !playBtn.disabled) playBtn.textContent = "再生";
    });
  }

  function ttsUrl(part) {
    return `/debate/api/sessions/${SESSION_ID}/parts/${part}/tts`;
  }

  function setPanelStatus(card, message, isError = false) {
    const el = card.querySelector("[data-ai-status]");
    if (!el) return;
    el.textContent = message || "";
    el.classList.toggle("text-rose-600", Boolean(isError && message));
    el.classList.toggle("text-slate-500", !isError);
  }

  function syncTextToggle(card) {
    const textEl = card.querySelector("[data-ai-text]");
    const btn = card.querySelector("[data-ai-toggle-text]");
    if (textEl) textEl.classList.toggle("hidden", !textVisible);
    if (btn) btn.textContent = textVisible ? "テキストを隠す" : "テキストを表示";
  }

  function startFakeProgress(card) {
    const log = card.querySelector("[data-ai-progress]");
    if (!log) return;
    log.classList.remove("hidden");
    log.innerHTML = "";
    const state = card._soloProgress || {};
    if (state.timer) clearInterval(state.timer);
    let shown = 0;
    const startedAt = Date.now();
    const append = (text) => {
      const li = document.createElement("li");
      li.className = "judge-progress-item";
      li.textContent = text;
      log.appendChild(li);
      const items = log.querySelectorAll(".judge-progress-item");
      items.forEach((item, index) => {
        item.classList.toggle("is-current", index === items.length - 1);
        item.classList.toggle("is-done", index < items.length - 1);
      });
      shown += 1;
    };
    append(PROGRESS_STEPS[0].text);
    state.timer = setInterval(() => {
      const elapsed = Date.now() - startedAt;
      while (shown < PROGRESS_STEPS.length && elapsed >= PROGRESS_STEPS[shown].atMs) {
        append(PROGRESS_STEPS[shown].text);
      }
      if (shown >= PROGRESS_STEPS.length) clearInterval(state.timer);
    }, 400);
    card._soloProgress = state;
  }

  function stopFakeProgress(card) {
    const state = card._soloProgress || {};
    if (state.timer) clearInterval(state.timer);
    card._soloProgress = {};
    card.querySelector("[data-ai-progress]")?.classList.add("hidden");
  }

  function applyGeneration(card, data) {
    if (!data) return;
    if (data.status) card.dataset.status = data.status;
    if (data.generation_status) card.dataset.generationStatus = data.generation_status;
    if (data.tts_status) card.dataset.ttsStatus = data.tts_status;
    if (data.tts_audio_file) card.dataset.ttsFile = data.tts_audio_file;

    const textEl = card.querySelector("[data-ai-text]");
    if (textEl && data.transcript_edited) textEl.textContent = data.transcript_edited;

    const playBtn = card.querySelector("[data-ai-play]");
    const retryTts = card.querySelector("[data-ai-retry-tts]");
    const retryText = card.querySelector("[data-ai-retry-text]");
    const audio = card.querySelector("[data-ai-audio]");

    const gen = data.generation_status || card.dataset.generationStatus || "idle";
    const tts = data.tts_status || card.dataset.ttsStatus || "idle";

    retryText?.classList.toggle("hidden", gen !== "error");
    retryTts?.classList.toggle("hidden", !(gen === "done" && tts === "error"));

    if (gen === "generating" || gen === "idle") {
      if (gen === "generating") startFakeProgress(card);
      setPanelStatus(card, "相手の準備中です…");
      if (playBtn) {
        playBtn.disabled = true;
        playBtn.textContent = "準備中";
      }
    } else {
      stopFakeProgress(card);
    }

    if (gen === "error") {
      setPanelStatus(card, data.generation_error || "相手の発話を生成できませんでした。", true);
      if (playBtn) {
        playBtn.disabled = true;
        playBtn.textContent = "準備中";
      }
    }

    if (gen === "done") {
      if (tts === "done" && audio) {
        const nextSrc = ttsUrl(card.dataset.part);
        if (!audio.src || audio.dataset.loadedSrc !== nextSrc) {
          audio.src = nextSrc;
          audio.dataset.loadedSrc = nextSrc;
        }
        if (playBtn) {
          playBtn.disabled = false;
          if (playBtn.textContent === "準備中") playBtn.textContent = "再生";
        }
        setPanelStatus(card, "");
      } else if (tts === "generating" || tts === "idle") {
        if (playBtn) {
          playBtn.disabled = true;
          playBtn.textContent = "準備中";
        }
        setPanelStatus(card, "音声を準備しています…");
      } else if (tts === "error") {
        if (playBtn) {
          playBtn.disabled = true;
          playBtn.textContent = "準備中";
        }
        setPanelStatus(card, data.tts_error || "音声の準備に失敗しました。テキストは読めます。", true);
      }
    }

    refreshLocks();
  }

  async function pollCard(card) {
    const part = card.dataset.part;
    try {
      const res = await fetch(`/debate/api/sessions/${SESSION_ID}/parts/${part}/generation`);
      if (!res.ok) return;
      const data = await res.json();
        applyGeneration(card, data);
      const gen = data.generation_status;
      const tts = data.tts_status;
      const readyForGen = precedingConfirmed(card.dataset.part);
      const stillBusy =
        gen === "generating" ||
        (gen === "idle" && readyForGen) ||
        (gen === "done" && (tts === "idle" || tts === "generating"));
      if (!stillBusy && card._soloPoll) {
        clearInterval(card._soloPoll);
        card._soloPoll = null;
      }
    } catch (_) {
      /* 次回ポーリングで再試行 */
    }
  }

  function ensurePolling(card) {
    const gen = card.dataset.generationStatus || "idle";
    const tts = card.dataset.ttsStatus || "idle";
    const readyForGen = precedingConfirmed(card.dataset.part);
    const busy =
      gen === "generating" ||
      (gen === "idle" && readyForGen) ||
      (gen === "done" && (tts === "idle" || tts === "generating"));
    if (!busy) return;
    if (card._soloPoll) return;
    pollCard(card);
    card._soloPoll = setInterval(() => pollCard(card), 2500);
  }

  function refreshLocks() {
    const confirmed = cards.filter((card) => card.dataset.status === "confirmed").length;
    const overallLabel = document.getElementById("overall-progress-label");
    if (overallLabel) overallLabel.textContent = `${confirmed}/${cards.length} パート確定`;
    document.getElementById("all-done-section")?.classList.toggle("hidden", confirmed !== cards.length);

    document.querySelectorAll("[data-step-part]").forEach((dot) => {
      const card = cards.find((item) => item.dataset.part === dot.dataset.stepPart);
      const status = card ? card.dataset.status : "not_started";
      const generating = card?.dataset.speaker === "ai" && card.dataset.generationStatus === "generating";
      const colorByStatus = {
        not_started: generating ? "bg-amber-400" : "bg-slate-200",
        recording: "bg-rose-400",
        transcribing: "bg-amber-400",
        needs_review: "bg-sky-400",
        confirmed: "bg-emerald-500",
      };
      dot.className = `h-1.5 rounded-full step-dot ${colorByStatus[status] || "bg-slate-200"}`;
    });

    cards.forEach((card) => {
      const ready = precedingConfirmed(card.dataset.part);
      if (card.dataset.speaker === "ai") {
        const waiting = !ready && (card.dataset.generationStatus || "idle") !== "done";
        card.classList.toggle("part-card--locked", waiting);
        card.querySelector("[data-lock-note]")?.classList.toggle("hidden", !waiting);
        if (waiting) setPanelStatus(card, "前のパートを確定すると解禁されます");
        return;
      }
      const humanLocked = !ready && card.dataset.status === "not_started";
      card.classList.toggle("part-card--locked", humanLocked);
      card.querySelector("[data-lock-note]")?.classList.toggle("hidden", !humanLocked);
      const btn = card.querySelector(".btn-record");
      if (btn && card.dataset.status === "not_started") {
        btn.disabled = humanLocked;
        btn.classList.toggle("opacity-40", humanLocked);
        btn.classList.toggle("cursor-not-allowed", humanLocked);
      }
    });
  }

  function bindPlayer(card) {
    const audio = card.querySelector("[data-ai-audio]");
    const playBtn = card.querySelector("[data-ai-play]");
    const backBtn = card.querySelector("[data-ai-back]");
    const rate = card.querySelector("[data-ai-rate]");
    const seek = card.querySelector("[data-ai-seek]");
    const timeEl = card.querySelector("[data-ai-time]");
    const toggle = card.querySelector("[data-ai-toggle-text]");
    const retryTts = card.querySelector("[data-ai-retry-tts]");
    const retryText = card.querySelector("[data-ai-retry-text]");
    if (!audio) return;

    const updateTime = () => {
      if (timeEl) timeEl.textContent = `${formatTime(audio.currentTime)} / ${formatTime(audio.duration || 0)}`;
      if (seek && audio.duration) {
        seek.value = String(Math.round((audio.currentTime / audio.duration) * 1000));
      }
    };

    playBtn?.addEventListener("click", async () => {
      if (playBtn.disabled) return;
      if (!audio.src) audio.src = ttsUrl(card.dataset.part);
      if (audio.paused) {
        stopOtherAudio(audio);
        try {
          await audio.play();
          playBtn.textContent = "一時停止";
          activeAudio = audio;
        } catch (err) {
          setPanelStatus(card, "音声を再生できませんでした。", true);
        }
      } else {
        audio.pause();
        playBtn.textContent = "再生";
      }
    });

    backBtn?.addEventListener("click", () => {
      audio.currentTime = Math.max(0, audio.currentTime - 10);
      updateTime();
    });

    rate?.addEventListener("change", () => {
      audio.playbackRate = Number(rate.value) || 1;
    });

    seek?.addEventListener("input", () => {
      if (!audio.duration) return;
      audio.currentTime = (Number(seek.value) / 1000) * audio.duration;
      updateTime();
    });

    audio.addEventListener("timeupdate", updateTime);
    audio.addEventListener("loadedmetadata", updateTime);
    audio.addEventListener("ended", () => {
      if (playBtn) playBtn.textContent = "再生";
    });

    toggle?.addEventListener("click", () => {
      textVisible = !textVisible;
      saveTextVisible(textVisible);
      cards.forEach(syncTextToggle);
    });

    retryTts?.addEventListener("click", async () => {
      retryTts.disabled = true;
      try {
        const res = await fetch(`/debate/api/sessions/${SESSION_ID}/parts/${card.dataset.part}/tts/retry`, {
          method: "POST",
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "音声の再試行に失敗しました。");
        applyGeneration(card, data);
        ensurePolling(card);
      } catch (err) {
        setPanelStatus(card, err.message, true);
      } finally {
        retryTts.disabled = false;
      }
    });

    retryText?.addEventListener("click", async () => {
      retryText.disabled = true;
      try {
        const res = await fetch(`/debate/api/sessions/${SESSION_ID}/parts/${card.dataset.part}/generate`, {
          method: "POST",
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "再試行に失敗しました。");
        applyGeneration(card, data);
        ensurePolling(card);
      } catch (err) {
        setPanelStatus(card, err.message, true);
      } finally {
        retryText.disabled = false;
      }
    });

    syncTextToggle(card);
  }

  window.DebateSolo = {
    isPartLocked,
    refreshLocks,
  };

  cards.forEach((card) => {
    if (card.dataset.speaker === "ai") {
      bindPlayer(card);
      applyGeneration(card, {
        status: card.dataset.status,
        generation_status: card.dataset.generationStatus || "idle",
        tts_status: card.dataset.ttsStatus || "idle",
        tts_audio_file: card.dataset.ttsFile || "",
        transcript_edited: card.querySelector("[data-ai-text]")?.textContent || "",
      });
      ensurePolling(card);
    }
  });
  refreshLocks();
})();
