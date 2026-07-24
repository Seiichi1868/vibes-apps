'use strict';

// ============================================================
//  GTEC Speaking 対策アプリ — フロントエンド
//  Web Speech API で文字起こし → /gtec/evaluate へテキスト送信のみ
// ============================================================

// ─── 1. パートメタデータ（問題本文は API から取得）────────────

const PART_META = {
  A: {
    title: 'Part A：音読 (Reading Aloud)',
    desc: '画面の英文を声に出して読んでください。準備時間 30 秒・解答時間 40 秒です。',
    prepTime: 30,
    recTime: 40,
    maxScore: 4,
  },
  B: {
    title: 'Part B：やり取り (Interacting with Others)',
    desc: 'Part Bは、全部で4問あります。与えられた情報をもとに、質問に対して英語で答えてください。はじめに準備時間が10秒あり、その後質問が始まります。解答時間はそれぞれ15秒です。開始の音が鳴ってから解答を始めてください。',
    prepTime: 10,
    recTime: 15,
    maxScore: 4,
  },
  C: {
    title: 'Part C：ストーリーを話す (Telling a Story)',
    desc: '4 コマのイラストを見て、ストーリーを英語で話してください。準備時間 30 秒・解答時間 60 秒です。',
    prepTime: 30,
    recTime: 60,
    maxScore: 12,
  },
  D: {
    title: 'Part D：意見表明 (Expressing Your Opinion)',
    desc: 'トピックについて自分の意見と理由を英語で述べてください。準備時間 60 秒・解答時間 60 秒です。',
    prepTime: 60,
    recTime: 60,
    maxScore: 11,
  },
};

const DEFAULT_PROBLEMS = {
  active: { a: 1, b: 1, c: 1, d: 1 },
  sets: { a: {}, b: {}, c: {}, d: {} },
};

// ─── 2. アプリ状態 ───────────────────────────────────────────

const App = {
  part: 'A',
  running: false,
  cancelRequested: false,
  submitRequested: false,
  recognition: null,
  settings: {
    part_a_prep_enabled: true, part_a_prep_seconds: 30,
    part_b_prep_enabled: true, part_b_prep_seconds: 10,
    part_c_prep_enabled: true, part_c_prep_seconds: 30,
    part_d_prep_enabled: true, part_d_prep_seconds: 60,
  },
  currentAudio: null,
  currentUtterance: null,
  problems: null,
  selectedProblem: { a: 1, b: 1, c: 1, d: 1 },
};

// ─── 3. 設定・問題読み込み ───────────────────────────────────

async function loadProblems() {
  try {
    const res = await fetch('/gtec/api/problems');
    if (res.ok) {
      App.problems = await res.json();
      for (const p of ['a', 'b', 'c', 'd']) {
        if (!App.selectedProblem[p]) {
          App.selectedProblem[p] = App.problems.active?.[p] || 1;
        }
      }
      return;
    }
  } catch (_) { /* fallback */ }
  App.problems = DEFAULT_PROBLEMS;
}

function getSelectedProblemNum(partId) {
  const key = partId.toLowerCase();
  return App.selectedProblem[key] || App.problems?.active?.[key] || 1;
}

function getPartData(partId) {
  const meta = PART_META[partId] || {};
  const key = partId.toLowerCase();
  const num = getSelectedProblemNum(partId);
  const content = App.problems?.sets?.[key]?.[String(num)] || {};
  return { ...meta, ...content, problemNum: num };
}

function problemPickerHTML(partId) {
  const key = partId.toLowerCase();
  const selected = getSelectedProblemNum(partId);
  const defaultNum = App.problems?.active?.[key] || 1;
  return `
    <div class="problem-picker mb-4" data-part="${partId}">
      <p class="text-xs text-slate-500 mb-2">問題を選んでください${defaultNum !== selected ? '' : `（クラス既定: 問題${defaultNum}）`}</p>
      <div class="grid grid-cols-4 gap-2">
        ${[1, 2, 3, 4].map(n => `
          <button type="button" class="problem-btn${n === selected ? ' problem-btn-active' : ''}"
            data-part="${partId}" data-num="${n}">問題${n}</button>
        `).join('')}
      </div>
    </div>`;
}

function wireProblemPicker(partId) {
  document.querySelectorAll(`.problem-btn[data-part="${partId}"]`).forEach(btn => {
    btn.onclick = async () => {
      const num = parseInt(btn.dataset.num, 10);
      if (!num || App.running) return;
      App.selectedProblem[partId.toLowerCase()] = num;
      await renderPartIdle(partId);
    };
  });
}

// ─── 4. 設定読み込み ─────────────────────────────────────────

async function loadSettings() {
  try {
    const res = await fetch('/gtec/api/settings');
    if (res.ok) {
      App.settings = { ...App.settings, ...(await res.json()) };
      applyBackgroundFromSettings();
    }
  } catch (_) { /* デフォルト設定を使用 */ }
}

function applyBackgroundFromSettings() {
  const image = App.settings.background_image;
  if (!image) return;
  const layer = document.getElementById('page-bg-layer');
  if (layer) {
    layer.style.backgroundImage = `url("/static/${image}")`;
    const opacity = Number(App.settings.background_opacity);
    layer.style.opacity = String(Number.isFinite(opacity) ? opacity : 0.38);
  }
}

function getPrepConfig(partLetter) {
  const p = partLetter.toLowerCase();
  const fallback = PART_META[partLetter.toUpperCase()]?.prepTime ?? 30;
  const enabled = App.settings[`part_${p}_prep_enabled`] !== false;
  const sec = parseInt(App.settings[`part_${p}_prep_seconds`], 10);
  return {
    enabled,
    seconds: Number.isFinite(sec) && sec >= 0 ? sec : fallback,
  };
}

function prepLabel(partLetter) {
  const prep = getPrepConfig(partLetter);
  if (!prep.enabled) return 'なし';
  return `${prep.seconds}秒`;
}

// ─── 4. ユーティリティ ───────────────────────────────────────

const $root = () => document.getElementById('app-root');

function fmt(sec) {
  const m = Math.floor(sec / 60).toString().padStart(2, '0');
  const s = (sec % 60).toString().padStart(2, '0');
  return `${m}:${s}`;
}

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

// Promise でラップしたカウントダウン。cancel / submit 中断可。
function countdown(seconds, onTick) {
  return new Promise(resolve => {
    let remaining = seconds;
    onTick(remaining);
    const id = setInterval(() => {
      if (App.cancelRequested || App.submitRequested) { clearInterval(id); resolve(); return; }
      remaining--;
      onTick(remaining);
      if (remaining <= 0) { clearInterval(id); resolve(); }
    }, 1000);
  });
}

// ─── 5. 単語比較（音読判定アプリと同ロジック・英語専用）──────────

const NUMBER_ONES = [
  'zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine',
  'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen',
  'seventeen', 'eighteen', 'nineteen',
];
const NUMBER_TENS = [
  '', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety',
];
const ENGLISH_NUMBER_WORDS = new Set([
  ...NUMBER_ONES,
  ...NUMBER_TENS.filter(Boolean),
  'hundred', 'thousand', 'million', 'oh',
]);

function intToEnglish(n) {
  const num = Math.floor(Number(n));
  if (!Number.isFinite(num) || num < 0) return '';
  if (num < 20) return NUMBER_ONES[num];
  if (num < 100) {
    const tens = Math.floor(num / 10);
    const ones = num % 10;
    return ones ? `${NUMBER_TENS[tens]} ${NUMBER_ONES[ones]}` : NUMBER_TENS[tens];
  }
  if (num < 1000) {
    const hundreds = Math.floor(num / 100);
    const rest = num % 100;
    if (!rest) return `${NUMBER_ONES[hundreds]} hundred`;
    return `${NUMBER_ONES[hundreds]} hundred ${intToEnglish(rest)}`;
  }
  if (num < 1000000) {
    const thousands = Math.floor(num / 1000);
    const rest = num % 1000;
    if (!rest) return `${intToEnglish(thousands)} thousand`;
    return `${intToEnglish(thousands)} thousand ${intToEnglish(rest)}`;
  }
  return String(num);
}

function expandOrdinals(text) {
  return String(text || '').replace(/\b(\d+)(st|nd|rd|th)\b/gi, (_, digits) =>
    intToEnglish(parseInt(digits, 10))
  );
}

