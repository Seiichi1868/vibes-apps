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

  function renderQuestion(kind, heading) {
    const list = visible(lesson[kind]);
    const steps = pieces(list);
    const step = reveal[kind] || 0;
    if (!list.length) {
      stage.innerHTML = `<div class="tb-screen-copy"><h2>${heading}</h2><p class="tb-wait">まだありません。</p></div>`;
      statusEl.textContent = "";
      return;
    }
    if (step <= 0) {
      stage.innerHTML = `<div class="tb-screen-copy"><h2>${heading}</h2><p class="tb-wait">クリックまたは ↓ で質問を表示します。</p></div>`;
    } else {
      const piece = steps[Math.min(step, steps.length) - 1];
      const item = list[piece.index];
      const answer = piece.kind === "answer"
        ? `<p class="tb-a"><span>A. </span>${esc(item.answer || item.a || "")}</p>`
        : "";
      stage.innerHTML = `<div class="tb-screen-copy"><h2>${heading}</h2><p class="tb-q">Q${piece.index + 1}. ${esc(item.text || item.q)}</p>${answer}</div>`;
    }
    statusEl.textContent = `${Math.min(step, steps.length)} / ${steps.length}　↑ で戻る`;
  }

  function renderWriting() {
    const list = visible(lesson.writing);
    const step = reveal.writing || 0;
    if (!list.length) {
      stage.innerHTML = "<div class='tb-screen-copy'><h2>書く</h2><p class='tb-wait'>まだありません。</p></div>";
      statusEl.textContent = "";
      return;
    }
    if (step <= 0) {
      stage.innerHTML = "<div class='tb-screen-copy'><h2>書く</h2><p class='tb-wait'>クリックまたは ↓ で話題を表示します。</p><p>O Opinion → R Reason → E Example → O Opinion</p></div>";
    } else {
      const topic = list[Math.min(step, list.length) - 1];
      const choices = (topic.options || []).length === 2
        ? `<p>${esc(topic.options[0])} or ${esc(topic.options[1])}</p>`
        : "<p>Your answer + Why?</p>";
      stage.innerHTML = `<div class="tb-screen-copy"><h2>書く</h2><p class="tb-q">T${Math.min(step, list.length)}. ${esc(topic.text)}</p>${choices}${topic.text_ja ? `<p>${esc(topic.text_ja)}</p>` : ""}<p>O Opinion → R Reason → E Example → O Opinion</p></div>`;
    }
    statusEl.textContent = `${Math.min(step, list.length)} / ${list.length}　↑ で戻る`;
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
        ? `<iframe title="CNN10" src="https://www.youtube.com/embed/${id}?${params}" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>`
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
    if (view === "warmup") return renderQuestion("warmup", "ウォームアップ");
    if (view === "discussion") return renderQuestion("discussion", "ディスカッション");
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
