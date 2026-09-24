"use strict";

const UNLOCK_STORAGE_KEY = "debate_admin_unlocked";

const passwordInput = document.getElementById("admin-password");
const unlockBtn = document.getElementById("unlock-btn");
const lockMessage = document.getElementById("lock-message");
const adminSettingsLock = document.getElementById("admin-settings-lock");
const adminSettingsPanel = document.getElementById("admin-settings-panel");
const sensitiveSettings = document.getElementById("sensitive-settings");
const statusMessage = document.getElementById("status-message");
const pageBgLayer = document.getElementById("page-bg-layer");
const bgPicker = document.getElementById("bg-picker");
const bgOpacitySlider = document.getElementById("bg-opacity-slider");
const bgOpacityValue = document.getElementById("bg-opacity-value");
const judgeModelPicker = document.getElementById("judge-model-picker");
const judgeModelCurrent = document.getElementById("judge-model-current");
const opponentModelPicker = document.getElementById("opponent-model-picker");
const opponentModelCurrent = document.getElementById("opponent-model-current");
const sessionsList = document.getElementById("sessions-list");
const sessionsCount = document.getElementById("sessions-count");
const sessionsRefreshBtn = document.getElementById("sessions-refresh-btn");
const transcriptionModePicker = document.getElementById("transcription-mode-picker");

let unlocked = false;
let saveTimer = null;
let notesSaveTimers = new Map();
let currentBackgroundId = null;
let currentJudgeModelMode = "5.6-luna";
let currentOpponentModelMode = "5.6-luna";

function getStoredPassword() {
  try {
    return sessionStorage.getItem(UNLOCK_STORAGE_KEY) || "";
  } catch (_) {
    return "";
  }
}

function saveUnlockState(password) {
  try {
    sessionStorage.setItem(UNLOCK_STORAGE_KEY, password);
  } catch (_) {}
}

function clearUnlockState() {
  try {
    sessionStorage.removeItem(UNLOCK_STORAGE_KEY);
  } catch (_) {}
}

function applyUnlockUI() {
  unlocked = true;
  adminSettingsLock?.classList.add("hidden");
  adminSettingsPanel?.classList.remove("hidden");
  if (sensitiveSettings) {
    sensitiveSettings.classList.remove("opacity-50", "pointer-events-none");
    sensitiveSettings.removeAttribute("aria-disabled");
  }
}

function showLockMessage(msg) {
  if (!lockMessage) return;
  lockMessage.textContent = msg;
  lockMessage.classList.remove("hidden");
}

function hideLockMessage() {
  lockMessage?.classList.add("hidden");
}

function applyBackgroundOpacity(opacity) {
  const value = Math.max(0, Math.min(1, Number(opacity) || 0));
  if (pageBgLayer) pageBgLayer.style.opacity = String(value);
  const percent = Math.round(value * 100);
  if (bgOpacitySlider) bgOpacitySlider.value = String(percent);
  if (bgOpacityValue) bgOpacityValue.textContent = String(percent);
}

function getBackgroundOpacityFromSlider() {
  const percent = parseInt(bgOpacitySlider?.value, 10);
  return Number.isFinite(percent) ? percent / 100 : 0.32;
}

function applyBackground(bgId, imageUrl) {
  currentBackgroundId = bgId;
  if (pageBgLayer && imageUrl) {
    pageBgLayer.style.backgroundImage = `url("${imageUrl}")`;
  }
  document.querySelectorAll(".bg-pick-btn").forEach((btn) => {
    btn.classList.toggle("bg-pick-btn-active", btn.dataset.bgId === bgId);
  });
}

function clampRatingLevel(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(5, Math.round(n)));
}

function renderJudgeModelRatingRow(label, level) {
  const filled = clampRatingLevel(level);
  const segments = Array.from({ length: 5 }, (_, index) => {
    const filledClass = index < filled ? " is-filled" : "";
    return `<span class="debate-mode-rating-seg${filledClass}"></span>`;
  }).join("");
  return `<span class="debate-mode-rating-row">
    <span class="debate-mode-rating-label">${label}</span>
    <span class="debate-mode-rating-bar" aria-label="${label} ${filled}/5">${segments}</span>
  </span>`;
}

