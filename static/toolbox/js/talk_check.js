(function () {
  const views = {};
  document.querySelectorAll("[data-view]").forEach((el) => { views[el.dataset.view] = el; });
  const settingsForm = document.getElementById("tb-talk-settings");
  const state = {
    view: "settings",
    audioBlob: null,
    transcript: "",
    browserTranscript: "",
    questions: [],
    sessionId: null,
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
  };

  function settings() {
    const fd = new FormData(settingsForm);
    return {
      level: fd.get("level") || "A2",
      count: Number(fd.get("count") || 5),
      include_inference: fd.has("include_inference"),
      notes: fd.get("notes") || "",
      keywords: fd.get("keywords") || "",
      stt_mode: fd.get("stt_mode") || "whisper",
      review_transcript: fd.has("review_transcript"),
      show_live: fd.has("show_live"),
      parallel_browser: fd.has("parallel_browser"),
      wait_prompt: fd.get("wait_prompt") || "Talk with your partner. What did you hear?",
      mic: fd.get("mic") || "",
    };
  }

  function show(name) {
    state.view = name;
    Object.entries(views).forEach(([key, el]) => { el.hidden = key !== name; });
  }

  document.querySelectorAll("[data-go]").forEach((btn) => {
    btn.addEventListener("click", () => show(btn.dataset.go));
  });

  function SpeechRecognitionCtor() {
    return window.SpeechRecognition || window.webkitSpeechRecognition || null;
  }

  async function loadMics() {
    const sel = document.getElementById("tb-mic");
    if (!navigator.mediaDevices?.enumerateDevices) return;
    const devices = await navigator.mediaDevices.enumerateDevices();
    const mics = devices.filter((d) => d.kind === "audioinput");
    const last = localStorage.getItem("toolbox.talk_check.mic") || "";
    sel.innerHTML = mics.map((d) => `<option value="${d.deviceId}">${d.label || "マイク"}</option>`).join("");
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
      state.browserTranscript = text.trim();
      if (liveEl && settings().show_live) liveEl.textContent = state.browserTranscript;
    };
    rec.onerror = () => {
      state.speechErrors += 1;
      if (state.speechErrors >= 3 && state.mediaRecorder) {
        stopRecognition("errors");
      }
    };
    rec.onend = () => {
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
    if (elapsed >= 600) stopRecording(false);
  }

  async function startRecording() {
    const stream = await getStream();
    state.stream = stream;
    state.chunks = [];
    state.browserTranscript = "";
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
    await requestWake();
    watchLevel(stream, document.getElementById("tb-rec-meter"), document.getElementById("tb-rec-msg"));
    const live = document.getElementById("tb-live");
    live.hidden = !settings().show_live;
    const cfg = settings();
    const canBrowser = !!SpeechRecognitionCtor();
    if (!canBrowser) {
      settingsForm.parallel_browser.closest("label").hidden = true;
      settingsForm.stt_mode.querySelector('option[value="browser"]').hidden = true;
    }
    if (canBrowser && (cfg.stt_mode === "browser" || cfg.parallel_browser)) {
      state.parallelOn = cfg.stt_mode !== "browser";
      startRecognition({ liveEl: live });
      toolboxFetch("/toolbox/api/talk/events", {
        method: "POST",
        body: JSON.stringify({ name: state.parallelOn ? "browser_stt_parallel_on" : "browser_stt_parallel_off" }),
      }).catch(() => {});
    }
    show("record");
  }

  document.querySelector("[data-go=record]").addEventListener("click", (ev) => {
    ev.preventDefault();
    startRecording().catch((err) => alert(err.message));
  });

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
    rec.onstop = () => {
      stream?.getTracks().forEach((t) => t.stop());
      if (!keep) {
        state.audioBlob = null;
        show("settings");
        return;
      }
      state.audioBlob = new Blob(state.chunks, { type: rec.mimeType || "audio/webm" });
      afterAudioReady("record", (Date.now() - state.recStarted) / 1000);
    };
    if (rec.state !== "inactive") rec.stop();
    else rec.onstop();
  }

  document.getElementById("tb-stop").addEventListener("click", () => stopRecording(true));
  document.getElementById("tb-cancel-rec").addEventListener("click", () => stopRecording(false));

  function beginWait() {
    show("wait");
    document.getElementById("tb-wait-prompt").textContent = settings().wait_prompt;
    document.getElementById("tb-start-qs").hidden = true;
    document.getElementById("tb-choose-qs").hidden = true;
    document.getElementById("tb-retry-send").hidden = true;
    document.getElementById("tb-wait-error").hidden = true;
    state.waitStarted = Date.now();
    clearInterval(state.waitTimer);
    state.waitTimer = setInterval(() => {
      const sec = Math.floor((Date.now() - state.waitStarted) / 1000);
      document.getElementById("tb-wait-clock").textContent = `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;
    }, 250);
  }

  function waitStatus(text) {
    document.getElementById("tb-wait-status").textContent = text;
  }

  function waitError(message, retry) {
    const el = document.getElementById("tb-wait-error");
    el.textContent = message;
    el.hidden = false;
    document.getElementById("tb-retry-send").hidden = !retry;
    state.pendingRetry = retry || null;
  }

  document.getElementById("tb-retry-send").addEventListener("click", () => {
    if (state.pendingRetry) state.pendingRetry();
  });

  async function transcribeBlob(blob, durationSec) {
    const cfg = settings();
    if (cfg.stt_mode === "browser") {
      if (!state.browserTranscript) throw new Error("ブラウザの文字起こしが取れませんでした。テキスト貼り付けを使ってください。");
      return state.browserTranscript;
    }
    const fd = new FormData();
    fd.append("audio", blob, "speech.webm");
    fd.append("duration_sec", String(Math.round(durationSec || 0)));
    fd.append("keywords", cfg.keywords);
    const res = await fetch("/toolbox/api/talk/transcribe", {
      method: "POST",
      headers: { "X-CSRF-Token": window.TOOLBOX_CSRF || "" },
      body: fd,
      credentials: "same-origin",
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      if (state.browserTranscript) return state.browserTranscript;
      const err = new Error(data.error || "文字起こしに失敗しました。テキスト貼り付けを試してください。");
      err.data = data;
      throw err;
    }
    return data.transcript;
  }

  async function generateFromTranscript(transcript, source) {
    const cfg = settings();
    const data = await toolboxFetch("/toolbox/api/talk/generate", {
      method: "POST",
      body: JSON.stringify({
        transcript,
        level: cfg.level,
        count: cfg.count,
        include_inference: cfg.include_inference,
        notes: cfg.notes,
        source,
        wait_prompt: cfg.wait_prompt,
        keywords: cfg.keywords,
      }),
    });
    state.sessionId = data.session_id;
    state.questions = data.questions || [];
    state.transcript = transcript;
    return data;
  }

  async function afterAudioReady(source, durationSec) {
    const cfg = settings();
    beginWait();
    waitStatus("文字起こし中");
    try {
      const text = await transcribeBlob(state.audioBlob, durationSec);
      state.transcript = text;
      if (cfg.review_transcript) {
        document.getElementById("tb-review").value = text;
        show("review");
        return;
      }
      waitStatus("問題作成中");
      await generateFromTranscript(text, source);
      readyToStart();
    } catch (err) {
      waitError(err.message + (err.message.includes("テキスト") ? "" : " テキスト貼り付けに切り替えられます。"), () => afterAudioReady(source, durationSec));
    }
  }

  function readyToStart() {
    waitStatus("準備完了");
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
    state.audioBlob = file;
    afterAudioReady("file", 0);
  });

  document.getElementById("tb-paste-go").addEventListener("click", async () => {
    const text = document.getElementById("tb-paste").value.trim();
    if (!text) {
      alert("英文を貼り付けてください。");
      return;
    }
    beginWait();
    waitStatus("問題作成中");
    try {
      await generateFromTranscript(text, "paste");
      readyToStart();
    } catch (err) {
      waitError(err.message, () => document.getElementById("tb-paste-go").click());
    }
  });

  document.getElementById("tb-review-go").addEventListener("click", async () => {
    const text = document.getElementById("tb-review").value.trim();
    beginWait();
    waitStatus("問題作成中");
    try {
      await generateFromTranscript(text, "record");
      readyToStart();
    } catch (err) {
      waitError(err.message, () => document.getElementById("tb-review-go").click());
    }
  });

  function visibleQuestions() {
    return state.questions.filter((q) => q.included !== false);
  }

  function renderSelect() {
    const list = document.getElementById("tb-select-list");
    list.innerHTML = state.questions.map((q, i) => `
      <li>
        <label class="tb-check"><input type="checkbox" data-i="${i}" ${q.included === false ? "" : "checked"}> 問題 ${i + 1}</label>
        <p class="tb-blur" data-reveal>${q.question}</p>
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
    const ans = document.getElementById("tb-answer");
    ans.hidden = !state.showingAnswer;
    ans.textContent = `${q.model_answer}  (${q.short_answer})`;
    const ev = document.getElementById("tb-evidence");
    ev.hidden = true;
    ev.textContent = q.evidence || "";
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
      `<li><strong>${q.question}</strong><br>${q.model_answer}</li>`
    )).join("");
  }

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

  async function openSession(id) {
    const data = await toolboxFetch(`/toolbox/api/talk/sessions/${id}`);
    state.sessionId = data.session.id;
    state.questions = data.session.questions || [];
    state.transcript = data.session.transcript || "";
    startPlay();
  }

  document.getElementById("tb-history-list").addEventListener("click", async (ev) => {
    const open = ev.target.dataset.open;
    const del = ev.target.dataset.del;
    if (open) openSession(open).catch((e) => alert(e.message));
    if (del && confirm("この履歴を削除しますか？")) {
      try {
        await toolboxFetch(`/toolbox/api/talk/sessions/${del}`, { method: "DELETE" });
        ev.target.closest("li").remove();
      } catch (e) {
        alert(e.message);
      }
    }
  });

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
})();
