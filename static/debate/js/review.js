(() => {
  const SESSION_ID = window.DEBATE_SESSION_ID;
  const PART = window.DEBATE_PART;

  const textarea = document.getElementById("transcript-edited");
  const confirmBtn = document.getElementById("confirm-btn");
  const redoBtn = document.getElementById("redo-btn");
  const retranscribeBtn = document.getElementById("retranscribe-btn");
  const transcribingBanner = document.getElementById("transcribing-banner");
  const transcriptErrorNote = document.getElementById("transcript-error-note");
  const errorBox = document.getElementById("review-error");

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

      if (data.transcript_error) {
        showError(`文字起こしに失敗しました: ${data.transcript_error}`);
        if (transcriptErrorNote) {
          transcriptErrorNote.textContent = `前回の文字起こしでエラーが発生しました: ${data.transcript_error}`;
          transcriptErrorNote.classList.remove("hidden");
        }
      } else {
        hideError();
        if (transcriptErrorNote) transcriptErrorNote.classList.add("hidden");
        textarea.value = data.transcript_edited || data.transcript_raw || "";
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

  retranscribeBtn?.addEventListener("click", async () => {
    retranscribeBtn.disabled = true;
    retranscribeBtn.textContent = "文字起こし中...";
    hideError();

    try {
      const res = await fetch(`/debate/api/sessions/${SESSION_ID}/parts/${PART}/retranscribe`, {
        method: "POST",
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
        body: JSON.stringify({ transcript_edited: textarea.value }),
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