function renderJudgeModelOptions(modes, selectedMode) {
  renderModelOptions(judgeModelPicker, "judge_model_mode", modes, selectedMode);
}

function renderOpponentModelOptions(modes, selectedMode) {
  renderModelOptions(opponentModelPicker, "opponent_model_mode", modes, selectedMode);
}

function renderModelOptions(picker, inputName, modes, selectedMode) {
  if (!picker || !Array.isArray(modes) || !modes.length) return;
  picker.innerHTML = modes
    .map((mode) => {
      const id = escapeHtml(mode.id || "");
      const title = escapeHtml(mode.model || mode.label || id);
      const checked = id === selectedMode ? " checked" : "";
      return `<label class="debate-mode-option debate-mode-option--compact debate-mode-option--rated">
        <input type="radio" name="${inputName}" value="${id}"${checked} />
        <span class="debate-mode-option-body">
          <span class="debate-mode-option-title">${title}</span>
          <span class="debate-mode-ratings">
            ${renderJudgeModelRatingRow("コスパ", mode.cost_performance)}
            ${renderJudgeModelRatingRow("性能", mode.performance)}
          </span>
        </span>
      </label>`;
    })
    .join("");
}

function applyJudgeModelMode(mode, activeModel) {
  currentJudgeModelMode = mode || "5.6-luna";
  if (judgeModelCurrent) {
    judgeModelCurrent.textContent = activeModel || "—";
  }
  judgeModelPicker?.querySelectorAll('input[name="judge_model_mode"]').forEach((input) => {
    input.checked = input.value === currentJudgeModelMode;
  });
}

function applyOpponentModelMode(mode, activeModel) {
  currentOpponentModelMode = mode || "5.6-luna";
  if (opponentModelCurrent) {
    opponentModelCurrent.textContent = activeModel || "—";
  }
  opponentModelPicker?.querySelectorAll('input[name="opponent_model_mode"]').forEach((input) => {
    input.checked = input.value === currentOpponentModelMode;
  });
}

function getSelectedJudgeModelMode() {
  const checked = judgeModelPicker?.querySelector('input[name="judge_model_mode"]:checked');
  return checked?.value || currentJudgeModelMode || "5.6-luna";
}

function getSelectedOpponentModelMode() {
  const checked = opponentModelPicker?.querySelector('input[name="opponent_model_mode"]:checked');
  return checked?.value || currentOpponentModelMode || "5.6-luna";
}

async function fetchSettings() {
  const res = await fetch("/debate/admin/api/settings");
  if (!res.ok) throw new Error("設定の取得に失敗しました");
  return res.json();
}

async function saveSettings(payload) {
  const res = await fetch("/debate/admin/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "保存に失敗しました");
  return data;
}

function getSelectedTranscriptionMode() {
  const checked = transcriptionModePicker?.querySelector('input[name="transcription_mode"]:checked');
  return checked?.value === "realtime" ? "realtime" : "batch";
}

function applyTranscriptionMode(mode) {
  const value = mode === "realtime" ? "realtime" : "batch";
  transcriptionModePicker?.querySelectorAll('input[name="transcription_mode"]').forEach((input) => {
    input.checked = input.value === value;
  });
}

function getAdminPassword() {
  return getStoredPassword() || passwordInput?.value.trim() || "";
}

async function loadSettingsIntoUI() {
  const data = await fetchSettings();
  const activeBtn = bgPicker?.querySelector(`.bg-pick-btn[data-bg-id="${data.background_id}"]`);
  applyBackground(data.background_id, activeBtn?.dataset.bgImage);
  applyBackgroundOpacity(data.background_opacity ?? 0.32);
  applyTranscriptionMode(data.transcription_mode ?? "batch");
  renderJudgeModelOptions(data.judge_model_modes || [], data.judge_model_mode || "5.6-luna");
  applyJudgeModelMode(data.judge_model_mode || "5.6-luna", data.judge_model);
  renderOpponentModelOptions(data.judge_model_modes || [], data.opponent_model_mode || "5.6-luna");
  applyOpponentModelMode(data.opponent_model_mode || "5.6-luna", data.opponent_model);
}

function scheduleBackgroundSave() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(async () => {
    try {
      const saved = await saveSettings({
        background_id: currentBackgroundId,
        background_opacity: getBackgroundOpacityFromSlider(),
      });
      const activeBtn = bgPicker?.querySelector(`.bg-pick-btn[data-bg-id="${saved.background_id}"]`);
      applyBackground(saved.background_id, activeBtn?.dataset.bgImage);
      applyBackgroundOpacity(saved.background_opacity ?? 0.32);
      if (statusMessage) statusMessage.textContent = "保存しました";
      hideLockMessage();
    } catch (err) {
      if (statusMessage) statusMessage.textContent = "";
      showLockMessage(err.message);
    }
  }, 300);
}

