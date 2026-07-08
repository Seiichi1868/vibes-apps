'use strict';

const PARTS = ['a', 'b', 'c', 'd'];
const PART_LABELS = {
  a: 'Part A 音読',
  b: 'Part B やり取り',
  c: 'Part C ストーリー',
  d: 'Part D 意見表明',
};
const DEFAULT_SECONDS = { a: 30, b: 10, c: 30, d: 60 };

const passwordInput = document.getElementById('admin-password');
const unlockBtn = document.getElementById('unlock-btn');
const lockMessage = document.getElementById('lock-message');
const settingsPanel = document.getElementById('settings-panel');
const statusMessage = document.getElementById('status-message');
const pageBgLayer = document.getElementById('page-bg-layer');
const bgCurrentLabel = document.getElementById('bg-current-label');
const bgPicker = document.getElementById('bg-picker');
const problemAdmin = document.getElementById('problem-admin');

let unlocked = false;
let saveTimer = null;
let problemSaveTimer = null;
let currentBackgroundId = null;
let problemsData = null;
let problemEditNum = { a: 1, b: 1, c: 1, d: 1 };

function showLockMessage(msg) {
  lockMessage.textContent = msg;
  lockMessage.classList.remove('hidden');
}

function hideLockMessage() {
  lockMessage.classList.add('hidden');
}

function applyBackground(bgId, imageUrl, label) {
  currentBackgroundId = bgId;
  if (pageBgLayer && imageUrl) {
    pageBgLayer.style.backgroundImage = `url("${imageUrl}")`;
  }
  if (bgCurrentLabel && label) {
    bgCurrentLabel.textContent = label;
  }
  document.querySelectorAll('.bg-pick-btn').forEach(btn => {
    btn.classList.toggle('bg-pick-btn-active', btn.dataset.bgId === bgId);
  });
}

function updatePartUI(part, enabled, seconds) {
  const row = document.querySelector(`.admin-part-row[data-part="${part}"]`);
  if (!row) return;

  const secondsInput = row.querySelector(`.prep-seconds[data-part="${part}"]`);
  const statusEl = row.querySelector(`.prep-status[data-part="${part}"]`);
  const secondsRow = row.querySelector('.prep-seconds-row');

  if (secondsInput) secondsInput.disabled = !enabled;
  if (secondsRow) secondsRow.style.opacity = enabled ? '1' : '0.45';

  if (statusEl) {
    statusEl.textContent = enabled
      ? `オン ${seconds}秒`
      : 'オフ';
  }
}

async function fetchProblems() {
  const res = await fetch('/gtec/admin/api/problems');
  if (!res.ok) throw new Error('問題データの取得に失敗しました');
  return res.json();
}

async function saveProblems(payload) {
  const res = await fetch('/gtec/admin/api/problems', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || '問題の保存に失敗しました');
  return data;
}

function problemSelectOptions(selected) {
  return [1, 2, 3, 4].map(n =>
    `<option value="${n}"${n === selected ? ' selected' : ''}>問題${n}</option>`
  ).join('');
}

