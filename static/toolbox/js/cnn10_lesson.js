(function () {
  const panel = document.getElementById("cnn10-panel");
  const list = document.getElementById("cnn10-list");
  const message = document.getElementById("cnn10-message");
  const moreBtn = document.getElementById("cnn10-more-btn");
  const statusEl = document.getElementById("lesson-status");
  const assistStatus = document.getElementById("assist-status");
  const previewHosts = {
    translation: document.getElementById("preview-translation"),
    vocabulary: document.getElementById("preview-vocab"),
    warmup: document.getElementById("preview-warmup"),
    discussion: document.getElementById("preview-discussion"),
    writing: document.getElementById("preview-writing"),
  };
  const archiveList = document.getElementById("archive-list");
  let offset = 0;
  let hasMore = false;
  let loading = false;
  let openRow = null;
  let currentLesson = {};

  function postJson(url, body) {
    return fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": window.TOOLBOX_CSRF || "",
      },
      body: JSON.stringify(body || {}),
    }).then((res) => res.json());
  }

  function esc(value) {
    return String(value || "").replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[ch]));
  }

  function formatTime(sec) {
    const total = Math.max(0, Math.floor(Number(sec) || 0));
    const m = Math.floor(total / 60);
    const s = total % 60;
    return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }

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

  function snippetDurationSec(snippets) {
    let max = 0;
    (snippets || []).forEach((snippet) => {
      max = Math.max(max, Math.ceil((Number(snippet.start) || 0) + (Number(snippet.duration) || 0)));
    });
    return Math.max(max, 1);
  }

  function lessonPayload() {
    return {
      lesson_name: document.getElementById("lesson-name").value.trim(),
      title: document.getElementById("lesson-title").value.trim(),
      url: document.getElementById("youtube-url").value.trim(),
      start: document.getElementById("start-time").value.trim(),
      end: document.getElementById("end-time").value.trim(),
      script: document.getElementById("lesson-script").value.trim(),
      subtitles: document.getElementById("subtitles-enabled").checked,
    };
  }

  async function saveLesson(extra) {
    const archiveName = document.getElementById("archive-title").value.trim();
    const body = { ...lessonPayload(), ...(extra || {}) };
    if (archiveName) body.title = body.title || archiveName;
    const data = await postJson("/toolbox/api/cnn10/lesson", body);
    if (!data.ok) throw new Error(data.error || "保存に失敗しました。");
    return data.lesson;
  }

  function renderAssist(lesson) {
    currentLesson = lesson || {};
    Object.values(previewHosts).forEach((host) => {
      if (host) host.innerHTML = "";
    });
    if (lesson.translation || (lesson.pairs || []).length) {
      const block = document.createElement("div");
      const pairs = (lesson.pairs || []).filter((row) => row && (row.en || row.ja));
      const rows = pairs.length
        ? pairs.map((row) => `<tr><td>${esc(row.en)}</td><td>${esc(row.ja)}</td></tr>`).join("")
        : String(lesson.translation).split(/\n+/).filter(Boolean).map((line) => `<tr><td></td><td>${esc(line)}</td></tr>`).join("");
      block.innerHTML = `<table class="tb-align"><thead><tr><th>英文</th><th>和訳</th></tr></thead><tbody>${rows}</tbody></table>`;
      previewHosts.translation.appendChild(block);
    }
    function bindCheck(box, item, label, items, heading, title, key) {
      box.addEventListener("change", () => {
        item.selected = box.checked;
        label.style.opacity = box.checked ? "" : "0.5";
        heading.textContent = `${title}（${items.filter((row) => row.selected !== false).length} / ${items.length}）`;
        saveLesson({ [key]: items }).catch((err) => {
          assistStatus.textContent = err.message;
        });
      });
    }

    function tableBlock(title, key, headers, cellsFor) {
      const items = lesson[key] || [];
      if (!items.length) return;
      const wrap = document.createElement("div");
      const heading = document.createElement("h3");
      heading.textContent = `${title}（${items.filter((item) => item.selected !== false).length} / ${items.length}）`;
      const table = document.createElement("table");
      table.className = "tb-align tb-align-check";
      table.innerHTML = `<thead><tr><th></th>${headers.map((name) => `<th>${esc(name)}</th>`).join("")}</tr></thead>`;
      const body = document.createElement("tbody");
      items.forEach((item) => {
        const row = document.createElement("tr");
        if (item.selected === false) row.style.opacity = "0.5";
        const checkCell = document.createElement("td");
        const box = document.createElement("input");
        box.type = "checkbox";
        box.checked = item.selected !== false;
        bindCheck(box, item, row, items, heading, title, key);
        checkCell.appendChild(box);
        row.appendChild(checkCell);
        cellsFor(item).forEach((value) => {
          const cell = document.createElement("td");
          cell.textContent = value || "";
          row.appendChild(cell);
        });
        body.appendChild(row);
      });
      table.appendChild(body);
      wrap.append(heading, table);
      previewHosts[key].appendChild(wrap);
    }

    function qaBlock(title, key) {
      const items = lesson[key] || [];
      if (!items.length) return;
      const wrap = document.createElement("div");
      const heading = document.createElement("h3");
      heading.textContent = `${title}（${items.filter((item) => item.selected !== false).length} / ${items.length}）`;
      const table = document.createElement("table");
      table.className = "tb-align tb-align-check";
      table.innerHTML = "<thead><tr><th></th><th>質問</th><th>答え</th></tr></thead>";
      const body = document.createElement("tbody");
      items.forEach((item) => {
        const row = document.createElement("tr");
        if (item.selected === false) row.style.opacity = "0.5";
        const checkCell = document.createElement("td");
        const box = document.createElement("input");
        box.type = "checkbox";
        box.checked = item.selected !== false;
        bindCheck(box, item, row, items, heading, title, key);
        checkCell.appendChild(box);
        const q = document.createElement("td");
        q.textContent = item.text || item.q || "";
        const a = document.createElement("td");
        a.textContent = item.answer || item.a || "";
        row.append(checkCell, q, a);
        body.appendChild(row);
      });
      table.appendChild(body);
      wrap.append(heading, table);
      previewHosts[key].appendChild(wrap);
    }
    tableBlock("語彙", "vocabulary", ["単語・熟語", "品詞", "CEFR", "意味"], (item) => [
      item.word,
      item.part_of_speech || item.pos || "",
      item.cefr || "",
      item.meaning || "",
    ]);
    qaBlock("Warm-up", "warmup");
    qaBlock("Discussion", "discussion");
    tableBlock("Writing", "writing", ["話題", "和訳", "選択肢"], (item) => [
      item.text,
      item.text_ja || "",
      (item.options || []).filter(Boolean).join(" / "),
    ]);
  }

  function renderArchives(rows) {
    archiveList.innerHTML = "";
    if (!rows.length) {
      archiveList.innerHTML = "<p class='tb-muted'>まだアーカイブはありません。</p>";
      return;
    }
    rows.forEach((row) => {
      const card = document.createElement("article");
      card.className = "tb-archive";
      if (row.thumbnail_url) {
        const img = document.createElement("img");
        img.className = "tb-archive-thumb";
        img.alt = "";
        img.src = row.thumbnail_url;
        card.appendChild(img);
      }
      const body = document.createElement("div");
      const marks = [
        row.has_vocab ? "語彙" : "",
        row.has_warmup ? "W" : "",
        row.has_discussion ? "D" : "",
        row.has_writing ? "書く" : "",
      ].filter(Boolean).join(" ");
      const title = document.createElement("p");
      title.innerHTML = `<strong>${esc(row.title)}</strong> <span class="tb-muted">${esc(row.archived_at)} ${esc(marks)}</span>`;
      const actions = document.createElement("div");
      actions.className = "tb-row-actions";
      const restore = document.createElement("button");
      restore.type = "button";
      restore.className = "tb-btn";
      restore.textContent = "授業に戻す";
      restore.addEventListener("click", () => restoreArchive(row.archive_id));
      const screen = document.createElement("a");
      screen.className = "tb-btn";
      screen.target = "_blank";
      screen.rel = "noopener";
      screen.href = `/toolbox/cnn10/screen?archive=${encodeURIComponent(row.archive_id)}`;
      screen.textContent = "画面";
      const scriptBtn = document.createElement("button");
      scriptBtn.type = "button";
      scriptBtn.className = "tb-btn";
      scriptBtn.textContent = "スクリプト";
      scriptBtn.addEventListener("click", () => {
        card.classList.toggle("is-open");
      });
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "tb-btn";
      remove.textContent = "削除";
      remove.addEventListener("click", () => deleteArchive(row.archive_id));
      actions.append(restore, screen, scriptBtn, remove);
      const script = document.createElement("pre");
      script.className = "tb-archive-script";
      script.textContent = row.script || "保存されたスクリプトはありません。";
      body.append(title, actions, script);
      card.appendChild(body);
      archiveList.appendChild(card);
    });
  }

  async function refreshArchives() {
    const res = await fetch("/toolbox/api/cnn10/archive");
    const data = await res.json();
    if (data.ok) renderArchives(data.archives || []);
  }

  async function restoreArchive(id) {
    const data = await postJson("/toolbox/api/cnn10/archive/restore", { archive_id: id });
    if (!data.ok) {
      statusEl.textContent = data.error || "戻せませんでした。";
      return;
    }
    applyLesson(data.lesson);
    statusEl.textContent = "アーカイブを授業設定に戻しました。";
  }

  async function deleteArchive(id) {
    if (!confirm("このアーカイブを削除しますか？")) return;
    const data = await postJson("/toolbox/api/cnn10/archive/delete", { archive_id: id });
    if (!data.ok) {
      statusEl.textContent = data.error || "削除できませんでした。";
      return;
    }
    renderArchives(data.archives || []);
  }

  function applyLesson(lesson) {
    document.getElementById("lesson-name").value = lesson.lesson_name || "";
    document.getElementById("lesson-title").value = lesson.title || "";
    document.getElementById("archive-title").value = lesson.title || "";
    document.getElementById("youtube-url").value = lesson.url || "";
    document.getElementById("start-time").value = lesson.start || "";
    document.getElementById("end-time").value = lesson.end || "";
    document.getElementById("lesson-script").value = lesson.script || "";
    document.getElementById("subtitles-enabled").checked = lesson.subtitles !== false;
    renderAssist(lesson);
  }

  async function fetchScriptRange(url, startSec, endSec) {
    const data = await window.YoutubeTranscript.fetchTranscript(url, {
      languages: ["en", "ja"],
      startSec,
      endSec,
    });
    return String(data.script || "").trim();
  }

  document.getElementById("fetch-script-btn").addEventListener("click", () => {
    const url = document.getElementById("youtube-url").value.trim();
    const start = parseTime(document.getElementById("start-time").value);
    const end = parseTime(document.getElementById("end-time").value);
    statusEl.textContent = "文字起こしを取得中…";
    fetchScriptRange(url, start, end).then(async (text) => {
      if (!text) throw new Error("この範囲の字幕がありません。");
      document.getElementById("lesson-script").value = text;
      await saveLesson();
      statusEl.textContent = "文字起こしを設定しました。";
    }).catch((err) => {
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

  document.getElementById("archive-btn").addEventListener("click", () => {
    const payload = lessonPayload();
    payload.title = document.getElementById("archive-title").value.trim() || payload.title;
    statusEl.textContent = "アーカイブしています…";
    postJson("/toolbox/api/cnn10/archive", {
      lesson: payload,
      title: payload.title,
      lesson_name: payload.lesson_name,
    }).then((data) => {
      if (!data.ok) throw new Error(data.error || "アーカイブに失敗しました。");
      renderArchives(data.archives || []);
      statusEl.textContent = "アーカイブしました。";
    }).catch((err) => {
      statusEl.textContent = err.message;
    });
  });

  document.getElementById("qa-compose").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const kind = document.getElementById("qa-add-kind").value;
    const text = document.getElementById("qa-add-text").value.trim();
    const answer = document.getElementById("qa-add-answer").value.trim();
    if (kind !== "warmup" && kind !== "discussion") return;
    if (!text) {
      assistStatus.textContent = "質問を入力してください。";
      return;
    }
    const items = Array.isArray(currentLesson[kind]) ? currentLesson[kind].slice() : [];
    items.push({ text, answer, selected: true });
    assistStatus.textContent = "追加しています…";
    saveLesson({ [kind]: items }).then((lesson) => {
      renderAssist(lesson);
      document.getElementById("qa-add-text").value = "";
      document.getElementById("qa-add-answer").value = "";
      assistStatus.textContent = "質問を追加しました。";
    }).catch((err) => {
      assistStatus.textContent = err.message;
    });
  });

  document.querySelectorAll("[data-assist]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      assistStatus.textContent = "作成中…";
      try {
        await saveLesson();
        const data = await postJson("/toolbox/api/cnn10/assist", {
          kind: btn.dataset.assist,
          script: document.getElementById("lesson-script").value.trim(),
          min_cefr: document.getElementById("vocab-min").value,
        });
        if (!data.ok) throw new Error(data.error || "作成に失敗しました。");
        renderAssist(data.lesson);
        assistStatus.textContent = "教室スクリーンに反映できる状態で保存しました。";
      } catch (err) {
        assistStatus.textContent = err.message;
      }
    });
  });

  function seekPreview(iframe, videoId, startSec, endSec) {
    const start = Math.max(0, parseInt(startSec, 10) || 0);
    const end = Math.max(start + 1, parseInt(endSec, 10) || start + 1);
    iframe.src = `https://www.youtube.com/embed/${encodeURIComponent(videoId)}?start=${start}&end=${end}&rel=0&modestbranding=1&hl=en&cc_lang_pref=en`;
  }

  function paintLines(container, snippets, highlight) {
    container.innerHTML = "";
    const startSec = highlight?.ok ? highlight.start_sec : null;
    const endSec = highlight?.ok ? highlight.end_sec : null;
    snippets.forEach((snippet) => {
      const line = document.createElement("div");
      const start = Number(snippet.start) || 0;
      const inRange = startSec !== null && endSec !== null && start >= startSec && start < endSec;
      line.className = inRange ? "tb-cnn10-line is-hit" : "tb-cnn10-line";
      line.textContent = `${formatTime(start)}  ${snippet.text || ""}`;
      container.appendChild(line);
    });
  }

  function renderSliders(banner, highlight, maxSec, handlers) {
    banner.hidden = false;
    banner.innerHTML = "";
    const heading = document.createElement("p");
    const story = String(highlight.story_title || "").trim();
    heading.textContent = highlight.from_ai
      ? `タイトル（${story || "この動画"}）に対応する区間（AI推定・スライダーで調整可）`
      : "再生区間（スライダーで調整可）";
    banner.appendChild(heading);
    if (highlight.note) {
      const note = document.createElement("p");
      note.textContent = highlight.note;
      banner.appendChild(note);
    } else if (highlight.error) {
      const note = document.createElement("p");
      note.textContent = `${highlight.error} 全区間から手動で調整できます。`;
      banner.appendChild(note);
    }
    const hint = document.createElement("p");
    hint.textContent = "調整した区間は「授業に設定」で開始・終了時間とスクリプトに反映されます。";
    banner.appendChild(hint);

    function row(label, value) {
      const wrap = document.createElement("div");
      const head = document.createElement("div");
      const name = document.createElement("span");
      name.textContent = label;
      const shown = document.createElement("span");
      shown.textContent = formatTime(value);
      head.append(name, shown);
      const input = document.createElement("input");
      input.type = "range";
      input.min = "0";
      input.max = String(maxSec);
      input.step = "1";
      input.value = String(value);
      wrap.append(head, input);
      return { wrap, input, shown };
    }

    const start = row("開始", highlight.start_sec);
    const end = row("終了", highlight.end_sec);
    banner.append(start.wrap, end.wrap);

    function emit(source) {
      let startSec = parseInt(start.input.value, 10) || 0;
      let endSec = parseInt(end.input.value, 10) || 0;
      if (endSec <= startSec) {
        if (source.startsWith("start")) endSec = Math.min(maxSec, startSec + 1);
        else startSec = Math.max(0, endSec - 1);
        start.input.value = String(startSec);
        end.input.value = String(endSec);
      }
      highlight.start_sec = startSec;
      highlight.end_sec = endSec;
      highlight.start_display = formatTime(startSec);
      highlight.end_display = formatTime(endSec);
      highlight.ok = true;
      start.shown.textContent = highlight.start_display;
      end.shown.textContent = highlight.end_display;
      if (source.endsWith("change")) handlers.onChange?.(highlight);
      else handlers.onInput?.(highlight);
    }
    start.input.addEventListener("input", () => emit("start"));
    end.input.addEventListener("input", () => emit("end"));
    start.input.addEventListener("change", () => emit("start-change"));
    end.input.addEventListener("change", () => emit("end-change"));
  }

  function createRow(episode) {
    const row = document.createElement("div");
    row.className = "tb-cnn10-row";
    const thumb = document.createElement("button");
    thumb.type = "button";
    thumb.className = "tb-cnn10-thumb";
    thumb.title = "プレビューを表示";
    const img = document.createElement("img");
    img.alt = "";
    img.src = episode.thumbnail_url || (episode.video_id ? `https://i.ytimg.com/vi/${episode.video_id}/mqdefault.jpg` : "");
    thumb.appendChild(img);
    const body = document.createElement("div");
    body.innerHTML = `<p class="tb-cnn10-meta">${esc(episode.published || "")}</p><p class="tb-cnn10-title">${esc(episode.title || "Untitled")}</p>`;
    const url = document.createElement("p");
    url.className = "tb-cnn10-url";
    const link = document.createElement("a");
    link.href = episode.url || "#";
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = episode.url || "";
    url.appendChild(link);
    const actions = document.createElement("div");
    actions.className = "tb-cnn10-actions";
    const selectBtn = document.createElement("button");
    selectBtn.type = "button";
    selectBtn.className = "tb-btn tb-btn-primary";
    selectBtn.textContent = "授業に設定";
    const open = document.createElement("a");
    open.href = episode.url || "#";
    open.target = "_blank";
    open.rel = "noopener";
    open.textContent = "YouTubeで開く";
    actions.append(selectBtn, open);
    body.append(url, actions);

    const previewPanel = document.createElement("div");
    previewPanel.className = "tb-cnn10-preview";
    const videoWrap = document.createElement("div");
    videoWrap.className = "tb-cnn10-video";
    const iframe = document.createElement("iframe");
    iframe.allow = "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture";
    iframe.allowFullscreen = true;
    iframe.src = episode.video_id
      ? `https://www.youtube.com/embed/${encodeURIComponent(episode.video_id)}?rel=0&modestbranding=1&hl=en&cc_lang_pref=en`
      : "";
    videoWrap.appendChild(iframe);
    const transcriptWrap = document.createElement("div");
    const meta = document.createElement("p");
    meta.className = "tb-cnn10-meta";
    const banner = document.createElement("div");
    banner.className = "tb-cnn10-banner";
    banner.hidden = true;
    const transcript = document.createElement("div");
    transcript.className = "tb-cnn10-script";
    transcriptWrap.append(meta, banner, transcript);
    previewPanel.append(videoWrap, transcriptWrap);
    row.append(thumb, body, previewPanel);

    let loaded = false;
    let busy = false;
    let highlight = null;
    let snippets = [];

    selectBtn.addEventListener("click", async () => {
      document.getElementById("lesson-title").value = episode.title || "";
      document.getElementById("archive-title").value = episode.title || "";
      document.getElementById("youtube-url").value = episode.url || "";
      if (highlight?.ok) {
        document.getElementById("start-time").value = highlight.start_display;
        document.getElementById("end-time").value = highlight.end_display;
      }
      statusEl.textContent = "授業設定に反映しています…";
      panel.hidden = true;
      try {
        const start = highlight?.ok ? highlight.start_sec : null;
        const end = highlight?.ok ? highlight.end_sec : null;
        const text = await fetchScriptRange(episode.url || episode.video_id, start, end);
        document.getElementById("lesson-script").value = text;
        await saveLesson({ video_id: episode.video_id || "" });
        statusEl.textContent = highlight?.ok
          ? "動画と調整した区間を授業設定に反映しました。"
          : "動画を授業設定に反映しました。開始・終了を入れると範囲の文字起こしを取得できます。";
      } catch (err) {
        statusEl.textContent = err.message || "反映に失敗しました。";
      }
    });

    async function loadTranscript() {
      if (loaded || busy) return;
      busy = true;
      transcript.textContent = "文字起こしを読み込み中…";
      try {
        const data = await window.YoutubeTranscript.fetchTranscript(episode.video_id, { languages: ["en", "ja"] });
        snippets = data.snippets || data.all_snippets || [];
        const maxSec = snippetDurationSec(data.all_snippets || snippets);
        let guessed = null;
        try {
          const payload = await postJson("/toolbox/api/cnn10/highlight", {
            title: episode.title || "",
            snippets: data.all_snippets || snippets,
          });
          if (!payload.ok) throw new Error(payload.error || "区間推定に失敗しました。");
          guessed = payload.highlight;
        } catch (err) {
          guessed = { ok: false, error: err.message || "区間推定に失敗しました。" };
        }
        highlight = {
          ok: true,
          start_sec: guessed?.ok ? guessed.start_sec : 0,
          end_sec: guessed?.ok ? guessed.end_sec : maxSec,
          start_display: guessed?.ok ? guessed.start_display : formatTime(0),
          end_display: guessed?.ok ? guessed.end_display : formatTime(maxSec),
          from_ai: Boolean(guessed?.ok),
          note: guessed?.note || "",
          error: guessed?.ok ? "" : (guessed?.error || ""),
          confidence: guessed?.confidence || "",
          story_title: episode.title || "",
        };
        if (highlight.end_sec <= highlight.start_sec) highlight.end_sec = Math.min(maxSec, highlight.start_sec + 1);
        renderSliders(banner, highlight, maxSec, {
          onInput: (updated) => paintLines(transcript, snippets, updated),
          onChange: (updated) => {
            paintLines(transcript, snippets, updated);
            seekPreview(iframe, episode.video_id, updated.start_sec, updated.end_sec);
          },
        });
        paintLines(transcript, snippets, highlight);
        seekPreview(iframe, episode.video_id, highlight.start_sec, highlight.end_sec);
        meta.textContent = `${data.language || "English"}${highlight.from_ai ? ` · AI推定 ${highlight.start_display}–${highlight.end_display}` : ""}`;
        loaded = true;
      } catch (err) {
        transcript.textContent = err.message || "文字起こしの取得に失敗しました。";
        const retry = document.createElement("button");
        retry.type = "button";
        retry.className = "tb-btn";
        retry.textContent = "文字起こしを再試行";
        retry.addEventListener("click", () => {
          loaded = false;
          loadTranscript();
        });
        transcript.appendChild(retry);
      } finally {
        busy = false;
      }
    }

    thumb.addEventListener("click", () => {
      if (openRow && openRow !== row) {
        openRow.classList.remove("is-open");
        openRow.querySelector(".tb-cnn10-thumb")?.classList.remove("is-open");
      }
      const opening = !row.classList.contains("is-open");
      row.classList.toggle("is-open", opening);
      thumb.classList.toggle("is-open", opening);
      openRow = opening ? row : null;
      if (opening) loadTranscript();
    });

    return row;
  }

  async function loadEpisodes(reset) {
    if (loading) return;
    loading = true;
    moreBtn.disabled = true;
    moreBtn.textContent = "読み込み中…";
    if (reset) {
      offset = 0;
      list.innerHTML = "";
      openRow = null;
    }
    try {
      const res = await fetch(`/toolbox/api/cnn10/episodes?offset=${offset}&limit=10`);
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || "一覧の取得に失敗しました。");
      (data.episodes || []).forEach((episode) => list.appendChild(createRow(episode)));
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
      moreBtn.textContent = "さらに古い動画を見る";
    }
  }

  document.getElementById("export-materials-docx-btn").addEventListener("click", async () => {
    const status = document.getElementById("export-materials-status");
    const include = {
      transcript: document.getElementById("export-include-transcript").checked,
      translation: document.getElementById("export-include-translation").checked,
      vocabulary: document.getElementById("export-include-vocab").checked,
      warmup: document.getElementById("export-include-warmup").checked,
      postview: document.getElementById("export-include-postview").checked,
    };
    if (!Object.values(include).some(Boolean)) {
      status.textContent = "出力する項目を選んでください。";
      return;
    }
    const btn = document.getElementById("export-materials-docx-btn");
    btn.disabled = true;
    status.textContent = "Word を作成しています…";
    try {
      const res = await fetch("/toolbox/api/cnn10/materials/docx", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": window.TOOLBOX_CSRF || "",
        },
        body: JSON.stringify({
          ...lessonPayload(),
          translation: currentLesson.translation || "",
          pairs: currentLesson.pairs || [],
          vocabulary: currentLesson.vocabulary || [],
          warmup: currentLesson.warmup || [],
          discussion: currentLesson.discussion || [],
          include,
        }),
      });
      const contentType = res.headers.get("content-type") || "";
      if (!res.ok || contentType.includes("application/json")) {
        let message = "Word の作成に失敗しました。";
        try {
          const data = await res.json();
          if (data.error) message = data.error;
        } catch (_err) { /* ignore */ }
        throw new Error(message);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      const name = (document.getElementById("lesson-name").value || document.getElementById("lesson-title").value || "lesson_materials")
        .replace(/[\\/:*?"<>|]+/g, " ").trim().slice(0, 40);
      a.href = url;
      a.download = name ? `${name}.docx` : "lesson_materials.docx";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      status.textContent = "Word をダウンロードしました。";
    } catch (err) {
      status.textContent = err.message;
    } finally {
      btn.disabled = false;
    }
  });

  const searchInput = document.getElementById("cnn10-search");
  const searchStatus = document.getElementById("cnn10-search-status");
  const libraryBtn = document.getElementById("cnn10-library-btn");
  const aiToggle = document.getElementById("cnn10-ai-toggle");
  const aiBtn = document.getElementById("cnn10-ai-btn");
  const aiPrep = document.getElementById("cnn10-ai-prep");
  let searchTimer = null;
  let libraryTimer = null;
  let embedTimer = null;

  function showSearchRows(episodes, summary) {
    list.innerHTML = "";
    openRow = null;
    if (summary) {
      const note = document.createElement("p");
      note.className = "tb-note";
      note.textContent = summary;
      list.appendChild(note);
    }
    (episodes || []).forEach((episode) => list.appendChild(createRow(episode)));
    moreBtn.hidden = true;
  }

  async function refreshLibraryStatus() {
    const res = await fetch("/toolbox/api/cnn10/library/status");
    const data = await res.json();
    if (!data.ok) return;
    const job = data.job || {};
    libraryBtn.disabled = Boolean(data.running);
    libraryBtn.textContent = data.running ? "取得中…" : (data.count ? "新着を取り込む" : "一覧を取得");
    if (!aiToggle.checked) {
      searchStatus.textContent = data.running
        ? `取得中… ${job.pages || 0} ページ / ${job.added || 0} 本`
        : (data.count ? `文字検索できる動画 ${data.count} 本` : "まだ一覧がありません。「一覧を取得」を押すと文字検索できます。");
    }
    if (data.running) {
      libraryTimer = setTimeout(refreshLibraryStatus, 2000);
    } else if (libraryTimer) {
      clearTimeout(libraryTimer);
      libraryTimer = null;
    }
  }

  async function refreshEmbedStatus() {
    const res = await fetch("/toolbox/api/cnn10/library/embeddings/status");
    const data = await res.json();
    if (!data.ok) return;
    aiBtn.disabled = !data.ready || data.running;
    aiPrep.hidden = !aiToggle.checked || data.running || (data.ready && !data.missing_count);
    aiPrep.textContent = data.ready ? "未準備分を準備" : "AI検索を準備";
    if (aiToggle.checked) {
      searchStatus.textContent = data.running
        ? "AI検索を準備しています…"
        : (data.ready ? `AI検索の準備済み ${data.embedded_count} 本` : "AI検索はまだ準備されていません。");
    }
    if (data.running) embedTimer = setTimeout(refreshEmbedStatus, 2000);
  }

  async function runTextSearch() {
    const query = searchInput.value.trim();
    if (aiToggle.checked) return;
    if (!query) {
      loadEpisodes(true);
      refreshLibraryStatus();
      return;
    }
    const res = await fetch(`/toolbox/api/cnn10/library/search?q=${encodeURIComponent(query)}&limit=50`);
    const data = await res.json();
    if (!data.ok) {
      searchStatus.textContent = data.error || "文字検索に失敗しました。";
      return;
    }
    const episodes = data.episodes || [];
    showSearchRows(episodes, episodes.length
      ? `${data.total} 件ヒット${data.total > episodes.length ? `（${episodes.length} 件表示）` : ""}`
      : "該当する動画がありません。");
  }

  async function runAiSearch() {
    const query = searchInput.value.trim();
    if (!query) {
      searchStatus.textContent = "検索する文章を入力してください。";
      return;
    }
    searchStatus.textContent = "AI検索中…";
    const res = await fetch(`/toolbox/api/cnn10/library/search/semantic?q=${encodeURIComponent(query)}&limit=10`);
    const data = await res.json();
    if (!data.ok) {
      searchStatus.textContent = data.error || "AI検索に失敗しました。";
      return;
    }
    const episodes = (data.episodes || []).map((episode) => ({
      ...episode,
      published: [`類似度 ${Math.round((Number(episode.score) || 0) * 100)}%`, episode.published || ""].filter(Boolean).join(" · "),
    }));
    showSearchRows(episodes, episodes.length ? `AI検索の結果 ${episodes.length} 件` : "近い動画がありません。");
  }

  searchInput.addEventListener("input", () => {
    if (aiToggle.checked) return;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(runTextSearch, 300);
  });
  searchInput.addEventListener("keydown", (ev) => {
    if (aiToggle.checked && ev.key === "Enter") {
      ev.preventDefault();
      runAiSearch();
    }
  });
  libraryBtn.addEventListener("click", async () => {
    const mode = libraryBtn.textContent.includes("新着") ? "diff" : "full";
    libraryBtn.disabled = true;
    const data = await postJson("/toolbox/api/cnn10/library/update", { mode });
    if (!data.ok) {
      searchStatus.textContent = data.error || "取得を開始できませんでした。";
      libraryBtn.disabled = false;
      return;
    }
    refreshLibraryStatus();
  });
  aiToggle.addEventListener("change", () => {
    const on = aiToggle.checked;
    aiBtn.hidden = !on;
    aiPrep.hidden = !on;
    searchInput.placeholder = on ? "AI検索（例: 健康診断の重要性）" : "文字検索（例: Mars, election）";
    if (on) refreshEmbedStatus();
    else {
      aiPrep.hidden = true;
      runTextSearch();
    }
  });
  aiBtn.addEventListener("click", runAiSearch);
  aiPrep.addEventListener("click", async () => {
    aiPrep.disabled = true;
    const data = await postJson("/toolbox/api/cnn10/library/embeddings/init", {});
    aiPrep.disabled = false;
    if (!data.ok) {
      searchStatus.textContent = data.error || "準備を開始できませんでした。";
      return;
    }
    refreshEmbedStatus();
  });

  document.getElementById("cnn10-open-btn").addEventListener("click", () => {
    panel.hidden = false;
    refreshLibraryStatus();
    if (!list.children.length) loadEpisodes(true);
  });
  document.getElementById("cnn10-close-btn").addEventListener("click", () => {
    panel.hidden = true;
  });
  moreBtn.addEventListener("click", () => loadEpisodes(false));

  fetch("/toolbox/api/cnn10/lesson").then((res) => res.json()).then((data) => {
    if (!data.ok) return;
    renderAssist(data.lesson || {});
    renderArchives(data.archives || []);
  }).catch(() => {});
})();