function scheduleSensitiveSave() {
  if (!unlocked) return;
  clearTimeout(saveTimer);
  saveTimer = setTimeout(async () => {
    try {
      const saved = await saveSettings({
        admin_password: getAdminPassword(),
        transcription_mode: getSelectedTranscriptionMode(),
        judge_model_mode: getSelectedJudgeModelMode(),
        opponent_model_mode: getSelectedOpponentModelMode(),
      });
      applyTranscriptionMode(saved.transcription_mode ?? "batch");
      applyJudgeModelMode(saved.judge_model_mode || "5.6-luna", saved.judge_model);
      applyOpponentModelMode(saved.opponent_model_mode || "5.6-luna", saved.opponent_model);
      if (statusMessage) statusMessage.textContent = "保存しました";
      hideLockMessage();
    } catch (err) {
      if (statusMessage) statusMessage.textContent = "";
      showLockMessage(err.message);
    }
  }, 300);
}

// ── 保存済みセッション一覧（再開・削除） ─────────────────────
function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function splitDateTime(iso) {
  if (!iso) return { date: "—", time: "—" };
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return { date: iso, time: "" };
    return {
      date: d.toLocaleDateString("ja-JP", { year: "numeric", month: "2-digit", day: "2-digit" }),
      time: d.toLocaleTimeString("ja-JP", { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
    };
  } catch (_) {
    return { date: iso, time: "" };
  }
}

function renderSessions(sessions) {
  if (!sessionsList) return;
  if (sessionsCount) sessionsCount.textContent = `${sessions.length}件`;

  if (!sessions.length) {
    sessionsList.innerHTML = '<p class="text-sm text-slate-400">保存されたセッションはありません。</p>';
    return;
  }

  const rows = sessions
    .map((s) => {
      const dt = splitDateTime(s.updated_at || s.created_at);
      const done = s.confirmed_parts === s.total_parts && s.total_parts > 0;
      const progressLabel = done
        ? `<span class="text-emerald-600 font-semibold">完了</span>`
        : `<span>${s.confirmed_parts}/${s.total_parts} 確定</span>` +
          (s.in_progress_parts ? ` ・ <span class="text-amber-600">${s.in_progress_parts} 進行中</span>` : "");

      const transcriptionLabelMap = { batch: "モードA", realtime: "モードB", mixed: "混在" };
      const transcriptionLabel = transcriptionLabelMap[s.transcription_mode] || "";
      const transcriptionMeta = transcriptionLabel
        ? `<span><span class="session-row__meta-key">文字起こし</span> ${transcriptionLabel}</span>`
        : "";

      const modeLabel = s.mode === "solo"
        ? `Solo ${escapeHtml(s.user_side || "")} / ${escapeHtml(s.ai_difficulty || "")}`
        : "通常";
      const modeMeta = `<span><span class="session-row__meta-key">モード</span> ${modeLabel}</span>`;

      let judgeLabel = "";
      if (s.judge_status === "done") {
        const modelLabel = s.judge_model ? escapeHtml(s.judge_model) : "";
        judgeLabel =
          `<span class="text-teal-700 font-semibold">判定: ${escapeHtml(s.judge_winner || "-")}勝利</span>` +
          (modelLabel ? ` <span class="text-slate-400">(${modelLabel})</span>` : "");
      } else if (s.judge_status === "judging") {
        judgeLabel = `<span class="text-amber-600">ジャッジ実行中…</span>`;
      } else if (s.judge_status === "error") {
        judgeLabel = `<span class="text-rose-600">ジャッジ失敗</span>`;
      }

      const copyBadge = s.copied_from_session_id
        ? `<span class="text-violet-600 font-semibold">コピー</span>`
        : "";

      return `
        <div class="session-row" data-session-id="${escapeHtml(s.session_id)}">
          <div class="session-row__main">
            <div class="session-row__body">
              <p class="session-row__title">${escapeHtml(s.motion)}</p>
              <div class="session-row__meta">
                <span><span class="session-row__meta-key">日付</span> ${escapeHtml(dt.date)}</span>
                <span><span class="session-row__meta-key">時刻</span> ${escapeHtml(dt.time)}</span>
                <span>${progressLabel}</span>
                ${modeMeta}
                ${transcriptionMeta}
                ${copyBadge ? `<span>${copyBadge}</span>` : ""}
                ${judgeLabel ? `<span>${judgeLabel}</span>` : ""}
              </div>
              <div class="session-row__notes">
                <span class="session-row__notes-label">備考</span>
                <input type="text" class="session-notes-input session-row__notes-input"
                  data-session-id="${escapeHtml(s.session_id)}"
                  value="${escapeHtml(s.admin_notes || "")}"
                  maxlength="200"
                  placeholder="例: Luna比較用コピー">
              </div>
            </div>
            <div class="session-row__actions">
              <a href="/debate/session/${encodeURIComponent(s.session_id)}"
                class="session-row__btn session-row__btn--resume">再開</a>
              <button type="button" class="session-row__btn session-row__btn--copy btn-copy-session"
                data-session-id="${escapeHtml(s.session_id)}">コピー</button>
              <button type="button" class="session-row__btn session-row__btn--delete btn-delete-session"
                data-session-id="${escapeHtml(s.session_id)}">削除</button>
            </div>
          </div>
        </div>
      `;
    })
    .join("");

  sessionsList.innerHTML = rows;
}

async function loadSessions() {
  if (!sessionsList) return;
  sessionsList.innerHTML = '<p class="text-sm text-slate-400">読み込み中...</p>';
  try {
    const res = await fetch("/debate/admin/api/sessions");
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "セッション一覧の取得に失敗しました");
    renderSessions(data.sessions || []);
  } catch (err) {
    sessionsList.innerHTML = `<p class="text-sm text-rose-600">${escapeHtml(err.message)}</p>`;
  }
}

