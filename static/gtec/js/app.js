'use strict';

// ============================================================
//  GTEC Speaking 対策アプリ — フロントエンド
//  Web Speech API で文字起こし → /gtec/evaluate へテキスト送信のみ
// ============================================================

// ─── 1. サンプル問題データ ──────────────────────────────────

const GTEC_DATA = {
  A: {
    title: 'Part A：音読 (Reading Aloud)',
    desc: '画面の英文を声に出して読んでください。準備時間 30 秒・解答時間 40 秒です。',
    prepTime: 30,
    recTime: 40,
    maxScore: 4,
    text:
      'Good morning, everyone! This is your Student Council with an important announcement. ' +
      'We are excited to invite all students to our annual Quiz Competition. ' +
      'The event will take place this Friday afternoon at three o\'clock in the school gymnasium. ' +
      'Students will form teams of three and compete in categories including science, history, and popular culture. ' +
      'Registration forms are available at the front office. ' +
      'Please sign up by Wednesday at noon. We look forward to seeing you there!',
  },

  B: {
    title: 'Part B：やり取り (Interacting with Others)',
    desc: '画面のスケジュール表を見ながら、音声で読まれる質問に答えてください。\n質問は画面に表示されません。準備時間 10 秒・解答時間 15 秒 × 4 問。',
    prepTime: 10,
    recTime: 15,
    maxScore: 4,
    schedule: [
      { time: '9:00 AM',          activity: 'Tennis Practice', place: 'Sports Hall'  },
      { time: '12:00 PM',         activity: 'Lunch',           place: 'Cafeteria'   },
      { time: '2:00 PM – 4:00 PM',activity: 'Study Group',     place: 'Library'     },
      { time: '5:00 PM',          activity: 'Movie',           place: 'Cinema'      },
    ],
    questions: [
      { text: 'What time does Akiko start tennis practice?',   context: "Akiko's Saturday schedule" },
      { text: 'Where will Akiko have lunch?',                  context: "Akiko's Saturday schedule" },
      { text: 'How many hours will the study group last?',     context: "Akiko's Saturday schedule" },
      { text: 'What will Akiko do at five o\'clock?',          context: "Akiko's Saturday schedule" },
    ],
  },

  C: {
    title: 'Part C：ストーリーを話す (Telling a Story)',
    desc: '4 コマのイラストを見て、ストーリーを英語で話してください。準備時間 30 秒・解答時間 60 秒です。',
    prepTime: 30,
    recTime: 60,
    maxScore: 12,
    panels: [
      { id: 1, icon: '👛', caption: 'Panel 1: 財布を発見', description: 'A student finds a wallet lying on the ground near the school entrance.' },
      { id: 2, icon: '🏫', caption: 'Panel 2: 職員室へ',   description: 'The student picks up the wallet and goes to the school office to hand it in.' },
      { id: 3, icon: '📞', caption: 'Panel 3: 持ち主に連絡', description: 'The teacher at the office calls the wallet\'s owner on the phone.' },
      { id: 4, icon: '🤝', caption: 'Panel 4: お礼を言われる', description: 'The owner comes to the school, collects the wallet, and thanks the student warmly.' },
    ],
  },

  D: {
    title: 'Part D：意見表明 (Expressing Your Opinion)',
    desc: 'トピックについて自分の意見と理由を英語で述べてください。準備時間 60 秒・解答時間 60 秒です。',
    prepTime: 60,
    recTime: 60,
    maxScore: 11,
    topic:    'Should students be allowed to use smartphones at school? State your opinion clearly and support it with reasons and specific examples.',
    topicJa:  '学校でのスマートフォン使用を許可すべきか？自分の意見を明確に述べ、理由と具体例を挙げて説明してください。',
  },
};

// ─── 2. アプリ状態 ───────────────────────────────────────────

