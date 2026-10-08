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
  let phaseNext = "prep";
  let themes = [];
  let teachers = [];
  let scopeTeacher = "";
  let scopeClass = "";
  let activeTheme = "";
  let classMenuOpen = false;
  let catType = 1;
  let catOffset = 0;
  let catPosReady = false;
  let lastSavedPos = "";
  const CAT_PAGE = 50;
  const catalogIds = { 1: null, 2: null };
  let catalogCount = 0;
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
        data.scopes = data.scopes || {};
        data.lastClass = data.lastClass || {};
        data.recentQueries = data.recentQueries || [];
        data.nextUse = data.nextUse || {};
        data.archived = data.archived || {};
        return data;
      }
    } catch (_) {}
    return { history: {}, rounds: {}, hiddenTopicIds: [], prefs: {}, scopes: {}, lastClass: {}, recentQueries: [], nextUse: {}, archived: {}, lastBackupAt: null };
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

  function archivedYears(classKey) {
    const id = classKey || classId();
    const years = (store.archived || {})[id] || {};
    return years && typeof years === "object" ? years : {};
  }

  function archivedRows(typeNum) {
    const rows = [];
    Object.values(archivedYears()).forEach((list) => {
      if (!Array.isArray(list)) return;
      list.forEach((row) => {
        if (typeNum == null || Number(row.type) === Number(typeNum)) rows.push(row);
      });
    });
    return rows;
  }

  function spentRows(typeNum) {
    return usedRows(typeNum).concat(archivedRows(typeNum));
  }

  function usedIds() {
    const type = typeValue();
    const types = type === "mixed" ? [1, 2] : [Number(type)];
    const ids = [];
    types.forEach((num) => spentRows(num).forEach((row) => ids.push(row.id)));
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

  const DEFAULT_SETTINGS = {
    type: "1",
    level: 2,
    prep: 60,
    speak: 60,
    format: "solo",
    unleveled: true,
    flagged: false,
    auto: true,
    ja: false,
    hints: true,
    blur: true,
    excludeUsed: false,
    ai: false,
  };

  function scopeKey(teacher, klass) {
    return `${teacher || ""}::${klass || ""}`;
  }

  function settingsFromForm() {
    return {
      type: typeValue(),
      level: Number(els["ms-level"].value) || 2,
      prep: Number(els["ms-prep"].value) || 60,
      speak: Number(els["ms-speak"].value) || 60,
      format: els["ms-format"].value || "solo",
      unleveled: els["ms-unleveled"].checked,
      flagged: els["ms-flagged"].checked,
      auto: els["ms-auto"].checked,
      ja: els["ms-ja"].checked,
      hints: els["ms-hints"].checked,
      blur: els["ms-blur"].checked,
      excludeUsed: els["ms-exclude-used"].checked,
      ai: els["ms-ai"].checked,
    };
  }

  function pickSettings(prefs) {
    if (!prefs || typeof prefs !== "object") return null;
    if (!prefs.type && prefs.level == null && prefs.prep == null && prefs.format == null) return null;
    return {
      type: prefs.type || DEFAULT_SETTINGS.type,
      level: Number(prefs.level) || DEFAULT_SETTINGS.level,
      prep: Number(prefs.prep) || DEFAULT_SETTINGS.prep,
      speak: Number(prefs.speak) || DEFAULT_SETTINGS.speak,
      format: prefs.format || DEFAULT_SETTINGS.format,
      unleveled: prefs.unleveled !== false,
      flagged: !!prefs.flagged,
      auto: prefs.auto !== false,
      ja: !!prefs.ja,
      hints: prefs.hints !== false,
      blur: prefs.blur !== false,
      excludeUsed: !!prefs.excludeUsed,
      ai: !!prefs.ai,
    };
  }

  function migrateScopes() {
    store.scopes = store.scopes && typeof store.scopes === "object" ? store.scopes : {};
    store.lastClass = store.lastClass && typeof store.lastClass === "object" ? store.lastClass : {};
    const prefs = store.prefs || {};
    const legacy = pickSettings(prefs);
    if (!legacy) return;
    const key = scopeKey(prefs.teacherId, prefs.classId);
    if (!store.scopes[key]) store.scopes[key] = legacy;
    if (prefs.teacherId) store.lastClass[prefs.teacherId] = prefs.classId || "";
    store.prefs = { teacherId: prefs.teacherId || "", classId: prefs.classId || "" };
  }

  function settingsFor(teacher, klass) {
    const scopes = store.scopes || {};
    const exact = scopes[scopeKey(teacher, klass)];
    if (exact) return exact;
    if (klass) {
      const suffix = `::${klass}`;
      const found = Object.keys(scopes).find((key) => key.endsWith(suffix) && scopes[key]);
      if (found) return scopes[found];
      const teacherDefault = scopes[scopeKey(teacher, "")];
      if (teacherDefault) return teacherDefault;
    }
    return null;
  }

  function applySettings(prefs) {
    const next = Object.assign({}, DEFAULT_SETTINGS, prefs || {});
    els["ms-type"].value = next.type;
    els["ms-level"].value = String(next.level);
    els["ms-prep"].value = String(next.prep);
    els["ms-speak"].value = String(next.speak);
    els["ms-format"].value = next.format;
    els["ms-unleveled"].checked = next.unleveled !== false;
    els["ms-flagged"].checked = !!next.flagged;
    els["ms-auto"].checked = next.auto !== false;
    els["ms-ja"].checked = !!next.ja;
    els["ms-hints"].checked = next.hints !== false;
    els["ms-blur"].checked = next.blur !== false;
    els["ms-exclude-used"].checked = !!next.excludeUsed;
    els["ms-ai"].checked = !!next.ai;
    els["ms-q"].placeholder = next.ai ? "AI検索（例: 旅行に関するお題）" : "番号・語句（例: 12、1-12、school）";
  }

  function rememberScope() {
    store.scopes = store.scopes || {};
    store.lastClass = store.lastClass || {};
    store.scopes[scopeKey(scopeTeacher, scopeClass)] = settingsFromForm();
    if (scopeTeacher) store.lastClass[scopeTeacher] = scopeClass;
    store.prefs = { teacherId: scopeTeacher, classId: scopeClass };
    saveStore();
  }

  function enterScope(teacher, klass) {
    scopeTeacher = teacher || "";
    scopeClass = klass || "";
    applySettings(settingsFor(scopeTeacher, scopeClass) || DEFAULT_SETTINGS);
    store.lastClass = store.lastClass || {};
    if (scopeTeacher) store.lastClass[scopeTeacher] = scopeClass;
    store.prefs = { teacherId: scopeTeacher, classId: scopeClass };
    saveStore();
  }

  function bindScope(teacher, klass, settings) {
    scopeTeacher = teacher || "";
    scopeClass = klass || "";
    store.scopes = store.scopes || {};
    store.lastClass = store.lastClass || {};
    store.scopes[scopeKey(scopeTeacher, scopeClass)] = settings;
    if (scopeTeacher) store.lastClass[scopeTeacher] = scopeClass;
    store.prefs = { teacherId: scopeTeacher, classId: scopeClass };
    saveStore();
  }

  async function confirmDelete(message) {
    if (!confirm(message)) return false;
    const password = prompt("削除するには管理パスワードを入力してください");
    if (password == null || password === "") return false;
    try {
      await toolboxFetch("/toolbox/api/minute-speech/confirm-delete", {
        method: "POST",
        body: JSON.stringify({ password }),
      });
      return true;
    } catch (err) {
      alert(err.message || "パスワードが違います。");
      return false;
    }
  }

  function selectClass(klass) {
    const select = els["ms-class"];
    const exists = Array.from(select.options).some((option) => option.value === (klass || ""));
    select.value = exists ? (klass || "") : "";
    updateClassToggle();
  }

  function readPrefsIntoForm() {
    migrateScopes();
    const prefs = store.prefs || {};
    if (prefs.teacherId && teachers.some((row) => row.id === prefs.teacherId)) {
      els["ms-teacher"].value = prefs.teacherId;
    }
    fillClasses();
    const savedClass = prefs.classId || (store.lastClass || {})[teacherId()] || "";
    selectClass(savedClass);
    enterScope(teacherId(), classId());
  }

  function writePrefs() {
    rememberScope();
  }

  function teacherId() {
    return els["ms-teacher"].value || "";
  }

  function newLocalId() {
    return (crypto.randomUUID && crypto.randomUUID()) || String(Date.now());
  }

  function fillTeachers() {
    teachers = window.ToolboxClasses ? window.ToolboxClasses.loadTeachers() : [];
    classes = window.ToolboxClasses ? window.ToolboxClasses.load() : [];
    const select = els["ms-teacher"];
    const current = select.value;
    select.innerHTML = "";
    if (!teachers.length) {
      const empty = document.createElement("option");
      empty.value = "";
      empty.textContent = "教員を追加してください";
      select.appendChild(empty);
    }
    teachers.forEach((row) => {
      const option = document.createElement("option");
      option.value = row.id;
      option.textContent = row.name;
      select.appendChild(option);
    });
    if (current && teachers.some((row) => row.id === current)) select.value = current;
  }

  function teacherClasses() {
    const teacher = teacherId();
    if (!teacher) return [];
    return classes.filter((row) => row.teacher_id === teacher);
  }

  function activeTeacherClasses() {
    return teacherClasses().filter((row) => !row.hidden_year);
  }

  function moveListedClass(list, id, direction) {
    const index = list.findIndex((row) => row.id === id);
    const next = index + direction;
    if (!id || index < 0 || next < 0 || next >= list.length) return;
    const from = classes.indexOf(list[index]);
    const to = classes.indexOf(list[next]);
    if (from < 0 || to < 0) return;
    const swapped = classes[from];
    classes[from] = classes[to];
    classes[to] = swapped;
    classes = window.ToolboxClasses.save(classes);
    const selected = classId();
    fillClasses();
    selectClass(selected);
    classMenuOpen = true;
    updateClassToggle();
  }

  function classLabel() {
    const row = classes.find((item) => item.id === classId());
    if (!row) return "クラスなし（記録しない）";
    return row.hidden_year ? `${row.name}（${row.hidden_year}）` : row.name;
  }

  function updateClassToggle() {
    const button = els["ms-class-toggle"];
    const menu = els["ms-class-menu"];
    if (!button || !menu) return;
    button.textContent = classLabel();
    button.setAttribute("aria-expanded", classMenuOpen ? "true" : "false");
    menu.hidden = !classMenuOpen;
  }

  function setClassHiddenYear(row, year) {
    row.hidden_year = year ? String(year) : "";
    classes = window.ToolboxClasses.save(classes);
    const selected = classId();
    fillClasses();
    selectClass(selected);
    classMenuOpen = true;
    updateClassToggle();
  }

  function classMenuYear() {
    const input = document.getElementById("ms-class-year");
    const year = Number(input && input.value);
    if (!Number.isInteger(year) || year < 2000 || year > 2100) return 0;
    return year;
  }

  function classRow(row, list) {
    const line = document.createElement("div");
    line.className = "ms-class-row";
    const name = document.createElement("button");
    name.type = "button";
    name.className = row.id === classId() ? "tb-btn tb-btn-primary ms-class-name" : "tb-btn ms-class-name";
    name.textContent = row.name;
    name.addEventListener("click", () => {
      classMenuOpen = false;
      selectClass(row.id);
      els["ms-class"].dispatchEvent(new Event("change"));
    });
    const up = document.createElement("button");
    up.type = "button";
    up.className = "tb-btn";
    up.textContent = "上";
    up.addEventListener("click", () => moveListedClass(list, row.id, -1));
    const down = document.createElement("button");
    down.type = "button";
    down.className = "tb-btn";
    down.textContent = "下";
    down.addEventListener("click", () => moveListedClass(list, row.id, 1));
    line.append(name, up, down);
    return line;
  }

  function fillClasses() {
    classes = window.ToolboxClasses ? window.ToolboxClasses.load() : [];
    const select = els["ms-class"];
    const current = select.value;
    const mine = teacherClasses();
    select.innerHTML = '<option value="">クラスなし（記録しない）</option>';
    mine.forEach((row) => {
      const option = document.createElement("option");
      option.value = row.id;
      option.textContent = row.hidden_year ? `${row.name}（${row.hidden_year}）` : row.name;
      select.appendChild(option);
    });
    if (current && mine.some((row) => row.id === current)) select.value = current;
    renderUnassigned();
    renderClassMenu();
  }

  function renderClassMenu() {
    const menu = els["ms-class-menu"];
    if (!menu) return;
    const currentYear = document.getElementById("ms-class-year");
    const keptYear = (currentYear && currentYear.value) || String(schoolYear());
    menu.innerHTML = "";
    const none = document.createElement("button");
    none.type = "button";
    none.className = classId() ? "tb-btn" : "tb-btn tb-btn-primary";
    none.textContent = "クラスなし（記録しない）";
    none.addEventListener("click", () => {
      classMenuOpen = false;
      selectClass("");
      els["ms-class"].dispatchEvent(new Event("change"));
    });
    menu.appendChild(none);
    const active = activeTeacherClasses();
    active.forEach((row) => {
      const line = classRow(row, active);
      const hide = document.createElement("button");
      hide.type = "button";
      hide.className = "tb-btn";
      hide.textContent = "非表示";
      hide.addEventListener("click", () => {
        const year = classMenuYear();
        if (!year) {
          alert("年度は2000〜2100で入力してください。");
          return;
        }
        setClassHiddenYear(row, year);
      });
      line.appendChild(hide);
      menu.appendChild(line);
    });
    const heading = document.createElement("h3");
    heading.textContent = "非表示";
    menu.appendChild(heading);
    const yearLine = document.createElement("label");
    yearLine.className = "ms-class-year";
    yearLine.textContent = "年度";
    const yearInput = document.createElement("input");
    yearInput.id = "ms-class-year";
    yearInput.type = "number";
    yearInput.min = "2000";
    yearInput.max = "2100";
    yearInput.value = keptYear;
    yearLine.appendChild(yearInput);
    menu.appendChild(yearLine);
    const hidden = teacherClasses().filter((row) => row.hidden_year);
    if (!hidden.length) {
      const empty = document.createElement("p");
      empty.className = "tb-note";
      empty.textContent = "まだありません。";
      menu.appendChild(empty);
    }
    const years = [...new Set(hidden.map((row) => row.hidden_year))].sort((a, b) => Number(b) - Number(a));
    years.forEach((year) => {
      const sub = document.createElement("h3");
      sub.textContent = year;
      menu.appendChild(sub);
      const group = hidden.filter((row) => row.hidden_year === year);
      group.forEach((row) => {
        const line = classRow(row, group);
        const back = document.createElement("button");
        back.type = "button";
        back.className = "tb-btn";
        back.textContent = "戻す";
        back.addEventListener("click", () => setClassHiddenYear(row, ""));
        line.appendChild(back);
        menu.appendChild(line);
      });
    });
    updateClassToggle();
  }

  function renderUnassigned() {
    const box = els["ms-unassigned"];
    box.innerHTML = "";
    const loose = classes.filter((row) => !row.teacher_id);
    if (!loose.length || !teacherId()) return;
    box.textContent = "担当が未設定のクラス: ";
    loose.forEach((row) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "tb-btn";
      button.textContent = `${row.name} をこの教員へ`;
      button.addEventListener("click", () => {
        rememberScope();
        row.teacher_id = teacherId();
        classes = window.ToolboxClasses.save(classes);
        fillClasses();
        selectClass(row.id);
        enterScope(teacherId(), classId());
        loadCatalog();
      });
      box.appendChild(button);
    });
  }

  function saveClassRow(existing) {
    const name = prompt("クラス名", existing ? existing.name : "");
    if (!name || !name.trim()) return;
    if (!teacherId()) {
      alert("先に担当教員を追加して選んでください。");
      return;
    }
    const count = Number(prompt("人数（1〜60）", existing ? existing.student_count : "30"));
    if (!Number.isFinite(count) || count < 1 || count > 60) {
      alert("人数は1〜60で入力してください。");
      return;
    }
    rememberScope();
    const settings = settingsFromForm();
    if (existing) {
      existing.name = name.trim();
      existing.student_count = count;
      existing.teacher_id = teacherId();
    } else {
      const layout = window.ToolboxClasses.suggestGrid(count);
      classes.push({
        id: newLocalId(),
        name: name.trim(),
        student_count: count,
        absent: [],
        seats: [],
        rows: layout.rows,
        cols: layout.cols,
        blocked: [],
        pick: { absent: [], picked: [], history: [] },
        teacher_id: teacherId(),
        hidden_year: "",
      });
    }
    classes = window.ToolboxClasses.save(classes);
    fillClasses();
    selectClass(existing ? existing.id : classes[classes.length - 1].id);
    bindScope(teacherId(), classId(), settings);
    loadCatalog();
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
    const showHint = els["ms-hints"].checked && (shownPhase() === "prep" || phase === "idle");
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

  function isPair() {
    return els["ms-format"].value === "pair";
  }

  function shownPhase() {
    if (phase === "gate") return phaseNext;
    if (phase === "idle" && isPair()) return "prep";
    return phase;
  }

  function setPhaseClass() {
    const shown = shownPhase();
    stage.classList.toggle("is-prep", shown === "prep" || phase === "idle");
    stage.classList.toggle("is-speak", shown === "speak" || shown === "speakA" || shown === "speakB");
    const warn = running && remainingMs > 0 && remainingMs <= 10000;
    stage.classList.toggle("is-warn", warn);
    stage.classList.toggle("is-end", phase === "done");
  }

  function renderClock() {
    const names = {
      idle: "READY",
      prep: "PREP",
      speak: "SPEAK",
      speakA: "SPEAKER A",
      speakB: "SPEAKER B",
      done: "TIME!",
    };
    const shown = shownPhase();
    els["ms-phase"].textContent = names[shown] || "";
    els["ms-phase"].style.letterSpacing = (names[shown] || "").length > 6 ? "0.04em" : "0.14em";
    if (phase === "done") {
      els["ms-time"].textContent = "TIME!";
      els["ms-time"].className = "ms-time is-time";
    } else {
      const idleMs = (Number(els["ms-prep"].value) || 60) * 1000;
      els["ms-time"].textContent = formatTime(phase === "idle" ? idleMs : remainingMs);
      els["ms-time"].className = "ms-time";
    }
    els["ms-start"].hidden = phase !== "idle" && phase !== "done" && phase !== "gate";
    els["ms-start"].textContent = phase === "done" ? "次の操作" : "Start";
    els["ms-pause"].hidden = phase === "idle" || phase === "done" || phase === "gate";
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
    return isPair() ? ["speakA", "speakB"] : ["speak"];
  }

  function phaseDuration(next) {
    if (next === "prep") return (Number(els["ms-prep"].value) || 60) * 1000;
    if (next === "speak" || next === "speakA" || next === "speakB") return (Number(els["ms-speak"].value) || 60) * 1000;
    return 0;
  }

  function armGate(next) {
    clearTimeout(switchTimer);
    stopTick();
    phase = "gate";
    phaseNext = next;
    durationMs = phaseDuration(next);
    remainingMs = durationMs;
    renderTopic();
    renderClock();
  }

  function nextPhaseAfter(current) {
    if (current === "prep") return speakPhases()[0];
    if (current === "speakA") return "speakB";
    return "";
  }

  function beginPhase(next) {
    clearTimeout(switchTimer);
    phase = next;
    durationMs = phaseDuration(next);
    remainingMs = durationMs;
    if ((next === "speak" || next === "speakA") && !marked) {
      markUsed();
      marked = true;
    }
    renderTopic();
    renderClock();
    if (next === "done") {
      playEnd();
      return;
    }
    startRunning();
  }

  function finishPhase() {
    const upcoming = nextPhaseAfter(phase);
    if (!upcoming) {
      phase = "done";
      playEnd();
      renderClock();
      return;
    }
    playCue();
    const autoSolo = !isPair() && phase === "prep" && els["ms-auto"].checked;
    if (autoSolo) beginPhase(upcoming);
    else armGate(upcoming);
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
    if (remainingMs > 0) {
      renderClock();
      return;
    }
    stopTick();
    finishPhase();
  }

  function toggleRun() {
    unlockAudio();
    if (phase === "idle") {
      beginPhase("prep");
      return;
    }
    if (phase === "gate") {
      beginPhase(phaseNext);
      return;
    }
    if (phase === "done") return;
    if (running) {
      remainingMs = Math.max(0, endAt - Date.now());
      stopTick();
      renderClock();
      return;
    }
    startRunning();
  }

  function topicInLists(item, lists) {
    return lists.some((rows) => Array.isArray(rows) && rows.some((row) => row.id === item.id));
  }

  function topicIsActiveUsed(item) {
    const id = classId();
    if (!id || !item || !item.id) return false;
    const bucket = store.history[id] || {};
    const typeKey = item.type != null && item.type !== "" ? String(item.type) : "";
    const lists = typeKey ? [bucket[typeKey] || []] : Object.values(bucket);
    return topicInLists(item, lists);
  }

  function topicIsUsed(item) {
    if (topicIsActiveUsed(item)) return true;
    if (!item || !item.id || !classId()) return false;
    return topicInLists(item, Object.values(archivedYears()));
  }

  function pushUsed(item) {
    const id = classId();
    if (!id || !item || !item.id) return;
    const typeKey = String(item.type || 1);
    store.history[id] = store.history[id] || { 1: [], 2: [] };
    store.history[id][typeKey] = store.history[id][typeKey] || [];
    if (!store.history[id][typeKey].some((row) => row.id === item.id)) {
      store.history[id][typeKey].push({
        id: item.id,
        usedAt: new Date().toISOString(),
        text: item.text,
        suffix: item.suffix,
        type: item.type,
        ja: item.ja || "",
        source_order: item.source_order,
      });
    }
    clearNext(item);
    saveStore();
  }

  function removeUsed(item) {
    const id = classId();
    if (!id || !item || !item.id) return;
    const bucket = store.history[id] || {};
    const typeKey = item.type != null && item.type !== "" ? String(item.type) : "";
    Object.keys(bucket).forEach((key) => {
      if (!Array.isArray(bucket[key])) return;
      if (typeKey && key !== typeKey) return;
      bucket[key] = bucket[key].filter((row) => row.id !== item.id);
    });
    saveStore();
  }

  function markUsed() {
    pushUsed(topic);
  }

  function undoUsed() {
    removeUsed(topic);
    marked = false;
  }

  function applyUsedLook(card, used) {
    card.classList.toggle("is-used", !!used);
    const badge = card.querySelector("[data-used-badge]");
    if (badge) badge.hidden = !used;
    const button = card.querySelector("[data-used-toggle]");
    if (button) {
      const active = topicIsActiveUsed({ id: card.dataset.topicId, type: card.dataset.topicType });
      button.textContent = active ? "使用済みを取り消す" : "使用済みにする";
    }
  }

  function applyNextLook(card, next) {
    card.classList.toggle("is-next", !!next);
    const badge = card.querySelector("[data-next-badge]");
    if (badge) badge.hidden = !next;
    const button = card.querySelector("[data-next-toggle]");
    if (button) button.textContent = next ? "次回使うを取り消す" : "次回使う";
  }

  function refreshUsedSurfaces(topicId) {
    renderUsedList();
    document.querySelectorAll("#ms-catalog .ms-card, #ms-results .ms-card").forEach((card) => {
      if (topicId && card.dataset.topicId !== topicId) return;
      applyUsedLook(card, topicIsUsed({ id: card.dataset.topicId, type: card.dataset.topicType }));
    });
    const shown = els["ms-catalog"].querySelectorAll(".ms-card").length;
    if (shown) {
      const usedCount = els["ms-catalog"].querySelectorAll(".ms-card.is-used").length;
      const nextCount = els["ms-catalog"].querySelectorAll(".ms-card.is-next").length;
      const total = catalogCount || (els["ms-cat-status"].textContent.match(/全 (\d+) 件/) || [])[1];
      els["ms-cat-status"].textContent = `このページ ${shown} 件中、使用済み ${usedCount} 件、次回使う ${nextCount} 件。${total ? `全 ${total} 件。` : ""}`;
    }
    if (!els["ms-panel-history"].hidden) renderHistory();
  }

  function toggleTopicUsed(item) {
    if (!classId()) {
      alert("クラスを選ぶと使用済みを記録できます。");
      return;
    }
    if (topicIsUsed(item)) removeUsed(item);
    else pushUsed(item);
    if (topic && item && topic.id === item.id) marked = topicIsActiveUsed(item);
    refreshUsedSurfaces(item.id);
    refreshNextSurfaces(item.id);
  }

  function usedBadge(used) {
    return `<span class="tb-badge ms-used-badge" data-used-badge ${used ? "" : "hidden"}>使用済み</span>`;
  }

  function usedToggleButton(item) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "tb-btn";
    button.dataset.usedToggle = "1";
    button.textContent = topicIsActiveUsed(item) ? "使用済みを取り消す" : "使用済みにする";
    button.addEventListener("click", () => toggleTopicUsed(item));
    return button;
  }

  function nextList() {
    const id = classId();
    store.nextUse = store.nextUse || {};
    if (!id) return [];
    if (!Array.isArray(store.nextUse[id])) store.nextUse[id] = [];
    return store.nextUse[id];
  }

  function topicIsNext(item) {
    if (!item || !item.id) return false;
    return nextList().some((row) => row.id === item.id);
  }

  function clearNext(item) {
    if (!item || !item.id) return;
    const rows = nextList();
    const index = rows.findIndex((row) => row.id === item.id);
    if (index >= 0) rows.splice(index, 1);
  }

  function topicSnapshot(item) {
    return {
      id: item.id,
      text: item.text,
      suffix: item.suffix,
      type: item.type,
      ja: item.ja || "",
      source_order: item.source_order,
    };
  }

  function toggleNext(item) {
    if (!classId()) {
      alert("クラスを選ぶと次回使うを記録できます。");
      return;
    }
    const rows = nextList();
    const index = rows.findIndex((row) => row.id === item.id);
    if (index >= 0) rows.splice(index, 1);
    else rows.push(topicSnapshot(item));
    saveStore();
    refreshNextSurfaces(item.id);
  }

  function nextBadge(next) {
    return `<span class="tb-badge ms-next-badge" data-next-badge ${next ? "" : "hidden"}>次回使う</span>`;
  }

  function nextToggleButton(item) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "tb-btn";
    button.dataset.nextToggle = "1";
    button.textContent = topicIsNext(item) ? "次回使うを取り消す" : "次回使う";
    button.addEventListener("click", () => toggleNext(item));
    return button;
  }

  function refreshNextSurfaces(topicId) {
    document.querySelectorAll("#ms-catalog .ms-card, #ms-results .ms-card").forEach((card) => {
      if (topicId && card.dataset.topicId !== topicId) return;
      applyNextLook(card, topicIsNext({ id: card.dataset.topicId }));
    });
    paintCatalogPages(catalogCount);
    const shown = els["ms-catalog"].querySelectorAll(".ms-card").length;
    if (shown && catalogCount) {
      const usedCount = els["ms-catalog"].querySelectorAll(".ms-card.is-used").length;
      const nextCount = els["ms-catalog"].querySelectorAll(".ms-card.is-next").length;
      els["ms-cat-status"].textContent = `このページ ${shown} 件中、使用済み ${usedCount} 件、次回使う ${nextCount} 件。全 ${catalogCount} 件。`;
    }
  }

  function schoolYear(date) {
    const now = date || new Date();
    return now.getMonth() >= 3 ? now.getFullYear() : now.getFullYear() - 1;
  }

  function archiveYear() {
    const year = Number(els["ms-archive-year"] && els["ms-archive-year"].value);
    if (!Number.isInteger(year) || year < 2000 || year > 2100) return 0;
    return year;
  }

  function archiveRows(rows, year) {
    const id = classId();
    if (!id || !year) return;
    store.archived = store.archived || {};
    store.archived[id] = archivedYears();
    const key = String(year);
    const existing = Array.isArray(store.archived[id][key]) ? store.archived[id][key] : [];
    const seen = new Set(existing.map((row) => row.id));
    rows.forEach((row) => {
      if (!row || !row.id) return;
      Object.keys(store.archived[id]).forEach((other) => {
        if (other === key || !Array.isArray(store.archived[id][other])) return;
        store.archived[id][other] = store.archived[id][other].filter((item) => item.id !== row.id);
        if (!store.archived[id][other].length) delete store.archived[id][other];
      });
      if (seen.has(row.id)) {
        removeUsed(row);
        clearNext(row);
        return;
      }
      seen.add(row.id);
      existing.push(Object.assign({}, topicSnapshot(row), { usedAt: row.usedAt || "", year: key }));
      removeUsed(row);
      clearNext(row);
    });
    store.archived[id][key] = existing;
    saveStore();
  }

  function restoreArchived(row) {
    if (!row || !row.id) return;
    pushUsed(row);
    const years = archivedYears();
    Object.keys(years).forEach((key) => {
      years[key] = (years[key] || []).filter((item) => item.id !== row.id);
      if (!years[key].length) delete years[key];
    });
    saveStore();
  }

  function restoreYear(year) {
    const rows = ((archivedYears()[String(year)] || []).slice());
    rows.forEach((row) => restoreArchived(row));
  }

  function cardActions() {
    const actions = document.createElement("div");
    actions.className = "ms-card-actions";
    return actions;
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
    loadCatalog();
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
      card.className = "ms-card is-blur is-used";
      card.innerHTML = `<div class="ms-meta"><span class="tb-badge">タイプ${row.type}${topicNumber(row) ? " " + topicNumber(row) : ""}</span>${usedBadge(true)}<span class="tb-muted">${esc(row.usedAt || "").slice(0, 16).replace("T", " ")}</span></div><p class="ms-card-text">${esc(row.text)}</p>`;
      card.querySelector(".ms-card-text").addEventListener("click", () => card.classList.remove("is-blur"));
      const button = document.createElement("button");
      button.type = "button";
      button.className = "tb-btn";
      button.textContent = "使用済みを取り消す";
      button.addEventListener("click", () => {
        removeUsed(row);
        refreshUsedSurfaces(row.id);
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
      const used = topicIsUsed(item);
      const card = document.createElement("article");
      card.className = blur ? "ms-card is-blur" : "ms-card";
      card.dataset.topicId = item.id;
      card.dataset.topicType = String(item.type || "");
      const next = topicIsNext(item);
      card.innerHTML = `<div class="ms-meta"><span class="tb-badge">タイプ${item.type}${topicNumber(item) ? " " + topicNumber(item) : ""}</span>${item.level ? `<span class="tb-badge">L${item.level}</span>` : ""}${usedBadge(used)}${nextBadge(next)}${(item.flags || []).length ? '<span class="tb-badge tb-badge-mute">配慮</span>' : ""}</div><p class="ms-card-text">${highlight(item.text, els["ms-q"].value)}</p>${item.ja ? `<p class="tb-muted">${esc(item.ja)}</p>` : ""}`;
      applyUsedLook(card, used);
      applyNextLook(card, next);
      card.querySelector(".ms-card-text").addEventListener("click", () => card.classList.remove("is-blur"));
      const use = document.createElement("button");
      use.type = "button";
      use.className = "tb-btn tb-btn-primary";
      use.textContent = "このお題を使う";
      use.addEventListener("click", () => useSearched(Object.assign({}, item, { used: topicIsUsed(item) })));
      const hide = document.createElement("button");
      hide.type = "button";
      hide.className = "tb-btn";
      hide.textContent = "今後出さない";
      hide.addEventListener("click", () => {
        if (!store.hiddenTopicIds.includes(item.id)) store.hiddenTopicIds.push(item.id);
        saveStore();
        card.remove();
      });
      const actions = cardActions();
      actions.append(use, nextToggleButton(item), usedToggleButton(item), hide);
      card.appendChild(actions);
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
      nextUse: store.nextUse,
      archived: store.archived,
      prefs: store.prefs,
      scopes: store.scopes,
      lastClass: store.lastClass,
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
        if (data.nextUse && typeof data.nextUse === "object") store.nextUse = data.nextUse;
        if (data.archived && typeof data.archived === "object") store.archived = data.archived;
        if (data.prefs && typeof data.prefs === "object") store.prefs = data.prefs;
        if (data.scopes && typeof data.scopes === "object") store.scopes = data.scopes;
        if (data.lastClass && typeof data.lastClass === "object") store.lastClass = data.lastClass;
        store.lastBackupAt = new Date().toISOString();
        saveStore();
        readPrefsIntoForm();
        refreshUsedSurfaces();
        loadCatalog();
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
  ["ms-type", "ms-level", "ms-prep", "ms-speak", "ms-format", "ms-unleveled", "ms-flagged", "ms-auto", "ms-ja", "ms-hints", "ms-blur", "ms-exclude-used", "ms-ai"].forEach((id) => {
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
    refreshUsedSurfaces();
    loadCatalog();
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

  fillTeachers();
  readPrefsIntoForm();
  renderRecent();
  loadStats().catch(() => {});
  if (els["ms-archive-year"]) els["ms-archive-year"].value = String(schoolYear());
  els["ms-archive-used"].addEventListener("click", () => {
    if (!classId()) {
      alert("クラスを選んでください。");
      return;
    }
    const year = archiveYear();
    if (!year) {
      alert("年度は2000〜2100で入力してください。");
      return;
    }
    const rows = allUsedRows();
    if (!rows.length) {
      alert("移す使用済みがありません。");
      return;
    }
    if (!confirm(`使用済み ${rows.length} 件を ${year} の非表示に移しますか？`)) return;
    archiveRows(rows, year);
    loadCatalog();
  });
  toolboxFetch("/toolbox/api/minute-speech/catalog-pos").then((pos) => {
    catType = Number(pos.type) === 2 ? 2 : 1;
    catOffset = Math.max(0, Number(pos.offset) || 0);
    els["ms-cat-1"].classList.toggle("tb-btn-primary", catType === 1);
    els["ms-cat-2"].classList.toggle("tb-btn-primary", catType === 2);
  }).catch(() => {}).then(() => { catPosReady = true; loadCatalog(); });

  els["ms-teacher"].addEventListener("change", () => {
    rememberScope();
    fillClasses();
    selectClass((store.lastClass || {})[teacherId()] || "");
    enterScope(teacherId(), classId());
    loadCatalog();
    if (!els["ms-panel-history"].hidden) renderHistory();
  });
  els["ms-class"].addEventListener("change", () => {
    rememberScope();
    enterScope(teacherId(), classId());
    loadCatalog();
    if (!els["ms-panel-history"].hidden) renderHistory();
  });
  els["ms-teacher-add"].addEventListener("click", () => {
    const name = prompt("担当教員名");
    if (!name || !name.trim()) return;
    rememberScope();
    teachers.push({ id: newLocalId(), name: name.trim() });
    teachers = window.ToolboxClasses.saveTeachers(teachers);
    fillTeachers();
    els["ms-teacher"].value = teachers[teachers.length - 1].id;
    fillClasses();
    selectClass("");
    enterScope(teacherId(), classId());
  });
  els["ms-teacher-edit"].addEventListener("click", () => {
    const row = teachers.find((item) => item.id === teacherId());
    if (!row) return;
    const name = prompt("担当教員名", row.name);
    if (!name || !name.trim()) return;
    row.name = name.trim();
    teachers = window.ToolboxClasses.saveTeachers(teachers);
    fillTeachers();
    els["ms-teacher"].value = row.id;
    writePrefs();
  });
  els["ms-teacher-del"].addEventListener("click", async () => {
    const row = teachers.find((item) => item.id === teacherId());
    if (!row) return;
    if (!await confirmDelete(`${row.name} を削除しますか？クラスは担当未設定として残ります。`)) return;
    classes.forEach((item) => {
      if (item.teacher_id === row.id) item.teacher_id = "";
    });
    classes = window.ToolboxClasses.save(classes);
    teachers = window.ToolboxClasses.saveTeachers(teachers.filter((item) => item.id !== row.id));
    fillTeachers();
    fillClasses();
    selectClass((store.lastClass || {})[teacherId()] || "");
    enterScope(teacherId(), classId());
    loadCatalog();
  });
  els["ms-class-toggle"].addEventListener("click", () => {
    classMenuOpen = !classMenuOpen;
    if (classMenuOpen) renderClassMenu();
    else updateClassToggle();
  });
  document.addEventListener("click", (ev) => {
    if (!classMenuOpen) return;
    if (ev.target.closest && ev.target.closest(".ms-class-pick")) return;
    classMenuOpen = false;
    updateClassToggle();
  });
  els["ms-class-add"].addEventListener("click", () => saveClassRow(null));
  els["ms-class-edit"].addEventListener("click", () => {
    const row = classes.find((item) => item.id === classId());
    if (row) saveClassRow(row);
  });
  els["ms-class-del"].addEventListener("click", async () => {
    const row = classes.find((item) => item.id === classId());
    if (!row) return;
    if (!await confirmDelete(`${row.name} をこの端末から削除しますか？`)) return;
    classes = window.ToolboxClasses.save(classes.filter((item) => item.id !== row.id));
    fillClasses();
    enterScope(teacherId(), classId());
    loadCatalog();
  });
  els["ms-cat-1"].addEventListener("click", () => {
    catType = 1;
    catOffset = 0;
    els["ms-cat-1"].classList.add("tb-btn-primary");
    els["ms-cat-2"].classList.remove("tb-btn-primary");
    loadCatalog();
  });
  els["ms-cat-2"].addEventListener("click", () => {
    catType = 2;
    catOffset = 0;
    els["ms-cat-2"].classList.add("tb-btn-primary");
    els["ms-cat-1"].classList.remove("tb-btn-primary");
    loadCatalog();
  });

  function allUsedRows() {
    const id = classId();
    if (!id) return [];
    const rows = [];
    Object.values(store.history[id] || {}).forEach((list) => {
      if (Array.isArray(list)) list.forEach((row) => rows.push(row));
    });
    rows.sort((a, b) => {
      const typeDiff = Number(a.type || 0) - Number(b.type || 0);
      if (typeDiff) return typeDiff;
      const orderDiff = Number(a.source_order || 0) - Number(b.source_order || 0);
      if (orderDiff) return orderDiff;
      return String(a.usedAt || "").localeCompare(String(b.usedAt || ""));
    });
    return rows;
  }

  function renderUsedList() {
    const box = els["ms-used"];
    const status = els["ms-used-status"];
    if (!box || !status) return;
    box.innerHTML = "";
    if (!classId()) {
      status.textContent = "クラスを選ぶと、使用済みを記録できます。";
      return;
    }
    const rows = allUsedRows();
    status.textContent = rows.length ? `使用済み ${rows.length} 件` : "このクラスの使用済みはまだありません。";
    rows.forEach((row) => {
      const card = document.createElement("article");
      card.className = "ms-card is-used";
      card.dataset.topicId = row.id;
      card.dataset.topicType = String(row.type || "");
      const when = esc(row.usedAt || "").slice(0, 16).replace("T", " ");
      card.innerHTML = `<div class="ms-meta"><span class="tb-badge">タイプ${row.type}${topicNumber(row) ? " " + topicNumber(row) : ""}</span>${usedBadge(true)}<span class="tb-muted">${when}</span></div><p class="ms-card-text">${esc(row.text)}</p>`;
      const use = document.createElement("button");
      use.type = "button";
      use.className = "tb-btn tb-btn-primary";
      use.textContent = "このお題を使う";
      use.addEventListener("click", () => useSearched(Object.assign({ used: true }, row)));
      const archive = document.createElement("button");
      archive.type = "button";
      archive.className = "tb-btn";
      archive.textContent = "非表示にする";
      archive.addEventListener("click", () => {
        const year = archiveYear();
        if (!year) {
          alert("年度は2000〜2100で入力してください。");
          return;
        }
        archiveRows([row], year);
        loadCatalog();
      });
      const actions = cardActions();
      actions.append(use, usedToggleButton(row), archive);
      card.appendChild(actions);
      box.appendChild(card);
    });
  }

  function renderArchived() {
    const box = els["ms-archived"];
    if (!box) return;
    box.innerHTML = "";
    if (!classId()) return;
    const years = archivedYears();
    const keys = Object.keys(years).filter((key) => (years[key] || []).length).sort((a, b) => Number(b) - Number(a));
    if (!keys.length) {
      const note = document.createElement("p");
      note.className = "tb-note";
      note.textContent = "非表示にしたお題はまだありません。";
      box.appendChild(note);
      return;
    }
    keys.forEach((year) => {
      const heading = document.createElement("h3");
      heading.className = "ms-year";
      heading.textContent = year;
      const back = document.createElement("button");
      back.type = "button";
      back.className = "tb-btn";
      back.textContent = `${year} を使用済みに戻す`;
      back.addEventListener("click", () => {
        restoreYear(year);
        loadCatalog();
      });
      const list = document.createElement("div");
      list.className = "ms-results";
      (years[year] || []).forEach((row) => {
        const card = document.createElement("article");
        card.className = "ms-card is-used";
        card.innerHTML = `<div class="ms-meta"><span class="tb-badge">タイプ${row.type}${topicNumber(row) ? " " + topicNumber(row) : ""}</span>${usedBadge(true)}</div><p class="ms-card-text">${esc(row.text)}</p>`;
        const restore = document.createElement("button");
        restore.type = "button";
        restore.className = "tb-btn";
        restore.textContent = "使用済みに戻す";
        restore.addEventListener("click", () => {
          restoreArchived(row);
          loadCatalog();
        });
        const actions = cardActions();
        actions.appendChild(restore);
        card.appendChild(actions);
        list.appendChild(card);
      });
      box.append(heading, back, list);
    });
  }

  function paintCatalogPages(count) {
    const pages = els["ms-cat-pages"];
    if (!pages) return;
    pages.innerHTML = "";
    if (!count) return;
    const ids = catalogIds[catType] || [];
    const nextIds = new Set(nextList().filter((row) => Number(row.type) === Number(catType)).map((row) => row.id));
    const pageCount = Math.ceil(count / CAT_PAGE);
    for (let index = 0; index < pageCount; index += 1) {
      const start = index * CAT_PAGE + 1;
      const slice = ids.slice(index * CAT_PAGE, index * CAT_PAGE + CAT_PAGE);
      const marked = slice.some((id) => nextIds.has(id));
      const button = document.createElement("button");
      button.type = "button";
      button.className = catOffset === index * CAT_PAGE ? "tb-btn tb-btn-primary" : "tb-btn";
      if (marked) button.classList.add("ms-page-next");
      button.textContent = `${start}–${Math.min(count, start + CAT_PAGE - 1)}`;
      button.addEventListener("click", () => {
        catOffset = index * CAT_PAGE;
        loadCatalog();
      });
      pages.appendChild(button);
    }
  }

  function loadCatalog() {
    if (catPosReady) {
      const posKey = `${catType}:${catOffset}`;
      if (posKey !== lastSavedPos) {
        lastSavedPos = posKey;
        toolboxFetch("/toolbox/api/minute-speech/catalog-pos", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ type: catType, offset: catOffset }),
        }).catch(() => {});
      }
    }
    renderUsedList();
    renderArchived();
    const status = els["ms-cat-status"];
    status.textContent = "読み込み中…";
    const params = new URLSearchParams({
      type: String(catType),
      offset: String(catOffset),
      limit: String(CAT_PAGE),
    });
    if (!catalogIds[catType]) params.set("index", "1");
    toolboxFetch(`/toolbox/api/minute-speech/catalog?${params}`).then((data) => {
      if (Array.isArray(data.ids)) catalogIds[catType] = data.ids;
      catalogCount = Number(data.count) || 0;
      const used = new Set(spentRows(catType).map((row) => row.id));
      const box = els["ms-catalog"];
      box.innerHTML = "";
      (data.results || []).forEach((item) => {
        const isUsed = used.has(item.id);
        const next = topicIsNext(item);
        const card = document.createElement("article");
        card.className = "ms-card";
        card.dataset.topicId = item.id;
        card.dataset.topicType = String(item.type || "");
        card.innerHTML = `<div class="ms-meta"><span class="tb-badge">タイプ${item.type} ${topicNumber(item)}</span>${usedBadge(isUsed)}${nextBadge(next)}</div><p class="ms-card-text">${esc(item.text)}</p>`;
        applyUsedLook(card, isUsed);
        applyNextLook(card, next);
        const use = document.createElement("button");
        use.type = "button";
        use.className = "tb-btn tb-btn-primary";
        use.textContent = "このお題を使う";
        use.addEventListener("click", () => useSearched(Object.assign({}, item, { used: topicIsUsed(item) })));
        const actions = cardActions();
        actions.append(use, nextToggleButton(item), usedToggleButton(item));
        card.appendChild(actions);
        box.appendChild(card);
      });
      paintCatalogPages(catalogCount);
      const shown = (data.results || []).length;
      const usedCount = (data.results || []).filter((item) => used.has(item.id)).length;
      const nextCount = (data.results || []).filter((item) => topicIsNext(item)).length;
      status.textContent = shown
        ? `このページ ${shown} 件中、使用済み ${usedCount} 件、次回使う ${nextCount} 件。全 ${catalogCount} 件。`
        : "表示できるお題がありません。";
    }).catch((err) => {
      status.textContent = err.message;
    });
  }
})();
