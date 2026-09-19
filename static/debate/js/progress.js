(() => {
  const SESSION_ID = window.DEBATE_SESSION_ID;
  const STATUS_LABELS = window.DEBATE_STATUS_LABELS || {};
  const CONFIGURED_MODE = window.DEBATE_TRANSCRIPTION_MODE || "batch";
  const IS_APPLE = /iPad|iPhone|iPod/.test(navigator.userAgent)
    || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)
    || (/Macintosh/.test(navigator.userAgent) && /^((?!chrome|android).)*safari/i.test(navigator.userAgent));
  const MIME_CANDIDATES = IS_APPLE
    ? ["audio/mp4", "audio/mp4;codecs=mp4a.40.2", "audio/aac", "audio/webm;codecs=opus", "audio/webm", "audio/ogg"]
    : ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg"];
  const SpeechRecognitionImpl = window.SpeechRecognition || window.webkitSpeechRecognition;
  const SPEECH_SUPPORTED = Boolean(SpeechRecognitionImpl);

  const cards = Array.from(document.querySelectorAll(".part-card"));
  const staleBanner = document.getElementById("stale-recording-banner");
  const modeFallbackBanner = document.getElementById("mode-fallback-banner");
  const allDoneSection = document.getElementById("all-done-section");
  const overallLabel = document.getElementById("overall-progress-label");
  const saveExitBtn = document.getElementById("save-exit-btn");
  const saveToast = document.getElementById("save-toast");

  /** @type {string|null} いま録音中のパート（これ以外の not_started パートだけ録音ボタンを無効化） */
  let activeRecordingPart = null;
  let modeFallbackWarned = false;

  const cardState = new Map();

  function getEffectiveMode() {
    if (CONFIGURED_MODE === "realtime" && !SPEECH_SUPPORTED) {
      if (!modeFallbackWarned) {
        modeFallbackWarned = true;
        modeFallbackBanner?.classList.remove("hidden");
      }
      return "batch";
    }
    return CONFIGURED_MODE;
  }

  function applyTranscriptionModeUI() {
    const mode = getEffectiveMode();
    const stopLabel = mode === "realtime" ? "停止して確定" : "停止して保存";
    document.querySelectorAll("[data-stop-label]").forEach((el) => {
      el.textContent = stopLabel;
    });
    document.querySelectorAll("[data-live-monitor-note]").forEach((el) => {
      el.textContent =
        mode === "realtime"
          ? "※ リアルタイム文字起こしモードです。発話内容がそのまま transcript_raw として保存されます。"
          : "※ 録音中の確認用の参考表示です（音量とブラウザのライブ認識）。保存される文字起こしはこの後Whisperで別途生成されます。";
    });
  }

  applyTranscriptionModeUI();

  // ── 時間経過の合図音（残り1分:1回／残り30秒:2回／制限到達後:連打） ──────
  let audioCtx = null;
  function getAudioCtx() {
    if (!audioCtx) {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return null;
      audioCtx = new AudioCtx();
    }
    if (audioCtx.state === "suspended") audioCtx.resume();
    return audioCtx;
  }

  function playBeep(delaySec = 0, freq = 880, duration = 0.14, volume = 0.35) {
    const ctx = getAudioCtx();
    if (!ctx) return;
    const startTime = ctx.currentTime + delaySec;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0.0001, startTime);
    gain.gain.exponentialRampToValueAtTime(volume, startTime + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, startTime + duration);
    osc.connect(gain).connect(ctx.destination);
    osc.start(startTime);
    osc.stop(startTime + duration + 0.02);
  }

  function playBeepSequence(count, interval = 0.22) {
    for (let i = 0; i < count; i += 1) {
      playBeep(i * interval);
    }
  }

  function pickMimeType() {
    if (!window.MediaRecorder) return "";
    for (const type of MIME_CANDIDATES) {
      if (MediaRecorder.isTypeSupported(type)) return type;
    }
    return "";
  }

  function extensionFor(mimeType) {
    if (mimeType.includes("mp4") || mimeType.includes("aac") || mimeType.includes("m4a")) return "mp4";
    if (mimeType.includes("ogg")) return "ogg";
    return "webm";
  }

  // ── 録音中のライブ確認表示（音量メーター／参考文字起こし） ───────
  // どちらも「録音が止まっていないか」を確認するための表示専用の機能で、
  // 保存される文字起こしデータ（Whisper API）には一切影響しない。

  function showLiveMonitor(card) {
    const monitor = card.querySelector("[data-live-monitor]");
    if (monitor) monitor.classList.remove("hidden");
  }

  function hideLiveMonitor(card) {
    const monitor = card.querySelector("[data-live-monitor]");
    if (monitor) monitor.classList.add("hidden");
    const bar = card.querySelector("[data-volume-bar]");
    if (bar) bar.style.width = "0%";
    const captionBox = card.querySelector("[data-live-caption]");
    if (captionBox) {
      captionBox.innerHTML =
        '<span class="text-slate-400">（発話するとここに認識したテキストが表示されます）</span>';
    }
  }

  function setupVolumeMeter(card, stream) {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    const bar = card.querySelector("[data-volume-bar]");
    if (!AudioCtx || !bar) return null;

    let ctx;
    try {
      ctx = new AudioCtx();
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      analyser.smoothingTimeConstant = 0.6;
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
        const level = Math.min(1, rms * 4); // マイクの一般的な入力レベルに合わせた感度調整
        bar.style.width = `${Math.round(level * 100)}%`;
        rafId = requestAnimationFrame(tick);
      };
      tick();

      return {
        stop() {
          if (rafId) cancelAnimationFrame(rafId);
          try { source.disconnect(); } catch (_) { /* ignore */ }
          try { analyser.disconnect(); } catch (_) { /* ignore */ }
          try { ctx.close(); } catch (_) { /* ignore */ }
          bar.style.width = "0%";
        },
      };
    } catch (err) {
      if (ctx) {
        try { ctx.close(); } catch (_) { /* ignore */ }
      }
      return null;
    }
  }

  function setupLiveCaption(card) {
    const captionBox = card.querySelector("[data-live-caption]");
    if (!captionBox) return null;

    if (!SpeechRecognitionImpl) {
      captionBox.innerHTML =
        '<span class="text-slate-400">このブラウザはライブ文字起こし表示に対応していません（録音自体は通常どおり行えます）。</span>';
      return null;
    }

    const recognition = new SpeechRecognitionImpl();
    recognition.lang = "en-US";
    recognition.continuous = true;
    recognition.interimResults = true;

    let finalText = "";
    let stopped = false;
    let paused = false;

    recognition.addEventListener("result", (event) => {
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const chunk = event.results[i][0].transcript;
        if (event.results[i].isFinal) finalText += `${chunk} `;
        else interim += chunk;
      }
      const combined = `${finalText}${interim}`.trim();
      captionBox.textContent =
        combined || "（発話するとここに認識したテキストが表示されます）";
    });

    recognition.addEventListener("error", () => {
      // 表示専用機能のため、認識エラー（無音区間など）は無視して継続する
    });

    recognition.addEventListener("end", () => {
      if (!stopped && !paused) {
        try { recognition.start(); } catch (_) { /* ignore */ }
      }
    });

    try {
      recognition.start();
    } catch (_) {
      /* ignore */
    }

    return {
      stop() {
        stopped = true;
        paused = false;
        try { recognition.stop(); } catch (_) { /* ignore */ }
      },
      pause() {
        paused = true;
        try { recognition.stop(); } catch (_) { /* ignore */ }
      },
      resume() {
        if (stopped) return;
        paused = false;
        try { recognition.start(); } catch (_) { /* ignore */ }
      },
    };
  }

  /** リアルタイム文字起こしモード用: 認識結果を transcript_raw として保存する */
  function setupRealtimeTranscription(card) {
    const captionBox = card.querySelector("[data-live-caption]");
    if (!captionBox || !SpeechRecognitionImpl) return null;

    const recognition = new SpeechRecognitionImpl();
    recognition.lang = "en-US";
    recognition.continuous = true;
    recognition.interimResults = true;

    let finalTranscript = "";
    let interimTranscript = "";
    let stopped = false;
    let paused = false;

    const rebuildFromResults = (event) => {
      const finalParts = [];
      const interimParts = [];
      for (let i = 0; i < event.results.length; i += 1) {
        const chunk = event.results[i][0].transcript.trim();
        if (!chunk) continue;
        if (event.results[i].isFinal) finalParts.push(chunk);
        else interimParts.push(chunk);
      }
      finalTranscript = finalParts.join(" ").trim();
      interimTranscript = interimParts.join(" ").trim();
    };

    const renderCaption = () => {
      const combined = `${finalTranscript} ${interimTranscript}`.trim();
      captionBox.textContent =
        combined || "（発話するとここに認識したテキストが表示されます）";
    };

    recognition.addEventListener("result", (event) => {
      rebuildFromResults(event);
      renderCaption();
    });

    recognition.addEventListener("error", () => {
      // 無音区間などは無視して継続
    });

    recognition.addEventListener("end", () => {
      if (!stopped && !paused) {
        try { recognition.start(); } catch (_) { /* ignore */ }
      }
    });

    try {
      recognition.start();
    } catch (_) {
      return null;
    }

    return {
      stop() {
        stopped = true;
        paused = false;
        try { recognition.stop(); } catch (_) { /* ignore */ }
      },
      pause() {
        paused = true;
        try { recognition.stop(); } catch (_) { /* ignore */ }
      },
      resume() {
        if (stopped) return;
        paused = false;
        try { recognition.start(); } catch (_) { /* ignore */ }
      },
      getTranscript() {
        return `${finalTranscript} ${interimTranscript}`.trim();
      },
    };
  }

  function formatSeconds(totalSeconds) {
    const sec = Math.max(0, Math.floor(totalSeconds || 0));
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
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

  function showSaveToast(message) {
    if (!saveToast) return;
    saveToast.textContent = message;
    saveToast.classList.remove("hidden");
    setTimeout(() => saveToast.classList.add("hidden"), 4000);
  }

  function showPartSaveMsg(card, message) {
    const el = card.querySelector(".part-save-msg");
    if (!el) return;
    el.textContent = message;
    el.classList.remove("hidden");
    setTimeout(() => {
      el.classList.add("hidden");
      el.textContent = "";
    }, 3000);
  }

  /** 録音中以外は not_started パートの録音ボタンを常に有効にする */
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
    const confirmed = cards.filter((c) => c.dataset.status === "confirmed").length;
    overallLabel.textContent = `${confirmed}/${total} パート確定`;

    document.querySelectorAll("[data-step-part]").forEach((dot) => {
      const card = cards.find((c) => c.dataset.part === dot.dataset.stepPart);
      const status = card ? card.dataset.status : "not_started";
      const colorByStatus = {
        not_started: "bg-slate-200",
        recording: "bg-rose-400",
        transcribing: "bg-amber-400",
        needs_review: "bg-sky-400",
        confirmed: "bg-emerald-500",
      };
      dot.className = `h-1.5 rounded-full step-dot ${colorByStatus[status] || "bg-slate-200"}`;
    });

    allDoneSection.classList.toggle("hidden", confirmed !== total);
    updateRecordButtonStates();
  }

  function renderCard(card) {
    const status = card.dataset.status;
    const part = card.dataset.part;
    const timeLimit = Number(card.dataset.timeLimit || 0);
    const elapsed = card.dataset.elapsed ? Number(card.dataset.elapsed) : null;

    const recordBtn = card.querySelector(".btn-record");
    const pauseBtn = card.querySelector(".btn-pause");
    const stopBtn = card.querySelector(".btn-stop");
    const reviewBtn = card.querySelector(".btn-review");
    const saveBtn = card.querySelector(".btn-save");
    const resetBtn = card.querySelector(".btn-reset");
    const uploadingLabel = card.querySelector(".btn-uploading");
    const pill = card.querySelector("[data-status-pill]");
    const timerEl = card.querySelector("[data-timer]");

    pill.textContent = STATUS_LABELS[status] || status;
    pill.className = `status-pill status-${status}`;

    recordBtn.classList.add("hidden");
    if (pauseBtn) pauseBtn.classList.add("hidden");
    stopBtn.classList.add("hidden");
    card.querySelector("[data-pause-note]")?.classList.add("hidden");
    reviewBtn.classList.add("hidden");
    if (saveBtn) saveBtn.classList.add("hidden");
    resetBtn.classList.add("hidden");
    uploadingLabel.classList.add("hidden");

    const state = cardState.get(part) || {};

    if (status === "not_started") {
      recordBtn.classList.remove("hidden");
      timerEl.textContent = formatSeconds(0);
      timerEl.classList.remove("text-rose-600");
    } else if (status === "recording") {
      stopBtn.classList.remove("hidden");
      if (pauseBtn) pauseBtn.classList.remove("hidden");
      const paused = Boolean(state.timerPaused);
      if (pauseBtn) pauseBtn.textContent = paused ? "録音を再開" : "一時停止";
      const recDot = card.querySelector(".rec-dot");
      recDot?.classList.toggle("is-paused", paused);
      const pauseNote = card.querySelector("[data-pause-note]");
      pauseNote?.classList.toggle("hidden", !paused);
      if (paused) {
        pill.textContent = "一時停止中";
        pill.className = "status-pill status-paused";
      }
      timerEl.textContent = formatSeconds(getElapsedSeconds(part));
      timerEl.classList.toggle("text-rose-600", getElapsedSeconds(part) > timeLimit);
    } else if (status === "transcribing") {
      uploadingLabel.classList.remove("hidden");
      reviewBtn.classList.remove("hidden");
      reviewBtn.textContent = "進捗を見る";
      if (saveBtn) saveBtn.classList.remove("hidden");
      if (elapsed !== null) {
        timerEl.textContent = formatSeconds(elapsed);
        timerEl.classList.toggle("text-rose-600", elapsed > timeLimit);
      }
    } else if (status === "needs_review") {
      reviewBtn.classList.remove("hidden");
      resetBtn.classList.remove("hidden");
      if (saveBtn) saveBtn.classList.remove("hidden");
      reviewBtn.textContent = "文字起こしを確認";
      if (elapsed !== null) {
        timerEl.textContent = formatSeconds(elapsed);
        timerEl.classList.toggle("text-rose-600", elapsed > timeLimit);
      }
    } else if (status === "confirmed") {
      reviewBtn.classList.remove("hidden");
      resetBtn.classList.remove("hidden");
      if (saveBtn) saveBtn.classList.remove("hidden");
      reviewBtn.textContent = "文字起こしを見る";
      if (elapsed !== null) {
        timerEl.textContent = formatSeconds(elapsed);
        timerEl.classList.toggle("text-rose-600", elapsed > timeLimit);
      }
    }

    cardState.set(part, state);
    refreshOverallProgress();
  }

  function freezeElapsed(part) {
    const state = cardState.get(part) || {};
    if (state.segmentStartedAt) {
      state.elapsedMs = (state.elapsedMs || 0) + (Date.now() - state.segmentStartedAt);
      state.segmentStartedAt = null;
    }
    cardState.set(part, state);
    return state.elapsedMs || 0;
  }

  function getElapsedSeconds(part) {
    const state = cardState.get(part) || {};
    const running = state.segmentStartedAt && !state.timerPaused
      ? Date.now() - state.segmentStartedAt
      : 0;
    return Math.max(0, Math.floor(((state.elapsedMs || 0) + running) / 1000));
  }

  function stopTimerIntervals(part) {
    const state = cardState.get(part) || {};
    state.timerGeneration = (state.timerGeneration || 0) + 1;
    if (state.intervalId) {
      clearInterval(state.intervalId);
      state.intervalId = null;
    }
    if (state.alarmIntervalId) {
      clearInterval(state.alarmIntervalId);
      state.alarmIntervalId = null;
    }
    cardState.set(part, state);
  }

  function stopClientTimer(part) {
    freezeElapsed(part);
    stopTimerIntervals(part);
  }

  function stopAllClientTimers() {
    cards.forEach((card) => stopClientTimer(card.dataset.part));
  }

  function startTimerInterval(card) {
    const part = card.dataset.part;
    stopTimerIntervals(part);

    const timeLimit = Number(card.dataset.timeLimit || 0);
    const timerEl = card.querySelector("[data-timer]");
    const state = cardState.get(part) || {};
    const generation = (state.timerGeneration || 0) + 1;
    state.timerGeneration = generation;
    state.timerPaused = false;
    state.segmentStartedAt = Date.now();
    state.alarmIntervalId = null;

    const intervalId = setInterval(() => {
      const s = cardState.get(part) || {};
      if (s.timerGeneration !== generation || s.timerPaused) return;

      const elapsed = getElapsedSeconds(part);
      const remaining = timeLimit - elapsed;
      timerEl.textContent = formatSeconds(elapsed);
      timerEl.classList.toggle("text-rose-600", remaining < 0);

      if (!s.cuesFired) s.cuesFired = { oneMin: false, thirtySec: false };
      if (!s.cuesFired.oneMin && remaining <= 60 && remaining > 30) {
        s.cuesFired.oneMin = true;
        playBeepSequence(1);
      }
      if (!s.cuesFired.thirtySec && remaining <= 30 && remaining > 0) {
        s.cuesFired.thirtySec = true;
        playBeepSequence(2);
      }
      if (remaining <= 0 && !s.alarmIntervalId) {
        playBeepSequence(2);
        s.alarmIntervalId = setInterval(() => {
          const current = cardState.get(part) || {};
          if (current.timerGeneration !== generation || current.timerPaused) return;
          playBeepSequence(2);
        }, 1000);
      }
      cardState.set(part, s);
    }, 500);

    state.intervalId = intervalId;
    cardState.set(part, state);
  }

  function startClientTimer(card) {
    const part = card.dataset.part;
    const state = cardState.get(part) || {};
    state.elapsedMs = 0;
    state.timerPaused = false;
    state.cuesFired = { oneMin: false, thirtySec: false };
    cardState.set(part, state);
    startTimerInterval(card);
  }

  async function handleRecordClick(card) {
    const part = card.dataset.part;
    if (activeRecordingPart) return;
    setError(card, "");

    const mode = getEffectiveMode();
    const isRealtime = mode === "realtime";

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setError(card, "このブラウザはマイク録音に対応していません。");
      return;
    }

    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      setError(card, "マイクへのアクセスが許可されませんでした。");
      return;
    }

    try {
      const res = await fetch(`/debate/api/sessions/${SESSION_ID}/parts/${part}/start`, {
        method: "POST",
      });
      if (!res.ok) throw new Error("録音開始の記録に失敗しました。");
    } catch (err) {
      setError(card, err.message);
      stream.getTracks().forEach((t) => t.stop());
      return;
    }

    stopAllClientTimers();

    activeRecordingPart = part;
    updateRecordButtonStates();

    const state = cardState.get(part) || {};
    state.recordingMode = mode;
    state.mediaStream = stream;
    state.volumeMeter = setupVolumeMeter(card, stream);
    showLiveMonitor(card);

    if (isRealtime) {
      state.realtimeTranscription = setupRealtimeTranscription(card);
      if (!state.realtimeTranscription) {
        stream.getTracks().forEach((t) => t.stop());
        activeRecordingPart = null;
        updateRecordButtonStates();
        setError(card, "リアルタイム文字起こしを開始できませんでした。ページを再読み込みしてお試しください。");
        return;
      }
      state.recorder = null;
    } else {
      const mimeType = pickMimeType();
      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
      const chunks = [];

      recorder.addEventListener("dataavailable", (e) => {
        if (e.data && e.data.size > 0) chunks.push(e.data);
      });

      recorder.addEventListener("stop", () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunks, { type: mimeType || "audio/webm" });
        window.DebateLocalAudio?.put(SESSION_ID, part, blob, mimeType || "audio/webm");
        uploadAudio(card, blob, mimeType || "audio/webm");
      });

      state.recorder = recorder;
      state.liveCaption = setupLiveCaption(card);
      recorder.start();
    }

    cardState.set(part, state);

    card.dataset.status = "recording";
    renderCard(card);
    startClientTimer(card);
  }

  function pauseRecording(card) {
    const part = card.dataset.part;
    const state = cardState.get(part) || {};
    if (state.timerPaused || card.dataset.status !== "recording") return;

    if (state.recorder) {
      if (state.recorder.state !== "recording") return;
      if (typeof state.recorder.pause !== "function") {
        setError(card, "このブラウザは録音の一時停止に対応していません。");
        return;
      }
      try {
        state.recorder.pause();
      } catch (_) {
        setError(card, "一時停止できませんでした。");
        return;
      }
    }
    state.liveCaption?.pause?.();
    state.realtimeTranscription?.pause?.();
    freezeElapsed(part);
    stopTimerIntervals(part);
    const next = cardState.get(part) || {};
    next.timerPaused = true;
    cardState.set(part, next);
    setError(card, "");
    renderCard(card);
  }

  function resumeRecording(card) {
    const part = card.dataset.part;
    const state = cardState.get(part) || {};
    if (!state.timerPaused || card.dataset.status !== "recording") return;

    if (state.recorder) {
      if (state.recorder.state !== "paused") return;
      try {
        state.recorder.resume();
      } catch (_) {
        setError(card, "録音を再開できませんでした。");
        return;
      }
    }
    state.liveCaption?.resume?.();
    state.realtimeTranscription?.resume?.();
    state.timerPaused = false;
    cardState.set(part, state);
    startTimerInterval(card);
    setError(card, "");
    renderCard(card);
  }

  function handlePauseClick(card) {
    const state = cardState.get(card.dataset.part) || {};
    if (state.timerPaused) resumeRecording(card);
    else pauseRecording(card);
  }

  function cleanupRecordingResources(card, part) {
    const state = cardState.get(part) || {};
    stopClientTimer(part);
    if (state.volumeMeter) {
      state.volumeMeter.stop();
      state.volumeMeter = null;
    }
    if (state.mediaStream && !state.recorder) {
      state.mediaStream.getTracks().forEach((t) => t.stop());
      state.mediaStream = null;
    }
    if (state.liveCaption) {
      state.liveCaption.stop();
      state.liveCaption = null;
    }
    if (state.realtimeTranscription) {
      state.realtimeTranscription.stop();
      state.realtimeTranscription = null;
    }
    cardState.set(part, state);
    hideLiveMonitor(card);
  }

  async function submitRealtimeTranscript(card, transcriptRaw, elapsedSec) {
    const part = card.dataset.part;

    try {
      const res = await fetch(`/debate/api/sessions/${SESSION_ID}/parts/${part}/transcript`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ transcript_raw: transcriptRaw, elapsed_sec: elapsedSec }),
      });
      const data = await res.json();

      activeRecordingPart = null;
      updateRecordButtonStates();

      if (!res.ok) {
        card.dataset.status = "needs_review";
        renderCard(card);
        setError(card, data.error || "文字起こしの保存に失敗しました。");
        return;
      }

      card.dataset.status = data.status || "needs_review";
      card.dataset.elapsed = data.elapsed_sec ?? "";
      if (data.end_time) card.dataset.endTime = data.end_time;
      setError(card, data.transcript_error || "");
      renderCard(card);
    } catch (err) {
      activeRecordingPart = null;
      updateRecordButtonStates();
      card.dataset.status = "needs_review";
      renderCard(card);
      setError(card, "文字起こしの保存に失敗しました。ネットワークをご確認のうえ、やり直してください。");
    }
  }

  function handleStopClick(card) {
    const part = card.dataset.part;
    const state = cardState.get(part) || {};
    const mode = state.recordingMode || getEffectiveMode();
    const elapsedSec = getElapsedSeconds(part);
    state.speakingElapsedSec = elapsedSec;
    cardState.set(part, state);

    if (mode === "realtime") {
      if (!state.realtimeTranscription) return;

      const transcriptRaw = state.realtimeTranscription.getTranscript();
      cleanupRecordingResources(card, part);

      activeRecordingPart = null;
      updateRecordButtonStates();

      card.dataset.status = "transcribing";
      card.dataset.endTime = new Date().toISOString();
      renderCard(card);

      submitRealtimeTranscript(card, transcriptRaw, elapsedSec);
      return;
    }

    if (!state.recorder || state.recorder.state === "inactive") return;

    cleanupRecordingResources(card, part);

    activeRecordingPart = null;
    updateRecordButtonStates();

    card.dataset.status = "transcribing";
    card.dataset.endTime = new Date().toISOString();
    renderCard(card);
    state.recorder.stop();
  }

  // ── 文字起こし完了待ちのポーリング ──────────────────────────
  const STUCK_TRANSCRIBE_MS = 90 * 1000;
  const UPLOAD_TIMEOUT_MS = 120 * 1000;

  function isTranscriptionStuck(endTimeIso) {
    if (!endTimeIso) return false;
    const endedAt = new Date(endTimeIso).getTime();
    if (Number.isNaN(endedAt)) return false;
    return Date.now() - endedAt > STUCK_TRANSCRIBE_MS;
  }

  function handleStuckTranscription(card) {
    // サーバー側は "transcribing" のままの可能性があるが、
    // レビュー画面へは進めるようにして手動での再試行・入力を可能にする。
    card.dataset.status = "needs_review";
    renderCard(card);
    setError(
      card,
      "文字起こしの処理に時間がかかっています。「文字起こしを確認」から手動入力するか、再試行できます。"
    );
  }

  function startStatusPolling(card) {
    const part = card.dataset.part;
    const state = cardState.get(part) || {};
    if (state.pollIntervalId) return;

    state.pollIntervalId = setInterval(async () => {
      try {
        const res = await fetch(`/debate/api/sessions/${SESSION_ID}/parts/${part}`);
        if (!res.ok) return;
        const data = await res.json();
        if (!data.status) return;

        if (data.status === "transcribing") {
          if (isTranscriptionStuck(data.end_time)) {
            stopStatusPolling(part);
            handleStuckTranscription(card);
          }
          return;
        }

        if (data.status !== card.dataset.status) {
          card.dataset.status = data.status;
          card.dataset.elapsed = data.elapsed_sec ?? "";
          if (data.end_time) card.dataset.endTime = data.end_time;
          if (data.transcript_error) card.dataset.transcriptError = data.transcript_error;
          renderCard(card);
        }

        stopStatusPolling(part);
        if (data.transcript_error) {
          setError(
            card,
            `文字起こしに失敗しました（${data.transcript_error}）。「文字起こしを確認」から手動入力するか再試行できます。`
          );
        } else {
          setError(card, "");
        }
      } catch (_) {
        // ネットワーク不調時は次回のポーリングで再試行する
      }
    }, 3000);
    cardState.set(part, state);
  }

  function stopStatusPolling(part) {
    const state = cardState.get(part) || {};
    if (state.pollIntervalId) {
      clearInterval(state.pollIntervalId);
      state.pollIntervalId = null;
    }
    cardState.set(part, state);
  }

  async function uploadAudio(card, blob, mimeType) {
    const part = card.dataset.part;
    const formData = new FormData();
    formData.append("audio", blob, `${part}.${extensionFor(mimeType)}`);
    const elapsedSec = (cardState.get(part) || {}).speakingElapsedSec;
    if (elapsedSec != null) formData.append("elapsed_sec", String(elapsedSec));

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), UPLOAD_TIMEOUT_MS);

    try {
      const res = await fetch(`/debate/api/sessions/${SESSION_ID}/parts/${part}/audio`, {
        method: "POST",
        body: formData,
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      const data = await res.json();

      activeRecordingPart = null;
      updateRecordButtonStates();

      if (!res.ok) {
        const partData = data.part || data;
        card.dataset.status = partData.status || "needs_review";
        card.dataset.elapsed = partData.elapsed_sec ?? "";
        renderCard(card);
        setError(card, data.error || "保存に失敗しました。文字起こし確認画面から手動で入力できます。");
        return;
      }

      card.dataset.status = data.status || "transcribing";
      card.dataset.elapsed = data.elapsed_sec ?? "";
      if (data.end_time) card.dataset.endTime = data.end_time;
      setError(card, "");
      renderCard(card);

      if (card.dataset.status === "transcribing") {
        startStatusPolling(card);
      }
    } catch (err) {
      clearTimeout(timeoutId);
      activeRecordingPart = null;
      updateRecordButtonStates();
      card.dataset.status = "needs_review";
      renderCard(card);
      const msg =
        err.name === "AbortError"
          ? "保存がタイムアウトしました。ネットワークをご確認のうえ、やり直してください。"
          : "保存に失敗しました。ネットワークをご確認のうえ、やり直してください。";
      setError(card, msg);
    }
  }

  async function handleSavePartClick(card) {
    const part = card.dataset.part;
    const btn = card.querySelector(".btn-save");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "保存中...";
    }
    try {
      const res = await fetch(`/debate/api/sessions/${SESSION_ID}/parts/${part}/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "保存に失敗しました。");
      showPartSaveMsg(card, "保存しました");
      showSaveToast(`${part} パートを保存しました。同じ端末のトップ画面から再開できます。`);
    } catch (err) {
      setError(card, err.message);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = "保存";
      }
    }
  }

  async function handleSaveExitClick() {
    if (activeRecordingPart) {
      showSaveToast("録音中（一時停止中を含む）は保存できません。停止してからお試しください。");
      return;
    }
    saveExitBtn.disabled = true;
    saveExitBtn.textContent = "保存中...";
    try {
      const res = await fetch(`/debate/api/sessions/${SESSION_ID}/checkpoint`, {
        method: "POST",
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "保存に失敗しました。");
      window.location.href = "/debate/";
    } catch (err) {
      showSaveToast(err.message);
      saveExitBtn.disabled = false;
      saveExitBtn.textContent = "保存して中断";
    }
  }

  async function handleResetClick(card) {
    const part = card.dataset.part;
    if (!window.confirm(`${part} パートの録音・文字起こしをリセットしてやり直しますか？`)) return;

    try {
      const res = await fetch(`/debate/api/sessions/${SESSION_ID}/parts/${part}/reset`, {
        method: "POST",
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "リセットに失敗しました。");

      window.DebateLocalAudio?.remove(SESSION_ID, part);
      card.dataset.status = data.status;
      card.dataset.elapsed = "";
      setError(card, "");
      renderCard(card);
    } catch (err) {
      setError(card, err.message);
    }
  }

  function handleReviewClick(card) {
    const part = card.dataset.part;
    window.location.href = `/debate/session/${SESSION_ID}/parts/${part}/review`;
  }

  async function resetStaleRecording(card) {
    const part = card.dataset.part;
    try {
      const res = await fetch(`/debate/api/sessions/${SESSION_ID}/parts/${part}/reset`, {
        method: "POST",
      });
      const data = await res.json();
      if (res.ok) {
        window.DebateLocalAudio?.remove(SESSION_ID, part);
        card.dataset.status = data.status;
        card.dataset.elapsed = "";
        renderCard(card);
        staleBanner.classList.remove("hidden");
      }
    } catch (err) {
      // 通信できなくても致命的ではないため無視する
    }
  }

  cards.forEach((card) => {
    card.querySelector(".btn-record").addEventListener("click", () => handleRecordClick(card));
    card.querySelector(".btn-pause")?.addEventListener("click", () => handlePauseClick(card));
    card.querySelector(".btn-stop").addEventListener("click", () => handleStopClick(card));
    card.querySelector(".btn-reset").addEventListener("click", () => handleResetClick(card));
    card.querySelector(".btn-review").addEventListener("click", () => handleReviewClick(card));
    card.querySelector(".btn-save")?.addEventListener("click", () => handleSavePartClick(card));

    if (card.dataset.status === "recording") {
      // ページ再読み込みでMediaRecorderの実体は失われているため、サーバー側もリセットする
      resetStaleRecording(card);
    } else {
      renderCard(card);
      if (card.dataset.status === "transcribing") {
        if (isTranscriptionStuck(card.dataset.endTime)) {
          handleStuckTranscription(card);
        } else {
          // ページ再読み込み後もバックグラウンドの文字起こし完了をポーリングで確認し続ける
          startStatusPolling(card);
        }
      } else if (card.dataset.transcriptError) {
        // 前回アクセス時に文字起こしが失敗していた場合、再読み込み後も分かるようにする
        setError(
          card,
          `文字起こしに失敗しました（${card.dataset.transcriptError}）。「文字起こしを確認」から手動入力するか再試行できます。`
        );
      }
    }
  });

  // 録音中にページを閉じる／再読み込みすると音声が失われるため注意喚起する
  // （録音以外の操作は逐次サーバーへ保存されるため、閉じても続きから再開できる）
  window.addEventListener("beforeunload", (event) => {
    if (activeRecordingPart) {
      event.preventDefault();
      event.returnValue = "";
    }
  });

  saveExitBtn?.addEventListener("click", handleSaveExitClick);

  // ── ジャッジ実行（6パート確定後に表示されるボタン） ─────────────
  const runJudgeBtn = document.getElementById("run-judge-btn");
  const runJudgeError = document.getElementById("run-judge-error");

  runJudgeBtn?.addEventListener("click", async () => {
    runJudgeBtn.disabled = true;
    runJudgeBtn.textContent = "ジャッジを開始しています...";
    if (runJudgeError) runJudgeError.classList.add("hidden");

    try {
      const res = await fetch(`/debate/api/sessions/${SESSION_ID}/judge`, { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "ジャッジの開始に失敗しました。");
      window.location.href = `/debate/session/${SESSION_ID}/judge`;
    } catch (err) {
      runJudgeBtn.disabled = false;
      runJudgeBtn.textContent = "ジャッジを実行";
      if (runJudgeError) {
        runJudgeError.textContent = err.message;
        runJudgeError.classList.remove("hidden");
      }
    }
  });

  refreshOverallProgress();
})();