const App = {
  part: 'A',
  running: false,
  cancelRequested: false,
  recognition: null,
  settings: { part_a_prep_enabled: true },
  currentUtterance: null,
};

// ─── 3. 設定読み込み ─────────────────────────────────────────

async function loadSettings() {
  try {
    const res = await fetch('/gtec/api/settings');
    if (res.ok) {
      App.settings = { ...App.settings, ...(await res.json()) };
    }
  } catch (_) { /* デフォルト設定を使用 */ }
}

function partAPrepEnabled() {
  return App.settings.part_a_prep_enabled !== false;
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

// Promise でラップしたカウントダウン。cancel中断可。
function countdown(seconds, onTick) {
  return new Promise(resolve => {
    let remaining = seconds;
    onTick(remaining);
    const id = setInterval(() => {
      if (App.cancelRequested) { clearInterval(id); resolve(); return; }
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
  if (refNorm === spokenNorm) return 3;
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
  const referenceWords = extractWordTokens(referenceText);
  const spokenWords = extractWordTokens(spokenText);
  const compared = compareWords(referenceWords, spokenWords);
  const percent = computeAccuracyPercent(compared);

  const baseLayer = referenceWords.map(w =>
    `<span class="token">${escapeHTML(w)}</span>`
  ).join('');
  const highlightLayer = compared.map(item =>
    `<span class="token ${item.state}">${escapeHTML(item.word)}</span>`
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

// ─── 6. TTS（Web Speech Synthesis）─────────────────────────

let voicesReadyPromise = null;

function isChromeBrowser() {
  return /Chrome/i.test(navigator.userAgent) && !/Edg|OPR|Brave/i.test(navigator.userAgent);
}

function ensureVoicesLoaded() {
  if (!voicesReadyPromise) {
    voicesReadyPromise = new Promise(resolve => {
      const tryResolve = () => {
        const voices = speechSynthesis.getVoices();
        if (voices.length) {
          resolve(voices);
          return true;
        }
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
  const voices = speechSynthesis.getVoices();
  if (!voices.length) return null;

  const enUS = voices.filter(v => v.lang === 'en-US' || v.lang.startsWith('en-US'));
  const pool = enUS.length ? enUS : voices.filter(v => v.lang.startsWith('en'));
  if (!pool.length) return null;

  if (isChromeBrowser()) {
    // Chrome のローカル音声は壊れることが多い → Google 等のネットワーク音声を優先
    const google = pool.find(v => /google/i.test(v.name));
    if (google) return google;
    const online = pool.find(v => !v.localService);
    if (online) return online;
  } else {
    const local = pool.find(v => v.localService);
    if (local) return local;
    const samantha = pool.find(v => /samantha|karen|daniel|alex/i.test(v.name));
    if (samantha) return samantha;
  }

  return pool[0];
}

let speakChain = Promise.resolve();

function speak(text) {
  speakChain = speakChain.then(() => speakOnce(text)).catch(() => {});
  return speakChain;
}

function speakOnce(text) {
  return ensureVoicesLoaded().then(() => new Promise(resolve => {
    const content = String(text || '').trim();
    if (!content) { resolve(); return; }

    speechSynthesis.cancel();

    setTimeout(() => {
      const utt = new SpeechSynthesisUtterance(content);
      utt.lang = 'en-US';
      utt.rate = 1;
      utt.pitch = 1;
      utt.volume = 1;

      const voice = getEnglishVoice();
      if (voice) {
        utt.voice = voice;
        utt.lang = voice.lang || 'en-US';
      }

      App.currentUtterance = utt;

      let started = false;
      const finish = () => {
        App.currentUtterance = null;
        resolve();
      };

      utt.onstart = () => { started = true; };
      utt.onend = finish;
      utt.onerror = finish;

      speechSynthesis.speak(utt);

      // Chrome: 音声が開始されない場合のフォールバック（voice 未設定で再試行）
      setTimeout(() => {
        if (!started) {
          utt.voice = null;
          utt.lang = 'en-US';
          speechSynthesis.speak(utt);
        }
      }, 300);
    }, 120);
  }));
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
    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    const rec = new SpeechRec();
    App.recognition = rec;
    rec.lang = 'en-US';
    rec.continuous = true;
    rec.interimResults = true;
    rec.maxAlternatives = 1;

    let finalText = '';
    const startMs = Date.now();

    const stopTimer = setTimeout(() => {
      try { rec.stop(); } catch (_) {}
    }, maxSeconds * 1000);

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
      clearTimeout(stopTimer);
      const duration = (Date.now() - startMs) / 1000;
      App.recognition = null;
      resolve({ text: finalText.trim(), duration });
    };

    rec.onerror = e => {
      clearTimeout(stopTimer);
      App.recognition = null;
      if (e.error === 'no-speech' || e.error === 'aborted') {
        const duration = (Date.now() - startMs) / 1000;
        resolve({ text: finalText.trim(), duration });
      } else {
        reject(new Error(`音声認識エラー: ${e.error}`));
      }
    };

    try {
      rec.start();
    } catch (err) {
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

  const corrections = (fb.grammar_corrections || []).map(c =>
    `<li class="mb-1">
      <span class="line-through text-red-400">${c.original}</span>
      <span class="mx-1 text-slate-400">→</span>
      <span class="text-emerald-700 font-medium">${c.corrected}</span>
      ${c.explanation ? `<span class="text-slate-500 text-xs"> (${c.explanation})</span>` : ''}
    </li>`
  ).join('');

  const vocab = (fb.upgrade_vocabulary || []).map(v =>
    `<li>${v.word} → <strong>${v.suggestion}</strong></li>`
  ).join('');

  return `
    <div class="space-y-3 text-sm">
      ${fb.good_points ? `
        <div class="bg-emerald-50 border border-emerald-200 rounded-xl p-3">
          <p class="font-semibold text-emerald-700 mb-1">✅ 良かった点</p>
          <p class="text-emerald-800">${fb.good_points}</p>
        </div>` : ''}

      ${corrections ? `
        <div class="bg-orange-50 border border-orange-200 rounded-xl p-3">
          <p class="font-semibold text-orange-700 mb-2">📝 文法の訂正</p>
          <ul class="space-y-1 text-slate-700">${corrections}</ul>
        </div>` : ''}

      ${vocab ? `
        <div class="bg-sky-50 border border-sky-200 rounded-xl p-3">
          <p class="font-semibold text-sky-700 mb-2">🔤 語彙アップグレード</p>
          <ul class="list-disc list-inside text-slate-700 space-y-0.5">${vocab}</ul>
        </div>` : ''}

      ${fb.next_step_advice ? `
        <div class="bg-indigo-50 border border-indigo-200 rounded-xl p-3">
          <p class="font-semibold text-indigo-700 mb-1">🎯 次のステップ</p>
          <p class="text-indigo-800">${fb.next_step_advice}</p>
        </div>` : ''}
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

// ─── 9. Part A ───────────────────────────────────────────────

async function runPartA() {
  const d = GTEC_DATA.A;
  if (App.cancelRequested) return;

  await loadSettings();
  const prepOn = partAPrepEnabled();
  const prepLabel = prepOn ? '30秒' : 'なし';

  // idle
  $root().innerHTML = cardWrap(`
    <p class="text-xs font-bold text-indigo-600 uppercase tracking-wider mb-1">${d.title}</p>
    <p class="text-sm text-slate-500 mb-4">${d.desc}</p>
    <div class="bg-indigo-50 border border-indigo-200 rounded-xl p-4 mb-4 text-base leading-relaxed text-slate-800 font-medium">
      ${d.text}
    </div>
    <div class="flex gap-3 text-xs text-slate-500 mb-4">
      <span>⏱ 準備: ${prepLabel}</span><span>🎤 解答: 40秒</span><span>📊 満点: 4点</span>
    </div>
    ${startBtn('練習スタート')}
  `);
  await waitForClick('start-btn');
  if (App.cancelRequested) return;

  // prep（管理設定でオフの場合はスキップ）
  if (prepOn) {
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
    await countdown(d.prepTime, sec => { timerEl.innerHTML = timerDisplay(sec, 'prep'); });
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
  `);
  timerEl  = document.getElementById('timer-wrap');
  transEl  = document.getElementById('transcript-el');

  const [{ text, duration }] = await Promise.all([
    startRecording(d.recTime, transEl),
    countdown(d.recTime, sec => { timerEl.innerHTML = timerDisplay(sec, 'rec'); }),
  ]);
  if (App.cancelRequested) return;
  if (!App.running) return;

  stopRecognition();
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
  const rows = schedule.map((r, i) =>
    `<tr class="${i % 2 === 0 ? 'bg-sky-50' : 'bg-white'}">
      <td class="px-3 py-2 font-mono text-xs text-sky-700 whitespace-nowrap">${r.time}</td>
      <td class="px-3 py-2 font-semibold text-slate-800 text-sm">${r.activity}</td>
      <td class="px-3 py-2 text-slate-500 text-xs">${r.place}</td>
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

async function runPartB() {
  const d = GTEC_DATA.B;
  if (App.cancelRequested) return;

  // idle
  $root().innerHTML = cardWrap(`
    <p class="text-xs font-bold text-sky-600 uppercase tracking-wider mb-1">${d.title}</p>
    <p class="text-sm text-slate-500 whitespace-pre-line mb-4">${d.desc}</p>
    <div class="border border-sky-200 rounded-xl overflow-hidden mb-4">${buildScheduleHTML(d.schedule)}</div>
    <div class="flex gap-3 text-xs text-slate-500 mb-4">
      <span>⏱ 準備: 10秒/問</span><span>🎤 解答: 15秒/問</span><span>📊 満点: 4点</span>
    </div>
    <p class="text-xs bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-amber-700 mb-4">
      ⚠️ 質問文は<strong>画面に表示されません</strong>。スピーカーの音声をよく聞いて答えてください。
    </p>
    ${startBtn('練習スタート')}
  `);
  await waitForClick('start-btn');
  if (App.cancelRequested) return;

  const recordings = [];

  for (let qi = 0; qi < d.questions.length; qi++) {
    if (App.cancelRequested) return;
    const q = d.questions[qi];

    // prep
    let timerEl;
    $root().innerHTML = cardWrap(`
      <p class="text-xs font-bold text-sky-600 uppercase tracking-wider mb-1">${d.title} — 質問 ${qi + 1} / ${d.questions.length}</p>
      <div id="timer-wrap"></div>
      <div class="border border-sky-200 rounded-xl overflow-hidden mb-3">${buildScheduleHTML(d.schedule)}</div>
      <div class="bg-sky-50 border border-sky-100 rounded-xl px-4 py-3 text-center text-sky-700 font-semibold">
        スピーカーから質問が流れます。よく聞いて答えてください
      </div>
    `);
    timerEl = document.getElementById('timer-wrap');
    await countdown(d.prepTime, sec => { timerEl.innerHTML = timerDisplay(sec, 'prep'); });
    if (App.cancelRequested) return;

    // TTS
    $root().querySelector('#timer-wrap').innerHTML = `
      <div class="bg-sky-50 border border-sky-200 rounded-2xl p-4 mb-4 text-center">
        <span class="text-2xl">🔊</span>
        <p class="text-sky-700 font-semibold mt-1">質問を読み上げています...</p>
      </div>`;
    await speak(q.text);
    if (App.cancelRequested) return;

    // recording
    let transEl;
    $root().innerHTML = cardWrap(`
      <p class="text-xs font-bold text-red-600 uppercase tracking-wider mb-1">${d.title} — Q${qi + 1} 解答</p>
      <div id="timer-wrap"></div>
      ${recIndicator(true)}
      <div class="border border-sky-200 rounded-xl overflow-hidden mb-3">${buildScheduleHTML(d.schedule)}</div>
      <p class="text-xs text-slate-400 mb-1">文字起こし</p>
      ${transcriptBox('transcript-el')}
    `);
    timerEl = document.getElementById('timer-wrap');
    transEl = document.getElementById('transcript-el');

    const [{ text, duration }] = await Promise.all([
      startRecording(d.recTime, transEl),
      countdown(d.recTime, sec => { timerEl.innerHTML = timerDisplay(sec, 'rec'); }),
    ]);
    stopRecognition();
    recordings.push({ text, duration, question: q });
  }

  if (App.cancelRequested) return;
  renderLoading('Part B 採点中... (4問)');

  try {
    const results = await Promise.all(
      recordings.map(r =>
        callEvaluate({
          part: 'B',
          text: r.text,
          duration: r.duration,
          question: r.question.text,
          context: r.question.context,
        })
      )
    );
    renderPartBResult(results, recordings);
  } catch (e) {
    renderError(e.message);
  }
}

function renderPartBResult(results, recordings) {
  const total = results.reduce((s, r) => s + (r.scores?.goal_achievement ?? 0), 0);
  const qCards = results.map((r, i) => {
    const score = r.scores?.goal_achievement ?? 0;
    const badge = score === 1
      ? '<span class="text-emerald-600 font-bold">✅ 1点</span>'
      : '<span class="text-red-500 font-bold">❌ 0点</span>';
    return `
      <div class="border border-slate-200 rounded-xl p-3 mb-2">
        <p class="text-xs font-semibold text-sky-600 mb-1">Q${i + 1}: ${recordings[i].question.text}</p>
        <p class="text-sm text-slate-700 mb-1">回答: <em>"${recordings[i].text || '（認識できませんでした）'}"</em></p>
        <div class="flex items-center gap-2">${badge}</div>
      </div>`;
  }).join('');

  $root().innerHTML = cardWrap(`
    <p class="text-xs font-bold text-sky-600 uppercase tracking-wider mb-4">Part B 結果</p>
    <div class="flex justify-around mb-5">
      ${scoreCircle(total, 4, 'Goal合計', 'sky')}
    </div>
    ${qCards}
    ${feedbackBlockPartB(mergePartBFeedback(results))}
    ${retryBtn()}
  `);
  document.getElementById('retry-btn').onclick = () => startPart('B');
}

// ─── 11. Part C ──────────────────────────────────────────────

function buildPanelGrid(panels) {
  return `
    <div class="grid grid-cols-2 gap-3 mb-4">
      ${panels.map(p => `
        <div class="bg-gradient-to-br from-violet-50 to-indigo-50 border border-violet-200 rounded-xl p-3 flex flex-col items-center gap-2">
          <span class="text-3xl">${p.icon}</span>
          <p class="text-xs font-bold text-violet-700">${p.caption}</p>
          <p class="text-xs text-slate-500 text-center leading-relaxed">${p.description}</p>
        </div>`).join('')}
    </div>`;
}

async function runPartC() {
  const d = GTEC_DATA.C;
  if (App.cancelRequested) return;

  // idle
  $root().innerHTML = cardWrap(`
    <p class="text-xs font-bold text-violet-600 uppercase tracking-wider mb-1">${d.title}</p>
    <p class="text-sm text-slate-500 mb-4">${d.desc}</p>
    ${buildPanelGrid(d.panels)}
    <div class="flex gap-3 text-xs text-slate-500 mb-4">
      <span>⏱ 準備: 30秒</span><span>🎤 解答: 60秒</span><span>📊 満点: 12点</span>
    </div>
    ${startBtn('練習スタート')}
  `);
  await waitForClick('start-btn');
  if (App.cancelRequested) return;

  // prep
  let timerEl;
  $root().innerHTML = cardWrap(`
    <p class="text-xs font-bold text-violet-600 uppercase tracking-wider mb-3">${d.title} — 準備</p>
    <div id="timer-wrap"></div>
    ${buildPanelGrid(d.panels)}
    <p class="text-center text-sm text-slate-400">4コマのストーリーを英語でどう話すか考えてください</p>
  `);
  timerEl = document.getElementById('timer-wrap');
  await countdown(d.prepTime, sec => { timerEl.innerHTML = timerDisplay(sec, 'prep'); });
  if (App.cancelRequested) return;

  // recording
  let transEl;
  $root().innerHTML = cardWrap(`
    <p class="text-xs font-bold text-red-600 uppercase tracking-wider mb-3">${d.title} — 録音</p>
    <div id="timer-wrap"></div>
    ${recIndicator(true)}
    ${buildPanelGrid(d.panels)}
    <p class="text-xs text-slate-400 mb-1">文字起こし</p>
    ${transcriptBox('transcript-el')}
  `);
  timerEl = document.getElementById('timer-wrap');
  transEl = document.getElementById('transcript-el');

  const [{ text, duration }] = await Promise.all([
    startRecording(d.recTime, transEl),
    countdown(d.recTime, sec => { timerEl.innerHTML = timerDisplay(sec, 'rec'); }),
  ]);
  if (App.cancelRequested) return;
  stopRecognition();

  renderLoading('Part C 採点中...');
  try {
    const result = await callEvaluate({
      part: 'C', text, duration,
      panel_descriptions: d.panels.map(p => p.description),
    });
    renderPartCResult(result, text);
  } catch (e) {
    renderError(e.message);
  }
}

function renderPartCResult(result, text) {
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
      ${scoreCircle(ga, 4, 'Goal Achievement', 'violet' in ({}) ? 'violet' : 'indigo')}
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
    ${feedbackBlock(result.feedback)}
    ${retryBtn()}
  `);
  document.getElementById('retry-btn').onclick = () => startPart('C');
}

// ─── 12. Part D ──────────────────────────────────────────────

async function runPartD() {
  const d = GTEC_DATA.D;
  if (App.cancelRequested) return;

  // idle
  $root().innerHTML = cardWrap(`
    <p class="text-xs font-bold text-rose-600 uppercase tracking-wider mb-1">${d.title}</p>
    <p class="text-sm text-slate-500 mb-4">${d.desc}</p>
    <div class="bg-rose-50 border border-rose-200 rounded-xl p-4 mb-2">
      <p class="font-semibold text-rose-800 text-base leading-relaxed">${d.topic}</p>
    </div>
    <p class="text-xs text-slate-500 text-right mb-4">🇯🇵 ${d.topicJa}</p>
    <div class="grid grid-cols-3 gap-2 text-xs text-slate-500 mb-4">
      <div class="bg-slate-50 border border-slate-200 rounded-lg p-2 text-center">
        <p class="font-bold text-rose-600">GA 意見</p><p>0〜1点</p>
      </div>
      <div class="bg-slate-50 border border-slate-200 rounded-lg p-2 text-center">
        <p class="font-bold text-rose-600">GA 理由</p><p>0〜2点</p>
      </div>
      <div class="bg-slate-50 border border-slate-200 rounded-lg p-2 text-center">
        <p class="font-bold text-rose-600">語い・流ちょう</p><p>各0〜4点</p>
      </div>
    </div>
    <div class="flex gap-3 text-xs text-slate-500 mb-4">
      <span>⏱ 準備: 60秒</span><span>🎤 解答: 60秒</span><span>📊 満点: 11点</span>
    </div>
    ${startBtn('練習スタート')}
  `);
  await waitForClick('start-btn');
  if (App.cancelRequested) return;

  // prep
  let timerEl;
  $root().innerHTML = cardWrap(`
    <p class="text-xs font-bold text-rose-600 uppercase tracking-wider mb-3">${d.title} — 準備</p>
    <div id="timer-wrap"></div>
    <div class="bg-rose-50 border border-rose-200 rounded-xl p-4 mb-3">
      <p class="font-semibold text-rose-800 text-base leading-relaxed">${d.topic}</p>
    </div>
    <p class="text-xs text-slate-400 text-center">
      ① 自分の意見（賛成/反対）→ ② 客観的な理由・具体例 の順で話す練習をしてください
    </p>
  `);
  timerEl = document.getElementById('timer-wrap');
  await countdown(d.prepTime, sec => { timerEl.innerHTML = timerDisplay(sec, 'prep'); });
  if (App.cancelRequested) return;

  // recording
  let transEl;
  $root().innerHTML = cardWrap(`
    <p class="text-xs font-bold text-red-600 uppercase tracking-wider mb-3">${d.title} — 録音</p>
    <div id="timer-wrap"></div>
    ${recIndicator(true)}
    <div class="bg-rose-50 border border-rose-200 rounded-xl p-3 mb-3">
      <p class="font-semibold text-rose-800 text-sm">${d.topic}</p>
    </div>
    <p class="text-xs text-slate-400 mb-1">文字起こし</p>
    ${transcriptBox('transcript-el')}
  `);
  timerEl = document.getElementById('timer-wrap');
  transEl = document.getElementById('transcript-el');

  const [{ text, duration }] = await Promise.all([
    startRecording(d.recTime, transEl),
    countdown(d.recTime, sec => { timerEl.innerHTML = timerDisplay(sec, 'rec'); }),
  ]);
  if (App.cancelRequested) return;
  stopRecognition();

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
    <p class="text-xs font-bold text-rose-600 uppercase tracking-wider mb-4">Part D 結果</p>
    <div class="grid grid-cols-2 gap-4 mb-4">
      ${scoreCircle(s.goal_achievement_opinion ?? 0, 1, 'GA①意見', 'rose')}
      ${scoreCircle(s.goal_achievement_reason  ?? 0, 2, 'GA②理由', 'amber')}
      ${scoreCircle(s.vocabulary_grammar       ?? 0, 4, '語い・文法', 'sky')}
      ${scoreCircle(s.fluency_pronunciation    ?? 0, 4, '流ちょうさ', 'emerald')}
    </div>
    <p class="text-center text-sm font-bold text-rose-700 mb-4">合計: ${total} / 11点</p>
    <div class="bg-amber-50 border border-amber-200 rounded-xl p-3 mb-4 text-xs text-amber-800">
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
    btn.addEventListener('click', resolve, { once: true });
  });
}

function stopRecognition() {
  if (App.recognition) {
    try { App.recognition.stop(); } catch (_) {}
    App.recognition = null;
  }
  speechSynthesis.cancel();
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
  // 実行中のテストをキャンセル
  App.cancelRequested = true;
  stopRecognition();
  await sleep(150);

  App.part = partId;
  App.cancelRequested = false;
  App.running = true;
  setActiveTab(partId);

  try {
    if (partId === 'A') await runPartA();
    else if (partId === 'B') await runPartB();
    else if (partId === 'C') await runPartC();
    else if (partId === 'D') await runPartD();
  } finally {
    App.running = false;
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

  ensureVoicesLoaded();

  // TTS 音声ロード（非同期）
  if (speechSynthesis.onvoiceschanged !== undefined) {
    speechSynthesis.onvoiceschanged = () => speechSynthesis.getVoices();
  }
  speechSynthesis.getVoices();

  // タブクリック
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => startPart(btn.dataset.part));
  });

  // Part A で初期表示
  startPart('A');
}

document.addEventListener('DOMContentLoaded', init);
