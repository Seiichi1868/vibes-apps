(function () {
  const screenApp = document.getElementById("screen-app");
  const classLabel = document.getElementById("screen-class-label");
  const loadingEl = document.getElementById("screen-loading");
  const errorEl = document.getElementById("screen-error");
  const controlsEl = document.getElementById("screen-controls");
  const fullscreenBtn = document.getElementById("screen-fullscreen-btn");

  const viewVideo = document.getElementById("view-video");
  const viewVocab = document.getElementById("view-vocab");
  const viewWarmup = document.getElementById("view-warmup");
  const youtubePlayer = document.getElementById("youtube-player-screen");
  const videoPlaceholder = document.getElementById("video-placeholder-screen");
  const vocabContent = document.getElementById("vocab-content-screen");
  const warmupContent = document.getElementById("warmup-content-screen");

  const viewMap = { video: viewVideo, vocab: viewVocab, warmup: viewWarmup };
  const viewButtons = controlsEl ? controlsEl.querySelectorAll("[data-view]") : [];

  let currentView = "video";
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
        videoPlaceholder.textContent = "動画が未設定です。管理画面で URL を登録してください。";
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
        '<p class="text-center text-lg text-slate-500">表示する単語がありません。管理画面で語彙を選択してください。</p>';
      return;
    }
    let html =
      '<table class="screen-vocab-table"><thead><tr>' +
      '<th>単語・熟語</th><th>品詞</th><th>意味（文脈）</th>' +
      "</tr></thead><tbody>";
    items.forEach(function (item) {
      html +=
        "<tr>" +
        '<td class="screen-vocab-word">' + escHtml(item.word) + "</td>" +
        '<td class="screen-vocab-pos">' + escHtml(item.part_of_speech) + "</td>" +
        "<td>" + escHtml(item.meaning) + "</td>" +
        "</tr>";
    });
    html += "</tbody></table>";
    vocabContent.innerHTML = html;
  }

  function renderWarmup(imageUrl, questions) {
    if (!warmupContent) return;
    if (!imageUrl && (!questions || !questions.length)) {
      warmupContent.innerHTML =
        '<p class="text-center text-lg text-slate-500">表示する導入質問がありません。管理画面で質問を選択してください。</p>';
      return;
    }
    let html = "";
    if (imageUrl) {
      html +=
        '<div class="mb-6 flex justify-center">' +
        '<img src="' + escHtml(imageUrl) + '" alt="Warmup illustration"' +
        ' class="max-h-[min(42vh,28rem)] w-auto max-w-full rounded-xl object-contain">' +
        "</div>";
    }
    if (questions && questions.length) {
      html += '<p class="mb-4 text-lg font-semibold text-sky-300 sm:text-xl">動画を見る前に考えてみよう</p>';
      html += '<ol class="space-y-4">';
      questions.forEach(function (q, i) {
        html +=
          '<li class="screen-warmup-q flex items-start gap-3">' +
          '<span class="screen-warmup-num">Q' + (i + 1) + ".</span>" +
          "<span>" + escHtml(q.text) + "</span>" +
          "</li>";
      });
      html += "</ol>";
    }
    warmupContent.innerHTML = html;
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
  }

  function configureControls(payload) {
    if (!controlsEl) return;
    const availability = {
      video: payload.has_video,
      vocab: payload.has_vocab,
      warmup: payload.has_warmup,
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
      (availability.vocab && "vocab") ||
      "video";
    setActiveView(defaultView);
  }

  async function loadScreen(classId) {
    if (!classId) {
      showError("クラスが指定されていません。管理画面から教室スクリーンを開いてください。");
      return;
    }

    showLoading(true);
    if (errorEl) {
      errorEl.classList.add("hidden");
      errorEl.classList.remove("flex");
    }

    try {
      const res = await fetch("/news/api/screen?class_id=" + encodeURIComponent(classId));
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || "読み込みに失敗しました");

      const cls = data.class;
      if (classLabel) classLabel.textContent = cls.name || "";

      await setVideoPlayer(cls.video);
      renderVocab(cls.vocabulary_data || []);
      renderWarmup(cls.warmup_image_url || "", cls.warmup_questions || []);
      configureControls(cls);
      showLoading(false);
    } catch (err) {
      showError(err.message || "読み込みに失敗しました");
    }
  }

  viewButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      if (btn.disabled) return;
      setActiveView(btn.dataset.view);
    });
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
    fullscreenBtn.title = document.fullscreenElement ? "全画面解除" : "全画面";
  });

  const urlParams = new URLSearchParams(window.location.search);
  const classId = urlParams.get("class") || window.SCREEN_INITIAL_CLASS_ID || "";
  loadScreen(classId);
})();