function expandClockTimes(text) {
  return String(text || '').replace(
    /\b(\d{1,2}):(\d{2})\b/g,
    (_, hour, minute) => {
      const h = parseInt(hour, 10);
      const m = parseInt(minute, 10);
      if (h > 23 || m > 59) return `${hour} ${minute}`;
      return `${intToEnglish(h)} ${intToEnglish(m)}`;
    }
  );
}

function expandSpacedClockTimes(text) {
  return String(text || '').replace(/\b(\d{1,2})\s+(\d{2})\b/g, (match, hour, minute) => {
    const h = parseInt(hour, 10);
    const m = parseInt(minute, 10);
    if (h > 23 || m > 59) return match;
    return `${intToEnglish(h)} ${intToEnglish(m)}`;
  });
}

function expandStandaloneNumbers(text) {
  return String(text || '').replace(/\b\d+\b/g, digits => intToEnglish(parseInt(digits, 10)));
}

function normalizeTextForWords(text) {
  let normalized = String(text || '').replace(/\r\n|\r|\n/g, ' ').toLowerCase();
  normalized = expandOrdinals(normalized);
  normalized = expandClockTimes(normalized);
  normalized = expandSpacedClockTimes(normalized);
  normalized = expandStandaloneNumbers(normalized);
  normalized = normalized.replace(/[,.!?;:()[\]{}"""''…—–-]/g, ' ');
  return normalized.replace(/\s+/g, ' ').trim();
}

function extractWordTokens(text) {
  const normalized = normalizeTextForWords(text);
  return normalized ? normalized.split(' ').filter(Boolean) : [];
}

function tokenizeReference(text) {
  return String(text || '')
    .replace(/\r\n|\r|\n/g, ' ')
    .replace(/[,.!?;:()[\]{}"""''…—–-]/g, ' ')
    .split(/\s+/)
    .filter(Boolean)
    .map(display => ({
      display,
      norm: canonicalCompareToken(display) || normalizeSingleToken(display),
    }));
}

function normalizeSingleToken(word) {
  let w = String(word || '').toLowerCase().trim();
  if (/^\d+$/.test(w)) return intToEnglish(parseInt(w, 10));
  return w.replace(/^[^a-z0-9]+|[^a-z0-9]+$/gi, '');
}

function canonicalCompareToken(token) {
  const word = String(token || '').trim().toLowerCase();
  if (!word) return '';
  if (/^\d{1,2}:\d{2}$/.test(word)) {
    const [hour, minute] = word.split(':');
    return `${intToEnglish(parseInt(hour, 10))} ${intToEnglish(parseInt(minute, 10))}`;
  }
  if (/^\d+$/.test(word)) return intToEnglish(parseInt(word, 10));
  if (ENGLISH_NUMBER_WORDS.has(word)) return word;
  return word.replace(/^[^a-z0-9]+|[^a-z0-9]+$/gi, '');
}

function levenshtein(a, b) {
  const m = a.length;
  const n = b.length;
  const dp = Array.from({ length: m + 1 }, () => Array(n + 1).fill(0));
  for (let i = 0; i <= m; i += 1) dp[i][0] = i;
  for (let j = 0; j <= n; j += 1) dp[0][j] = j;
  for (let i = 1; i <= m; i += 1) {
    for (let j = 1; j <= n; j += 1) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      dp[i][j] = Math.min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost);
    }
  }
  return dp[m][n];
}

function tokenMatchScore(refToken, spokenToken) {
  const refNorm = canonicalCompareToken(refToken);
  const spokenNorm = canonicalCompareToken(spokenToken);
  if (!refNorm || !spokenNorm) return -2;
  // スピーキング採点: 大文字・小文字の違いは不一致にしない
  if (refNorm.toLowerCase() === spokenNorm.toLowerCase()) return 3;
  if (levenshtein(refNorm, spokenNorm) <= 1) return 1;
  const refParts = refNorm.split(' ').filter(Boolean);
  const spokenParts = spokenNorm.split(' ').filter(Boolean);
  if (refParts.length > 1 && refParts.join(' ') === spokenNorm) return 3;
  if (spokenParts.length > 1 && spokenParts.join(' ') === refNorm) return 3;
  return -2;
}

function compareWords(referenceWords, spokenWords) {
  const n = referenceWords.length;
  const m = spokenWords.length;
  if (n === 0) return [];
  if (m === 0) return referenceWords.map(word => ({ word, state: 'miss' }));

  const GAP = 1;
  const dp = Array.from({ length: n + 1 }, () => Array(m + 1).fill(0));
  const trace = Array.from({ length: n + 1 }, () => Array(m + 1).fill(null));

  for (let i = 1; i <= n; i += 1) dp[i][0] = -i * GAP;
  for (let j = 1; j <= m; j += 1) dp[0][j] = -j * GAP;

  for (let i = 1; i <= n; i += 1) {
    for (let j = 1; j <= m; j += 1) {
      const match = dp[i - 1][j - 1] + tokenMatchScore(referenceWords[i - 1], spokenWords[j - 1]);
      const skipSpoken = dp[i][j - 1] - GAP;
      const skipRef = dp[i - 1][j] - GAP;
      let best = match;
      let dir = 'diag';
      if (skipSpoken > best) { best = skipSpoken; dir = 'left'; }
      if (skipRef > best) { best = skipRef; dir = 'up'; }
      dp[i][j] = best;
      trace[i][j] = dir;
    }
  }

  const refStates = Array(n).fill('miss');
  let i = n;
  let j = m;
  while (i > 0 || j > 0) {
    const dir = trace[i][j];
    if (i > 0 && j > 0 && dir === 'diag') {
      const score = tokenMatchScore(referenceWords[i - 1], spokenWords[j - 1]);
      refStates[i - 1] = score >= 3 ? 'exact' : score >= 1 ? 'near' : 'miss';
      i -= 1; j -= 1;
    } else if (i > 0 && (j === 0 || dir === 'up')) {
      refStates[i - 1] = 'miss';
      i -= 1;
    } else {
      j -= 1;
    }
  }

  return referenceWords.map((word, idx) => ({ word, state: refStates[idx] }));
}

function computeAccuracyPercent(compared) {
  if (!compared.length) return 0;
  let score = 0;
  compared.forEach(item => {
    if (item.state === 'exact') score += 1;
    else if (item.state === 'near') score += 0.5;
  });
  return Math.round((score / compared.length) * 100);
}

