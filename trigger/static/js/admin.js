(() => {
  "use strict";

  const API = "/trigger/admin/api";
  const $ = (id) => document.getElementById(id);

  const state = {
    settings: null,
    themes: [],
    students: [],
  };

  async function fetchJson(url, options = {}) {
    const res = await fetch(url, options);
    let data;
    try {
      data = await res.json();
    } catch (_) {
      throw new Error(`サーバーエラー (HTTP ${res.status})`);
    }
    if (!res.ok || data.ok === false) {
      throw new Error(data.error || `エラーが発生しました (HTTP ${res.status})`);
    }
    return data;
  }

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text || "";
    return div.innerHTML;
  }

  // ── タブ切替 ────────────────────────────────────────────

  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("is-selected"));
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.add("hidden"));
      btn.classList.add("is-selected");
      $(`tab-${btn.dataset.tab}`).classList.remove("hidden");
    });
  });
  const firstTab = document.querySelector(".tab-btn");
  if (firstTab) firstTab.click();

  // ── 設定タブ ────────────────────────────────────────────

  function barString(score) {
    return "●".repeat(score) + "○".repeat(5 - score);
  }

  function modelById(modelId) {
    return state.settings.ai_model_modes.find((m) => m.id === modelId);
  }

  function updateModelStatsRow(select) {
    const statsRow = select.parentElement.querySelector(".model-stats-row");
    const m = modelById(select.value);
    if (!statsRow || !m) return;
    statsRow.innerHTML = `
      <span class="inline-flex items-center gap-1"><span class="text-slate-400">コスト</span> <span class="tracking-tight accent-blue">${barString(m.cost_score)}</span></span>
      <span class="inline-flex items-center gap-1"><span class="text-slate-400">性能</span> <span class="tracking-tight accent-good">${barString(m.performance)}</span></span>
    `;
  }

  function renderModelSelectList() {
    const container = $("model-select-list");
    container.innerHTML = "";
    state.settings.task_keys.forEach((key) => {
      const wrap = document.createElement("div");
      wrap.className = "glass-inset rounded-xl p-3";
      const label = document.createElement("label");
      label.className = "mb-1 block text-xs font-semibold accent-label";
      label.textContent = state.settings.task_labels[key];
      const select = document.createElement("select");
      select.className = "compact-input model-select";
      select.dataset.taskKey = key;
      state.settings.ai_model_modes.forEach((m) => {
        const opt = document.createElement("option");
        opt.value = m.id;
        opt.textContent = `${m.label}　コスト${barString(m.cost_score)}　性能${barString(m.performance)}`;
        if (state.settings.task_model_modes[key] === m.id) opt.selected = true;
        select.appendChild(opt);
      });
      const statsRow = document.createElement("div");
      statsRow.className = "model-stats-row mt-1.5 flex gap-3 text-[11px]";
      select.addEventListener("change", () => {
        updateModelStatsRow(select);
        refreshCostEstimatePreview();
      });
      wrap.appendChild(label);
      wrap.appendChild(select);
      wrap.appendChild(statsRow);
      container.appendChild(wrap);
      updateModelStatsRow(select);
    });
  }

  function renderWhisperSelect() {
    const select = $("whisper-model-select");
    select.innerHTML = "";
    state.settings.whisper_models.forEach((m) => {
      const opt = document.createElement("option");
      opt.value = m.id;
      opt.textContent = `${m.label}（$${m.cost_per_min_usd}/分）`;
      if (state.settings.whisper_model === m.id) opt.selected = true;
      select.appendChild(opt);
    });
    select.addEventListener("change", refreshCostEstimatePreview);
  }

  function renderCostEstimate(estimate) {
    const box = $("cost-estimate-box");
    box.innerHTML = `
      <p class="mb-1 font-semibold accent-strong">1セッションあたりの概算コスト: 約 ¥${estimate.total_jpy}（$${estimate.total_usd}）</p>
      <p class="text-slate-500">内訳: 評価用GPT呼び出し $${estimate.chat_total_usd} ／ TTS $${estimate.tts_total_usd} ／ Whisper $${estimate.whisper_total_usd}</p>
      <p class="mt-1 text-slate-400">※ Q&amp;A質問数・スピーチトピック数を増やすほど、TTS・Whisper・評価用GPT呼び出しの回数が線形に増加しコストも増加します。</p>
    `;
  }

  async function refreshCostEstimatePreview() {
    const payload = collectSettingsPayload();
    try {
      const data = await fetchJson(`${API}/cost-estimate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      renderCostEstimate(data.cost_estimate);
    } catch (_) {
      /* ignore preview errors */
    }
  }

  function collectSettingsPayload() {
    const task_model_modes = {};
    document.querySelectorAll(".model-select").forEach((select) => {
      task_model_modes[select.dataset.taskKey] = select.value;
    });
    return {
      task_model_modes,
      whisper_model: $("whisper-model-select").value,
      qa_question_count: parseInt($("qa-count-input").value, 10) || 1,
      speech_topic_count: parseInt($("topic-count-input").value, 10) || 1,
      speech_topic_tts_enabled: $("speech-tts-checkbox").checked,
      student_info_required: $("student-info-required-checkbox").checked,
    };
  }

  async function loadSettings() {
    const data = await fetchJson(`${API}/settings`);
    state.settings = data;
    renderModelSelectList();
    renderWhisperSelect();
    $("qa-count-input").min = data.qa_question_count_range[0];
    $("qa-count-input").max = data.qa_question_count_range[1];
    $("qa-count-input").value = data.qa_question_count;
    $("topic-count-input").min = data.speech_topic_count_range[0];
    $("topic-count-input").max = data.speech_topic_count_range[1];
    $("topic-count-input").value = data.speech_topic_count;
    $("speech-tts-checkbox").checked = !!data.speech_topic_tts_enabled;
    $("student-info-required-checkbox").checked = data.student_info_required !== false;
    renderCostEstimate(data.cost_estimate);

    ["qa-count-input", "topic-count-input", "speech-tts-checkbox", "student-info-required-checkbox"].forEach((id) => {
      $(id).addEventListener("change", refreshCostEstimatePreview);
    });
  }

  $("btn-save-settings").addEventListener("click", async () => {
    const messageEl = $("settings-message");
    messageEl.textContent = "";
    messageEl.className = "mt-2 text-xs";
    try {
      const payload = collectSettingsPayload();
      payload.admin_password = $("admin-password-input").value;
      const data = await fetchJson(`${API}/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      state.settings = data;
      renderModelSelectList();
      renderWhisperSelect();
      renderCostEstimate(data.cost_estimate);
      messageEl.textContent = "保存しました。";
      messageEl.classList.add("accent-good");
      $("admin-password-input").value = "";
    } catch (exc) {
      messageEl.textContent = exc.message;
      messageEl.classList.add("text-rose-600");
    }
  });

  // ── テーマ管理タブ ──────────────────────────────────────

  function renderThemeListAdmin() {
    const container = $("theme-list-admin");
    container.innerHTML = "";
    state.themes.forEach((theme) => {
      const row = document.createElement("div");
      row.className = "glass-inset flex items-center justify-between gap-2 rounded-lg px-2.5 py-1";
      row.innerHTML = `
        <div class="min-w-0 flex items-baseline gap-2">
          <p class="shrink-0 text-[13px] font-semibold accent-heading">${escapeHtml(theme.title)} ${theme.is_active ? "" : '<span class="text-[11px] font-normal text-slate-400">(無効)</span>'}</p>
          <p class="truncate text-[11px] text-slate-500">${escapeHtml(theme.description_hint || "")}</p>
        </div>
        <div class="flex shrink-0 gap-1">
          <button class="compact-btn-outline !px-2 !py-0.5 text-[11px] edit-theme-btn" data-id="${theme.id}">編集</button>
          <button class="compact-btn-outline !px-2 !py-0.5 text-[11px] delete-theme-btn" data-id="${theme.id}">削除</button>
        </div>`;
      container.appendChild(row);
    });

    container.querySelectorAll(".edit-theme-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const theme = state.themes.find((t) => t.id === btn.dataset.id);
        if (!theme) return;
        $("theme-id-input").value = theme.id;
        $("theme-title-input").value = theme.title;
        $("theme-hint-input").value = theme.description_hint;
        $("theme-active-input").checked = theme.is_active;
        $("btn-cancel-theme-edit").classList.remove("hidden");
      });
    });
    container.querySelectorAll(".delete-theme-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (!confirm("このテーマを削除しますか？")) return;
        const data = await fetchJson(`${API}/themes/${btn.dataset.id}`, { method: "DELETE" });
        state.themes = data.themes;
        renderThemeListAdmin();
      });
    });
  }

  $("btn-save-theme").addEventListener("click", async () => {
    const theme = {
      id: $("theme-id-input").value || undefined,
      title: $("theme-title-input").value.trim(),
      description_hint: $("theme-hint-input").value.trim(),
      is_active: $("theme-active-input").checked,
    };
    if (!theme.title) {
      alert("テーマ名を入力してください。");
      return;
    }
    const data = await fetchJson(`${API}/themes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ theme }),
    });
    state.themes = data.themes;
    renderThemeListAdmin();
    resetThemeForm();
  });

  function resetThemeForm() {
    $("theme-id-input").value = "";
    $("theme-title-input").value = "";
    $("theme-hint-input").value = "";
    $("theme-active-input").checked = true;
    $("btn-cancel-theme-edit").classList.add("hidden");
  }
  $("btn-cancel-theme-edit").addEventListener("click", resetThemeForm);

  // ── 生徒名簿タブ ────────────────────────────────────────

  function renderRosterTable() {
    const container = $("roster-table");
    if (state.students.length === 0) {
      container.innerHTML = '<p class="text-xs text-slate-400">登録された生徒がいません。</p>';
      return;
    }
    const rows = state.students
      .map(
        (s) => `<tr class="accent-row">
          <td class="px-2 py-1">${escapeHtml(s.class_name)}</td>
          <td class="px-2 py-1">${escapeHtml(s.number)}</td>
          <td class="px-2 py-1">${escapeHtml(s.name)}</td>
          <td class="px-2 py-1"><button class="delete-student-btn text-xs text-rose-500" data-id="${s.id}">削除</button></td>
        </tr>`
      )
      .join("");
    container.innerHTML = `<table class="w-full text-left text-xs">
      <thead><tr class="text-slate-400"><th class="px-2 py-1">クラス</th><th class="px-2 py-1">番号</th><th class="px-2 py-1">名前</th><th></th></tr></thead>
      <tbody>${rows}</tbody></table>`;
    container.querySelectorAll(".delete-student-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const data = await fetchJson(`${API}/students/${btn.dataset.id}`, { method: "DELETE" });
        state.students = data.students;
        renderRosterTable();
      });
    });
  }

  $("btn-add-student").addEventListener("click", async () => {
    const student = {
      id: $("student-id-input").value || undefined,
      class_name: $("student-class-input").value.trim(),
      number: $("student-number-input").value.trim(),
      name: $("student-name-input").value.trim(),
    };
    const data = await fetchJson(`${API}/students`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ student }),
    });
    state.students = data.students;
    renderRosterTable();
    $("student-id-input").value = "";
    $("student-class-input").value = "";
    $("student-number-input").value = "";
    $("student-name-input").value = "";
  });

  $("btn-upload-roster").addEventListener("click", async () => {
    const fileInput = $("roster-upload-input");
    if (!fileInput.files.length) {
      alert("Excelファイルを選択してください。");
      return;
    }
    const formData = new FormData();
    formData.append("file", fileInput.files[0]);
    try {
      const data = await fetchJson(`${API}/students/upload`, { method: "POST", body: formData });
      state.students = data.students;
      renderRosterTable();
      alert(`${data.count}件の生徒を登録しました。`);
    } catch (exc) {
      alert(exc.message);
    }
  });

  // ── レポート一覧タブ ────────────────────────────────────

  async function loadSubmissions() {
    const data = await fetchJson(`${API}/submissions`);
    renderSubmissionsTable(data.submissions);
  }

  function renderSubmissionsTable(submissions) {
    const container = $("submissions-table");
    if (!submissions.length) {
      container.innerHTML = '<p class="text-xs text-slate-400">まだ完了したセッションがありません。</p>';
      return;
    }
    const rows = submissions
      .map((s) => {
        const info = s.student_info || {};
        const finalEval = s.final_evaluation || {};
        return `<tr class="accent-row">
          <td class="px-2 py-1 whitespace-nowrap">${escapeHtml(s.submitted_at)}</td>
          <td class="px-2 py-1">${escapeHtml(info.class_name)}</td>
          <td class="px-2 py-1">${escapeHtml(info.number)}</td>
          <td class="px-2 py-1">${escapeHtml(info.name)}</td>
          <td class="px-2 py-1">${escapeHtml(s.theme_title)}</td>
          <td class="px-2 py-1">${finalEval.overall_score_90 ?? "-"}</td>
          <td class="px-2 py-1">${escapeHtml(finalEval.cefr_level || "-")}</td>
          <td class="px-2 py-1"><button class="delete-submission-btn text-xs text-rose-500" data-id="${s.id}">削除</button></td>
        </tr>`;
      })
      .join("");
    container.innerHTML = `<table class="w-full text-left text-xs">
      <thead><tr class="text-slate-400">
        <th class="px-2 py-1">日時</th><th class="px-2 py-1">クラス</th><th class="px-2 py-1">番号</th>
        <th class="px-2 py-1">名前</th><th class="px-2 py-1">テーマ</th><th class="px-2 py-1">スコア</th>
        <th class="px-2 py-1">CEFR</th><th></th>
      </tr></thead><tbody>${rows}</tbody></table>`;
    container.querySelectorAll(".delete-submission-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (!confirm("このレポートを削除しますか？")) return;
        await fetchJson(`${API}/submissions/${btn.dataset.id}`, { method: "DELETE" });
        loadSubmissions();
      });
    });
  }

  // ── 初期化 ────────────────────────────────────────────────

  async function init() {
    await loadSettings();
    state.themes = (await fetchJson(`${API}/themes`)).themes;
    renderThemeListAdmin();
    state.students = (await fetchJson(`${API}/students`)).students;
    renderRosterTable();
    await loadSubmissions();
  }

  init();
})();
