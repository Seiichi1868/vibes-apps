(function () {
  const app = document.getElementById("app");
  const token = document.body.dataset.token;
  const deviceKey = "speech_rec_device";
  let deviceId = localStorage.getItem(deviceKey);
  if (!deviceId) {
    deviceId = crypto.randomUUID();
    localStorage.setItem(deviceKey, deviceId);
  }

  const readKey = `speech_rec_read:${token}`;
  const audioMode = document.body.dataset.audio || "default";
  const state = { info: null, blobs: [], mime: "", recorder: null, stream: null, samples: [], stopTimer: 0, hidden: false };

  function micConstraint() {
    if (audioMode === "ns_on_agc_off") {
      return { noiseSuppression: true, autoGainControl: false, echoCancellation: true };
    }
    if (audioMode === "ns_off") return { noiseSuppression: false };
    return true;
  }

  function clearRead() {
    localStorage.removeItem(readKey);
  }

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
  }

  function pickMime() {
    const types = ["audio/mp4", "audio/webm;codecs=opus", "audio/webm"];
    return types.find((type) => window.MediaRecorder && MediaRecorder.isTypeSupported(type)) || "";
  }

  function beep() {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.frequency.value = 880;
    osc.connect(gain);
    gain.connect(ctx.destination);
    gain.gain.setValueAtTime(0.15, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.35);
    osc.start();
    osc.stop(ctx.currentTime + 0.36);
  }

  function reasons(code) {
    return {
      preparing: "準備中です。先生の開始を待ってください。",
      expired: "この出題は期限が切れています。",
      closed: "この出題は終了しています。",
      full: "提出の上限に達しました。",
      not_found: "このリンクは見つかりません。",
    }[code] || "いま開けません。";
  }

  async function load() {
    await window.SpeechRecAudio.purgeExpired().catch(() => {});
    const res = await fetch(`/rec/api/a/${encodeURIComponent(token)}`);
    const data = await res.json().catch(() => ({ reason: "not_found" }));
    state.info = data;
    const pending = localStorage.getItem(readKey);
    if (pending && data.ok) {
      poll(pending);
      return;
    }
    if (!data.ok) {
      app.innerHTML = `<p class="status">${esc(reasons(data.reason))}</p>`;
      const kept = await window.SpeechRecAudio.loadClip(token).catch(() => null);
      if (kept && data.reason !== "preparing") {
        app.insertAdjacentHTML("beforeend", `<p class="small">前回の録音が端末に残っています。</p><button id="retry" class="primary">もう一度採点</button>`);
        document.getElementById("retry").onclick = () => upload(kept.blob, kept.meta || {}, kept.meta && kept.meta.retry_of);
      }
      return;
    }
    intro();
  }

  function idSelects(info) {
    const spec = info.id_fields || {};
    if (!spec.enabled) return "";
    const year = info.school_year;
    const grades = [1, 2, 3].map((n) => `<option value="${n}">${n}</option>`).join("");
    const classes = Array.from({ length: spec.class_max || 10 }, (_, i) => `<option value="${i + 1}">${i + 1}</option>`).join("");
    const numbers = Array.from({ length: spec.number_max || 45 }, (_, i) => `<option value="${i + 1}">${i + 1}</option>`).join("");
    return `<div class="row">
      <label>年度<select id="year"><option value="${year}">${year}</option></select></label>
      <label>学年<select id="grade">${grades}</select></label>
      <label>クラス<select id="klass">${classes}</select></label>
      <label>番号<select id="number">${numbers}</select></label>
    </div>`;
  }

  function intro() {
    const info = state.info;
    app.innerHTML = `
      <p class="topic">${esc(info.topic)}</p>
      ${idSelects(info)}
      <p class="mine"><a href="/rec/my">自分の結果</a></p>
      <p class="note">下のボタンを押してスピーチを開始してください。終わると評価が表示されるので、スクリーンショットで保存してください。音声は採点後すぐに、文字起こしやコメントは30分後に、サーバーから自動的に削除されます。</p>
      <button id="start" class="primary">${Number(info.prep_sec) > 0 ? "準備スタート" : "スピーチ開始"}</button>
      <p class="err" id="err"></p>`;
    document.getElementById("start").onclick = startPrep;
  }

  function selectedId() {
    const spec = (state.info.id_fields || {});
    if (!spec.enabled) return {};
    return {
      year: document.getElementById("year").value,
      grade: document.getElementById("grade").value,
      class: document.getElementById("klass").value,
      number: document.getElementById("number").value,
    };
  }

  async function startPrep() {
    const err = document.getElementById("err");
    try {
      state.stream = await navigator.mediaDevices.getUserMedia({ audio: micConstraint() });
    } catch (error) {
      err.textContent = "マイクが使えません。ブラウザの設定でこのサイトのマイクを許可してください。";
      return;
    }
    if (navigator.wakeLock && navigator.wakeLock.request) {
      navigator.wakeLock.request("screen").catch(() => {});
    }
    state.identity = selectedId();
    if (!Number(state.info.prep_sec)) {
      beginSpeech();
      return;
    }
    runCountdown(state.info.prep_sec, "準備", ["Opinion", "Reason", "Example", "Opinion"], beginSpeech, "準備おわり");
  }

  function runCountdown(seconds, label, hints, done, skipLabel) {
    let left = seconds;
    app.innerHTML = `<p class="hint">${esc(label)}</p><p class="timer" id="left">${left}</p><p class="hint">${hints.map(esc).join(" → ")}</p>${skipLabel ? `<button id="skip">${esc(skipLabel)}</button>` : ""}`;
    const timer = setInterval(() => {
      left -= 1;
      const node = document.getElementById("left");
      if (node) node.textContent = String(Math.max(left, 0));
      if (left <= 0) {
        clearInterval(timer);
        done();
      }
    }, 1000);
    const skip = document.getElementById("skip");
    if (skip) skip.onclick = () => { clearInterval(timer); done(); };
  }

  function beginSpeech() {
    let n = 3;
    app.innerHTML = `<p class="timer" id="left">${n}</p>`;
    const timer = setInterval(() => {
      n -= 1;
      if (n <= 0) {
        clearInterval(timer);
        startRecording();
        return;
      }
      const node = document.getElementById("left");
      if (node) node.textContent = String(n);
    }, 700);
  }

  function startRecording() {
    state.samples = [];
    state.blobs = [];
    state.hidden = false;
    state.mime = pickMime();
    const recorder = new MediaRecorder(state.stream, state.mime ? { mimeType: state.mime, audioBitsPerSecond: 24000 } : { audioBitsPerSecond: 24000 });
    state.recorder = recorder;
    recorder.ondataavailable = (event) => { if (event.data && event.data.size) state.blobs.push(event.data); };
    recorder.onstop = () => finishRecording();
    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const source = audioCtx.createMediaStreamSource(state.stream);
    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 2048;
    source.connect(analyser);
    const buf = new Uint8Array(analyser.fftSize);
    recorder.start(250);
    const started = Date.now();
    const speakMs = state.info.speak_sec * 1000;
    app.innerHTML = `<p class="hint">録音中</p><p class="timer" id="left">${state.info.speak_sec}</p><div class="meter"><span id="bar"></span></div><button id="stop">終了</button>`;
    const meter = setInterval(() => {
      analyser.getByteTimeDomainData(buf);
      let sum = 0;
      for (const value of buf) {
        const x = (value - 128) / 128;
        sum += x * x;
      }
      const rms = Math.sqrt(sum / buf.length);
      state.samples.push(rms);
      const bar = document.getElementById("bar");
      if (bar) bar.style.width = `${Math.min(100, rms * 400)}%`;
      const left = Math.max(0, Math.ceil((speakMs - (Date.now() - started)) / 1000));
      const node = document.getElementById("left");
      if (node) node.textContent = String(left);
    }, 50);
    state.stopTimer = window.setTimeout(() => stopRecording(meter, audioCtx), speakMs);
    document.getElementById("stop").onclick = () => stopRecording(meter, audioCtx);
    document.addEventListener("visibilitychange", onHide);
    state._meter = meter;
    state._ctx = audioCtx;
  }

  function onHide() {
    if (document.visibilityState === "hidden" && state.recorder && state.recorder.state === "recording") {
      state.hidden = true;
      stopRecording(state._meter, state._ctx);
    }
  }

  function stopRecording(meter, audioCtx) {
    clearInterval(meter);
    clearTimeout(state.stopTimer);
    document.removeEventListener("visibilitychange", onHide);
    if (state.recorder && state.recorder.state !== "inactive") state.recorder.stop();
    if (audioCtx) audioCtx.close().catch(() => {});
    beep();
  }

  function releaseMic() {
    if (state.stream) state.stream.getTracks().forEach((track) => track.stop());
    state.stream = null;
  }

  async function finishRecording() {
    releaseMic();
    if (state.hidden) {
      app.innerHTML = `<p class="err">画面が裏に回ったので録音を中断しました。回数には数えません。</p><button id="again" class="primary">もう一度録音</button>`;
      document.getElementById("again").onclick = () => intro();
      return;
    }
    const blob = new Blob(state.blobs, { type: state.mime || "audio/mp4" });
    const duration = state.samples.length * 50;
    const stats = levels(state.samples);
    const meta = { duration_ms: duration, client_stats: stats, identity: state.identity || {} };
    try {
      await window.SpeechRecAudio.saveClip(token, blob, meta);
    } catch (error) {
      app.innerHTML = `<p class="err">端末への保存に失敗しました。プライベートブラウズでは再送できません。このまま送信します。</p>`;
    }
    await upload(blob, meta);
  }

  function levels(samples) {
    if (!samples.length) return { rms_p10: 0, rms_p90: 0, snr_db: 0 };
    const sorted = samples.slice().sort((a, b) => a - b);
    const at = (p) => sorted[Math.min(sorted.length - 1, Math.floor((sorted.length - 1) * p))];
    const p10 = Math.max(at(0.1), 1e-6);
    const p90 = Math.max(at(0.9), 1e-6);
    return { rms_p10: p10, rms_p90: p90, snr_db: 20 * Math.log10(p90 / p10) };
  }

  async function upload(blob, meta, retryOf) {
    app.innerHTML = `<p class="status" id="phase">送信中…</p>`;
    const body = new FormData();
    const type = blob.type || "audio/mp4";
    const ext = type.includes("webm") ? "webm" : "m4a";
    body.append("audio", blob, `speech.${ext}`);
    body.append("duration_ms", String(meta.duration_ms || 0));
    body.append("device_id", deviceId);
    body.append("client_stats", JSON.stringify(meta.client_stats || {}));
    const identity = meta.identity || {};
    ["year", "grade", "class", "number"].forEach((key) => {
      if (identity[key]) body.append(key, identity[key]);
    });
    if (retryOf) body.append("retry_of", retryOf);
    let res = null;
    for (let i = 0; i < 3; i += 1) {
      try {
        res = await fetch(`/rec/api/a/${encodeURIComponent(token)}/submit`, { method: "POST", body });
        break;
      } catch (error) {
        document.getElementById("phase").textContent = `送信をやり直しています（${i + 2}回目）`;
        await new Promise((resolve) => setTimeout(resolve, 800 * (i + 1)));
      }
    }
    if (!res) {
      failed("通信できませんでした。復旧したら、端末に残した音声でもう一度送れます。");
      return;
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const text = {
        too_short: "録音が短すぎるか、ほとんど音がありません。回数には数えません。",
        too_long: "録音が長すぎるため受け取れませんでした。",
        attempts: "上限に達したので、これ以上は送信できません。担当者に確認してください。",
        full: "提出の上限に達しました。",
        busy: "混み合っています。30秒後にもう一度おしてください。",
        limit: "本日の受付上限に達しました。",
        preparing: "準備中です。",
      }[data.error] || "送れませんでした。";
      if (["too_short", "too_long", "attempts", "full", "preparing"].includes(data.error)) {
        app.innerHTML = `<p class="err">${esc(text)}</p>`;
        return;
      }
      failed(text, data.error);
      return;
    }
    localStorage.setItem(readKey, data.read_token);
    rememberHistory(data.read_token);
    await poll(data.read_token);
  }

  function reevalButton(readToken) {
    const button = document.createElement("button");
    button.className = "primary";
    button.textContent = "もう一度採点";
    button.onclick = async () => {
      const res = await fetch(`/rec/api/r/${encodeURIComponent(readToken)}/reevaluate`, { method: "POST" });
      if (res.status === 409) {
        const kept = await window.SpeechRecAudio.loadClip(token);
        if (!kept) {
          app.innerHTML = `<p class="err">期限が切れたので、もう一度録音してください。</p>`;
          return;
        }
        await upload(kept.blob, kept.meta || {}, "");
        return;
      }
      if (!res.ok) {
        app.innerHTML = `<p class="err">もう一度採点できませんでした。</p>`;
        return;
      }
      await poll(readToken);
    };
    return button;
  }

  function bars(level) {
    const n = Math.max(0, Math.min(6, Number(level) || 0));
    return `<span class="ticks">${[1, 2, 3, 4, 5, 6].map((i) => `<i class="${i <= n ? "on" : ""}"></i>`).join("")}</span>`;
  }

  function points(data, key) {
    if (!data.show_points) return "";
    const value = data.scores && data.scores.points ? data.scores.points[key] : "";
    return esc(value);
  }

  function renderScore(data) {
    const oreo = data.oreo || {};
    const mark = (on) => `<span class="dot ${on ? "on" : ""}"></span>`;
    const when = esc(String(data.created_at || "").replace("T", " ").slice(0, 16));
    const total = data.show_points && data.scores ? esc(data.scores.total) : "—";
    const wpm = data.show_points ? esc(data.wpm_points) : "—";
    const rubric = data.show_points && data.scores ? esc(Math.round((data.scores.total || 0) - (data.wpm_points || 0))) : "—";
    app.className = "app sheet";
    app.innerHTML = `
      <p class="meta"><a href="/rec/my">自分の結果</a> ${when} ・ 試行 ${esc(data.attempt)}</p>
      <p class="topic">${esc(data.topic)}</p>
      <p class="total">${total}</p>
      <p class="sub">WPM点 ${wpm} ／ ルーブリック ${rubric}</p>
      <div class="bars">
        <div class="bar-row"><span>General Description</span>${bars((data.levels || {}).general_description)}<span>${points(data, "general_description")}</span></div>
        <div class="bar-row"><span>Delivery（流暢さ）</span>${bars((data.levels || {}).delivery)}<span>${points(data, "delivery")}</span></div>
        <div class="bar-row"><span>Language Use</span>${bars((data.levels || {}).language_use)}<span>${points(data, "language_use")}</span></div>
        <div class="bar-row"><span>Topic Development</span>${bars((data.levels || {}).topic_development)}<span>${points(data, "topic_development")}</span></div>
      </div>
      <p class="oreo">OREO ${mark(oreo.opinion_open)} O ${mark(oreo.reason)} R ${mark(oreo.example)} E ${mark(oreo.opinion_close)} O</p>
      <div class="foot">
        <button type="button" id="detail">詳細</button>
        <span class="code">${esc(data.verify_code || "")}</span>
      </div>`;
    document.getElementById("detail").onclick = () => openDetail(state.readToken);
  }

  async function openDetail(readToken) {
    app.className = "app detail";
    const res = await fetch(`/rec/api/r/${encodeURIComponent(readToken)}?detail=1`);
    const data = await res.json().catch(() => ({}));
    if (data.detail_expired || data.transcript == null) {
      app.innerHTML = `<p class="err">期限が切れました</p><button type="button" id="back">結果に戻る</button>`;
      document.getElementById("back").onclick = () => renderScore(state.result || data);
      return;
    }
    const comments = data.comments || {};
    const evidence = data.evidence || {};
    const levels = data.levels || {};
    app.innerHTML = `
      <button type="button" id="back">結果に戻る</button>
      <h2>詳細</h2>
      <div id="player"><button type="button" id="play">再生</button><input id="seek" type="range" min="0" max="1000" value="0"></div>
      <p>General Description ${esc(levels.general_description || "")}：${esc(comments.general_description || "")}</p>
      <p>Delivery（流暢さ） ${esc(levels.delivery || "")}：${esc(data.delivery_text || "")}</p>
      <p>Language Use ${esc(levels.language_use || "")}：${esc(comments.language_use || "")}</p>
      <p>Topic Development ${esc(levels.topic_development || "")}：${esc(comments.topic_development || "")}</p>
      <p>次の一歩：${esc(data.next_step || "")}</p>
      <p>Opinion ${esc(evidence.opinion_open || "")}</p>
      <p>Reason ${esc(evidence.reason || "")}</p>
      <p>Example ${esc(evidence.example || "")}</p>
      <p>結び ${esc(evidence.opinion_close || "")}</p>
      <p>${esc(data.transcript)}</p>`;
    document.getElementById("back").onclick = () => {
      stopPlayer();
      renderScore(state.result || data);
    };
    bindPlayer(state.audioBlob, state.durationMs);
  }

  const player = { audio: null, url: "" };

  function stopPlayer() {
    if (!player.audio) return;
    player.audio.pause();
    if (player.url) URL.revokeObjectURL(player.url);
    player.url = "";
    player.audio.removeAttribute("src");
    player.audio.load();
  }

  function bindPlayer(blob, durationMs) {
    const button = document.getElementById("play");
    const seek = document.getElementById("seek");
    if (!blob) {
      button.textContent = "この画面を開き直すと録音は聞けません";
      button.disabled = true;
      return;
    }
    if (!player.audio) player.audio = new Audio();
    stopPlayer();
    player.url = URL.createObjectURL(blob);
    const audio = player.audio;
    audio.src = player.url;
    const fallback = Math.max(0, Number(durationMs) || 0) / 1000;
    const known = () => (Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration : fallback);
    audio.addEventListener("loadedmetadata", () => {
      if (!Number.isFinite(audio.duration)) {
        const back = () => {
          audio.currentTime = 0;
          audio.removeEventListener("durationchange", back);
        };
        audio.addEventListener("durationchange", back);
        try { audio.currentTime = 1e101; } catch (error) { /* ブラウザが拒否することがある */ }
      }
    }, { once: true });
    button.onclick = () => {
      if (!audio.paused) {
        audio.pause();
        button.textContent = "再生";
        return;
      }
      audio.play();
      button.textContent = "停止";
    };
    audio.ontimeupdate = () => {
      const length = known();
      if (length > 0) seek.value = String(Math.round((audio.currentTime / length) * 1000));
    };
    audio.onended = () => {
      audio.currentTime = 0;
      seek.value = "0";
      button.textContent = "再生";
    };
    seek.oninput = () => {
      const length = known();
      if (length > 0) audio.currentTime = (Number(seek.value) / 1000) * length;
    };
    window.addEventListener("pagehide", stopPlayer, { once: true });
  }

  function rememberHistory(readToken) {
    const key = "speechrec:history";
    const now = Date.now();
    const keep = 60 * 24 * 60 * 60 * 1000;
    let rows = [];
    try { rows = JSON.parse(localStorage.getItem(key) || "[]"); } catch (error) { rows = []; }
    if (!Array.isArray(rows)) rows = [];
    rows = rows.filter((row) => row && row.read_token && now - Number(row.saved_at) < keep && row.read_token !== readToken);
    rows.push({ read_token: readToken, saved_at: now });
    localStorage.setItem(key, JSON.stringify(rows.slice(-30)));
  }

  function retryButton(recordId) {
    const button = document.createElement("button");
    button.className = "primary";
    button.textContent = "もう一度採点";
    button.onclick = async () => {
      const kept = await window.SpeechRecAudio.loadClip(token);
      if (!kept) {
        app.innerHTML = `<p class="err">端末の録音が見つかりません。もう一度録音してください。</p>`;
        return;
      }
      await upload(kept.blob, kept.meta || {}, recordId || "");
    };
    return button;
  }

  async function poll(readToken) {
    localStorage.setItem(readKey, readToken);
    app.innerHTML = `<p class="status" id="phase">文字起こし中…</p>`;
    let data = {};
    const started = Date.now();
    let wait = 1500;
    while (Date.now() - started < 180000) {
      const res = await fetch(`/rec/api/r/${encodeURIComponent(readToken)}`);
      data = await res.json().catch(() => ({}));
      if (data.status === "done" || data.status === "error") break;
      const phase = document.getElementById("phase");
      if (phase) phase.textContent = data.status === "received" ? "送信しました。文字起こしを待っています。" : "文字起こし中…";
      await new Promise((resolve) => setTimeout(resolve, wait));
      wait = Math.min(5000, wait + 500);
    }
    if (data.status === "done") {
      clearRead();
      const kept = await window.SpeechRecAudio.loadClip(token).catch(() => null);
      state.audioBlob = kept && kept.blob;
      state.durationMs = kept && kept.meta ? kept.meta.duration_ms : 0;
      await window.SpeechRecAudio.deleteClip(token).catch(() => {});
      state.result = data;
      state.readToken = readToken;
      renderScore(data);
      return;
    }
    if (data.status === "error") {
      if (data.error_code !== "eval_failed") clearRead();
      const quiet = data.error_code === "too_short" || data.error_code === "silent";
      app.innerHTML = `<p class="err">${esc(quiet ? "録音が短すぎるか、ほとんど言葉がありません。回数には数えません。" : data.error_code === "eval_failed" ? "評価ができませんでした。文字起こしが残っていれば、もう一度採点できます。" : "文字起こしができませんでした。端末に残した音声でもう一度採点できます。")}</p>`;
      if (data.error_code === "eval_failed") app.appendChild(reevalButton(readToken));
      else if (!quiet) app.appendChild(retryButton(data.id));
      return;
    }
    app.innerHTML = `<p class="status">時間がかかっています。端末に残した音声でもう一度採点できます。</p>`;
    app.appendChild(retryButton(data.id));
  }

  function failed(message) {
    app.innerHTML = `<p class="err">${esc(message)}</p><button id="resend" class="primary">もう一度送る</button><button id="drop">端末の録音を削除</button>`;
    document.getElementById("resend").onclick = async () => {
      const kept = await window.SpeechRecAudio.loadClip(token);
      if (!kept) {
        app.innerHTML = `<p class="err">端末の録音が見つかりません。もう一度録音してください。</p>`;
        return;
      }
      upload(kept.blob, kept.meta || {});
    };
    document.getElementById("drop").onclick = async () => {
      clearRead();
      await window.SpeechRecAudio.deleteClip(token);
      app.innerHTML = `<p class="status">削除しました。</p>`;
    };
  }

  if (document.body.dataset.preview) renderScore(JSON.parse(document.body.dataset.preview));
  else load();
})();