sessionsRefreshBtn?.addEventListener("click", loadSessions);

function scheduleNotesSave(sessionId, notes) {
  if (!sessionId) return;
  clearTimeout(notesSaveTimers.get(sessionId));
  notesSaveTimers.set(
    sessionId,
    setTimeout(async () => {
      try {
        const res = await fetch(`/debate/admin/api/sessions/${encodeURIComponent(sessionId)}/notes`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ notes }),
        });
        const data = await res.json();
        if (!res.ok || !data.ok) throw new Error(data.error || "備考の保存に失敗しました");
        if (statusMessage) statusMessage.textContent = "備考を保存しました";
        hideLockMessage();
      } catch (err) {
        if (statusMessage) statusMessage.textContent = "";
        showLockMessage(err.message);
      }
    }, 500)
  );
}

sessionsList?.addEventListener("input", (e) => {
  const input = e.target.closest(".session-notes-input");
  if (!input) return;
  scheduleNotesSave(input.dataset.sessionId, input.value.trim());
});

sessionsList?.addEventListener("click", async (e) => {
  const copyBtn = e.target.closest(".btn-copy-session");
  if (copyBtn) {
    const sessionId = copyBtn.dataset.sessionId;
    const notesInput = sessionsList.querySelector(`.session-notes-input[data-session-id="${sessionId}"]`);
    const suggestedNotes = notesInput?.value.trim() || "";
    const defaultNotes = suggestedNotes || `コピー（${new Date().toLocaleDateString("ja-JP")}）`;
    const notes = window.prompt("コピー先セッションの備考（空欄可）", defaultNotes);
    if (notes === null) return;

    copyBtn.disabled = true;
    const originalLabel = copyBtn.textContent;
    copyBtn.textContent = "コピー中...";
    try {
      const res = await fetch(`/debate/admin/api/sessions/${encodeURIComponent(sessionId)}/copy`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes: notes.trim() }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || "コピーに失敗しました");
      if (statusMessage) statusMessage.textContent = "セッションをコピーしました";
      hideLockMessage();
      await loadSessions();
    } catch (err) {
      if (statusMessage) statusMessage.textContent = "";
      showLockMessage(err.message);
      copyBtn.disabled = false;
      copyBtn.textContent = originalLabel;
    }
    return;
  }

  const btn = e.target.closest(".btn-delete-session");
  if (!btn) return;

  const sessionId = btn.dataset.sessionId;
  if (!window.confirm("このセッションの録音・文字起こしデータを完全に削除します。よろしいですか？")) return;

  btn.disabled = true;
  btn.textContent = "削除中...";
  try {
    const res = await fetch(`/debate/admin/api/sessions/${encodeURIComponent(sessionId)}/delete`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || "削除に失敗しました");
    if (statusMessage) statusMessage.textContent = "セッションを削除しました";
    hideLockMessage();
    await loadSessions();
  } catch (err) {
    if (statusMessage) statusMessage.textContent = "";
    showLockMessage(err.message);
    btn.disabled = false;
    btn.textContent = "削除";
  }
});

