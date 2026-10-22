(function () {
  const app = document.getElementById("app");
  const token = document.body.dataset.token;
  const deviceKey = "speech_rec_device";
  let deviceId = localStorage.getItem(deviceKey);
  if (!deviceId) {
    deviceId = crypto.randomUUID();
    localStorage.setItem(deviceKey, deviceId);
  }

  const state = { info: null, blobs: [], mime: "", recorder: null, stream: null, samples: [], stopTimer: 0, hidden: false };

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
      <p class="note">あなたの声は採点のため、外部のAIサービス（OpenAI）に送られます。このアプリには音声を残しません。文字起こしは30分で消えます。結果は先生に提出するスクリーンショットだけに残ります。</p>
      <p class="small">準備 ${info.prep_sec} 秒 → スピーチ ${info.speak_sec} 秒。端末ごとに ${info.attempts_per_device} 回まで。</p>
      <button id="start" class="primary">マイクを許可して準備スタート</button>
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
      state.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (error) {
      err.textContent = "マイクが使えません。ブラウザの設定でこのサイトのマイクを許可してください。";
      return;
    }
    if (navigator.wakeLock && navigator.wakeLock.request) {
      navigator.wakeLock.request("screen").catch(() => {});
    }
    state.identity = selectedId();
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
        attempts: "この端末の回数（2回）を使い切りました。",
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
    await poll(data.read_token);
  }

  async function poll(readToken) {
    const phase = document.getElementById("phase") || app.appendChild(document.createElement("p"));
    phase.id = "phase";
    phase.textContent = "受け付けました。採点が始まるまで、この画面を開いたままにしてください。";
    const res = await fetch(`/rec/api/r/${encodeURIComponent(readToken)}`);
    const data = await res.json().catch(() => ({}));
    if (data.status === "done") {
      await window.SpeechRecAudio.deleteClip(token).catch(() => {});
      phase.textContent = "採点が終わりました。";
      return;
    }
    if (data.status === "error") {
      phase.textContent = "サーバー側で採点できませんでした。";
      const button = document.createElement("button");
      button.className = "primary";
      button.textContent = "もう一度採点";
      button.onclick = async () => {
        const kept = await window.SpeechRecAudio.loadClip(token);
        if (!kept) {
          phase.textContent = "端末の録音が見つかりません。もう一度録音してください。";
          return;
        }
        kept.meta.retry_of = data.id;
        await upload(kept.blob, kept.meta, data.id);
      };
      app.appendChild(button);
      return;
    }
    phase.textContent = `受け付けました（試行 ${data.attempt || ""}）。採点は次の更新から始まります。録音は結果が出るまで端末に残しています。`;
    const del = document.createElement("button");
    del.textContent = "端末の録音を削除";
    del.onclick = async () => {
      await window.SpeechRecAudio.deleteClip(token);
      del.textContent = "削除しました";
    };
    app.appendChild(del);
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
      await window.SpeechRecAudio.deleteClip(token);
      app.innerHTML = `<p class="status">削除しました。</p>`;
    };
  }

  load();
})();
