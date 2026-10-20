(() => {
  const SESSION_ID = window.DEBATE_SESSION_ID;
  const PART = window.DEBATE_PART;

  const textarea = document.getElementById("transcript-edited");
  const confirmBtn = document.getElementById("confirm-btn");
  const redoBtn = document.getElementById("redo-btn");
  const retranscribeBtn = document.getElementById("retranscribe-btn");
  const localReuploadBtn = document.getElementById("local-reupload-btn");
  const transcribingBanner = document.getElementById("transcribing-banner");
  const transcriptErrorNote = document.getElementById("transcript-error-note");
  const errorBox = document.getElementById("review-error");
  const browserNote = document.getElementById("browser-fallback-note");

  function showBrowserNote(show) {
    browserNote?.classList.toggle("hidden", !show);
  }

  function applyTranscript(data) {
    const source = data.transcript_source || "";
    window.DEBATE_TRANSCRIPT_SOURCE = source;
    if (data.transcript_browser) window.DEBATE_TRANSCRIPT_BROWSER = data.transcript_browser;
    if (data.audio_url) {
      window.DEBATE_AUDIO_URL = data.audio_url;
      if (retranscribeBtn) retranscribeBtn.classList.remove("hidden");
    }
    const next = data.transcript_edited || data.transcript_raw || "";
    if (next || source === "whisper") textarea.value = next;
    showBrowserNote(source === "browser");
  }

  let pollTimer = null;

  function showError(message) {
    errorBox.textContent = message;
    errorBox.classList.remove("hidden");
  }

  function hideError() {
    errorBox.classList.add("hidden");
    errorBox.textContent = "";
  }

  function setProcessingUI(isProcessing) {
    if (transcribingBanner) transcribingBanner.classList.toggle("hidden", !isProcessing);
    confirmBtn.disabled = isProcessing;
    if (retranscribeBtn) retranscribeBtn.disabled = isProcessing;
    if (localReuploadBtn) localReuploadBtn.disabled = isProcessing;
    textarea.disabled = isProcessing;
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  async function pollUntilDone() {
    try {
      const res = await fetch(`/debate/api/sessions/${SESSION_ID}/parts/${PART}`);
      if (!res.ok) return;
      const data = await res.json();
      if (data.status === "transcribing") return;

      stopPolling();
      setProcessingUI(false);
      if (retranscribeBtn) retranscribeBtn.textContent = "文字起こしを再試行";

      applyTranscript(data);
      if (data.transcript_error) {
        showError(`文字起こしに失敗しました: ${data.transcript_error}`);
        if (transcriptErrorNote) {
          transcriptErrorNote.textContent = `前回の文字起こしでエラーが発生しました: ${data.transcript_error}`;
          transcriptErrorNote.classList.remove("hidden");
        }
      } else {
        hideError();
        if (transcriptErrorNote) transcriptErrorNote.classList.add("hidden");
      }
    } catch (_) {
      // ネットワーク不調時は次回のポーリングで再試行する
    }
  }

  function startPolling() {
    setProcessingUI(true);
    stopPolling();
    pollTimer = setInterval(pollUntilDone, 3000);
  }

  if (window.DEBATE_PART_STATUS === "transcribing") {
    startPolling();
  }

  if (!window.DEBATE_AUDIO_URL && localReuploadBtn) {
    window.DebateLocalAudio?.get(SESSION_ID, PART).then((local) => {
      if (local?.blob && local.blob.size > 0) localReuploadBtn.hidden = false;
    });
  }

  localReuploadBtn?.addEventListener("click", async () => {
    localReuploadBtn.disabled = true;
    localReuploadBtn.textContent = "保存して文字起こし中...";
    hideError();
    try {
      const local = await window.DebateLocalAudio?.get(SESSION_ID, PART);
      if (!local?.blob || local.blob.size <= 0) {
        throw new Error("この端末に録音が見つかりません。録音からやり直してください。");
      }
      const mime = local.mimeType || local.blob.type || "audio/webm";
      const ext = mime.includes("mp4") ? "mp4" : mime.includes("ogg") ? "ogg" : "webm";
      const formData = new FormData();
      formData.append("audio", local.blob, `${PART}.${ext}`);
      formData.append("browser_transcript", local.browserTranscript || "");
      const res = await fetch(`/debate/api/sessions/${SESSION_ID}/parts/${PART}/audio`, {
        method: "POST",
        body: formData,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || "保存のやり直しに失敗しました。");
      window.DEBATE_AUDIO_URL = data.audio_url || window.DEBATE_AUDIO_URL;
      localReuploadBtn.hidden = true;
      startPolling();
    } catch (err) {
      localReuploadBtn.disabled = false;
      localReuploadBtn.textContent = "端末の録音で文字起こし";
      showError(err.message);
    }
  });

  window.DebateLocalAudio?.get(SESSION_ID, PART).then((local) => {
    const browser = (local?.browserTranscript || "").trim();
    if (!browser) return;
    if (!window.DEBATE_TRANSCRIPT_BROWSER) window.DEBATE_TRANSCRIPT_BROWSER = browser;
    if (!textarea.value.trim() && window.DEBATE_TRANSCRIPT_SOURCE !== "whisper") {
      textarea.value = browser;
      window.DEBATE_TRANSCRIPT_SOURCE = "browser";
      showBrowserNote(true);
    }
  });

  retranscribeBtn?.addEventListener("click", async () => {
    const browser = (window.DEBATE_TRANSCRIPT_BROWSER || "").trim();
    const current = textarea.value.trim();
    let overwrite = false;
    if (window.DEBATE_TRANSCRIPT_SOURCE === "browser" && browser && current && current !== browser) {
      const replace = window.confirm(
        "編集した文章をWhisperの文字起こしで置き換えますか？キャンセルすると、今の文章を残して再試行しません。"
      );
      if (!replace) return;
      overwrite = true;
    }
    retranscribeBtn.disabled = true;
    retranscribeBtn.textContent = "文字起こし中...";
    hideError();

    try {
      const res = await fetch(`/debate/api/sessions/${SESSION_ID}/parts/${PART}/retranscribe`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(overwrite ? { overwrite: true } : {}),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "再試行の開始に失敗しました。");
      startPolling();
    } catch (err) {
      retranscribeBtn.disabled = false;
      retranscribeBtn.textContent = "文字起こしを再試行";
      showError(err.message);
    }
  });

  confirmBtn.addEventListener("click", async () => {
    confirmBtn.disabled = true;
    confirmBtn.textContent = "保存中...";
    errorBox.classList.add("hidden");

    try {
      const res = await fetch(`/debate/api/sessions/${SESSION_ID}/parts/${PART}/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          transcript_edited: textarea.value,
          transcript_browser: window.DEBATE_TRANSCRIPT_BROWSER || "",
          transcript_source:
            window.DEBATE_TRANSCRIPT_SOURCE === "browser" &&
            textarea.value.trim() === (window.DEBATE_TRANSCRIPT_BROWSER || "").trim()
              ? "browser"
              : window.DEBATE_TRANSCRIPT_SOURCE === "browser"
                ? "edited"
                : window.DEBATE_TRANSCRIPT_SOURCE || "",
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "保存に失敗しました。");

      window.location.href = `/debate/session/${SESSION_ID}`;
    } catch (err) {
      showError(err.message);
      confirmBtn.disabled = false;
      confirmBtn.textContent = "保存して確定";
    }
  });

  redoBtn.addEventListener("click", async () => {
    if (!window.confirm(`${PART} パートの録音・文字起こしをリセットしてやり直しますか？`)) return;

    redoBtn.disabled = true;
    try {
      const res = await fetch(`/debate/api/sessions/${SESSION_ID}/parts/${PART}/reset`, {
        method: "POST",
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "リセットに失敗しました。");

      window.DebateLocalAudio?.remove(SESSION_ID, PART);
      window.location.href = `/debate/session/${SESSION_ID}`;
    } catch (err) {
      showError(err.message);
      redoBtn.disabled = false;
    }
  });
})();
