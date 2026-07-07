'use strict';

const PARTS = ['a', 'b', 'c', 'd'];
const DEFAULT_SECONDS = { a: 30, b: 10, c: 30, d: 60 };

const passwordInput = document.getElementById('admin-password');
const unlockBtn = document.getElementById('unlock-btn');
const lockMessage = document.getElementById('lock-message');
const settingsPanel = document.getElementById('settings-panel');
const statusMessage = document.getElementById('status-message');

let unlocked = false;
let saveTimer = null;

function showLockMessage(msg) {
  lockMessage.textContent = msg;
  lockMessage.classList.remove('hidden');
}

function hideLockMessage() {
  lockMessage.classList.add('hidden');
}

function updatePartUI(part, enabled, seconds) {
  const row = document.querySelector(`.prep-seconds-row .prep-seconds[data-part="${part}"]`)?.closest('.admin-card');
  if (!row) return;

  const secondsInput = row.querySelector(`.prep-seconds[data-part="${part}"]`);
  const statusEl = row.querySelector(`.prep-status[data-part="${part}"]`);
  const secondsRow = row.querySelector('.prep-seconds-row');

  if (secondsInput) secondsInput.disabled = !enabled;
  if (secondsRow) secondsRow.style.opacity = enabled ? '1' : '0.5';

  if (statusEl) {
    statusEl.textContent = enabled
      ? `準備時間: オン（${seconds}秒）`
      : '準備時間: オフ（即開始）';
  }
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
  PARTS.forEach(part => {
    const enabled = data[`part_${part}_prep_enabled`] !== false;
    const seconds = parseInt(data[`part_${part}_prep_seconds`], 10) || DEFAULT_SECONDS[part];
    const toggle = document.querySelector(`.prep-toggle[data-part="${part}"]`);
    const secondsInput = document.querySelector(`.prep-seconds[data-part="${part}"]`);
    if (toggle) toggle.checked = enabled;
    if (secondsInput) secondsInput.value = seconds;
    updatePartUI(part, enabled, seconds);
  });
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
      statusMessage.textContent = '設定を保存しました';
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