function renderProblemAdmin() {
  if (!problemAdmin || !problemsData) return;

  problemAdmin.innerHTML = PARTS.map(part => {
    const editNum = problemEditNum[part] || 1;
    const set = problemsData.sets?.[part]?.[String(editNum)] || {};
    const active = problemsData.active?.[part] || 1;

    let fields = '';
    if (part === 'a') {
      fields = `
        <label class="block text-[10px] text-slate-600 mb-1">音読テキスト</label>
        <textarea class="admin-problem-textarea problem-field" data-part="${part}" data-num="${editNum}" data-key="text">${set.text || ''}</textarea>`;
    } else if (part === 'b') {
      fields = `
        <label class="block text-[10px] text-slate-600 mb-1">スケジュール（JSON）</label>
        <textarea class="admin-problem-textarea problem-field" data-part="${part}" data-num="${editNum}" data-key="schedule" rows="4">${JSON.stringify(set.schedule || [], null, 2)}</textarea>
        <label class="block text-[10px] text-slate-600 mt-2 mb-1">質問（JSON）</label>
        <textarea class="admin-problem-textarea problem-field" data-part="${part}" data-num="${editNum}" data-key="questions" rows="5">${JSON.stringify(set.questions || [], null, 2)}</textarea>`;
    } else if (part === 'c') {
      const panels = set.panels || [];
      fields = `
        <label class="block text-[10px] text-slate-600 mb-1">イラスト画像パス</label>
        <input class="admin-problem-input problem-field mb-2" data-part="${part}" data-num="${editNum}" data-key="storyImage" value="${set.storyImage || ''}" placeholder="gtec/images/part-c-story-${editNum}.png" />
        ${[0, 1, 2, 3].map(i => `
          <div class="mt-2">
            <label class="block text-[10px] font-semibold text-violet-700 mb-1">Panel ${i + 1}</label>
            <input class="admin-problem-input problem-field mb-1" data-part="${part}" data-num="${editNum}" data-key="panel-desc-${i}" value="${panels[i]?.description || ''}" placeholder="description" />
            <input class="admin-problem-input problem-field" data-part="${part}" data-num="${editNum}" data-key="panel-ex-${i}" value="${panels[i]?.example || ''}" placeholder="example sentence" />
          </div>
        `).join('')}`;
    } else if (part === 'd') {
      fields = `
        <label class="block text-[10px] text-slate-600 mb-1">トピック（英語）</label>
        <textarea class="admin-problem-textarea problem-field" data-part="${part}" data-num="${editNum}" data-key="topic" rows="3">${set.topic || ''}</textarea>
        <label class="block text-[10px] text-slate-600 mt-2 mb-1">トピック（日本語）</label>
        <textarea class="admin-problem-textarea problem-field" data-part="${part}" data-num="${editNum}" data-key="topicJa" rows="2">${set.topicJa || ''}</textarea>`;
    }

    return `
      <div class="admin-problem-part" data-part="${part}">
        <div class="flex flex-wrap items-center gap-2 mb-2">
          <p class="text-[11px] font-bold text-indigo-800">${PART_LABELS[part]}</p>
          <label class="text-[10px] text-slate-600">既定
            <select class="admin-problem-select problem-active-select ml-1" data-part="${part}">${problemSelectOptions(active)}</select>
          </label>
          <label class="text-[10px] text-slate-600">編集
            <select class="admin-problem-select problem-edit-select ml-1" data-part="${part}">${problemSelectOptions(editNum)}</select>
          </label>
        </div>
        ${fields}
      </div>`;
  }).join('');

  problemAdmin.querySelectorAll('.problem-active-select').forEach(el => {
    el.addEventListener('change', () => {
      problemsData.active[el.dataset.part] = parseInt(el.value, 10) || 1;
      scheduleProblemSave();
    });
  });

  problemAdmin.querySelectorAll('.problem-edit-select').forEach(el => {
    el.addEventListener('change', () => {
      collectProblemFieldsFromUI();
      problemEditNum[el.dataset.part] = parseInt(el.value, 10) || 1;
      renderProblemAdmin();
    });
  });

  problemAdmin.querySelectorAll('.problem-field').forEach(el => {
    el.addEventListener('input', scheduleProblemSave);
  });
}

function collectProblemFieldsFromUI() {
  if (!problemsData) return;
  problemAdmin?.querySelectorAll('.problem-field').forEach(el => {
    const part = el.dataset.part;
    const num = String(el.dataset.num);
    const key = el.dataset.key;
    if (!problemsData.sets[part]) problemsData.sets[part] = {};
    if (!problemsData.sets[part][num]) problemsData.sets[part][num] = {};

    const set = problemsData.sets[part][num];
    if (key === 'text') set.text = el.value;
    else if (key === 'topic') set.topic = el.value;
    else if (key === 'topicJa') set.topicJa = el.value;
    else if (key === 'storyImage') set.storyImage = el.value.trim();
    else if (key === 'schedule') {
      try { set.schedule = JSON.parse(el.value); } catch (_) {}
    } else if (key === 'questions') {
      try { set.questions = JSON.parse(el.value); } catch (_) {}
    } else if (key.startsWith('panel-desc-')) {
      const i = parseInt(key.split('-').pop(), 10);
      if (!set.panels) set.panels = [{}, {}, {}, {}];
      if (!set.panels[i]) set.panels[i] = {};
      set.panels[i].description = el.value;
    } else if (key.startsWith('panel-ex-')) {
      const i = parseInt(key.split('-').pop(), 10);
      if (!set.panels) set.panels = [{}, {}, {}, {}];
      if (!set.panels[i]) set.panels[i] = {};
      set.panels[i].example = el.value;
    }
  });
}

function scheduleProblemSave() {
  if (!unlocked) return;
  clearTimeout(problemSaveTimer);
  problemSaveTimer = setTimeout(async () => {
    try {
      collectProblemFieldsFromUI();
      const saved = await saveProblems({
        admin_password: passwordInput.value.trim(),
        active: problemsData.active,
        sets: problemsData.sets,
      });
      problemsData = saved;
      statusMessage.textContent = '問題を保存しました';
    } catch (err) {
      statusMessage.textContent = '';
      showLockMessage(err.message);
    }
  }, 600);
}

