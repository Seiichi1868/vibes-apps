(function () {
  const views = {};
  document.querySelectorAll("[data-view]").forEach((el) => { views[el.dataset.view] = el; });
  const settingsForm = document.getElementById("tb-talk-settings");
  const DEVICE_KEY = "toolbox.talk_check.device.v1";
  const SETTINGS_KEY = "toolbox.talk_check.settings.v1";
  const RESUME_KEY = "toolbox.talk_check.resume.v1";
  const DRAFT_KEY = "toolbox.talk_check.drafts.v1";
  const FORM_FIELDS = [
    "level", "count", "include_inference", "notes", "keywords", "stt_mode",
    "review_transcript", "show_live", "parallel_browser", "wait_prompt",
  ];

  const state = {
    view: "settings",
    source: "paste",
    audioBlob: null,
    durationSec: 0,
    transcript: "",
    browserTranscript: "",
    sttBase: "",
    reviewed: false,
    localAudioName: "",
    questions: [],
    sessionId: null,
    detail: null,
    index: 0,
    showingAnswer: false,
    mediaRecorder: null,
    stream: null,
    chunks: [],
    recStarted: 0,
    recTimer: 0,
    analyser: null,
    silentFor: 0,
    lastLevelAt: 0,
    recognition: null,
    parallelOn: false,
    speechErrors: 0,
    waitStarted: 0,
    waitTimer: 0,
    wakeLock: null,
    pendingRetry: null,
    regenBusy: false,
    abort: null,
    running: false,
    arDirty: false,
  };

  // ── 共通ユーティリティ ───────────────────────────────────────
  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function fmtDuration(sec) {
    const total = Math.round(Number(sec) || 0);
    if (!total) return "-";
    return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
  }

  function fmtDate(iso) {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso || "";
    const p = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}/${p(d.getMonth() + 1)}/${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
  }

  function readJson(storage, key, fallback) {
    try {
      const raw = storage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (_) {
      return fallback;
    }
  }

  function writeJson(storage, key, value) {
    try { storage.setItem(key, JSON.stringify(value)); } catch (_) {}
  }

  function deviceId() {
    let id = "";
    try { id = localStorage.getItem(DEVICE_KEY) || ""; } catch (_) {}
    if (!id) {
      id = (crypto.randomUUID && crypto.randomUUID()) || String(Date.now());
      try { localStorage.setItem(DEVICE_KEY, id); } catch (_) {}
    }
    return id;
  }

  const baseFetch = window.toolboxFetch;
  window.toolboxFetch = function (url, options) {
    const next = Object.assign({}, options || {});
    if (String(url).indexOf("/toolbox/api/talk/") !== -1) {
      next.headers = Object.assign({ "X-Toolbox-Device": deviceId() }, next.headers || {});
    }
    return baseFetch(url, next);
  };

  async function postForm(url, fd, signal) {
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "X-CSRF-Token": window.TOOLBOX_CSRF || "",
        "X-Toolbox-Device": deviceId(),
      },
      body: fd,
      credentials: "same-origin",
      signal,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const err = new Error(data.error || "通信に失敗しました。もう一度試してください。");
      err.data = data;
      throw err;
    }
    return data;
  }

  // ── 音声のローカル保存（このパソコンのフォルダ）──────────────
  const dirSupported = typeof window.showDirectoryPicker === "function";

  function idbOpen() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open("toolbox-talk-check", 1);
      req.onupgradeneeded = () => req.result.createObjectStore("kv");
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }
  async function idbGet(key) {
    const db = await idbOpen();
    return new Promise((resolve, reject) => {
      const req = db.transaction("kv").objectStore("kv").get(key);
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }
  async function idbSet(key, value) {
    const db = await idbOpen();
    return new Promise((resolve, reject) => {
      const tx = db.transaction("kv", "readwrite");
      tx.objectStore("kv").put(value, key);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }

  // 選択済みフォルダのハンドル。権限がなければ null（ask=true のときはクリック操作中に許可を求める）
  async function getDir(ask) {
    if (!dirSupported) return null;
    try {
      const handle = await idbGet("dir");
      if (!handle) return null;
      let perm = await handle.queryPermission({ mode: "readwrite" });
      if (perm !== "granted" && ask) perm = await handle.requestPermission({ mode: "readwrite" });
      return perm === "granted" ? handle : null;
    } catch (_) {
      return null;
    }
  }

  async function pickDir() {
    const handle = await window.showDirectoryPicker({ id: "toolbox-talk-audio", mode: "readwrite", startIn: "documents" });
    await idbSet("dir", handle);
    return handle;
  }

  async function updateDirStatus() {
    const el = document.getElementById("tb-dir-status");
    const btn = document.getElementById("tb-dir-pick");
    if (!el) return;
    if (!dirSupported) {
      el.textContent = "このブラウザはフォルダへ直接保存できないため、音声はいったんサーバーに保存されます。月に一度、まとめてダウンロードして「ToolboxTalkAudio」フォルダへ移すお知らせが出ます。";
      btn.textContent = "音声をまとめてダウンロード";
      return;
    }
    let handle = null;
    try { handle = await idbGet("dir"); } catch (_) {}
    if (!handle) {
      el.textContent = "未設定です。選ぶまでは音声がサーバーに保存されます。";
      btn.textContent = "保存先フォルダを選ぶ";
      return;
    }
    const ok = await getDir(false);
    el.textContent = ok
      ? `保存先: ${handle.name}（使用できます）`
      : `保存先: ${handle.name}（アクセス許可が必要です。録音を始めるときに許可を求めます）`;
    btn.textContent = "保存先フォルダを変更";
  }

  const dirPick = document.getElementById("tb-dir-pick");
  if (dirPick) dirPick.addEventListener("click", async () => {
    if (!dirSupported) {
      if (window.ToolboxAudioArchive) window.ToolboxAudioArchive.show();
      return;
    }
    try {
      await pickDir();
    } catch (err) {
      if (err && err.name !== "AbortError") alert(`フォルダを選べませんでした: ${err.message}`);
    }
    updateDirStatus();
  });

  function localFileName(id, blob) {
    const d = new Date();
    const p = (n) => String(n).padStart(2, "0");
    const stamp = `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}`;
    return `${stamp}_${id}.${blobExt(blob)}`;
  }

  // 録音をこのパソコンのフォルダへ書き込む。できなければ false（サーバーの音声をそのまま残す）
  async function saveLocalAudio() {
    if (!state.audioBlob || !state.sessionId) return false;
    const dir = await getDir(false);
    if (!dir) return false;
    try {
      const name = localFileName(state.sessionId, state.audioBlob);
      const fh = await dir.getFileHandle(name, { create: true });
      const w = await fh.createWritable();
      await w.write(state.audioBlob);
      await w.close();
      state.localAudioName = name;
      await toolboxFetch(`/toolbox/api/talk/sessions/${state.sessionId}/audio-local`, {
        method: "POST",
        body: JSON.stringify({ filename: name, release: false }),
      });
      return true;
    } catch (_) {
      state.localAudioName = "";
      return false;
    }
  }

  // 文字起こしが終わったら、サーバー上の音声を消す（ローカルに保存済みの場合のみ）
  async function releaseServerAudio() {
    if (!state.localAudioName || !state.sessionId) return;
    try {
      await toolboxFetch(`/toolbox/api/talk/sessions/${state.sessionId}/audio-local`, {
        method: "POST",
        body: JSON.stringify({ filename: state.localAudioName, release: true }),
      });
    } catch (_) {}
  }

  async function readLocalFile(name) {
    const dir = await getDir(false);
    if (!dir) return null;
    try {
      const fh = await dir.getFileHandle(name);
      return await fh.getFile();
    } catch (_) {
      return null;
    }
  }

  // ── 設定（保存ボタンで確定）──────────────────────────────────
  function readForm() {
    const fd = new FormData(settingsForm);
    let count = Math.floor(Number(fd.get("count")));
    if (!Number.isFinite(count) || count < 1) count = 5;
    return {
      level: fd.get("level") || "A2",
      count,
      include_inference: fd.has("include_inference"),
      notes: fd.get("notes") || "",
      keywords: fd.get("keywords") || "",
      stt_mode: fd.get("stt_mode") || "whisper",
      review_transcript: fd.has("review_transcript"),
      show_live: fd.has("show_live"),
      parallel_browser: fd.has("parallel_browser"),
      wait_prompt: fd.get("wait_prompt") || "Talk with your partner. What did you hear?",
    };
  }

  function applyToForm(values) {
    FORM_FIELDS.forEach((name) => {
      const el = settingsForm.elements[name];
      if (!el || values[name] === undefined) return;
      if (el.type === "checkbox") el.checked = !!values[name];
      else el.value = values[name];
    });
  }

  let applied = Object.assign(readForm(), readJson(localStorage, SETTINGS_KEY, {}));
  applyToForm(applied);

  function settings() {
    const mic = settingsForm.elements.mic ? settingsForm.elements.mic.value : "";
    return Object.assign({}, applied, { mic });
  }

  function isDirty() {
    const now = readForm();
    return FORM_FIELDS.some((k) => now[k] !== applied[k]);
  }

  const saveBtn = document.getElementById("tb-save-settings");
  function refreshSaveBtn() {
    const dirty = isDirty();
    saveBtn.disabled = !dirty;
    saveBtn.classList.toggle("is-dirty", dirty);
    saveBtn.textContent = dirty ? "変更を保存して更新" : "設定は保存済み";
  }

  function saveSettings() {
    applied = readForm();
    writeJson(localStorage, SETTINGS_KEY, applied);
    applyToForm(applied);
    refreshSaveBtn();
    updateEstimate();
  }

  function ensureSaved() {
    if (!isDirty()) return true;
    if (confirm("設定に未保存の変更があります。保存して続けますか？")) {
      saveSettings();
      return true;
    }
    return false;
  }

  function estimateSeconds(count, reasoning) {
    const calls = Math.max(1, Math.ceil(count / 12));
    const base = 6 + 2 * calls + 3 * count;
    return base * (reasoning ? 3 : 1);
  }

  function fmtEstimate(sec) {
    const rounded = Math.max(5, Math.round(sec / 5) * 5);
    if (rounded < 60) return `約${rounded}秒`;
    const m = Math.floor(rounded / 60);
    const s = rounded % 60;
    return s ? `約${m}分${s}秒` : `約${m}分`;
  }

  function updateEstimate() {
    const el = document.getElementById("tb-count-est");
    if (!el) return;
    const count = readForm().count;
    const reasoning = settingsForm.dataset.reasoning === "1";
    let text = `問題作成の待ち時間の目安: ${fmtEstimate(estimateSeconds(count, reasoning))}（モデルや混雑で変わります）`;
    if (isDirty()) text += " ※保存すると反映されます";
    el.textContent = text;
  }

  settingsForm.addEventListener("input", () => { refreshSaveBtn(); updateEstimate(); });
  settingsForm.addEventListener("change", () => { refreshSaveBtn(); updateEstimate(); });
  settingsForm.addEventListener("submit", (ev) => ev.preventDefault());
  saveBtn.addEventListener("click", saveSettings);
  refreshSaveBtn();
  updateEstimate();

  // ── 画面遷移と復元 ───────────────────────────────────────────
  function saveResume() {
    writeJson(sessionStorage, RESUME_KEY, {
      view: state.view,
      sessionId: state.sessionId,
      index: state.index,
      showingAnswer: state.showingAnswer,
    });
  }

  function show(name) {
    state.view = name;
    Object.entries(views).forEach(([key, el]) => { el.hidden = key !== name; });
    saveResume();
  }

  function resetSession() {
    state.audioBlob = null;
    state.durationSec = 0;
    state.transcript = "";
    state.browserTranscript = "";
    state.sttBase = "";
    state.reviewed = false;
    state.localAudioName = "";
    state.questions = [];
    state.sessionId = null;
    state.detail = null;
    state.index = 0;
    state.showingAnswer = false;
    state.pendingRetry = null;
    updateDownloadLink();
  }

  function goTo(name) {
    if (state.view === "settings" && name !== "settings" && !ensureSaved()) return;
    if (name === "history") {
      show("history");
      loadHistory();
      return;
    }
    if (name === "paste") {
      resetSession();
      state.source = "paste";
      document.getElementById("tb-paste").value = readJson(sessionStorage, DRAFT_KEY, {}).paste || "";
    }
    if (name === "file") resetSession();
    show(name);
  }

  document.querySelectorAll("[data-go]").forEach((btn) => {
    btn.addEventListener("click", (ev) => {
      if (btn.dataset.go === "record") {
        ev.preventDefault();
        if (state.view === "settings" && !ensureSaved()) return;
        startRecording().catch((err) => alert(err.message));
        return;
      }
      goTo(btn.dataset.go);
    });
  });

  // 下書き（更新しても消えないように）
  function saveDraft(key, value) {
    const drafts = readJson(sessionStorage, DRAFT_KEY, {});
    drafts[key] = value;
    writeJson(sessionStorage, DRAFT_KEY, drafts);
  }
  document.getElementById("tb-paste").addEventListener("input", (ev) => saveDraft("paste", ev.target.value));
  document.getElementById("tb-review").addEventListener("input", (ev) => {
    state.transcript = ev.target.value;
    saveDraft("review", ev.target.value);
  });

  window.addEventListener("beforeunload", (ev) => {
    if (state.mediaRecorder && state.mediaRecorder.state === "recording") {
      ev.preventDefault();
      ev.returnValue = "";
    }
  });

  // ── 録音まわり ───────────────────────────────────────────────
  function SpeechRecognitionCtor() {
    return window.SpeechRecognition || window.webkitSpeechRecognition || null;
  }

  async function loadMics() {
    const sel = document.getElementById("tb-mic");
    if (!navigator.mediaDevices?.enumerateDevices) return;
    const devices = await navigator.mediaDevices.enumerateDevices();
    const mics = devices.filter((d) => d.kind === "audioinput");
    const last = localStorage.getItem("toolbox.talk_check.mic") || "";
    sel.innerHTML = mics.map((d) => `<option value="${esc(d.deviceId)}">${esc(d.label || "マイク")}</option>`).join("");
    if (last) sel.value = last;
  }

  document.getElementById("tb-mic").addEventListener("change", (ev) => {
    localStorage.setItem("toolbox.talk_check.mic", ev.target.value);
  });

  function pickMime() {
    const types = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];
    if (!window.MediaRecorder) return "";
    return types.find((t) => MediaRecorder.isTypeSupported(t)) || "";
  }

  function blobExt(blob) {
    const t = (blob && blob.type) || "";
    if (t.includes("mp4")) return "mp4";
    if (t.includes("ogg")) return "ogg";
    if (t.includes("wav")) return "wav";
    if (t.includes("mpeg")) return "mp3";
    return "webm";
  }

  function setMeter(el, value) {
    const bar = el?.querySelector("span");
    if (bar) bar.style.width = `${Math.min(100, Math.round(value * 100))}%`;
  }

  async function getStream() {
    const cfg = settings();
    try {
      return await navigator.mediaDevices.getUserMedia({
        audio: cfg.mic ? { deviceId: { exact: cfg.mic } } : true,
      });
    } catch (err) {
      throw new Error("マイクを使えません。Chrome のサイト設定からマイクを許可し、設定画面でマイクテストをしてください。");
    }
  }

  async function requestWake() {
    try {
      if (navigator.wakeLock) state.wakeLock = await navigator.wakeLock.request("screen");
    } catch (_) {}
  }
  function releaseWake() {
    if (state.wakeLock) {
      state.wakeLock.release().catch(() => {});
      state.wakeLock = null;
    }
  }

  function stopRecognition(reason) {
    if (!state.recognition) return;
    try { state.recognition.onend = null; state.recognition.stop(); } catch (_) {}
    state.recognition = null;
    if (state.parallelOn && reason) {
      toolboxFetch("/toolbox/api/talk/events", {
        method: "POST",
        body: JSON.stringify({ name: "browser_stt_auto_stop" }),
      }).catch(() => {});
    }
    state.parallelOn = false;
  }

  function renderLive(liveEl, note) {
    if (!liveEl || liveEl.hidden) return;
    const text = state.browserTranscript;
    liveEl.textContent = text || "（ここにブラウザの文字起こしが表示されます）";
    liveEl.classList.toggle("is-empty", !text);
    if (note) {
      const small = document.createElement("div");
      small.className = "tb-live-note";
      small.textContent = note;
      liveEl.appendChild(small);
    }
    liveEl.scrollTop = liveEl.scrollHeight;
  }

  function startRecognition({ liveEl }) {
    const Ctor = SpeechRecognitionCtor();
    if (!Ctor) return;
    const rec = new Ctor();
    rec.lang = "en-US";
    rec.continuous = true;
    rec.interimResults = true;
    rec.onresult = (ev) => {
      let text = "";
      for (let i = 0; i < ev.results.length; i += 1) text += ev.results[i][0].transcript + " ";
      // 認識が自動で再開されると結果がリセットされるため、確定済みの文章に追記する
      state.browserTranscript = `${state.sttBase} ${text}`.trim();
      renderLive(liveEl);
    };
    rec.onerror = (ev) => {
      const code = ev && ev.error;
      if (code === "no-speech" || code === "aborted") return;
      state.speechErrors += 1;
      if (state.speechErrors >= 3 && state.mediaRecorder) {
        stopRecognition("errors");
        renderLive(liveEl, "ブラウザの文字起こしは停止しました（録音は続いています）");
      }
    };
    rec.onend = () => {
      state.sttBase = state.browserTranscript;
      if (state.mediaRecorder && state.mediaRecorder.state === "recording") {
        try { rec.start(); } catch (_) {}
      }
    };
    try { rec.start(); state.recognition = rec; } catch (_) {}
  }

  function watchLevel(stream, meterEl, msgEl) {
    const ctx = new AudioContext();
    const source = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);
    state.analyser = { ctx, analyser, data: new Uint8Array(analyser.frequencyBinCount) };
    state.silentFor = 0;
    state.lastLevelAt = Date.now();
    const loop = () => {
      if (!state.analyser) {
        ctx.close().catch(() => {});
        return;
      }
      state.analyser.analyser.getByteTimeDomainData(state.analyser.data);
      let sum = 0;
      for (let i = 0; i < state.analyser.data.length; i += 1) {
        const v = (state.analyser.data[i] - 128) / 128;
        sum += v * v;
      }
      const rms = Math.sqrt(sum / state.analyser.data.length);
      setMeter(meterEl, Math.min(1, rms * 6));
      if (rms < 0.01) state.silentFor += 0.2;
      else {
        state.silentFor = 0;
        state.lastLevelAt = Date.now();
      }
      if (msgEl && state.silentFor >= 5) msgEl.textContent = "音が入っていません";
      else if (msgEl && msgEl.textContent === "音が入っていません") msgEl.textContent = "";
      if (state.mediaRecorder && Date.now() - state.lastLevelAt > 4000 && state.parallelOn) {
        stopRecognition("meter_stop");
      }
      setTimeout(loop, 200);
    };
    loop();
  }

  document.getElementById("tb-mic-test").addEventListener("click", async () => {
    const meter = document.getElementById("tb-mic-meter");
    const msg = document.getElementById("tb-mic-msg");
    meter.hidden = false;
    msg.textContent = "5秒間、声を出して確認します。";
    try {
      const stream = await getStream();
      await loadMics();
      watchLevel(stream, meter, msg);
      setTimeout(() => {
        stream.getTracks().forEach((t) => t.stop());
        if (state.analyser) {
          state.analyser.ctx.close().catch(() => {});
          state.analyser = null;
        }
        msg.textContent = "マイクテストを終了しました。";
      }, 5000);
    } catch (err) {
      msg.textContent = err.message;
    }
  });

  function recClock() {
    const elapsed = Math.floor((Date.now() - state.recStarted) / 1000);
    const m = String(Math.floor(elapsed / 60)).padStart(2, "0");
    const s = String(elapsed % 60).padStart(2, "0");
    document.getElementById("tb-rec-clock").textContent = `${m}:${s}`;
    const msg = document.getElementById("tb-rec-msg");
    if (elapsed >= 480 && elapsed < 600) msg.textContent = "まもなく10分です。長い場合は一度停止してください。";
    if (elapsed >= 600) stopRecording(true);
  }

  async function startRecording() {
    await getDir(true); // クリック操作中に保存先フォルダの許可を取っておく
    resetSession();
    state.source = "record";
    const stream = await getStream();
    state.stream = stream;
    state.chunks = [];
    state.speechErrors = 0;
    const mime = pickMime();
    state.mediaRecorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
    state.mediaRecorder.ondataavailable = (ev) => { if (ev.data.size) state.chunks.push(ev.data); };
    state.mediaRecorder.onerror = () => {
      if (state.parallelOn) stopRecognition("recorder_error");
    };
    state.mediaRecorder.start(1000);
    state.recStarted = Date.now();
    state.recTimer = setInterval(recClock, 250);
    document.getElementById("tb-rec-clock").textContent = "00:00";
    document.getElementById("tb-rec-msg").textContent = "";
    await requestWake();
    watchLevel(stream, document.getElementById("tb-rec-meter"), document.getElementById("tb-rec-msg"));
    const cfg = settings();
    const canBrowser = !!SpeechRecognitionCtor();
    if (!canBrowser) {
      const box = settingsForm.parallel_browser.closest("label");
      if (box) box.hidden = true;
      const opt = settingsForm.stt_mode.querySelector('option[value="browser"]');
      if (opt) opt.hidden = true;
    }
    const useBrowser = canBrowser && (cfg.stt_mode === "browser" || cfg.parallel_browser);
    const live = document.getElementById("tb-live");
    live.hidden = !(useBrowser && cfg.show_live);
    renderLive(live);
    if (useBrowser) {
      state.parallelOn = cfg.stt_mode !== "browser";
      startRecognition({ liveEl: live });
      toolboxFetch("/toolbox/api/talk/events", {
        method: "POST",
        body: JSON.stringify({ name: state.parallelOn ? "browser_stt_parallel_on" : "browser_stt_parallel_off" }),
      }).catch(() => {});
    }
    show("record");
  }

  function stopRecording(keep) {
    clearInterval(state.recTimer);
    releaseWake();
    stopRecognition();
    if (state.analyser) {
      state.analyser.ctx.close().catch(() => {});
      state.analyser = null;
    }
    const rec = state.mediaRecorder;
    const stream = state.stream;
    state.mediaRecorder = null;
    state.stream = null;
    if (!rec) return;
    const durationSec = (Date.now() - state.recStarted) / 1000;
    rec.onstop = () => {
      stream?.getTracks().forEach((t) => t.stop());
      if (!keep) {
        state.audioBlob = null;
        show("settings");
        return;
      }
      state.audioBlob = new Blob(state.chunks, { type: rec.mimeType || "audio/webm" });
      state.durationSec = durationSec;
      state.source = "record";
      state.reviewed = false;
      runPipeline();
    };
    if (rec.state !== "inactive") rec.stop();
    else rec.onstop();
  }

  document.getElementById("tb-stop").addEventListener("click", () => stopRecording(true));
  document.getElementById("tb-cancel-rec").addEventListener("click", () => {
    if (!confirm("録音を破棄しますか？（保存されません）")) return;
    stopRecording(false);
  });

  // ── 待機画面とエラー復帰 ─────────────────────────────────────
  function updateDownloadLink() {
    const link = document.getElementById("tb-wait-dl");
    if (!link) return;
    if (link.dataset.url) {
      URL.revokeObjectURL(link.dataset.url);
      link.dataset.url = "";
    }
    if (state.audioBlob) {
      const url = URL.createObjectURL(state.audioBlob);
      link.dataset.url = url;
      link.href = url;
      link.download = `speech.${blobExt(state.audioBlob)}`;
      link.hidden = false;
    } else {
      link.hidden = true;
      link.removeAttribute("href");
    }
  }

  function beginWait() {
    show("wait");
    document.getElementById("tb-wait-prompt").textContent = settings().wait_prompt;
    document.getElementById("tb-start-qs").hidden = true;
    document.getElementById("tb-choose-qs").hidden = true;
    document.getElementById("tb-retry-send").hidden = true;
    document.getElementById("tb-wait-error").hidden = true;
    document.getElementById("tb-wait-recover").hidden = true;
    state.waitStarted = Date.now();
    clearInterval(state.waitTimer);
    state.waitTimer = setInterval(() => {
      const sec = Math.floor((Date.now() - state.waitStarted) / 1000);
      document.getElementById("tb-wait-clock").textContent = `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;
    }, 250);
  }

  function endWaitTimer() {
    clearInterval(state.waitTimer);
  }

  function waitStatus(text) {
    document.getElementById("tb-wait-status").textContent = text;
  }

  function waitError(message, retry) {
    endWaitTimer();
    waitStatus("エラー");
    const el = document.getElementById("tb-wait-error");
    el.textContent = message;
    el.hidden = false;
    document.getElementById("tb-retry-send").hidden = !retry;
    state.pendingRetry = retry || null;
    document.getElementById("tb-wait-open").hidden = !state.sessionId;
    document.getElementById("tb-wait-paste").hidden = !(state.transcript || state.browserTranscript);
    updateDownloadLink();
    document.getElementById("tb-wait-recover").hidden = false;
  }

  document.getElementById("tb-retry-send").addEventListener("click", () => {
    if (state.pendingRetry) state.pendingRetry();
  });

  document.getElementById("tb-wait-open").addEventListener("click", () => {
    if (state.sessionId) openArchive(state.sessionId).catch((e) => alert(e.message));
  });

  document.getElementById("tb-wait-paste").addEventListener("click", () => {
    const text = state.transcript || state.browserTranscript || "";
    document.getElementById("tb-paste").value = text;
    state.source = state.source === "record" || state.source === "file" ? state.source : "paste";
    show("paste");
  });

  function probeDuration(blob) {
    return new Promise((resolve) => {
      try {
        const url = URL.createObjectURL(blob);
        const audio = new Audio();
        const done = (v) => { URL.revokeObjectURL(url); resolve(v); };
        const timer = setTimeout(() => done(0), 4000);
        audio.preload = "metadata";
        audio.onloadedmetadata = () => {
          clearTimeout(timer);
          done(Number.isFinite(audio.duration) ? audio.duration : 0);
        };
        audio.onerror = () => { clearTimeout(timer); done(0); };
        audio.src = url;
      } catch (_) {
        resolve(0);
      }
    });
  }

  function isAbort(err) {
    return err && (err.name === "AbortError");
  }

  async function uploadAudio(signal) {
    const cfg = settings();
    const fd = new FormData();
    const name = state.audioBlob.name || `speech.${blobExt(state.audioBlob)}`;
    fd.append("audio", state.audioBlob, name);
    fd.append("duration_sec", String(Math.round(state.durationSec || 0)));
    fd.append("source", state.source === "file" ? "file" : "record");
    fd.append("level", cfg.level);
    fd.append("keywords", cfg.keywords);
    fd.append("browser_transcript", state.browserTranscript || "");
    const data = await postForm("/toolbox/api/talk/audio", fd, signal);
    state.sessionId = data.session_id;
    saveResume();
    await saveLocalAudio();
  }

  async function createTextSession(signal) {
    const data = await toolboxFetch("/toolbox/api/talk/sessions", {
      method: "POST",
      body: JSON.stringify({ transcript: state.transcript, level: settings().level }),
      signal,
    });
    state.sessionId = data.session_id;
    saveResume();
  }

  async function transcribeSaved(signal) {
    const cfg = settings();
    if (cfg.stt_mode === "browser") {
      if (!state.browserTranscript) {
        throw new Error("ブラウザの文字起こしが取れませんでした。保存済みの音声は残っています。Whisper で文字起こしするか、テキスト貼り付けを使ってください。");
      }
      await toolboxFetch(`/toolbox/api/talk/sessions/${state.sessionId}`, {
        method: "PUT",
        body: JSON.stringify({ transcript: state.browserTranscript }),
        signal,
      });
      return state.browserTranscript;
    }
    try {
      const data = await toolboxFetch("/toolbox/api/talk/transcribe", {
        method: "POST",
        body: JSON.stringify({ session_id: state.sessionId, keywords: cfg.keywords }),
        signal,
      });
      return data.transcript;
    } catch (err) {
      if (isAbort(err)) throw err;
      if (state.browserTranscript) {
        await toolboxFetch(`/toolbox/api/talk/sessions/${state.sessionId}`, {
          method: "PUT",
          body: JSON.stringify({ transcript: state.browserTranscript }),
        }).catch(() => {});
        return state.browserTranscript;
      }
      throw err;
    }
  }

  async function generateForSession(signal) {
    const cfg = settings();
    const data = await toolboxFetch("/toolbox/api/talk/generate", {
      method: "POST",
      body: JSON.stringify({
        session_id: state.sessionId,
        transcript: state.transcript,
        level: cfg.level,
        count: cfg.count,
        include_inference: cfg.include_inference,
        notes: cfg.notes,
        source: state.source,
        wait_prompt: cfg.wait_prompt,
        keywords: cfg.keywords,
      }),
      signal,
    });
    state.sessionId = data.session_id;
    state.questions = data.questions || [];
    saveResume();
    return data;
  }

  // 音声保存 → 文字起こし → （確認）→ 問題作成。途中で失敗しても、完了済みの段階は再実行しない。
  async function runPipeline() {
    if (state.running) return;
    state.running = true;
    const controller = new AbortController();
    state.abort = controller;
    beginWait();
    try {
      if (!state.sessionId) {
        if (state.audioBlob) {
          waitStatus("音声を保存中");
          if (!state.durationSec) state.durationSec = await probeDuration(state.audioBlob);
          await uploadAudio(controller.signal);
        } else if (state.transcript) {
          waitStatus("テキストを保存中");
          await createTextSession(controller.signal);
        } else {
          throw new Error("音声または文章がありません。");
        }
      }
      if (!state.transcript) {
        waitStatus("文字起こし中");
        state.transcript = await transcribeSaved(controller.signal);
      }
      await releaseServerAudio();
      if (settings().review_transcript && !state.reviewed) {
        state.running = false;
        endWaitTimer();
        document.getElementById("tb-review").value = state.transcript;
        show("review");
        return;
      }
      waitStatus(`問題作成中（${state.questionTarget || settings().count}問）`);
      await generateForSession(controller.signal);
      readyToStart();
    } catch (err) {
      if (isAbort(err)) return;
      const saved = state.sessionId ? " 保存済みのデータは「履歴（アーカイブ）」から確認できます。" : "";
      waitError(`${err.message}${saved}`, () => runPipeline());
    } finally {
      state.running = false;
      if (state.abort === controller) state.abort = null;
    }
  }

  function readyToStart() {
    endWaitTimer();
    waitStatus("準備完了");
    document.getElementById("tb-wait-error").hidden = true;
    document.getElementById("tb-wait-recover").hidden = true;
    document.getElementById("tb-retry-send").hidden = true;
    document.getElementById("tb-start-qs").hidden = false;
    document.getElementById("tb-choose-qs").hidden = false;
  }

  document.getElementById("tb-start-qs").addEventListener("click", startPlay);
  document.getElementById("tb-choose-qs").addEventListener("click", () => {
    renderSelect();
    show("select");
  });

  document.getElementById("tb-file-go").addEventListener("click", async () => {
    const file = document.getElementById("tb-file").files[0];
    if (!file) {
      alert("音声ファイルを選んでください。");
      return;
    }
    await getDir(true);
    resetSession();
    state.audioBlob = file;
    state.source = "file";
    state.durationSec = await probeDuration(file);
    runPipeline();
  });

  document.getElementById("tb-paste-go").addEventListener("click", () => {
    const text = document.getElementById("tb-paste").value.trim();
    if (!text) {
      alert("英文を貼り付けてください。");
      return;
    }
    // エラー画面から編集して戻った場合は同じアーカイブを使い続ける
    state.transcript = text;
    state.reviewed = true;
    if (!state.sessionId) state.source = "paste";
    runPipeline();
  });

  document.getElementById("tb-review-go").addEventListener("click", () => {
    const text = document.getElementById("tb-review").value.trim();
    if (!text) {
      alert("文章が空です。");
      return;
    }
    state.transcript = text;
    state.reviewed = true;
    runPipeline();
  });

  // ── 出題前の選択・出題 ───────────────────────────────────────
  function visibleQuestions() {
    return state.questions.filter((q) => q.included !== false);
  }

  function renderSelect() {
    const list = document.getElementById("tb-select-list");
    list.innerHTML = state.questions.map((q, i) => `
      <li>
        <label class="tb-check"><input type="checkbox" data-i="${i}" ${q.included === false ? "" : "checked"}> 問題 ${i + 1}${q.section ? ` <small class="tb-muted">(${esc(q.section)})</small>` : ""}</label>
        <p class="tb-blur" data-reveal>${esc(q.question)}</p>
      </li>
    `).join("");
    list.querySelectorAll("[data-reveal]").forEach((p) => {
      p.addEventListener("click", () => p.classList.toggle("tb-blur"));
    });
    list.querySelectorAll("input[data-i]").forEach((input) => {
      input.addEventListener("change", () => {
        state.questions[Number(input.dataset.i)].included = input.checked;
      });
    });
  }

  function revealAllQuestions() {
    document.querySelectorAll("#tb-select-list [data-reveal].tb-blur").forEach((p) => {
      p.classList.remove("tb-blur");
    });
  }

  document.getElementById("tb-reveal-all").addEventListener("click", revealAllQuestions);
  document.getElementById("tb-start-selected").addEventListener("click", startPlay);

  function startPlay() {
    const qs = visibleQuestions();
    if (!qs.length) {
      alert("出す問題を1つ以上選んでください。");
      return;
    }
    state.index = 0;
    state.showingAnswer = false;
    show("play");
    renderQuestion();
  }

  function currentQ() {
    return visibleQuestions()[state.index];
  }

  function renderQuestion() {
    const qs = visibleQuestions();
    const q = currentQ();
    if (!q) {
      endPlay();
      return;
    }
    document.getElementById("tb-q-progress").textContent = `${state.index + 1}/${qs.length}`;
    document.getElementById("tb-question").textContent = q.question;
    stopSpeak();
    const ans = document.getElementById("tb-answer");
    ans.hidden = !state.showingAnswer;
    ans.textContent = q.model_answer || "";
    const ev = document.getElementById("tb-evidence");
    ev.hidden = true;
    ev.textContent = q.evidence || "";
    saveResume();
  }

  function stepNext() {
    if (!state.showingAnswer) {
      state.showingAnswer = true;
      renderQuestion();
      return;
    }
    if (state.index + 1 >= visibleQuestions().length) {
      endPlay();
      return;
    }
    state.index += 1;
    state.showingAnswer = false;
    renderQuestion();
  }

  function stepPrev() {
    if (state.showingAnswer) {
      state.showingAnswer = false;
      renderQuestion();
      return;
    }
    if (state.index > 0) {
      state.index -= 1;
      state.showingAnswer = true;
      renderQuestion();
    }
  }

  let speakAudio = null;
  let speakUrl = "";
  let speakGen = 0;

  function stopSpeak() {
    speakGen += 1;
    const btn = document.getElementById("tb-speak");
    if (speakAudio) {
      speakAudio.pause();
      speakAudio = null;
    }
    if (speakUrl) {
      URL.revokeObjectURL(speakUrl);
      speakUrl = "";
    }
    if (btn) {
      btn.disabled = false;
      btn.textContent = "読み上げ";
    }
  }

  document.getElementById("tb-speak").addEventListener("click", async () => {
    const btn = document.getElementById("tb-speak");
    const q = currentQ();
    if (!q || !(q.question || "").trim()) return;
    if (speakAudio && !speakAudio.paused) {
      stopSpeak();
      return;
    }
    stopSpeak();
    const gen = speakGen;
    btn.disabled = true;
    btn.textContent = "音声を準備中…";
    try {
      const res = await fetch("/toolbox/api/talk/speak", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": window.TOOLBOX_CSRF || "",
          "X-Toolbox-Device": deviceId(),
        },
        credentials: "same-origin",
        body: JSON.stringify({ text: q.question }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || "読み上げに失敗しました。");
      }
      const blob = await res.blob();
      if (gen !== speakGen) return;
      speakUrl = URL.createObjectURL(blob);
      speakAudio = new Audio(speakUrl);
      speakAudio.addEventListener("ended", stopSpeak);
      await speakAudio.play();
      btn.disabled = false;
      btn.textContent = "停止";
    } catch (err) {
      stopSpeak();
      alert(err.message);
    }
  });

  document.getElementById("tb-skip").addEventListener("click", () => {
    const q = currentQ();
    if (q) q.included = false;
    if (!visibleQuestions()[state.index]) state.index = Math.max(0, visibleQuestions().length - 1);
    state.showingAnswer = false;
    if (!visibleQuestions().length) endPlay();
    else renderQuestion();
  });

  document.getElementById("tb-regen").addEventListener("click", async (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
    const q = currentQ();
    const btn = document.getElementById("tb-regen");
    if (!q) return;
    if (!state.sessionId) {
      alert("この問題は作り直せません。もう一度問題を作ってください。");
      return;
    }
    if (state.regenBusy) return;
    const realIndex = state.questions.indexOf(q);
    if (realIndex < 0) return;
    const label = btn.textContent;
    state.regenBusy = true;
    btn.disabled = true;
    btn.textContent = "作り直し中…";
    try {
      const data = await toolboxFetch("/toolbox/api/talk/regenerate-one", {
        method: "POST",
        body: JSON.stringify({ session_id: state.sessionId, index: realIndex }),
      });
      if (!data.question) throw new Error("新しい問題が返りませんでした。");
      state.questions[realIndex] = data.question;
      state.showingAnswer = false;
      renderQuestion();
    } catch (err) {
      alert(err.message);
    } finally {
      state.regenBusy = false;
      btn.disabled = false;
      btn.textContent = label;
    }
  });

  function endPlay() {
    show("end");
    document.getElementById("tb-end-list").innerHTML = visibleQuestions().map((q) => (
      `<li><strong>${esc(q.question)}</strong><br>${esc(q.model_answer)}</li>`
    )).join("");
  }

  document.getElementById("tb-end-archive").addEventListener("click", () => {
    if (state.sessionId) openArchive(state.sessionId).catch((e) => alert(e.message));
  });

  function displayOn() {
    return !!(window.ToolboxDisplay && window.ToolboxDisplay.isOn && window.ToolboxDisplay.isOn());
  }

  views.play.addEventListener("click", (ev) => {
    if (window.toolboxIsBlank && window.toolboxIsBlank()) return;
    if (displayOn()) return;
    if (ev.target.closest("button, a, input, select, textarea, label")) return;
    stepNext();
  });

  document.addEventListener("keydown", (ev) => {
    if (window.toolboxIsBlank && window.toolboxIsBlank()) return;
    if (state.view !== "play" && state.view !== "wait") return;
    if (ev.target && /INPUT|TEXTAREA|SELECT/.test(ev.target.tagName)) return;
    if (ev.key === "e" || ev.key === "E") {
      const evd = document.getElementById("tb-evidence");
      if (evd && state.view === "play") evd.hidden = !evd.hidden;
    }
    if (displayOn()) return;
    if ((ev.key === " " || ev.key === "Enter") && state.view === "wait") {
      const start = document.getElementById("tb-start-qs");
      if (!start.hidden) start.click();
    }
    if (state.view === "play") {
      if (ev.key === " " || ev.key === "Enter" || ev.key === "ArrowRight" || ev.key === "ArrowDown") {
        ev.preventDefault();
        stepNext();
      }
      if (ev.key === "ArrowLeft" || ev.key === "ArrowUp") {
        ev.preventDefault();
        stepPrev();
      }
    }
  });

  // ── 履歴（アーカイブ）──────────────────────────────────────
  const STATUS_LABEL = {
    recorded: "文字起こし未完了",
    transcribed: "問題未作成",
  };

  async function loadHistory() {
    const list = document.getElementById("tb-history-list");
    const empty = document.getElementById("tb-history-empty");
    list.innerHTML = '<li class="tb-muted">読み込み中…</li>';
    empty.hidden = true;
    try {
      const data = await toolboxFetch("/toolbox/api/talk/sessions");
      const rows = data.sessions || [];
      empty.hidden = rows.length > 0;
      list.innerHTML = rows.map((s) => {
        const status = STATUS_LABEL[s.status] || "";
        const meta = [
          fmtDate(s.created_at),
          `${s.question_count || 0}問`,
          `音声 ${fmtDuration(s.duration_sec)}`,
          `CEFR ${s.level || "-"}`,
        ].join(" ・ ");
        return `
        <li data-id="${esc(s.id)}">
          <div class="tb-hist-title">${esc(s.title)}${status ? ` <span class="tb-badge">${esc(status)}</span>` : ""}${s.last_error ? ' <span class="tb-badge tb-badge-warn">エラーあり</span>' : ""}</div>
          <div class="tb-muted tb-hist-meta">${esc(meta)}</div>
          <div class="tb-actions">
            <button class="tb-btn" type="button" data-open="${esc(s.id)}">開く・修正</button>
            ${s.question_count ? `<button class="tb-btn tb-btn-primary" type="button" data-play="${esc(s.id)}">出題 ▶</button>` : ""}
            <button class="tb-btn" type="button" data-del="${esc(s.id)}" data-local="${esc(s.local_audio || "")}">削除</button>
          </div>
        </li>`;
      }).join("");
    } catch (err) {
      list.innerHTML = `<li class="tb-error">${esc(err.message)}</li>`;
    }
  }

  async function fetchDetail(id) {
    const data = await toolboxFetch(`/toolbox/api/talk/sessions/${id}`);
    return data.session;
  }

  async function playSession(id) {
    const detail = await fetchDetail(id);
    if (!(detail.questions || []).length) throw new Error("この履歴にはまだ問題がありません。開いて問題を作ってください。");
    state.sessionId = detail.id;
    state.questions = detail.questions;
    state.transcript = detail.transcript || "";
    state.source = detail.source || "paste";
    startPlay();
  }

  document.getElementById("tb-history-list").addEventListener("click", async (ev) => {
    const { open, del, play, local } = ev.target.dataset;
    if (open) openArchive(open).catch((e) => alert(e.message));
    if (play) playSession(play).catch((e) => alert(e.message));
    if (del && confirm("この履歴（音声・文字起こし・問題）を削除しますか？")) {
      try {
        await toolboxFetch(`/toolbox/api/talk/sessions/${del}`, { method: "DELETE" });
        ev.target.closest("li").remove();
        if (local) {
          const dir = await getDir(false);
          if (dir) await dir.removeEntry(local).catch(() => {});
        }
      } catch (e) {
        alert(e.message);
      }
    }
  });

  // ── アーカイブ詳細（修正・再利用）────────────────────────────
  const ar = {
    title: document.getElementById("tb-ar-title"),
    meta: document.getElementById("tb-ar-meta"),
    error: document.getElementById("tb-ar-error"),
    audioBox: document.getElementById("tb-ar-audio-box"),
    audio: document.getElementById("tb-ar-audio"),
    transcript: document.getElementById("tb-ar-transcript"),
    browserBox: document.getElementById("tb-ar-browser-box"),
    browser: document.getElementById("tb-ar-browser"),
    list: document.getElementById("tb-ar-questions"),
    questions: [],
  };

  function renderArchiveQuestions() {
    ar.list.innerHTML = ar.questions.map((q, i) => `
      <li data-i="${i}">
        <label class="tb-check"><input type="checkbox" data-f="included" ${q.included === false ? "" : "checked"}> 出題する（問題 ${i + 1}${q.section ? ` / ${esc(q.section)}` : ""}）</label>
        <input data-f="question" value="${esc(q.question)}" placeholder="問題文">
        <input data-f="model_answer" value="${esc(q.model_answer)}" placeholder="模範解答（英文）">
        <input data-f="evidence" value="${esc(q.evidence)}" placeholder="根拠（スピーチからの引用）">
        <button class="tb-btn" type="button" data-act="del">この問題を削除</button>
      </li>
    `).join("") || '<li class="tb-muted">問題はまだありません。</li>';
  }

  function syncArchiveQuestions() {
    ar.list.querySelectorAll("li[data-i]").forEach((li) => {
      const q = ar.questions[Number(li.dataset.i)];
      if (!q) return;
      li.querySelectorAll("[data-f]").forEach((input) => {
        q[input.dataset.f] = input.type === "checkbox" ? input.checked : input.value;
      });
    });
  }

  let arAudioUrl = "";
  async function loadArchiveAudio(detail) {
    const note = document.getElementById("tb-ar-audio-note");
    const pick = document.getElementById("tb-ar-audio-pick");
    if (arAudioUrl) {
      URL.revokeObjectURL(arAudioUrl);
      arAudioUrl = "";
    }
    ar.audio.removeAttribute("src");
    note.hidden = true;
    pick.hidden = true;
    ar.audioBox.hidden = !(detail.has_audio || detail.local_audio);
    if (detail.has_audio) {
      ar.audio.src = `/toolbox/api/talk/sessions/${detail.id}/audio`;
      return;
    }
    if (!detail.local_audio) return;
    const file = await readLocalFile(detail.local_audio);
    if (file) {
      arAudioUrl = URL.createObjectURL(file);
      ar.audio.src = arAudioUrl;
      note.textContent = `このパソコンのフォルダ内: ${detail.local_audio}`;
    } else if (!dirSupported) {
      note.textContent = `音声は「ToolboxTalkAudio」フォルダの ${detail.local_audio} に保存されています。聞き直すときはファイルを選んでください。`;
      pick.textContent = "音声ファイルを選んで再生";
      pick.hidden = false;
      pick.onclick = () => {
        const input = document.createElement("input");
        input.type = "file";
        input.accept = "audio/*,video/mp4,video/webm";
        input.onchange = () => {
          const chosen = input.files && input.files[0];
          if (!chosen) return;
          if (arAudioUrl) URL.revokeObjectURL(arAudioUrl);
          arAudioUrl = URL.createObjectURL(chosen);
          ar.audio.src = arAudioUrl;
          ar.audio.play().catch(() => {});
        };
        input.click();
      };
    } else {
      note.textContent = `音声はこのパソコンのフォルダ（${detail.local_audio}）に保存されています。フォルダへのアクセス許可が必要です。別のパソコンでは再生できません。`;
      pick.textContent = "保存先フォルダを選んで再生";
      pick.hidden = false;
      pick.onclick = async () => {
        try {
          if (!(await getDir(true))) await pickDir();
        } catch (_) {}
        updateDirStatus();
        loadArchiveAudio(detail);
      };
    }
    note.hidden = false;
  }

  function renderArchive(detail) {
    state.detail = detail;
    state.arDirty = false;
    ar.title.value = detail.title || "";
    ar.meta.textContent = [
      fmtDate(detail.created_at),
      `${(detail.questions || []).length}問`,
      `音声 ${fmtDuration(detail.duration_sec)}`,
      `CEFR ${detail.level || "-"}`,
      { record: "録音", file: "音声ファイル", paste: "テキスト" }[detail.source] || "",
    ].filter(Boolean).join(" ・ ");
    ar.error.hidden = !detail.last_error;
    ar.error.textContent = detail.last_error ? `直前のエラー: ${detail.last_error}` : "";
    loadArchiveAudio(detail);
    document.getElementById("tb-ar-retranscribe").hidden = !(detail.has_audio || detail.local_audio);
    ar.transcript.value = detail.transcript || "";
    const bt = detail.browser_transcript || "";
    ar.browserBox.hidden = !bt;
    ar.browser.textContent = bt;
    ar.questions = (detail.questions || []).map((q) => Object.assign({}, q));
    renderArchiveQuestions();
  }

  async function openArchive(id) {
    const detail = await fetchDetail(id);
    state.sessionId = detail.id;
    renderArchive(detail);
    show("archive");
  }

  ar.list.addEventListener("input", () => { state.arDirty = true; });
  ar.title.addEventListener("input", () => { state.arDirty = true; });
  ar.transcript.addEventListener("input", () => { state.arDirty = true; });

  ar.list.addEventListener("click", (ev) => {
    if (ev.target.dataset.act !== "del") return;
    syncArchiveQuestions();
    const li = ev.target.closest("li[data-i]");
    ar.questions.splice(Number(li.dataset.i), 1);
    state.arDirty = true;
    renderArchiveQuestions();
  });

  document.getElementById("tb-ar-add-q").addEventListener("click", () => {
    syncArchiveQuestions();
    ar.questions.push({ question: "", model_answer: "", short_answer: "", evidence: "", type: "fact", included: true });
    state.arDirty = true;
    renderArchiveQuestions();
  });

  document.getElementById("tb-ar-use-browser").addEventListener("click", () => {
    ar.transcript.value = ar.browser.textContent;
    state.arDirty = true;
  });

  async function saveArchive() {
    syncArchiveQuestions();
    const data = await toolboxFetch(`/toolbox/api/talk/sessions/${state.detail.id}`, {
      method: "PUT",
      body: JSON.stringify({
        title: ar.title.value,
        transcript: ar.transcript.value,
        questions: ar.questions.filter((q) => (q.question || "").trim()),
      }),
    });
    renderArchive(data.session);
    return data.session;
  }

  function busy(btn, text, fn) {
    const label = btn.textContent;
    btn.disabled = true;
    btn.textContent = text;
    return Promise.resolve().then(fn).finally(() => {
      btn.disabled = false;
      btn.textContent = label;
    });
  }

  document.getElementById("tb-ar-save").addEventListener("click", (ev) => {
    busy(ev.target, "保存中…", saveArchive)
      .then(() => { ar.meta.textContent += " ・ 保存しました"; })
      .catch((e) => alert(e.message));
  });

  document.getElementById("tb-ar-play").addEventListener("click", (ev) => {
    busy(ev.target, "保存中…", async () => {
      const saved = await saveArchive();
      state.sessionId = saved.id;
      state.questions = saved.questions;
      state.transcript = saved.transcript || "";
      state.source = saved.source || "paste";
      startPlay();
    }).catch((e) => alert(e.message));
  });

  document.getElementById("tb-ar-retranscribe").addEventListener("click", (ev) => {
    if (ar.transcript.value.trim() && !confirm("現在の文字起こしは音声からの結果で置き換わります。よろしいですか？")) return;
    busy(ev.target, "文字起こし中…", async () => {
      const detail = state.detail;
      let fromLocal = false;
      if (!detail.has_audio && detail.local_audio) {
        await getDir(true);
        const file = await readLocalFile(detail.local_audio);
        if (!file) throw new Error("保存先フォルダ内に音声が見つかりません。フォルダへのアクセスを許可するか、正しいフォルダを選んでください。");
        const fd = new FormData();
        fd.append("audio", file, detail.local_audio);
        await postForm(`/toolbox/api/talk/sessions/${detail.id}/audio-upload`, fd);
        fromLocal = true;
      }
      const data = await toolboxFetch("/toolbox/api/talk/transcribe", {
        method: "POST",
        body: JSON.stringify({ session_id: state.detail.id, keywords: settings().keywords }),
      });
      ar.transcript.value = data.transcript;
      state.arDirty = true;
      if (fromLocal) {
        await toolboxFetch(`/toolbox/api/talk/sessions/${detail.id}/audio-local`, {
          method: "POST",
          body: JSON.stringify({ filename: detail.local_audio, release: true }),
        }).catch(() => {});
        state.detail.has_audio = false;
      }
    }).catch((e) => alert(e.message));
  });

  document.getElementById("tb-ar-regenerate").addEventListener("click", async () => {
    const text = ar.transcript.value.trim();
    if (!text) {
      alert("文字起こしが空です。");
      return;
    }
    if (!confirm(`この文字起こしから、現在の設定（${settings().count}問・CEFR ${settings().level}）で問題を作り直します。今の問題は置き換わります。`)) return;
    try {
      await saveArchive();
    } catch (e) {
      alert(e.message);
      return;
    }
    state.sessionId = state.detail.id;
    state.transcript = text;
    state.source = state.detail.source || "paste";
    state.audioBlob = null;
    state.reviewed = true;
    runPipeline();
  });

  // ── 各画面の「更新」ボタン（画面だけを更新し、データは失わない）──
  function flash(view, text) {
    const el = views[view]?.querySelector(".tb-refresh-msg");
    if (!el) return;
    el.textContent = text;
    clearTimeout(el._t);
    el._t = setTimeout(() => { el.textContent = ""; }, 3000);
  }

  function mergeIncluded(fresh) {
    const old = new Map(state.questions.map((q) => [q.id, q.included]));
    return (fresh || []).map((q) => (old.has(q.id) && old.get(q.id) === false ? Object.assign({}, q, { included: false }) : q));
  }

  async function reconcileWait() {
    if (state.abort) {
      state.abort.abort();
      state.abort = null;
    }
    state.running = false;
    if (!state.sessionId) {
      waitError("処理を中断しました。最初からやり直してください。", null);
      document.getElementById("tb-wait-recover").hidden = !state.audioBlob;
      return;
    }
    try {
      const detail = await fetchDetail(state.sessionId);
      if ((detail.questions || []).length) {
        state.questions = mergeIncluded(detail.questions);
        state.transcript = detail.transcript || state.transcript;
        readyToStart();
        flash("wait", "問題は作成済みでした");
        return;
      }
      state.transcript = detail.transcript || state.transcript;
      state.browserTranscript = state.browserTranscript || detail.browser_transcript || "";
      waitError("処理を中断しました。保存済みのデータから再開できます。", () => runPipeline());
    } catch (err) {
      waitError(`状態を確認できませんでした: ${err.message}`, () => runPipeline());
    }
  }

  async function refreshView(name) {
    switch (name) {
      case "settings":
        await loadMics().catch(() => {});
        document.getElementById("tb-mic-msg").textContent = "";
        document.getElementById("tb-mic-meter").hidden = true;
        refreshSaveBtn();
        updateEstimate();
        flash("settings", "更新しました");
        break;
      case "record": {
        const rec = state.mediaRecorder;
        if (rec && rec.state === "recording") {
          recClock();
          renderLive(document.getElementById("tb-live"));
          flash("record", "録音は続いています");
        } else if (state.chunks.length) {
          flash("record", "録音を保存します");
          stopRecording(true);
        } else {
          show("settings");
        }
        break;
      }
      case "wait":
        await reconcileWait();
        break;
      case "select":
        if (state.sessionId) {
          const detail = await fetchDetail(state.sessionId);
          state.questions = mergeIncluded(detail.questions);
        }
        renderSelect();
        flash("select", "更新しました");
        break;
      case "play":
        if (state.sessionId) {
          const detail = await fetchDetail(state.sessionId);
          state.questions = mergeIncluded(detail.questions);
        }
        state.index = Math.min(state.index, Math.max(0, visibleQuestions().length - 1));
        renderQuestion();
        flash("play", "更新しました");
        break;
      case "end":
        endPlay();
        flash("end", "更新しました");
        break;
      case "history":
        await loadHistory();
        break;
      case "archive":
        if (state.arDirty && !confirm("未保存の修正は破棄されます。更新しますか？")) break;
        renderArchive(await fetchDetail(state.detail.id));
        flash("archive", "更新しました");
        break;
      default:
        flash(name, "更新しました");
    }
  }

  Object.entries(views).forEach(([name, el]) => {
    const row = document.createElement("div");
    row.className = "tb-refresh-row";
    row.innerHTML = '<button class="tb-btn tb-refresh-btn" type="button" title="この画面だけを更新します（入力済みのデータは残ります）">↻ この画面を更新</button><span class="tb-refresh-msg tb-muted"></span>';
    el.insertBefore(row, el.firstChild);
    row.querySelector("button").addEventListener("click", async (ev) => {
      const btn = ev.currentTarget;
      btn.disabled = true;
      try {
        await refreshView(name);
      } catch (err) {
        flash(name, `更新できませんでした: ${err.message}`);
      } finally {
        btn.disabled = false;
      }
    });
  });

  // ── ブラウザ再読み込み後の復元 ───────────────────────────────
  async function restore() {
    const resume = readJson(sessionStorage, RESUME_KEY, null);
    if (!resume || resume.view === "settings") return;
    const drafts = readJson(sessionStorage, DRAFT_KEY, {});
    if (resume.view === "paste" && !resume.sessionId) {
      document.getElementById("tb-paste").value = drafts.paste || "";
      show("paste");
      return;
    }
    if (resume.view === "history") {
      show("history");
      loadHistory();
      return;
    }
    if (!resume.sessionId) return;
    try {
      const detail = await fetchDetail(resume.sessionId);
      state.sessionId = detail.id;
      state.questions = detail.questions || [];
      state.transcript = detail.transcript || "";
      state.browserTranscript = detail.browser_transcript || "";
      state.source = detail.source || "paste";
      state.index = resume.index || 0;
      state.showingAnswer = !!resume.showingAnswer;
      const hasQ = state.questions.length > 0;
      if (resume.view === "archive") {
        renderArchive(detail);
        show("archive");
      } else if ((resume.view === "play" || resume.view === "end" || resume.view === "select") && hasQ) {
        if (resume.view === "select") {
          renderSelect();
          show("select");
        } else if (resume.view === "end") endPlay();
        else {
          show("play");
          renderQuestion();
        }
      } else if (resume.view === "review" && detail.transcript) {
        document.getElementById("tb-review").value = drafts.review || detail.transcript;
        show("review");
      } else if (hasQ) {
        beginWait();
        readyToStart();
      } else if (resume.view === "wait" || resume.view === "review" || resume.view === "record") {
        beginWait();
        waitError("画面を更新しました。保存済みのデータから再開できます。", () => runPipeline());
      }
    } catch (_) {
      show("settings");
    }
  }

  if (!SpeechRecognitionCtor()) {
    const box = settingsForm.parallel_browser.closest("label");
    if (box) box.hidden = true;
    const opt = settingsForm.stt_mode.querySelector('option[value="browser"]');
    if (opt) opt.hidden = true;
  }

  ToolboxDisplay.init({
    onNext: () => {
      if (state.view === "wait") {
        const start = document.getElementById("tb-start-qs");
        if (!start.hidden) start.click();
      } else if (state.view === "play") stepNext();
    },
    onPrev: () => {
      if (state.view === "play") stepPrev();
    },
  });

  loadMics().catch(() => {});
  updateDirStatus();
  restore();
})();