function escapeHTML(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function renderWordComparisonHTML(referenceText, spokenText) {
  const refTokens = tokenizeReference(referenceText);
  const spokenWords = extractWordTokens(spokenText);
  const compared = compareWords(refTokens.map(t => t.norm), spokenWords);
  const percent = computeAccuracyPercent(compared);

  const baseLayer = refTokens.map(t =>
    `<span class="token">${escapeHTML(t.display)}</span>`
  ).join('');
  const highlightLayer = compared.map((item, idx) =>
    `<span class="token ${item.state}">${escapeHTML(refTokens[idx]?.display || item.word)}</span>`
  ).join('');

  return {
    compared,
    percent,
    html: `
      <div class="mb-3">
        <div class="flex items-center justify-between mb-2">
          <p class="text-xs font-semibold text-slate-600">発音一致率</p>
          <span class="text-sm font-bold text-indigo-700">${percent}%</span>
        </div>
        <div class="accuracy-bar mb-2">
          <div class="accuracy-bar-fill" style="width:${percent}%"></div>
        </div>
        <div class="word-overlay-wrap">
          <p class="word-base-layer">${baseLayer}</p>
          <p class="word-highlight-layer">${highlightLayer}</p>
        </div>
        <div class="word-legend">
          <span class="word-legend-item"><span class="token exact">正確</span></span>
          <span class="word-legend-item"><span class="token near">近似</span></span>
          <span class="word-legend-item"><span class="token miss">不一致</span></span>
        </div>
      </div>`,
  };
}

// ─── 6. TTS（ブラウザ合成音声優先 + OpenAI サーバー fallback）────────────

let speakChain = Promise.resolve();
let voicesReadyPromise = null;

function isMobileDevice() {
  return /Mobi|Android|iPad|iPhone|iPod/i.test(navigator.userAgent);
}

function isChromeBrowser() {
  return /Chrome/i.test(navigator.userAgent) && !/Edg|OPR|Brave/i.test(navigator.userAgent);
}

function unlockAudioSync() {
  try {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (AC) {
      const ctx = new AC();
      const buf = ctx.createBuffer(1, 1, 22050);
      const src = ctx.createBufferSource();
      src.buffer = buf;
      src.connect(ctx.destination);
      src.start(0);
      src.onended = () => ctx.close().catch(() => {});
    }
  } catch (_) {}

  // 音声合成もジェスチャー内で primer を流す（iOS でのセッション認証）
  if ('speechSynthesis' in window) {
    try {
      speechSynthesis.cancel();
      const primer = new SpeechSynthesisUtterance(' ');
      primer.volume = 0;
      speechSynthesis.speak(primer);
    } catch (_) {}
  }
}

function ensureVoicesLoaded() {
  if (!('speechSynthesis' in window)) return Promise.resolve([]);
  if (!voicesReadyPromise) {
    voicesReadyPromise = new Promise(resolve => {
      const tryResolve = () => {
        const voices = speechSynthesis.getVoices();
        if (voices.length) { resolve(voices); return true; }
        return false;
      };
      if (tryResolve()) return;
      speechSynthesis.addEventListener('voiceschanged', () => tryResolve(), { once: true });
      setTimeout(() => resolve(speechSynthesis.getVoices()), 1500);
    });
  }
  return voicesReadyPromise;
}

function getEnglishVoice() {
  if (!('speechSynthesis' in window)) return null;
  const voices = speechSynthesis.getVoices();
  if (!voices.length) return null;

  const enUS = voices.filter(v => v.lang === 'en-US' || v.lang.startsWith('en-US'));
  const pool = enUS.length ? enUS : voices.filter(v => v.lang.startsWith('en'));
  if (!pool.length) return null;

  // iOS/Android: ローカル声を優先
  if (isMobileDevice()) {
    const local = pool.find(v => v.localService);
    if (local) return local;
  }
  if (isChromeBrowser()) {
    const google = pool.find(v => /google/i.test(v.name));
    if (google) return google;
    const online = pool.find(v => !v.localService);
    if (online) return online;
  } else {
    const local = pool.find(v => v.localService);
    if (local) return local;
    const named = pool.find(v => /samantha|karen|daniel|alex/i.test(v.name));
    if (named) return named;
  }
  return pool[0];
}

/** 現在の音声・合成音声を完全停止 */
function stopCurrentSpeech() {
  if (App.currentAudio) {
    App.currentAudio.pause();
    App.currentAudio = null;
  }
  if ('speechSynthesis' in window) {
    speechSynthesis.cancel();
    App.currentUtterance = null;
  }
}

function speak(text) {
  speakChain = speakChain.then(() => speakOnce(text)).catch(() => {});
  return speakChain;
}

/**
 * ブラウザ合成音声を優先。3 秒以内に再生開始しなければサーバー TTS へ fallback。
 * cancelRequested / submitRequested 時は即座に return。
 */
async function speakOnce(text) {
  const content = String(text || '').trim();
  if (!content || App.cancelRequested) return;

  // 必ず先に既存の音声・合成音声を完全停止（Chrome 二重再生防止）
  stopCurrentSpeech();

  // ブラウザ合成音声を優先（費用ゼロ）
  const voices = await ensureVoicesLoaded();
  if (voices.length > 0 && !App.cancelRequested) {
    const ok = await speakWithBrowser(content);
    if (ok) return;
  }

  // サーバー TTS fallback（声が全くない環境向け）
  if (!App.cancelRequested) {
    await speakFromServer(content).catch(err => console.warn('Server TTS:', err));
  }
}

/**
 * ブラウザ合成音声で再生。
 * @returns {Promise<boolean>} 再生が開始されたら true、タイムアウト/エラーなら false
 */
function speakWithBrowser(text) {
  if (!('speechSynthesis' in window)) return Promise.resolve(false);
  const voices = speechSynthesis.getVoices();
  if (!voices.length) return Promise.resolve(false);

  return new Promise(resolve => {
    if (App.cancelRequested) { resolve(false); return; }

    speechSynthesis.cancel();

    setTimeout(() => {
      if (App.cancelRequested) { resolve(false); return; }

      const makeUtt = (fallbackVoice = false) => {
        const utt = new SpeechSynthesisUtterance(text);
        utt.lang = 'en-US';
        utt.rate = 1;
        utt.pitch = 1;
        utt.volume = 1;
        if (!fallbackVoice) {
          const voice = getEnglishVoice();
          if (voice) { utt.voice = voice; utt.lang = voice.lang || 'en-US'; }
        }
        return utt;
      };

      let started = false;
      let resolved = false;
      const done = (val) => { if (!resolved) { resolved = true; App.currentUtterance = null; resolve(val); } };

      // 3 秒以内に onstart が来なければ false（サーバー TTS へ）
      const failTimer = setTimeout(() => { if (!started) { speechSynthesis.cancel(); done(false); } }, 3000);

      const utt = makeUtt();
      App.currentUtterance = utt;

      utt.onstart = () => { started = true; clearTimeout(failTimer); };
      utt.onend   = () => { clearTimeout(failTimer); done(true); };
      utt.onerror = () => { clearTimeout(failTimer); done(false); };

      speechSynthesis.speak(utt);

      // Chrome: voice 指定で始まらない場合、voice なしで再試行
      setTimeout(() => {
        if (!started && !App.cancelRequested) {
          speechSynthesis.cancel();
          const utt2 = makeUtt(true);
          App.currentUtterance = utt2;
          utt2.onstart = () => { started = true; clearTimeout(failTimer); };
          utt2.onend   = () => { clearTimeout(failTimer); done(true); };
          utt2.onerror = () => { clearTimeout(failTimer); done(false); };
          speechSynthesis.speak(utt2);
        }
      }, 400);
    }, 80);
  });
}

/**
 * スマホで gesturecontext 内から直接呼ぶ TTS（play ボタン tap 時）
 */
function speakInGestureContext(text) {
  return new Promise(resolve => {
    if (!('speechSynthesis' in window)) { resolve(); return; }
    speechSynthesis.cancel();
    const utt = new SpeechSynthesisUtterance(text);
    utt.lang = 'en-US';
    utt.rate = 1;
    utt.pitch = 1;
    utt.volume = 1;
    const voice = getEnglishVoice();
    if (voice) { utt.voice = voice; utt.lang = voice.lang || 'en-US'; }
    App.currentUtterance = utt;
    utt.onend   = () => { App.currentUtterance = null; resolve(); };
    utt.onerror = () => { App.currentUtterance = null; resolve(); };
    speechSynthesis.speak(utt);
  });
}

/** サーバー TTS fallback（費用発生 ── 合成音声が使えない環境のみ）*/
async function speakFromServer(text) {
  const res = await fetch('/gtec/api/tts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw new Error(`TTS ${res.status}`);
  const { url } = await res.json();
  return new Promise((resolve, reject) => {
    const audio = new Audio(url);
    audio.playsInline = true;
    App.currentAudio = audio;
    const cleanup = () => { audio.onended = audio.onerror = null; if (App.currentAudio === audio) App.currentAudio = null; };
    audio.onended = () => { cleanup(); resolve(); };
    audio.onerror = () => { cleanup(); reject(new Error('Audio playback failed')); };
    audio.play().catch(reject);
  });
}

// ─── 5. 音声認識（Web Speech API）──────────────────────────

function checkSpeechSupport() {
  return !!(window.SpeechRecognition || window.webkitSpeechRecognition);
}

/**
 * 最大 maxSeconds 秒録音し { text, duration } を返す Promise。
 * transcriptEl が渡されれば、そこにリアルタイム字幕を表示する。
 */
function startRecording(maxSeconds, transcriptEl) {
  return new Promise((resolve, reject) => {
    if (!checkSpeechSupport()) {
      reject(new Error('このブラウザは音声認識に対応していません。Chrome をお使いください。'));
      return;
    }

    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    const rec = new SpeechRec();
    App.recognition = rec;
    rec.lang = 'en-US';
    rec.continuous = true;
    rec.interimResults = true;
    rec.maxAlternatives = 1;

    let finalText = '';
    const startMs = Date.now();
    let stopTimer = null;
    let finished = false;

    const finish = () => {
      if (finished) return;
      finished = true;
      clearTimeout(stopTimer);
      App.recognition = null;
      const duration = (Date.now() - startMs) / 1000;
      resolve({ text: finalText.trim(), duration });
    };

    const scheduleStop = () => {
      clearTimeout(stopTimer);
      const remaining = maxSeconds * 1000 - (Date.now() - startMs);
      if (remaining <= 0) {
        try { rec.stop(); } catch (_) {}
        return;
      }
      stopTimer = setTimeout(() => {
        try { rec.stop(); } catch (_) {}
      }, remaining);
    };

    rec.onresult = e => {
      let interim = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) finalText += t + ' ';
        else interim += t;
      }
      if (transcriptEl) {
        transcriptEl.innerHTML =
          `<span class="text-slate-800">${finalText}</span>` +
          `<span class="text-slate-400 italic">${interim}</span>`;
      }
    };

    rec.onend = () => {
      if (App.cancelRequested || App.submitRequested) { finish(); return; }
      const elapsed = (Date.now() - startMs) / 1000;
      if (elapsed < maxSeconds - 0.5) {
        try {
          rec.start();
          scheduleStop();
          return;
        } catch (_) { /* 再起動不可 → 終了 */ }
      }
      finish();
    };

    rec.onerror = e => {
      if (App.cancelRequested || App.submitRequested) { finish(); return; }
      clearTimeout(stopTimer);
      App.recognition = null;
      if (e.error === 'no-speech' || e.error === 'aborted') {
        const elapsed = (Date.now() - startMs) / 1000;
        if (elapsed < maxSeconds - 0.5 && !App.cancelRequested) {
          try {
            App.recognition = rec;
            rec.start();
            scheduleStop();
            return;
          } catch (_) {}
        }
        finish();
      } else {
        reject(new Error(`音声認識エラー: ${e.error}`));
      }
    };

    try {
      rec.start();
      scheduleStop();
    } catch (err) {
      App.recognition = null;
      reject(err);
    }
  });
}

