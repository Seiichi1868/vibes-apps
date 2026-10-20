(() => {
  const SESSION_ID = window.LEVEL_CHECK_SESSION_ID;
  const IS_APPLE = /iPad|iPhone|iPod/.test(navigator.userAgent)
    || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)
    || (/Macintosh/.test(navigator.userAgent) && /^((?!chrome|android).)*safari/i.test(navigator.userAgent));
  const MIME_CANDIDATES = IS_APPLE
    ? ["audio/mp4", "audio/mp4;codecs=mp4a.40.2", "audio/aac", "audio/webm;codecs=opus", "audio/webm", "audio/ogg"]
    : ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg"];
  const VAD_THRESHOLD = 0.06;
  const AUDIO_PROMPT_TYPES = new Set(["A", "B", "C", "D", "E"]);
  const TIMER_TYPES = new Set(["A", "E", "F"]);
  const STATUS_LABELS = {
    not_started: "未実施",
    recording: "録音中",
    transcribing: "文字起こし中",
    scoring: "採点中",
    done: "完了",
    error: "エラー",
  };

  const cards = Array.from(document.querySelectorAll(".part-card"));
  const allDoneSection = document.getElementById("all-done-section");
  const overallLabel = document.getElementById("overall-progress-label");
  const micErrorBanner = document.getElementById("mic-error-banner");

  let activeRecordingPart = null;
  let currentAudio = null;
  const cardState = new Map();

  function pickMimeType() {
    if (!window.MediaRecorder) return "";
    for (const type of MIME_CANDIDATES) {
      if (MediaRecorder.isTypeSupported(type)) return type;
    }
    return "";
  }

  function extensionFor(mimeType) {
    if (mimeType.includes("mp4")) return "mp4";
    if (mimeType.includes("ogg")) return "ogg";
    return IS_APPLE ? "mp4" : "webm";
  }

  function setError(card, message) {
    const el = card.querySelector(".part-error");
    if (!message) {
      el.classList.add("hidden");
      el.textContent = "";
      return;
    }
    el.textContent = message;
    el.classList.remove("hidden");
  }

  function updateRecordButtonStates() {
    cards.forEach((card) => {
      const btn = card.querySelector(".btn-record");
      if (!btn || card.dataset.status !== "not_started") return;
      const locked = activeRecordingPart !== null;
      btn.disabled = locked;
      btn.classList.toggle("opacity-40", locked);
      btn.classList.toggle("cursor-not-allowed", locked);
    });
  }

  function refreshOverallProgress() {
    const total = cards.length;
    const finished = cards.filter((c) => ["done", "error"].includes(c.dataset.status)).length;
    overallLabel.textContent = `${finished}/${total} 問完了`;

    document.querySelectorAll("[data-step-part]").forEach((dot) => {
      const card = cards.find((c) => c.dataset.partId === dot.dataset.stepPart);
      const status = card ? card.dataset.status : "not_started";
      const colorByStatus = {
        not_started: "bg-slate-200",
        recording: "bg-rose-400",
        transcribing: "bg-amber-400",
        scoring: "bg-amber-400",
        done: "bg-emerald-500",
        error: "bg-rose-500",
      };
      dot.className = `h-1.5 rounded-full step-dot ${colorByStatus[status] || "bg-slate-200"}`;
    });

    allDoneSection.classList.toggle("hidden", finished !== total);
    updateRecordButtonStates();
  }

  function renderCard(card) {
    const status = card.dataset.status;
    const recordBtn = card.querySelector(".btn-record");
    const stopBtn = card.querySelector(".btn-stop");
    const retryBtn = card.querySelector(".btn-retry");
    const processingLabel = card.querySelector(".btn-processing");
    const pill = card.querySelector("[data-status-pill]");

    pill.textContent = STATUS_LABELS[status] || status;
    pill.className = `status-pill status-${status}`;

    recordBtn.classList.add("hidden");
    stopBtn.classList.add("hidden");
    retryBtn.classList.add("hidden");
    processingLabel.classList.add("hidden");

    if (status === "not_started") {
      recordBtn.classList.remove("hidden");
    } else if (status === "recording") {
      stopBtn.classList.remove("hidden");
    } else if (status === "transcribing" || status === "scoring") {
      processingLabel.classList.remove("hidden");
    } else if (status === "done" || status === "error") {
      retryBtn.classList.remove("hidden");
    }

    refreshOverallProgress();
  }

  function stopCurrentAudio() {
    if (currentAudio) {
      try {
        currentAudio.pause();
        currentAudio.src = "";
      } catch (_) { /* ignore */ }
      currentAudio = null;
    }
    if (window.speechSynthesis) {
      try { window.speechSynthesis.cancel(); } catch (_) { /* ignore */ }
    }
  }

  function speakFallback(text, onEnd) {
    const finish = () => { if (onEnd) onEnd(); };
    if (!window.speechSynthesis || !window.SpeechSynthesisUtterance || !text) {
      finish();
      return false;
    }
    window.speechSynthesis.cancel();
    const voices = window.speechSynthesis.getVoices();
    const voice = voices.find((item) => item.lang === "en-US" && item.localService)
      || voices.find((item) => (item.lang || "").toLowerCase().startsWith("en"));
    const chunks = IS_APPLE && text.length > 180
      ? text.split(/(?<=[.!?])\s+/).reduce((acc, part) => {
          if (!acc.length) return [part];
          const next = `${acc[acc.length - 1]} ${part}`;
          if (next.length > 180) return acc.concat(part);
          return acc.slice(0, -1).concat(next);
        }, [])
      : [text];
    chunks.forEach((chunk, index) => {
      const utter = new SpeechSynthesisUtterance(chunk);
      utter.lang = voice && voice.lang ? voice.lang : "en-US";
      utter.rate = 1;
      utter.pitch = 1;
      utter.volume = 1;
      if (voice) utter.voice = voice;
      if (index === chunks.length - 1) {
        utter.onend = finish;
        utter.onerror = finish;
      }
      window.speechSynthesis.speak(utter);
    });
    if (!voices.length) {
      window.speechSynthesis.addEventListener("voiceschanged", () => {
        window.speechSynthesis.getVoices();
      }, { once: true });
    }
    return true;
  }

  function playPrompt(card, onEnd) {
    const finish = () => { if (onEnd) onEnd(); };
    const audioUrl = card.dataset.promptAudioUrl || "";
    const promptText = card.dataset.promptText || card.dataset.targetText || card.dataset.questionText || "";
    stopCurrentAudio();

    if (audioUrl) {
      const audio = new Audio(audioUrl);
      audio.playsInline = true;
      audio.setAttribute("playsinline", "");
      audio.preload = "auto";
      currentAudio = audio;
      let done = false;
      const complete = () => {
        if (done) return;
        done = true;
        if (currentAudio === audio) currentAudio = null;
        finish();
      };
      audio.addEventListener("ended", complete);
      audio.addEventListener("error", () => {
        // サーバー音声が失敗したらブラウザ合成へ
        if (!speakFallback(promptText, complete)) complete();
      });
      audio.play().catch(() => {
        if (!speakFallback(promptText, complete)) complete();
      });
      return true;
    }

    return speakFallback(promptText, finish);
  }

  function revealAfterAudio(card, taskType) {
    const questionReveal = card.querySelector("[data-question-reveal]");
    if (!questionReveal) return;
    // C/D: 質問文、E: 日本語の指示。A/B は英語本文を出さない。
    const revealTypes = new Set(["C", "D", "E"]);
    if (!revealTypes.has(taskType)) {
      questionReveal.textContent = "";
      questionReveal.classList.add("hidden");
      return;
    }
    const text = (card.dataset.questionText || "").trim();
    if (!text) {
      questionReveal.textContent = "";
      questionReveal.classList.add("hidden");
      return;
    }
    questionReveal.textContent = text;
    questionReveal.classList.remove("hidden");
  }

  function resetStimulusUi(card) {
    const questionReveal = card.querySelector("[data-question-reveal]");
    const fallbackEl = card.querySelector("[data-fallback-text]");
    if (questionReveal) {
      questionReveal.textContent = "";
      questionReveal.classList.add("hidden");
    }
    if (fallbackEl) {
      fallbackEl.textContent = "";
      fallbackEl.classList.add("hidden");
    }
  }

  function setupStimulus(card) {
    const taskType = card.dataset.taskType;
    const state = cardState.get(card.dataset.partId) || {};
    resetStimulusUi(card);

    if (AUDIO_PROMPT_TYPES.has(taskType)) {
      const noteEl = card.querySelector("[data-audio-note]");
      const fallbackEl = card.querySelector("[data-fallback-text]");
      const recordBtn = card.querySelector(".btn-record");
      const replayBtn = card.querySelector(".btn-replay");
      const PLAY_LABEL = "🔊 問題を聞いて録音";
      if (recordBtn) recordBtn.textContent = PLAY_LABEL;

      const playStimulus = (onSpoken) => {
        if (recordBtn) {
          recordBtn.disabled = true;
          recordBtn.textContent = "🔊 再生中...";
        }
        // 再生中は問題文を隠す（再再生時も含む）
        resetStimulusUi(card);
        if (noteEl) noteEl.classList.remove("hidden");

        const spoke = playPrompt(card, () => {
          state.stimulusReadyAt = Date.now();
          cardState.set(card.dataset.partId, state);
          revealAfterAudio(card, taskType);
          if (recordBtn && card.dataset.status === "not_started") {
            recordBtn.disabled = false;
            recordBtn.textContent = PLAY_LABEL;
          }
          if (onSpoken) onSpoken();
        });
        if (!spoke) {
          // 音声不可時のみフォールバック表示（聞き取り課題の代替）
          const text = card.dataset.promptText || card.dataset.questionText || "";
          if (fallbackEl && text) {
            fallbackEl.textContent = text;
            fallbackEl.classList.remove("hidden");
          }
          if (noteEl) {
            noteEl.textContent = "🔊 音声再生に対応していないため、文章を表示しました。";
            noteEl.classList.remove("hidden");
          }
          revealAfterAudio(card, taskType);
          state.stimulusReadyAt = Date.now();
          cardState.set(card.dataset.partId, state);
          if (recordBtn) {
            recordBtn.disabled = false;
            recordBtn.textContent = "● 録音開始";
          }
        }
      };

      // 二重登録防止
      if (replayBtn && !replayBtn.dataset.bound) {
        replayBtn.dataset.bound = "1";
        replayBtn.addEventListener("click", () => playStimulus());
      }
      card._playAndRecord = () => playStimulus(() => handleRecordClick(card));
      if (noteEl) {
        noteEl.textContent = taskType === "B"
          ? "🔊「問題を聞いて録音」を押すと音声が流れ、終わると同時に自動で録音が始まります。"
          : "🔊「問題を聞いて録音」を押すと音声が流れます。聞き終わったら録音できます。";
      }
    } else if (taskType === "F") {
      state.stimulusReadyAt = Date.now();
      cardState.set(card.dataset.partId, state);
    }
  }

  function setupVadMeter(card, stream, state) {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    const bar = card.querySelector("[data-volume-bar]");
    if (!AudioCtx) return null;

    let ctx;
    try {
      ctx = new AudioCtx();
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      analyser.smoothingTimeConstant = 0.5;
      source.connect(analyser);

      const dataArray = new Uint8Array(analyser.frequencyBinCount);
      let rafId = null;

      const tick = () => {
        analyser.getByteTimeDomainData(dataArray);
        let sumSquares = 0;
        for (let i = 0; i < dataArray.length; i += 1) {
          const v = (dataArray[i] - 128) / 128;
          sumSquares += v * v;
        }
        const rms = Math.sqrt(sumSquares / dataArray.length);
        if (bar) bar.style.width = `${Math.round(Math.min(1, rms * 4) * 100)}%`;

        if (!state.speechOnsetAt && rms >= VAD_THRESHOLD) {
          state.speechOnsetAt = Date.now();
        }
        rafId = requestAnimationFrame(tick);
      };
      tick();

      return {
        stop() {
          if (rafId) cancelAnimationFrame(rafId);
          try { source.disconnect(); } catch (_) { /* ignore */ }
          try { analyser.disconnect(); } catch (_) { /* ignore */ }
          try { ctx.close(); } catch (_) { /* ignore */ }
          if (bar) bar.style.width = "0%";
        },
      };
    } catch (_) {
      if (ctx) {
        try { ctx.close(); } catch (_) { /* ignore */ }
      }
      return null;
    }
  }

  function formatSeconds(totalSeconds) {
    const sec = Math.max(0, Math.floor(totalSeconds || 0));
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }

  function startCountdown(card, state) {
    const timeLimit = Number(card.dataset.timeLimit || 0);
    const timerEl = card.querySelector("[data-timer]");
    if (!timerEl || timeLimit <= 0) return;
    const startedAt = Date.now();

    state.timerIntervalId = setInterval(() => {
      const elapsed = (Date.now() - startedAt) / 1000;
      const remaining = timeLimit - elapsed;
      timerEl.textContent = formatSeconds(Math.max(0, remaining));
      timerEl.classList.toggle("text-rose-600", remaining <= 3);
      if (remaining <= 0) {
        clearInterval(state.timerIntervalId);
        state.timerIntervalId = null;
        handleStopClick(card);
      }
    }, 200);
  }

  function stopCountdown(state) {
    if (state.timerIntervalId) {
      clearInterval(state.timerIntervalId);
      state.timerIntervalId = null;
    }
  }

  async function handleRecordClick(card) {
    const partId = card.dataset.partId;
    if (activeRecordingPart) return;
    setError(card, "");
    micErrorBanner.classList.add("hidden");
    stopCurrentAudio();

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setError(card, "このブラウザはマイク録音に対応していません。別のブラウザでお試しください。");
      return;
    }

    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      setError(card, "マイクへのアクセスが許可されませんでした。ブラウザの設定を確認し、もう一度お試しください。");
      return;
    }

    const state = cardState.get(partId) || {};
    state.speechOnsetAt = null;
    state.mediaStream = stream;
    state.recordingStartedAt = Date.now();
    if (!state.stimulusReadyAt) state.stimulusReadyAt = state.recordingStartedAt;

    const mimeType = pickMimeType();
    const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
    const chunks = [];

    recorder.addEventListener("dataavailable", (e) => {
      if (e.data && e.data.size > 0) chunks.push(e.data);
    });

    recorder.addEventListener("stop", () => {
      stream.getTracks().forEach((t) => t.stop());
      const blob = new Blob(chunks, { type: mimeType || "audio/webm" });
      const onsetAt = state.speechOnsetAt || state.recordingStartedAt;
      const stimulusReadyAt = state.stimulusReadyAt || state.recordingStartedAt;
      const latencyMs = Math.max(0, onsetAt - stimulusReadyAt);
      uploadAudio(card, blob, mimeType || "audio/webm", latencyMs);
    });

    recorder.addEventListener("error", () => {
      setError(card, "録音中にエラーが発生しました。もう一度お試しください。");
      cleanupRecording(card, partId);
      activeRecordingPart = null;
      updateRecordButtonStates();
    });

    state.recorder = recorder;
    state.vadMeter = setupVadMeter(card, stream, state);
    cardState.set(partId, state);

    activeRecordingPart = partId;
    updateRecordButtonStates();

    card.dataset.status = "recording";
    renderCard(card);
    card.querySelector("[data-live-monitor]")?.classList.remove("hidden");

    try {
      recorder.start();
    } catch (err) {
      setError(card, "録音を開始できませんでした。もう一度お試しください。");
      cleanupRecording(card, partId);
      activeRecordingPart = null;
      updateRecordButtonStates();
      card.dataset.status = "not_started";
      renderCard(card);
      return;
    }

    if (TIMER_TYPES.has(card.dataset.taskType) || Number(card.dataset.timeLimit || 0) > 0) {
      startCountdown(card, state);
    }
  }

  function cleanupRecording(card, partId) {
    const state = cardState.get(partId) || {};
    stopCountdown(state);
    if (state.vadMeter) {
      state.vadMeter.stop();
      state.vadMeter = null;
    }
    cardState.set(partId, state);
    card.querySelector("[data-live-monitor]")?.classList.add("hidden");
  }

  function handleStopClick(card) {
    const partId = card.dataset.partId;
    const state = cardState.get(partId) || {};
    if (!state.recorder || state.recorder.state === "inactive") return;

    cleanupRecording(card, partId);
    activeRecordingPart = null;
    updateRecordButtonStates();

    card.dataset.status = "transcribing";
    renderCard(card);
    state.recorder.stop();
  }

  async function uploadAudio(card, blob, mimeType, latencyMs) {
    const partId = card.dataset.partId;
    const formData = new FormData();
    formData.append("audio", blob, `${partId}.${extensionFor(mimeType)}`);
    formData.append("response_latency_ms", String(Math.round(latencyMs)));

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 60000);

    try {
      const res = await fetch(`/level_check/api/sessions/${SESSION_ID}/parts/${partId}/audio`, {
        method: "POST",
        body: formData,
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      const data = await res.json();

      if (!res.ok || !data.ok) {
        card.dataset.status = "error";
        renderCard(card);
        setError(card, data.error || "アップロードに失敗しました。「やり直す」から再度お試しください。");
        return;
      }

      card.dataset.status = data.part.status || "transcribing";
      setError(card, "");
      renderCard(card);
      startStatusPolling(card);
    } catch (err) {
      clearTimeout(timeoutId);
      card.dataset.status = "error";
      renderCard(card);
      const msg =
        err.name === "AbortError"
          ? "アップロードがタイムアウトしました。ネットワークをご確認のうえ、やり直してください。"
          : "アップロードに失敗しました。ネットワークをご確認のうえ、やり直してください。";
      setError(card, msg);
    }
  }

  function startStatusPolling(card) {
    const partId = card.dataset.partId;
    const state = cardState.get(partId) || {};
    if (state.pollIntervalId) return;

    state.pollIntervalId = setInterval(async () => {
      try {
        const res = await fetch(`/level_check/api/sessions/${SESSION_ID}/parts/${partId}`);
        if (!res.ok) return;
        const data = await res.json();
        if (!data.ok) return;
        const part = data.part;

        if (part.status === card.dataset.status) return;
        card.dataset.status = part.status;
        renderCard(card);

        if (part.status === "done" || part.status === "error") {
          stopStatusPolling(partId);
          if (part.transcript_error) setError(card, part.transcript_error);
        }
      } catch (_) {
        // ネットワーク不調時は次回のポーリングで再試行
      }
    }, 2500);
    cardState.set(partId, state);
  }

  function stopStatusPolling(partId) {
    const state = cardState.get(partId) || {};
    if (state.pollIntervalId) {
      clearInterval(state.pollIntervalId);
      state.pollIntervalId = null;
    }
    cardState.set(partId, state);
  }

  async function handleRetryClick(card) {
    const partId = card.dataset.partId;
    try {
      const res = await fetch(`/level_check/api/sessions/${SESSION_ID}/parts/${partId}/retry`, { method: "POST" });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || "リセットに失敗しました。");

      card.dataset.status = "not_started";
      setError(card, "");
      renderCard(card);
      setupStimulus(card);
    } catch (err) {
      setError(card, err.message);
    }
  }

  cards.forEach((card) => {
    cardState.set(card.dataset.partId, {});
    card.querySelector(".btn-record")?.addEventListener("click", () => {
      if (AUDIO_PROMPT_TYPES.has(card.dataset.taskType) && typeof card._playAndRecord === "function") {
        card._playAndRecord();
      } else {
        handleRecordClick(card);
      }
    });
    card.querySelector(".btn-stop")?.addEventListener("click", () => handleStopClick(card));
    card.querySelector(".btn-retry")?.addEventListener("click", () => handleRetryClick(card));

    if (card.dataset.status === "not_started") {
      setupStimulus(card);
    } else if (card.dataset.status === "transcribing" || card.dataset.status === "scoring") {
      startStatusPolling(card);
    }
    renderCard(card);
  });

  window.addEventListener("beforeunload", (event) => {
    if (activeRecordingPart) {
      event.preventDefault();
      event.returnValue = "";
    }
  });

  refreshOverallProgress();
})();
