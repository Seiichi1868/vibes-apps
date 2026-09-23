(() => {
  const SESSION_ID = window.CONJUGATE_SESSION_ID;
  const ASR_ENGINE = window.CONJUGATE_ASR_ENGINE || "whisper";
  const TENSE_LABELS = window.CONJUGATE_TENSE_LABELS || {};
  const CATEGORY_LABELS = window.CONJUGATE_CATEGORY_LABELS || {};
  const PERSON_LABELS = window.CONJUGATE_PERSON_LABELS || { tu: "tú", el_ella_usted: "él/ella/usted" };
  const EL_HINT = window.CONJUGATE_EL_HINT || "";
  const MIME_CANDIDATES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg"];

  const progressLabel = document.getElementById("progress-label");
  const micErrorBanner = document.getElementById("mic-error-banner");
  const categoryPill = document.getElementById("category-pill");
  const personPill = document.getElementById("person-pill");
  const tenseTargetPill = document.getElementById("tense-target-pill");
  const verbHeaderBlock = document.getElementById("verb-header-block");
  const gustarHeaderBlock = document.getElementById("gustar-header-block");
  const infinitiveTitle = document.getElementById("infinitive-title");
  const meaningJa = document.getElementById("meaning-ja");
  const verbNote = document.getElementById("verb-note");
  const personHint = document.getElementById("person-hint");
  const gustarTopic = document.getElementById("gustar-topic");
  const gustarHint = document.getElementById("gustar-hint");
  const personHintGustar = document.getElementById("person-hint-gustar");
  const sentenceList = document.getElementById("sentence-list");
  const targetStepper = document.getElementById("target-stepper");
  const recordBtn = document.getElementById("record-btn");
  const recordControl = document.getElementById("record-control");
  const recordLabel = recordBtn ? recordBtn.querySelector(".vsc-record-label") : null;
  const stopBtn = document.getElementById("stop-btn");
  const recordingStatus = document.getElementById("recording-status");
  const feedbackBox = document.getElementById("feedback-box");
  const nextBtn = document.getElementById("next-btn");
  const volumeMeter = document.getElementById("volume-meter");
  const volumeBar = document.getElementById("volume-bar");
  const typeAnswerBlock = document.getElementById("type-answer-block");
  const typeForm = document.getElementById("type-form");
  const typeInput = document.getElementById("type-input");
  const typeSubmitBtn = document.getElementById("type-submit-btn");

  let session = null;
  let questionIndex = 0;
  let targetIndex = 0;
  let elHintShown = false;
  let mediaRecorder = null;
  let mediaStream = null;
  let speechRecognizer = null;
  let abandonRecording = false;

  function go(url) {
    if (window.vscNavigate) window.vscNavigate(url);
    else window.location.href = url;
  }

  function setRecordState(state) {
    if (!recordControl) return;
    recordControl.classList.toggle("is-recording", state === "recording");
    recordControl.classList.toggle("is-complete", state === "complete");
    if (recordBtn) recordBtn.classList.toggle("is-recording", state === "recording");
    if (recordLabel) {
      recordLabel.textContent = state === "recording" ? "録音中 · タップで終了" : "発話して録音";
    }
  }

  function wait(ms) {
    return new Promise((resolve) => window.setTimeout(resolve, ms));
  }

  async function finishRecordingThenSubmit(payload) {
    setRecordState("complete");
    await wait(280);
    await submitAnswer(payload);
  }

  function useWebSpeech() {
    return ASR_ENGINE === "web_speech" && (window.SpeechRecognition || window.webkitSpeechRecognition);
  }

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
    return "webm";
  }

  async function loadSession() {
    const res = await fetch(`/conjugate/api/sessions/${SESSION_ID}`);
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || "セッションの取得に失敗しました。");
    session = data.session;
  }

  function currentQuestion() {
    return session.questions[questionIndex];
  }

  function currentTarget() {
    const q = currentQuestion();
    return q.targets[targetIndex];
  }

  function updateProgress() {
    progressLabel.textContent = `${questionIndex + 1}/${session.questions.length}問`;
  }

  function renderTargetStepper(q) {
    targetStepper.innerHTML = "";
    if (q.targets.length <= 1) return;
    q.targets.forEach((t, i) => {
      const dot = document.createElement("span");
      const label = q.kind === "gustar" ? "gustar" : (TENSE_LABELS[t] || t);
      dot.textContent = label;
      dot.className = `vsc-step-dot ${i === targetIndex ? "vsc-step-dot-active" : i < targetIndex ? "vsc-step-dot-done" : ""}`;
      targetStepper.appendChild(dot);
    });
  }

  function currentPerson() {
    const q = currentQuestion();
    return q.person === "el_ella_usted" ? "el_ella_usted" : "tu";
  }

  function showElHintIfNeeded(targetEl) {
    if (!targetEl || !EL_HINT) return;
    if (currentPerson() !== "el_ella_usted") {
      targetEl.classList.add("hidden");
      targetEl.textContent = "";
      return;
    }
    if (elHintShown) {
      targetEl.classList.add("hidden");
      return;
    }
    targetEl.textContent = EL_HINT;
    targetEl.classList.remove("hidden");
    elHintShown = true;
  }

  function renderQuestion() {
    const q = currentQuestion();
    feedbackBox.classList.add("hidden");
    feedbackBox.innerHTML = "";
    nextBtn.classList.add("hidden");
    recordBtn.classList.remove("hidden");
    stopBtn.classList.add("hidden");
    setRecordState("idle");
    recordingStatus.textContent = "";
    typeAnswerBlock.classList.remove("hidden");
    typeInput.value = "";
    typeInput.disabled = false;
    typeSubmitBtn.disabled = false;
    updateProgress();
    renderTargetStepper(q);

    if (q.kind === "gustar") {
      verbHeaderBlock.classList.add("hidden");
      gustarHeaderBlock.classList.remove("hidden");
      gustarTopic.textContent = q.topic_ja;
      categoryPill.textContent = "特殊構文編";
      if (personPill) {
        personPill.textContent = PERSON_LABELS[currentPerson()] || currentPerson();
        personPill.classList.toggle("is-el", currentPerson() === "el_ella_usted");
      }
      tenseTargetPill.textContent = "gustar";
      if (gustarHint) {
        gustarHint.textContent = currentPerson() === "el_ella_usted"
          ? "gustarは活用しません。変わるのは me→le だけです。"
          : "gustarは活用しません。変わるのは me→te だけです。";
      }
      showElHintIfNeeded(personHintGustar);
      if (personHint) personHint.classList.add("hidden");

      sentenceList.innerHTML = "";
      const li = document.createElement("li");
      li.className = "vsc-form-item vsc-form-item-target";
      li.innerHTML = `<span class="vsc-form-bullet"></span><span>${q.yo_sentence}</span>`;
      sentenceList.appendChild(li);
    } else {
      verbHeaderBlock.classList.remove("hidden");
      gustarHeaderBlock.classList.add("hidden");
      infinitiveTitle.textContent = q.infinitive.toUpperCase();
      meaningJa.textContent = q.meaning_ja;
      if (q.note) {
        verbNote.textContent = `💡 ${q.note}`;
        verbNote.classList.remove("hidden");
      } else {
        verbNote.classList.add("hidden");
      }
      showElHintIfNeeded(personHint);
      if (personHintGustar) personHintGustar.classList.add("hidden");
      categoryPill.textContent = CATEGORY_LABELS[q.category] || q.category;
      if (personPill) {
        personPill.textContent = PERSON_LABELS[currentPerson()] || currentPerson();
        personPill.classList.toggle("is-el", currentPerson() === "el_ella_usted");
      }

      const target = currentTarget();
      tenseTargetPill.textContent = `→ ${TENSE_LABELS[target] || target} に変換`;

      sentenceList.innerHTML = "";
      Object.keys(q.forms).forEach((tense) => {
        const li = document.createElement("li");
        const isTarget = q.targets.includes(tense);
        const isCurrentTarget = tense === target;
        li.className = `vsc-form-item ${isTarget ? "vsc-form-item-target" : ""} ${isCurrentTarget ? "vsc-form-item-active" : ""}`;
        const badge = isTarget ? `<span class="vsc-mini-badge">${isCurrentTarget ? "今回の対象" : "対象"}</span>` : "";
        li.innerHTML = `<span class="vsc-form-bullet"></span><span>${q.forms[tense].yo}</span>${badge}`;
        sentenceList.appendChild(li);
      });
    }
  }

  function setMicError(message) {
    if (!message) {
      micErrorBanner.classList.add("hidden");
      micErrorBanner.textContent = "";
      return;
    }
    micErrorBanner.textContent = message;
    micErrorBanner.classList.remove("hidden");
  }

  function levelInfo(level) {
    const map = {
      correct: { label: "正解！", cls: "vsc-feedback-correct" },
      pronoun_error: { label: "惜しい（代名詞ミス）", cls: "vsc-feedback-warn" },
      conjugation_error: { label: "活用形が違います", cls: "vsc-feedback-warn" },
      way_off: { label: "全く違います", cls: "vsc-feedback-bad" },
    };
    return map[level] || map.way_off;
  }

  function showFeedback(result) {
    const info = levelInfo(result.level);
    feedbackBox.className = `mt-4 vsc-feedback ${info.cls}`;
    feedbackBox.innerHTML = `
      <div class="font-bold">${info.label}</div>
      <div class="text-sm mt-1">${result.message}</div>
      ${result.newly_mastered ? '<div class="vsc-mastered-toast">習得バッジを獲得！</div>' : ""}
      <div class="text-xs mt-2" style="color: var(--text-secondary);">${result.transcript_source === "typed" ? "入力" : "認識結果"}: 「${result.transcript || "（空）"}」</div>
      ${result.counts_toward_mastery === false ? '<div class="text-xs mt-1" style="color: var(--text-secondary);">発音の読み取り違いは、間違いの累計と連続正解には入れません。</div>' : ""}
    `;
    feedbackBox.classList.remove("hidden");
    if (window.vscCelebrateFromResult) window.vscCelebrateFromResult(result);
  }

  function lockAnswerControls() {
    recordBtn.classList.add("hidden");
    stopBtn.classList.add("hidden");
    typeAnswerBlock.classList.add("hidden");
    typeInput.disabled = true;
    typeSubmitBtn.disabled = true;
  }

  async function submitAnswer({ audioBlob, mimeType, transcript, answerMode, alternatives }) {
    const q = currentQuestion();
    const target = currentTarget();
    const url = `/conjugate/api/sessions/${SESSION_ID}/questions/${q.question_id}/targets/${target}/answer`;

    const formData = new FormData();
    if (audioBlob) {
      formData.append("audio", audioBlob, `answer.${extensionFor(mimeType || "audio/webm")}`);
    } else {
      formData.append("transcript", transcript || "");
      if (answerMode) formData.append("answer_mode", answerMode);
      if (alternatives && alternatives.length > 1) {
        formData.append("alternatives", JSON.stringify(alternatives.slice(0, 5)));
      }
    }

    recordingStatus.textContent = "判定中...";
    const res = await fetch(url, { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || "採点に失敗しました。");
    recordingStatus.textContent = "";
    showFeedback(data.result);

    lockAnswerControls();
    nextBtn.classList.remove("hidden");
    nextBtn.textContent = isLastTargetOfQuestion() ? (isLastQuestion() ? "結果を見る →" : "次の問題へ →") : "次の文型へ →";
  }

  function isLastTargetOfQuestion() {
    const q = currentQuestion();
    return targetIndex >= q.targets.length - 1;
  }

  function isLastQuestion() {
    return questionIndex >= session.questions.length - 1;
  }

  async function handleNext() {
    if (!isLastTargetOfQuestion()) {
      targetIndex += 1;
      renderQuestion();
      return;
    }
    if (!isLastQuestion()) {
      questionIndex += 1;
      targetIndex = 0;
      renderQuestion();
      return;
    }
    await finishSession();
  }

  async function finishSession() {
    nextBtn.disabled = true;
    nextBtn.textContent = "集計中...";
    try {
      await fetch(`/conjugate/api/sessions/${SESSION_ID}/finish`, { method: "POST" });
    } catch (_) {
      // ネットワーク不調でもサマリ画面側で再計算されるため続行する
    }
    go(`/conjugate/session/${SESSION_ID}/summary`);
  }

  function setupVolumeMeter(stream) {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return null;
    try {
      const ctx = new AudioCtx();
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
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
        volumeBar.style.width = `${Math.round(Math.min(1, rms * 4) * 100)}%`;
        rafId = requestAnimationFrame(tick);
      };
      tick();

      return {
        stop() {
          if (rafId) cancelAnimationFrame(rafId);
          try { source.disconnect(); } catch (_) { /* ignore */ }
          try { analyser.disconnect(); } catch (_) { /* ignore */ }
          try { ctx.close(); } catch (_) { /* ignore */ }
          volumeBar.style.width = "0%";
        },
      };
    } catch (_) {
      return null;
    }
  }

  async function startRecordingWithMediaRecorder() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setMicError("このブラウザはマイク録音に対応していません。別のブラウザでお試しください。");
      return;
    }
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (_) {
      setMicError("マイクへのアクセスが許可されませんでした。ブラウザの設定を確認してください。");
      return;
    }
    setMicError("");
    mediaStream = stream;
    const mimeType = pickMimeType();
    mediaRecorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
    const chunks = [];
    const volMeter = setupVolumeMeter(stream);
    volumeMeter.classList.remove("hidden");

    mediaRecorder.addEventListener("dataavailable", (e) => {
      if (e.data && e.data.size > 0) chunks.push(e.data);
    });
    mediaRecorder.addEventListener("stop", async () => {
      stream.getTracks().forEach((t) => t.stop());
      if (volMeter) volMeter.stop();
      volumeMeter.classList.add("hidden");
      if (abandonRecording) {
        abandonRecording = false;
        setRecordState("idle");
        typeInput.disabled = false;
        typeSubmitBtn.disabled = false;
        recordingStatus.textContent = "";
        return;
      }
      const blob = new Blob(chunks, { type: mimeType || "audio/webm" });
      try {
        await finishRecordingThenSubmit({ audioBlob: blob, mimeType: mimeType || "audio/webm" });
      } catch (err) {
        recordingStatus.textContent = "";
        setMicError(err.message);
        setRecordState("idle");
        recordBtn.classList.remove("hidden");
        typeInput.disabled = false;
        typeSubmitBtn.disabled = false;
      }
    });

    setRecordState("recording");
    recordBtn.classList.remove("hidden");
    stopBtn.classList.add("hidden");
    typeInput.disabled = true;
    typeSubmitBtn.disabled = true;
    recordingStatus.textContent = "録音中... もう一度タップすると終了します。";
    mediaRecorder.start();
  }

  function stopRecordingWithMediaRecorder() {
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      recordingStatus.textContent = "アップロード中...";
      mediaRecorder.stop();
    }
  }

  function startRecordingWithWebSpeech() {
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    speechRecognizer = new Recognition();
    speechRecognizer.lang = "es-ES";
    speechRecognizer.interimResults = false;
    speechRecognizer.maxAlternatives = 5;
    speechRecognizer.continuous = false;

    setRecordState("recording");
    recordBtn.classList.remove("hidden");
    stopBtn.classList.add("hidden");
    typeInput.disabled = true;
    typeSubmitBtn.disabled = true;
    recordingStatus.textContent = "録音中（低遅延モード）... 発話が終わると自動で判定します。";

    let speechGotResult = false;
    speechRecognizer.addEventListener("result", async (event) => {
      speechGotResult = true;
      const recognition = event.results[0];
      const alternatives = [];
      for (let i = 0; i < recognition.length; i += 1) {
        const text = recognition[i].transcript;
        if (text) alternatives.push(text);
      }
      const transcript = alternatives[0] || "";
      stopBtn.classList.add("hidden");
      try {
        await finishRecordingThenSubmit({ transcript, alternatives });
      } catch (err) {
        recordingStatus.textContent = "";
        setMicError(err.message);
        setRecordState("idle");
        recordBtn.classList.remove("hidden");
        typeInput.disabled = false;
        typeSubmitBtn.disabled = false;
      }
    });
    speechRecognizer.addEventListener("error", () => {
      recordingStatus.textContent = "";
      stopBtn.classList.add("hidden");
      setRecordState("idle");
      recordBtn.classList.remove("hidden");
      typeInput.disabled = false;
      typeSubmitBtn.disabled = false;
      setMicError("音声認識でエラーが発生しました。もう一度お試しください。");
    });
    speechRecognizer.addEventListener("end", () => {
      stopBtn.classList.add("hidden");
      if (!speechGotResult) {
        setRecordState("idle");
        recordBtn.classList.remove("hidden");
        typeInput.disabled = false;
        typeSubmitBtn.disabled = false;
        if (!recordingStatus.textContent) {
          recordingStatus.textContent = "";
        }
      }
    });

    try {
      speechRecognizer.start();
    } catch (_) {
      setMicError("音声認識を開始できませんでした。");
      setRecordState("idle");
      recordBtn.classList.remove("hidden");
      stopBtn.classList.add("hidden");
      typeInput.disabled = false;
      typeSubmitBtn.disabled = false;
    }
  }

  function handleRecordClick() {
    if (recordControl && recordControl.classList.contains("is-recording")) {
      handleStopClick();
      return;
    }
    if (recordControl && recordControl.classList.contains("is-complete")) return;
    setMicError("");
    feedbackBox.classList.add("hidden");
    abandonRecording = false;
    if (useWebSpeech()) {
      startRecordingWithWebSpeech();
    } else {
      startRecordingWithMediaRecorder();
    }
  }

  function handleStopClick() {
    if (useWebSpeech() && speechRecognizer) {
      speechRecognizer.stop();
    } else {
      stopRecordingWithMediaRecorder();
    }
  }

  async function handleTypeSubmit(event) {
    event.preventDefault();
    const transcript = (typeInput.value || "").trim();
    if (!transcript) {
      setMicError("スペルをタイプしてから解答してください。");
      typeInput.focus();
      return;
    }
    setMicError("");
    feedbackBox.classList.add("hidden");
    recordBtn.classList.add("hidden");
    typeSubmitBtn.disabled = true;
    typeInput.disabled = true;
    try {
      await submitAnswer({ transcript, answerMode: "typed" });
    } catch (err) {
      recordingStatus.textContent = "";
      setMicError(err.message);
      recordBtn.classList.remove("hidden");
      typeSubmitBtn.disabled = false;
      typeInput.disabled = false;
    }
  }

  recordBtn.addEventListener("click", handleRecordClick);
  stopBtn.addEventListener("click", handleStopClick);
  typeForm.addEventListener("submit", handleTypeSubmit);
  nextBtn.addEventListener("click", handleNext);

  const tenseGuideBtn = document.getElementById("tense-guide-btn");
  const tenseGuideModal = document.getElementById("tense-guide-modal");
  const tenseGuideTabs = tenseGuideModal ? tenseGuideModal.querySelectorAll("[data-tense-guide]") : [];
  const tenseGuidePanels = tenseGuideModal ? tenseGuideModal.querySelectorAll("[data-tense-guide-panel]") : [];

  function preferredGuideTense() {
    try {
      const q = currentQuestion();
      if (!q || q.kind === "gustar") return "present";
      const target = currentTarget();
      if ([...tenseGuideTabs].some((tab) => tab.dataset.tenseGuide === target)) return target;
    } catch (_) { /* session not ready */ }
    return "present";
  }

  function showGuideTense(tenseId) {
    const chosen = [...tenseGuideTabs].some((tab) => tab.dataset.tenseGuide === tenseId)
      ? tenseId
      : (tenseGuideTabs[0] ? tenseGuideTabs[0].dataset.tenseGuide : "");
    tenseGuideTabs.forEach((tab) => {
      const on = tab.dataset.tenseGuide === chosen;
      tab.classList.toggle("is-active", on);
      tab.setAttribute("aria-selected", on ? "true" : "false");
    });
    tenseGuidePanels.forEach((panel) => {
      panel.classList.toggle("hidden", panel.dataset.tenseGuidePanel !== chosen);
    });
  }

  function openTenseGuide() {
    if (!tenseGuideModal) return;
    showGuideTense(preferredGuideTense());
    tenseGuideModal.classList.remove("hidden");
    document.body.classList.add("vsc-modal-open");
    if (tenseGuideBtn) tenseGuideBtn.setAttribute("aria-expanded", "true");
  }

  function closeTenseGuide() {
    if (!tenseGuideModal) return;
    tenseGuideModal.classList.add("hidden");
    document.body.classList.remove("vsc-modal-open");
    if (tenseGuideBtn) tenseGuideBtn.setAttribute("aria-expanded", "false");
  }

  if (tenseGuideBtn) {
    tenseGuideBtn.setAttribute("aria-expanded", "false");
    tenseGuideBtn.addEventListener("click", () => {
      if (tenseGuideModal && !tenseGuideModal.classList.contains("hidden")) closeTenseGuide();
      else openTenseGuide();
    });
  }
  if (tenseGuideModal) {
    tenseGuideModal.querySelectorAll("[data-close-tense-guide]").forEach((el) => {
      el.addEventListener("click", closeTenseGuide);
    });
    tenseGuideTabs.forEach((tab) => {
      tab.addEventListener("click", () => showGuideTense(tab.dataset.tenseGuide));
    });
  }
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && tenseGuideModal && !tenseGuideModal.classList.contains("hidden")) {
      event.preventDefault();
      closeTenseGuide();
    }
  });

  (async () => {
    try {
      await loadSession();
      if (!session.questions.length) throw new Error("出題できる問題がありません。");
      if (session.status === "done") {
        go(`/conjugate/session/${SESSION_ID}/summary`);
        return;
      }
      renderQuestion();
    } catch (err) {
      setMicError(err.message);
    }
  })();

  window.addEventListener("beforeunload", (event) => {
    if (mediaRecorder && mediaRecorder.state === "recording") {
      event.preventDefault();
      event.returnValue = "";
    }
  });

  function abandonActiveRecording() {
    if (!recordControl || !recordControl.classList.contains("is-recording")) {
      setRecordState("idle");
      return;
    }
    abandonRecording = true;
    if (useWebSpeech() && speechRecognizer) {
      try {
        if (speechRecognizer.abort) speechRecognizer.abort();
        else speechRecognizer.stop();
      } catch (_) { /* ignore */ }
      setRecordState("idle");
      typeInput.disabled = false;
      typeSubmitBtn.disabled = false;
      recordingStatus.textContent = "";
      return;
    }
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      try { mediaRecorder.stop(); } catch (_) { /* ignore */ }
      return;
    }
    setRecordState("idle");
  }

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) abandonActiveRecording();
  });
  window.addEventListener("pagehide", abandonActiveRecording);
})();
