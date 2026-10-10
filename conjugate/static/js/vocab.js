(() => {
  const SESSION_ID = window.CONJUGATE_VOCAB_SESSION_ID;
  const progressLabel = document.getElementById("progress-label");
  const errorBanner = document.getElementById("vocab-error-banner");
  const directionPill = document.getElementById("direction-pill");
  const promptKicker = document.getElementById("prompt-kicker");
  const promptWord = document.getElementById("prompt-word");
  const choiceList = document.getElementById("choice-list");
  const feedbackBox = document.getElementById("feedback-box");
  const nextBtn = document.getElementById("next-btn");

  const DIRECTION_COPY = {
    ja_to_es: { kicker: "この日本語の意味の動詞は？", pill: "日本語 → スペイン語" },
    es_to_ja: { kicker: "このスペイン語の意味は？", pill: "スペイン語 → 日本語" },
  };

  let session = null;
  let questionIndex = 0;
  let answering = false;

  function setError(message) {
    if (!message) {
      errorBanner.classList.add("hidden");
      errorBanner.textContent = "";
      return;
    }
    errorBanner.textContent = message;
    errorBanner.classList.remove("hidden");
  }

  async function loadSession() {
    const res = await fetch(`/conjugate/api/vocab/${SESSION_ID}`);
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || "セッションの取得に失敗しました。");
    session = data.session;
  }

  function currentQuestion() {
    return session.questions[questionIndex];
  }

  function isLastQuestion() {
    return questionIndex >= session.questions.length - 1;
  }

  function updateProgress() {
    progressLabel.textContent = `${questionIndex + 1}/${session.questions.length}問`;
  }

  function renderQuestion() {
    const q = currentQuestion();
    const copy = DIRECTION_COPY[q.direction] || DIRECTION_COPY.ja_to_es;
    answering = false;
    feedbackBox.classList.add("hidden");
    feedbackBox.innerHTML = "";
    nextBtn.classList.add("hidden");
    directionPill.textContent = copy.pill;
    promptKicker.textContent = q.prompt_kicker || copy.kicker;
    promptWord.textContent = q.prompt;
    updateProgress();

    choiceList.innerHTML = "";
    q.choices.forEach((choice) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "vsc-choice-btn";
      btn.dataset.choiceId = choice.id;
      btn.textContent = choice.label;
      btn.addEventListener("click", () => handleChoice(choice.id));
      choiceList.appendChild(btn);
    });

    if (q.answer) {
      applyResult(q.answer, q.answer.choice_id);
    }
  }

  function applyResult(result, selectedId) {
    const buttons = Array.from(choiceList.querySelectorAll(".vsc-choice-btn"));
    buttons.forEach((btn) => {
      btn.disabled = true;
      if (btn.dataset.choiceId === result.correct_choice_id) {
        btn.classList.add("is-correct");
      } else if (btn.dataset.choiceId === selectedId && !result.correct) {
        btn.classList.add("is-wrong");
      }
    });
    feedbackBox.className = `mt-4 vsc-feedback ${result.correct ? "vsc-feedback-correct" : "vsc-feedback-bad"}`;
    const guardianBonus = Number((result.progress || {}).guardian_bonus_awarded || 0) > 0;
    feedbackBox.innerHTML = `<div class="font-bold">${result.message}</div>${
      result.newly_mastered ? '<div class="vsc-mastered-toast">暗記マスターしました！</div>' : ""
    }${guardianBonus ? '<div class="vsc-mastered-toast vsc-guardian-bonus-toast">🛡️ 暗記マスター5個達成でGuardiánを1体獲得！</div>' : ""}`;
    feedbackBox.classList.remove("hidden");
    nextBtn.classList.remove("hidden");
    nextBtn.textContent = isLastQuestion() ? "結果を見る →" : "次の問題へ →";
    if (window.vscCelebrateFromResult) window.vscCelebrateFromResult(result);
  }

  async function handleChoice(choiceId) {
    if (answering) return;
    answering = true;
    setError("");
    try {
      const q = currentQuestion();
      const res = await fetch(`/conjugate/api/vocab/${SESSION_ID}/questions/${q.question_id}/answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ choice_id: choiceId }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || "採点に失敗しました。");
      q.answer = data.result;
      applyResult(data.result, choiceId);
    } catch (err) {
      answering = false;
      setError(err.message);
    }
  }

  async function handleNext() {
    if (!isLastQuestion()) {
      questionIndex += 1;
      renderQuestion();
      return;
    }
    nextBtn.disabled = true;
    nextBtn.textContent = "集計中...";
    try {
      await fetch(`/conjugate/api/vocab/${SESSION_ID}/finish`, { method: "POST" });
    } catch (_) {
      // サマリ画面側で再計算される
    }
    if (window.vscNavigate) window.vscNavigate(`/conjugate/vocab/${SESSION_ID}/summary`);
    else window.location.href = `/conjugate/vocab/${SESSION_ID}/summary`;
  }

  nextBtn.addEventListener("click", handleNext);

  (async () => {
    try {
      await loadSession();
      if (!session.questions.length) throw new Error("出題できる問題がありません。");
      if (session.status === "done") {
        if (window.vscNavigate) window.vscNavigate(`/conjugate/vocab/${SESSION_ID}/summary`);
    else window.location.href = `/conjugate/vocab/${SESSION_ID}/summary`;
        return;
      }
      const firstUnanswered = session.questions.findIndex((q) => !q.answer);
      questionIndex = firstUnanswered === -1 ? 0 : firstUnanswered;
      renderQuestion();
    } catch (err) {
      setError(err.message);
    }
  })();
})();
