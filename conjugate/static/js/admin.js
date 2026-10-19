(() => {
  const form = document.getElementById("settings-form");
  const btn = document.getElementById("save-btn");
  const messageEl = document.getElementById("save-message");
  const bgIdInput = document.getElementById("background-id");
  const bgOpacityInput = document.getElementById("background-opacity");
  const bgSlider = document.getElementById("bg-opacity-slider");
  const bgOpacityValue = document.getElementById("bg-opacity-value");
  const bgLabel = document.getElementById("bg-current-label");
  const pageBg = document.getElementById("page-bg-layer");
  const pageWash = document.getElementById("page-bg-wash");
  if (!form) return;

  function showMessage(message, isError) {
    messageEl.textContent = message;
    messageEl.className = `text-sm mt-2 ${isError ? "font-semibold" : "font-semibold"}`;
    messageEl.style.color = isError ? "var(--danger-text)" : "var(--ok-text)";
    messageEl.classList.remove("hidden");
  }

  function applyBackgroundPreview(imageUrl, opacity) {
    if (pageBg && imageUrl) pageBg.style.backgroundImage = `url('${imageUrl}')`;
    if (typeof opacity === "number") {
      if (pageBg) pageBg.style.opacity = String(opacity);
      if (pageWash) pageWash.style.opacity = String(Math.max(0, 1 - opacity));
    }
  }

  const bgPicker = document.getElementById("bg-picker");

  function setBgStyle(style) {
    if (!bgPicker) return;
    bgPicker.dataset.activeStyle = style || "photo";
    document.querySelectorAll("#bg-style-tabs .vsc-bg-tab").forEach((tab) => {
      tab.classList.toggle("is-active", tab.dataset.bgStyle === bgPicker.dataset.activeStyle);
    });
  }

  document.querySelectorAll("#bg-style-tabs .vsc-bg-tab").forEach((tab) => {
    tab.addEventListener("click", () => setBgStyle(tab.dataset.bgStyle));
  });

  document.querySelectorAll(".vsc-bg-pick").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".vsc-bg-pick").forEach((el) => el.classList.remove("vsc-bg-pick-active"));
      button.classList.add("vsc-bg-pick-active");
      if (bgIdInput) bgIdInput.value = button.dataset.bgId || "";
      if (bgLabel) bgLabel.textContent = button.dataset.bgLabel || "";
      setBgStyle(button.dataset.bgStyle);
      applyBackgroundPreview(button.dataset.bgImage, undefined);
    });
  });

  if (bgSlider) {
    bgSlider.addEventListener("input", () => {
      const opacity = Math.max(0, Math.min(100, parseInt(bgSlider.value, 10) || 0)) / 100;
      if (bgOpacityValue) bgOpacityValue.textContent = String(Math.round(opacity * 100));
      if (bgOpacityInput) bgOpacityInput.value = String(opacity);
      applyBackgroundPreview(undefined, opacity);
    });
  }

  const streakPreviewBtn = document.getElementById("streak-preview-btn");
  const streakPreviewDays = document.getElementById("streak-preview-days");

  function previewStreakCelebration() {
    const streak = Math.max(1, Math.min(365, parseInt((streakPreviewDays && streakPreviewDays.value) || "5", 10) || 5));
    if (streakPreviewDays) streakPreviewDays.value = String(streak);
    if (typeof window.showStreakCelebration !== "function") return;
    window.showStreakCelebration(streak, Math.max(streak - 1, 0));
  }

  if (streakPreviewBtn) {
    streakPreviewBtn.addEventListener("click", previewStreakCelebration);
  }
  if (streakPreviewDays) {
    streakPreviewDays.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      previewStreakCelebration();
    });
  }

  const previewParam = Number(new URLSearchParams(window.location.search).get("preview_streak"));
  if (Number.isFinite(previewParam) && previewParam > 0) {
    if (streakPreviewDays) streakPreviewDays.value = String(previewParam);
    window.setTimeout(previewStreakCelebration, 80);
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();

    const enabledCategories = Array.from(form.querySelectorAll('input[name="enabled_categories"]:checked')).map((el) => el.value);
    const enabledTenses = Array.from(form.querySelectorAll('input[name="enabled_tenses"]:checked')).map((el) => el.value);

    const payload = {
      enabled_categories: enabledCategories,
      enabled_tenses: enabledTenses,
      asr_engine: form.querySelector('select[name="asr_engine"]').value,
      whisper_model: form.querySelector('select[name="whisper_model"]').value,
      strictness: form.querySelector('select[name="strictness"]').value,
      targets_per_question: parseInt(form.querySelector('select[name="targets_per_question"]').value, 10),
      questions_per_session: parseInt(form.querySelector('input[name="questions_per_session"]').value, 10),
      prioritize_weak_verbs: form.querySelector('input[name="prioritize_weak_verbs"]').checked,
      gustar_enabled: form.querySelector('input[name="gustar_enabled"]').checked,
      gustar_per_session: parseInt(form.querySelector('input[name="gustar_per_session"]').value, 10),
      person_mode: (form.querySelector('input[name="person_mode"]:checked') || {}).value || "tu",
      conjugation_mastery_threshold: parseInt(form.querySelector('input[name="conjugation_mastery_threshold"]').value, 10),
      vocab_mastery_threshold: parseInt(form.querySelector('input[name="vocab_mastery_threshold"]').value, 10),
      guardian_price_coins: parseInt(form.querySelector('input[name="guardian_price_coins"]').value, 10),
      background_id: bgIdInput ? bgIdInput.value : "meadow",
      background_opacity: bgOpacityInput ? parseFloat(bgOpacityInput.value) : 0.38,
      opening_enabled: form.querySelector('input[name="opening_enabled"]').checked,
      opening_ms: parseInt(form.querySelector('input[name="opening_ms"]').value, 10),
    };

    btn.disabled = true;
    btn.textContent = "保存中...";
    messageEl.classList.add("hidden");

    try {
      const password = form.querySelector('input[name="admin_password"]').value;
      if (password) {
        const loginRes = await fetch("/conjugate/admin/api/login", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ password }),
        });
        const loginData = await loginRes.json().catch(() => ({}));
        if (!loginRes.ok) throw new Error(loginData.error || "ログインに失敗しました。");
        form.querySelector('input[name="admin_password"]').value = "";
      }
      const res = await fetch("/conjugate/admin/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || "保存に失敗しました。");
      showMessage("設定を保存しました。", false);
      form.querySelector('input[name="admin_password"]').value = "";
    } catch (err) {
      showMessage(err.message, true);
    } finally {
      btn.disabled = false;
      btn.textContent = "設定を保存";
    }
  });
})();
