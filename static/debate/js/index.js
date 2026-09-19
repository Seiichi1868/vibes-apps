(() => {
  const openingOverlay = document.getElementById("opening-overlay");
  if (openingOverlay) {
    setTimeout(() => {
      openingOverlay.classList.add("opacity-0", "pointer-events-none", "transition-opacity", "duration-300");
      setTimeout(() => openingOverlay.remove(), 320);
    }, 1950);
  }

  const form = document.getElementById("motion-form");
  const motionPicker = document.getElementById("motion-picker");
  const motionInput = document.getElementById("motion-input");
  const startBtn = document.getElementById("start-btn");
  const errorBox = document.getElementById("form-error");

  const presetMotions = motionPicker
    ? Array.from(motionPicker.options)
        .map((option) => option.value.trim())
        .filter(Boolean)
    : [];

  motionPicker?.addEventListener("change", () => {
    const selected = motionPicker.value.trim();
    if (selected) {
      motionInput.value = selected;
      motionInput.focus();
    }
  });

  motionInput?.addEventListener("input", () => {
    if (!motionPicker) return;
    const current = motionInput.value.trim();
    const matched = presetMotions.find((motion) => motion === current);
    motionPicker.value = matched || "";
  });

  function showError(message) {
    errorBox.textContent = message;
    errorBox.classList.remove("hidden");
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorBox.classList.add("hidden");

    const motion = motionInput.value.trim();
    if (!motion) {
      showError("論題を選ぶか、入力してください。");
      return;
    }

    startBtn.disabled = true;
    startBtn.textContent = "作成中...";

    try {
      const response = await fetch("/debate/api/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ motion }),
      });
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || "セッションの作成に失敗しました。");
      }

      window.DebateLocalSessions?.remember(data.session_id);
      window.location.href = `/debate/session/${data.session_id}`;
    } catch (err) {
      showError(err.message || "予期しないエラーが発生しました。");
      startBtn.disabled = false;
      startBtn.textContent = "ディベートを始める →";
    }
  });
})();