// ─── 6. API 呼び出し ─────────────────────────────────────────

async function callEvaluate(payload) {
  const res = await fetch('/gtec/evaluate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `HTTP ${res.status}`);
  }
  return res.json();
}

// ─── 7. UI パーツ ────────────────────────────────────────────

function cardWrap(html) {
  return `<div class="glass-card rounded-2xl p-5 mb-4">${html}</div>`;
}

function timerDisplay(sec, phase) {
  const color =
    phase === 'prep' ? 'text-sky-600' :
    sec <= 5         ? 'text-red-600 animate-pulse' :
    sec <= 10        ? 'text-orange-500' : 'text-emerald-600';
  const label = phase === 'prep' ? '準備時間' : '解答時間';
  const bg    = phase === 'prep' ? 'bg-sky-50 border-sky-200' : 'bg-emerald-50 border-emerald-200';
  return `
    <div class="flex flex-col items-center ${bg} border rounded-2xl p-5 mb-4">
      <span class="text-xs font-semibold uppercase tracking-widest text-slate-500 mb-1">${label}</span>
      <span class="font-mono font-black text-6xl ${color} tabular-nums">${fmt(sec)}</span>
    </div>`;
}

function recIndicator(show) {
  if (!show) return '';
  return `
    <div class="flex items-center gap-2 mb-3">
      <span class="inline-block w-3 h-3 rounded-full bg-red-500 animate-pulse"></span>
      <span class="text-sm font-semibold text-red-600">録音中 — 英語で話してください</span>
    </div>`;
}

function transcriptBox(id) {
  return `
    <div class="bg-slate-50 border border-slate-200 rounded-xl p-3 min-h-[60px] text-sm leading-relaxed" id="${id}">
      <span class="text-slate-400 italic">（ここに文字起こしが表示されます）</span>
    </div>`;
}

function startBtn(label = 'スタート', id = 'start-btn') {
  return `
    <button id="${id}"
      class="w-full py-3.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 active:scale-95
             text-white font-bold text-base shadow transition-all">
      ▶ ${label}
    </button>`;
}

function renderLoading(msg = '採点中...') {
  $root().innerHTML = `
    <div class="flex flex-col items-center justify-center py-16 gap-4">
      <div class="w-12 h-12 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin"></div>
      <p class="text-indigo-700 font-semibold text-lg">${msg}</p>
      <p class="text-slate-400 text-sm">OpenAI で採点しています。しばらくお待ちください。</p>
    </div>`;
}

// ─── 8. 結果レンダラ ─────────────────────────────────────────

function scoreCircle(score, max, label, color = 'indigo') {
  const colors = {
    indigo: ['bg-indigo-600', 'text-indigo-700'],
    sky:    ['bg-sky-500',    'text-sky-700'],
    violet: ['bg-violet-500', 'text-violet-700'],
    teal:   ['bg-teal-500',   'text-teal-700'],
    emerald:['bg-emerald-500','text-emerald-700'],
    amber:  ['bg-amber-500',  'text-amber-700'],
    rose:   ['bg-rose-500',   'text-rose-700'],
  };
  const [bg, txt] = colors[color] || colors.indigo;
  const pct = max > 0 ? Math.round((score / max) * 100) : 0;
  const grade = pct >= 80 ? '🌟' : pct >= 60 ? '👍' : pct >= 40 ? '📝' : '💪';
  return `
    <div class="flex flex-col items-center gap-1">
      <div class="w-16 h-16 rounded-full ${bg} flex items-center justify-center shadow">
        <span class="text-white font-black text-xl">${score}</span>
      </div>
      <span class="text-xs ${txt} font-semibold text-center leading-tight">${label}</span>
      <span class="text-xs text-slate-400">/ ${max}</span>
      <span class="text-base">${grade}</span>
    </div>`;
}

function feedbackBlockPartB(fb) {
  if (!fb) return '';

  const corrections = (fb.corrections || fb.grammar_corrections || []).map(c =>
    `<li class="mb-1">
      <span class="line-through text-red-400">${escapeHTML(c.original)}</span>
      <span class="mx-1 text-slate-400">→</span>
      <span class="text-emerald-700 font-medium">${escapeHTML(c.corrected)}</span>
      ${c.explanation ? `<span class="text-slate-500 text-xs"> (${escapeHTML(c.explanation)})</span>` : ''}
    </li>`
  );

  (fb.upgrade_vocabulary || []).forEach(v => {
    corrections.push(
      `<li class="mb-1">
        <span class="line-through text-red-400">${escapeHTML(v.word)}</span>
        <span class="mx-1 text-slate-400">→</span>
        <span class="text-emerald-700 font-medium">${escapeHTML(v.suggestion)}</span>
      </li>`
    );
  });

  if (!corrections.length) return '';

  return `
    <div class="bg-orange-50 border border-orange-200 rounded-xl p-3 text-sm">
      <p class="font-semibold text-orange-700 mb-2">📝 文法・語彙の訂正</p>
      <ul class="space-y-1 text-slate-700">${corrections.join('')}</ul>
    </div>`;
}

function mergePartBFeedback(results) {
  const corrections = [];
  results.forEach(r => {
    const fb = r.feedback || {};
    (fb.corrections || fb.grammar_corrections || []).forEach(c => corrections.push(c));
    (fb.upgrade_vocabulary || []).forEach(v => {
      corrections.push({ original: v.word, corrected: v.suggestion, explanation: '' });
    });
  });
  return { corrections };
}

function feedbackBlock(fb) {
  if (!fb) return '';

  const corrections = (fb.corrections || fb.grammar_corrections || []).map(c =>
    `<li class="mb-1">
      <span class="line-through text-red-400">${escapeHTML(c.original)}</span>
      <span class="mx-1 text-slate-400">→</span>
      <span class="text-emerald-700 font-medium">${escapeHTML(c.corrected)}</span>
      ${c.explanation ? `<span class="text-slate-500 text-xs"> (${escapeHTML(c.explanation)})</span>` : ''}
    </li>`
  );

  (fb.upgrade_vocabulary || []).forEach(v => {
    corrections.push(
      `<li class="mb-1">
        <span class="line-through text-red-400">${escapeHTML(v.word)}</span>
        <span class="mx-1 text-slate-400">→</span>
        <span class="text-emerald-700 font-medium">${escapeHTML(v.suggestion)}</span>
      </li>`
    );
  });

  if (!corrections.length) return '';

  return `
    <div class="bg-orange-50 border border-orange-200 rounded-xl p-3 text-sm">
      <p class="font-semibold text-orange-700 mb-2">📝 文法・語彙の訂正</p>
      <ul class="space-y-1 text-slate-700">${corrections.join('')}</ul>
    </div>`;
}

