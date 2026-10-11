(() => {
  const SESSION_ID = window.DEBATE_SESSION_ID;
  const STATUS = window.DEBATE_JUDGE_STATUS;

  const runBtn = document.getElementById("run-judge-btn");
  const errorBox = document.getElementById("run-judge-error");

  function showError(message) {
    if (!errorBox) return;
    errorBox.textContent = message;
    errorBox.classList.remove("hidden");
  }

  async function triggerJudge() {
    if (!runBtn) return;
    runBtn.disabled = true;
    const originalLabel = runBtn.textContent;
    runBtn.textContent = "ジャッジを開始しています...";
    if (errorBox) errorBox.classList.add("hidden");

    try {
      const res = await fetch(`/debate/api/sessions/${SESSION_ID}/judge`, { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "ジャッジの開始に失敗しました。");
      window.location.reload();
    } catch (err) {
      runBtn.disabled = false;
      runBtn.textContent = originalLabel;
      showError(err.message);
    }
  }

  runBtn?.addEventListener("click", triggerJudge);

  // ── 擬似進捗（APIコスト増なし・待ち時間の体感改善用） ──────────────
  const PROGRESS_STEPS = [
    { atMs: 0, text: "6パートの発言内容を読み込んでいます…" },
    { atMs: 3500, text: "Gov / Opp それぞれの論点を抽出しています…" },
    { atMs: 9000, text: "反論・再反論の流れを追跡しています…" },
    { atMs: 16000, text: "論点の状態を整理しています…" },
    { atMs: 24000, text: "内容・構成のルーブリックを評価しています…" },
    { atMs: 34000, text: "勝敗と講評をまとめています…" },
    { atMs: 48000, text: "最終確認をしています… もうしばらくお待ちください" },
  ];

  function startProgressLog() {
    const log = document.getElementById("judge-progress-log");
    if (!log) return;

    let shown = 0;
    const startedAt = Date.now();

    function appendStep(text) {
      const li = document.createElement("li");
      li.className = "judge-progress-item";
      li.textContent = text;
      log.appendChild(li);
      // 直前の項目は少し薄くする
      const items = log.querySelectorAll(".judge-progress-item");
      items.forEach((item, index) => {
        item.classList.toggle("is-current", index === items.length - 1);
        item.classList.toggle("is-done", index < items.length - 1);
      });
      shown += 1;
    }

    appendStep(PROGRESS_STEPS[0].text);

    const tick = setInterval(() => {
      const elapsed = Date.now() - startedAt;
      while (shown < PROGRESS_STEPS.length && elapsed >= PROGRESS_STEPS[shown].atMs) {
        appendStep(PROGRESS_STEPS[shown].text);
      }
      if (shown >= PROGRESS_STEPS.length) clearInterval(tick);
    }, 400);

    return () => clearInterval(tick);
  }

  // ── 実行中のポーリング（完了したら画面を再読み込みして結果を表示） ──────
  if (STATUS === "judging") {
    const stopProgress = startProgressLog();
    const pollTimer = setInterval(async () => {
      try {
        const res = await fetch(`/debate/api/sessions/${SESSION_ID}/judge`);
        if (!res.ok) return;
        const data = await res.json();
        if (data.status && data.status !== "judging") {
          clearInterval(pollTimer);
          stopProgress?.();
          window.location.reload();
        }
      } catch (_) {
        // ネットワーク不調時は次回のポーリングで再試行する
      }
    }, 3000);
  }
})();
