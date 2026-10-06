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

  function qaShell(label, top, bottom) {
    return `<div class="tb-qa"><p class="tb-qa-label">${esc(label)}</p><div class="tb-qa-top">${top}</div><div class="tb-qa-bottom">${bottom}</div></div>`;
  }

  function renderQuestion(kind, label) {
    const list = visible(lesson[kind]);
    const steps = pieces(list);
    const step = reveal[kind] || 0;
    if (!list.length) {
      stage.innerHTML = qaShell(label, `<p class="tb-qa-hint">No questions yet.</p>`, "");
      statusEl.textContent = "";
      return;
    }
    if (step <= 0) {
      stage.innerHTML = qaShell(label, `<p class="tb-qa-hint">Click or press down.</p>`, "");
      statusEl.textContent = `0 / ${steps.length}`;
      return;
    }
    const piece = steps[Math.min(step, steps.length) - 1];
    const item = list[piece.index];
    const question = `<p class="tb-qa-text">Q${piece.index + 1}. ${esc(item.text || item.q)}</p>`;
    const answer = piece.kind === "answer"
      ? `<p class="tb-qa-text">A. ${esc(item.answer || item.a || "")}</p>`
      : "";
    stage.innerHTML = qaShell(label, question, answer);
    statusEl.textContent = `${Math.min(step, steps.length)} / ${steps.length}`;
  }

  function renderWriting() {
    const list = visible(lesson.writing);
    const step = reveal.writing || 0;
    if (!list.length) {
      stage.innerHTML = qaShell("Writing", `<p class="tb-qa-hint">No topics yet.</p>`, "");
      statusEl.textContent = "";
      return;
    }
    if (step <= 0) {
      stage.innerHTML = qaShell("Writing", `<p class="tb-qa-hint">Click or press down.</p>`, "");
      statusEl.textContent = `0 / ${list.length}`;
      return;
    }
    const topic = list[Math.min(step, list.length) - 1];
    const question = `<p class="tb-qa-text">${esc(topic.text)}</p>`;
    const lines = [];
    if ((topic.options || []).length === 2) {
      lines.push(`${esc(topic.options[0])} or ${esc(topic.options[1])}`);
    }
    if (topic.text_ja) lines.push(esc(topic.text_ja));
    const below = lines.length ? `<p class="tb-qa-text">${lines.join("<br>")}</p>` : "";
    stage.innerHTML = qaShell("Writing", question, below);
    statusEl.textContent = `${Math.min(step, list.length)} / ${list.length}`;
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
    if (view === "warmup") return renderQuestion("warmup", "Warm-up");
    if (view === "discussion") return renderQuestion("discussion", "Discussion");
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
