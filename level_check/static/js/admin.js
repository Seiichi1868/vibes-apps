(() => {
  const SPEAKING_AXES = window.LEVEL_CHECK_SPEAKING_AXES || [
    "fluency", "pronunciation", "accuracy", "vocabulary", "response_latency",
  ];
  const LISTENING_AXES = window.LEVEL_CHECK_LISTENING_AXES || [
    "comprehension_accuracy", "response_relevance",
  ];
  const CATEGORIES = window.LEVEL_CHECK_CATEGORIES || ["A", "B", "C", "D", "E", "F"];

  const statusMessage = document.getElementById("status-message");

  let settingsCache = null;
  let questionsCache = null;
  let currentQuestionTaskTab = "A";

  const TASK_FIELDS = {
    A: [
      { key: "question", label: "質問文", wide: true },
      { key: "expected_answer", label: "想定解答", wide: true },
    ],
    B: [{ key: "text", label: "復唱文", wide: true }],
    C: [
      { key: "dialog_text", label: "会話文", wide: true },
      { key: "question", label: "質問", wide: true },
      { key: "expected_answer", label: "想定解答", wide: true },
    ],
    D: [
      { key: "passage_text", label: "文章", wide: true },
      { key: "question", label: "質問", wide: true },
      { key: "expected_answer", label: "想定解答", wide: true },
    ],
    E: [
      { key: "story_text", label: "ストーリー", wide: true },
      { key: "time_limit_sec", label: "秒", type: "number", wide: false },
    ],
    F: [
      { key: "prompt", label: "テーマ", wide: true },
      { key: "time_limit_sec", label: "秒", type: "number", wide: false },
    ],
  };

  function showStatus(message, isError) {
    statusMessage.textContent = message;
    statusMessage.classList.toggle("text-emerald-700", !isError);
    statusMessage.classList.toggle("text-rose-600", Boolean(isError));
    if (message) setTimeout(() => { statusMessage.textContent = ""; }, 4000);
  }

  async function apiFetch(path, options = {}) {
    const url = new URL(path, window.location.origin);
    const opts = { ...options };
    if (opts.body && !(opts.body instanceof FormData)) {
      opts.headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
    }
    const res = await fetch(url.toString(), opts);
    const data = await res.json();
    if (!res.ok || data.ok === false) throw new Error(data.error || "リクエストに失敗しました。");
    return data;
  }

  async function loadAll() {
    await Promise.all([loadSettings(), loadRoster(), loadQuestions(), loadSubmissions()]);
  }

  async function loginAdmin(password) {
    const res = await fetch("/level_check/admin/api/login", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || "ログインに失敗しました。");
    return data;
  }

  async function boot() {
    try {
      const res = await fetch("/level_check/admin/api/status", { credentials: "same-origin" });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.logged_in) {
        await loadAll();
        return;
      }
    } catch (_) {
      /* ログイン前は一覧を読まない */
    }
    showStatus("管理ログインが必要です。下のパスワードを入れてAIモデルを変更してください。", true);
  }
  boot();

  document.querySelectorAll("#admin-tabs .admin-tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#admin-tabs .admin-tab-btn").forEach((b) => b.classList.remove("is-active"));
      btn.classList.add("is-active");
      const tab = btn.dataset.tab;
      document.querySelectorAll(".admin-tab-panel").forEach((panel) => {
        panel.classList.toggle("hidden", panel.dataset.tabPanel !== tab);
      });
    });
  });

  document.querySelectorAll("#question-task-tabs .admin-tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#question-task-tabs .admin-tab-btn").forEach((b) => b.classList.remove("is-active"));
      btn.classList.add("is-active");
      currentQuestionTaskTab = btn.dataset.taskTab;
      renderQuestions();
    });
  });

  function renderWeightRows(containerId, axes, defaultsKey, weightsKey) {
    const container = document.getElementById(containerId);
    if (!container || !settingsCache) return;
    container.innerHTML = "";
    axes.forEach((axis) => {
      const defaults = (settingsCache[defaultsKey] || {})[axis] || {};
      const weightPct = Math.round(((settingsCache[weightsKey] || {})[axis] || 0) * 100);
      const row = document.createElement("div");
      row.className = "rubric-weight-row";
      row.innerHTML = `
        <span class="rubric-weight-label">${defaults.label || axis}</span>
        <input type="range" min="0" max="100" value="${weightPct}" class="rubric-weight-slider" data-axis="${axis}">
        <span class="rubric-weight-value" data-axis-value="${axis}">${weightPct}%</span>
      `;
      container.appendChild(row);
    });
    container.querySelectorAll(".rubric-weight-slider").forEach((slider) => {
      slider.addEventListener("input", () => {
        const valueEl = container.querySelector(`[data-axis-value="${slider.dataset.axis}"]`);
        if (valueEl) valueEl.textContent = `${slider.value}%`;
      });
    });
  }

  function collectWeights(containerId) {
    const weights = {};
    document.querySelectorAll(`#${containerId} .rubric-weight-slider`).forEach((slider) => {
      weights[slider.dataset.axis] = Number(slider.value) / 100;
    });
    return weights;
  }

  async function loadSettings() {
    const data = await apiFetch("/level_check/admin/api/settings");
    settingsCache = data;
    renderSettings();
  }

  function renderSettings() {
    if (!settingsCache) return;

    const modelPicker = document.getElementById("ai-model-picker");
    modelPicker.innerHTML = "";
    settingsCache.ai_model_modes.forEach((mode) => {
      const label = document.createElement("label");
      label.className = "lc-mode-option";
      label.innerHTML = `<input type="radio" name="ai_model_mode" value="${mode.id}" ${mode.id === settingsCache.ai_model_mode ? "checked" : ""}>${mode.label}`;
      modelPicker.appendChild(label);
    });

    const infoPicker = document.getElementById("info-level-picker");
    infoPicker.innerHTML = "";
    settingsCache.info_levels.forEach((lvl) => {
      const label = document.createElement("label");
      label.className = "lc-mode-option";
      label.innerHTML = `<input type="radio" name="student_info_level" value="${lvl.id}" ${lvl.id === settingsCache.student_info_level ? "checked" : ""}>${lvl.label}`;
      infoPicker.appendChild(label);
    });

    const qpc = document.getElementById("questions-per-category");
    qpc.innerHTML = "";
    const counts = settingsCache.questions_per_category || {};
    CATEGORIES.forEach((cat) => {
      const wrap = document.createElement("label");
      wrap.className = "text-xs text-slate-500 flex items-center gap-1";
      wrap.innerHTML = `${cat}<input class="lc-input w-14" type="number" min="0" max="15" data-cat="${cat}" value="${counts[cat] ?? 0}">`;
      qpc.appendChild(wrap);
    });

    const bgOpacitySlider = document.getElementById("bg-opacity-slider");
    const bgOpacityValue = document.getElementById("bg-opacity-value");
    const bgOpacityPct = Math.round((settingsCache.background_opacity ?? 0.35) * 100);
    if (bgOpacitySlider) bgOpacitySlider.value = String(bgOpacityPct);
    if (bgOpacityValue) bgOpacityValue.textContent = `${bgOpacityPct}%`;

    const overall = settingsCache.overall_weights || { speaking: 0.5, listening: 0.5 };
    const overallContainer = document.getElementById("overall-weights");
    overallContainer.innerHTML = "";
    [["speaking", "スピーキング"], ["listening", "リスニング"]].forEach(([key, label]) => {
      const pct = Math.round((overall[key] || 0) * 100);
      const row = document.createElement("div");
      row.className = "rubric-weight-row";
      row.innerHTML = `
        <span class="rubric-weight-label">${label}</span>
        <input type="range" min="0" max="100" value="${pct}" class="rubric-weight-slider" data-axis="${key}">
        <span class="rubric-weight-value" data-axis-value="${key}">${pct}%</span>
      `;
      overallContainer.appendChild(row);
    });
    overallContainer.querySelectorAll(".rubric-weight-slider").forEach((slider) => {
      slider.addEventListener("input", () => {
        const valueEl = overallContainer.querySelector(`[data-axis-value="${slider.dataset.axis}"]`);
        if (valueEl) valueEl.textContent = `${slider.value}%`;
      });
    });

    renderWeightRows("speaking-rubric-weights", SPEAKING_AXES, "speaking_rubric_defaults", "speaking_rubric_weights");
    renderWeightRows("listening-rubric-weights", LISTENING_AXES, "listening_rubric_defaults", "listening_rubric_weights");
  }

  document.getElementById("bg-opacity-slider")?.addEventListener("input", (e) => {
    const pct = Number(e.target.value);
    const valueEl = document.getElementById("bg-opacity-value");
    if (valueEl) valueEl.textContent = `${pct}%`;
    const layer = document.getElementById("lc-bg-image-layer");
    if (layer) layer.style.opacity = String(pct / 100);
  });

  document.getElementById("save-settings-btn")?.addEventListener("click", async () => {
    const infoLevel = document.querySelector('input[name="student_info_level"]:checked')?.value;
    const bgOpacityPct = document.getElementById("bg-opacity-slider")?.value;
    const questionsPerCategory = {};
    document.querySelectorAll("#questions-per-category input[data-cat]").forEach((input) => {
      questionsPerCategory[input.dataset.cat] = Number(input.value);
    });

    try {
      await apiFetch("/level_check/admin/api/settings", {
        method: "POST",
        body: JSON.stringify({
          student_info_level: infoLevel,
          questions_per_category: questionsPerCategory,
          background_opacity: bgOpacityPct !== undefined ? Number(bgOpacityPct) / 100 : undefined,
          speaking_rubric_weights: collectWeights("speaking-rubric-weights"),
          listening_rubric_weights: collectWeights("listening-rubric-weights"),
          overall_weights: collectWeights("overall-weights"),
        }),
      });
      showStatus("設定を保存しました。");
      await loadSettings();
    } catch (err) {
      showStatus(err.message, true);
    }
  });

  document.getElementById("change-model-btn")?.addEventListener("click", async () => {
    const modelMode = document.querySelector('input[name="ai_model_mode"]:checked')?.value;
    const pwInput = document.getElementById("model-admin-password");
    const statusEl = document.getElementById("model-change-status");
    const password = pwInput?.value.trim() || "";

    try {
      if (password) {
        await loginAdmin(password);
        if (pwInput) pwInput.value = "";
        await loadAll();
      }
      await apiFetch("/level_check/admin/api/settings", {
        method: "POST",
        body: JSON.stringify({ ai_model_mode: modelMode }),
      });
      if (statusEl) {
        statusEl.textContent = "AIモデルを変更しました。";
        statusEl.classList.remove("text-rose-600");
        statusEl.classList.add("text-emerald-700");
      }
      if (pwInput) pwInput.value = "";
      await loadSettings();
    } catch (err) {
      if (statusEl) {
        statusEl.textContent = err.message;
        statusEl.classList.remove("text-emerald-700");
        statusEl.classList.add("text-rose-600");
      }
    }
  });

  async function loadRoster() {
    const data = await apiFetch("/level_check/admin/api/students");
    renderRoster(data.students || []);
  }

  function renderRoster(students) {
    const list = document.getElementById("roster-list");
    list.innerHTML = "";
    if (!students.length) {
      list.innerHTML = '<p class="text-sm text-slate-400">名簿が登録されていません。</p>';
      return;
    }
    students.forEach((student) => {
      const row = document.createElement("div");
      row.className = "roster-row flex items-center gap-2 flex-wrap";
      row.innerHTML = `
        <input class="lc-input w-24" data-field="class_name" value="${student.class_name}" placeholder="クラス">
        <input class="lc-input w-16" data-field="number" value="${student.number}" placeholder="番号">
        <input class="lc-input flex-1 min-w-[8rem]" data-field="name" value="${student.name}" placeholder="氏名">
        <button type="button" class="text-xs px-2.5 py-1 rounded-full border border-rose-200 text-rose-600 hover:bg-rose-50">削除</button>
      `;
      const inputs = row.querySelectorAll("input");
      const saveStudent = async () => {
        const updated = { id: student.id };
        inputs.forEach((input) => { updated[input.dataset.field] = input.value; });
        try {
          await apiFetch("/level_check/admin/api/students", {
            method: "POST",
            body: JSON.stringify({ student: updated }),
          });
          showStatus("名簿を保存しました。");
        } catch (err) {
          showStatus(err.message, true);
        }
      };
      inputs.forEach((input) => input.addEventListener("blur", saveStudent));
      row.querySelector("button").addEventListener("click", async () => {
        try {
          await apiFetch(`/level_check/admin/api/students/${student.id}`, { method: "DELETE" });
          await loadRoster();
        } catch (err) {
          showStatus(err.message, true);
        }
      });
      list.appendChild(row);
    });
  }

  document.getElementById("roster-add-btn")?.addEventListener("click", async () => {
    try {
      await apiFetch("/level_check/admin/api/students", {
        method: "POST",
        body: JSON.stringify({ student: { class_name: "", number: "", name: "" } }),
      });
      await loadRoster();
    } catch (err) {
      showStatus(err.message, true);
    }
  });

  document.getElementById("roster-upload-btn")?.addEventListener("click", async () => {
    const fileInput = document.getElementById("roster-file-input");
    const file = fileInput.files[0];
    if (!file) {
      showStatus("ファイルを選択してください。", true);
      return;
    }
    const formData = new FormData();
    formData.append("file", file);
    try {
      const data = await apiFetch("/level_check/admin/api/students/upload", { method: "POST", body: formData });
      showStatus(`${data.count}件の名簿を読み込みました。`);
      fileInput.value = "";
      await loadRoster();
    } catch (err) {
      showStatus(err.message, true);
    }
  });

  async function loadQuestions() {
    const data = await apiFetch("/level_check/admin/api/questions");
    questionsCache = data.questions;
    renderQuestions();
  }

  function escapeAttr(value) {
    return String(value || "").replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
  }

  function renderQuestions() {
    const list = document.getElementById("questions-list");
    list.innerHTML = "";
    if (!questionsCache) return;

    const items = questionsCache[currentQuestionTaskTab] || [];
    const fields = TASK_FIELDS[currentQuestionTaskTab] || [];

    if (!items.length) {
      list.innerHTML = '<p class="text-sm text-slate-400">問題が登録されていません。「AIで追加生成」または「手動で追加」してください。</p>';
      return;
    }

    items.forEach((item) => {
      const row = document.createElement("div");
      row.className = "question-row space-y-1.5";
      const fieldHtml = fields.map((field) => {
        const width = field.wide ? "w-full" : "w-20";
        const type = field.type === "number" ? 'type="number" min="5" max="120"' : 'type="text"';
        return `<input class="lc-input ${width}" data-field="${field.key}" ${type} value="${escapeAttr(item[field.key])}" placeholder="${field.label}">`;
      }).join("");
      row.innerHTML = `
        <div class="flex flex-wrap items-center gap-2">
          ${fieldHtml}
          <input class="lc-input w-16" data-field="level" value="${escapeAttr(item.level)}" placeholder="レベル">
          <label class="text-xs flex items-center gap-1"><input type="checkbox" data-field="active" ${item.active ? "checked" : ""}>表示</label>
          <button type="button" class="text-xs px-2.5 py-1 rounded-full border border-rose-200 text-rose-600 hover:bg-rose-50" data-action="delete">削除</button>
        </div>
      `;

      const saveItem = async () => {
        const updates = {};
        row.querySelectorAll("[data-field]").forEach((input) => {
          if (input.type === "checkbox") updates[input.dataset.field] = input.checked;
          else updates[input.dataset.field] = input.value;
        });
        try {
          const data = await apiFetch(`/level_check/admin/api/questions/${currentQuestionTaskTab}/${item.id}`, {
            method: "POST",
            body: JSON.stringify({ item: updates }),
          });
          questionsCache = data.questions;
          showStatus("問題を保存しました。");
        } catch (err) {
          showStatus(err.message, true);
        }
      };
      row.querySelectorAll("input").forEach((input) => {
        input.addEventListener(input.type === "checkbox" ? "change" : "blur", saveItem);
      });
      row.querySelector('[data-action="delete"]').addEventListener("click", async () => {
        try {
          const data = await apiFetch(`/level_check/admin/api/questions/${currentQuestionTaskTab}/${item.id}`, {
            method: "DELETE",
          });
          questionsCache = data.questions;
          renderQuestions();
        } catch (err) {
          showStatus(err.message, true);
        }
      });
      list.appendChild(row);
    });
  }

  document.getElementById("question-add-btn")?.addEventListener("click", async () => {
    const fields = TASK_FIELDS[currentQuestionTaskTab] || [];
    const item = { level: "A2" };
    fields.forEach((field) => {
      item[field.key] = field.type === "number" ? 30 : "";
    });
    try {
      const data = await apiFetch(`/level_check/admin/api/questions/${currentQuestionTaskTab}`, {
        method: "POST",
        body: JSON.stringify({ item }),
      });
      questionsCache = data.questions;
      renderQuestions();
    } catch (err) {
      showStatus(err.message, true);
    }
  });

  document.getElementById("generate-questions-btn")?.addEventListener("click", async () => {
    const count = document.getElementById("generate-count").value || 5;
    const statusEl = document.getElementById("generate-status");
    statusEl.textContent = "生成中...";
    try {
      const data = await apiFetch(`/level_check/admin/api/questions/${currentQuestionTaskTab}/generate`, {
        method: "POST",
        body: JSON.stringify({ count }),
      });
      questionsCache = data.questions;
      renderQuestions();
      statusEl.textContent = `${data.generated_count}件を生成しました。`;
    } catch (err) {
      statusEl.textContent = "";
      showStatus(err.message, true);
    }
  });

  let allSubmissionsSelected = false;

  async function loadSubmissions() {
    const data = await apiFetch("/level_check/admin/api/submissions");
    renderSubmissions(data.submissions || []);
    document.getElementById("export-submissions-link").href = "/level_check/admin/api/submissions/export";
  }

  function getSubmissionCheckboxes() {
    return Array.from(document.querySelectorAll("#submissions-list .submission-select"));
  }

  function updateBulkPdfState() {
    const boxes = getSubmissionCheckboxes();
    const selectedCount = boxes.filter((box) => box.checked).length;
    const selectAllBtn = document.getElementById("submissions-select-all-btn");
    const pdfSelectedBtn = document.getElementById("submissions-pdf-selected-btn");
    if (selectAllBtn) {
      selectAllBtn.disabled = boxes.length === 0;
      allSubmissionsSelected = boxes.length > 0 && selectedCount === boxes.length;
      selectAllBtn.textContent = allSubmissionsSelected ? "選択解除" : "全て選択";
    }
    if (pdfSelectedBtn) {
      pdfSelectedBtn.disabled = selectedCount === 0;
      pdfSelectedBtn.textContent = selectedCount
        ? `PDF個票ダウンロード（${selectedCount}件）`
        : "PDF個票ダウンロード";
    }
  }

  async function downloadPdfFromResponse(res, filename) {
    if (!res.ok) {
      let message = "PDFの生成に失敗しました。";
      try {
        const data = await res.json();
        if (data && data.error) message = data.error;
      } catch (_) {
        /* ignore */
      }
      throw new Error(message);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  }

  function renderSubmissions(submissions) {
    const list = document.getElementById("submissions-list");
    list.innerHTML = "";
    if (!submissions.length) {
      list.innerHTML = '<p class="text-sm text-slate-400">受験結果はまだありません。</p>';
      updateBulkPdfState();
      return;
    }
    submissions.forEach((s) => {
      const info = s.student_info || {};
      const overall = s.overall || {};
      const row = document.createElement("div");
      row.className = "submission-row flex items-center justify-between gap-2 flex-wrap";
      const infoText = [info.class_name, info.number, info.name].filter(Boolean).join(" / ") || "（情報なし）";
      const score = overall.speaking_level_score ?? overall.score_100 ?? "—";
      row.innerHTML = `
        <label class="flex items-center gap-2 min-w-0 flex-1">
          <input type="checkbox" class="submission-select shrink-0" data-id="${s.id}">
          <div class="min-w-0">
            <p class="text-sm font-semibold text-slate-700">${infoText}</p>
            <p class="text-xs text-slate-400">${s.submitted_at || ""} ・ Speaking Level Score: <strong>${score}/90</strong>（CEFR: ${overall.cefr_band || "—"}） / S:${overall.speaking_subscore ?? "—"} L:${overall.listening_subscore ?? "—"}</p>
          </div>
        </label>
        <div class="flex items-center gap-1.5 shrink-0">
          <button type="button" class="text-xs px-2.5 py-1 rounded-full border border-emerald-200 text-emerald-700 hover:bg-emerald-50" data-action="pdf">PDF</button>
          <button type="button" class="text-xs px-2.5 py-1 rounded-full border border-rose-200 text-rose-600 hover:bg-rose-50" data-action="delete">削除</button>
        </div>
      `;
      row.querySelector(".submission-select").addEventListener("change", updateBulkPdfState);
      row.querySelector('[data-action="pdf"]').addEventListener("click", async (event) => {
        const btn = event.currentTarget;
        if (!confirm("この受験結果の個票をPDFで出力しますか？")) return;
        const originalLabel = btn.textContent;
        btn.disabled = true;
        btn.textContent = "生成中…";
        try {
          const res = await fetch(`/level_check/admin/api/submissions/${encodeURIComponent(s.id)}/pdf`);
          if (!res.ok) {
            let message = "PDFの生成に失敗しました。";
            try {
              const data = await res.json();
              if (data && data.error) message = data.error;
            } catch (_) {
              /* ignore */
            }
            throw new Error(message);
          }
          const blob = await res.blob();
          const url = URL.createObjectURL(blob);
          const opened = window.open(url, "_blank", "noopener,noreferrer");
          if (!opened) {
            const a = document.createElement("a");
            a.href = url;
            a.download = `level_check_${s.id}.pdf`;
            document.body.appendChild(a);
            a.click();
            a.remove();
          }
          setTimeout(() => URL.revokeObjectURL(url), 60_000);
        } catch (err) {
          showStatus(err.message, true);
        } finally {
          btn.disabled = false;
          btn.textContent = originalLabel || "PDF";
        }
      });
      row.querySelector('[data-action="delete"]').addEventListener("click", async () => {
        try {
          await apiFetch(`/level_check/admin/api/submissions/${s.id}`, { method: "DELETE" });
          await loadSubmissions();
        } catch (err) {
          showStatus(err.message, true);
        }
      });
      list.appendChild(row);
    });
    updateBulkPdfState();
  }

  document.getElementById("submissions-select-all-btn")?.addEventListener("click", () => {
    const boxes = getSubmissionCheckboxes();
    const nextChecked = !allSubmissionsSelected;
    boxes.forEach((box) => {
      box.checked = nextChecked;
    });
    updateBulkPdfState();
  });

  document.getElementById("submissions-pdf-selected-btn")?.addEventListener("click", async () => {
    const ids = getSubmissionCheckboxes()
      .filter((box) => box.checked)
      .map((box) => box.dataset.id)
      .filter(Boolean);
    if (!ids.length) return;

    const btn = document.getElementById("submissions-pdf-selected-btn");
    btn.disabled = true;
    btn.textContent = ids.length >= 5 ? `PDF生成中（${ids.length}件）…` : "PDF生成中…";
    try {
      const res = await fetch("/level_check/admin/api/submissions/pdf", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids }),
      });
      await downloadPdfFromResponse(res, `level_check_reports_${ids.length}.pdf`);
      showStatus(`${ids.length}件の個票PDFをダウンロードしました。`);
    } catch (err) {
      showStatus(err.message, true);
    } finally {
      updateBulkPdfState();
    }
  });
})();
