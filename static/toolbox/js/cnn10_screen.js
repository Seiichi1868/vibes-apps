(function () {
  const root = document.getElementById("cnn10-screen");
  const stage = document.getElementById("screen-stage");
  const statusEl = document.getElementById("screen-status");
  const archiveId = root.dataset.archive || "";
  let lesson = null;
  let view = "video";
  const reveal = { warmup: 0, discussion: 0, writing: 0 };

  function esc(value) {
    return String(value || "").replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[ch]));
  }

  function parseTime(text) {
    const raw = String(text || "").trim();
    if (!raw) return 0;
    if (/^\d+$/.test(raw)) return parseInt(raw, 10);
    const parts = raw.split(":").map((part) => parseInt(part, 10));
    if (parts.some((value) => !Number.isFinite(value))) return 0;
    if (parts.length === 2) return parts[0] * 60 + parts[1];
    if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
    return 0;
  }

  function videoId() {
    if (lesson.video_id && /^[a-zA-Z0-9_-]{11}$/.test(lesson.video_id)) return lesson.video_id;
    const match = String(lesson.url || "").match(/([a-zA-Z0-9_-]{11})(?![a-zA-Z0-9_-])/);
    return match ? match[1] : "";
  }

  function visible(list) {
    return (list || []).filter((item) => item && item.selected !== false);
  }

  function pieces(list) {
    const out = [];
    (list || []).forEach((item, index) => {
      if (!(item.text || item.q)) return;
      out.push({ index, kind: "question" });
      if (item.answer || item.a) out.push({ index, kind: "answer" });
    });
    return out;
  }

  function questionFontSize() {
    return "clamp(2.15rem, 6.8vmin, 5.6rem)";
  }

  function qaFrame(heading, body, hint, size) {
    const fontSize = size || questionFontSize();
    const head = heading ? `<p class="screen-warmup-heading">${esc(heading)}</p>` : "";
    return `<div class="screen-view--warmup"><div class="screen-warmup-inner" style="--warmup-q-size:${fontSize}">${head}${body}<p class="screen-postview-hint">${esc(hint)}</p></div></div>`;
  }

  function renderQuestion(kind, heading) {
    const list = visible(lesson[kind]);
    const steps = pieces(list);
    const step = reveal[kind] || 0;
    if (!list.length) {
      stage.innerHTML = qaFrame(heading, `<p class="screen-qa-waiting">No questions yet.</p>`, "");
      statusEl.textContent = "";
      return;
    }
    const hint = `Down for next, up to go back (${Math.min(step, steps.length)}/${steps.length})`;
    if (step <= 0) {
      stage.innerHTML = qaFrame(heading, `<p class="screen-qa-waiting">Click or press down to show a question</p>`, hint);
      statusEl.textContent = "";
      return;
    }
    const piece = steps[Math.min(step, steps.length) - 1];
    const item = list[piece.index];
    let body = `<div class="screen-qa-current"><div class="screen-warmup-q"><span class="screen-warmup-num">Q${piece.index + 1}.</span><span class="screen-warmup-text">${esc(item.text || item.q)}</span></div>`;
    if (piece.kind === "answer") {
      body += `<p class="screen-postview-answer"><span class="screen-postview-answer-label">A.</span>${esc(item.answer || item.a || "")}</p>`;
    }
    body += "</div>";
    stage.innerHTML = qaFrame(heading, body, hint);
    statusEl.textContent = "";
  }

  function renderWriting() {
    const list = visible(lesson.writing);
    const step = reveal.writing || 0;
    const size = "clamp(2rem, 6.4vmin, 5.25rem)";
    if (!list.length) {
      stage.innerHTML = qaFrame("", `<p class="screen-qa-waiting">No topics yet.</p>`, "", size);
      statusEl.textContent = "";
      return;
    }
    const hint = `Down for next, up to go back (${Math.min(step, list.length)}/${list.length})`;
    if (step <= 0) {
      stage.innerHTML = qaFrame("", `<p class="screen-qa-waiting">Click or press down to show a topic</p>`, hint, size);
      statusEl.textContent = "";
      return;
    }
    const index = Math.min(step, list.length) - 1;
    const topic = list[index];
    let body = `<div class="screen-qa-current"><div class="screen-writing-item"><div class="screen-warmup-q"><span class="screen-warmup-num">T${index + 1}.</span><span class="screen-warmup-text">${esc(topic.text)}</span></div>`;
    if ((topic.options || []).length === 2) {
      body += `<div class="screen-writing-choices"><span class="screen-writing-choice">${esc(topic.options[0])}</span><span class="screen-writing-or">or</span><span class="screen-writing-choice">${esc(topic.options[1])}</span></div>`;
    }
    if (topic.text_ja) body += `<p class="screen-writing-ja">${esc(topic.text_ja)}</p>`;
    body += "</div></div>";
    stage.innerHTML = qaFrame("", body, hint, size);
    statusEl.textContent = "";
  }

  function render() {
    root.classList.toggle("is-video", view === "video");
    document.querySelectorAll("[data-view]").forEach((btn) => {
      btn.classList.toggle("is-on", btn.dataset.view === view);
    });
    if (view === "video") {
      const id = videoId();
      const start = parseTime(lesson.start);
      const end = parseTime(lesson.end);
      const params = new URLSearchParams({
        start: String(start),
        rel: "0",
        modestbranding: "1",
        hl: "en",
        cc_lang_pref: "en",
      });
      if (end > start) params.set("end", String(end));
      if (lesson.subtitles !== false) params.set("cc_load_policy", "1");
      stage.innerHTML = id
        ? `<iframe title="News Talk" src="https://www.youtube.com/embed/${id}?${params}" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>`
        : "<p class='tb-screen-copy'>動画 URL がありません。</p>";
      statusEl.textContent = "";
      return;
    }
    if (view === "vocab") {
      const items = visible(lesson.vocabulary);
      stage.innerHTML = "<div class='tb-screen-copy'>" + (items.length
        ? "<table class='tb-vocab'><thead><tr><th>単語・熟語</th><th>品詞</th><th>意味</th></tr></thead><tbody>"
          + items.map((item) => `<tr><td class="word">${esc(item.word)}</td><td>${esc(item.part_of_speech || item.pos || "")}</td><td>${esc(item.meaning || "")}</td></tr>`).join("")
          + "</tbody></table>"
        : "<p class='tb-wait'>まだありません。</p>") + "</div>";
      statusEl.textContent = "";
      return;
    }
    if (view === "warmup") return renderQuestion("warmup", "Think about this before watching");
    if (view === "discussion") return renderQuestion("discussion", "Talk about this after watching");
    if (view === "writing") return renderWriting();
  }

  function move(delta) {
    if (view === "warmup" || view === "discussion") {
      const max = pieces(visible(lesson[view])).length;
      reveal[view] = Math.min(max, Math.max(0, (reveal[view] || 0) + delta));
    } else if (view === "writing") {
      const max = visible(lesson.writing).length;
      reveal.writing = Math.min(max, Math.max(0, reveal.writing + delta));
    }
    render();
  }

  document.querySelectorAll("[data-view]").forEach((btn) => {
    btn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      view = btn.dataset.view;
      render();
    });
  });
  stage.addEventListener("click", () => move(1));
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "ArrowDown" || ev.key === "ArrowRight" || ev.key === "Enter" || ev.key === " ") {
      ev.preventDefault();
      move(1);
    }
    if (ev.key === "ArrowUp" || ev.key === "ArrowLeft") {
      ev.preventDefault();
      move(-1);
    }
  });

  const query = archiveId ? `?archive=${encodeURIComponent(archiveId)}` : "";
  fetch(`/toolbox/api/cnn10/lesson${query}`)
    .then((res) => res.json())
    .then((data) => {
      if (!data.ok) throw new Error(data.error || "読み込めません。");
      lesson = data.lesson;
      render();
    })
    .catch((err) => {
      statusEl.textContent = err.message;
    });
})();
