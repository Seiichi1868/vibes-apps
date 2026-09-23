(() => {
  "use strict";

  const openingOverlay = document.getElementById("opening-overlay");
  if (openingOverlay) {
    window.setTimeout(() => {
      openingOverlay.style.transition = "opacity 300ms ease";
      openingOverlay.style.opacity = "0";
      openingOverlay.style.pointerEvents = "none";
      window.setTimeout(() => openingOverlay.remove(), 320);
    }, 1950);
  }

  const API = "/trigger/api";
  const STEP_ORDER = ["login", "script", "sample", "readaloud", "qa", "speech", "report"];

  const state = {
    sessionId: null,
    session: null,
    themes: [],
    studentInfoRequired: true,
    selectedThemeId: null,
    scriptMode: null,
    qaIndex: 0,
    speechIndex: 0,
    mediaRecorder: null,
    audioChunks: [],
    speechTimerHandle: null,
    speechTimerStart: null,
  };

  const $ = (id) => document.getElementById(id);

  function showScreen(name) {
    document.querySelectorAll(".screen").forEach((el) => el.classList.add("hidden"));
    const el = $(`screen-${name}`);
    if (el) el.classList.remove("hidden");
    document.querySelectorAll("#step-dots .step-dot").forEach((dot) => {
      const step = dot.getAttribute("data-step");
      dot.classList.remove("active", "done");
      const stepIdx = STEP_ORDER.indexOf(step);
      const currentIdx = STEP_ORDER.indexOf(name);
      if (stepIdx < currentIdx) dot.classList.add("done");
      else if (stepIdx === currentIdx) dot.classList.add("active");
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function fetchJson(url, options = {}) {
    const res = await fetch(url, options);
    let data;
    try {
      data = await res.json();
    } catch (_) {
      throw new Error(`サーバーエラー (HTTP ${res.status})`);
    }
    if (!res.ok || data.ok === false) {
      throw new Error(data.error || `エラーが発生しました (HTTP ${res.status})`);
    }
    return data;
  }

  function setError(id, message) {
    const el = $(id);
    if (el) el.textContent = message || "";
  }

  // ── ログイン / テーマ選択 ────────────────────────────────

  async function loadThemesAndRoster() {
    try {
      const configData = await fetchJson(`${API}/config`).catch(() => ({ student_info_required: true }));
      state.studentInfoRequired = configData.student_info_required !== false;
      if (!state.studentInfoRequired) {
        $("student-info-section").classList.add("hidden");
      }
      validateLoginForm();

      const [themeData, rosterData] = await Promise.all([
        fetchJson(`${API}/themes`),
        state.studentInfoRequired
          ? fetchJson(`${API}/roster`).catch(() => ({ students: [], classes: [] }))
          : Promise.resolve({ students: [], classes: [] }),
      ]);
      state.themes = themeData.themes || [];
      renderThemeList();

      const classList = $("class-list");
      (rosterData.classes || []).forEach((c) => {
        const opt = document.createElement("option");
        opt.value = c;
        classList.appendChild(opt);
      });

      if ((rosterData.students || []).length > 0) {
        $("roster-select-wrap").classList.remove("hidden");
        const select = $("roster-select");
        rosterData.students.forEach((s) => {
          const opt = document.createElement("option");
          opt.value = JSON.stringify(s);
          opt.textContent = `${s.class_name || ""}　${s.number || ""}　${s.name || ""}`.trim();
          select.appendChild(opt);
        });
        select.addEventListener("change", (e) => {
          if (!e.target.value) return;
          try {
            const s = JSON.parse(e.target.value);
            $("input-class").value = s.class_name || "";
            $("input-number").value = s.number || "";
            $("input-name").value = s.name || "";
            validateLoginForm();
          } catch (_) {
            /* ignore */
          }
        });
      }
    } catch (exc) {
      setError("login-error", exc.message);
    }
  }

  function renderThemeList() {
    const container = $("theme-list");
    container.innerHTML = "";
    state.themes.forEach((theme) => {
      const card = document.createElement("button");
      card.type = "button";
      card.className =
        "theme-card glass-inset rounded-xl p-3 text-left transition";
      card.dataset.themeId = theme.id;
      card.innerHTML = `<p class="text-sm font-semibold accent-heading">${escapeHtml(theme.title)}</p>
        <p class="mt-1 text-xs text-slate-500">${escapeHtml(theme.description_hint || "")}</p>`;
      card.addEventListener("click", () => {
        state.selectedThemeId = theme.id;
        document.querySelectorAll(".theme-card").forEach((c) => c.classList.remove("is-selected"));
        card.classList.add("is-selected");
        validateLoginForm();
      });
      container.appendChild(card);
    });
  }

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text || "";
    return div.innerHTML;
  }

  function validateLoginForm() {
    if (!state.studentInfoRequired) {
      $("btn-start").disabled = !state.selectedThemeId;
      return;
    }
    const hasName = $("input-name").value.trim() || $("input-number").value.trim();
    $("btn-start").disabled = !(hasName && state.selectedThemeId);
  }

  ["input-class", "input-number", "input-name"].forEach((id) => {
    $(id).addEventListener("input", validateLoginForm);
  });

  $("btn-start").addEventListener("click", async () => {
    setError("login-error", "");
    try {
      const payload = {
        theme_id: state.selectedThemeId,
        student_info: {
          class_name: $("input-class").value.trim(),
          number: $("input-number").value.trim(),
          name: $("input-name").value.trim(),
        },
      };
      const data = await fetchJson(`${API}/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      state.sessionId = data.session_id;
      state.session = data.session;
      history.replaceState(null, "", `/trigger/session/${state.sessionId}`);
      const theme = state.themes.find((t) => t.id === state.selectedThemeId);
      $("script-theme-label").textContent = `テーマ: ${theme ? theme.title : ""}${theme && theme.description_hint ? " ｜ " + theme.description_hint : ""}`;
      showScreen("script");
    } catch (exc) {
      setError("login-error", exc.message);
    }
  });

  // ── ステップ1: 台本作成 ─────────────────────────────────

  document.querySelectorAll(".mode-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.scriptMode = btn.dataset.mode;
      document.querySelectorAll(".mode-btn").forEach((b) => b.classList.remove("is-selected"));
      btn.classList.add("is-selected");
      $("script-input").placeholder =
        state.scriptMode === "translate"
          ? "日本語で自由に書いてください（AIが英訳します）"
          : "英語で書いてください（AIが校正します）";
      $("btn-generate-script").disabled = false;
    });
  });

  async function runScriptStep() {
    setError("script-error", "");
    const inputText = $("script-input").value.trim();
    if (!inputText) {
      setError("script-error", "テキストを入力してください。");
      return;
    }
    $("btn-generate-script").disabled = true;
    $("btn-generate-script").textContent = "AI処理中...";
    try {
      const endpoint = state.scriptMode === "translate" ? "translate" : "correct";
      const data = await fetchJson(`${API}/script/${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: state.sessionId, input_text: inputText }),
      });
      $("script-output").value = data.script.output_text;
      $("script-notes").textContent = data.script.notes || "";
      const correctionsBox = $("script-corrections");
      correctionsBox.innerHTML = "";
      (data.script.corrections || []).forEach((c) => {
        const p = document.createElement("p");
        p.innerHTML = `<span class="line-through text-rose-500">${escapeHtml(c.before)}</span> → <span class="accent-good">${escapeHtml(c.after)}</span> <span class="text-slate-400">(${escapeHtml(c.reason)})</span>`;
        correctionsBox.appendChild(p);
      });
      $("script-result").classList.remove("hidden");
    } catch (exc) {
      setError("script-error", exc.message);
    } finally {
      $("btn-generate-script").disabled = false;
      $("btn-generate-script").textContent = "AIに送る";
    }
  }

  $("btn-generate-script").addEventListener("click", runScriptStep);
  $("btn-regenerate-script").addEventListener("click", runScriptStep);

  $("btn-confirm-script").addEventListener("click", async () => {
    setError("script-error", "");
    try {
      const outputText = $("script-output").value.trim();
      const data = await fetchJson(`${API}/script/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: state.sessionId, output_text: outputText }),
      });
      state.session = data.session;
      $("sample-script-text").textContent = outputText;
      $("readaloud-script-text").textContent = outputText;
      await generateSampleAudio();
    } catch (exc) {
      setError("script-error", exc.message);
    }
  });

  // ── ステップ2: 模範音声 ─────────────────────────────────

  async function generateSampleAudio() {
    setError("sample-error", "");
    try {
      const data = await fetchJson(`${API}/tts/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: state.sessionId }),
      });
      $("sample-audio").src = data.audio_url;
      showScreen("sample");
    } catch (exc) {
      setError("sample-error", exc.message);
      showScreen("sample");
    }
  }

  $("btn-to-readaloud").addEventListener("click", () => {
    showScreen("readaloud");
  });

  // ── 録音共通処理 ────────────────────────────────────────

  async function startRecording(onStop) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      state.mediaRecorder = recorder;
      state.audioChunks = [];
      recorder.addEventListener("dataavailable", (e) => {
        if (e.data.size > 0) state.audioChunks.push(e.data);
      });
      recorder.addEventListener("stop", () => {
        stream.getTracks().forEach((track) => track.stop());
        const blob = new Blob(state.audioChunks, { type: recorder.mimeType || "audio/webm" });
        onStop(blob);
      });
      recorder.start();
      return true;
    } catch (exc) {
      alert("マイクへのアクセスが許可されていません。ブラウザの設定をご確認ください。");
      return false;
    }
  }

  function stopRecording() {
    if (state.mediaRecorder && state.mediaRecorder.state !== "inactive") {
      state.mediaRecorder.stop();
    }
  }

  // ── ステップ3: 音読→発音評価 ────────────────────────────

  $("btn-record-readaloud").addEventListener("click", async () => {
    if (state.mediaRecorder && state.mediaRecorder.state === "recording") {
      $("btn-record-readaloud").disabled = true;
      $("readaloud-status").textContent = "採点中です。しばらくお待ちください...";
      stopRecording();
      return;
    }
    setError("readaloud-error", "");
    const started = await startRecording(async (blob) => {
      await submitReadaloud(blob);
    });
    if (started) {
      $("btn-record-readaloud").textContent = "⏹ 録音終了";
      $("readaloud-rec-indicator").classList.remove("hidden");
      $("readaloud-rec-indicator").classList.add("flex");
    }
  });

  async function submitReadaloud(blob) {
    $("readaloud-rec-indicator").classList.add("hidden");
    try {
      const formData = new FormData();
      formData.append("session_id", state.sessionId);
      formData.append("audio", blob, "readaloud.webm");
      const data = await fetchJson(`${API}/pronunciation/evaluate`, { method: "POST", body: formData });
      const result = data.pronunciation_result;
      $("readaloud-accuracy").textContent = result.scores.accuracy;
      $("readaloud-fluency").textContent = result.scores.fluency;
      $("readaloud-feedback").textContent = result.feedback_text;
      $("readaloud-result").classList.remove("hidden");
      $("readaloud-status").textContent = "";
    } catch (exc) {
      setError("readaloud-error", exc.message);
      $("readaloud-status").textContent = "";
    } finally {
      $("btn-record-readaloud").disabled = false;
      $("btn-record-readaloud").textContent = "🎙 録音開始";
    }
  }

  $("btn-to-qa").addEventListener("click", async () => {
    setError("qa-error", "");
    try {
      const data = await fetchJson(`${API}/qa/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: state.sessionId }),
      });
      state.session = data.session;
      state.qaIndex = 0;
      showScreen("qa");
      renderQaItem();
    } catch (exc) {
      setError("qa-error", exc.message);
    }
  });

  // ── ステップ4: フォローアップQ&A ─────────────────────────

  function renderQaItem() {
    const items = state.session.qa_items || [];
    const item = items[state.qaIndex];
    if (!item) return;
    $("qa-progress-label").textContent = `質問 ${state.qaIndex + 1} / ${items.length}`;
    $("qa-question-text").textContent = item.question_text;
    $("qa-question-audio").src = item.question_audio_url || "";
    $("qa-result").classList.add("hidden");
    $("btn-record-qa").classList.remove("hidden");
    $("btn-record-qa").textContent = "🎙 録音して回答";
    $("btn-record-qa").disabled = false;
  }

  $("btn-record-qa").addEventListener("click", async () => {
    if (state.mediaRecorder && state.mediaRecorder.state === "recording") {
      $("btn-record-qa").disabled = true;
      $("qa-status").textContent = "採点中です。しばらくお待ちください...";
      stopRecording();
      return;
    }
    setError("qa-error", "");
    const items = state.session.qa_items || [];
    const item = items[state.qaIndex];
    const started = await startRecording(async (blob) => {
      await submitQaAnswer(item.id, blob);
    });
    if (started) {
      $("btn-record-qa").textContent = "⏹ 録音終了";
      $("qa-rec-indicator").classList.remove("hidden");
      $("qa-rec-indicator").classList.add("flex");
    }
  });

  async function submitQaAnswer(qaId, blob) {
    $("qa-rec-indicator").classList.add("hidden");
    try {
      const formData = new FormData();
      formData.append("session_id", state.sessionId);
      formData.append("qa_id", qaId);
      formData.append("audio", blob, "qa_answer.webm");
      const data = await fetchJson(`${API}/qa/evaluate`, { method: "POST", body: formData });
      state.session = data.session;
      const evalResult = data.qa_item.evaluation;
      $("qa-transcript").textContent = data.qa_item.student_answer_transcript;
      $("qa-relevance").textContent = evalResult.scores.relevance;
      $("qa-consistency").textContent = evalResult.scores.content_consistency;
      $("qa-feedback").textContent = evalResult.feedback_text;
      $("qa-result").classList.remove("hidden");
      $("btn-record-qa").classList.add("hidden");
      $("qa-status").textContent = "";
      $("btn-qa-next").dataset.allAnswered = data.all_answered ? "1" : "0";
    } catch (exc) {
      setError("qa-error", exc.message);
      $("qa-status").textContent = "";
      $("btn-record-qa").disabled = false;
      $("btn-record-qa").textContent = "🎙 録音して回答";
    }
  }

  $("btn-qa-next").addEventListener("click", async () => {
    const items = state.session.qa_items || [];
    if (state.qaIndex < items.length - 1) {
      state.qaIndex += 1;
      renderQaItem();
    } else {
      await proceedToSpeech();
    }
  });

  // ── ステップ5: 即興スピーチ ─────────────────────────────

  async function proceedToSpeech() {
    setError("speech-error", "");
    try {
      const data = await fetchJson(`${API}/speech/topic`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: state.sessionId }),
      });
      state.session = data.session;
      state.speechIndex = 0;
      showScreen("speech");
      renderSpeechItem();
    } catch (exc) {
      setError("speech-error", exc.message);
    }
  }

  function renderSpeechItem() {
    const items = state.session.speech_items || [];
    const item = items[state.speechIndex];
    if (!item) return;
    $("speech-progress-label").textContent = `トピック ${state.speechIndex + 1} / ${items.length}`;
    $("speech-topic-text").textContent = item.topic_text;
    $("speech-topic-text-ja").textContent = item.topic_text_ja || "";
    const audioEl = $("speech-topic-audio");
    if (item.topic_audio_url) {
      audioEl.src = item.topic_audio_url;
      audioEl.classList.remove("hidden");
    } else {
      audioEl.classList.add("hidden");
    }
    $("speech-result").classList.add("hidden");
    $("btn-record-speech").classList.remove("hidden");
    $("btn-record-speech").textContent = "🎙 録音開始";
    $("btn-record-speech").disabled = false;
  }

  function startSpeechTimer() {
    state.speechTimerStart = Date.now();
    $("speech-rec-timer").textContent = "録音中... 0:00";
    state.speechTimerHandle = setInterval(() => {
      const elapsed = Math.floor((Date.now() - state.speechTimerStart) / 1000);
      const mm = Math.floor(elapsed / 60);
      const ss = String(elapsed % 60).padStart(2, "0");
      $("speech-rec-timer").textContent = `録音中... ${mm}:${ss}`;
    }, 1000);
  }

  function stopSpeechTimer() {
    if (state.speechTimerHandle) {
      clearInterval(state.speechTimerHandle);
      state.speechTimerHandle = null;
    }
  }

  $("btn-record-speech").addEventListener("click", async () => {
    if (state.mediaRecorder && state.mediaRecorder.state === "recording") {
      $("btn-record-speech").disabled = true;
      $("speech-status").textContent = "採点中です。しばらくお待ちください...";
      stopSpeechTimer();
      stopRecording();
      return;
    }
    setError("speech-error", "");
    const items = state.session.speech_items || [];
    const item = items[state.speechIndex];
    const started = await startRecording(async (blob) => {
      await submitSpeech(item.id, blob);
    });
    if (started) {
      $("btn-record-speech").textContent = "⏹ 録音終了";
      $("speech-rec-indicator").classList.remove("hidden");
      $("speech-rec-indicator").classList.add("flex");
      startSpeechTimer();
    }
  });

  async function submitSpeech(itemId, blob) {
    $("speech-rec-indicator").classList.add("hidden");
    try {
      const formData = new FormData();
      formData.append("session_id", state.sessionId);
      formData.append("item_id", itemId);
      formData.append("audio", blob, "speech.webm");
      const data = await fetchJson(`${API}/speech/evaluate`, { method: "POST", body: formData });
      state.session = data.session;
      const evalResult = data.speech_item.evaluation;
      $("speech-sentence-mastery").textContent = evalResult.scores.sentence_mastery;
      $("speech-vocabulary").textContent = evalResult.scores.vocabulary;
      $("speech-fluency").textContent = evalResult.scores.fluency;
      $("speech-coherence").textContent = evalResult.scores.coherence;
      $("speech-feedback").textContent = evalResult.feedback_text;
      $("speech-result").classList.remove("hidden");
      $("btn-record-speech").classList.add("hidden");
      $("speech-status").textContent = "";
      $("btn-speech-next").dataset.allAnswered = data.all_answered ? "1" : "0";
    } catch (exc) {
      setError("speech-error", exc.message);
      $("speech-status").textContent = "";
      $("btn-record-speech").disabled = false;
      $("btn-record-speech").textContent = "🎙 録音開始";
    }
  }

  $("btn-speech-next").addEventListener("click", async () => {
    const items = state.session.speech_items || [];
    if (state.speechIndex < items.length - 1) {
      state.speechIndex += 1;
      renderSpeechItem();
    } else {
      await proceedToReport();
    }
  });

  // ── ステップ6: 総合評価レポート ──────────────────────────

  async function proceedToReport() {
    showScreen("report");
    setError("report-error", "");
    try {
      const data = await fetchJson(`${API}/report/final`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: state.sessionId }),
      });
      renderReport(data.final_evaluation);
    } catch (exc) {
      setError("report-error", exc.message);
      $("report-loading").textContent = "";
    }
  }

  const CATEGORY_LABELS = {
    sentence_mastery: "Sentence Mastery",
    vocabulary: "Vocabulary",
    fluency: "Fluency",
    pronunciation: "Pronunciation",
    comprehension: "Comprehension",
  };

  function renderReport(finalEval) {
    $("report-loading").classList.add("hidden");
    $("report-overall-score").textContent = `${finalEval.overall_score_90 ?? "-"} / 90`;
    $("report-cefr").textContent = finalEval.cefr_level ? `CEFR: ${finalEval.cefr_level}` : "";

    const categoriesBox = $("report-categories");
    categoriesBox.innerHTML = "";
    Object.entries(finalEval.versant_scores_90 || {}).forEach(([key, value]) => {
      const div = document.createElement("div");
      div.className = "glass-inset rounded-xl p-3";
      div.innerHTML = `<p class="text-xs text-slate-500">${CATEGORY_LABELS[key] || key}</p>
        <p class="text-lg font-bold accent-strong">${value ?? "-"} <span class="text-xs font-normal text-slate-400">/ 90</span></p>`;
      categoriesBox.appendChild(div);
    });

    $("report-summary").textContent = finalEval.summary_text || "";

    const strengthsBox = $("report-strengths");
    strengthsBox.innerHTML = "";
    (finalEval.strengths || []).forEach((s) => {
      const li = document.createElement("li");
      li.textContent = s;
      strengthsBox.appendChild(li);
    });

    const improvementsBox = $("report-improvements");
    improvementsBox.innerHTML = "";
    (finalEval.improvements || []).forEach((s) => {
      const li = document.createElement("li");
      li.textContent = s;
      improvementsBox.appendChild(li);
    });

    $("report-body").classList.remove("hidden");
  }

  // ── 初期化 ────────────────────────────────────────────────

  async function init() {
    showScreen("login");
    await loadThemesAndRoster();

    if (window.TRIGGER_INITIAL_SESSION_ID) {
      try {
        const data = await fetchJson(`${API}/sessions/${window.TRIGGER_INITIAL_SESSION_ID}`);
        state.sessionId = window.TRIGGER_INITIAL_SESSION_ID;
        state.session = data.session;
        resumeFromSession();
      } catch (_) {
        /* セッションが見つからない場合はログイン画面のまま */
      }
    }
  }

  function resumeFromSession() {
    const session = state.session;
    const script = session.script || {};
    if (script.output_text) {
      $("script-output").value = script.output_text;
      $("sample-script-text").textContent = script.output_text;
      $("readaloud-script-text").textContent = script.output_text;
    }
    if (session.pronunciation_result) {
      const result = session.pronunciation_result;
      $("readaloud-accuracy").textContent = result.scores.accuracy;
      $("readaloud-fluency").textContent = result.scores.fluency;
      $("readaloud-feedback").textContent = result.feedback_text;
      $("readaloud-result").classList.remove("hidden");
    }
    if (session.sample_audio_url) {
      $("sample-audio").src = session.sample_audio_url;
    }

    if (session.status === "done") {
      showScreen("report");
      if (session.final_evaluation) renderReport(session.final_evaluation);
      return;
    }
    if (session.status === "report") {
      proceedToReport();
      return;
    }
    if (session.status === "speech") {
      state.speechIndex = (session.speech_items || []).findIndex((s) => !s.evaluation);
      if (state.speechIndex === -1) state.speechIndex = 0;
      if ((session.speech_items || []).length === 0) {
        proceedToSpeech();
      } else {
        showScreen("speech");
        renderSpeechItem();
      }
      return;
    }
    if (session.status === "qa") {
      state.qaIndex = (session.qa_items || []).findIndex((q) => !q.evaluation);
      if (state.qaIndex === -1) state.qaIndex = 0;
      if ((session.qa_items || []).length === 0) {
        showScreen("readaloud");
      } else {
        showScreen("qa");
        renderQaItem();
      }
      return;
    }
    if (session.status === "readaloud") {
      showScreen("readaloud");
      return;
    }
    if (session.status === "sample") {
      showScreen("sample");
      return;
    }
    showScreen("script");
  }

  init();
})();