function retryBtn() {
  return `
    <button id="retry-btn"
      class="mt-4 w-full py-3 rounded-xl border-2 border-indigo-600 text-indigo-700 font-bold
             hover:bg-indigo-50 active:scale-95 transition-all">
      🔁 もう一度練習する
    </button>`;
}

function submitBtn(label = 'ここで提出する（早く終わった場合）') {
  return `
    <button id="submit-btn"
      class="mt-3 w-full py-3 rounded-xl bg-emerald-600 hover:bg-emerald-700 active:scale-95
             text-white font-bold text-sm shadow transition-all">
      ✅ ${label}
    </button>`;
}

function wireSubmitBtn() {
  App.submitRequested = false;
  const btn = document.getElementById('submit-btn');
  if (btn) {
    btn.addEventListener('click', () => {
      App.submitRequested = true;
      stopAllMedia();
    }, { once: true });
  }
}

// ─── 9. Part A ───────────────────────────────────────────────

async function runPartA() {
  const d = getPartData('A');
  if (App.cancelRequested) return;

  await renderPartIdle('A');
  await waitForClick('start-btn');
  if (App.cancelRequested) return;
  setStopButtonVisible(true);

  const prep = getPrepConfig('A');

  // prep（管理設定でオフの場合はスキップ）
  if (prep.enabled) {
    let timerEl;
    $root().innerHTML = cardWrap(`
      <p class="text-xs font-bold text-indigo-600 uppercase tracking-wider mb-3">${d.title} — 準備</p>
      <div id="timer-wrap"></div>
      <div class="bg-indigo-50 border border-indigo-200 rounded-xl p-4 text-base leading-relaxed text-slate-800 font-medium">
        ${d.text}
      </div>
      <p class="text-center text-sm text-slate-400 mt-3">英文をよく読んで発音を確認してください</p>
    `);
    timerEl = document.getElementById('timer-wrap');
    await countdown(prep.seconds, sec => { timerEl.innerHTML = timerDisplay(sec, 'prep'); });
    if (App.cancelRequested) return;
  }

  // recording
  let timerEl;
  let transEl;
  $root().innerHTML = cardWrap(`
    <p class="text-xs font-bold text-red-600 uppercase tracking-wider mb-3">${d.title} — 録音</p>
    <div id="timer-wrap"></div>
    ${recIndicator(true)}
    <div class="bg-indigo-50 border border-indigo-200 rounded-xl p-4 text-base leading-relaxed text-slate-800 font-medium mb-3">
      ${d.text}
    </div>
    <p class="text-xs text-slate-400 mb-1">文字起こし</p>
    ${transcriptBox('transcript-el')}
    ${submitBtn()}
  `);
  timerEl  = document.getElementById('timer-wrap');
  transEl  = document.getElementById('transcript-el');
  wireSubmitBtn();

  const [{ text, duration }] = await Promise.all([
    startRecording(d.recTime, transEl),
    countdown(d.recTime, sec => { timerEl.innerHTML = timerDisplay(sec, 'rec'); }),
  ]);
  App.submitRequested = false;
  if (App.cancelRequested) return;
  if (!App.running) return;

  stopRecognition();
  setStopButtonVisible(false);
  renderLoading('Part A 採点中...');

  try {
    const result = await callEvaluate({
      part: 'A', text, duration,
      target_text: d.text,
    });
    renderPartAResult(result, text, duration, d.text);
  } catch (e) {
    renderError(e.message);
  }
}

function renderPartAResult(result, text, duration, targetText) {
  const s = result.scores || {};
  const wpm = result.wpm_calculated || 0;
  const comparison = renderWordComparisonHTML(targetText, text);

  $root().innerHTML = `
    <div class="mb-4">${cardWrap(`
      <p class="text-xs font-bold text-indigo-600 uppercase tracking-wider mb-4">Part A 結果</p>
      <div class="flex justify-around mb-4">
        ${scoreCircle(s.fluency_pronunciation ?? 0, 4, '発音・流ちょうさ', 'indigo')}
      </div>
      <div class="text-xs text-slate-500 text-center mb-4">
        推定 WPM: <strong>${wpm}</strong>（目安: 120〜150）
      </div>
      ${comparison.html}
      <p class="text-xs text-slate-400 mb-1">あなたの回答（文字起こし）</p>
      <div class="bg-slate-50 border border-slate-200 rounded-xl p-3 text-sm text-slate-700 mb-4">${escapeHTML(text) || '（認識できませんでした）'}</div>
      ${retryBtn()}
    `)}</div>`;
  document.getElementById('retry-btn').onclick = () => startPart('A');
}

// ─── 10. Part B ──────────────────────────────────────────────