async function tryUnlock() {
  hideLockMessage();
  const password = passwordInput?.value.trim() || "";
  if (!password) {
    showLockMessage("パスワードを入力してください");
    return;
  }

  try {
    const res = await fetch("/debate/admin/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ admin_password: password }),
    });
    const data = await res.json();
    if (res.status === 403) {
      showLockMessage("パスワードが違います");
      return;
    }
    if (!res.ok) throw new Error(data.error || "解除に失敗しました");

    saveUnlockState(password);
    applyUnlockUI();
    applyTranscriptionMode(data.transcription_mode ?? "batch");
    renderJudgeModelOptions(data.judge_model_modes || [], data.judge_model_mode || "5.6-luna");
    applyJudgeModelMode(data.judge_model_mode || "5.6-luna", data.judge_model);
    renderOpponentModelOptions(data.judge_model_modes || [], data.opponent_model_mode || "5.6-luna");
    applyOpponentModelMode(data.opponent_model_mode || "5.6-luna", data.opponent_model);
    if (statusMessage) statusMessage.textContent = "管理設定を解除しました";
  } catch (err) {
    showLockMessage(err.message);
  }
}

async function restoreUnlockFromStorage() {
  const password = getStoredPassword();
  if (!password) return;

  if (passwordInput) passwordInput.value = password;
  hideLockMessage();

  try {
    const res = await fetch("/debate/admin/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ admin_password: password }),
    });
    const data = await res.json();
    if (res.status === 403) {
      clearUnlockState();
      if (passwordInput) passwordInput.value = "";
      return;
    }
    if (!res.ok) return;

    applyUnlockUI();
    applyTranscriptionMode(data.transcription_mode ?? "batch");
    renderJudgeModelOptions(data.judge_model_modes || [], data.judge_model_mode || "5.6-luna");
    applyJudgeModelMode(data.judge_model_mode || "5.6-luna", data.judge_model);
    renderOpponentModelOptions(data.judge_model_modes || [], data.opponent_model_mode || "5.6-luna");
    applyOpponentModelMode(data.opponent_model_mode || "5.6-luna", data.opponent_model);
  } catch (_) {
    // 保存済み解除の復元に失敗した場合はロックのまま
  }
}

unlockBtn?.addEventListener("click", tryUnlock);
passwordInput?.addEventListener("keydown", (e) => {
  if (e.key === "Enter") tryUnlock();
});

bgPicker?.addEventListener("click", (e) => {
  const btn = e.target.closest(".bg-pick-btn");
  if (!btn) return;
  applyBackground(btn.dataset.bgId, btn.dataset.bgImage);
  scheduleBackgroundSave();
});

judgeModelPicker?.addEventListener("change", () => {
  if (!unlocked) return;
  scheduleSensitiveSave();
});

opponentModelPicker?.addEventListener("change", () => {
  if (!unlocked) return;
  scheduleSensitiveSave();
});

bgOpacitySlider?.addEventListener("input", () => {
  applyBackgroundOpacity(getBackgroundOpacityFromSlider());
  scheduleBackgroundSave();
});

transcriptionModePicker?.addEventListener("change", () => {
  if (!unlocked) return;
  scheduleSensitiveSave();
});

(async function initAdminPage() {
  try {
    await loadSettingsIntoUI();
  } catch (err) {
    showLockMessage(err.message);
  }
  await loadSessions();
  await restoreUnlockFromStorage();
})();
