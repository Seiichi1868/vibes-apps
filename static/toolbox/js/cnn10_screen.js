(function () {
  const titleEl = document.getElementById("screen-title");
  const videoEl = document.getElementById("screen-video");
  const bodyEl = document.getElementById("screen-body");
  const statusEl = document.getElementById("screen-status");
  let steps = [];
  let index = 0;

  function escapeHtml(value) {
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

  function show() {
    const step = steps[index];
    if (!step) {
      bodyEl.innerHTML = "<p>表示するものがありません。</p>";
      return;
    }
    statusEl.textContent = `${index + 1} / ${steps.length}　${step.label}`;
    bodyEl.innerHTML = step.html;
  }

  function build(lesson) {
    const videoId = (lesson.url || "").match(/([a-zA-Z0-9_-]{11})(?=$|[^a-zA-Z0-9_-])/);
    const id = lesson.video_id || (videoId ? videoId[1] : "");
    const start = parseTime(lesson.start);
    titleEl.textContent = lesson.title || "CNN10";
    if (id) {
      videoEl.innerHTML = `<iframe title="CNN10" width="100%" height="360" src="https://www.youtube.com/embed/${id}?start=${start}" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>`;
    }
    steps = [];
    (lesson.warmup || []).forEach((item, i) => {
      steps.push({
        label: "ウォームアップ",
        html: `<h2>ウォームアップ ${i + 1}</h2><p>${escapeHtml(item.q)}</p><p class="tb-muted">${escapeHtml(item.a || "")}</p>`,
      });
    });
    if ((lesson.vocabulary || []).length) {
      steps.push({
        label: "語彙",
        html: "<h2>語彙</h2><ul>" + lesson.vocabulary.map((item) =>
          `<li><strong>${escapeHtml(item.word)}</strong> ${escapeHtml(item.meaning || "")}</li>`
        ).join("") + "</ul>",
      });
    }
    if (lesson.script) {
      steps.push({ label: "文字起こし", html: `<h2>文字起こし</h2><p>${escapeHtml(lesson.script)}</p>` });
    }
    if (lesson.translation) {
      steps.push({ label: "和訳", html: `<h2>和訳</h2><p>${escapeHtml(lesson.translation)}</p>` });
    }
    (lesson.discussion || []).forEach((item, i) => {
      steps.push({
        label: "ディスカッション",
        html: `<h2>ディスカッション ${i + 1}</h2><p>${escapeHtml(item.q)}</p><p class="tb-muted">${escapeHtml(item.a || "")}</p>`,
      });
    });
    index = 0;
    show();
  }

  function move(delta) {
    index = Math.min(steps.length - 1, Math.max(0, index + delta));
    show();
  }

  document.addEventListener("keydown", (ev) => {
    if (ev.key === "ArrowDown" || ev.key === "ArrowRight") move(1);
    if (ev.key === "ArrowUp" || ev.key === "ArrowLeft") move(-1);
  });
  document.getElementById("cnn10-screen").addEventListener("click", () => move(1));

  fetch("/toolbox/api/cnn10/lesson")
    .then((res) => res.json())
    .then((data) => {
      if (!data.ok) throw new Error(data.error || "読み込めません。");
      build(data.lesson);
    })
    .catch((err) => {
      statusEl.textContent = err.message;
    });
})();
