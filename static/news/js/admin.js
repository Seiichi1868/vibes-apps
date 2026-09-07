(function () {
  const CEFR_LEVELS = window.CEFR_LEVELS || ["A2", "B1", "B2"];

  function t(key, vars) {
    return window.NewsI18n ? window.NewsI18n.t(key, vars) : key;
  }
  function mapPos(pos) {
    return window.NewsI18n ? window.NewsI18n.mapPos(pos) : pos || "";
  }
  function showAssistive() {
    return window.NewsI18n ? window.NewsI18n.showAssistive() : true;
  }
  function assistiveLang() {
    return window.NewsI18n ? window.NewsI18n.assistiveLang() : "ja";
  }

  const classSelect = document.getElementById("class-select");
  const newClassName = document.getElementById("new-class-name");
  const createClassBtn = document.getElementById("create-class-btn");
  const reloadClassBtn = document.getElementById("reload-class-btn");
  const classMessage = document.getElementById("class-message");
  const lessonForm = document.getElementById("lesson-form");
  const lessonMessage = document.getElementById("lesson-message");
  const lessonClassId = document.getElementById("lesson-class-id");
  const lessonClassLabel = document.getElementById("lesson-class-label");
  const archiveBtn = document.getElementById("archive-btn");
  const archiveTitle = document.getElementById("archive-title");
  const archiveSummary = document.getElementById("archive-summary");
  const archiveList = document.getElementById("archive-list");
  const archiveEmptyMessage = document.getElementById("archive-empty-message");
  const resetLessonBtn = document.getElementById("reset-lesson-btn");
  const settingsForm = document.getElementById("settings-form");
  const settingsMessage = document.getElementById("settings-message");
  const adminSettingsLock = document.getElementById("admin-settings-lock");
  const adminSettingsPassword = document.getElementById("admin-settings-password");
  const adminSettingsUnlock = document.getElementById("admin-settings-unlock");
  const adminSettingsLockMessage = document.getElementById("admin-settings-lock-message");
  const adminSettingsPanel = document.getElementById("admin-settings-panel");
  const generateLinkBtn = document.getElementById("generate-link-btn");
  const copyShareLinkBtn = document.getElementById("copy-share-link-btn");
  const shareLinkOutput = document.getElementById("share-link-output");
  const openScreenBtn = document.getElementById("open-screen-btn");
  const copyScreenLinkBtn = document.getElementById("copy-screen-link-btn");
  const cnn10OpenBtn = document.getElementById("cnn10-open-btn");
  const cnn10Panel = document.getElementById("cnn10-panel");
  const cnn10CloseBtn = document.getElementById("cnn10-close-btn");
  const cnn10List = document.getElementById("cnn10-list");
  const cnn10Message = document.getElementById("cnn10-message");
  const cnn10MoreBtn = document.getElementById("cnn10-more-btn");
  const tabLesson = document.getElementById("tab-lesson");
  const tabResults = document.getElementById("tab-results");
  const resultsClassFilter = document.getElementById("results-class-filter");
  const resultsLessonFilter = document.getElementById("results-lesson-filter");
  const resultsLoadBtn = document.getElementById("results-load-btn");
  const resultsExportBtn = document.getElementById("results-export-btn");
  const resultsSelectAllBtn = document.getElementById("results-select-all-btn");
  const resultsDeleteSelectedBtn = document.getElementById("results-delete-selected-btn");
  const resultsPdfSelectedBtn = document.getElementById("results-pdf-selected-btn");
  const resultsSortKey = document.getElementById("results-sort-key");
  const resultsSortDirection = document.getElementById("results-sort-direction");
  const resultsTable = document.getElementById("results-table");
  const resultsTbody = document.getElementById("results-tbody");
  const resultsEmpty = document.getElementById("results-empty");
  const rosterFileInput = document.getElementById("roster-file-input");
  const rosterUploadBtn = document.getElementById("roster-upload-btn");
  const rosterMessage = document.getElementById("roster-message");
  const scriptTranslateBtn = document.getElementById("script-translate-btn");
  const scriptTranslateStatus = document.getElementById("script-translate-status");
  const scriptTranslatePanel = document.getElementById("script-translate-panel");
  const scriptTranslateList = document.getElementById("script-translate-list");
  const scriptTranslatePanelStatus = document.getElementById("script-translate-panel-status");
  const scriptTranslateCloseBtn = document.getElementById("script-translate-close-btn");
  const scriptTranslateRetryBtn = document.getElementById("script-translate-retry-btn");
  const scriptTranslateDocxBtn = document.getElementById("script-translate-docx-btn");
  const vocabScaffoldingEnabledEl = document.getElementById("vocab-scaffolding-enabled");
  const vocabExtractBtn = document.getElementById("vocab-extract-btn");
  const vocabExtractStatus = document.getElementById("vocab-extract-status");
  const vocabPreview = document.getElementById("vocab-preview");
  const vocabManualWord = document.getElementById("vocab-manual-word");
  const vocabManualPos = document.getElementById("vocab-manual-pos");
  const vocabManualMeaning = document.getElementById("vocab-manual-meaning");
  const vocabManualCefr = document.getElementById("vocab-manual-cefr");
  const vocabManualAddBtn = document.getElementById("vocab-manual-add-btn");
  const vocabMinCefrEl = document.getElementById("vocab-min-cefr");
  let adminVocabItems = [];
  const warmupScaffoldingEnabledEl = document.getElementById("warmup-scaffolding-enabled");
  const warmupGenerateBtn = document.getElementById("warmup-generate-btn");
  const warmupGenerateStatus = document.getElementById("warmup-generate-status");
  const warmupPreview = document.getElementById("warmup-preview");
  const warmupManualSection = document.getElementById("warmup-manual-section");
  const warmupManualRows = document.getElementById("warmup-manual-rows");
  const warmupAddQuestionBtn = document.getElementById("warmup-add-question-btn");
  let adminWarmupQuestions = [];
  let adminWarmupImageUrl = "";
  let warmupSelectionSaving = false;
  let warmupManualSaveTimer = null;
  let vocabSelectionSaving = false;
  const postviewScaffoldingEnabledEl = document.getElementById("postview-scaffolding-enabled");
  const postviewGenerateBtn = document.getElementById("postview-generate-btn");
  const postviewGenerateStatus = document.getElementById("postview-generate-status");
  const postviewPreview = document.getElementById("postview-preview");
  const postviewManualRows = document.getElementById("postview-manual-rows");
  const postviewAddQuestionBtn = document.getElementById("postview-add-question-btn");
  const exportMaterialsDocxBtn = document.getElementById("export-materials-docx-btn");
  const exportMaterialsStatus = document.getElementById("export-materials-status");
  let adminPostviewQuestions = [];
  let postviewSelectionSaving = false;
  let postviewManualSaveTimer = null;
  const ADMIN_SETTINGS_PASSWORD = "2479";
  const ADMIN_SETTINGS_UNLOCK_KEY = "news-admin-settings-unlocked";
  let adminClasses = window.ADMIN_CLASSES || [];
  let adminSettingsPasswordValue = "";
  let latestSubmissions = [];
  let allResultsSelected = false;
  let cnn10NextOffset = 0;
  let cnn10HasMore = false;
  let cnn10Loading = false;
  let cnn10OpenPreviewRow = null;
  const transcriptClientCache = new Map();
  let suppressAutoScriptFill = false;
  let scriptAutoManaged = false;
  let autoScriptTimer = null;
  let autoScriptRequestId = 0;
  const pageBgLayer = document.getElementById("page-bg-layer");
  const bgCurrentLabel = document.getElementById("bg-current-label");
  const bgPicker = document.getElementById("bg-picker");
  const bgOpacitySlider = document.getElementById("bg-opacity-slider");
  const bgOpacityValue = document.getElementById("bg-opacity-value");
  let currentBackgroundId = bgPicker?.querySelector(".bg-pick-btn-active")?.dataset.bgId || "mountain";

  function showMessage(el, text, isError) {
    if (!el) return;
    el.textContent = text;
    el.classList.remove("hidden", "text-emerald-600", "text-red-600", "text-amber-800");
    el.classList.add(isError ? "text-red-600" : "text-emerald-600");
  }

  function pageBackgroundLayers() {
    const layers = Array.from(document.querySelectorAll(".page-bg"));
    if (pageBgLayer && !layers.includes(pageBgLayer)) layers.push(pageBgLayer);
    return layers;
  }

  function applyBackgroundOpacity(opacity) {
    const value = Math.max(0, Math.min(1, Number(opacity) || 0));
    pageBackgroundLayers().forEach((el) => {
      el.style.opacity = "1";
    });
    document.querySelectorAll(".page-bg-veil").forEach((el) => {
      el.style.opacity = String(1 - value);
    });
    const percent = Math.round(value * 100);
    if (bgOpacitySlider) bgOpacitySlider.value = String(percent);
    if (bgOpacityValue) bgOpacityValue.textContent = String(percent);
  }

  function getBackgroundOpacityFromSlider() {
    const percent = parseInt(bgOpacitySlider?.value, 10);
    return Number.isFinite(percent) ? percent / 100 : 0.38;
  }

  function applyBackground(bgId, imageUrl, label) {
    currentBackgroundId = bgId;
    if (imageUrl) {
      pageBackgroundLayers().forEach((el) => {
        el.style.backgroundImage = `url("${imageUrl}")`;
      });
    }
    if (bgCurrentLabel && label) {
      bgCurrentLabel.textContent = label;
    }
    bgPicker?.querySelectorAll(".bg-pick-btn").forEach((btn) => {
      btn.classList.toggle("bg-pick-btn-active", btn.dataset.bgId === bgId);
    });
  }

  function showCnn10Panel() {
    if (!cnn10Panel) return;
    cnn10Panel.classList.remove("hidden");
    cnn10Panel.classList.add("flex");
  }

  function hideCnn10Panel() {
    if (!cnn10Panel) return;
    if (cnn10OpenPreviewRow) {
      const prevPanel = cnn10OpenPreviewRow.querySelector("[data-cnn10-preview]");
      const prevThumb = cnn10OpenPreviewRow.querySelector("[data-cnn10-thumb]");
      const prevIframe = cnn10OpenPreviewRow.querySelector("iframe");
      prevPanel?.classList.add("hidden");
      prevThumb?.classList.remove("ring-2", "ring-sky-400");
      if (prevIframe) prevIframe.src = prevIframe.src;
      cnn10OpenPreviewRow = null;
    }
    cnn10Panel.classList.add("hidden");
    cnn10Panel.classList.remove("flex");
  }

  function parseLessonTime(text) {
    const raw = String(text || "").trim();
    if (!raw) return null;
    const normalized = raw.replace(/\s*秒\s*$/i, "").trim();
    if (/^\d+$/.test(normalized)) return parseInt(normalized, 10);
    if (normalized.includes(":")) {
      const parts = normalized.split(":").map((part) => parseInt(part, 10));
      if (parts.some((value) => !Number.isFinite(value))) return null;
      if (parts.length === 2) return parts[0] * 60 + parts[1];
      if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
      return null;
    }
    return null;
  }

  function getVideoIdFromLessonUrl() {
    const url = document.getElementById("youtube-url")?.value.trim() || "";
    if (/^[a-zA-Z0-9_-]{11}$/.test(url)) return url;
    const match = url.match(/(?:v=|vi=|\/)([0-9A-Za-z_-]{11})(?=$|[^0-9A-Za-z_-])/i);
    return match ? match[1] : "";
  }

  async function fetchYoutubeTranscriptClient({ videoId, startSec = null, endSec = null } = {}) {
    if (!window.YoutubeTranscript?.fetchTranscript) {
      throw new Error("字幕取得モジュールが読み込まれていません。ページを再読み込みしてください。");
    }

    const cacheKey = `${videoId || ""}:${startSec ?? ""}:${endSec ?? ""}`;
    if (transcriptClientCache.has(cacheKey)) {
      return transcriptClientCache.get(cacheKey);
    }

    try {
      const data = await window.YoutubeTranscript.fetchTranscript(videoId, {
        languages: ["en", "ja"],
        startSec,
        endSec,
      });
      transcriptClientCache.set(cacheKey, data);
      return data;
    } catch (err) {
      throw err instanceof Error ? err : new Error(String(err || "文字起こしの取得に失敗しました。"));
    }
  }

  async function fetchYoutubeHighlight(title, snippets) {
    const res = await fetch("/news/admin/api/youtube/highlight", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title,
        snippets: snippets || [],
      }),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "区間推定に失敗しました。");
    return data.highlight || null;
  }

  async function autoFillLessonScriptFromTranscript() {
    if (suppressAutoScriptFill) return;

    const startEl = document.getElementById("start-time");
    const endEl = document.getElementById("end-time");
    const scriptEl = document.getElementById("lesson-script");
    if (!startEl || !endEl || !scriptEl) return;

    const videoId = getVideoIdFromLessonUrl();
    const startSec = parseLessonTime(startEl.value);
    const endSec = parseLessonTime(endEl.value);
    if (!videoId || startSec === null || endSec === null || endSec <= startSec) return;

    const currentScript = scriptEl.value.trim();
    if (currentScript && !scriptAutoManaged) return;

    const requestId = ++autoScriptRequestId;
    scriptEl.placeholder = "文字起こしを取得中…";

    try {
      const data = await fetchYoutubeTranscriptClient({
        videoId,
        startSec,
        endSec,
      });
      if (requestId !== autoScriptRequestId) return;

      scriptEl.value = data.script || "";
      scriptEl.placeholder = "英文スクリプトをここに貼り付け…";
      setLessonScriptJa("");
      setLessonScriptJaPairs([]);
      scriptAutoManaged = true;
      if (lessonMessage) {
        showMessage(
          lessonMessage,
          "指定時間のスクリプトを自動入力しました。内容を確認して保存してください。",
          false
        );
      }
    } catch (err) {
      if (requestId !== autoScriptRequestId) return;
      scriptEl.placeholder = "英文スクリプトをここに貼り付け…";
      if (lessonMessage) {
        showMessage(lessonMessage, err.message || "文字起こしの自動取得に失敗しました。", true);
      }
    }
  }

  function scheduleAutoScriptFill() {
    if (autoScriptTimer) clearTimeout(autoScriptTimer);
    autoScriptTimer = setTimeout(() => {
      autoScriptTimer = null;
      autoFillLessonScriptFromTranscript();
    }, 600);
  }

  function setLessonTitle(title) {
    const value = String(title || "").trim();
    const lessonTitleEl = document.getElementById("lesson-title");
    if (lessonTitleEl) lessonTitleEl.value = value;
    if (archiveTitle) archiveTitle.value = value;
  }

  function getLessonTitle() {
    const lessonTitleEl = document.getElementById("lesson-title");
    const fromLesson = lessonTitleEl ? lessonTitleEl.value.trim() : "";
    if (fromLesson) return fromLesson;
    return archiveTitle ? archiveTitle.value.trim() : "";
  }

  function selectCnn10EpisodeForLesson(episode, highlight) {
    const urlEl = document.getElementById("youtube-url");
    const startEl = document.getElementById("start-time");
    const endEl = document.getElementById("end-time");
    const scriptEl = document.getElementById("lesson-script");

    suppressAutoScriptFill = true;
    if (urlEl) urlEl.value = episode.url || "";
    setLessonTitle(episode.title || "");
    if (highlight?.ok) {
      if (startEl) startEl.value = highlight.start_display || formatTime(highlight.start_sec);
      if (endEl) endEl.value = highlight.end_display || formatTime(highlight.end_sec);
    } else {
      if (startEl) startEl.value = "";
      if (endEl) endEl.value = "";
    }
    if (scriptEl) {
      scriptEl.value = "";
      scriptEl.placeholder = highlight?.ok
        ? "開始・終了時間を確認するとスクリプトが自動入力されます…"
        : "開始・終了時間を入力すると自動入力されます…";
    }
    setLessonScriptJa("");
    setLessonScriptJaPairs([]);
    suppressAutoScriptFill = false;
    scriptAutoManaged = true;

    hideCnn10Panel();
    document.querySelector('.tab-btn[data-tab="lesson"]')?.click();
    startEl?.focus();
    if (lessonMessage) {
      showMessage(
        lessonMessage,
        highlight?.ok
          ? "動画と調整した区間を授業設定に反映しました。内容を確認して保存してください。"
          : "動画を授業設定に反映しました。開始・終了時間を入力するとスクリプトが自動入力されます。",
        false
      );
    }
    scheduleAutoScriptFill();
  }

  function updateCnn10MoreButton() {
    if (!cnn10MoreBtn) return;
    cnn10MoreBtn.classList.toggle("hidden", !cnn10HasMore);
    cnn10MoreBtn.disabled = cnn10Loading;
    cnn10MoreBtn.textContent = cnn10Loading ? "読み込み中…" : "さらに古い動画を見る";
  }

  function snippetDurationSec(snippets) {
    let max = 0;
    (snippets || []).forEach((snippet) => {
      const start = Number(snippet.start) || 0;
      const duration = Number(snippet.duration) || 0;
      max = Math.max(max, Math.ceil(start + duration));
    });
    return Math.max(max, 1);
  }

  function normalizeHighlightRange(highlight, maxSec) {
    const ceiling = Math.max(1, parseInt(maxSec, 10) || 1);
    let start = Math.max(0, Math.min(parseInt(highlight?.start_sec, 10) || 0, ceiling));
    let end = Math.max(0, Math.min(parseInt(highlight?.end_sec, 10) || ceiling, ceiling));
    if (end <= start) end = Math.min(ceiling, start + 1);
    if (end <= start) start = Math.max(0, end - 1);
    return {
      ...(highlight && typeof highlight === "object" ? highlight : {}),
      ok: true,
      start_sec: start,
      end_sec: end,
      start_display: formatTime(start),
      end_display: formatTime(end),
    };
  }

  function seekCnn10Preview(iframe, videoId, startSec, endSec) {
    if (!iframe || !videoId) return;
    const start = Math.max(0, parseInt(startSec, 10) || 0);
    const end = Math.max(start + 1, parseInt(endSec, 10) || start + 1);
    iframe.src =
      `https://www.youtube.com/embed/${encodeURIComponent(videoId)}` +
      `?start=${start}&end=${end}&rel=0&modestbranding=1&hl=en&cc_lang_pref=en`;
  }

  async function loadCnn10Transcript(videoId, episodeTitle, transcriptMeta, transcriptText, highlightBanner, iframe) {
    transcriptText.textContent = "文字起こしを読み込み中…";
    transcriptText.classList.remove("font-mono");
    if (highlightBanner) {
      highlightBanner.classList.add("hidden");
      highlightBanner.innerHTML = "";
    }
    transcriptMeta.classList.add("hidden");

    const data = await fetchYoutubeTranscriptClient({ videoId });
    const snippets = data.snippets || [];
    let highlight = null;
    if (episodeTitle) {
      try {
        highlight = await fetchYoutubeHighlight(episodeTitle, data.all_snippets || snippets);
      } catch (err) {
        highlight = { ok: false, error: err.message || "区間推定に失敗しました。" };
      }
    }

    const maxSec = snippetDurationSec(data.all_snippets || snippets);
    const adjustable = snippets.length
      ? normalizeHighlightRange(
          highlight?.ok ? highlight : { start_sec: 0, end_sec: maxSec, note: highlight?.error || "" },
          maxSec
        )
      : null;
    if (adjustable) {
      adjustable.story_title = episodeTitle || highlight?.title || "";
    }
    if (adjustable && highlight?.ok) {
      adjustable.confidence = highlight.confidence;
      adjustable.note = highlight.note;
      adjustable.from_ai = true;
    } else if (adjustable) {
      adjustable.from_ai = false;
      adjustable.error = highlight?.error || "";
    }

    renderCnn10Transcript(transcriptText, snippets, adjustable, highlightBanner, {
      maxSec,
      onInput: (updated) => {
        paintCnn10TranscriptLines(transcriptText, snippets, updated);
      },
      onChange: (updated) => {
        paintCnn10TranscriptLines(transcriptText, snippets, updated);
        seekCnn10Preview(iframe, videoId, updated.start_sec, updated.end_sec);
      },
    });
    if (adjustable) {
      seekCnn10Preview(iframe, videoId, adjustable.start_sec, adjustable.end_sec);
    }

    const kind = data.is_generated ? "自動生成" : "手動";
    let metaText = `${data.language || "English"} (${kind})`;
    if (adjustable?.from_ai) {
      metaText += ` · AI推定区間 ${adjustable.start_display}–${adjustable.end_display} (${adjustable.confidence || "medium"})`;
    }
    transcriptMeta.textContent = metaText;
    transcriptMeta.classList.remove("hidden");
    return { ...data, snippets, highlight: adjustable };
  }

  function paintCnn10TranscriptLines(container, snippets, highlight) {
    container.innerHTML = "";
    container.classList.remove("font-mono");
    if (!snippets.length) {
      container.textContent = "（文字起こしが空です）";
      container.classList.add("font-mono");
      return;
    }

    const startSec = highlight?.from_ai && highlight?.ok ? highlight.start_sec : null;
    const endSec = highlight?.from_ai && highlight?.ok ? highlight.end_sec : null;
    snippets.forEach((snippet) => {
      const line = document.createElement("div");
      const start = Number(snippet.start) || 0;
      const inRange =
        startSec !== null && endSec !== null && start >= startSec && start < endSec;
      line.className = inRange
        ? "rounded bg-amber-100/90 px-1 py-0.5 -mx-1 font-mono text-[10px] leading-relaxed text-slate-800"
        : "font-mono text-[10px] leading-relaxed text-slate-700";
      line.textContent = `${formatTime(start)}  ${snippet.text || ""}`;
      container.appendChild(line);
    });
  }

  function renderCnn10HighlightControls(banner, highlight, maxSec, handlers = {}) {
    banner.classList.remove("hidden");
    banner.className =
      "mb-2 rounded border border-amber-200 bg-amber-50 px-2 py-1.5 text-[10px] text-amber-950";
    banner.innerHTML = "";

    const heading = document.createElement("p");
    heading.className = "font-semibold";
    const storyTitle = String(highlight.story_title || highlight.title || "").trim();
    heading.textContent = highlight.from_ai
      ? storyTitle
        ? `タイトル（${storyTitle}）に対応する区間（AI推定・スライダーで調整可）`
        : "タイトルに対応する区間（AI推定・スライダーで調整可）"
      : "再生区間（スライダーで調整可）";
    banner.appendChild(heading);

    if (highlight.from_ai && highlight.note) {
      const note = document.createElement("p");
      note.className = "mt-0.5 text-[10px] text-amber-800/90";
      note.textContent = highlight.note;
      banner.appendChild(note);
    } else if (!highlight.from_ai && highlight.error) {
      const note = document.createElement("p");
      note.className = "mt-0.5 text-[10px] text-amber-800/90";
      note.textContent = `${highlight.error} 全区間から手動で調整できます。`;
      banner.appendChild(note);
    }

    const hint = document.createElement("p");
    hint.className = "mt-0.5 text-[10px] text-amber-800/80";
    hint.textContent = "調整した区間は「授業に設定」で授業設定の開始・終了時間とスクリプトに反映されます。";
    banner.appendChild(hint);

    const startRow = document.createElement("div");
    startRow.className = "mt-1.5";
    const startLabel = document.createElement("div");
    startLabel.className = "mb-0.5 flex items-center justify-between font-semibold";
    const startName = document.createElement("span");
    startName.textContent = "開始";
    const startVal = document.createElement("span");
    startVal.textContent = highlight.start_display;
    startLabel.appendChild(startName);
    startLabel.appendChild(startVal);
    const startRange = document.createElement("input");
    startRange.type = "range";
    startRange.min = "0";
    startRange.max = String(maxSec);
    startRange.step = "1";
    startRange.value = String(highlight.start_sec);
    startRange.className = "cnn10-range";
    startRow.appendChild(startLabel);
    startRow.appendChild(startRange);

    const endRow = document.createElement("div");
    endRow.className = "mt-1";
    const endLabel = document.createElement("div");
    endLabel.className = "mb-0.5 flex items-center justify-between font-semibold";
    const endName = document.createElement("span");
    endName.textContent = "終了";
    const endVal = document.createElement("span");
    endVal.textContent = highlight.end_display;
    endLabel.appendChild(endName);
    endLabel.appendChild(endVal);
    const endRange = document.createElement("input");
    endRange.type = "range";
    endRange.min = "0";
    endRange.max = String(maxSec);
    endRange.step = "1";
    endRange.value = String(highlight.end_sec);
    endRange.className = "cnn10-range";
    endRow.appendChild(endLabel);
    endRow.appendChild(endRange);

    banner.appendChild(startRow);
    banner.appendChild(endRow);

    function emit(source) {
      let start = parseInt(startRange.value, 10) || 0;
      let end = parseInt(endRange.value, 10) || 0;
      const movingStart = source.startsWith("start");
      if (end <= start) {
        if (movingStart) end = Math.min(maxSec, start + 1);
        else start = Math.max(0, end - 1);
        startRange.value = String(start);
        endRange.value = String(end);
      }
      highlight.start_sec = start;
      highlight.end_sec = end;
      highlight.start_display = formatTime(start);
      highlight.end_display = formatTime(end);
      highlight.ok = true;
      startVal.textContent = highlight.start_display;
      endVal.textContent = highlight.end_display;
      if (source.endsWith("change")) handlers.onChange?.(highlight);
      else handlers.onInput?.(highlight);
    }

    startRange.addEventListener("input", () => emit("start"));
    endRange.addEventListener("input", () => emit("end"));
    startRange.addEventListener("change", () => emit("start-change"));
    endRange.addEventListener("change", () => emit("end-change"));
  }

  function renderCnn10Transcript(container, snippets, highlight, highlightBanner, options = {}) {
    if (highlightBanner) {
      if (highlight?.ok) {
        renderCnn10HighlightControls(
          highlightBanner,
          highlight,
          options.maxSec || snippetDurationSec(snippets),
          {
            onInput: options.onInput,
            onChange: options.onChange,
          }
        );
      } else {
        highlightBanner.classList.add("hidden");
        highlightBanner.innerHTML = "";
      }
    }
    paintCnn10TranscriptLines(container, snippets, highlight);
  }

  function createCnn10EpisodeRow(episode) {
    const videoUrl = episode.url || "#";
    const thumbnailUrl =
      episode.thumbnail_url ||
      (episode.video_id ? `https://i.ytimg.com/vi/${episode.video_id}/mqdefault.jpg` : "");

    const row = document.createElement("div");
    row.className = "rounded-lg border border-teal-50 bg-white/70 px-2 py-2";
    row.dataset.videoId = episode.video_id || "";

    const main = document.createElement("div");
    main.className = "flex items-start gap-3";

    const thumbBtn = document.createElement("button");
    thumbBtn.type = "button";
    thumbBtn.title = "プレビューを表示";
    thumbBtn.dataset.cnn10Thumb = "1";
    thumbBtn.className =
      "block shrink-0 overflow-hidden rounded border border-slate-100 bg-slate-100 hover:ring-2 hover:ring-sky-300";
    thumbBtn.innerHTML = `
      <img src="${esc(thumbnailUrl)}" alt="" loading="lazy" width="112" height="63"
        class="aspect-video h-16 w-28 object-cover pointer-events-none"
        onerror="this.closest('button')?.classList.add('hidden')">`;

    const body = document.createElement("div");
    body.className = "min-w-0 flex-1";

    const published = document.createElement("p");
    published.className = "text-[11px] font-semibold text-slate-500";
    published.textContent = episode.published || "";

    const title = document.createElement("p");
    title.className = "mt-0.5 font-semibold text-slate-800";
    title.textContent = episode.title || "Untitled";

    const urlLine = document.createElement("p");
    urlLine.className = "mt-0.5 truncate font-mono text-[10px] text-slate-500";
    const urlLink = document.createElement("a");
    urlLink.className = "text-sky-600 hover:text-sky-800 hover:underline";
    urlLink.href = videoUrl;
    urlLink.target = "_blank";
    urlLink.rel = "noopener noreferrer";
    urlLink.textContent = videoUrl !== "#" ? videoUrl : "";
    urlLink.title = videoUrl;
    urlLine.appendChild(urlLink);

    const actions = document.createElement("div");
    actions.className = "mt-1 flex flex-wrap items-center gap-2";

    const selectBtn = document.createElement("button");
    selectBtn.type = "button";
    selectBtn.className =
      "rounded-full border border-sky-200 bg-sky-600 px-2.5 py-0.5 text-[11px] font-semibold text-white hover:bg-sky-500";
    selectBtn.textContent = "授業に設定";

    const openLink = document.createElement("a");
    openLink.className = "text-[11px] font-medium text-sky-600 hover:text-sky-800";
    openLink.href = videoUrl;
    openLink.target = "_blank";
    openLink.rel = "noopener noreferrer";
    openLink.textContent = "YouTubeで開く";

    const previewPanel = document.createElement("div");
    previewPanel.dataset.cnn10Preview = "1";
    previewPanel.className = "mt-2 hidden rounded border border-slate-100 bg-slate-50/80 p-2";

    const previewGrid = document.createElement("div");
    previewGrid.className = "grid gap-2 md:grid-cols-2";

    const videoWrap = document.createElement("div");
    videoWrap.className = "aspect-video overflow-hidden rounded border border-slate-100 bg-black";
    const iframe = document.createElement("iframe");
    iframe.className = "h-full w-full";
    iframe.src = episode.video_id
      ? `https://www.youtube.com/embed/${encodeURIComponent(episode.video_id)}?rel=0&modestbranding=1&hl=en&cc_lang_pref=en&enablejsapi=1`
      : "";
    iframe.title = episode.title || "YouTube preview";
    iframe.loading = "lazy";
    iframe.allow =
      "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share";
    iframe.referrerPolicy = "strict-origin-when-cross-origin";
    iframe.allowFullscreen = true;
    videoWrap.appendChild(iframe);

    const transcriptWrap = document.createElement("div");
    transcriptWrap.className = "flex min-h-[10rem] flex-col";

    const transcriptMeta = document.createElement("p");
    transcriptMeta.className = "mb-1 hidden text-[10px] text-slate-500";

    const highlightBanner = document.createElement("div");
    highlightBanner.className = "mb-1 hidden";

    const transcriptText = document.createElement("div");
    transcriptText.className =
      "min-h-[10rem] flex-1 overflow-y-auto rounded border border-slate-100 bg-white/80 p-2 leading-relaxed";

    transcriptWrap.appendChild(transcriptMeta);
    transcriptWrap.appendChild(highlightBanner);
    transcriptWrap.appendChild(transcriptText);
    previewGrid.appendChild(videoWrap);
    previewGrid.appendChild(transcriptWrap);
    previewPanel.appendChild(previewGrid);

    actions.appendChild(selectBtn);
    actions.appendChild(openLink);
    body.appendChild(published);
    body.appendChild(title);
    body.appendChild(urlLine);
    body.appendChild(actions);
    main.appendChild(thumbBtn);
    main.appendChild(body);
    row.appendChild(main);
    row.appendChild(previewPanel);

    let transcriptLoaded = false;
    let transcriptLoading = false;
    let episodeHighlight = null;

    selectBtn.addEventListener("click", () => {
      selectCnn10EpisodeForLesson(episode, episodeHighlight);
    });

    async function togglePreview() {
      if (cnn10OpenPreviewRow === row) {
        previewPanel.classList.add("hidden");
        thumbBtn.classList.remove("ring-2", "ring-sky-400");
        iframe.src = iframe.src;
        cnn10OpenPreviewRow = null;
        return;
      }

      if (cnn10OpenPreviewRow) {
        const prevPanel = cnn10OpenPreviewRow.querySelector("[data-cnn10-preview]");
        const prevThumb = cnn10OpenPreviewRow.querySelector("[data-cnn10-thumb]");
        const prevIframe = cnn10OpenPreviewRow.querySelector("iframe");
        prevPanel?.classList.add("hidden");
        prevThumb?.classList.remove("ring-2", "ring-sky-400");
        if (prevIframe) prevIframe.src = prevIframe.src;
      }

      cnn10OpenPreviewRow = row;
      previewPanel.classList.remove("hidden");
      thumbBtn.classList.add("ring-2", "ring-sky-400");

      if (!episode.video_id) {
        transcriptText.textContent = "動画 ID がありません。";
        return;
      }

      loadPreviewTranscript();
    }

    async function loadPreviewTranscript() {
      if (transcriptLoaded || transcriptLoading) return;

      transcriptLoading = true;
      if (cnn10Message) {
        cnn10Message.classList.add("hidden");
        cnn10Message.textContent = "";
      }
      try {
        const data = await loadCnn10Transcript(
          episode.video_id,
          episode.title || "",
          transcriptMeta,
          transcriptText,
          highlightBanner,
          iframe
        );
        episodeHighlight = data.highlight?.ok ? data.highlight : null;
        transcriptLoaded = true;
      } catch (err) {
        const msg = err.message || "文字起こしの取得に失敗しました。";
        transcriptText.replaceChildren();
        const errBox = document.createElement("div");
        errBox.className = "space-y-2";
        const p = document.createElement("p");
        p.className = "rounded border border-amber-100 bg-amber-50 p-2 text-[11px] text-amber-800";
        p.textContent = msg;
        const retryBtn = document.createElement("button");
        retryBtn.type = "button";
        retryBtn.className =
          "rounded-full border border-sky-200 bg-sky-50 px-2.5 py-0.5 text-[11px] font-semibold text-sky-700 hover:bg-sky-100";
        retryBtn.textContent = "文字起こしを再試行";
        retryBtn.addEventListener("click", () => {
          transcriptLoaded = false;
          loadPreviewTranscript();
        });
        errBox.append(p, retryBtn);
        transcriptText.appendChild(errBox);
      } finally {
        transcriptLoading = false;
      }
    }

    thumbBtn.addEventListener("click", () => {
      togglePreview();
    });

    return row;
  }

  function appendCnn10Episodes(episodes) {
    if (!cnn10List || !episodes.length) return;
    episodes.forEach((episode) => {
      cnn10List.appendChild(createCnn10EpisodeRow(episode));
    });
  }

  async function loadCnn10Episodes(reset = true) {
    if (cnn10Loading) return;

    if (reset) {
      cnn10NextOffset = 0;
      cnn10HasMore = false;
      cnn10OpenPreviewRow = null;
      if (cnn10Message) {
        cnn10Message.classList.add("hidden");
        cnn10Message.textContent = "";
      }
      if (cnn10List) {
        cnn10List.innerHTML =
          '<p class="rounded border border-slate-100 bg-slate-50 px-2 py-2 text-slate-500">読み込み中…</p>';
      }
    }

    cnn10Loading = true;
    updateCnn10MoreButton();

    try {
      const res = await fetch(`/news/admin/api/cnn10/episodes?offset=${cnn10NextOffset}&limit=10`);
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || "CNN10 の取得に失敗しました。");

      const episodes = data.episodes || [];
      if (reset) {
        if (!episodes.length) {
          cnn10List.innerHTML =
            '<p class="rounded border border-slate-100 bg-slate-50 px-2 py-2 text-slate-500">動画一覧がありません。</p>';
        } else {
          cnn10List.innerHTML = "";
          appendCnn10Episodes(episodes);
        }
      } else {
        appendCnn10Episodes(episodes);
      }

      cnn10NextOffset = data.next_offset ?? cnn10NextOffset + episodes.length;
      cnn10HasMore = !!data.has_more;
    } catch (err) {
      if (reset && cnn10List) cnn10List.innerHTML = "";
      if (cnn10Message) {
        cnn10Message.textContent = err.message || "CNN10 の取得に失敗しました。";
        cnn10Message.classList.remove("hidden");
      }
    } finally {
      cnn10Loading = false;
      updateCnn10MoreButton();
    }
  }

  async function loadMoreCnn10Episodes() {
    if (!cnn10HasMore || cnn10Loading) return;
    await loadCnn10Episodes(false);
  }

  function getSelectedClassId() {
    return classSelect ? classSelect.value.trim() : "";
  }

  function collectDefaultCriteria() {
    const criteria = {};
    CEFR_LEVELS.forEach((lv) => {
      const el = document.getElementById(`default-criteria-${lv}`);
      criteria[lv] = el ? el.value.trim() : "";
    });
    return criteria;
  }

  function collectClassCriteria() {
    const criteria = {};
    CEFR_LEVELS.forEach((lv) => {
      const el = document.getElementById(`class-criteria-${lv}`);
      criteria[lv] = el ? el.value.trim() : "";
    });
    return criteria;
  }

  function fillLessonForm(cls) {
    if (!cls || !cls.current) return;
    const c = cls.current;
    suppressAutoScriptFill = true;
    document.getElementById("youtube-url").value = c.source_url || "";
    setLessonTitle(c.title || "");
    document.getElementById("start-time").value = formatTime(c.start_seconds || 0);
    document.getElementById("end-time").value = formatTime(c.end_seconds || 0);
    document.getElementById("lesson-script").value = c.script || "";
    setLessonScriptJa(c.script_ja || "");
    setLessonScriptJaPairs(c.script_ja_pairs || []);
    setLessonScriptEs(c.script_es || "");
    setLessonScriptEsPairs(c.script_es_pairs || []);
    document.getElementById("prep-timer-seconds").value = c.prep_timer_seconds ?? 60;
    document.getElementById("record-timer-seconds").value = c.record_timer_seconds ?? 60;
    document.getElementById("timers-visible").checked = c.timers_visible !== false;
    document.getElementById("subtitles-enabled").checked = c.subtitles_enabled === true;
    const requireStudentInfoEl = document.getElementById("require-student-info");
    if (requireStudentInfoEl) requireStudentInfoEl.checked = cls.require_student_info === true;
    if (vocabScaffoldingEnabledEl) vocabScaffoldingEnabledEl.checked = c.vocabulary_scaffolding_enabled === true;
    if (vocabMinCefrEl && c.vocabulary_min_cefr) vocabMinCefrEl.value = c.vocabulary_min_cefr;
    renderAdminVocabPreview(c.vocabulary_data || []);
    if (warmupScaffoldingEnabledEl) warmupScaffoldingEnabledEl.checked = c.warmup_scaffolding_enabled === true;
    renderAdminWarmupPreview(c.warmup_image_url || "", c.warmup_questions || []);
    if (postviewScaffoldingEnabledEl) postviewScaffoldingEnabledEl.checked = c.postview_scaffolding_enabled === true;
    renderAdminPostviewPreview(c.postview_questions || []);
    scriptAutoManaged = false;
    suppressAutoScriptFill = false;
    if (lessonClassId) lessonClassId.value = cls.id;
    if (lessonClassLabel) lessonClassLabel.textContent = cls.name;
    CEFR_LEVELS.forEach((lv) => {
      const el = document.getElementById(`class-criteria-${lv}`);
      if (el) el.value = (c.evaluation_criteria && c.evaluation_criteria[lv]) || "";
    });
    if (archiveBtn) archiveBtn.disabled = false;
    if (resetLessonBtn) resetLessonBtn.disabled = false;
    const saveBtn = document.getElementById("save-lesson-btn");
    if (saveBtn) saveBtn.disabled = false;
    updateScreenButtons(cls.id);
    renderArchiveList(cls);
  }

  function updateScreenButtons(classId) {
    const enabled = Boolean(classId);
    if (openScreenBtn) openScreenBtn.disabled = !enabled;
    if (copyScreenLinkBtn) copyScreenLinkBtn.disabled = !enabled;
  }

  async function fetchScreenLink(classId) {
    const res = await fetch(
      `/news/admin/api/screen-link?class_id=${encodeURIComponent(classId)}`
    );
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "スクリーンリンクの取得に失敗しました");
    return data.link;
  }

  function formatTime(sec) {
    const s = Math.max(0, parseInt(sec, 10) || 0);
    const m = Math.floor(s / 60);
    const r = s % 60;
    return `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
  }

  function parseTimerValue(el, fallback) {
    if (!el || el.value.trim() === "") return fallback;
    const value = parseInt(el.value, 10);
    return Number.isFinite(value) ? Math.max(0, value) : fallback;
  }

  function renderArchiveList(cls) {
    if (!archiveList || !archiveSummary || !archiveEmptyMessage) return;
    const archive = cls && Array.isArray(cls.archive) ? cls.archive : [];
    const currentClassId = cls ? cls.id : getSelectedClassId();

    archiveSummary.textContent = t("archiveSummary", { n: archive.length });
    archiveList.innerHTML = "";
    archiveEmptyMessage.classList.toggle("hidden", archive.length > 0);

    archive.forEach((item, index) => {
      const li = document.createElement("li");
      li.className = "rounded border border-teal-100/80 bg-white/50 px-1.5 py-1";
      li.dataset.archiveIndex = String(index);

      const row = document.createElement("div");
      row.className = "flex min-w-0 items-center gap-1.5";

      const textWrap = document.createElement("div");
      textWrap.className = "min-w-0 flex-1";

      const title = document.createElement("p");
      title.className = "truncate font-semibold leading-tight text-slate-700";
      title.textContent = item.title || item.video_id || "無題のアーカイブ";

      const meta = document.createElement("p");
      meta.className = "truncate leading-tight";
      const archivedAt = item.archived_at ? String(item.archived_at).slice(0, 10) : "—";
      const scriptLength = (item.script || "").length;
      meta.textContent = `${archivedAt} · ${item.video_id || "—"} · ${item.start_seconds || 0}s–${item.end_seconds || 0}s · ${scriptLength}字`;

      textWrap.append(title, meta);
      row.appendChild(textWrap);

      const actions = document.createElement("div");
      actions.className = "flex shrink-0 items-center gap-1";

      const restoreBtn = document.createElement("button");
      restoreBtn.type = "button";
      restoreBtn.className = "restore-archive-btn rounded border border-sky-100 bg-white/80 px-1.5 py-0.5 text-[9px] font-semibold leading-none text-sky-700 hover:bg-sky-50";
      restoreBtn.textContent = "戻す";

      const deleteBtn = document.createElement("button");
      deleteBtn.type = "button";
      deleteBtn.className = "delete-archive-btn rounded border border-red-100 bg-white/80 px-1.5 py-0.5 text-[9px] font-semibold leading-none text-red-600 hover:bg-red-50";
      deleteBtn.textContent = "削除";

      actions.append(restoreBtn, deleteBtn);

      const copyTargets = adminClasses.filter((c) => c.id !== currentClassId);
      if (copyTargets.length) {
        const targetSelect = document.createElement("select");
        targetSelect.className = "archive-copy-target rounded border border-teal-100 bg-white/80 px-1 py-0.5 text-[9px] text-slate-700";
        copyTargets.forEach((c) => {
          const opt = document.createElement("option");
          opt.value = c.id;
          opt.textContent = c.name;
          targetSelect.appendChild(opt);
        });

        const copyBtn = document.createElement("button");
        copyBtn.type = "button";
        copyBtn.className = "copy-archive-btn rounded border border-emerald-100 bg-white/80 px-1.5 py-0.5 text-[9px] font-semibold leading-none text-emerald-700 hover:bg-emerald-50";
        copyBtn.textContent = "コピー";
        actions.append(targetSelect, copyBtn);
      }

      row.appendChild(actions);
      li.appendChild(row);
      archiveList.appendChild(li);
    });
  }

  async function refreshClassList(selectId) {
    const res = await fetch("/news/admin/api/classes");
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "クラス一覧の取得に失敗しました");
    adminClasses = data.classes || [];

    if (classSelect) {
      const prev = classSelect.value;
      classSelect.innerHTML = "";
      if (!data.classes.length) {
        const opt = document.createElement("option");
        opt.value = "";
        opt.textContent = "（クラス未作成）";
        classSelect.appendChild(opt);
      } else {
        data.classes.forEach((c) => {
          const opt = document.createElement("option");
          opt.value = c.id;
          opt.textContent = c.name;
          classSelect.appendChild(opt);
        });
      }
      const target = selectId || data.active_class_id || prev;
      if (target) classSelect.value = target;
    }
    return data;
  }

  async function selectClass(classId) {
    const res = await fetch("/news/admin/api/classes/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ class_id: classId }),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "クラスの切り替えに失敗しました");
    fillLessonForm(data.class);
    return data;
  }

  if (classSelect) {
    classSelect.addEventListener("change", async () => {
      const id = getSelectedClassId();
      if (!id) return;
      try {
        await selectClass(id);
        showMessage(classMessage, "クラスを切り替えました。", false);
      } catch (err) {
        showMessage(classMessage, err.message, true);
      }
    });
  }

  if (createClassBtn) {
    createClassBtn.addEventListener("click", async () => {
      const name = newClassName ? newClassName.value.trim() : "";
      if (!name) {
        showMessage(classMessage, "クラス名を入力してください。", true);
        return;
      }
      createClassBtn.disabled = true;
      try {
        const res = await fetch("/news/admin/api/classes", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name }),
        });
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || "作成に失敗しました");
        await refreshClassList(data.class.id);
        fillLessonForm(data.class);
        if (newClassName) newClassName.value = "";
        showMessage(classMessage, `「${data.class.name}」を作成しました。`, false);
      } catch (err) {
        showMessage(classMessage, err.message, true);
      } finally {
        createClassBtn.disabled = false;
      }
    });
  }

  if (reloadClassBtn) {
    reloadClassBtn.addEventListener("click", () => location.reload());
  }

  function isAdminSettingsOpen() {
    return settingsForm && !settingsForm.classList.contains("hidden");
  }

  function readAdminSettingsUnlock() {
    try {
      return sessionStorage.getItem(ADMIN_SETTINGS_UNLOCK_KEY) === "1";
    } catch (err) {
      return false;
    }
  }

  function persistAdminSettingsUnlock() {
    try {
      sessionStorage.setItem(ADMIN_SETTINGS_UNLOCK_KEY, "1");
    } catch (err) {
      // Ignore storage failures; in-memory unlock still works for this page.
    }
  }

  function syncAdminSettingsLockUi() {
    if (!adminSettingsPassword) return;
    if (adminSettingsPasswordValue) {
      adminSettingsPassword.classList.add("hidden");
      adminSettingsPassword.value = "";
    } else {
      adminSettingsPassword.classList.remove("hidden");
    }
  }

  function rememberAdminSettingsUnlock(password) {
    adminSettingsPasswordValue = password;
    persistAdminSettingsUnlock();
    syncAdminSettingsLockUi();
  }

  function restoreAdminSettingsUnlock() {
    if (readAdminSettingsUnlock()) {
      adminSettingsPasswordValue = ADMIN_SETTINGS_PASSWORD;
    }
    syncAdminSettingsLockUi();
  }

  function openAdminSettingsPanel() {
    if (settingsForm) settingsForm.classList.remove("hidden");
    if (adminSettingsLock) adminSettingsLock.classList.add("hidden");
    if (adminSettingsLockMessage) adminSettingsLockMessage.classList.add("hidden");
  }

  function closeAdminSettingsPanel() {
    if (settingsForm) settingsForm.classList.add("hidden");
    if (adminSettingsLock) adminSettingsLock.classList.remove("hidden");
    if (settingsMessage) settingsMessage.classList.add("hidden");
    syncAdminSettingsLockUi();
  }

  function unlockAdminSettings() {
    if (adminSettingsPasswordValue) {
      openAdminSettingsPanel();
      return;
    }

    const password = adminSettingsPassword ? adminSettingsPassword.value.trim() : "";
    if (password !== ADMIN_SETTINGS_PASSWORD) {
      if (adminSettingsLockMessage) {
        adminSettingsLockMessage.textContent = "パスワードが違います。";
        adminSettingsLockMessage.classList.remove("hidden");
      }
      return;
    }

    rememberAdminSettingsUnlock(password);
    openAdminSettingsPanel();
  }

  restoreAdminSettingsUnlock();

  if (adminSettingsUnlock) {
    adminSettingsUnlock.addEventListener("click", unlockAdminSettings);
  }

  document.addEventListener("click", (e) => {
    if (!isAdminSettingsOpen()) return;
    if (adminSettingsPanel && !adminSettingsPanel.contains(e.target)) {
      closeAdminSettingsPanel();
    }
  });

  if (adminSettingsPassword) {
    adminSettingsPassword.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        unlockAdminSettings();
      }
    });
  }

  if (lessonForm) {
    lessonForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const classId = getSelectedClassId() || (lessonClassId && lessonClassId.value);
      if (!classId) {
        showMessage(lessonMessage, "クラスを選択または作成してください。", true);
        return;
      }

      const btn = document.getElementById("save-lesson-btn");
      btn.disabled = true;
      btn.textContent = t("saving");
      lessonMessage.classList.add("hidden");

      const payload = {
        class_id: classId,
        url: document.getElementById("youtube-url").value.trim(),
        title: getLessonTitle(),
        start_time: document.getElementById("start-time").value.trim(),
        end_time: document.getElementById("end-time").value.trim(),
        script: document.getElementById("lesson-script").value.trim(),
        script_ja: getLessonScriptJa(),
        script_ja_pairs: getLessonScriptJaPairs(),
        script_es: getLessonScriptEs(),
        script_es_pairs: getLessonScriptEsPairs(),
        evaluation_criteria: collectClassCriteria(),
        prep_timer_seconds: parseTimerValue(document.getElementById("prep-timer-seconds"), 0),
        record_timer_seconds: parseTimerValue(document.getElementById("record-timer-seconds"), 60),
        timers_visible: document.getElementById("timers-visible").checked,
        subtitles_enabled: document.getElementById("subtitles-enabled").checked,
        require_student_info: document.getElementById("require-student-info")?.checked ?? false,
        vocabulary_scaffolding_enabled: vocabScaffoldingEnabledEl?.checked ?? false,
        vocabulary_min_cefr: vocabMinCefrEl?.value || "B1",
      };

      try {
        const res = await fetch("/news/admin/api/class/lesson", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || "保存に失敗しました");
        showMessage(lessonMessage, data.message || "保存しました。", false);
        if (data.class) fillLessonForm(data.class);
      } catch (err) {
        showMessage(lessonMessage, err.message, true);
      } finally {
        btn.disabled = false;
        btn.textContent = t("saveLesson");
      }
    });
  }

  if (archiveBtn) {
    archiveBtn.addEventListener("click", async () => {
      const classId = getSelectedClassId();
      if (!classId) return;
      if (!confirm("現在の授業をアーカイブし、入力欄を空にします。よろしいですか？")) return;

      archiveBtn.disabled = true;
      try {
        const res = await fetch("/news/admin/api/class/archive", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ class_id: classId, title: getLessonTitle() }),
        });
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || "アーカイブに失敗しました");
        showMessage(lessonMessage, data.message || "アーカイブしました。", false);
        setTimeout(() => location.reload(), 700);
      } catch (err) {
        showMessage(lessonMessage, err.message, true);
        archiveBtn.disabled = false;
      }
    });
  }

  if (resetLessonBtn) {
    resetLessonBtn.addEventListener("click", async () => {
      const classId = getSelectedClassId();
      if (!classId) return;
      if (!confirm("現在開いているリンク、時間、スクリプト、評価基準、タイマー設定を消去します。よろしいですか？")) {
        return;
      }

      resetLessonBtn.disabled = true;
      try {
        const res = await fetch("/news/admin/api/class/lesson/reset", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ class_id: classId }),
        });
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || "リセットに失敗しました");
        if (data.class) fillLessonForm(data.class);
        if (archiveTitle) archiveTitle.value = "";
        showMessage(lessonMessage, data.message || "現在の授業設定をリセットしました。", false);
      } catch (err) {
        showMessage(lessonMessage, err.message, true);
      } finally {
        resetLessonBtn.disabled = false;
      }
    });
  }

  if (archiveList) {
    archiveList.addEventListener("click", async (e) => {
      const btn = e.target.closest("button");
      if (!btn) return;
      const itemEl = btn.closest("li");
      const classId = getSelectedClassId();
      const archiveIndex = parseInt(itemEl && itemEl.dataset.archiveIndex, 10);
      if (!classId || !Number.isFinite(archiveIndex)) return;

      btn.disabled = true;
      try {
        if (btn.classList.contains("restore-archive-btn")) {
          if (!confirm("現在設定されている動画やスクリプトなどは上書きされます。アーカイブの内容を設定画面に戻しますか？")) {
            return;
          }
          const res = await fetch("/news/admin/api/class/archive/restore", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ class_id: classId, archive_index: archiveIndex }),
          });
          const data = await res.json();
          if (!data.ok) throw new Error(data.error || "復元に失敗しました");
          if (data.class) fillLessonForm(data.class);
          showMessage(lessonMessage, data.message || "アーカイブを設定画面に戻しました。", false);
          return;
        }

        if (btn.classList.contains("delete-archive-btn")) {
          if (!confirm("このアーカイブを削除します。元に戻せません。よろしいですか？")) {
            return;
          }
          const res = await fetch("/news/admin/api/class/archive/delete", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ class_id: classId, archive_index: archiveIndex }),
          });
          const data = await res.json();
          if (!data.ok) throw new Error(data.error || "削除に失敗しました");
          if (data.class) renderArchiveList(data.class);
          showMessage(lessonMessage, data.message || "アーカイブを削除しました。", false);
          return;
        }

        if (btn.classList.contains("copy-archive-btn")) {
          const targetSelect = itemEl.querySelector(".archive-copy-target");
          const targetClassId = targetSelect ? targetSelect.value : "";
          const targetName = targetSelect && targetSelect.selectedOptions[0] ? targetSelect.selectedOptions[0].textContent : "コピー先";
          if (!targetClassId) return;
          if (!confirm(`このアーカイブを「${targetName}」へコピーしますか？`)) {
            return;
          }
          const res = await fetch("/news/admin/api/class/archive/copy", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ class_id: classId, archive_index: archiveIndex, target_class_id: targetClassId }),
          });
          const data = await res.json();
          if (!data.ok) throw new Error(data.error || "コピーに失敗しました");
          showMessage(lessonMessage, data.message || "アーカイブをコピーしました。", false);
        }
      } catch (err) {
        showMessage(lessonMessage, err.message, true);
      } finally {
        btn.disabled = false;
      }
    });
  }

  if (settingsForm) {
    settingsForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const payload = {
        display_language: document.getElementById("display-language").value,
        ai_model: document.getElementById("ai-model").value,
        ai_transcript_model: document.getElementById("ai-transcript-model").value,
        ai_eval_model: document.getElementById("ai-eval-model").value,
        default_cefr_level: document.getElementById("default-cefr-level").value,
        openai_api_key: document.getElementById("openai-api-key").value.trim(),
        default_evaluation_criteria: collectDefaultCriteria(),
        background_id: currentBackgroundId,
        background_opacity: getBackgroundOpacityFromSlider(),
        admin_password: adminSettingsPasswordValue,
      };
      try {
        const res = await fetch("/news/admin/api/settings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || "保存に失敗しました");
        const activeBtn = bgPicker?.querySelector(`.bg-pick-btn[data-bg-id="${data.background_id}"]`);
        applyBackground(
          data.background_id || currentBackgroundId,
          activeBtn?.dataset.bgImage,
          data.background_label || activeBtn?.title
        );
        applyBackgroundOpacity(data.background_opacity ?? getBackgroundOpacityFromSlider());
        showMessage(settingsMessage, t("settingsSaved"), false);
        const nextLang = payload.display_language;
        if (nextLang && nextLang !== window.DISPLAY_LANGUAGE) {
          window.location.reload();
        }
        document.getElementById("openai-api-key").value = "";
        closeAdminSettingsPanel();
      } catch (err) {
        showMessage(settingsMessage, err.message, true);
      }
    });
  }

  bgPicker?.addEventListener("click", (event) => {
    const btn = event.target.closest(".bg-pick-btn");
    if (!btn) return;
    event.preventDefault();
    applyBackground(btn.dataset.bgId, btn.dataset.bgImage, btn.title);
  });

  bgOpacitySlider?.addEventListener("input", () => {
    applyBackgroundOpacity(getBackgroundOpacityFromSlider());
  });

  function copyTextFromInput(inputEl, buttonEl, emptyMessage) {
    const text = inputEl ? inputEl.value.trim() : "";
    if (!text) {
      alert(emptyMessage || "コピーする内容がありません。");
      return;
    }
    const copy = async () => {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
      } else if (inputEl) {
        inputEl.select();
        document.execCommand("copy");
        inputEl.blur();
      }
    };
    copy()
      .then(() => {
        if (!buttonEl) return;
        const prev = buttonEl.textContent;
        buttonEl.textContent = "済";
        setTimeout(() => {
          buttonEl.textContent = prev;
        }, 1200);
      })
      .catch(() => {
        alert("コピーできませんでした。リンク欄を選択してコピーしてください。");
      });
  }

  if (generateLinkBtn) {
    generateLinkBtn.addEventListener("click", async () => {
      const classId = getSelectedClassId();
      if (!classId) {
        alert("クラスを選択してください。");
        return;
      }
      const level = document.getElementById("share-level").value;
      try {
        const res = await fetch(
          `/news/admin/api/share-link?level=${encodeURIComponent(level)}&class_id=${encodeURIComponent(classId)}`
        );
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || "リンク生成に失敗しました");
        shareLinkOutput.value = data.link;
      } catch (err) {
        shareLinkOutput.value = "";
        alert(err.message);
      }
    });
  }

  if (copyShareLinkBtn) {
    copyShareLinkBtn.addEventListener("click", () => {
      copyTextFromInput(shareLinkOutput, copyShareLinkBtn, "先に共有リンクを生成してください。");
    });
  }

  if (openScreenBtn) {
    openScreenBtn.addEventListener("click", async () => {
      const classId = getSelectedClassId();
      if (!classId) {
        alert("クラスを選択してください。");
        return;
      }
      try {
        const link = await fetchScreenLink(classId);
        window.open(link, "_blank", "noopener,noreferrer");
      } catch (err) {
        alert(err.message);
      }
    });
  }

  if (copyScreenLinkBtn) {
    copyScreenLinkBtn.addEventListener("click", async () => {
      const classId = getSelectedClassId();
      if (!classId) {
        alert("クラスを選択してください。");
        return;
      }
      try {
        const link = await fetchScreenLink(classId);
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(link);
        } else {
          prompt("教室スクリーン URL:", link);
          return;
        }
        const prev = copyScreenLinkBtn.textContent;
        copyScreenLinkBtn.textContent = "済";
        setTimeout(() => {
          copyScreenLinkBtn.textContent = prev;
        }, 1200);
      } catch (err) {
        alert(err.message);
      }
    });
  }

  if (cnn10OpenBtn) {
    cnn10OpenBtn.addEventListener("click", () => {
      showCnn10Panel();
      loadCnn10Episodes(true);
    });
  }

  if (cnn10MoreBtn) {
    cnn10MoreBtn.addEventListener("click", loadMoreCnn10Episodes);
  }

  if (cnn10CloseBtn) {
    cnn10CloseBtn.addEventListener("click", hideCnn10Panel);
  }

  if (cnn10Panel) {
    cnn10Panel.addEventListener("click", (e) => {
      if (e.target === cnn10Panel) hideCnn10Panel();
    });
  }

  ["start-time", "end-time", "youtube-url"].forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener("input", scheduleAutoScriptFill);
    el.addEventListener("change", scheduleAutoScriptFill);
  });

  const lessonTitleEl = document.getElementById("lesson-title");
  if (lessonTitleEl) {
    lessonTitleEl.addEventListener("input", () => {
      if (archiveTitle) archiveTitle.value = lessonTitleEl.value;
    });
  }
  if (archiveTitle) {
    archiveTitle.addEventListener("input", () => {
      const titleInput = document.getElementById("lesson-title");
      if (titleInput) titleInput.value = archiveTitle.value;
    });
  }

  const lessonScriptEl = document.getElementById("lesson-script");
  if (lessonScriptEl) {
    lessonScriptEl.addEventListener("input", () => {
      scriptAutoManaged = false;
    });
  }

  function getLessonScriptJa() {
    const el = document.getElementById("lesson-script-ja");
    return el ? el.value.trim() : "";
  }

  function setLessonScriptJa(value) {
    const el = document.getElementById("lesson-script-ja");
    if (el) el.value = value || "";
  }

  function getLessonScriptJaPairs() {
    const el = document.getElementById("lesson-script-ja-pairs");
    if (!el || !el.value.trim()) return [];
    try {
      const parsed = JSON.parse(el.value);
      return Array.isArray(parsed) ? parsed : [];
    } catch (_err) {
      return [];
    }
  }

  function setLessonScriptJaPairs(pairs) {
    const el = document.getElementById("lesson-script-ja-pairs");
    if (!el) return;
    const normalized = Array.isArray(pairs)
      ? pairs
          .map((item) => ({
            en: String(item?.en || "").trim(),
            ja: String(item?.ja || "").trim(),
          }))
          .filter((item) => item.en || item.ja)
      : [];
    el.value = JSON.stringify(normalized);
  }

  function getLessonScriptEs() {
    const el = document.getElementById("lesson-script-es");
    return el ? el.value.trim() : "";
  }

  function setLessonScriptEs(value) {
    const el = document.getElementById("lesson-script-es");
    if (el) el.value = value || "";
  }

  function getLessonScriptEsPairs() {
    const el = document.getElementById("lesson-script-es-pairs");
    if (!el || !el.value.trim()) return [];
    try {
      const parsed = JSON.parse(el.value);
      return Array.isArray(parsed) ? parsed : [];
    } catch (_err) {
      return [];
    }
  }

  function setLessonScriptEsPairs(pairs) {
    const el = document.getElementById("lesson-script-es-pairs");
    if (!el) return;
    const normalized = Array.isArray(pairs)
      ? pairs
          .map((item) => ({
            en: String(item?.en || "").trim(),
            ja: String(item?.ja || "").trim(),
          }))
          .filter((item) => item.en || item.ja)
      : [];
    el.value = JSON.stringify(normalized);
  }

  function currentTranslationLang() {
    return assistiveLang();
  }

  function getLessonTranslationText() {
    return currentTranslationLang() === "es" ? getLessonScriptEs() : getLessonScriptJa();
  }

  function getLessonTranslationPairs() {
    return currentTranslationLang() === "es" ? getLessonScriptEsPairs() : getLessonScriptJaPairs();
  }

  function setLessonTranslation(text, pairs) {
    if (currentTranslationLang() === "es") {
      setLessonScriptEs(text);
      setLessonScriptEsPairs(pairs);
    } else {
      setLessonScriptJa(text);
      setLessonScriptJaPairs(pairs);
    }
  }

  function splitScriptChunks(text) {
    const trimmed = String(text || "").trim();
    if (!trimmed) return [];
    const lines = trimmed.split(/\n/).map((part) => part.trim()).filter(Boolean);
    if (lines.length > 1) return lines;
    const sentences = trimmed.split(/(?<=[.!?])\s+/).map((part) => part.trim()).filter(Boolean);
    return sentences.length ? sentences : [trimmed];
  }

  function translationNeedsRealign(script) {
    const units = splitScriptChunks(script);
    const pairs = getLessonTranslationPairs();
    if (!units.length || !pairs.length || pairs.length !== units.length) return true;
    return pairs.some((pair, index) => String(pair.en || "").trim() !== units[index]);
  }

  function showScriptTranslatePanelStatus(message, isError) {
    if (!scriptTranslatePanelStatus) return;
    if (!message) {
      scriptTranslatePanelStatus.classList.add("hidden");
      scriptTranslatePanelStatus.textContent = "";
      return;
    }
    scriptTranslatePanelStatus.textContent = message;
    scriptTranslatePanelStatus.classList.toggle("border-red-100", Boolean(isError));
    scriptTranslatePanelStatus.classList.toggle("bg-red-50", Boolean(isError));
    scriptTranslatePanelStatus.classList.toggle("text-red-800", Boolean(isError));
    scriptTranslatePanelStatus.classList.toggle("border-amber-100", !isError);
    scriptTranslatePanelStatus.classList.toggle("bg-amber-50", !isError);
    scriptTranslatePanelStatus.classList.toggle("text-amber-800", !isError);
    scriptTranslatePanelStatus.classList.remove("hidden");
  }

  function getScriptTranslationRows(script, translation, pairs) {
    if (Array.isArray(pairs) && pairs.length) {
      return pairs
        .map((item) => ({
          en: String(item?.en || "").trim(),
          ja: String(item?.ja || "").trim(),
        }))
        .filter((item) => item.en || item.ja);
    }
    const units = splitScriptChunks(script);
    const jaChunks = splitScriptChunks(translation);
    return units.map((en, index) => ({
      en,
      ja: jaChunks.length === units.length ? jaChunks[index] : index === 0 ? translation : "",
    }));
  }

  function translationDocxFilename(title) {
    const safe = String(title || "")
      .replace(/[\\/:*?"<>|]/g, "")
      .replace(/\s+/g, "_")
      .slice(0, 40);
    return safe ? `原文と和訳_${safe}.docx` : "原文と和訳.docx";
  }

  async function downloadScriptTranslationWord() {
    const rows = getScriptTranslationRows(
      document.getElementById("lesson-script")?.value.trim() || "",
      getLessonTranslationText(),
      getLessonTranslationPairs()
    );
    if (!rows.length) {
      showScriptTranslatePanelStatus("原文と和訳がありません。先に和訳を作成してください。", true);
      return;
    }

    const classId = getSelectedClassId() || (lessonClassId && lessonClassId.value) || "";
    const title = document.getElementById("lesson-title")?.value.trim() || "";
    if (scriptTranslateDocxBtn) {
      scriptTranslateDocxBtn.disabled = true;
        scriptTranslateDocxBtn.textContent = t("exporting");
    }
    showScriptTranslatePanelStatus("Word ファイルを作成しています…", false);

    try {
      const res = await fetch("/news/admin/api/class/lesson/translate/docx", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          class_id: classId,
          title,
          pairs: rows,
        }),
      });
      const contentType = res.headers.get("content-type") || "";
      if (!res.ok || contentType.includes("application/json")) {
        let message = "Word の作成に失敗しました。";
        try {
          const data = await res.json();
          if (data && data.error) message = data.error;
        } catch (_err) {
          /* ignore */
        }
        throw new Error(message);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = translationDocxFilename(title);
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      showScriptTranslatePanelStatus("", false);
    } catch (err) {
      showScriptTranslatePanelStatus(err.message || "Word の作成に失敗しました。", true);
    } finally {
      if (scriptTranslateDocxBtn) {
        scriptTranslateDocxBtn.disabled = false;
        scriptTranslateDocxBtn.textContent = t("exportWord");
      }
    }
  }

  function renderScriptTranslationList(script, translation, pairs) {
    if (!scriptTranslateList) return;
    scriptTranslateList.innerHTML = "";
    const rows = getScriptTranslationRows(script, translation, pairs);

    const table = document.createElement("div");
    table.className = "overflow-hidden rounded-lg border border-teal-100/80 bg-white/80";

    const head = document.createElement("div");
    head.className = "grid grid-cols-2 border-b border-teal-100 bg-teal-50/70";
    const translationHeader =
      currentTranslationLang() === "es" ? t("translationColEs") : t("translationCol");
    head.innerHTML = `
      <p class="px-2.5 py-1.5 text-[10px] font-semibold tracking-wider text-slate-500">${t("original")}</p>
      <p class="px-2.5 py-1.5 text-[10px] font-semibold tracking-wider text-amber-800/80">${translationHeader}</p>`;
    table.appendChild(head);

    rows.forEach((row, index) => {
      const item = document.createElement("div");
      item.className =
        "grid grid-cols-2 items-stretch " +
        (index < rows.length - 1 ? "border-b border-teal-50" : "");
      const en = document.createElement("p");
      en.className = "border-r border-teal-50 px-2.5 py-2 leading-relaxed text-slate-800";
      en.textContent = row.en || t("noOriginal");
      const ja = document.createElement("p");
      ja.className = "px-2.5 py-2 leading-relaxed text-slate-700";
      ja.textContent = row.ja || (currentTranslationLang() === "es" ? t("noTranslationEs") : t("noTranslation"));
      item.append(en, ja);
      table.appendChild(item);
    });

    scriptTranslateList.appendChild(table);
  }

  function showScriptTranslatePanel() {
    if (!scriptTranslatePanel) return;
    scriptTranslatePanel.classList.remove("hidden");
    scriptTranslatePanel.classList.add("flex");
  }

  function hideScriptTranslatePanel() {
    if (!scriptTranslatePanel) return;
    scriptTranslatePanel.classList.add("hidden");
    scriptTranslatePanel.classList.remove("flex");
  }

  async function generateLessonScriptTranslation({ force = false } = {}) {
    const classId = getSelectedClassId() || (lessonClassId && lessonClassId.value);
    if (!classId) {
      throw new Error("クラスを選択または作成してください。");
    }
    const script = document.getElementById("lesson-script")?.value.trim() || "";
    if (!script) {
      throw new Error("文字起こし（スクリプト）を入力してから和訳を作成してください。");
    }
    if (!force && !translationNeedsRealign(script)) {
      return { script_translation: getLessonTranslationText(), pairs: getLessonTranslationPairs() };
    }

    const res = await fetch("/news/admin/api/class/lesson/translate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ class_id: classId, script, target_lang: currentTranslationLang() }),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || t("translationFail"));
    const translationText = data.script_translation || "";
    const pairs = data.pairs || [];
    setLessonTranslation(translationText, pairs);
    if (data.script_ja != null) setLessonScriptJa(data.script_ja);
    if (data.script_ja_pairs) setLessonScriptJaPairs(data.script_ja_pairs);
    if (data.script_es != null) setLessonScriptEs(data.script_es);
    if (data.script_es_pairs) setLessonScriptEsPairs(data.script_es_pairs);
    return { script_translation: translationText, pairs };
  }

  async function openScriptTranslationPopup({ force = false } = {}) {
    const script = document.getElementById("lesson-script")?.value.trim() || "";
    if (!script) {
      showMessage(lessonMessage, "文字起こし（スクリプト）を入力してから和訳を作成してください。", true);
      return;
    }

    showScriptTranslatePanel();
    renderScriptTranslationList(script, getLessonTranslationText(), getLessonTranslationPairs());
    const needsGenerate = force || translationNeedsRealign(script);
    const isEs = currentTranslationLang() === "es";
    if (scriptTranslateBtn) {
      scriptTranslateBtn.disabled = true;
      scriptTranslateBtn.textContent = needsGenerate ? t("creatingTranslation") : t("scriptAndTranslation");
    }
    if (scriptTranslateRetryBtn) scriptTranslateRetryBtn.disabled = true;
    if (scriptTranslateDocxBtn) scriptTranslateDocxBtn.disabled = needsGenerate;
    if (scriptTranslateStatus) {
      scriptTranslateStatus.textContent = needsGenerate ? (isEs ? t("translatingEs") : t("translating")) : "";
      scriptTranslateStatus.classList.toggle("hidden", !needsGenerate);
    }
    showScriptTranslatePanelStatus(
      needsGenerate ? (isEs ? t("translatingWaitEs") : t("translatingWait")) : "",
      false
    );

    try {
      const translation = await generateLessonScriptTranslation({ force });
      renderScriptTranslationList(script, translation.script_translation, translation.pairs);
      showScriptTranslatePanelStatus("", false);
      if (needsGenerate) {
        showMessage(lessonMessage, isEs ? t("translationDoneEs") : t("translationDone"), false);
      }
      if (scriptTranslateStatus) scriptTranslateStatus.classList.add("hidden");
    } catch (err) {
      showScriptTranslatePanelStatus(err.message || (isEs ? t("translationFailEs") : t("translationFail")), true);
      showMessage(lessonMessage, err.message, true);
      if (scriptTranslateStatus) {
        scriptTranslateStatus.textContent = isEs ? t("translationFailEs") : t("translationFail");
        scriptTranslateStatus.classList.remove("hidden");
      }
    } finally {
      if (scriptTranslateBtn) {
        scriptTranslateBtn.disabled = false;
        scriptTranslateBtn.textContent = t("scriptAndTranslation");
      }
      if (scriptTranslateRetryBtn) scriptTranslateRetryBtn.disabled = false;
      if (scriptTranslateDocxBtn) scriptTranslateDocxBtn.disabled = false;
    }
  }

  function esc(str) {
    return String(str || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function scoreOnlyFeedback(feedback) {
    const text = String(feedback || "").trim();
    const start = text.indexOf("項目別評価点");
    if (start < 0) return text;
    const rest = text.slice(start);
    const nextHeading = rest.search(/\n\s*(要点チェックとキーワードチェック|文法・構成アドバイス|【AIからの模範要約】|今回の要約スピーチへのアドバイス|今回の要約スピーチ文の改良例)/);
    return (nextHeading >= 0 ? rest.slice(0, nextHeading) : rest).trim();
  }

  async function loadLessonFilterOptions() {
    if (!resultsLessonFilter) return;
    const classId = resultsClassFilter ? resultsClassFilter.value : "";
    resultsLessonFilter.innerHTML = "";
    if (!classId) {
      resultsLessonFilter.disabled = true;
      resultsLessonFilter.innerHTML = '<option value="">先にクラスを選択</option>';
      return;
    }
    resultsLessonFilter.disabled = false;
    resultsLessonFilter.innerHTML = '<option value="">すべての動画</option>';
    try {
      const res = await fetch(`/news/admin/api/class/lessons?class_id=${encodeURIComponent(classId)}`);
      const data = await res.json();
      (data.lessons || []).forEach((lesson) => {
        const opt = document.createElement("option");
        opt.value = lesson.key || "";
        opt.textContent = lesson.title || "未分類";
        resultsLessonFilter.appendChild(opt);
      });
    } catch (err) {
      console.error("動画タイトルの取得に失敗:", err);
    }
  }

  async function loadResults() {
    if (!resultsTbody || !resultsTable || !resultsEmpty) return;
    const classId = resultsClassFilter ? resultsClassFilter.value : "";
    const lessonKey = resultsLessonFilter && !resultsLessonFilter.disabled ? resultsLessonFilter.value : "";
    const params = new URLSearchParams();
    if (classId) params.set("class_id", classId);
    if (lessonKey) params.set("lesson_key", lessonKey);
    const url = params.toString() ? `/news/admin/api/submissions?${params.toString()}` : "/news/admin/api/submissions";
    try {
      const res = await fetch(url);
      const data = await res.json();
      latestSubmissions = data.submissions || [];
      renderResults(latestSubmissions);
    } catch (err) {
      console.error("結果の取得に失敗:", err);
    }
  }

  function renderResults(submissions) {
    submissions = sortSubmissions(submissions);
    allResultsSelected = false;
    resultsTbody.innerHTML = "";
    updateBulkDeleteState();
    if (!submissions.length) {
      resultsTable.classList.add("hidden");
      resultsEmpty.classList.remove("hidden");
      return;
    }
    resultsTable.classList.remove("hidden");
    resultsEmpty.classList.add("hidden");

    submissions.forEach((submission) => {
      const tr = document.createElement("tr");
      const dt = submission.submitted_at ? new Date(submission.submitted_at).toLocaleString("ja-JP") : "";
      tr.innerHTML = `
        <td class="py-1 pr-2 text-center">
          <input type="checkbox" class="submission-select h-3.5 w-3.5 rounded border-teal-200 text-teal-600" data-id="${esc(submission.id)}">
        </td>
        <td class="py-1 pr-2 whitespace-nowrap text-slate-500">${esc(dt)}</td>
        <td class="py-1 pr-2">${esc(submission.class_name)}</td>
        <td class="py-1 pr-2">${esc(submission.student_hr_class)}</td>
        <td class="py-1 pr-2">${esc(submission.student_number)}</td>
        <td class="py-1 pr-2 font-medium">${esc(submission.student_name)}</td>
        <td class="py-1 pr-2">${esc(submission.lesson_title || "未分類")}</td>
        <td class="py-1 pr-2 text-center font-semibold text-slate-700">${esc(submission.content_score)}</td>
        <td class="py-1 pr-2 text-center font-semibold text-slate-700">${esc(submission.organization_score)}</td>
        <td class="py-1 pr-2 text-center font-semibold text-slate-700">${esc(submission.language_score)}</td>
        <td class="py-1 pr-2 text-center font-semibold text-slate-700">${esc(submission.speaking_summary_score)}</td>
        <td class="py-1 pr-2 text-center font-bold text-teal-700">${esc(submission.total_score)}</td>
        <td class="py-1 pr-2">${esc(submission.level)}</td>
        <td class="py-1 pr-2 align-top">
          <div class="max-h-32 overflow-y-auto whitespace-pre-wrap rounded bg-white/45 p-1">${esc(submission.transcript)}</div>
        </td>
        <td class="py-1 pr-2 align-top text-slate-600">
          <div class="max-h-40 overflow-y-auto whitespace-pre-wrap rounded bg-white/45 p-1">${esc(scoreOnlyFeedback(submission.feedback))}</div>
        </td>
        <td class="py-1">
          <div class="flex items-center gap-2 whitespace-nowrap">
            <button type="button" data-id="${esc(submission.id)}"
              class="pdf-submission-btn text-[10px] font-semibold text-emerald-600 hover:text-emerald-700">PDF</button>
            <button type="button" data-id="${esc(submission.id)}"
              class="del-submission-btn text-[10px] text-red-400 hover:text-red-600">削除</button>
          </div>
        </td>`;
      resultsTbody.appendChild(tr);
    });
    updateBulkDeleteState();
  }

  function getSubmissionCheckboxes() {
    return resultsTbody ? Array.from(resultsTbody.querySelectorAll(".submission-select")) : [];
  }

  function updateBulkDeleteState() {
    const boxes = getSubmissionCheckboxes();
    const selectedCount = boxes.filter((box) => box.checked).length;
    if (resultsSelectAllBtn) {
      resultsSelectAllBtn.disabled = boxes.length === 0;
      allResultsSelected = boxes.length > 0 && selectedCount === boxes.length;
      resultsSelectAllBtn.textContent = allResultsSelected ? "選択解除" : "全て選択";
    }
    if (resultsDeleteSelectedBtn) {
      resultsDeleteSelectedBtn.disabled = selectedCount === 0;
      resultsDeleteSelectedBtn.textContent = selectedCount ? `選択削除（${selectedCount}件）` : "選択削除";
    }
    if (resultsPdfSelectedBtn) {
      resultsPdfSelectedBtn.disabled = selectedCount === 0;
      resultsPdfSelectedBtn.textContent = selectedCount
        ? `PDF個票ダウンロード（${selectedCount}件）`
        : "PDF個票ダウンロード";
    }
  }

  function normalizeNumber(value) {
    const number = parseInt(String(value || "").replace(/[^\d]/g, ""), 10);
    return Number.isFinite(number) ? number : 999999;
  }

  function sortSubmissions(submissions) {
    const key = resultsSortKey ? resultsSortKey.value : "submitted_at";
    const direction = resultsSortDirection ? resultsSortDirection.dataset.direction || "desc" : "desc";
    const multiplier = direction === "asc" ? 1 : -1;
    return [...submissions].sort((a, b) => {
      if (key === "student_number") {
        return (normalizeNumber(a.student_number) - normalizeNumber(b.student_number)) * multiplier;
      }
      const aValue = String(a[key] || "");
      const bValue = String(b[key] || "");
      return aValue.localeCompare(bValue, "ja", { numeric: true }) * multiplier;
    });
  }

  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tab = btn.dataset.tab;
      document.querySelectorAll(".tab-btn").forEach((b) => {
        const active = b === btn;
        b.classList.toggle("tab-btn--active", active);
        b.classList.toggle("tab-btn--inactive", !active);
      });
      if (tabLesson) tabLesson.classList.toggle("hidden", tab !== "lesson");
      if (tabResults) tabResults.classList.toggle("hidden", tab !== "results");
      if (tab === "results") loadResults();
    });
  });

  if (resultsLoadBtn) {
    resultsLoadBtn.addEventListener("click", loadResults);
  }

  if (resultsClassFilter) {
    resultsClassFilter.addEventListener("change", async () => {
      await loadLessonFilterOptions();
      loadResults();
    });
  }

  if (resultsLessonFilter) {
    resultsLessonFilter.addEventListener("change", loadResults);
  }

  if (resultsSortKey) {
    resultsSortKey.addEventListener("change", () => renderResults(latestSubmissions));
  }

  if (resultsSortDirection) {
    resultsSortDirection.addEventListener("click", () => {
      const next = resultsSortDirection.dataset.direction === "asc" ? "desc" : "asc";
      resultsSortDirection.dataset.direction = next;
      resultsSortDirection.textContent = next === "asc" ? "昇順" : "降順";
      renderResults(latestSubmissions);
    });
  }

  if (resultsSelectAllBtn) {
    resultsSelectAllBtn.addEventListener("click", () => {
      const boxes = getSubmissionCheckboxes();
      const nextChecked = !allResultsSelected;
      boxes.forEach((box) => {
        box.checked = nextChecked;
      });
      updateBulkDeleteState();
    });
  }

  if (resultsDeleteSelectedBtn) {
    resultsDeleteSelectedBtn.addEventListener("click", async () => {
      const ids = getSubmissionCheckboxes()
        .filter((box) => box.checked)
        .map((box) => box.dataset.id)
        .filter(Boolean);
      if (!ids.length) return;
      if (!confirm(`選択した${ids.length}件の提出データを削除しますか？`)) return;
      resultsDeleteSelectedBtn.disabled = true;
      try {
        await Promise.all(
          ids.map((id) => fetch(`/news/admin/api/submissions/${encodeURIComponent(id)}`, { method: "DELETE" }))
        );
        loadResults();
      } catch (err) {
        alert("削除に失敗しました。もう一度試してください。");
        updateBulkDeleteState();
      }
    });
  }

  if (resultsPdfSelectedBtn) {
    resultsPdfSelectedBtn.addEventListener("click", async () => {
      const ids = getSubmissionCheckboxes()
        .filter((box) => box.checked)
        .map((box) => box.dataset.id)
        .filter(Boolean);
      if (!ids.length) return;

      resultsPdfSelectedBtn.disabled = true;
      resultsPdfSelectedBtn.textContent =
        ids.length >= 5 ? `PDF生成中（${ids.length}件）…` : "PDF生成中…";
      try {
        const res = await fetch("/news/admin/api/submissions/pdf", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ids }),
        });
        if (!res.ok) {
          let message = "PDFの生成に失敗しました。";
          try {
            const data = await res.json();
            if (data && data.error) message = data.error;
          } catch (_) {
            /* ignore */
          }
          throw new Error(message);
        }
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `vibe_speak_news_reports_${ids.length}.pdf`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
      } catch (err) {
        alert(err && err.message ? err.message : "PDFの生成に失敗しました。");
      } finally {
        updateBulkDeleteState();
      }
    });
  }

  if (resultsTbody) {
    resultsTbody.addEventListener("click", async (e) => {
      if (e.target.closest(".submission-select")) {
        updateBulkDeleteState();
        return;
      }
      const pdfBtn = e.target.closest(".pdf-submission-btn");
      if (pdfBtn) {
        const id = pdfBtn.dataset.id;
        if (!id) return;
        if (!confirm("この生徒の帳票をPDFで出力しますか？")) return;
        const originalLabel = pdfBtn.textContent;
        pdfBtn.disabled = true;
        pdfBtn.textContent = "生成中…";
        try {
          const res = await fetch(`/news/admin/api/submissions/${encodeURIComponent(id)}/pdf`);
          if (!res.ok) {
            let message = "PDFの生成に失敗しました。";
            try {
              const data = await res.json();
              if (data && data.error) message = data.error;
            } catch (_) {
              /* ignore */
            }
            throw new Error(message);
          }
          const blob = await res.blob();
          const url = URL.createObjectURL(blob);
          const opened = window.open(url, "_blank", "noopener,noreferrer");
          if (!opened) {
            const a = document.createElement("a");
            a.href = url;
            a.download = `vibe_speak_news_${id}.pdf`;
            document.body.appendChild(a);
            a.click();
            a.remove();
          }
          setTimeout(() => URL.revokeObjectURL(url), 60_000);
        } catch (err) {
          alert(err && err.message ? err.message : "PDFの生成に失敗しました。");
        } finally {
          pdfBtn.disabled = false;
          pdfBtn.textContent = originalLabel || "PDF";
        }
        return;
      }
      const btn = e.target.closest(".del-submission-btn");
      if (!btn) return;
      if (!confirm("この提出データを削除しますか？")) return;
      await fetch(`/news/admin/api/submissions/${encodeURIComponent(btn.dataset.id)}`, { method: "DELETE" });
      loadResults();
    });
  }

  if (resultsExportBtn) {
    resultsExportBtn.addEventListener("click", () => {
      const classId = resultsClassFilter ? resultsClassFilter.value : "";
      const lessonKey = resultsLessonFilter && !resultsLessonFilter.disabled ? resultsLessonFilter.value : "";
      const params = new URLSearchParams();
      if (classId) params.set("class_id", classId);
      if (lessonKey) params.set("lesson_key", lessonKey);
      window.location.href = params.toString()
        ? `/news/admin/api/submissions/export?${params.toString()}`
        : "/news/admin/api/submissions/export";
    });
  }

  if (rosterUploadBtn) {
    rosterUploadBtn.addEventListener("click", async () => {
      const classId = classSelect ? classSelect.value : "";
      if (!classId) {
        showMessage(rosterMessage, "先にクラスを選択してください。", true);
        return;
      }
      if (!rosterFileInput || !rosterFileInput.files.length) {
        showMessage(rosterMessage, "ファイルを選択してください。", true);
        return;
      }

      const form = new FormData();
      form.append("class_id", classId);
      form.append("file", rosterFileInput.files[0]);

      try {
        const res = await fetch("/news/admin/api/roster/upload", { method: "POST", body: form });
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || "アップロードに失敗しました。");
        showMessage(rosterMessage, `✓ ${data.count} 件の名簿を登録しました。`, false);
      } catch (err) {
        showMessage(rosterMessage, err.message, true);
      }
    });
  }

  // ── 語彙補助（Scaffolding）──────────────────────────────────────

  function countSelectedVocab(items) {
    return (items || []).filter((item) => item.selected !== false).length;
  }

  function nextWarmupQuestionId() {
    const ids = adminWarmupQuestions.map((q) => Number(q.id)).filter((id) => Number.isFinite(id));
    return ids.length ? Math.max(...ids) + 1 : 1;
  }

  function getManualWarmupQuestions() {
    return adminWarmupQuestions.filter((q) => q.manual);
  }

  function getAiWarmupQuestions() {
    return adminWarmupQuestions.filter((q) => !q.manual);
  }

  function ensureManualWarmupRow() {
    if (!getManualWarmupQuestions().length) {
      adminWarmupQuestions.push({
        id: nextWarmupQuestionId(),
        text: "",
        selected: true,
        manual: true,
      });
    }
  }

  function scheduleWarmupManualSave() {
    if (warmupManualSaveTimer) clearTimeout(warmupManualSaveTimer);
    warmupManualSaveTimer = setTimeout(() => {
      warmupManualSaveTimer = null;
      saveWarmupSelection({ silent: true });
    }, 700);
  }

  function renderAdminVocabPreview(items) {
    if (!vocabPreview) return;
    adminVocabItems = (items || []).map((item) => ({
      word: item.word || "",
      cefr: item.cefr || "",
      part_of_speech: item.part_of_speech || "",
      meaning: item.meaning || "",
      meaning_es: item.meaning_es || "",
      selected: item.selected !== false,
    }));
    if (!adminVocabItems.length) {
      vocabPreview.classList.add("hidden");
      return;
    }
    const selectedCount = countSelectedVocab(adminVocabItems);
    const isEs = currentTranslationLang() === "es";
    let html = `<p class="mb-1.5 font-semibold text-slate-600">${t("vocabPreview", { selected: selectedCount, total: adminVocabItems.length })}</p>`;
    html += `<p class="mb-1 text-[9px] text-slate-500">${t("vocabPreviewHint")}</p>`;
    html += `<div class="space-y-px">`;
    adminVocabItems.forEach((item, i) => {
      const rowBg = i % 2 === 0 ? "bg-white/70" : "";
      const dimClass = item.selected ? "" : " opacity-50";
      const meaning = isEs ? (item.meaning_es || item.meaning) : (item.meaning || item.meaning_es);
      html += `<label class="flex items-start gap-2 rounded px-1.5 py-1 ${rowBg}${dimClass} cursor-pointer">
        <input type="checkbox" class="vocab-select-cb shrink-0 mt-0.5 h-3.5 w-3.5 rounded border-violet-200 text-violet-600"
          data-index="${i}" ${item.selected ? "checked" : ""}>
        <span class="shrink-0 w-28 font-semibold text-slate-800 leading-snug">${esc(item.word)}</span>
        <span class="shrink-0 w-8 text-violet-500 leading-snug">${esc(item.cefr)}</span>
        <span class="shrink-0 w-12 text-slate-400 leading-snug">${esc(mapPos(item.part_of_speech))}</span>
        <span class="text-slate-600 leading-snug">${esc(meaning)}</span>
      </label>`;
    });
    html += `</div>`;
    vocabPreview.innerHTML = html;
    vocabPreview.classList.remove("hidden");

    vocabPreview.querySelectorAll(".vocab-select-cb").forEach((cb) => {
      cb.addEventListener("change", onVocabSelectionChange);
    });
  }

  async function saveVocabSelection(options) {
    const silent = options && options.silent;
    const classId = getSelectedClassId() || (lessonClassId && lessonClassId.value);
    if (!classId || !adminVocabItems.length) return true;

    vocabSelectionSaving = true;
    try {
      const res = await fetch("/news/admin/api/class/lesson/vocabulary/selection", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ class_id: classId, vocabulary_data: adminVocabItems }),
      });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || "保存に失敗しました");
      adminVocabItems = (data.vocabulary_data || adminVocabItems).map((item) => ({
        word: item.word || "",
        cefr: item.cefr || "",
        part_of_speech: item.part_of_speech || "",
        meaning: item.meaning || "",
        meaning_es: item.meaning_es || "",
        selected: item.selected !== false,
      }));
      renderAdminVocabPreview(adminVocabItems);
      if (!silent) {
        showMessage(lessonMessage, data.message || "語彙の表示設定を保存しました。", false);
      }
      return true;
    } catch (err) {
      if (!silent) showMessage(lessonMessage, err.message, true);
      return false;
    } finally {
      vocabSelectionSaving = false;
    }
  }

  async function onVocabSelectionChange(event) {
    if (vocabSelectionSaving) {
      event.target.checked = !event.target.checked;
      return;
    }
    const index = Number(event.target.dataset.index);
    if (!Number.isInteger(index) || !adminVocabItems[index]) return;

    const previous = adminVocabItems[index].selected;
    adminVocabItems[index].selected = event.target.checked;
    renderAdminVocabPreview(adminVocabItems);

    const ok = await saveVocabSelection({ silent: true });
    if (!ok) {
      adminVocabItems[index].selected = previous;
      renderAdminVocabPreview(adminVocabItems);
      showMessage(lessonMessage, "語彙の表示設定の保存に失敗しました。", true);
    }
  }

  if (vocabScaffoldingEnabledEl) {
    vocabScaffoldingEnabledEl.addEventListener("change", async () => {
      const classId = getSelectedClassId() || (lessonClassId && lessonClassId.value);
      if (!classId) {
        showMessage(lessonMessage, "クラスを選択してから操作してください。", true);
        vocabScaffoldingEnabledEl.checked = !vocabScaffoldingEnabledEl.checked;
        return;
      }
      const enabled = vocabScaffoldingEnabledEl.checked;
      try {
        const res = await fetch("/news/admin/api/class/lesson/vocabulary/toggle", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ class_id: classId, vocabulary_scaffolding_enabled: enabled }),
        });
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || "保存に失敗しました");
        showMessage(lessonMessage, data.message || "語彙補助の設定を保存しました。", false);
      } catch (err) {
        showMessage(lessonMessage, err.message, true);
        vocabScaffoldingEnabledEl.checked = !enabled;
      }
    });
  }

  if (scriptTranslateBtn) {
    scriptTranslateBtn.addEventListener("click", () => {
      openScriptTranslationPopup({ force: false });
    });
  }
  if (scriptTranslateRetryBtn) {
    scriptTranslateRetryBtn.addEventListener("click", () => {
      openScriptTranslationPopup({ force: true });
    });
  }
  if (scriptTranslateDocxBtn) {
    scriptTranslateDocxBtn.addEventListener("click", () => {
      downloadScriptTranslationWord();
    });
  }
  if (scriptTranslateCloseBtn) {
    scriptTranslateCloseBtn.addEventListener("click", hideScriptTranslatePanel);
  }
  if (scriptTranslatePanel) {
    scriptTranslatePanel.addEventListener("click", (e) => {
      if (e.target === scriptTranslatePanel) hideScriptTranslatePanel();
    });
  }

  if (vocabExtractBtn) {
    vocabExtractBtn.addEventListener("click", async () => {
      const classId = getSelectedClassId() || (lessonClassId && lessonClassId.value);
      if (!classId) {
        showMessage(lessonMessage, "クラスを選択または作成してください。", true);
        return;
      }
      const script = document.getElementById("lesson-script")?.value.trim() || "";
      if (!script) {
        showMessage(lessonMessage, "スクリプトを入力してから語彙を抽出してください。", true);
        return;
      }

      vocabExtractBtn.disabled = true;
      vocabExtractBtn.textContent = t("extracting");
      if (vocabExtractStatus) {
        vocabExtractStatus.textContent = t("extractingVocab");
        vocabExtractStatus.classList.remove("hidden");
      }
      if (vocabPreview) vocabPreview.classList.add("hidden");

      try {
        const res = await fetch("/news/admin/api/class/lesson/vocabulary", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            class_id: classId,
            script,
            min_cefr: vocabMinCefrEl?.value || "B1",
          }),
        });
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || "語彙抽出に失敗しました");
        renderAdminVocabPreview(data.vocabulary_data || []);
        showMessage(lessonMessage, data.message || "語彙を抽出しました。", false);
        if (vocabExtractStatus) vocabExtractStatus.classList.add("hidden");
      } catch (err) {
        showMessage(lessonMessage, err.message, true);
        if (vocabExtractStatus) {
          vocabExtractStatus.textContent = t("extractFail");
        }
      } finally {
        vocabExtractBtn.disabled = false;
        vocabExtractBtn.textContent = t("aiExtract");
      }
    });
  }

  if (vocabManualAddBtn) {
    vocabManualAddBtn.addEventListener("click", async () => {
      const word = vocabManualWord?.value.trim() || "";
      const meaning = vocabManualMeaning?.value.trim() || "";
      const partOfSpeech = vocabManualPos?.value.trim() || "";
      const cefr = vocabManualCefr?.value || "B1";
      if (!word) {
        showMessage(lessonMessage, "単語を入力してください。", true);
        vocabManualWord?.focus();
        return;
      }
      if (!meaning) {
        showMessage(lessonMessage, "意味を入力してください。", true);
        vocabManualMeaning?.focus();
        return;
      }
      if (currentTranslationLang() === "es") {
        adminVocabItems.push({
          word,
          cefr,
          part_of_speech: partOfSpeech,
          meaning: "",
          meaning_es: meaning,
          selected: true,
        });
      } else {
        adminVocabItems.push({
          word,
          cefr,
          part_of_speech: partOfSpeech,
          meaning,
          meaning_es: "",
          selected: true,
        });
      }
      if (vocabManualWord) vocabManualWord.value = "";
      if (vocabManualPos) vocabManualPos.value = "";
      if (vocabManualMeaning) vocabManualMeaning.value = "";
      renderAdminVocabPreview(adminVocabItems);
      const ok = await saveVocabSelection({ silent: false });
      if (!ok) {
        adminVocabItems.pop();
        renderAdminVocabPreview(adminVocabItems);
      }
    });
  }

  // ── 導入補助（Warmup Scaffolding） ─────────────────────────────

  function renderWarmupManualRows() {
    if (!warmupManualRows) return;
    ensureManualWarmupRow();
    const manualQuestions = getManualWarmupQuestions();
    let html = "";
    manualQuestions.forEach((q) => {
      const index = adminWarmupQuestions.indexOf(q);
      const dimClass = q.selected ? "" : " opacity-50";
      html += `<label class="flex items-center gap-1 rounded px-1 py-0.5 bg-white/70${dimClass} cursor-pointer">
        <input type="checkbox" class="warmup-manual-select-cb shrink-0 h-3.5 w-3.5 rounded border-sky-200 text-sky-600"
          data-index="${index}" ${q.selected ? "checked" : ""}>
        <span class="shrink-0 text-[9px] font-bold text-sky-600">Q${q.id}</span>
        <input type="text" class="warmup-manual-input compact-input min-w-0 flex-1 text-[10px] py-0.5"
          data-index="${index}" value="${esc(q.text)}" placeholder="質問（英語）">
      </label>`;
    });
    warmupManualRows.innerHTML = html;

    warmupManualRows.querySelectorAll(".warmup-manual-select-cb").forEach((cb) => {
      cb.addEventListener("change", onWarmupSelectionChange);
    });
    warmupManualRows.querySelectorAll(".warmup-manual-input").forEach((input) => {
      input.addEventListener("input", onWarmupManualInputChange);
      input.addEventListener("blur", () => saveWarmupSelection({ silent: true }));
    });
  }

  function onWarmupManualInputChange(event) {
    const index = Number(event.target.dataset.index);
    if (!Number.isInteger(index) || !adminWarmupQuestions[index]) return;
    adminWarmupQuestions[index].text = event.target.value;
    scheduleWarmupManualSave();
  }

  function addManualWarmupRow() {
    adminWarmupQuestions.push({
      id: nextWarmupQuestionId(),
      text: "",
      selected: true,
      manual: true,
    });
    renderWarmupManualRows();
    const inputs = warmupManualRows?.querySelectorAll(".warmup-manual-input") || [];
    const lastInput = inputs[inputs.length - 1];
    if (lastInput) lastInput.focus();
  }

  if (warmupAddQuestionBtn) {
    warmupAddQuestionBtn.addEventListener("click", addManualWarmupRow);
  }

  function renderAdminWarmupPreview(imageUrl, questions) {
    if (typeof imageUrl === "string") {
      adminWarmupImageUrl = imageUrl;
    }
    const incoming = (questions || []).map(function (q) {
      return {
        id: q.id,
        text: q.text || "",
        selected: q.selected !== false,
        manual: q.manual === true,
      };
    });
    const manualFromState = incoming.length
      ? incoming.filter((q) => q.manual)
      : getManualWarmupQuestions();
    const aiFromState = incoming.filter((q) => !q.manual);
    adminWarmupQuestions = [...aiFromState, ...manualFromState];

    const aiQuestions = getAiWarmupQuestions();
    if (!warmupPreview) {
      renderWarmupManualRows();
      return;
    }
    if (!adminWarmupImageUrl && !aiQuestions.length) {
      warmupPreview.classList.add("hidden");
      renderWarmupManualRows();
      return;
    }
    const selectedCount = aiQuestions.filter(function (q) { return q.selected; }).length;
    let html = "";
    if (adminWarmupImageUrl) {
      html += `<div class="mb-2"><img src="${esc(adminWarmupImageUrl)}" alt="Warmup illustration"
        class="w-full max-h-48 rounded-lg object-contain border border-slate-100 bg-slate-50"></div>`;
    }
    if (aiQuestions.length) {
      html += `<p class="mb-1 font-semibold text-slate-600">AI生成の導入質問（表示 ${selectedCount} / ${aiQuestions.length} 問）</p>`;
      html += `<p class="mb-1 text-[9px] text-slate-500">チェックを外した質問は生徒画面に表示されません。</p>`;
      html += `<div class="space-y-1">`;
      aiQuestions.forEach(function (q) {
        const index = adminWarmupQuestions.indexOf(q);
        const dimClass = q.selected ? "" : " opacity-50";
        html += `<label class="flex items-start gap-2 rounded px-1.5 py-1 ${index % 2 === 0 ? "bg-white/70" : ""}${dimClass} cursor-pointer">
          <input type="checkbox" class="warmup-select-cb shrink-0 mt-0.5 h-3.5 w-3.5 rounded border-sky-200 text-sky-600"
            data-index="${index}" ${q.selected ? "checked" : ""}>
          <span class="shrink-0 mr-1 text-sky-600 font-bold">Q${q.id}.</span>
          <span class="text-slate-700 leading-snug">${esc(q.text)}</span>
        </label>`;
      });
      html += `</div>`;
    }
    warmupPreview.innerHTML = html;
    warmupPreview.classList.remove("hidden");
    warmupPreview.querySelectorAll(".warmup-select-cb").forEach(function (cb) {
      cb.addEventListener("change", onWarmupSelectionChange);
    });
    renderWarmupManualRows();
  }

  async function saveWarmupSelection(options) {
    const silent = options && options.silent;
    const classId = getSelectedClassId() || (lessonClassId && lessonClassId.value);
    if (!classId) return true;
    const questionsToSave = adminWarmupQuestions.filter((q) => (q.text || "").trim());
    if (!questionsToSave.length) return true;
    warmupSelectionSaving = true;
    try {
      const res = await fetch("/news/admin/api/class/lesson/warmup/selection", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ class_id: classId, warmup_questions: questionsToSave }),
      });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || "保存に失敗しました");
      const savedManual = getManualWarmupQuestions();
      const savedFromServer = (data.warmup_questions || questionsToSave).map(function (q) {
        return {
          id: q.id,
          text: q.text || "",
          selected: q.selected !== false,
          manual: q.manual === true,
        };
      });
      const serverManual = savedFromServer.filter((q) => q.manual);
      const serverAi = savedFromServer.filter((q) => !q.manual);
      const draftManual = savedManual.filter((q) => !(q.text || "").trim());
      adminWarmupQuestions = [...serverAi, ...serverManual, ...draftManual];
      if (!silent) {
        renderAdminWarmupPreview(adminWarmupImageUrl, adminWarmupQuestions);
        showMessage(lessonMessage, data.message || "質問の表示設定を保存しました。", false);
      }
      return true;
    } catch (err) {
      if (!silent) showMessage(lessonMessage, err.message, true);
      return false;
    } finally {
      warmupSelectionSaving = false;
    }
  }

  async function onWarmupSelectionChange(event) {
    if (warmupSelectionSaving) {
      event.target.checked = !event.target.checked;
      return;
    }
    const index = Number(event.target.dataset.index);
    if (!Number.isInteger(index) || !adminWarmupQuestions[index]) return;
    const previous = adminWarmupQuestions[index].selected;
    adminWarmupQuestions[index].selected = event.target.checked;
    renderAdminWarmupPreview(adminWarmupImageUrl, adminWarmupQuestions);
    const ok = await saveWarmupSelection({ silent: true });
    if (!ok) {
      adminWarmupQuestions[index].selected = previous;
      renderAdminWarmupPreview(adminWarmupImageUrl, adminWarmupQuestions);
      showMessage(lessonMessage, "質問の表示設定の保存に失敗しました。", true);
    }
  }

  if (warmupScaffoldingEnabledEl) {
    warmupScaffoldingEnabledEl.addEventListener("change", async function () {
      const classId = getSelectedClassId() || (lessonClassId && lessonClassId.value);
      if (!classId) {
        showMessage(lessonMessage, "クラスを選択してから操作してください。", true);
        warmupScaffoldingEnabledEl.checked = !warmupScaffoldingEnabledEl.checked;
        return;
      }
      const enabled = warmupScaffoldingEnabledEl.checked;
      try {
        const res = await fetch("/news/admin/api/class/lesson/warmup/toggle", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ class_id: classId, warmup_scaffolding_enabled: enabled }),
        });
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || "保存に失敗しました");
        showMessage(lessonMessage, data.message || "導入補助の設定を保存しました。", false);
      } catch (err) {
        showMessage(lessonMessage, err.message, true);
        warmupScaffoldingEnabledEl.checked = !enabled;
      }
    });
  }

  if (warmupGenerateBtn) {
    warmupGenerateBtn.addEventListener("click", async function () {
      const classId = getSelectedClassId() || (lessonClassId && lessonClassId.value);
      if (!classId) {
        showMessage(lessonMessage, "クラスを選択または作成してください。", true);
        return;
      }
      const script = document.getElementById("lesson-script") ? document.getElementById("lesson-script").value.trim() : "";
      if (!script) {
        showMessage(lessonMessage, "スクリプトを入力してから生成してください。", true);
        return;
      }
      warmupGenerateBtn.disabled = true;
      warmupGenerateBtn.textContent = "生成中…";
      if (warmupGenerateStatus) {
        warmupGenerateStatus.textContent = "AI がイラストと質問を生成中です（15〜30秒かかります）…";
        warmupGenerateStatus.classList.remove("hidden");
      }
      if (warmupPreview) warmupPreview.classList.add("hidden");
      try {
        const res = await fetch("/news/admin/api/class/lesson/warmup", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ class_id: classId, script }),
        });
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || "生成に失敗しました");
        const preservedManual = getManualWarmupQuestions();
        const aiQuestions = (data.warmup_questions || []).map((q) => ({
          id: q.id,
          text: q.text || "",
          selected: q.selected !== false,
          manual: false,
        }));
        renderAdminWarmupPreview(data.warmup_image_url || "", [...aiQuestions, ...preservedManual]);
        showMessage(lessonMessage, data.message || "導入補助を生成しました。", false);
        if (warmupGenerateStatus) warmupGenerateStatus.classList.add("hidden");
      } catch (err) {
        showMessage(lessonMessage, err.message, true);
        if (warmupGenerateStatus) {
          warmupGenerateStatus.textContent = "⚠ 生成に失敗しました。";
        }
      } finally {
        warmupGenerateBtn.disabled = false;
        warmupGenerateBtn.textContent = "🎨 AI生成";
      }
    });
  }

  // ── 事後質問（視聴後） ──────────────────────────────────────────

  function nextPostviewQuestionId() {
    const ids = adminPostviewQuestions.map((q) => Number(q.id)).filter((id) => Number.isFinite(id));
    return ids.length ? Math.max(...ids) + 1 : 1;
  }

  function getManualPostviewQuestions() {
    return adminPostviewQuestions.filter((q) => q.manual);
  }

  function getAiPostviewQuestions() {
    return adminPostviewQuestions.filter((q) => !q.manual);
  }

  function ensureManualPostviewRow() {
    if (!getManualPostviewQuestions().length) {
      adminPostviewQuestions.push({
        id: nextPostviewQuestionId(),
        text: "",
        selected: true,
        manual: true,
      });
    }
  }

  function schedulePostviewManualSave() {
    if (postviewManualSaveTimer) clearTimeout(postviewManualSaveTimer);
    postviewManualSaveTimer = setTimeout(() => {
      postviewManualSaveTimer = null;
      savePostviewSelection({ silent: true });
    }, 700);
  }

  function renderPostviewManualRows() {
    if (!postviewManualRows) return;
    ensureManualPostviewRow();
    const manualQuestions = getManualPostviewQuestions();
    let html = "";
    manualQuestions.forEach((q) => {
      const index = adminPostviewQuestions.indexOf(q);
      const dimClass = q.selected ? "" : " opacity-50";
      html += `<label class="flex items-center gap-1 rounded px-1 py-0.5 bg-white/70${dimClass} cursor-pointer">
        <input type="checkbox" class="postview-manual-select-cb shrink-0 h-3.5 w-3.5 rounded border-amber-200 text-amber-600"
          data-index="${index}" ${q.selected ? "checked" : ""}>
        <span class="shrink-0 text-[9px] font-bold text-amber-700">Q${q.id}</span>
        <input type="text" class="postview-manual-input compact-input min-w-0 flex-1 text-[10px] py-0.5"
          data-index="${index}" value="${esc(q.text)}" placeholder="質問（英語）">
      </label>`;
    });
    postviewManualRows.innerHTML = html;
    postviewManualRows.querySelectorAll(".postview-manual-select-cb").forEach((cb) => {
      cb.addEventListener("change", onPostviewSelectionChange);
    });
    postviewManualRows.querySelectorAll(".postview-manual-input").forEach((input) => {
      input.addEventListener("input", onPostviewManualInputChange);
      input.addEventListener("blur", () => savePostviewSelection({ silent: true }));
    });
  }

  function onPostviewManualInputChange(event) {
    const index = Number(event.target.dataset.index);
    if (!Number.isInteger(index) || !adminPostviewQuestions[index]) return;
    adminPostviewQuestions[index].text = event.target.value;
    schedulePostviewManualSave();
  }

  function addManualPostviewRow() {
    adminPostviewQuestions.push({
      id: nextPostviewQuestionId(),
      text: "",
      selected: true,
      manual: true,
    });
    renderPostviewManualRows();
    const inputs = postviewManualRows?.querySelectorAll(".postview-manual-input") || [];
    const lastInput = inputs[inputs.length - 1];
    if (lastInput) lastInput.focus();
  }

  if (postviewAddQuestionBtn) {
    postviewAddQuestionBtn.addEventListener("click", addManualPostviewRow);
  }

  function renderAdminPostviewPreview(questions) {
    const incoming = (questions || []).map(function (q) {
      return {
        id: q.id,
        text: q.text || "",
        selected: q.selected !== false,
        manual: q.manual === true,
      };
    });
    const manualFromState = incoming.length
      ? incoming.filter((q) => q.manual)
      : getManualPostviewQuestions();
    const aiFromState = incoming.filter((q) => !q.manual);
    adminPostviewQuestions = [...aiFromState, ...manualFromState];

    const aiQuestions = getAiPostviewQuestions();
    if (!postviewPreview) {
      renderPostviewManualRows();
      return;
    }
    if (!aiQuestions.length) {
      postviewPreview.classList.add("hidden");
      renderPostviewManualRows();
      return;
    }
    const selectedCount = aiQuestions.filter(function (q) { return q.selected; }).length;
    let html = `<p class="mb-1 font-semibold text-slate-600">${t("postviewPreview", { selected: selectedCount, total: aiQuestions.length })}</p>`;
    html += `<p class="mb-1 text-[9px] text-slate-500">${t("postviewPreviewHint")}</p>`;
    html += `<div class="space-y-1">`;
    aiQuestions.forEach(function (q) {
      const index = adminPostviewQuestions.indexOf(q);
      const dimClass = q.selected ? "" : " opacity-50";
      html += `<label class="flex items-start gap-2 rounded px-1.5 py-1 ${index % 2 === 0 ? "bg-white/70" : ""}${dimClass} cursor-pointer">
        <input type="checkbox" class="postview-select-cb shrink-0 mt-0.5 h-3.5 w-3.5 rounded border-amber-200 text-amber-600"
          data-index="${index}" ${q.selected ? "checked" : ""}>
        <span class="shrink-0 mr-1 text-amber-700 font-bold">Q${q.id}.</span>
        <span class="text-slate-700 leading-snug">${esc(q.text)}</span>
      </label>`;
    });
    html += `</div>`;
    postviewPreview.innerHTML = html;
    postviewPreview.classList.remove("hidden");
    postviewPreview.querySelectorAll(".postview-select-cb").forEach(function (cb) {
      cb.addEventListener("change", onPostviewSelectionChange);
    });
    renderPostviewManualRows();
  }

  async function savePostviewSelection(options) {
    const silent = options && options.silent;
    const classId = getSelectedClassId() || (lessonClassId && lessonClassId.value);
    if (!classId) return true;
    const questionsToSave = adminPostviewQuestions.filter((q) => (q.text || "").trim());
    if (!questionsToSave.length) return true;
    postviewSelectionSaving = true;
    try {
      const res = await fetch("/news/admin/api/class/lesson/postview/selection", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ class_id: classId, postview_questions: questionsToSave }),
      });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || "保存に失敗しました");
      const savedManual = getManualPostviewQuestions();
      const savedFromServer = (data.postview_questions || questionsToSave).map(function (q) {
        return {
          id: q.id,
          text: q.text || "",
          selected: q.selected !== false,
          manual: q.manual === true,
        };
      });
      const serverManual = savedFromServer.filter((q) => q.manual);
      const serverAi = savedFromServer.filter((q) => !q.manual);
      const draftManual = savedManual.filter((q) => !(q.text || "").trim());
      adminPostviewQuestions = [...serverAi, ...serverManual, ...draftManual];
      if (!silent) {
        renderAdminPostviewPreview(adminPostviewQuestions);
        showMessage(lessonMessage, data.message || "事後質問の表示設定を保存しました。", false);
      }
      return true;
    } catch (err) {
      if (!silent) showMessage(lessonMessage, err.message, true);
      return false;
    } finally {
      postviewSelectionSaving = false;
    }
  }

  async function onPostviewSelectionChange(event) {
    if (postviewSelectionSaving) {
      event.target.checked = !event.target.checked;
      return;
    }
    const index = Number(event.target.dataset.index);
    if (!Number.isInteger(index) || !adminPostviewQuestions[index]) return;
    const previous = adminPostviewQuestions[index].selected;
    adminPostviewQuestions[index].selected = event.target.checked;
    renderAdminPostviewPreview(adminPostviewQuestions);
    const ok = await savePostviewSelection({ silent: true });
    if (!ok) {
      adminPostviewQuestions[index].selected = previous;
      renderAdminPostviewPreview(adminPostviewQuestions);
      showMessage(lessonMessage, "事後質問の表示設定の保存に失敗しました。", true);
    }
  }

  if (postviewScaffoldingEnabledEl) {
    postviewScaffoldingEnabledEl.addEventListener("change", async function () {
      const classId = getSelectedClassId() || (lessonClassId && lessonClassId.value);
      if (!classId) {
        showMessage(lessonMessage, "クラスを選択してから操作してください。", true);
        postviewScaffoldingEnabledEl.checked = !postviewScaffoldingEnabledEl.checked;
        return;
      }
      const enabled = postviewScaffoldingEnabledEl.checked;
      try {
        const res = await fetch("/news/admin/api/class/lesson/postview/toggle", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ class_id: classId, postview_scaffolding_enabled: enabled }),
        });
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || "保存に失敗しました");
        showMessage(lessonMessage, data.message || "事後質問の設定を保存しました。", false);
      } catch (err) {
        showMessage(lessonMessage, err.message, true);
        postviewScaffoldingEnabledEl.checked = !enabled;
      }
    });
  }

  if (postviewGenerateBtn) {
    postviewGenerateBtn.addEventListener("click", async function () {
      const classId = getSelectedClassId() || (lessonClassId && lessonClassId.value);
      if (!classId) {
        showMessage(lessonMessage, "クラスを選択または作成してください。", true);
        return;
      }
      const script = document.getElementById("lesson-script") ? document.getElementById("lesson-script").value.trim() : "";
      if (!script) {
        showMessage(lessonMessage, "スクリプトを入力してから生成してください。", true);
        return;
      }
      postviewGenerateBtn.disabled = true;
      postviewGenerateBtn.textContent = t("generatingQuestions");
      if (postviewGenerateStatus) {
        postviewGenerateStatus.textContent = t("generatingPostview");
        postviewGenerateStatus.classList.remove("hidden");
      }
      if (postviewPreview) postviewPreview.classList.add("hidden");
      try {
        const res = await fetch("/news/admin/api/class/lesson/postview", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ class_id: classId, script }),
        });
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || "生成に失敗しました");
        renderAdminPostviewPreview(data.postview_questions || []);
        showMessage(lessonMessage, data.message || "事後質問を生成しました。", false);
        if (postviewGenerateStatus) postviewGenerateStatus.classList.add("hidden");
      } catch (err) {
        showMessage(lessonMessage, err.message, true);
        if (postviewGenerateStatus) {
          postviewGenerateStatus.textContent = t("generateFail");
        }
      } finally {
        postviewGenerateBtn.disabled = false;
        postviewGenerateBtn.textContent = t("aiGeneratePostview");
      }
    });
  }

  function materialsDocxFilename(title) {
    const safe = String(title || "")
      .replace(/[\\/:*?"<>|]/g, "")
      .replace(/\s+/g, "_")
      .slice(0, 40);
    return safe ? `授業教材_${safe}.docx` : "授業教材.docx";
  }

  function showExportMaterialsStatus(message, isError) {
    if (!exportMaterialsStatus) return;
    if (!message) {
      exportMaterialsStatus.classList.add("hidden");
      exportMaterialsStatus.textContent = "";
      return;
    }
    exportMaterialsStatus.textContent = message;
    exportMaterialsStatus.classList.toggle("text-red-600", Boolean(isError));
    exportMaterialsStatus.classList.toggle("text-slate-500", !isError);
    exportMaterialsStatus.classList.remove("hidden");
  }

  async function downloadLessonMaterialsWord() {
    const include = {
      transcript: document.getElementById("export-include-transcript")?.checked === true,
      translation: document.getElementById("export-include-translation")?.checked === true,
      vocabulary: document.getElementById("export-include-vocab")?.checked === true,
      warmup: document.getElementById("export-include-warmup")?.checked === true,
      postview: document.getElementById("export-include-postview")?.checked === true,
    };
    if (!Object.values(include).some(Boolean)) {
      showExportMaterialsStatus(t("selectExportSection"), true);
      return;
    }

    const classId = getSelectedClassId() || (lessonClassId && lessonClassId.value) || "";
    const title = document.getElementById("lesson-title")?.value.trim() || "";
    const script = document.getElementById("lesson-script")?.value.trim() || "";
    const translationText = getLessonTranslationText();
    const pairs = getScriptTranslationRows(script, translationText, getLessonTranslationPairs());
    const warmupToExport = adminWarmupQuestions.filter((q) => (q.text || "").trim() && q.selected !== false);
    const postviewToExport = adminPostviewQuestions.filter((q) => (q.text || "").trim() && q.selected !== false);
    const vocabToExport = adminVocabItems.filter((item) => item.selected !== false);

    if (exportMaterialsDocxBtn) {
      exportMaterialsDocxBtn.disabled = true;
      exportMaterialsDocxBtn.textContent = t("exporting");
    }
    showExportMaterialsStatus(t("creatingWord"), false);

    try {
      const res = await fetch("/news/admin/api/class/lesson/materials/docx", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          class_id: classId,
          title,
          script,
          script_ja: translationText,
          pairs,
          vocabulary_data: vocabToExport,
          warmup_questions: warmupToExport,
          postview_questions: postviewToExport,
          include,
        }),
      });
      const contentType = res.headers.get("content-type") || "";
      if (!res.ok || contentType.includes("application/json")) {
        let message = "Word の作成に失敗しました。";
        try {
          const data = await res.json();
          if (data && data.error) message = data.error;
        } catch (_err) {
          /* ignore */
        }
        throw new Error(message);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = materialsDocxFilename(title);
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      showExportMaterialsStatus("", false);
    } catch (err) {
      showExportMaterialsStatus(err.message || "Word の作成に失敗しました。", true);
    } finally {
      if (exportMaterialsDocxBtn) {
        exportMaterialsDocxBtn.disabled = false;
        exportMaterialsDocxBtn.textContent = t("exportWordMaterials");
      }
    }
  }

  if (exportMaterialsDocxBtn) {
    exportMaterialsDocxBtn.addEventListener("click", downloadLessonMaterialsWord);
  }

  if (window.NewsI18n) {
    if (assistiveLang() === "es") {
      const panelHint = document.getElementById("script-translate-panel-hint");
      if (panelHint) {
        panelHint.setAttribute("data-i18n", "scriptAndTranslationHintEs");
      }
    }
    window.NewsI18n.apply();
  }
  if (window.ADMIN_ACTIVE_CLASS) {
    fillLessonForm(window.ADMIN_ACTIVE_CLASS);
  } else {
    renderAdminWarmupPreview("", []);
    renderAdminPostviewPreview([]);
  }
  if (!window.ADMIN_ACTIVE_CLASS && (window.ADMIN_WARMUP_IMAGE_URL || (window.ADMIN_WARMUP_QUESTIONS && window.ADMIN_WARMUP_QUESTIONS.length))) {
    renderAdminWarmupPreview(window.ADMIN_WARMUP_IMAGE_URL || "", window.ADMIN_WARMUP_QUESTIONS || []);
  }
  if (!window.ADMIN_ACTIVE_CLASS && window.ADMIN_POSTVIEW_QUESTIONS && window.ADMIN_POSTVIEW_QUESTIONS.length) {
    renderAdminPostviewPreview(window.ADMIN_POSTVIEW_QUESTIONS);
  }
})();
