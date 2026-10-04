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
  const affiliationPicker = document.getElementById("affiliation-picker");
  const startBtn = document.getElementById("start-btn");
  const errorBox = document.getElementById("form-error");
  const soloOptions = document.getElementById("solo-options");
  const soloSide = document.getElementById("solo-side");
  const soloDifficulty = document.getElementById("solo-difficulty");
  const practiceOptions = document.getElementById("practice-options");
  const practiceParts = document.getElementById("practice-parts");
  const practiceSummary = document.getElementById("practice-summary");
  const practiceError = document.getElementById("practice-error");
  const practiceDifficultyWrap = document.getElementById("practice-difficulty-wrap");
  const practiceDifficulty = document.getElementById("practice-difficulty");

  const PRACTICE_PARTS = [
    { id: "PM", label: "PM（首相）" },
    { id: "LO", label: "LO（野党党首）" },
    { id: "MG", label: "MG（与党議員）" },
    { id: "MO", label: "MO（野党議員）" },
    { id: "LOR", label: "LOR（野党・最終弁論）" },
    { id: "PMR", label: "PMR（首相・最終弁論）" },
  ];
  const PRACTICE_PRESETS = {
    pm: { PM: "human" },
    lo: { PM: "ai", LO: "human" },
    mg: { PM: "human", LO: "ai", MG: "human" },
    mo: { PM: "ai", LO: "human", MG: "ai", MO: "human" },
  };

  function selectedMode() {
    const checked = form.querySelector('input[name="debate_mode"]:checked');
    const value = checked?.value;
    if (value === "solo" || value === "practice") return value;
    return "duo";
  }

  function syncModeOptions() {
    const mode = selectedMode();
    soloOptions?.classList.toggle("hidden", mode !== "solo");
    practiceOptions?.classList.toggle("hidden", mode !== "practice");
  }

  function roleInputs(part) {
    return Array.from(form.querySelectorAll(`input[name="practice-${part}"]`));
  }

  function readPracticeRoles() {
    const roles = {};
    PRACTICE_PARTS.forEach((part) => {
      const checked = roleInputs(part.id).find((input) => input.checked);
      roles[part.id] = checked?.value || "none";
    });
    return roles;
  }

  function writePracticeRoles(roles) {
    PRACTICE_PARTS.forEach((part) => {
      const value = roles[part.id] || "none";
      roleInputs(part.id).forEach((input) => {
        input.checked = input.value === value;
      });
    });
  }

  function showPracticeError(message) {
    if (!practiceError) return;
    practiceError.textContent = message || "";
    practiceError.classList.toggle("hidden", !message);
  }

  function renderPracticeSummary() {
    const roles = readPracticeRoles();
    const active = PRACTICE_PARTS.filter((part) => roles[part.id] !== "none");
    const hasAi = active.some((part) => roles[part.id] === "ai");
    const hasHuman = active.some((part) => roles[part.id] === "human");
    practiceDifficultyWrap?.classList.toggle("hidden", !hasAi);
    if (!practiceSummary) return;
    if (!active.length) {
      practiceSummary.textContent = "PMから練習する範囲を選んでください。";
      return;
    }
    const bits = active.map((part) => `${part.id}（${roles[part.id] === "ai" ? "AI" : "自分"}）`);
    practiceSummary.textContent = hasHuman
      ? `評価範囲: ${bits.join(" → ")}`
      : `評価範囲: ${bits.join(" → ")}（自分が話すパートが必要です）`;
  }

  function applyPracticeChange(changedPart, changedRole) {
    const roles = readPracticeRoles();
    roles[changedPart] = changedRole;
    const fixed = {};
    let stoppedAt = null;
    PRACTICE_PARTS.forEach((part) => {
      const role = roles[part.id] || "none";
      if (!stoppedAt && role !== "none") {
        fixed[part.id] = role;
        return;
      }
      if (!stoppedAt && role === "none") {
        stoppedAt = part.id;
      }
      fixed[part.id] = "none";
    });

    let error = "";
    if (changedRole !== "none" && fixed[changedPart] === "none") {
      error = `${stoppedAt}を自分かAIにしてから${changedPart}を選べます。`;
    }
    writePracticeRoles(fixed);
    showPracticeError(error);
    renderPracticeSummary();
  }

  function buildPracticeRows() {
    if (!practiceParts) return;
    practiceParts.innerHTML = PRACTICE_PARTS.map((part) => {
      const noneDisabled = part.id === "PM" ? "disabled" : "";
      return `
        <div class="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg bg-white/70 px-3 py-2">
          <span class="w-36 text-xs font-semibold text-slate-700">${part.label}</span>
          <label class="inline-flex items-center gap-1 text-xs text-slate-700">
            <input type="radio" name="practice-${part.id}" value="human" class="accent-teal-600" ${part.id === "PM" ? "checked" : ""}>
            自分
          </label>
          <label class="inline-flex items-center gap-1 text-xs text-slate-700">
            <input type="radio" name="practice-${part.id}" value="ai" class="accent-teal-600">
            AI
          </label>
          <label class="inline-flex items-center gap-1 text-xs text-slate-500">
            <input type="radio" name="practice-${part.id}" value="none" class="accent-teal-600" ${part.id === "PM" ? "" : "checked"} ${noneDisabled}>
            やらない
          </label>
        </div>
      `;
    }).join("");
    practiceParts.querySelectorAll('input[type="radio"]').forEach((input) => {
      input.addEventListener("change", () => {
        const part = input.name.replace("practice-", "");
        applyPracticeChange(part, input.value);
      });
    });
    renderPracticeSummary();
  }

  document.getElementById("practice-presets")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-practice-preset]");
    if (!button) return;
    const preset = PRACTICE_PRESETS[button.dataset.practicePreset] || {};
    const roles = {};
    PRACTICE_PARTS.forEach((part) => {
      roles[part.id] = preset[part.id] || "none";
    });
    writePracticeRoles(roles);
    showPracticeError("");
    renderPracticeSummary();
  });

  buildPracticeRows();

  form.querySelectorAll('input[name="debate_mode"]').forEach((input) => {
    input.addEventListener("change", syncModeOptions);
  });
  syncModeOptions();

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

    const affiliationId = affiliationPicker?.value.trim() || "";
    const hasAffiliationOptions = Boolean(
      affiliationPicker && Array.from(affiliationPicker.options).some((option) => option.value.trim())
    );
    if (!hasAffiliationOptions) {
      showError("所属がまだ登録されていません。管理画面で所属を追加してください。");
      return;
    }
    if (!affiliationId) {
      showError("所属を選択してください。");
      affiliationPicker?.focus();
      return;
    }

    const payload = { motion, affiliation_id: affiliationId };
    const mode = selectedMode();
    if (mode === "solo") {
      payload.mode = "solo";
      payload.user_side = soloSide?.value || "Gov";
      payload.ai_difficulty = soloDifficulty?.value || "normal";
    } else if (mode === "practice") {
      const roles = readPracticeRoles();
      const active = PRACTICE_PARTS.filter((part) => roles[part.id] !== "none");
      if (!active.length) {
        showError("PMから練習する範囲を選んでください。");
        return;
      }
      if (!active.some((part) => roles[part.id] === "human")) {
        showError("自分が練習するパートを1つ以上選んでください。");
        return;
      }
      payload.mode = "practice";
      payload.part_roles = roles;
      if (active.some((part) => roles[part.id] === "ai")) {
        payload.ai_difficulty = practiceDifficulty?.value || "normal";
      }
    }

    startBtn.disabled = true;
    startBtn.textContent = "作成中...";

    try {
      const response = await fetch("/debate/api/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
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