function buildScheduleHTML(schedule) {
  if (schedule.some(r => Object.prototype.hasOwnProperty.call(r, 'date'))) {
    let rows = '';
    for (let i = 0; i < schedule.length; i++) {
      const row = schedule[i];
      const previousActivity = schedule[i - 1]?.activity;
      const startsActivity = row.activity && row.activity !== previousActivity;
      let rowSpan = 1;
      if (startsActivity) {
        while (schedule[i + rowSpan]?.activity === row.activity) rowSpan++;
      }
      rows += `
        <tr class="bg-white border-b border-slate-300 last:border-b-0">
          <td class="w-24 px-3 py-2 text-center font-bold text-slate-800 border-r border-slate-300">
            <span class="${row.publicHoliday ? 'inline-block border-2 border-sky-600 px-2 py-0.5' : ''}">
              ${escapeHTML(row.date || '')}
            </span>
          </td>
          ${startsActivity
            ? `<td rowspan="${rowSpan}" class="px-4 py-2 text-center align-middle font-semibold text-lg italic text-slate-800">
                ${escapeHTML(row.activity)}
               </td>`
            : (!row.activity ? '<td class="px-4 py-2"></td>' : '')}
        </tr>`;
    }
    return `
      <table class="w-full border-collapse text-sm">
        <tbody>${rows}</tbody>
      </table>
      <p class="px-3 py-2 text-xs text-slate-600 bg-slate-50 border-t border-slate-300">
        <span class="inline-block w-9 h-4 border-2 border-sky-600 align-middle mr-1"></span>
        = public holiday
      </p>`;
  }

  const rows = schedule.map((r, i) =>
    `<tr class="${i % 2 === 0 ? 'bg-sky-50' : 'bg-white'}">
      <td class="px-3 py-2 font-mono text-xs text-sky-700 whitespace-nowrap">${escapeHTML(r.time || '')}</td>
      <td class="px-3 py-2 font-semibold text-slate-800 text-sm">${escapeHTML(r.activity || '')}</td>
      <td class="px-3 py-2 text-slate-500 text-xs">${escapeHTML(r.place || '')}</td>
    </tr>`
  ).join('');
  return `
    <table class="w-full text-left border-collapse rounded-xl overflow-hidden text-sm">
      <thead>
        <tr class="bg-sky-600 text-white">
          <th class="px-3 py-2 font-semibold">時刻</th>
          <th class="px-3 py-2 font-semibold">予定</th>
          <th class="px-3 py-2 font-semibold">場所</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function buildPartBInformationHTML(d) {
  return `
    ${d.heading ? `<p class="text-lg font-semibold text-slate-800 underline mb-3">${escapeHTML(d.heading)}</p>` : ''}
    ${d.instructionJa ? `
      <div class="border border-slate-300 rounded-lg px-4 py-3 mb-4 text-sm leading-relaxed text-slate-700">
        ${escapeHTML(d.instructionJa)}
      </div>` : ''}
    <div class="border border-sky-200 rounded-xl overflow-hidden">${buildScheduleHTML(d.schedule || [])}</div>`;
}

async function runPartB() {
  const d = getPartData('B');
  if (App.cancelRequested) return;

  await renderPartIdle('B');
  await waitForClick('start-btn');
  if (App.cancelRequested) return;
  setStopButtonVisible(true);

  const prep = getPrepConfig('B');
  const recordings = [];
  let earlySubmit = false;
  const mobile = isMobileDevice();

  // Part B の準備時間は、全質問の開始前に1回だけ設ける。
  if (prep.enabled) {
    let timerEl;
    $root().innerHTML = cardWrap(`
      <p class="text-xs font-bold text-sky-600 uppercase tracking-wider mb-3">${d.title} — 準備</p>
      <div id="timer-wrap"></div>
      ${buildPartBInformationHTML(d)}
      <p class="text-center text-sm text-slate-400 mt-3">予定表を確認してください</p>
    `);
    timerEl = document.getElementById('timer-wrap');
    await countdown(prep.seconds, sec => { timerEl.innerHTML = timerDisplay(sec, 'prep'); });
    if (App.cancelRequested) return;
  }

  for (let qi = 0; qi < d.questions.length; qi++) {
    if (App.cancelRequested) return;
    const q = d.questions[qi];

    // TTS フェーズ
    if (mobile) {
      // スマホ: ユーザーがタップするまで待つ → ジェスチャー内で即座に読み上げ
      $root().innerHTML = cardWrap(`
        <p class="text-xs font-bold text-sky-600 uppercase tracking-wider mb-1">${d.title} — 質問 ${qi + 1} / ${d.questions.length}</p>
        <div class="mb-4">${buildPartBInformationHTML(d)}</div>
        <button id="hear-btn"
          class="w-full py-4 rounded-xl bg-sky-600 hover:bg-sky-700 active:scale-95 text-white font-bold text-base shadow-lg transition-all">
          🔊 タップして質問を聞く（Q${qi + 1}）
        </button>
      `);
      await new Promise(resolve => {
        const btn = document.getElementById('hear-btn');
        if (!btn) { resolve(); return; }
        btn.addEventListener('click', () => {
          btn.disabled = true;
          btn.innerHTML = '<span class="opacity-70">🔊 読み上げ中...</span>';
          speakInGestureContext(q.text).then(resolve);
        }, { once: true });
      });
    } else {
      // PC: 自動読み上げ
      $root().innerHTML = cardWrap(`
        <p class="text-xs font-bold text-sky-600 uppercase tracking-wider mb-1">${d.title} — 質問 ${qi + 1} / ${d.questions.length}</p>
        <div class="bg-sky-50 border border-sky-200 rounded-2xl p-4 mb-4 text-center">
          <span class="text-2xl">🔊</span>
          <p class="text-sky-700 font-semibold mt-1">質問を読み上げています...</p>
        </div>
        ${buildPartBInformationHTML(d)}
      `);
      await speak(q.text);
    }
    if (App.cancelRequested) return;
    await sleep(300);

    // recording
    let timerEl;
    let transEl;
    $root().innerHTML = cardWrap(`
      <p class="text-xs font-bold text-red-600 uppercase tracking-wider mb-1">${d.title} — Q${qi + 1} / ${d.questions.length} 解答</p>
      <div id="timer-wrap"></div>
      ${recIndicator(true)}
      <div class="mb-3">${buildPartBInformationHTML(d)}</div>
      <p class="text-xs text-slate-400 mb-1">文字起こし</p>
      ${transcriptBox('transcript-el')}
      ${submitBtn(`Q${qi + 1} の回答でここまで提出`)}
    `);
    timerEl = document.getElementById('timer-wrap');
    transEl = document.getElementById('transcript-el');
    wireSubmitBtn();

    const [{ text, duration }] = await Promise.all([
      startRecording(d.recTime, transEl),
      countdown(d.recTime, sec => { timerEl.innerHTML = timerDisplay(sec, 'rec'); }),
    ]);
    const wasSubmit = App.submitRequested;
    App.submitRequested = false;
    if (App.cancelRequested || !App.running) return;
    stopRecognition();
    recordings.push({ text, duration, question: q });

    if (wasSubmit) { earlySubmit = true; break; }
  }

  if (App.cancelRequested || !App.running) return;
  setStopButtonVisible(false);
  const qCount = recordings.length;
  renderLoading(`Part B 採点中... (${qCount}問)`);

  // 空回答はスキップして採点
  const answeredRecordings = recordings.filter(r => r.text.trim());
  if (!answeredRecordings.length) {
    renderError('回答が録音されていません。もう一度練習してください。');
    return;
  }

  try {
    const results = await Promise.all(
      answeredRecordings.map(r =>
        callEvaluate({
          part: 'B',
          text: r.text,
          duration: r.duration,
          question: r.question.text,
          context: r.question.context,
        })
      )
    );
    renderPartBResult(results, answeredRecordings, recordings.length);
  } catch (e) {
    renderError(e.message);
  }
}

function renderPartBResult(results, recordings, totalQCount = 4) {
  const total = results.reduce((s, r) => s + (r.scores?.goal_achievement ?? 0), 0);
  const answeredCount = recordings.length;
  const partialNote = answeredCount < totalQCount
    ? `<p class="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mb-4">
        ⚡ ${answeredCount} / ${totalQCount} 問を提出しました
       </p>`
    : '';

  const qCards = results.map((r, i) => {
    const score = r.scores?.goal_achievement ?? 0;
    const badge = score === 1
      ? '<span class="text-emerald-600 font-bold">✅ 1点</span>'
      : '<span class="text-red-500 font-bold">❌ 0点</span>';
    const examples = (recordings[i].question.examples || [])
      .map(example => `<li>${escapeHTML(example)}</li>`)
      .join('');
    return `
      <div class="border border-slate-200 rounded-xl p-3 mb-2">
        <p class="text-xs font-semibold text-sky-600 mb-1">Q${i + 1}: ${escapeHTML(recordings[i].question.text)}</p>
        <p class="text-sm text-slate-700 mb-1">回答: <em>"${escapeHTML(recordings[i].text) || '（認識できませんでした）'}"</em></p>
        <div class="flex items-center gap-2">${badge}</div>
        ${examples ? `
          <div class="mt-3 bg-sky-50 border border-sky-100 rounded-lg px-3 py-2">
            <p class="text-xs font-bold text-sky-700 mb-1">解答例</p>
            <ul class="list-disc pl-5 text-xs text-slate-700 space-y-1">${examples}</ul>
          </div>` : ''}
      </div>`;
  }).join('');

  $root().innerHTML = cardWrap(`
    <p class="text-xs font-bold text-sky-600 uppercase tracking-wider mb-4">Part B 結果</p>
    ${partialNote}
    <div class="flex justify-around mb-5">
      ${scoreCircle(total, answeredCount, 'Goal合計', 'sky')}
    </div>
    ${qCards}
    ${feedbackBlockPartB(mergePartBFeedback(results))}
    ${retryBtn()}
  `);
  document.getElementById('retry-btn').onclick = () => startPart('B');
}

// ─── 11. Part C ──────────────────────────────────────────────

function buildStoryComic(imageSrc) {
  if (!imageSrc) {
    return `
      <div class="part-c-comic part-c-comic-placeholder mb-4">
        <p class="text-sm text-slate-500 text-center py-8">4コマのイラストは準備中です</p>
      </div>`;
  }
  return `
    <div class="part-c-comic mb-4">
      <img
        src="${imageSrc}"
        alt="4コマのストーリーイラスト"
        class="part-c-comic-img"
        loading="lazy"
        onerror="this.closest('.part-c-comic').classList.add('part-c-comic-placeholder'); this.replaceWith(Object.assign(document.createElement('p'),{className:'text-sm text-slate-500 text-center py-8',textContent:'イラストを読み込めませんでした'}));"
      >
    </div>`;
}

function buildPanelExamples(panels) {
  return `
    <div class="bg-violet-50 border border-violet-200 rounded-xl p-3 mb-4">
      <p class="text-xs font-semibold text-violet-700 mb-3">見本（各コマの例文）</p>
      <ol class="space-y-2 list-none">
        ${panels.map((p, i) => `
          <li class="text-sm leading-relaxed">
            <span class="font-bold text-violet-600">Panel ${i + 1}:</span>
            <span class="text-slate-700">${p.example}</span>
          </li>`).join('')}
      </ol>
    </div>`;
}

async function runPartC() {
  const d = getPartData('C');
  if (App.cancelRequested) return;

  await renderPartIdle('C');
  await waitForClick('start-btn');
  if (App.cancelRequested) return;
  setStopButtonVisible(true);

  const prep = getPrepConfig('C');

  // prep
  if (prep.enabled) {
    let timerEl;
    $root().innerHTML = cardWrap(`
      <p class="text-xs font-bold text-violet-600 uppercase tracking-wider mb-3">${d.title} — 準備</p>
      <div id="timer-wrap"></div>
      ${buildStoryComic(d.storyImage)}
      <p class="text-center text-sm text-slate-400">4コマのストーリーを英語でどう話すか考えてください</p>
    `);
    timerEl = document.getElementById('timer-wrap');
    await countdown(prep.seconds, sec => { timerEl.innerHTML = timerDisplay(sec, 'prep'); });
    if (App.cancelRequested) return;
  }

  // recording
  let timerEl;
  let transEl;
  $root().innerHTML = cardWrap(`
    <p class="text-xs font-bold text-red-600 uppercase tracking-wider mb-3">${d.title} — 録音</p>
    <div id="timer-wrap"></div>
    ${recIndicator(true)}
    ${buildStoryComic(d.storyImage)}
    <p class="text-xs text-slate-400 mb-1">文字起こし</p>
    ${transcriptBox('transcript-el')}
    ${submitBtn()}
  `);
  timerEl = document.getElementById('timer-wrap');
  transEl = document.getElementById('transcript-el');
  wireSubmitBtn();

  const [{ text, duration }] = await Promise.all([
    startRecording(d.recTime, transEl),
    countdown(d.recTime, sec => { timerEl.innerHTML = timerDisplay(sec, 'rec'); }),
  ]);
  App.submitRequested = false;
  if (App.cancelRequested || !App.running) return;
  stopRecognition();
  setStopButtonVisible(false);

  renderLoading('Part C 採点中...');
  try {
    const result = await callEvaluate({
      part: 'C', text, duration,
      panel_descriptions: d.panels.map(p => p.description),
    });
    renderPartCResult(result, text, d.panels);
  } catch (e) {
    renderError(e.message);
  }
}

function renderPartCResult(result, text, panels) {
  const s = result.scores || {};
  const ga = (s.goal_achievement_panel1 ?? 0) + (s.goal_achievement_panel2 ?? 0) +
             (s.goal_achievement_panel3 ?? 0) + (s.goal_achievement_panel4 ?? 0);
  const total = ga + (s.vocabulary_grammar ?? 0) + (s.fluency_pronunciation ?? 0);

  const panelBadges = [1,2,3,4].map(n => {
    const sc = s[`goal_achievement_panel${n}`] ?? 0;
    return `<div class="flex items-center gap-1 text-sm">
      <span class="${sc ? 'text-emerald-600' : 'text-red-400'} font-bold">${sc ? '✅' : '❌'}</span>
      <span class="text-slate-600">Panel ${n}</span>
    </div>`;
  }).join('');

  $root().innerHTML = cardWrap(`
    <p class="text-xs font-bold text-violet-600 uppercase tracking-wider mb-4">Part C 結果</p>
    <div class="flex justify-around mb-4">
      ${scoreCircle(ga, 4, 'Goal Achievement', 'violet')}
      ${scoreCircle(s.vocabulary_grammar ?? 0, 4, '語い・文法', 'sky')}
      ${scoreCircle(s.fluency_pronunciation ?? 0, 4, '流ちょうさ', 'emerald')}
    </div>
    <div class="bg-indigo-50 border border-indigo-200 rounded-xl p-3 mb-4">
      <p class="text-xs font-semibold text-indigo-700 mb-2">コマ別 Goal Achievement</p>
      <div class="grid grid-cols-2 gap-2">${panelBadges}</div>
    </div>
    <p class="text-center text-sm font-bold text-indigo-700 mb-4">合計: ${total} / 12点</p>
    <p class="text-xs text-slate-400 mb-1">あなたの回答</p>
    <div class="bg-slate-50 border border-slate-200 rounded-xl p-3 text-sm text-slate-700 mb-4">${text || '（認識できませんでした）'}</div>
    ${buildPanelExamples(panels)}
    ${feedbackBlock(result.feedback)}
    ${retryBtn()}
  `);
  document.getElementById('retry-btn').onclick = () => startPart('C');
}

// ─── 12. Part D ──────────────────────────────────────────────

async function runPartD() {
  const d = getPartData('D');
  if (App.cancelRequested) return;

  await renderPartIdle('D');
  await waitForClick('start-btn');
  if (App.cancelRequested) return;
  setStopButtonVisible(true);

  const prep = getPrepConfig('D');

  // prep
  if (prep.enabled) {
    let timerEl;
    $root().innerHTML = cardWrap(`
      <p class="text-xs font-bold text-teal-600 uppercase tracking-wider mb-3">${d.title} — 準備</p>
      <div id="timer-wrap"></div>
      <div class="bg-teal-50 border border-teal-200 rounded-xl p-4 mb-3">
        <p class="font-semibold text-teal-900 text-base leading-relaxed">${d.topic}</p>
      </div>
      <p class="text-xs text-slate-400 text-center">
        ① 自分の意見（賛成/反対）→ ② 客観的な理由・具体例 の順で話す練習をしてください
      </p>
    `);
    timerEl = document.getElementById('timer-wrap');
    await countdown(prep.seconds, sec => { timerEl.innerHTML = timerDisplay(sec, 'prep'); });
    if (App.cancelRequested) return;
  }

  // recording
  let timerEl;
  let transEl;
  $root().innerHTML = cardWrap(`
    <p class="text-xs font-bold text-teal-600 uppercase tracking-wider mb-3">${d.title} — 録音</p>
    <div id="timer-wrap"></div>
    ${recIndicator(true)}
    <div class="bg-teal-50 border border-teal-200 rounded-xl p-3 mb-3">
      <p class="font-semibold text-teal-900 text-sm">${d.topic}</p>
    </div>
    <p class="text-xs text-slate-400 mb-1">文字起こし</p>
    ${transcriptBox('transcript-el')}
    ${submitBtn()}
  `);
  timerEl = document.getElementById('timer-wrap');
  transEl = document.getElementById('transcript-el');
  wireSubmitBtn();

  const [{ text, duration }] = await Promise.all([
    startRecording(d.recTime, transEl),
    countdown(d.recTime, sec => { timerEl.innerHTML = timerDisplay(sec, 'rec'); }),
  ]);
  App.submitRequested = false;
  if (App.cancelRequested || !App.running) return;
  stopRecognition();
  setStopButtonVisible(false);

  renderLoading('Part D 採点中...');
  try {
    const result = await callEvaluate({ part: 'D', text, duration, topic: d.topic });
    renderPartDResult(result, text);
  } catch (e) {
    renderError(e.message);
  }
}

function renderPartDResult(result, text) {
  const s = result.scores || {};
  const total =
    (s.goal_achievement_opinion ?? 0) +
    (s.goal_achievement_reason  ?? 0) +
    (s.vocabulary_grammar       ?? 0) +
    (s.fluency_pronunciation    ?? 0);

  $root().innerHTML = cardWrap(`
    <p class="text-xs font-bold text-teal-600 uppercase tracking-wider mb-4">Part D 結果</p>
    <div class="grid grid-cols-2 gap-4 mb-4">
      ${scoreCircle(s.goal_achievement_opinion ?? 0, 1, 'GA①意見', 'teal')}
      ${scoreCircle(s.goal_achievement_reason  ?? 0, 2, 'GA②理由', 'amber')}
      ${scoreCircle(s.vocabulary_grammar       ?? 0, 4, '語い・文法', 'sky')}
      ${scoreCircle(s.fluency_pronunciation    ?? 0, 4, '流ちょうさ', 'emerald')}
    </div>
    <p class="text-center text-sm font-bold text-teal-700 mb-4">合計: ${total} / 11点</p>
    <div class="bg-slate-50 border border-slate-200 rounded-xl p-3 mb-4 text-xs text-slate-600">
      <strong>GA②理由の採点基準:</strong><br>
      2点: 客観的・社会的な視点からの理由と具体例あり<br>
      1点: 個人的な体験・感想のみ<br>
      0点: 理由・具体例なし
    </div>
    <p class="text-xs text-slate-400 mb-1">あなたの回答</p>
    <div class="bg-slate-50 border border-slate-200 rounded-xl p-3 text-sm text-slate-700 mb-4">${text || '（認識できませんでした）'}</div>
    ${feedbackBlock(result.feedback)}
    ${retryBtn()}
  `);
  document.getElementById('retry-btn').onclick = () => startPart('D');
}

// ─── 13. エラー表示 ──────────────────────────────────────────

function renderError(msg) {
  $root().innerHTML = cardWrap(`
    <div class="flex flex-col items-center py-6 gap-3">
      <span class="text-4xl">❌</span>
      <p class="font-bold text-red-600">エラーが発生しました</p>
      <p class="text-sm text-slate-600 text-center">${msg}</p>
      <button id="retry-btn"
        class="mt-2 px-6 py-2.5 rounded-xl bg-indigo-600 text-white font-bold hover:bg-indigo-700 transition-all">
        🔁 もう一度
      </button>
    </div>
  `);
  document.getElementById('retry-btn').onclick = () => startPart(App.part);
}

// ─── 14. 共通ヘルパー ────────────────────────────────────────

function waitForClick(id) {
  return new Promise(resolve => {
    const btn = document.getElementById(id);
    if (!btn) { resolve(); return; }
    btn.addEventListener('click', () => {
      unlockAudioSync();   // ジェスチャーウィンドウ内で AudioContext を unlock
      resolve();
    }, { once: true });
  });
}

function setStopButtonVisible(visible) {
  const btn = document.getElementById('stop-btn');
  if (btn) btn.classList.toggle('hidden', !visible);
}

function stopAllMedia() {
  if (App.recognition) {
    try { App.recognition.stop(); } catch (_) {}
    try { App.recognition.abort(); } catch (_) {}
    App.recognition = null;
  }
  // 音声・合成音声を必ず停止
  stopCurrentSpeech();
}

function stopRecognition() { stopAllMedia(); }

async function stopAndReset() {
  App.cancelRequested = true;
  App.running = false;
  stopAllMedia();
  speakChain = Promise.resolve();
  await sleep(300);
  setStopButtonVisible(false);
  const part = App.part;
  await renderPartIdle(part);
  App.cancelRequested = false;
}

async function renderPartIdle(partId) {
  await loadSettings();
  await loadProblems();

  if (partId === 'A') {
    const d = getPartData('A');
    $root().innerHTML = cardWrap(`
      <p class="text-xs font-bold text-indigo-600 uppercase tracking-wider mb-1">${d.title}</p>
      <p class="text-sm text-slate-500 mb-3">${d.desc}</p>
      ${problemPickerHTML('A')}
      <div class="bg-indigo-50 border border-indigo-200 rounded-xl p-4 mb-4 text-base leading-relaxed text-slate-800 font-medium">
        ${escapeHTML(d.text || '')}
      </div>
      <div class="flex gap-3 text-xs text-slate-500 mb-4">
        <span>⏱ 準備: ${prepLabel('A')}</span><span>🎤 解答: 40秒</span><span>📊 満点: 4点</span>
      </div>
      ${startBtn('練習スタート')}
    `);
  } else if (partId === 'B') {
    const d = getPartData('B');
    $root().innerHTML = cardWrap(`
      <p class="text-xs font-bold text-sky-600 uppercase tracking-wider mb-1">${d.title}</p>
      <p class="text-sm text-slate-500 whitespace-pre-line mb-3">${d.desc}</p>
      ${problemPickerHTML('B')}
      <div class="mb-4">${buildPartBInformationHTML(d)}</div>
      <div class="flex gap-3 text-xs text-slate-500 mb-4">
        <span>⏱ 準備: ${prepLabel('B')}</span><span>🎤 解答: 15秒/問</span><span>📊 この問題: ${d.questions?.length || 0}点</span>
      </div>
      <p class="text-xs bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-amber-700 mb-4">
        ⚠️ 質問文は<strong>画面に表示されません</strong>。スピーカーの音声をよく聞いて答えてください。
      </p>
      ${startBtn('練習スタート')}
    `);
  } else if (partId === 'C') {
    const d = getPartData('C');
    $root().innerHTML = cardWrap(`
      <p class="text-xs font-bold text-violet-600 uppercase tracking-wider mb-1">${d.title}</p>
      <p class="text-sm text-slate-500 mb-3">${d.desc}</p>
      ${problemPickerHTML('C')}
      ${buildStoryComic(d.storyImage)}
      <div class="flex gap-3 text-xs text-slate-500 mb-4">
        <span>⏱ 準備: ${prepLabel('C')}</span><span>🎤 解答: 60秒</span><span>📊 満点: 12点</span>
      </div>
      ${startBtn('練習スタート')}
    `);
  } else if (partId === 'D') {
    const d = getPartData('D');
    $root().innerHTML = cardWrap(`
      <p class="text-xs font-bold text-teal-600 uppercase tracking-wider mb-1">${d.title}</p>
      <p class="text-sm text-slate-500 mb-3">${d.desc}</p>
      ${problemPickerHTML('D')}
      <div class="bg-teal-50 border border-teal-200 rounded-xl p-4 mb-2">
        <p class="font-semibold text-teal-900 text-base leading-relaxed">${escapeHTML(d.topic || '')}</p>
      </div>
      <p class="text-xs text-slate-500 text-right mb-4">🇯🇵 ${escapeHTML(d.topicJa || '')}</p>
      <div class="grid grid-cols-3 gap-2 text-xs text-slate-500 mb-4">
        <div class="bg-slate-50 border border-slate-200 rounded-lg p-2 text-center">
          <p class="font-bold text-teal-600">GA 意見</p><p>0〜1点</p>
        </div>
        <div class="bg-slate-50 border border-slate-200 rounded-lg p-2 text-center">
          <p class="font-bold text-teal-600">GA 理由</p><p>0〜2点</p>
        </div>
        <div class="bg-slate-50 border border-slate-200 rounded-lg p-2 text-center">
          <p class="font-bold text-teal-600">語い・流ちょう</p><p>各0〜4点</p>
        </div>
      </div>
      <div class="flex gap-3 text-xs text-slate-500 mb-4">
        <span>⏱ 準備: ${prepLabel('D')}</span><span>🎤 解答: 60秒</span><span>📊 満点: 11点</span>
      </div>
      ${startBtn('練習スタート')}
    `);
  }
  wireProblemPicker(partId);
}

// ─── 15. タブ・パート切り替え ────────────────────────────────

function setActiveTab(partId) {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    const active = btn.dataset.part === partId;
    btn.classList.toggle('tab-active', active);
    btn.classList.toggle('tab-inactive', !active);
  });
}

async function startPart(partId) {
  App.cancelRequested = true;
  App.submitRequested = false;
  stopAllMedia();
  speakChain = Promise.resolve();
  await sleep(150);

  App.part = partId;
  App.cancelRequested = false;
  App.running = true;
  setActiveTab(partId);
  setStopButtonVisible(false);

  try {
    if (partId === 'A') await runPartA();
    else if (partId === 'B') await runPartB();
    else if (partId === 'C') await runPartC();
    else if (partId === 'D') await runPartD();
  } finally {
    App.running = false;
    setStopButtonVisible(false);
  }
}

// ─── 16. 初期化 ──────────────────────────────────────────────

async function init() {
  // ブラウザ対応チェック
  const supported = checkSpeechSupport();
  if (supported) {
    const badge = document.getElementById('browser-badge');
    if (badge) badge.classList.remove('hidden');
  } else {
    const banner = document.getElementById('no-support-banner');
    if (banner) banner.classList.remove('hidden');
  }

  await loadSettings();
  await loadProblems();
  for (const p of ['a', 'b', 'c', 'd']) {
    App.selectedProblem[p] = App.problems?.active?.[p] || 1;
  }

  // ブラウザ合成音声リストを事前ロード（Part B TTS のラグを減らす）
  ensureVoicesLoaded().catch(() => {});

  // タブクリック
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => startPart(btn.dataset.part));
  });

  const stopBtn = document.getElementById('stop-btn');
  if (stopBtn) stopBtn.addEventListener('click', () => stopAndReset());

  // Part A で初期表示
  startPart('A');
}

document.addEventListener('DOMContentLoaded', init);
