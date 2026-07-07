'use strict';

const passwordInput = document.getElementById('admin-password');
const unlockBtn = document.getElementById('unlock-btn');
const lockMessage = document.getElementById('lock-message');
const settingsPanel = document.getElementById('settings-panel');
const statusMessage = document.getElementById('status-message');
const prepToggle = document.getElementById('part-a-prep-toggle');
const prepStatus = document.getElementById('part-a-prep-status');

let unlocked = false;
let saveTimer = null;

function showLockMessage(msg) {
  lockMessage.textContent = msg;
  lockMessage.classList.remove('hidden');
}

function hideLockMessage() {
  lockMessage.classList.add('hidden');
}

function updatePrepStatus(enabled) {
  prepStatus.textContent = enabled
    ? '準備時間: オン（30秒）'
    : '準備時間: オフ（即録音開始）';
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
  const enabled = data.part_a_prep_enabled !== false;
  prepToggle.checked = enabled;
  updatePrepStatus(enabled);
}

function scheduleSave() {
  if (!unlocked) return;
  clearTimeout(saveTimer);
  saveTimer = setTimeout(async () => {
    try {
      const enabled = prepToggle.checked;
      await saveSettings({
        admin_password: passwordInput.value.trim(),
        part_a_prep_enabled: enabled,
      });
      updatePrepStatus(enabled);
      statusMessage.textContent = '設定を保存しました';
    } catch (err) {
      statusMessage.textContent = '';
      showLockMessage(err.message);
    }
  }, 300);
}

unlockBtn.addEventListener('click', tryUnlock);
passwordInput.addEventListener('keydown', e => {
  if (e.key === 'Enter') tryUnlock();
});
prepToggle.addEventListener('change', scheduleSave);