async function fetchSettings() {
  const res = await fetch('/gtec/admin/api/settings');
  if (!res.ok) throw new Error('設定の取得に失敗しました');
  return res.json();
}

async function saveSettings(payload) {
  const res = await fetch('/gtec/admin/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || '保存に失敗しました');
  return data;
}

function collectPayload() {
  const payload = { admin_password: passwordInput.value.trim() };
  PARTS.forEach(part => {
    const toggle = document.querySelector(`.prep-toggle[data-part="${part}"]`);
    const secondsInput = document.querySelector(`.prep-seconds[data-part="${part}"]`);
    payload[`part_${part}_prep_enabled`] = toggle?.checked !== false;
    payload[`part_${part}_prep_seconds`] = parseInt(secondsInput?.value, 10) || DEFAULT_SECONDS[part];
  });
  if (currentBackgroundId) {
    payload.background_id = currentBackgroundId;
  }
  return payload;
}

async function tryUnlock() {
  hideLockMessage();
  const password = passwordInput.value.trim();
  if (!password) {
    showLockMessage('パスワードを入力してください');
    return;
  }

  try {
    const res = await fetch('/gtec/admin/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ admin_password: password }),
    });
    const data = await res.json();
    if (res.status === 403) {
      showLockMessage('パスワードが違います');
      return;
    }
    if (!res.ok) throw new Error(data.error || '解除に失敗しました');

    unlocked = true;
    passwordInput.disabled = true;
    unlockBtn.disabled = true;
    settingsPanel.classList.remove('hidden');
    await loadSettingsIntoUI();
    statusMessage.textContent = '管理設定を解除しました';
  } catch (err) {
    showLockMessage(err.message);
  }
}

async function loadSettingsIntoUI() {
  const data = await fetchSettings();
  problemsData = await fetchProblems();
  PARTS.forEach(part => {
    const enabled = data[`part_${part}_prep_enabled`] !== false;
    const seconds = parseInt(data[`part_${part}_prep_seconds`], 10) || DEFAULT_SECONDS[part];
    const toggle = document.querySelector(`.prep-toggle[data-part="${part}"]`);
    const secondsInput = document.querySelector(`.prep-seconds[data-part="${part}"]`);
    if (toggle) toggle.checked = enabled;
    if (secondsInput) secondsInput.value = seconds;
    updatePartUI(part, enabled, seconds);
    problemEditNum[part] = problemsData.active?.[part] || 1;
  });

  const activeBtn = bgPicker?.querySelector(`.bg-pick-btn[data-bg-id="${data.background_id}"]`);
  applyBackground(
    data.background_id,
    activeBtn?.dataset.bgImage,
    data.background_label || activeBtn?.title,
  );
  renderProblemAdmin();
}

function scheduleSave() {
  if (!unlocked) return;
  clearTimeout(saveTimer);
  saveTimer = setTimeout(async () => {
    try {
      const payload = collectPayload();
      const saved = await saveSettings(payload);
      PARTS.forEach(part => {
        const enabled = saved[`part_${part}_prep_enabled`] !== false;
        const seconds = parseInt(saved[`part_${part}_prep_seconds`], 10) || DEFAULT_SECONDS[part];
        updatePartUI(part, enabled, seconds);
      });
      const activeBtn = bgPicker?.querySelector(`.bg-pick-btn[data-bg-id="${saved.background_id}"]`);
      applyBackground(
        saved.background_id,
        activeBtn?.dataset.bgImage,
        saved.background_label || activeBtn?.title,
      );
      statusMessage.textContent = '保存しました';
    } catch (err) {
      statusMessage.textContent = '';
      showLockMessage(err.message);
    }
  }, 400);
}

unlockBtn.addEventListener('click', tryUnlock);
passwordInput.addEventListener('keydown', e => {
  if (e.key === 'Enter') tryUnlock();
});

document.querySelectorAll('.prep-toggle').forEach(el => {
  el.addEventListener('change', () => {
    const part = el.dataset.part;
    const seconds = parseInt(document.querySelector(`.prep-seconds[data-part="${part}"]`)?.value, 10)
      || DEFAULT_SECONDS[part];
    updatePartUI(part, el.checked, seconds);
    scheduleSave();
  });
});

document.querySelectorAll('.prep-seconds').forEach(el => {
  el.addEventListener('input', scheduleSave);
});

bgPicker?.addEventListener('click', e => {
  const btn = e.target.closest('.bg-pick-btn');
  if (!btn || !unlocked) return;
  applyBackground(btn.dataset.bgId, btn.dataset.bgImage, btn.title);
  scheduleSave();
});
