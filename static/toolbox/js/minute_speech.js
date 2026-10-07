(function () {
  const KEY = "toolbox.minuteSpeech.v1";
  const HINTS = {
    1: "Answer → Detail 1 → Detail 2 → Wrap-up",
    2: "Position → Reason 1 (+example) → Reason 2 (+example) → Conclusion",
  };
  const TYPE_LABEL = { 1: "タイプ1：身近なテーマ", 2: "タイプ2：立場を選んで意見", mixed: "両方からランダム" };

  const setup = document.getElementById("ms-setup");
  const stage = document.getElementById("ms-stage");
  const els = {};
  document.querySelectorAll("[id^='ms-']").forEach((node) => { els[node.id] = node; });

  let store = loadStore();
  let classes = [];
  let topic = null;
  let phase = "idle";
  let sessionNo = 0;
  let sessionSkipped = [];
  let marked = false;
  let running = false;
  let endAt = 0;
  let remainingMs = 0;
  let durationMs = 60000;
  let tickId = 0;
  let wakeLock = null;
  let switchTimer = 0;
  let themes = [];
  let activeTheme = "";
  let searchOffset = 0;
  let audio = null;

  function loadStore() {
    try {
      const data = JSON.parse(localStorage.getItem(KEY) || "null");
      if (data && typeof data === "object") {
        data.history = data.history || {};
        data.rounds = data.rounds || {};
        data.hiddenTopicIds = data.hiddenTopicIds || [];
        data.prefs = data.prefs || {};
        data.recentQueries = data.recentQueries || [];
        return data;
      }
    } catch (_) {}
    return { history: {}, rounds: {}, hiddenTopicIds: [], prefs: {}, recentQueries: [], lastBackupAt: null };
  }

  function saveStore() {
    localStorage.setItem(KEY, JSON.stringify(store));
  }

  function classId() {
    return els["ms-class"].value || "";
  }

  function typeValue() {
    return els["ms-type"].value;
  }

  function usedRows(typeNum) {
    const id = classId();
    if (!id) return [];
    const bucket = (store.history[id] || {})[String(typeNum)] || [];
    return bucket;
  }

  function usedIds() {
    const type = typeValue();
    const types = type === "mixed" ? [1, 2] : [Number(type)];
    const ids = [];
    types.forEach((num) => usedRows(num).forEach((row) => ids.push(row.id)));
    return ids;
  }

  function filters() {
    return {
      type: typeValue(),
      level_max: Number(els["ms-level"].value),
      include_flagged: els["ms-flagged"].checked,
      include_unleveled: els["ms-unleveled"].checked,
    };
  }

  function readPrefsIntoForm() {
    const prefs = store.prefs || {};
    if (prefs.type) els["ms-type"].value = prefs.type;
    if (prefs.level) els["ms-level"].value = String(prefs.level);
    if (prefs.prep) els["ms-prep"].value = prefs.prep;
    if (prefs.speak) els["ms-speak"].value = prefs.speak;
    if (prefs.format) els["ms-format"].value = prefs.format;
    if (prefs.classId) els["ms-class"].value = prefs.classId;
    els["ms-unleveled"].checked = prefs.unleveled !== false;
    els["ms-flagged"].checked = !!prefs.flagged;
    els["ms-auto"].checked = prefs.auto !== false;
    els["ms-ja"].checked = !!prefs.ja;
    els["ms-hints"].checked = prefs.hints !== false;
    els["ms-blur"].checked = prefs.blur !== false;
    els["ms-exclude-used"].checked = !!prefs.excludeUsed;
    els["ms-ai"].checked = !!prefs.ai;
  }

  function writePrefs() {
    store.prefs = {
      classId: classId(),
      type: typeValue(),
      level: Number(els["ms-level"].value),
      prep: Number(els["ms-prep"].value) || 60,
      speak: Number(els["ms-speak"].value) || 60,
      format: els["ms-format"].value,
      unleveled: els["ms-unleveled"].checked,
      flagged: els["ms-flagged"].checked,
      auto: els["ms-auto"].checked,
      ja: els["ms-ja"].checked,
      hints: els["ms-hints"].checked,
      blur: els["ms-blur"].checked,
      excludeUsed: els["ms-exclude-used"].checked,
      ai: els["ms-ai"].checked,
    };
    saveStore();
  }

  function fillClasses() {
    classes = window.ToolboxClasses ? window.ToolboxClasses.load() : [];
    const select = els["ms-class"];
    const current = select.value;
    select.innerHTML = '<option value="">クラスなし（記録しない）</option>';
    classes.forEach((row) => {
      const option = document.createElement("option");
      option.value = row.id;
      option.textContent = row.name;
      select.appendChild(option);
    });
    if (current) select.value = current;
  }

  function topicNumber(item) {
    const order = Number(item && item.source_order);
    if (!order || order > 10000) return "";
    return `No.${order}`;
  }

  function esc(value) {
    return String(value || "").replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[ch]));
  }

  function highlight(text, query) {
    const safe = esc(text);
    const parts = String(query || "").replace(/[「」"]/g, " ").split(/\s+/).filter((part) => part.length >= 2);
    let html = safe;
    parts.forEach((part) => {
      const pattern = new RegExp(esc(part).replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "ig");
      html = html.replace(pattern, (match) => `<mark class="ms-hit">${match}</mark>`);
    });
    return html;
  }

  function formatTime(ms) {
    const total = Math.max(0, Math.ceil(ms / 1000));
    const minutes = Math.floor(total / 60);
    const seconds = total % 60;
    return `${minutes}:${String(seconds).padStart(2, "0")}`;
  }

  function fitTopic() {
    const box = els["ms-topic-box"];
    const text = els["ms-topic-text"];
    if (!box || !text) return;
    const long = (topic && Number(topic.words) >= 60) || stage.classList.contains("is-long");
    let low = 2.4;
    let high = long ? 7.5 : 11;
    for (let i = 0; i < 12; i += 1) {
      const mid = (low + high) / 2;
      text.style.fontSize = `${mid}vh`;
      if (text.scrollHeight > box.clientHeight * 0.72 || text.scrollWidth > box.clientWidth) high = mid;
      else low = mid;
    }
    text.style.fontSize = `${low}vh`;
  }

  function renderTopic() {
    if (!topic) return;
    els["ms-topic-text"].textContent = topic.text || "";
    const suffix = topic.suffix === "details";
    els["ms-suffix"].hidden = !suffix;
    els["ms-suffix"].textContent = suffix ? "Include specific details." : "";
    const showJa = els["ms-ja"].checked && topic.ja;
    els["ms-ja-line"].hidden = !showJa;
    els["ms-ja-line"].textContent = showJa ? topic.ja : "";
    const showHint = els["ms-hints"].checked && (phase === "prep" || phase === "idle");
    els["ms-hint"].hidden = !showHint;
    els["ms-hint"].textContent = showHint ? (HINTS[topic.type] || "") : "";
    stage.classList.toggle("is-long", Number(topic.words) >= 60);
    const number = topicNumber(topic);
    els["ms-meta-type"].textContent = `${TYPE_LABEL[topic.type] || ""}${number ? " " + number : ""}`;
    const selected = classes.find((row) => row.id === classId());
    els["ms-meta-class"].textContent = selected ? selected.name : "クラスなし";
    els["ms-meta-no"].textContent = sessionNo ? `#${sessionNo}` : "";
    requestAnimationFrame(fitTopic);
  }

  function setPhaseClass() {
    stage.classList.toggle("is-prep", phase === "prep" || phase === "idle");
    stage.classList.toggle("is-speak", phase === "speak" || phase === "speakA" || phase === "speakB");
    const warn = running && remainingMs > 0 && remainingMs <= 10000 && phase !== "switch";
    stage.classList.toggle("is-warn", warn);
    stage.classList.toggle("is-end", phase === "done" || remainingMs <= 0 && phase !== "idle" && phase !== "switch");
  }

  function renderClock() {
    const names = {
      idle: "READY",
      prep: "PREP",
      speak: "SPEAK",
      speakA: "SPEAK A",
      speakB: "SPEAK B",
      switch: "SWITCH",
      done: "TIME!",
    };
    els["ms-phase"].textContent = names[phase] || "";
    if (phase === "switch") {
      els["ms-time"].textContent = "Switch!";
      els["ms-time"].className = "ms-time ms-switch";
    } else if (phase === "done") {
      els["ms-time"].textContent = "TIME!";
      els["ms-time"].className = "ms-time is-time";
    } else {
      els["ms-time"].textContent = formatTime(phase === "idle" ? (Number(els["ms-prep"].value) || 60) * 1000 : remainingMs);
      els["ms-time"].className = "ms-time";
    }
    els["ms-start"].hidden = phase !== "idle" && phase !== "done";
    els["ms-start"].textContent = phase === "done" ? "次の操作" : "Start";
    els["ms-pause"].hidden = phase === "idle" || phase === "done" || phase === "switch";
    els["ms-pause"].textContent = running ? "一時停止" : "再開";
    els["ms-again"].hidden = phase !== "done";
    els["ms-undo"].hidden = phase !== "done";
    setPhaseClass();
  }

  function unlockAudio() {
    if (audio) return;
    audio = new Audio("/static/toolbox/sounds/timer_end.wav");
    audio.preload = "auto";
    audio.volume = 0.35;
    audio.play().then(() => {
      audio.pause();
      audio.currentTime = 0;
    }).catch(() => {});
  }

  function beep(freq, seconds) {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.frequency.value = freq;
      gain.gain.value = 0.05;
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + seconds);
      setTimeout(() => ctx.close(), seconds * 1000 + 200);
    } catch (_) {}
  }

  function playEnd() {
    if (audio) {
      audio.loop = false;
      audio.currentTime = 0;
      audio.play().catch(() => beep(520, 0.35));
      return;
    }
    beep(520, 0.35);
  }

  function playCue() {
    beep(880, 0.12);
  }

  async function requestWake() {
    try {
      if (navigator.wakeLock) wakeLock = await navigator.wakeLock.request("screen");
    } catch (_) {}
  }

  function releaseWake() {
    if (wakeLock) {
      wakeLock.release().catch(() => {});
      wakeLock = null;
    }
  }

  function stopTick() {
    clearInterval(tickId);
    running = false;
    releaseWake();
  }

  function speakPhases() {
    return els["ms-format"].value === "pair" ? ["speakA", "speakB"] : ["speak"];
  }

  function beginPhase(next) {
    clearTimeout(switchTimer);
    phase = next;
    if (next === "prep") durationMs = (Number(els["ms-prep"].value) || 60) * 1000;
    else if (next === "speak" || next === "speakA" || next === "speakB") durationMs = (Number(els["ms-speak"].value) || 60) * 1000;
    else durationMs = 0;
    remainingMs = durationMs;
    if ((next === "speak" || next === "speakA") && !marked) {
      markUsed();
      marked = true;
    }
    renderTopic();
    renderClock();
    if (next === "switch") {
      playCue();
      switchTimer = setTimeout(() => beginPhase("speakB"), 1600);
      return;
    }
    if (next === "done") {
      playEnd();
      return;
    }
    startRunning();
  }

  function startRunning() {
    unlockAudio();
    running = true;
    endAt = Date.now() + remainingMs;
    requestWake();
    clearInterval(tickId);
    tickId = setInterval(tick, 100);
    tick();
  }

  function tick() {
    remainingMs = Math.max(0, endAt - Date.now());
    renderClock();
    if (remainingMs > 0) return;
    stopTick();
    if (phase === "prep") {
      playCue();
      if (els["ms-auto"].checked) beginPhase(speakPhases()[0]);
      else renderClock();
      return;
    }
    if (phase === "speakA") {
      beginPhase("switch");
      return;
    }
    if (phase === "speak" || phase === "speakB") {
      phase = "done";
      playEnd();
      renderClock();
    }
  }

  function toggleRun() {
    unlockAudio();
    if (phase === "idle") {
      beginPhase("prep");
      return;
    }
    if (phase === "done" || phase === "switch") return;
    if (phase === "prep" && !running && remainingMs <= 0) {
      beginPhase(speakPhases()[0]);
      return;
    }
    if (running) {
      remainingMs = Math.max(0, endAt - Date.now());
      stopTick();
      renderClock();
      return;
    }
    startRunning();
  }

  function markUsed() {
    const id = classId();
    if (!id || !topic) return;
    const typeKey = String(topic.type || 1);
    store.history[id] = store.history[id] || { 1: [], 2: [] };
    store.history[id][typeKey] = store.history[id][typeKey] || [];
    if (!store.history[id][typeKey].some((row) => row.id === topic.id)) {
      store.history[id][typeKey].push({
        id: topic.id,
        usedAt: new Date().toISOString(),
        text: topic.text,
        suffix: topic.suffix,
        type: topic.type,
        ja: topic.ja || "",
        source_order: topic.source_order,
      });
    }
    saveStore();
  }

  function undoUsed() {
    const id = classId();
    if (!id || !topic) return;
    const typeKey = String(topic.type || 1);
    const rows = ((store.history[id] || {})[typeKey] || []).filter((row) => row.id !== topic.id);
    store.history[id][typeKey] = rows;
    marked = false;
    saveStore();
  }

  function excludeIds() {
    return usedIds().concat(sessionSkipped, store.hiddenTopicIds || []);
  }

  async function drawNext(retried) {
    const data = await toolboxFetch("/toolbox/api/minute-speech/draw", {
      method: "POST",
      body: JSON.stringify(Object.assign({ exclude_ids: excludeIds() }, filters())),
    });
    if (!data.topic) {
      if (retried || !classId()) {
        alert("条件に合うお題がありません。難易度やフラグの設定を確認してください。");
        return false;
      }
      const ok = confirm("このクラスの選んだタイプは全部使い終わりました。履歴をリセットして最初から出しますか？");
      if (!ok) return false;
      resetTypes();
      return drawNext(true);
    }
    topic = data.topic;
    sessionNo += 1;
    marked = false;
    phase = "idle";
    stopTick();
    remainingMs = (Number(els["ms-prep"].value) || 60) * 1000;
    showStage();
    renderTopic();
    renderClock();
    return true;
  }

  function resetTypes() {
    const id = classId();
    if (!id) return;
    const types = typeValue() === "mixed" ? ["1", "2"] : [String(typeValue())];
    store.history[id] = store.history[id] || {};
    store.rounds[id] = store.rounds[id] || {};
    types.forEach((key) => {
      store.history[id][key] = [];
      store.rounds[id][key] = (Number(store.rounds[id][key]) || 1) + 1;
    });
    sessionSkipped = [];
    saveStore();
  }

  function showStage() {
    setup.hidden = true;
    stage.hidden = false;
    stage.classList.add("is-on");
    if (window.ToolboxDisplay && !window.ToolboxDisplay.isOn()) window.ToolboxDisplay.enter();
  }

  function showSetup() {
    stopTick();
    clearTimeout(switchTimer);
    stage.classList.remove("is-on");
    stage.hidden = true;
    setup.hidden = false;
    if (window.ToolboxDisplay && window.ToolboxDisplay.isOn()) window.ToolboxDisplay.exit();
    renderHistory();
  }

  function skipTopic() {
    if (topic && !sessionSkipped.includes(topic.id)) sessionSkipped.push(topic.id);
    drawNext().catch((err) => alert(err.message));
  }

  function hideTopic() {
    if (!topic) return;
    if (!store.hiddenTopicIds.includes(topic.id)) store.hiddenTopicIds.push(topic.id);
    saveStore();
    skipTopic();
  }

  function renderRecent() {
    els["ms-recent"].innerHTML = "";
    (store.recentQueries || []).slice(0, 5).forEach((query) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "tb-btn";
      button.textContent = query;
      button.addEventListener("click", () => {
        els["ms-q"].value = query;
        runSearch(true);
      });
      els["ms-recent"].appendChild(button);
    });
  }

  function rememberQuery(query) {
    store.recentQueries = [query].concat((store.recentQueries || []).filter((item) => item !== query)).slice(0, 5);
    saveStore();
    renderRecent();
  }

  function renderThemes() {
    const box = els["ms-themes"];
    box.innerHTML = "";
    themes.slice(0, 24).forEach((theme) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "tb-btn";
      button.textContent = theme;
      if (theme === activeTheme) button.classList.add("tb-btn-primary");
      button.addEventListener("click", () => {
        activeTheme = activeTheme === theme ? "" : theme;
        renderThemes();
        runSearch(true);
      });
      box.appendChild(button);
    });
  }

  async function loadStats() {
    const params = new URLSearchParams({
      type: typeValue() === "mixed" ? "" : typeValue(),
      level_max: els["ms-level"].value,
      include_flagged: els["ms-flagged"].checked ? "1" : "0",
      include_unleveled: els["ms-unleveled"].checked ? "1" : "0",
    });
    const data = await toolboxFetch(`/toolbox/api/minute-speech/stats?${params}`);
    themes = data.themes || [];
    renderThemes();
    const type = typeValue();
    const numbers = type === "mixed" ? ["1", "2"] : [String(type)];
    let active = 0;
    let used = 0;
    numbers.forEach((key) => {
      active += (data.types[key] || {}).active || 0;
      used += usedRows(Number(key)).length;
    });
    const rounds = numbers.map((key) => {
      const count = ((store.rounds[classId()] || {})[key]) || 1;
      return `${key === "1" ? "タイプ1" : "タイプ2"} ${count}周目`;
    }).join(" / ");
    els["ms-progress"].textContent = classId()
      ? `使用済み ${used}／有効 ${active}。${rounds}`
      : "クラスなしのため、使用済みは記録しません。";
    const backup = store.lastBackupAt ? new Date(store.lastBackupAt) : null;
    const old = !backup || (Date.now() - backup.getTime()) > 30 * 86400000;
    els["ms-backup-note"].textContent = old && used
      ? `書き出しから30日以上たっています。${backup ? backup.toLocaleDateString() : "未書き出し"}`
      : (backup ? `前回の書き出し ${backup.toLocaleDateString()}` : "");
    return data;
  }

  function renderHistory() {
    const box = els["ms-history"];
    box.innerHTML = "";
    const type = typeValue();
    const numbers = type === "mixed" ? [1, 2] : [Number(type)];
    const rows = [];
    numbers.forEach((num) => usedRows(num).forEach((row) => rows.push(row)));
    rows.sort((a, b) => String(b.usedAt).localeCompare(String(a.usedAt)));
    rows.slice(0, 40).forEach((row) => {
      const card = document.createElement("article");
      card.className = "ms-card is-blur";
      card.innerHTML = `<div class="ms-meta"><span class="tb-badge">タイプ${row.type}${topicNumber(row) ? " " + topicNumber(row) : ""}</span><span class="tb-muted">${esc(row.usedAt || "").slice(0, 16).replace("T", " ")}</span></div><p class="ms-card-text">${esc(row.text)}</p>`;
      card.querySelector(".ms-card-text").addEventListener("click", () => card.classList.remove("is-blur"));
      const button = document.createElement("button");
      button.type = "button";
      button.className = "tb-btn";
      button.textContent = "未使用に戻す";
      button.addEventListener("click", () => {
        const key = String(row.type);
        const id = classId();
        store.history[id][key] = (store.history[id][key] || []).filter((item) => item.id !== row.id);
        saveStore();
        renderHistory();
        loadStats().catch(() => {});
      });
      card.appendChild(button);
      box.appendChild(card);
    });
    loadStats().catch((err) => { els["ms-progress"].textContent = err.message; });
  }

  function useSearched(item) {
    const go = () => {
      topic = item;
      sessionNo += 1;
      marked = false;
      phase = "idle";
      stopTick();
      remainingMs = (Number(els["ms-prep"].value) || 60) * 1000;
      showStage();
      renderTopic();
      renderClock();
    };
    if (item.used && !confirm("このお題は使用済みです。もう一度使いますか？")) return;
    go();
  }

  function renderResults(items, append) {
    const box = els["ms-results"];
    if (!append) box.innerHTML = "";
    const blur = els["ms-blur"].checked;
    items.forEach((item) => {
      const card = document.createElement("article");
      card.className = blur ? "ms-card is-blur" : "ms-card";
      card.innerHTML = `<div class="ms-meta"><span class="tb-badge">タイプ${item.type}${topicNumber(item) ? " " + topicNumber(item) : ""}</span>${item.level ? `<span class="tb-badge">L${item.level}</span>` : ""}${item.used ? '<span class="tb-badge">使用済み</span>' : ""}${(item.flags || []).length ? '<span class="tb-badge tb-badge-mute">配慮</span>' : ""}</div><p class="ms-card-text">${highlight(item.text, els["ms-q"].value)}</p>${item.ja ? `<p class="tb-muted">${esc(item.ja)}</p>` : ""}`;
      card.querySelector(".ms-card-text").addEventListener("click", () => card.classList.remove("is-blur"));
      const use = document.createElement("button");
      use.type = "button";
      use.className = "tb-btn tb-btn-primary";
      use.textContent = "このお題を使う";
      use.addEventListener("click", () => useSearched(item));
      const hide = document.createElement("button");
      hide.type = "button";
      hide.className = "tb-btn";
      hide.textContent = "今後出さない";
      hide.addEventListener("click", () => {
        if (!store.hiddenTopicIds.includes(item.id)) store.hiddenTopicIds.push(item.id);
        saveStore();
        card.remove();
      });
      card.append(use, hide);
      box.appendChild(card);
    });
  }

  async function runSearch(reset) {
    const query = els["ms-q"].value.trim();
    if (query.length < 2) {
      els["ms-search-status"].textContent = "検索語は2文字以上にしてください。";
      return;
    }
    if (reset) searchOffset = 0;
    rememberQuery(query);
    els["ms-ai"].checked ? els["ms-q"].placeholder = "AI検索（例: 部活の経験が話せる話題）" : els["ms-q"].placeholder = "番号・語句（例: 12、1-12、school）";
    els["ms-search-status"].textContent = "検索中…";
    try {
      const data = await toolboxFetch("/toolbox/api/minute-speech/search", {
        method: "POST",
        body: JSON.stringify(Object.assign({
          q: query,
          mode: els["ms-ai"].checked ? "ai" : "keyword",
          used_ids: usedIds(),
          hidden_ids: store.hiddenTopicIds,
          exclude_used: els["ms-exclude-used"].checked,
          themes: activeTheme ? [activeTheme] : [],
          limit: 20,
          offset: searchOffset,
        }, filters())),
      });
      renderResults(data.results || [], !reset && searchOffset > 0);
      searchOffset += (data.results || []).length;
      els["ms-search-status"].textContent = data.notice || ((data.results || []).length ? "" : "見つかりませんでした。");
      if (data.has_more) {
        const more = document.createElement("button");
        more.type = "button";
        more.className = "tb-btn";
        more.textContent = "さらに表示";
        more.addEventListener("click", () => {
          more.remove();
          runSearch(false);
        });
        els["ms-results"].appendChild(more);
      }
    } catch (err) {
      const aiDown = els["ms-ai"].checked && (err.status === 409 || err.status === 429 || err.status === 502);
      els["ms-search-status"].textContent = aiDown
        ? `${err.message} 一致検索に切り替えてください。`
        : err.message;
      if (err.data && err.data.code === "index_missing") els["ms-ai"].checked = false;
    }
  }

  function exportHistory() {
    const blob = new Blob([JSON.stringify({
      version: 1,
      exportedAt: new Date().toISOString(),
      history: store.history,
      rounds: store.rounds,
      hiddenTopicIds: store.hiddenTopicIds,
      prefs: store.prefs,
    }, null, 2)], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "minute-speech-history.json";
    link.click();
    store.lastBackupAt = new Date().toISOString();
    saveStore();
    renderHistory();
  }

  function importHistory(file) {
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const data = JSON.parse(String(reader.result || ""));
        if (!data || typeof data.history !== "object") throw new Error("形式が違います。");
        store.history = data.history || {};
        store.rounds = data.rounds || {};
        store.hiddenTopicIds = data.hiddenTopicIds || [];
        if (data.prefs) store.prefs = Object.assign(store.prefs, data.prefs);
        store.lastBackupAt = new Date().toISOString();
        saveStore();
        readPrefsIntoForm();
        renderHistory();
      } catch (err) {
        alert(err.message || "読み込めませんでした。");
      }
    };
    reader.readAsText(file);
  }

  document.getElementById("ms-tab-setup").addEventListener("click", () => {
    els["ms-panel-setup"].hidden = false;
    els["ms-panel-history"].hidden = true;
  });
  document.getElementById("ms-tab-history").addEventListener("click", () => {
    els["ms-panel-setup"].hidden = true;
    els["ms-panel-history"].hidden = false;
    renderHistory();
  });
  els["ms-presets"].addEventListener("click", (ev) => {
    const button = ev.target.closest("button");
    if (!button) return;
    if (button.dataset.prep) els["ms-prep"].value = button.dataset.prep;
    if (button.dataset.speak) els["ms-speak"].value = button.dataset.speak;
    writePrefs();
  });
  ["ms-class", "ms-type", "ms-level", "ms-prep", "ms-speak", "ms-format", "ms-unleveled", "ms-flagged", "ms-auto", "ms-ja", "ms-hints", "ms-blur", "ms-exclude-used", "ms-ai"].forEach((id) => {
    els[id].addEventListener("change", () => {
      writePrefs();
      if (els["ms-ai"].checked) els["ms-q"].placeholder = "AI検索（例: 旅行に関するお題）";
      else els["ms-q"].placeholder = "番号・語句（例: 12、1-12、school）";
    });
  });
  els["ms-draw"].addEventListener("click", () => {
    writePrefs();
    drawNext().catch((err) => alert(err.message));
  });
  els["ms-search-btn"].addEventListener("click", () => runSearch(true));
  els["ms-q"].addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") {
      ev.preventDefault();
      runSearch(true);
    }
  });
  els["ms-start"].addEventListener("click", toggleRun);
  els["ms-pause"].addEventListener("click", toggleRun);
  els["ms-clock"].addEventListener("click", () => {
    if (window.ToolboxDisplay && window.ToolboxDisplay.isOn()) return;
    toggleRun();
  });
  els["ms-reset"].addEventListener("click", () => {
    stopTick();
    clearTimeout(switchTimer);
    phase = "idle";
    remainingMs = (Number(els["ms-prep"].value) || 60) * 1000;
    renderTopic();
    renderClock();
  });
  els["ms-next"].addEventListener("click", () => {
    if (topic && phase !== "speak" && phase !== "speakA" && phase !== "speakB" && phase !== "done" && !marked) {
      if (!sessionSkipped.includes(topic.id)) sessionSkipped.push(topic.id);
    }
    drawNext().catch((err) => alert(err.message));
  });
  els["ms-again"].addEventListener("click", () => {
    phase = "idle";
    stopTick();
    renderTopic();
    renderClock();
  });
  els["ms-undo"].addEventListener("click", () => {
    undoUsed();
    alert("使用済みを取り消しました。");
  });
  els["ms-skip"].addEventListener("click", skipTopic);
  els["ms-hide"].addEventListener("click", hideTopic);
  els["ms-toggle-ja"].addEventListener("click", () => {
    els["ms-ja"].checked = !els["ms-ja"].checked;
    writePrefs();
    renderTopic();
  });
  els["ms-toggle-hint"].addEventListener("click", () => {
    els["ms-hints"].checked = !els["ms-hints"].checked;
    writePrefs();
    renderTopic();
  });
  els["ms-back"].addEventListener("click", showSetup);
  els["ms-export"].addEventListener("click", exportHistory);
  els["ms-import"].addEventListener("click", () => els["ms-import-file"].click());
  els["ms-import-file"].addEventListener("change", () => {
    const file = els["ms-import-file"].files && els["ms-import-file"].files[0];
    if (file) importHistory(file);
  });
  els["ms-reset-type"].addEventListener("click", () => {
    if (!classId()) {
      alert("クラスなしでは履歴がありません。");
      return;
    }
    if (!confirm("このクラス・このタイプの履歴を消して、最初から出しますか？")) return;
    resetTypes();
    renderHistory();
  });

  document.addEventListener("keydown", (ev) => {
    if (ev.target && /INPUT|TEXTAREA|SELECT/.test(ev.target.tagName)) return;
    if (stage.hidden) return;
    const key = ev.key.toLowerCase();
    if (key === " " && window.ToolboxDisplay && window.ToolboxDisplay.isOn()) return;
    if (key === " ") {
      ev.preventDefault();
      toggleRun();
    }
    if (key === "n") {
      ev.preventDefault();
      els["ms-next"].click();
    }
    if (key === "r") {
      ev.preventDefault();
      els["ms-reset"].click();
    }
    if (key === "j") els["ms-toggle-ja"].click();
    if (key === "h") els["ms-toggle-hint"].click();
  });
  document.addEventListener("visibilitychange", () => {
    if (running) tick();
  });
  window.addEventListener("resize", fitTopic);
  if (window.ToolboxDisplay) {
    ToolboxDisplay.init({
      onNext: toggleRun,
      onPrev: () => els["ms-reset"].click(),
    });
  }

  fillClasses();
  readPrefsIntoForm();
  renderRecent();
  loadStats().catch(() => {});
})();
