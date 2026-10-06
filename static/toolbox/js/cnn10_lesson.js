(function () {
  const panel = document.getElementById("cnn10-panel");
  const list = document.getElementById("cnn10-list");
  const message = document.getElementById("cnn10-message");
  const moreBtn = document.getElementById("cnn10-more-btn");
  const statusEl = document.getElementById("lesson-status");
  const assistStatus = document.getElementById("assist-status");
  const preview = document.getElementById("assist-preview");
  let offset = 0;
  let hasMore = false;
  let loading = false;

  function parseTime(text) {
    const raw = String(text || "").trim();
    if (!raw) return null;
    if (/^\d+$/.test(raw)) return parseInt(raw, 10);
    const parts = raw.split(":").map((part) => parseInt(part, 10));
    if (parts.some((value) => !Number.isFinite(value))) return null;
    if (parts.length === 2) return parts[0] * 60 + parts[1];
    if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
    return null;
  }

  function formatTime(sec) {
    const total = Math.max(0, Math.floor(Number(sec) || 0));
    const m = Math.floor(total / 60);
    const s = total % 60;
    return `${m}:${String(s).padStart(2, "0")}`;
  }

  function lessonPayload() {
    return {
      title: document.getElementById("lesson-title").value.trim(),
      url: document.getElementById("youtube-url").value.trim(),
      start: document.getElementById("start-time").value.trim(),
      end: document.getElementById("end-time").value.trim(),
      script: document.getElementById("lesson-script").value.trim(),
    };
  }

  async function saveLesson(extra) {
    const res = await fetch("/toolbox/api/cnn10/lesson", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...lessonPayload(), ...(extra || {}) }),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "保存に失敗しました。");
    return data.lesson;
  }

  function renderAssist(lesson) {
    const bits = [];
    if (lesson.translation) bits.push(`<h3>和訳</h3><p>${escapeHtml(lesson.translation)}</p>`);
    if ((lesson.vocabulary || []).length) {
      bits.push("<h3>語彙</h3><ul>" + lesson.vocabulary.map((item) =>
        `<li><strong>${escapeHtml(item.word)}</strong> ${escapeHtml(item.pos || "")} ${escapeHtml(item.cefr || "")} — ${escapeHtml(item.meaning || "")}</li>`
      ).join("") + "</ul>");
    }
    ["warmup", "discussion"].forEach((key) => {
      const label = key === "warmup" ? "ウォームアップ" : "ディスカッション";
      if (!(lesson[key] || []).length) return;
      bits.push(`<h3>${label}</h3><ol>` + lesson[key].map((item) =>
        `<li>${escapeHtml(item.q)}<br><span class="tb-muted">${escapeHtml(item.a || "")}</span></li>`
      ).join("") + "</ol>");
    });
    preview.innerHTML = bits.join("");
  }

  function escapeHtml(value) {
    return String(value || "").replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[ch]));
  }

  async function fetchScript() {
    const url = document.getElementById("youtube-url").value.trim();
    const start = parseTime(document.getElementById("start-time").value);
    const end = parseTime(document.getElementById("end-time").value);
    if (!window.YoutubeTranscript) throw new Error("字幕モジュールが読み込まれていません。");
    statusEl.textContent = "文字起こしを取得中…";
    const data = await window.YoutubeTranscript.fetchTranscript(url, {
      languages: ["en", "ja"],
      startSec: start,
      endSec: end,
    });
    const text = String(data.script || "").trim();
    if (!text) throw new Error("この範囲の字幕がありません。開始・終了を確認してください。");
    document.getElementById("lesson-script").value = text;
    if (data.language) statusEl.textContent = `取得しました（${data.language}）。`;
    else statusEl.textContent = "取得しました。";
    await saveLesson();
  }

  document.getElementById("fetch-script-btn").addEventListener("click", () => {
    fetchScript().catch((err) => {
      statusEl.textContent = err.message || "取得に失敗しました。";
    });
  });

  document.getElementById("cnn10-form").addEventListener("submit", (ev) => {
    ev.preventDefault();
    saveLesson().then(() => {
      statusEl.textContent = "保存しました。";
    }).catch((err) => {
      statusEl.textContent = err.message;
    });
  });

  document.querySelectorAll("[data-assist]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const script = document.getElementById("lesson-script").value.trim();
      assistStatus.textContent = "作成中…";
      try {
        await saveLesson();
        const res = await fetch("/toolbox/api/cnn10/assist", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            kind: btn.dataset.assist,
            script,
            min_cefr: document.getElementById("vocab-min").value,
          }),
        });
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || "作成に失敗しました。");
        renderAssist(data.lesson);
        assistStatus.textContent = "教室スクリーンに反映しました。";
      } catch (err) {
        assistStatus.textContent = err.message;
      }
    });
  });

  function addEpisode(episode) {
    const li = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "tb-btn";
    button.textContent = episode.title || episode.video_id;
    button.addEventListener("click", () => {
      document.getElementById("lesson-title").value = episode.title || "";
      document.getElementById("youtube-url").value = episode.url || `https://www.youtube.com/watch?v=${episode.video_id}`;
      document.getElementById("start-time").value = "0:00";
      document.getElementById("end-time").value = "";
      document.getElementById("lesson-script").value = "";
      panel.hidden = true;
      statusEl.textContent = "動画を入れました。範囲を入れて文字起こしを取得してください。終了が空なら字幕の最後まで取ります。";
      if (episode.duration_sec) {
        document.getElementById("end-time").placeholder = formatTime(episode.duration_sec);
      }
    });
    li.appendChild(button);
    list.appendChild(li);
  }

  async function loadEpisodes(reset) {
    if (loading) return;
    loading = true;
    if (reset) {
      offset = 0;
      list.innerHTML = "";
    }
    moreBtn.disabled = true;
    try {
      const res = await fetch(`/toolbox/api/cnn10/episodes?offset=${offset}&limit=10`);
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || "一覧の取得に失敗しました。");
      (data.episodes || []).forEach(addEpisode);
      offset = data.next_offset || offset;
      hasMore = Boolean(data.has_more);
      moreBtn.hidden = !hasMore;
      message.hidden = true;
    } catch (err) {
      message.hidden = false;
      message.textContent = err.message;
    } finally {
      loading = false;
      moreBtn.disabled = false;
    }
  }

  document.getElementById("cnn10-open-btn").addEventListener("click", () => {
    panel.hidden = false;
    if (!list.children.length) loadEpisodes(true);
  });
  document.getElementById("cnn10-close-btn").addEventListener("click", () => {
    panel.hidden = true;
  });
  moreBtn.addEventListener("click", () => loadEpisodes(false));

  fetch("/toolbox/api/cnn10/lesson").then((res) => res.json()).then((data) => {
    if (data.ok) renderAssist(data.lesson);
  }).catch(() => {});
})();
