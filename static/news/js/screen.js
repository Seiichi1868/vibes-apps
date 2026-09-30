(function () {
  function t(key, vars) {
    return window.NewsI18n ? window.NewsI18n.t(key, vars) : key;
  }
  function mapPos(pos) {
    return window.NewsI18n ? window.NewsI18n.mapPos(pos) : pos || "";
  }
  function showAssistive() {
    return window.NewsI18n ? window.NewsI18n.showAssistive() : true;
  }

  const screenApp = document.getElementById("screen-app");
  const classLabel = document.getElementById("screen-class-label");
  const loadingEl = document.getElementById("screen-loading");
  const errorEl = document.getElementById("screen-error");
  const controlsEl = document.getElementById("screen-controls");
  const fullscreenBtn = document.getElementById("screen-fullscreen-btn");

  const viewVideo = document.getElementById("view-video");
  const viewVocab = document.getElementById("view-vocab");
  const viewWarmup = document.getElementById("view-warmup");
  const viewPostview = document.getElementById("view-postview");
  const youtubePlayer = document.getElementById("youtube-player-screen");
  const videoPlaceholder = document.getElementById("video-placeholder-screen");
  const vocabContent = document.getElementById("vocab-content-screen");
  const warmupContent = document.getElementById("warmup-content-screen");
  const postviewContent = document.getElementById("postview-content-screen");
  const viewWriting = document.getElementById("view-writing");
  const writingContent = document.getElementById("writing-content-screen");

  const viewMap = { video: viewVideo, vocab: viewVocab, warmup: viewWarmup, postview: viewPostview, writing: viewWriting };
  const viewButtons = controlsEl ? controlsEl.querySelectorAll("[data-view]") : [];

  let currentView = "video";
  const questionReveal = {
    warmup: { questions: [], step: 0, imageUrl: "" },
    postview: { questions: [], step: 0, imageUrl: "" },
  };
  const writingReveal = { topics: [], step: 0 };
  let youtubeApiPlayer = null;
  let youtubeApiReadyPromise = null;
  let activePlayerSubtitles = null;
  let videoStartSeconds = 0;
  let videoEndSeconds = 0;
  let videoRangeGuardInterval = null;

  function escHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function showLoading(show) {
    if (loadingEl) loadingEl.classList.toggle("hidden", !show);
  }

  function showError(msg) {
    showLoading(false);
    if (errorEl) {
      errorEl.textContent = msg;
      errorEl.classList.remove("hidden");
      errorEl.classList.add("flex");
    }
    if (controlsEl) controlsEl.classList.add("hidden");
  }

  function buildPlayerVars(start, end, subtitlesEnabled) {
    const vars = {
      start: Math.max(0, start || 0),
      playsinline: 1,
      rel: 0,
      modestbranding: 1,
      enablejsapi: 1,
      fs: 1,
      iv_load_policy: 3,
      hl: "en",
      cc_lang_pref: "en",
      origin: window.location.origin,
      widget_referrer: window.location.origin,
    };
    if (end && end > start) vars.end = end;
    if (subtitlesEnabled) {
      vars.cc_load_policy = 1;
      vars.cc_lang_pref = "en";
    }
    return vars;
  }

  function buildEmbedUrl(videoId, start, end, subtitlesEnabled) {
    const params = new URLSearchParams();
    Object.entries(buildPlayerVars(start, end, subtitlesEnabled)).forEach(([key, value]) => {
      params.set(key, String(value));
    });
    return `https://www.youtube.com/embed/${videoId}?${params.toString()}`;
  }

  function destroyYouTubePlayer() {
    if (youtubeApiPlayer && typeof youtubeApiPlayer.destroy === "function") {
      try {
        youtubeApiPlayer.destroy();
      } catch (_) {
        /* ignore */
      }
    }
    youtubeApiPlayer = null;
    activePlayerSubtitles = null;
    if (youtubePlayer) {
      youtubePlayer.innerHTML = "";
      youtubePlayer.classList.add("hidden");
    }
  }

  function loadYouTubeApi() {
    if (window.YT && window.YT.Player) return Promise.resolve();
    if (youtubeApiReadyPromise) return youtubeApiReadyPromise;

    youtubeApiReadyPromise = new Promise((resolve) => {
      const previousReady = window.onYouTubeIframeAPIReady;
      window.onYouTubeIframeAPIReady = () => {
        if (typeof previousReady === "function") previousReady();
        resolve();
      };
      if (!document.querySelector('script[src="https://www.youtube.com/iframe_api"]')) {
        const script = document.createElement("script");
        script.src = "https://www.youtube.com/iframe_api";
        document.head.appendChild(script);
      }
    });
    return youtubeApiReadyPromise;
  }

  function stopVideoRangeGuard() {
    clearInterval(videoRangeGuardInterval);
    videoRangeGuardInterval = null;
  }

  function mountPlainEmbed(embedUrl) {
    if (!youtubePlayer) return;
    destroyYouTubePlayer();
    const iframe = document.createElement("iframe");
    iframe.className = "absolute inset-0 h-full w-full border-0";
    iframe.title = "News video player";
    iframe.src = embedUrl;
    iframe.allow =
      "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share";
    iframe.referrerPolicy = "strict-origin-when-cross-origin";
    iframe.allowFullscreen = true;
    iframe.setAttribute("playsinline", "");
    youtubePlayer.appendChild(iframe);
    youtubePlayer.classList.remove("hidden");
    if (videoPlaceholder) videoPlaceholder.classList.add("hidden");
  }

  function applySubtitles(player, enabled) {
    if (!player || !enabled) return;
    try {
      if (typeof player.loadModule === "function") player.loadModule("captions");
      if (typeof player.setOption === "function") {
        player.setOption("captions", "track", { languageCode: "en" });
      }
    } catch (_) {
      /* ignore */
    }
  }

  function enforceVideoRange() {
    if (!youtubeApiPlayer || typeof youtubeApiPlayer.getCurrentTime !== "function") return;
    const current = youtubeApiPlayer.getCurrentTime();
    if (!Number.isFinite(current)) return;
    if (current < videoStartSeconds - 0.5) {
      youtubeApiPlayer.seekTo(videoStartSeconds, true);
      return;
    }
    if (videoEndSeconds > videoStartSeconds && current > videoEndSeconds + 0.5) {
      youtubeApiPlayer.seekTo(videoStartSeconds, true);
      if (typeof youtubeApiPlayer.pauseVideo === "function") youtubeApiPlayer.pauseVideo();
    }
  }

  function startVideoRangeGuard() {
    clearInterval(videoRangeGuardInterval);
    videoRangeGuardInterval = setInterval(enforceVideoRange, 500);
  }

  async function mountYouTubePlayer(videoId, start, end, subtitlesEnabled) {
    if (!youtubePlayer || !videoId) return;

    await loadYouTubeApi();
    const playerVars = buildPlayerVars(start, end, subtitlesEnabled);

    if (youtubeApiPlayer && activePlayerSubtitles !== subtitlesEnabled) {
      destroyYouTubePlayer();
    }

    if (youtubeApiPlayer && typeof youtubeApiPlayer.loadVideoById === "function") {
      youtubeApiPlayer.loadVideoById({ videoId, startSeconds: Math.max(0, start || 0) });
      applySubtitles(youtubeApiPlayer, subtitlesEnabled);
      activePlayerSubtitles = subtitlesEnabled;
      youtubePlayer.classList.remove("hidden");
      if (videoPlaceholder) videoPlaceholder.classList.add("hidden");
      return;
    }

    destroyYouTubePlayer();
    youtubePlayer.classList.remove("hidden");
    if (videoPlaceholder) videoPlaceholder.classList.add("hidden");

    await new Promise((resolve, reject) => {
      let settled = false;
      const timeout = window.setTimeout(() => {
        if (settled) return;
        settled = true;
        reject(new Error("YouTube player timeout"));
      }, 8000);

      youtubeApiPlayer = new window.YT.Player(youtubePlayer, {
        videoId,
        width: "100%",
        height: "100%",
        playerVars,
        events: {
          onReady: () => {
            if (settled) return;
            settled = true;
            clearTimeout(timeout);
            applySubtitles(youtubeApiPlayer, subtitlesEnabled);
            activePlayerSubtitles = subtitlesEnabled;
            enforceVideoRange();
            startVideoRangeGuard();
            resolve();
          },
          onStateChange: enforceVideoRange,
          onError: () => {
            if (settled) return;
            settled = true;
            clearTimeout(timeout);
            reject(new Error("YouTube player error"));
          },
        },
      });
    });
  }

  async function setVideoPlayer(video) {
    stopVideoRangeGuard();
    if (!video || !video.video_id) {
      destroyYouTubePlayer();
      if (videoPlaceholder) {
        videoPlaceholder.classList.remove("hidden");
        videoPlaceholder.textContent = t("screenVideoUnset");
      }
      return;
    }

    videoStartSeconds = Math.max(0, parseInt(video.start_seconds, 10) || 0);
    videoEndSeconds = Math.max(0, parseInt(video.end_seconds, 10) || 0);
    const embedUrl = buildEmbedUrl(
      video.video_id,
      videoStartSeconds,
      videoEndSeconds,
      video.subtitles_enabled
    );

    try {
      await mountYouTubePlayer(
        video.video_id,
        videoStartSeconds,
        videoEndSeconds,
        video.subtitles_enabled
      );
    } catch (_) {
      mountPlainEmbed(embedUrl);
    }
  }

  function renderVocab(items) {
    if (!vocabContent) return;
    if (!items || !items.length) {
      vocabContent.innerHTML =
        '<p class="text-center text-lg text-slate-500">' + t("screenNoVocab") + "</p>";
      return;
    }
    let html =
      '<table class="screen-vocab-table"><thead><tr>' +
      "<th>" + t("vocabWord") + "</th><th>" + t("pos") + "</th><th>" + t("vocabMeaning") + "</th>" +
      "</tr></thead><tbody>";
    items.forEach(function (item) {
      html +=
        "<tr>" +
        '<td class="screen-vocab-word">' + escHtml(item.word) + "</td>" +
        '<td class="screen-vocab-pos">' + escHtml(mapPos(item.part_of_speech)) + "</td>" +
        "<td>" + escHtml(item.meaning) + "</td>" +
        "</tr>";
    });
    html += "</tbody></table>";
    vocabContent.innerHTML = html;
  }

  function singleQuestionFontSize(hasImage) {
    const scale = hasImage ? 0.88 : 1;
    return (
      "clamp(" +
      (2.15 * scale).toFixed(2) +
      "rem, " +
      (6.8 * scale).toFixed(1) +
      "vmin, " +
      (5.6 * scale).toFixed(1) +
      "rem)"
    );
  }

  function warmupImageMaxHeight() {
    return "min(28vh, 18rem)";
  }

  function questionRevealPieces(questions) {
    const pieces = [];
    (questions || []).forEach(function (q, index) {
      if (!q || !q.text) return;
      pieces.push({ kind: "question", index: index });
      if (q.answer) pieces.push({ kind: "answer", index: index });
    });
    return pieces;
  }

  function questionRevealViewEl(kind) {
    return kind === "warmup" ? viewWarmup : viewPostview;
  }

  function questionRevealContentEl(kind) {
    return kind === "warmup" ? warmupContent : postviewContent;
  }

  function isStepRevealView(view) {
    return view === "warmup" || view === "postview" || view === "writing";
  }

  function prefersTouchNav() {
    return Boolean(
      window.matchMedia &&
        (window.matchMedia("(pointer: coarse)").matches || window.matchMedia("(hover: none)").matches)
    );
  }

  function updateQuestionRevealUi(kind) {
    const state = questionReveal[kind];
    const viewEl = questionRevealViewEl(kind);
    const contentEl = questionRevealContentEl(kind);
    if (!state || !viewEl || !contentEl) return;
    const pieces = questionRevealPieces(state.questions);
    const pending = pieces.length > 0 && state.step < pieces.length;
    viewEl.classList.toggle("is-reveal-pending", pending);
    const hint = contentEl.querySelector(".screen-postview-hint");
    if (!hint) return;
    if (!pieces.length) {
      hint.classList.add("hidden");
      return;
    }
    hint.classList.remove("hidden");
    const hintKey = prefersTouchNav() ? "screenFlickNext" : "screenClickNext";
    hint.textContent = t(hintKey, { shown: state.step, total: pieces.length });
  }

  function renderQuestionReveal(kind) {
    const state = questionReveal[kind];
    const contentEl = questionRevealContentEl(kind);
    if (!state || !contentEl) return;
    const list = state.questions;
    const imageUrl = state.imageUrl || "";
    const emptyKey = kind === "warmup" ? "screenNoWarmup" : "screenNoPostview";
    const headingKey = kind === "warmup" ? "screenWarmupHeading" : "screenPostviewHeading";

    if (!imageUrl && !list.length) {
      contentEl.innerHTML = '<p class="text-center text-lg text-slate-500">' + t(emptyKey) + "</p>";
      const viewEl = questionRevealViewEl(kind);
      if (viewEl) viewEl.classList.remove("is-reveal-pending");
      return;
    }

    const hasImage = Boolean(imageUrl);
    contentEl.style.setProperty("--warmup-q-size", singleQuestionFontSize(hasImage));
    contentEl.style.setProperty("--warmup-img-max-h", warmupImageMaxHeight());

    const pieces = questionRevealPieces(list);
    let html = "";
    if (imageUrl) {
      html +=
        '<div class="screen-warmup-img-wrap">' +
        '<img src="' + escHtml(imageUrl) + '" alt="Warmup illustration">' +
        "</div>";
    }
    html += '<p class="screen-warmup-heading">' + t(headingKey) + "</p>";

    if (pieces.length && state.step > 0) {
      const piece = pieces[Math.min(state.step, pieces.length) - 1];
      const q = list[piece.index];
      html += '<div class="screen-qa-current">';
      html +=
        '<div class="screen-warmup-q flex items-start gap-[0.35em]">' +
        '<span class="screen-warmup-num">Q' + (piece.index + 1) + ".</span>" +
        '<span class="screen-warmup-text">' + escHtml(q.text) + "</span>" +
        "</div>";
      if (piece.kind === "answer") {
        html +=
          '<p class="screen-postview-answer is-shown" aria-hidden="false"><span>' +
          '<span class="screen-postview-answer-label">A.</span>' +
          escHtml(q.answer) +
          "</span></p>";
      }
      html += "</div>";
    } else if (list.length) {
      html +=
        '<p class="screen-qa-waiting">' +
        t(prefersTouchNav() ? "screenFlickToStart" : "screenClickToStart") +
        "</p>";
    }

    if (pieces.length) {
      html += '<p class="screen-postview-hint"></p>';
    }
    contentEl.innerHTML = html;
    updateQuestionRevealUi(kind);
  }

  function revealNextQuestionStep(kind) {
    if (currentView !== kind) return;
    const state = questionReveal[kind];
    if (!state) return;
    const pieces = questionRevealPieces(state.questions);
    if (state.step >= pieces.length) return;
    state.step += 1;
    renderQuestionReveal(kind);
  }

  function hideLastQuestionStep(kind) {
    if (currentView !== kind) return;
    const state = questionReveal[kind];
    if (!state || state.step <= 0) return;
    state.step -= 1;
    renderQuestionReveal(kind);
  }

  function renderWarmup(imageUrl, questions) {
    questionReveal.warmup.imageUrl = imageUrl || "";
    questionReveal.warmup.questions = (questions || []).filter(function (q) {
      return q && q.text;
    });
    questionReveal.warmup.step = 0;
    renderQuestionReveal("warmup");
  }

  function renderPostview(questions) {
    questionReveal.postview.imageUrl = "";
    questionReveal.postview.questions = (questions || []).filter(function (q) {
      return q && q.text;
    });
    questionReveal.postview.step = 0;
    renderQuestionReveal("postview");
  }

  function writingTopicFontSize() {
    return "clamp(2rem, 6.4vmin, 5.25rem)";
  }

  function writingOreoHtml() {
    return (
      '<div class="screen-writing-oreo">' +
      '<span class="screen-writing-oreo-step"><b>O</b>Opinion</span>' +
      '<span class="screen-writing-oreo-arrow">→</span>' +
      '<span class="screen-writing-oreo-step"><b>R</b>Reason</span>' +
      '<span class="screen-writing-oreo-arrow">→</span>' +
      '<span class="screen-writing-oreo-step"><b>E</b>Example</span>' +
      '<span class="screen-writing-oreo-arrow">→</span>' +
      '<span class="screen-writing-oreo-step"><b>O</b>Opinion</span>' +
      '<span class="screen-writing-oreo-words">about 100 words</span>' +
      "</div>"
    );
  }

  function writingTopicBodyHtml(topic, index) {
    let html = '<div class="screen-writing-item">';
    html +=
      '<div class="screen-warmup-q flex items-start gap-[0.35em]">' +
      '<span class="screen-warmup-num">T' + (index + 1) + ".</span>" +
      '<span class="screen-warmup-text">' + escHtml(topic.text) + "</span>" +
      "</div>";
    if (topic.kind === "opinion" && topic.options && topic.options.length === 2) {
      html +=
        '<div class="screen-writing-choices">' +
        '<span class="screen-writing-choice">' + escHtml(topic.options[0]) + "</span>" +
        '<span class="screen-writing-or">or</span>' +
        '<span class="screen-writing-choice">' + escHtml(topic.options[1]) + "</span>" +
        "</div>";
    } else {
      html +=
        '<div class="screen-writing-choices">' +
        '<span class="screen-writing-answer-cue">Your answer + Why?</span>' +
        "</div>";
    }
    if (topic.text_ja) {
      html += '<p class="screen-writing-ja">' + escHtml(topic.text_ja) + "</p>";
    }
    html += "</div>";
    return html;
  }

  function updateWritingRevealUi() {
    if (!viewWriting || !writingContent) return;
    const total = writingReveal.topics.length;
    const pending = total > 0 && writingReveal.step < total;
    viewWriting.classList.toggle("is-reveal-pending", pending);
    const hint = writingContent.querySelector(".screen-postview-hint");
    if (!hint) return;
    if (!total) {
      hint.classList.add("hidden");
      return;
    }
    hint.classList.remove("hidden");
    const hintKey = prefersTouchNav() ? "screenFlickNext" : "screenClickNext";
    hint.textContent = t(hintKey, { shown: writingReveal.step, total: total });
  }

  function renderWritingReveal() {
    if (!writingContent) return;
    const list = writingReveal.topics;
    if (!list.length) {
      writingContent.innerHTML =
        '<p class="text-center text-slate-400">' + t("screenNoWriting") + "</p>";
      if (viewWriting) viewWriting.classList.remove("is-reveal-pending");
      return;
    }
    writingContent.style.setProperty("--warmup-q-size", writingTopicFontSize());
    let html = '<p class="screen-warmup-heading">' + t("screenWritingHeading") + "</p>";
    if (writingReveal.step > 0) {
      const index = Math.min(writingReveal.step, list.length) - 1;
      html += '<div class="screen-qa-current">';
      html += writingTopicBodyHtml(list[index], index);
      html += "</div>";
    } else {
      html +=
        '<p class="screen-qa-waiting">' +
        t(prefersTouchNav() ? "screenFlickWritingToStart" : "screenWritingToStart") +
        "</p>";
    }
    html += writingOreoHtml();
    html += '<p class="screen-postview-hint"></p>';
    writingContent.innerHTML = html;
    updateWritingRevealUi();
  }

  function revealNextWritingStep() {
    if (currentView !== "writing") return;
    if (writingReveal.step >= writingReveal.topics.length) return;
    writingReveal.step += 1;
    renderWritingReveal();
  }

  function hideLastWritingStep() {
    if (currentView !== "writing") return;
    if (writingReveal.step <= 0) return;
    writingReveal.step -= 1;
    renderWritingReveal();
  }

  function renderWriting(topics) {
    writingReveal.topics = (topics || []).filter(function (topic) {
      return topic && topic.text;
    });
    writingReveal.step = 0;
    renderWritingReveal();
  }

  function getAvailableViews() {
    const views = [];
    viewButtons.forEach(function (btn) {
      const view = btn.dataset.view;
      if (!view || btn.disabled || btn.classList.contains("hidden")) return;
      views.push(view);
    });
    return views;
  }

  function goAdjacentView(delta) {
    const views = getAvailableViews();
    if (views.length < 2) return false;
    let index = views.indexOf(currentView);
    if (index < 0) index = 0;
    const next = views[(index + delta + views.length) % views.length];
    if (!next || next === currentView) return false;
    setActiveView(next);
    return true;
  }

  function setActiveView(view) {
    currentView = view;
    Object.entries(viewMap).forEach(function ([key, el]) {
      if (!el) return;
      el.classList.toggle("is-active", key === view);
    });
    viewButtons.forEach(function (btn) {
      btn.classList.toggle("is-active", btn.dataset.view === view);
    });
    if (screenApp) screenApp.classList.toggle("is-video-view", view === "video");
  }

  function configureControls(payload) {
    if (!controlsEl) return;
    const availability = {
      video: payload.has_video,
      vocab: payload.has_vocab && showAssistive(),
      warmup: payload.has_warmup,
      postview: payload.has_postview,
      writing: payload.has_writing,
    };

    viewButtons.forEach(function (btn) {
      const view = btn.dataset.view;
      const available = availability[view];
      btn.disabled = !available;
      btn.classList.toggle("hidden", !available);
    });

    controlsEl.classList.remove("hidden");

    const defaultView =
      (availability.video && "video") ||
      (availability.warmup && "warmup") ||
      (availability.postview && "postview") ||
      (availability.writing && "writing") ||
      (availability.vocab && "vocab") ||
      "video";
    setActiveView(defaultView);
  }

  async function loadScreen(classId, archiveId) {
    if (!classId) {
      showError(t("screenNoClass"));
      return;
    }

    showLoading(true);
    if (errorEl) {
      errorEl.classList.add("hidden");
      errorEl.classList.remove("flex");
    }

    try {
      let url = "/news/api/screen?class_id=" + encodeURIComponent(classId);
      if (archiveId) url += "&archive=" + encodeURIComponent(archiveId);
      const res = await fetch(url);
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || t("screenLoadFail"));

      if (data.display_language && window.NewsI18n) {
        window.NewsI18n.setLang(data.display_language);
      }

      const cls = data.class;
      if (classLabel) {
        const name = cls.name || "";
        const lesson = String(cls.lesson_title || "").trim();
        classLabel.textContent = lesson ? name + " · " + lesson : name;
      }

      await setVideoPlayer(cls.video);
      renderVocab(cls.vocabulary_data || []);
      renderWarmup(cls.warmup_image_url || "", cls.warmup_questions || []);
      renderPostview(cls.postview_questions || []);
      renderWriting(cls.writing_topics || []);
      configureControls(cls);
      showLoading(false);
    } catch (err) {
      showError(err.message || t("screenLoadFail"));
    }
  }

  viewButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      if (btn.disabled) return;
      setActiveView(btn.dataset.view);
    });
  });

  function bindQuestionRevealClick(viewEl, kind) {
    if (!viewEl) return;
    viewEl.addEventListener("click", function (event) {
      if (ignoreQuestionClick) {
        event.preventDefault();
        event.stopImmediatePropagation();
        ignoreQuestionClick = false;
        return;
      }
      if (event.target && event.target.closest && event.target.closest("button, a, input, textarea")) return;
      revealNextQuestionStep(kind);
    });
  }

  bindQuestionRevealClick(viewWarmup, "warmup");
  bindQuestionRevealClick(viewPostview, "postview");
  if (viewWriting) {
    viewWriting.addEventListener("click", function (event) {
      if (ignoreQuestionClick) {
        event.preventDefault();
        event.stopImmediatePropagation();
        ignoreQuestionClick = false;
        return;
      }
      if (event.target && event.target.closest && event.target.closest("button, a, input, textarea")) return;
      revealNextWritingStep();
    });
  }

  let swipeStartX = 0;
  let swipeStartY = 0;
  let swipeTracking = false;
  let ignoreQuestionClick = false;

  function suppressQuestionClick() {
    ignoreQuestionClick = true;
    window.setTimeout(function () {
      ignoreQuestionClick = false;
    }, 400);
  }

  function onScreenTouchStart(event) {
    if (event.touches.length !== 1) {
      swipeTracking = false;
      return;
    }
    if (event.target && event.target.closest && event.target.closest("button, a, input, textarea")) {
      swipeTracking = false;
      return;
    }
    const touch = event.touches[0];
    swipeStartX = touch.clientX;
    swipeStartY = touch.clientY;
    swipeTracking = true;
  }

  function onScreenTouchMove(event) {
    if (!swipeTracking || event.touches.length !== 1) return;
    const touch = event.touches[0];
    const dx = touch.clientX - swipeStartX;
    const dy = touch.clientY - swipeStartY;
    const absX = Math.abs(dx);
    const absY = Math.abs(dy);
    const isStepView = isStepRevealView(currentView);
    if (absX > 16 && absX > absY * 1.15) {
      event.preventDefault();
      return;
    }
    if (isStepView && absY > 16 && absY > absX * 1.15) {
      event.preventDefault();
    }
  }

  function onScreenTouchEnd(event) {
    if (!swipeTracking) return;
    swipeTracking = false;
    const touch = event.changedTouches && event.changedTouches[0];
    if (!touch) return;
    const dx = touch.clientX - swipeStartX;
    const dy = touch.clientY - swipeStartY;
    const absX = Math.abs(dx);
    const absY = Math.abs(dy);
    if (absX >= 48 && absX > absY * 1.2) {
      suppressQuestionClick();
      goAdjacentView(dx < 0 ? 1 : -1);
      return;
    }
    if (!isStepRevealView(currentView)) return;
    if (absY < 48 || absY <= absX * 1.2) return;
    suppressQuestionClick();
    if (currentView === "writing") {
      if (dy < 0) revealNextWritingStep();
      else hideLastWritingStep();
      return;
    }
    if (dy < 0) revealNextQuestionStep(currentView);
    else hideLastQuestionStep(currentView);
  }

  if (screenApp) {
    screenApp.addEventListener("touchstart", onScreenTouchStart, { passive: true });
    screenApp.addEventListener("touchmove", onScreenTouchMove, { passive: false });
    screenApp.addEventListener("touchend", onScreenTouchEnd);
    screenApp.addEventListener("touchcancel", function () {
      swipeTracking = false;
    });
  }

  document.addEventListener("keydown", function (event) {
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    if (event.target && event.target.closest && event.target.closest("button, a, input, textarea")) return;
    const key = event.key;
    if (key === "ArrowLeft" || key === "ArrowRight") {
      event.preventDefault();
      goAdjacentView(key === "ArrowRight" ? 1 : -1);
      return;
    }
    if (currentView === "writing") {
      const showNext = key === " " || key === "Spacebar" || key === "ArrowDown" || key === "PageDown" || key === "Enter";
      const hidePrev = key === "ArrowUp" || key === "PageUp";
      if (!showNext && !hidePrev) return;
      event.preventDefault();
      if (hidePrev) hideLastWritingStep();
      else revealNextWritingStep();
      return;
    }
    if (currentView !== "postview" && currentView !== "warmup") return;
    const showNext = key === " " || key === "Spacebar" || key === "ArrowDown" || key === "PageDown" || key === "Enter";
    const hidePrev = key === "ArrowUp" || key === "PageUp";
    if (!showNext && !hidePrev) return;
    event.preventDefault();
    if (hidePrev) hideLastQuestionStep(currentView);
    else revealNextQuestionStep(currentView);
  });

  if (fullscreenBtn) {
    fullscreenBtn.addEventListener("click", function () {
      const target = screenApp || document.documentElement;
      if (document.fullscreenElement) {
        document.exitFullscreen().catch(function () {});
      } else if (target.requestFullscreen) {
        target.requestFullscreen().catch(function () {});
      }
    });
  }

  document.addEventListener("fullscreenchange", function () {
    if (!fullscreenBtn) return;
    fullscreenBtn.textContent = document.fullscreenElement ? "⛶" : "⛶";
    fullscreenBtn.title = document.fullscreenElement ? t("exitFullscreen") : t("fullscreen");
  });

  const urlParams = new URLSearchParams(window.location.search);
  const classId = urlParams.get("class") || window.SCREEN_INITIAL_CLASS_ID || "";
  const archiveId = urlParams.get("archive") || window.SCREEN_INITIAL_ARCHIVE_ID || "";
  loadScreen(classId, archiveId);
})();
