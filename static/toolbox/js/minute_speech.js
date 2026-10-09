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
  let endedPhase = "";
  let ringing = false;
  let themes = [];
  let teachers = [];
  let scopeTeacher = "";
  let scopeClass = "";
  let scopeCourse = "";
  let courses = [];
  let activeTheme = "";
  let listType = 1;
  let listFilter = "all";
  let undoTimer = 0;
  let undoSnapshot = null;
  let catType = 1;
  let catOffset = 0;
  let catPosReady = false;
  let lastSavedPos = "";
  const CAT_PAGE = 50;
  const catalogIds = { 1: null, 2: null };
  let catalogCount = 0;
  let catalogPageSnapshot = null;
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
        data.courseState = data.courseState || {};
        data.lastCourse = data.lastCourse || {};
        if (window.MinuteSpeechCourses) {
          const ensured = window.MinuteSpeechCourses.ensureLoaded(data);
          return ensured.store;
        }
        return data;
      }
    } catch (_) {}
    const empty = window.MinuteSpeechCourses
      ? window.MinuteSpeechCourses.defaultStore()
      : { history: {}, rounds: {}, hiddenTopicIds: [], prefs: {}, scopes: {}, lastClass: {}, recentQueries: [], nextUse: {}, archived: {}, lastBackupAt: null };
    if (window.MinuteSpeechCourses) return window.MinuteSpeechCourses.ensureLoaded(empty).store;
    return empty;
  }

  function patchStoreOnto(fresh) {
    fresh.courseState = store.courseState || fresh.courseState || {};
    fresh.prefs = Object.assign({ teacherId: "", courseId: "", classId: "" }, fresh.prefs, store.prefs);
    fresh.lastCourse = Object.assign({}, fresh.lastCourse, store.lastCourse);
    fresh.hiddenTopicIds = store.hiddenTopicIds || fresh.hiddenTopicIds || [];
    fresh.recentQueries = store.recentQueries || fresh.recentQueries || [];
    fresh.lastBackupAt = store.lastBackupAt != null ? store.lastBackupAt : fresh.lastBackupAt;
    fresh.migrationNotes = store.migrationNotes || fresh.migrationNotes;
    fresh.migrationPending = store.migrationPending != null ? store.migrationPending : fresh.migrationPending;
    fresh.schemaVersion = store.schemaVersion || fresh.schemaVersion;
    if (store.history) fresh.history = store.history;
    if (store.scopes) fresh.scopes = store.scopes;
    if (store.nextUse) fresh.nextUse = store.nextUse;
    if (store.archived) fresh.archived = store.archived;
    if (store.rounds) fresh.rounds = store.rounds;
    if (store.lastClass) fresh.lastClass = store.lastClass;
  }

  function saveStore() {
    if (window.MinuteSpeechCourses) {
      store = window.MinuteSpeechCourses.mergeSave((fresh) => {
        patchStoreOnto(fresh);
      });
      return;
    }
    localStorage.setItem(KEY, JSON.stringify(store));
  }

  function courseMode() {
    return !!(window.MinuteSpeechCourses && courseId() && currentCourse());
  }

  function courseId() {
    return (store.prefs && store.prefs.courseId) || scopeCourse || "";
  }

  function currentCourse() {
    const id = courseId();
    return courses.find((row) => row.id === id) || null;
  }

  function courseBucket() {
    if (!window.MinuteSpeechCourses || !courseId()) return null;
    return window.MinuteSpeechCourses.ensureCourseBucket(store, courseId());
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
    if (courseMode()) return window.MinuteSpeechCourses.allListTopicIds(store, courseId());
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
    store.prefs = {
      teacherId: prefs.teacherId || "",
      courseId: prefs.courseId || "",
      classId: prefs.classId || "",
    };
  }

  function settingsFor(teacher, klass) {
    if (courseId() && courseBucket() && courseBucket().settings) return courseBucket().settings;
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
    const settings = settingsFromForm();
    if (courseId() && courseBucket()) courseBucket().settings = settings;
    else {
      store.scopes = store.scopes || {};
      store.scopes[scopeKey(scopeTeacher, scopeClass)] = settings;
    }
    store.lastClass = store.lastClass || {};
    store.lastCourse = store.lastCourse || {};
    if (scopeTeacher) {
      store.lastClass[scopeTeacher] = scopeClass;
      if (scopeCourse) store.lastCourse[scopeTeacher] = scopeCourse;
    }
    if (courseId() && courseBucket() && scopeClass) courseBucket().lastClassId = scopeClass;
    store.prefs = { teacherId: scopeTeacher, courseId: scopeCourse, classId: scopeClass };
    saveStore();
  }

  function enterScope(teacher, klass, course) {
    scopeTeacher = teacher || "";
    scopeClass = klass || "";
    scopeCourse = course || courseId() || "";
    applySettings(settingsFor(scopeTeacher, scopeClass) || DEFAULT_SETTINGS);
    store.lastClass = store.lastClass || {};
    store.lastCourse = store.lastCourse || {};
    if (scopeTeacher) {
      store.lastClass[scopeTeacher] = scopeClass;
      if (scopeCourse) store.lastCourse[scopeTeacher] = scopeCourse;
    }
    if (scopeCourse && courseBucket() && scopeClass) courseBucket().lastClassId = scopeClass;
    store.prefs = { teacherId: scopeTeacher, courseId: scopeCourse, classId: scopeClass };
    saveStore();
  }

  function bindScope(teacher, klass, settings, course) {
    scopeTeacher = teacher || "";
    scopeClass = klass || "";
    scopeCourse = course || courseId() || "";
    if (scopeCourse && courseBucket()) courseBucket().settings = settings;
    else {
      store.scopes = store.scopes || {};
      store.scopes[scopeKey(scopeTeacher, scopeClass)] = settings;
    }
    store.lastClass = store.lastClass || {};
    store.lastCourse = store.lastCourse || {};
    if (scopeTeacher) {
      store.lastClass[scopeTeacher] = scopeClass;
      if (scopeCourse) store.lastCourse[scopeTeacher] = scopeCourse;
    }
    store.prefs = { teacherId: scopeTeacher, courseId: scopeCourse, classId: scopeClass };
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
    renderTodayClasses();
  }

  function readPrefsIntoForm() {
    migrateScopes();
    const prefs = store.prefs || {};
    if (prefs.teacherId && teachers.some((row) => row.id === prefs.teacherId)) {
      els["ms-teacher"].value = prefs.teacherId;
    }
    fillCourses();
    fillClasses();
    const savedCourse = prefs.courseId || (store.lastCourse || {})[teacherId()] || "";
    if (savedCourse && courses.some((row) => row.id === savedCourse) && els["ms-course"]) {
      els["ms-course"].value = savedCourse;
      scopeCourse = savedCourse;
    }
    const savedClass = prefs.classId
      || (courseBucket() && courseBucket().lastClassId)
      || (store.lastClass || {})[teacherId()]
      || "";
    selectClass(savedClass);
    enterScope(teacherId(), classId(), courseId());
    showMigrationNotes();
  }

  function showMigrationNotes() {
    const box = els["ms-migration-note"];
    const fin = els["ms-finalize-migration"];
    if (!box) return;
    const notes = store.migrationNotes || [];
    if (store.migrationPending && notes.length) {
      box.hidden = false;
      box.textContent = notes.join(" ");
    } else {
      box.hidden = true;
      box.textContent = "";
    }
    if (fin) fin.hidden = !store.migrationPending;
  }

  function fillCourses() {
    courses = window.ToolboxClasses ? window.ToolboxClasses.loadCourses() : [];
    const select = els["ms-course"];
    if (!select) return;
    const current = select.value;
    const list = window.ToolboxClasses
      ? window.ToolboxClasses.coursesForTeacher(teacherId(), courses)
      : [];
    select.innerHTML = "";
    if (!list.length) {
      const empty = document.createElement("option");
      empty.value = "";
      empty.textContent = teacherId() ? "授業を追加してください" : "教員を選んでください";
      select.appendChild(empty);
    }
    list.forEach((row) => {
      const option = document.createElement("option");
      option.value = row.id;
      option.textContent = row.name;
      select.appendChild(option);
    });
    if (current && list.some((row) => row.id === current)) select.value = current;
    else if (list.length === 1) select.value = list[0].id;
    scopeCourse = select.value || "";
  }

  function courseClassRows() {
    const course = currentCourse();
    if (!course) return [];
    const order = course.class_ids || [];
    return order
      .map((id) => classes.find((row) => row.id === id))
      .filter((row) => row && !row.hidden_year);
  }

  function renderTodayClasses() {
    const box = els["ms-today-classes"];
    if (!box) return;
    box.innerHTML = "";
    const none = document.createElement("button");
    none.type = "button";
    none.className = classId() ? "tb-btn" : "tb-btn tb-btn-primary";
    none.textContent = "記録しない";
    none.addEventListener("click", () => {
      selectClass("");
      enterScope(teacherId(), "", courseId());
      renderTodayClasses();
      renderTopicList();
    });
    box.appendChild(none);
    courseClassRows().forEach((row) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "ms-class-chip";
      if (row.id === classId()) chip.classList.add("is-today");
      chip.textContent = row.name;
      chip.addEventListener("click", () => {
        selectClass(row.id);
        enterScope(teacherId(), classId(), courseId());
        renderTodayClasses();
        renderTopicList();
        loadCatalog();
      });
      box.appendChild(chip);
    });
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

  function moveCourseClass(id, direction) {
    const course = currentCourse();
    if (!course || !id) return;
    const ids = course.class_ids.slice();
    const index = ids.indexOf(id);
    const next = index + direction;
    if (index < 0 || next < 0 || next >= ids.length) return;
    const tmp = ids[index];
    ids[index] = ids[next];
    ids[next] = tmp;
    course.class_ids = ids;
    courses = window.ToolboxClasses.saveCourses(courses.map((row) => (row.id === course.id ? course : row)));
    renderTodayClasses();
    renderTopicList();
  }

  function fillClasses() {
    classes = window.ToolboxClasses ? window.ToolboxClasses.load() : [];
    const select = els["ms-class"];
    const current = select.value;
    const rows = courseClassRows();
    select.innerHTML = '<option value="">クラスなし（記録しない）</option>';
    rows.forEach((row) => {
      const option = document.createElement("option");
      option.value = row.id;
      option.textContent = row.name;
      select.appendChild(option);
    });
    if (current && rows.some((row) => row.id === current)) select.value = current;
    else if (rows.length && !current) select.value = rows[0].id;
    renderUnassigned();
    renderTodayClasses();
  }

  function classesNotInCourse() {
    const course = currentCourse();
    const inCourse = new Set((course && course.class_ids) || []);
    const teacher = teacherId();
    return classes.filter((row) => {
      if (row.hidden_year) return false;
      if (inCourse.has(row.id)) return false;
      if (row.teacher_id === teacher || !row.teacher_id) return true;
      return false;
    });
  }

  function renderUnassigned() {
    const box = els["ms-unassigned"];
    if (!box) return;
    box.innerHTML = "";
    if (!teacherId() || !currentCourse()) return;
    const loose = classesNotInCourse();
    if (!loose.length) return;
    box.textContent = "この授業に未登録のクラス: ";
    loose.forEach((row) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "tb-btn";
      button.textContent = `${row.name} をこの授業へ`;
      button.addEventListener("click", () => {
        rememberScope();
        if (!row.teacher_id) row.teacher_id = teacherId();
        classes = window.ToolboxClasses.save(classes);
        courses = window.ToolboxClasses.addClassToCourse(courseId(), row.id, courses);
        fillClasses();
        selectClass(row.id);
        enterScope(teacherId(), classId(), courseId());
        loadCatalog();
        renderTopicList();
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
      const newId = newLocalId();
      classes.push({
        id: newId,
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
      if (courseId() && confirm(`${name.trim()} を現在の授業に追加しますか？`)) {
        courses = window.ToolboxClasses.addClassToCourse(courseId(), newId, courses);
      }
    }
    classes = window.ToolboxClasses.save(classes);
    fillClasses();
    selectClass(existing ? existing.id : classes[classes.length - 1].id);
    bindScope(teacherId(), classId(), settings, courseId());
    loadCatalog();
    renderTopicList();
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
    const course = currentCourse();
    const selected = classes.find((row) => row.id === classId());
    const courseLabel = course ? course.name : "";
    const classLabel = selected ? selected.name : "記録しない";
    els["ms-meta-class"].textContent = courseLabel ? `${courseLabel} · ${classLabel}` : classLabel;
    els["ms-meta-no"].textContent = sessionNo ? `#${sessionNo}` : "";
    requestAnimationFrame(fitTopic);
  }

  function isPair() {
    return els["ms-format"].value === "pair" || els["ms-format"].value === "trio";
  }

  function shownPhase() {
    if (phase === "gate") return phaseNext;
    if (phase === "idle" && isPair()) return "prep";
    return phase;
  }

  function setPhaseClass() {
    const shown = shownPhase();
    stage.classList.toggle("is-prep", shown === "prep" || phase === "idle");
    stage.classList.toggle("is-speak", shown === "speak" || shown === "speakA" || shown === "speakB" || shown === "speakC");
    const warn = running && remainingMs > 0 && remainingMs <= 10000;
    stage.classList.toggle("is-warn", warn);
    stage.classList.toggle("is-end", timeUpVisible());
  }

  function isSpeakPhase(name) {
    return name === "speak" || name === "speakA" || name === "speakB" || name === "speakC";
  }

  function timeUpVisible() {
    return phase === "done" || (phase === "gate" && isSpeakPhase(endedPhase));
  }

  function renderClock() {
    const names = {
      idle: "READY",
      prep: "PREP",
      speak: "SPEAK",
      speakA: "SPEAKER A",
      speakB: "SPEAKER B",
      speakC: "SPEAKER C",
      done: "TIME!",
    };
    const shown = shownPhase();
    if (timeUpVisible()) {
      els["ms-phase"].textContent = "";
      els["ms-time"].textContent = "TIME UP";
      els["ms-time"].className = "ms-time is-time";
    } else {
    els["ms-phase"].textContent = names[shown] || "";
    els["ms-phase"].style.letterSpacing = (names[shown] || "").length > 6 ? "0.04em" : "0.14em";
      const idleMs = (Number(els["ms-prep"].value) || 60) * 1000;
      els["ms-time"].textContent = formatTime(phase === "idle" ? idleMs : remainingMs);
      els["ms-time"].className = "ms-time";
    }
    els["ms-start"].hidden = phase !== "idle" && phase !== "done" && phase !== "gate";
    els["ms-start"].textContent = phase === "done" ? "次の操作" : "Start";
    els["ms-pause"].hidden = phase === "idle" || phase === "done" || phase === "gate";
    els["ms-pause"].textContent = running ? "一時停止" : "再開";
    setPhaseClass();
  }

  function unlockAudio() {
    if (audio) return;
    audio = new Audio("/static/toolbox/sounds/timer_end.wav");
    audio.preload = "auto";
    audio.volume = 0.35;
    audio.playbackRate = Number(window.TOOLBOX_TIMER_END_RATE) || 3;
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

  function stopEnd() {
    ringing = false;
    if (!audio) return;
    audio.pause();
    audio.currentTime = 0;
  }

  function silenceGateRing() {
    if (phase !== "gate" || !ringing) return false;
    stopEnd();
    endedPhase = "";
    renderClock();
    return true;
  }

  function playEnd(loop) {
    unlockAudio();
    if (!audio) {
      beep(520, 0.35);
      return;
    }
    audio.playbackRate = Number(window.TOOLBOX_TIMER_END_RATE) || 3;
    audio.loop = loop !== false;
    audio.currentTime = 0;
    ringing = audio.loop;
    audio.play().catch(() => beep(520, 0.35));
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
    const f = els["ms-format"].value;
    if (f === "trio") return ["speakA", "speakB", "speakC"];
    return f === "pair" ? ["speakA", "speakB"] : ["speak"];
  }

  function phaseDuration(next) {
    if (next === "prep") return (Number(els["ms-prep"].value) || 60) * 1000;
    if (next === "speak" || next === "speakA" || next === "speakB" || next === "speakC") return (Number(els["ms-speak"].value) || 60) * 1000;
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
    if (current === "speakB" && els["ms-format"].value === "trio") return "speakC";
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
      playEnd(true);
      return;
    }
    startRunning();
  }

  function finishPhase() {
    const upcoming = nextPhaseAfter(phase);
    endedPhase = phase;
    if (!upcoming) {
      phase = "done";
      playEnd(true);
      renderClock();
      return;
    }
    const autoSolo = !isPair() && phase === "prep" && els["ms-auto"].checked;
    if (autoSolo) {
      playEnd(false);
      beginPhase(upcoming);
      return;
    }
    playEnd(true);
    armGate(upcoming);
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
      stopEnd();
      beginPhase("prep");
      return;
    }
    if (phase === "gate") {
      if (silenceGateRing()) return;
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
    if (courseMode()) {
      if (!item || !item.id) return false;
      return window.MinuteSpeechCourses.findListEntry(store, courseId(), item.id, item.type) != null;
    }
    if (topicIsActiveUsed(item)) return true;
    if (!item || !item.id || !classId()) return false;
    return topicInLists(item, Object.values(archivedYears()));
  }

  function topicIsCompleteForCourse(item) {
    if (!courseMode() || !item || !item.id) return false;
    const hit = window.MinuteSpeechCourses.findListEntry(store, courseId(), item.id, item.type);
    return !!(hit && hit.entry.completedAt);
  }

  function pushUsed(item) {
    if (courseMode()) {
      if (!classId() || !item || !item.id) return;
      window.MinuteSpeechCourses.markClassDone(store, courseId(), classId(), item, item.type);
      clearNext(item);
      saveStore();
      renderTopicList();
      return;
    }
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
    if (courseMode()) {
      if (!classId() || !item || !item.id) return;
      window.MinuteSpeechCourses.toggleClassDone(store, courseId(), classId(), item.id, item.type);
      saveStore();
      renderTopicList();
      return;
    }
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

  function nextTopicOrder(item) {
    const order = Number(item && item.source_order);
    if (order > 0 && order <= 10000) return order;
    const ids = catalogIds[Number(item.type)] || [];
    const idx = ids.indexOf(item.id);
    return idx >= 0 ? idx + 1 : 1e9;
  }

  function nextTopicsForCatalogType(typeNum) {
    return nextList()
      .filter((row) => Number(row.type) === Number(typeNum))
      .slice()
      .sort((a, b) => nextTopicOrder(a) - nextTopicOrder(b));
  }

  function catalogItemsWithNextPinned(pageResults, typeNum) {
    const pinned = nextTopicsForCatalogType(typeNum);
    if (!pinned.length) return pageResults.slice();
    const pinnedIds = new Set(pinned.map((row) => row.id));
    return pinned.concat((pageResults || []).filter((item) => !pinnedIds.has(item.id)));
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

  function addToCourseListButton(item) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "tb-btn";
    button.textContent = topicIsUsed(item) ? "リストに追加済み" : "この授業のお題リストに追加";
    button.disabled = topicIsUsed(item);
    button.addEventListener("click", () => {
      if (!courseId()) {
        alert("授業を選んでください。");
        return;
      }
      window.MinuteSpeechCourses.appendTopicToList(store, courseId(), item);
      saveStore();
      button.disabled = true;
      button.textContent = "リストに追加済み";
      renderTopicList();
      refreshUsedSurfaces(item.id);
    });
    return button;
  }

  function refreshNextSurfaces(topicId) {
    document.querySelectorAll("#ms-results .ms-card").forEach((card) => {
      if (topicId && card.dataset.topicId !== topicId) return;
      applyNextLook(card, topicIsNext({ id: card.dataset.topicId }));
    });
    if (catalogPageSnapshot !== null) {
      renderCatalogCards(catalogItemsWithNextPinned(catalogPageSnapshot, catType));
    } else {
      document.querySelectorAll("#ms-catalog .ms-card").forEach((card) => {
        if (topicId && card.dataset.topicId !== topicId) return;
        applyNextLook(card, topicIsNext({ id: card.dataset.topicId }));
      });
      const shown = els["ms-catalog"].querySelectorAll(".ms-card").length;
      if (shown && catalogCount) {
        const usedCount = els["ms-catalog"].querySelectorAll(".ms-card.is-used").length;
        const nextCount = els["ms-catalog"].querySelectorAll(".ms-card.is-next").length;
        els["ms-cat-status"].textContent = `このページ ${shown} 件中、使用済み ${usedCount} 件、次回使う ${nextCount} 件。全 ${catalogCount} 件。`;
      }
    }
    paintCatalogPages(catalogCount);
  }

  function renderCatalogCards(items) {
    const used = courseMode()
      ? new Set(window.MinuteSpeechCourses.allListTopicIds(store, courseId()))
      : new Set(spentRows(catType).map((row) => row.id));
    const box = els["ms-catalog"];
    const status = els["ms-cat-status"];
    box.innerHTML = "";
    items.forEach((item) => {
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
      actions.append(use, courseMode() ? addToCourseListButton(item) : nextToggleButton(item), usedToggleButton(item));
      card.appendChild(actions);
      box.appendChild(card);
    });
    const shown = items.length;
    const usedCount = items.filter((item) => used.has(item.id)).length;
    const nextCount = items.filter((item) => topicIsNext(item)).length;
    if (status) {
      status.textContent = shown
        ? `このページ ${shown} 件中、使用済み ${usedCount} 件${courseMode() ? "" : `、次回使う ${nextCount} 件`}。全 ${catalogCount} 件。`
        : "表示できるお題がありません。";
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

  function drawTypeNum() {
    const type = typeValue();
    if (type === "mixed") return Math.random() < 0.5 ? 1 : 2;
    return Number(type);
  }

  async function drawNext(retried) {
    if (courseMode() && classId()) {
      const typeNum = drawTypeNum();
      const list = (courseBucket().lists[String(typeNum)] || []);
      let pending = null;
      for (let i = 0; i < list.length; i += 1) {
        const entry = list[i];
        if (entry.completedAt) continue;
        const tid = window.MinuteSpeechCourses.entryTopicId(entry);
        if (sessionSkipped.includes(tid)) continue;
        if (!entry.done || !entry.done[classId()]) {
          pending = entry;
          break;
        }
      }
      if (pending) {
        topic = window.MinuteSpeechCourses.entryAsTopic(pending);
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
    }
    const data = await toolboxFetch("/toolbox/api/minute-speech/draw", {
      method: "POST",
      body: JSON.stringify(Object.assign({ exclude_ids: excludeIds() }, filters())),
    });
    if (!data.topic) {
      if (retried || !classId()) {
        alert("条件に合うお題がありません。難易度やフラグの設定を確認してください。");
        return false;
      }
      const ok = courseMode()
        ? confirm("この授業の選んだタイプは全部使い終わりました。リストをアーカイブして最初から出しますか？")
        : confirm("このクラスの選んだタイプは全部使い終わりました。履歴をリセットして最初から出しますか？");
      if (!ok) return false;
      resetTypes();
      return drawNext(true);
    }
    if (courseMode() && classId()) {
      window.MinuteSpeechCourses.appendTopicToList(store, courseId(), data.topic);
      saveStore();
      renderTopicList();
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
    if (courseMode() && courseId()) {
      const bucket = courseBucket();
      const types = typeValue() === "mixed" ? ["1", "2"] : [String(typeValue())];
      const year = String(schoolYear());
      bucket.archived = bucket.archived || {};
      bucket.archived[year] = bucket.archived[year] || { 1: [], 2: [] };
      types.forEach((key) => {
        const completed = (bucket.lists[key] || []).filter((e) => e.completedAt);
        bucket.archived[year][key] = (bucket.archived[year][key] || []).concat(
          completed.map((e) => Object.assign({}, window.MinuteSpeechCourses.entryAsTopic(e), { archivedAt: new Date().toISOString() })),
        );
        bucket.lists[key] = (bucket.lists[key] || []).filter((e) => !e.completedAt);
        bucket.rounds[key] = (Number(bucket.rounds[key]) || 1) + 1;
      });
      sessionSkipped = [];
      saveStore();
      renderTopicList();
      return;
    }
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
    stopEnd();
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

  function showUndoToast(message, undoFn) {
    const toast = els["ms-undo-toast"];
    const msg = els["ms-undo-msg"];
    const btn = els["ms-undo-btn"];
    if (!toast || !btn) return;
    clearTimeout(undoTimer);
    if (msg) msg.textContent = message;
    undoSnapshot = undoFn;
    toast.hidden = false;
    undoTimer = setTimeout(() => {
      toast.hidden = true;
      undoSnapshot = null;
    }, 5000);
    btn.onclick = () => {
      if (undoSnapshot) undoSnapshot();
      toast.hidden = true;
      undoSnapshot = null;
      clearTimeout(undoTimer);
      renderTopicList();
      refreshUsedSurfaces();
    };
  }

  function renderTopicList() {
    const openBox = els["ms-topic-list-open"];
    const doneBox = els["ms-topic-list-done"];
    if (!openBox || !doneBox) return;
    openBox.innerHTML = "";
    doneBox.innerHTML = "";
    const course = currentCourse();
    if (!course || !courseId()) {
      if (els["ms-topic-list-summary"]) els["ms-topic-list-summary"].textContent = "授業を選ぶと、お題リストが表示されます。";
      return;
    }
    const MSC = window.MinuteSpeechCourses;
    const targets = MSC.targetClassIds(course, classes);
    const list = (courseBucket().lists[String(listType)] || []);
    let completeCount = 0;
    list.forEach((entry, index) => {
      const complete = !!entry.completedAt;
      if (complete) completeCount += 1;
      const show = listFilter === "all"
        || (listFilter === "done" && complete)
        || (listFilter === "open" && !complete);
      if (!show) return;
      const row = document.createElement("div");
      row.className = complete ? "ms-topic-row is-complete" : "ms-topic-row";
      const left = document.createElement("div");
      const topicObj = MSC.entryAsTopic(entry);
      const jaLine = els["ms-ja"].checked && topicObj.ja
        ? `<p class="tb-muted" style="margin:4px 0 0;font-size:0.82rem">${esc(topicObj.ja)}</p>`
        : "";
      left.innerHTML = `<strong>${index + 1}</strong> · ${esc(topicObj.text || "")}${jaLine}`;
      const chips = document.createElement("div");
      chips.className = "ms-topic-chips";
      const doneN = MSC.entryDoneCount(entry, targets);
      const progress = document.createElement("span");
      progress.className = "ms-topic-progress";
      progress.textContent = complete ? "使用済み" : (doneN ? `${doneN}/${targets.length}` : "未着手");
      MSC.targetClassIds(course, classes).forEach((cid) => {
        const classRow = classes.find((c) => c.id === cid);
        if (!classRow) return;
        const label = document.createElement("label");
        label.className = "ms-check-label";
        if (classRow.id === classId()) label.classList.add("is-today");
        const box = document.createElement("input");
        box.type = "checkbox";
        box.checked = !!(entry.done && entry.done[classRow.id]);
        label.append(box, document.createTextNode(classRow.name));
        box.addEventListener("change", () => {
          const before = JSON.parse(JSON.stringify(entry.done || {}));
          const beforeCompleted = entry.completedAt;
          MSC.toggleClassDone(store, courseId(), classRow.id, MSC.entryTopicId(entry), listType);
          saveStore();
          showUndoToast("済の変更を元に戻しますか？", () => {
            entry.done = before;
            entry.completedAt = beforeCompleted;
            saveStore();
          });
          renderTopicList();
        });
        chips.appendChild(label);
      });
      row.append(left, chips, progress);
      (complete ? doneBox : openBox).appendChild(row);
    });
    if (els["ms-topic-list-title"]) els["ms-topic-list-title"].textContent = `${course.name} · タイプ${listType}`;
    if (els["ms-topic-list-summary"]) {
      els["ms-topic-list-summary"].textContent = `クラス ${targets.length} / 完了 ${completeCount} / リスト ${list.length}`;
    }
    const sum = els["ms-topic-list-done-summary"];
    if (sum) sum.textContent = `使用済み（${completeCount}）`;
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
      actions.append(use, courseMode() ? addToCourseListButton(item) : nextToggleButton(item), usedToggleButton(item), hide);
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
      version: store.schemaVersion >= 2 ? 2 : 1,
      exportedAt: new Date().toISOString(),
      history: store.history,
      rounds: store.rounds,
      hiddenTopicIds: store.hiddenTopicIds,
      nextUse: store.nextUse,
      archived: store.archived,
      prefs: store.prefs,
      scopes: store.scopes,
      lastClass: store.lastClass,
      courseState: store.courseState,
      lastCourse: store.lastCourse,
      schemaVersion: store.schemaVersion,
      courses: window.ToolboxClasses ? window.ToolboxClasses.loadCourses() : [],
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
        if (window.MinuteSpeechCourses) window.MinuteSpeechCourses.backupKeys();
        const data = JSON.parse(String(reader.result || ""));
        if (!data || (typeof data.history !== "object" && !data.courseState)) throw new Error("形式が違います。");
        if (Array.isArray(data.courses) && window.ToolboxClasses) {
          window.ToolboxClasses.saveCourses(data.courses);
        }
        store.history = data.history || store.history || {};
        store.rounds = data.rounds || store.rounds || {};
        store.hiddenTopicIds = data.hiddenTopicIds || [];
        if (data.nextUse && typeof data.nextUse === "object") store.nextUse = data.nextUse;
        if (data.archived && typeof data.archived === "object") store.archived = data.archived;
        if (data.prefs && typeof data.prefs === "object") store.prefs = data.prefs;
        if (data.scopes && typeof data.scopes === "object") store.scopes = data.scopes;
        if (data.lastClass && typeof data.lastClass === "object") store.lastClass = data.lastClass;
        if (data.courseState && typeof data.courseState === "object") store.courseState = data.courseState;
        if (data.lastCourse && typeof data.lastCourse === "object") store.lastCourse = data.lastCourse;
        if (data.schemaVersion) store.schemaVersion = data.schemaVersion;
        if (window.MinuteSpeechCourses) window.MinuteSpeechCourses.ensureLoaded(store);
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

  function showPanel(name) {
    els["ms-panel-setup"].hidden = name !== "setup";
    if (els["ms-panel-topics"]) els["ms-panel-topics"].hidden = name !== "topics";
    els["ms-panel-history"].hidden = name !== "history";
    document.getElementById("ms-tab-setup").classList.toggle("tb-btn-primary", name === "setup");
    if (document.getElementById("ms-tab-topics")) {
      document.getElementById("ms-tab-topics").classList.toggle("tb-btn-primary", name === "topics");
    }
    document.getElementById("ms-tab-history").classList.toggle("tb-btn-primary", name === "history");
    if (name === "topics") renderTopicList();
    if (name === "history") renderHistory();
  }

  document.getElementById("ms-tab-setup").addEventListener("click", () => showPanel("setup"));
  if (document.getElementById("ms-tab-topics")) {
    document.getElementById("ms-tab-topics").addEventListener("click", () => showPanel("topics"));
  }
  document.getElementById("ms-tab-history").addEventListener("click", () => showPanel("history"));
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
      if (id === "ms-ja") renderTopicList();
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
  els["ms-reset"].addEventListener("click", () => {
    stopTick();
    stopEnd();
    clearTimeout(switchTimer);
    endedPhase = "";
    phase = "idle";
    remainingMs = (Number(els["ms-prep"].value) || 60) * 1000;
    renderTopic();
    renderClock();
  });
  function phaseSeq() {
    return ["prep"].concat(speakPhases());
  }
  function stepPhase(delta) {
    const seq = phaseSeq();
    const cur = phase === "done" ? seq.length - 1 : Math.max(0, seq.indexOf(shownPhase()));
    const to = Math.min(seq.length - 1, Math.max(0, cur + delta));
    if (to === cur && phase !== "done") return;
    stopEnd();
    endedPhase = "";
    armGate(seq[to]);
  }
  els["ms-phase-prev"].addEventListener("click", () => stepPhase(-1));
  els["ms-phase-next"].addEventListener("click", () => stepPhase(1));
  els["ms-toggle-ja"].addEventListener("click", () => {
    els["ms-ja"].checked = !els["ms-ja"].checked;
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

  document.addEventListener("pointerdown", (ev) => {
    if (!ringing || phase === "gate") return;
    if (ev.target && ev.target.closest && ev.target.closest("#ms-start, #ms-pause, #ms-reset, #ms-phase-prev, #ms-phase-next")) return;
    ev.preventDefault();
    stopEnd();
  }, true);
  document.addEventListener("keydown", (ev) => {
    if (ev.target && /INPUT|TEXTAREA|SELECT/.test(ev.target.tagName)) return;
    if (stage.hidden) return;
    const key = ev.key.toLowerCase();
    if (key === " " && window.ToolboxDisplay && window.ToolboxDisplay.isOn()) return;
    if (key === " ") {
      ev.preventDefault();
      toggleRun();
    }
    if (key === "arrowleft") { ev.preventDefault(); els["ms-phase-prev"].click(); }
    if (key === "arrowright") { ev.preventDefault(); els["ms-phase-next"].click(); }
    if (key === "r") {
      ev.preventDefault();
      els["ms-reset"].click();
    }
    if (key === "j") els["ms-toggle-ja"].click();
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
  renderTopicList();
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
    fillCourses();
    fillClasses();
    const savedCourse = (store.lastCourse || {})[teacherId()] || "";
    if (savedCourse && courses.some((row) => row.id === savedCourse) && els["ms-course"]) {
      els["ms-course"].value = savedCourse;
    }
    selectClass((courseBucket() && courseBucket().lastClassId) || (store.lastClass || {})[teacherId()] || "");
    enterScope(teacherId(), classId(), courseId());
    loadCatalog();
    renderTopicList();
    if (!els["ms-panel-history"].hidden) renderHistory();
  });
  if (els["ms-course"]) {
    els["ms-course"].addEventListener("change", () => {
      scopeCourse = els["ms-course"].value || "";
      fillClasses();
      selectClass((courseBucket() && courseBucket().lastClassId) || "");
      enterScope(teacherId(), classId(), courseId());
      loadCatalog();
      renderTopicList();
    });
  }
  els["ms-class"].addEventListener("change", () => {
    rememberScope();
    enterScope(teacherId(), classId(), courseId());
    renderTodayClasses();
    loadCatalog();
    renderTopicList();
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
    fillCourses();
    fillClasses();
    selectClass("");
    enterScope(teacherId(), classId(), courseId());
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
    courses.forEach((item) => {
      if (item.teacher_id === row.id) item.teacher_id = "";
    });
    classes = window.ToolboxClasses.save(classes);
    courses = window.ToolboxClasses.saveCourses(courses);
    teachers = window.ToolboxClasses.saveTeachers(teachers.filter((item) => item.id !== row.id));
    fillTeachers();
    fillCourses();
    fillClasses();
    selectClass((store.lastClass || {})[teacherId()] || "");
    enterScope(teacherId(), classId(), courseId());
    loadCatalog();
  });
  if (els["ms-course-add"]) {
    els["ms-course-add"].addEventListener("click", () => {
      if (!teacherId()) {
        alert("先に担当教員を選んでください。");
        return;
      }
      const name = prompt("授業名");
      if (!name || !name.trim()) return;
      const classIds = activeTeacherClasses().map((row) => row.id);
      const id = newLocalId();
      courses.push({
        id,
        name: name.trim(),
        teacher_id: teacherId(),
        class_ids: classIds,
        year: "",
        hidden_year: "",
        order: courses.length,
      });
      courses = window.ToolboxClasses.saveCourses(courses);
      window.MinuteSpeechCourses.ensureCourseBucket(store, id).settings = settingsFromForm();
      fillCourses();
      els["ms-course"].value = id;
      scopeCourse = id;
      fillClasses();
      enterScope(teacherId(), classId(), id);
      saveStore();
      renderTopicList();
    });
  }
  if (els["ms-course-edit"]) {
    els["ms-course-edit"].addEventListener("click", () => {
      const course = currentCourse();
      if (!course) return;
      const name = prompt("授業名", course.name);
      if (!name || !name.trim()) return;
      course.name = name.trim();
      courses = window.ToolboxClasses.saveCourses(courses.map((row) => (row.id === course.id ? course : row)));
      fillCourses();
      els["ms-course"].value = course.id;
      renderTopicList();
    });
  }
  if (els["ms-course-split"]) {
    els["ms-course-split"].addEventListener("click", () => {
      const course = currentCourse();
      if (!course || !course.class_ids.length) return;
      const names = courseClassRows().map((row) => row.name).join("、");
      const pick = prompt(`新しい授業へ分けるクラス名（例: 1-2）\nこの授業: ${names}`);
      if (!pick || !pick.trim()) return;
      const tokens = pick.split(/[,、]/).map((s) => s.trim()).filter(Boolean);
      const moveIds = courseClassRows().filter((row) => tokens.includes(row.name)).map((row) => row.id);
      if (!moveIds.length) {
        alert("クラス名が一致しませんでした。");
        return;
      }
      const newName = prompt("新しい授業名", "論理表現II");
      if (!newName || !newName.trim()) return;
      const newId = newLocalId();
      const newCourse = {
        id: newId,
        name: newName.trim(),
        teacher_id: course.teacher_id,
        class_ids: moveIds.slice(),
        year: "",
        hidden_year: "",
        order: courses.length,
      };
      const srcBucket = courseBucket();
      const dstBucket = window.MinuteSpeechCourses.ensureCourseBucket(store, newId);
      dstBucket.settings = JSON.parse(JSON.stringify(srcBucket.settings || settingsFromForm()));
      dstBucket.lists = { 1: [], 2: [] };
      ["1", "2"].forEach((typeKey) => {
        (srcBucket.lists[typeKey] || []).forEach((entry) => {
          const copy = JSON.parse(JSON.stringify(entry));
          copy.done = {};
          moveIds.forEach((cid) => {
            if (entry.done && entry.done[cid]) copy.done[cid] = entry.done[cid];
            if (entry.done && entry.done[cid]) delete entry.done[cid];
          });
          const targets = window.MinuteSpeechCourses.targetClassIds(course, classes);
          window.MinuteSpeechCourses.recomputeCompletedAt(entry, targets);
          if (Object.keys(copy.done).length) dstBucket.lists[typeKey].push(copy);
        });
      });
      course.class_ids = course.class_ids.filter((id) => !moveIds.includes(id));
      courses = courses.concat([newCourse]);
      courses = window.ToolboxClasses.saveCourses(courses);
      saveStore();
      fillCourses();
      els["ms-course"].value = course.id;
      fillClasses();
      renderTopicList();
    });
  }
  if (els["ms-course-copy"]) {
    els["ms-course-copy"].addEventListener("click", () => {
      const course = currentCourse();
      if (!course) return;
      const name = prompt("来年度用の授業名", `${course.name}（2027）`);
      if (!name || !name.trim()) return;
      const year = prompt("元の授業を非表示にする年度（空ならそのまま）", String(schoolYear()));
      const id = newLocalId();
      const newCourse = {
        id,
        name: name.trim(),
        teacher_id: course.teacher_id,
        class_ids: [],
        year: "",
        hidden_year: "",
        order: courses.length,
      };
      if (/^\d{4}$/.test(String(year || ""))) course.hidden_year = String(year);
      const bucket = courseBucket();
      window.MinuteSpeechCourses.ensureCourseBucket(store, id).settings = JSON.parse(JSON.stringify(bucket.settings || settingsFromForm()));
      courses = window.ToolboxClasses.saveCourses(courses.map((row) => (row.id === course.id ? course : row)).concat([newCourse]));
      fillCourses();
      els["ms-course"].value = id;
      scopeCourse = id;
      fillClasses();
      saveStore();
      renderTopicList();
    });
  }
  if (els["ms-course-del"]) {
    els["ms-course-del"].addEventListener("click", async () => {
      const course = currentCourse();
      if (!course) return;
      if (!await confirmDelete(`${course.name} を削除しますか？お題リストも消えます。書き出しを済ませてください。`)) return;
      delete store.courseState[course.id];
      courses = window.ToolboxClasses.saveCourses(courses.filter((row) => row.id !== course.id));
      fillCourses();
      fillClasses();
      enterScope(teacherId(), classId(), courseId());
      saveStore();
      renderTopicList();
    });
  }
  // ── クラスの振り分け（1年→論理表現 I / 2年→論理表現 II）──────────
  const ASSIGN_DEFS = {
    "1": { name: "論理表現 I", key: "論理表現i" },
    "2": { name: "論理表現 II", key: "論理表現ii" },
  };
  const ASSIGN_LAST = "toolbox.minuteSpeech.assignBackupLast";
  const ASSIGN_PREFIX = "toolbox.minuteSpeech.assignBackup.";
  const RAW_KEYS = {
    teachers: "toolbox.local_teachers.v1",
    classes: "toolbox.local_classes.v1",
    courses: "toolbox.local_courses.v1",
    speech: KEY,
  };

  function nfkc(text) { return String(text || "").normalize("NFKC"); }
  function courseKey(text) { return nfkc(text).toLowerCase().replace(/\s+/g, ""); }
  function gradeOf(name) {
    const m = nfkc(name).replace(/^\s+/, "").match(/^([12])(?!\d)/);
    return m ? m[1] : "";
  }
  function naturalCompare(a, b) {
    const fix = (t) => nfkc(t).replace(/前半/g, "~1").replace(/後半/g, "~2");
    return fix(a).localeCompare(fix(b), "ja", { numeric: true });
  }
  function isMigrationCourse(course) { return nfkc(course.name).startsWith("(移行)"); }
  function oldUsedCount(classKey) {
    const hist = (store.history || {})[classKey] || {};
    let n = 0;
    Object.values(hist).forEach((list) => { if (Array.isArray(list)) n += list.length; });
    n += (((store.nextUse || {})[classKey]) || []).length;
    return n;
  }

  function assignCandidates() {
    const teacher = teacherId();
    const all = window.ToolboxClasses.load();
    const allCourses = window.ToolboxClasses.loadCourses();
    return all
      .filter((row) => !row.hidden_year)
      .filter((row) => !row.teacher_id || row.teacher_id === teacher)
      .filter((row) => allCourses.filter((c) => c.class_ids.includes(row.id)).every(isMigrationCourse))
      .sort((a, b) => naturalCompare(a.name, b.name));
  }

  function closeAssignDialog() {
    els["ms-assign-dialog"].hidden = true;
    els["ms-assign-box"].innerHTML = "";
  }

  function openAssignDialog() {
    const teacher = teacherId();
    if (!teacher) {
      alert("先に担当教員を選んでください。");
      return;
    }
    const all = window.ToolboxClasses.load();
    const allCourses = window.ToolboxClasses.loadCourses();
    const rows = assignCandidates();
    const mine = all.filter((c) => c.teacher_id === teacher).length;
    const none = all.filter((c) => !c.teacher_id).length;
    const other = all.length - mine - none;
    const box = els["ms-assign-box"];
    const hasBackup = !!localStorage.getItem(ASSIGN_LAST);
    box.innerHTML = `<h2>クラスを振り分ける</h2>
      <p class="tb-note">診断: クラス ${all.length} 件（担当あり ${mine}／担当なし ${none}／他教員 ${other}）、授業 ${allCourses.length} 件（移行授業 ${allCourses.filter(isMigrationCourse).length}）。対象 ${rows.length} クラス。</p>`;
    const table = document.createElement("table");
    table.innerHTML = "<thead><tr><th>クラス名</th><th>振り分け先</th><th>旧データの使用済み</th></tr></thead>";
    const tbody = document.createElement("tbody");
    const selects = [];
    rows.forEach((row) => {
      const tr = document.createElement("tr");
      const grade = gradeOf(row.name);
      tr.innerHTML = `<td>${esc(row.name)}</td><td></td><td>${oldUsedCount(row.id)} 件</td>`;
      const sel = document.createElement("select");
      sel.innerHTML = `<option value="">振り分けない</option><option value="1">${ASSIGN_DEFS["1"].name}</option><option value="2">${ASSIGN_DEFS["2"].name}</option>`;
      sel.value = grade;
      tr.children[1].appendChild(sel);
      selects.push({ row, sel });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    box.appendChild(table);
    if (!rows.length) {
      const empty = document.createElement("p");
      empty.className = "tb-note";
      empty.textContent = "振り分け対象のクラスはありません（未設定、または移行授業にだけ入っているクラス）。";
      box.appendChild(empty);
    }
    const importLabel = document.createElement("label");
    importLabel.className = "tb-check";
    importLabel.innerHTML = '<input type="checkbox" checked> 旧データの使用済みを、済として取り込む';
    box.appendChild(importLabel);
    const actions = document.createElement("div");
    actions.className = "ms-chips";
    const run = document.createElement("button");
    run.type = "button";
    run.className = "tb-btn tb-btn-primary";
    run.textContent = "実行";
    run.disabled = !rows.length;
    run.addEventListener("click", () => {
      const plan = selects.map((s) => ({ row: s.row, grade: s.sel.value }));
      runAssign(plan, importLabel.querySelector("input").checked);
    });
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "tb-btn";
    cancel.textContent = "閉じる";
    cancel.addEventListener("click", closeAssignDialog);
    actions.append(run, cancel);
    if (hasBackup) actions.appendChild(undoAssignButton());
    box.appendChild(actions);
    els["ms-assign-dialog"].hidden = false;
  }

  function undoAssignButton() {
    const undo = document.createElement("button");
    undo.type = "button";
    undo.className = "tb-btn";
    undo.textContent = "直前の振り分けを元に戻す";
    undo.addEventListener("click", () => {
      const stamp = localStorage.getItem(ASSIGN_LAST);
      let data = null;
      try { data = JSON.parse(localStorage.getItem(ASSIGN_PREFIX + stamp) || "null"); } catch (_) {}
      if (!data) {
        alert("バックアップが見つかりません。");
        return;
      }
      if (!confirm("直前の振り分けの前の状態に戻します。よろしいですか？")) return;
      Object.keys(RAW_KEYS).forEach((name) => {
        if (data[name] == null) localStorage.removeItem(RAW_KEYS[name]);
        else localStorage.setItem(RAW_KEYS[name], data[name]);
      });
      localStorage.removeItem(ASSIGN_LAST);
      location.reload();
    });
    return undo;
  }

  function runAssign(plan, doImport) {
    const targets = plan.filter((p) => p.grade);
    if (!targets.length) {
      alert("振り分け先が選ばれたクラスがありません。");
      return;
    }
    if (!confirm(`${targets.length} クラスを振り分けます。実行前に自動バックアップを取ります。よろしいですか？`)) return;
    const teacher = teacherId();
    const stamp = new Date().toISOString();
    const backup = { at: stamp };
    Object.keys(RAW_KEYS).forEach((name) => { backup[name] = localStorage.getItem(RAW_KEYS[name]); });
    localStorage.setItem(ASSIGN_PREFIX + stamp, JSON.stringify(backup));
    localStorage.setItem(ASSIGN_LAST, stamp);

    const MSC = window.MinuteSpeechCourses;
    let cs = window.ToolboxClasses.loadCourses();
    const all = window.ToolboxClasses.load();
    const created = [];
    const ensureCourse = (grade) => {
      const def = ASSIGN_DEFS[grade];
      let course = cs.find((c) => c.teacher_id === teacher && courseKey(c.name) === def.key);
      if (!course) {
        course = { id: newLocalId(), name: def.name, teacher_id: teacher, class_ids: [], year: "", hidden_year: "", order: cs.length };
        cs.push(course);
        created.push(def.name);
      }
      return course;
    };

    const ops = [];
    const summary = {};
    const touchedSources = new Set();
    targets.forEach(({ row, grade }) => {
      const dst = ensureCourse(grade);
      const dstBucket = MSC.ensureCourseBucket(store, dst.id);
      const sources = cs.filter((c) => c.id !== dst.id && c.class_ids.includes(row.id) && isMigrationCourse(c));
      if (!dstBucket.settings) {
        const srcSettings = sources.map((s) => ((store.courseState || {})[s.id] || {}).settings).find(Boolean);
        dstBucket.settings = JSON.parse(JSON.stringify(srcSettings || settingsFromForm()));
      }
      sources.forEach((src) => {
        src.class_ids = src.class_ids.filter((id) => id !== row.id);
        touchedSources.add(src.id);
        const sb = (store.courseState || {})[src.id];
        if (!sb) return;
        ["1", "2"].forEach((typeKey) => {
          (sb.lists[typeKey] || []).forEach((entry) => {
            if (entry.done && entry.done[row.id]) {
              ops.push({ dst, typeKey, id: MSC.entryTopicId(entry), meta: entry.meta || {}, date: entry.done[row.id], cid: row.id });
            }
          });
        });
      });
      if (doImport) {
        const hist = (store.history || {})[row.id] || {};
        ["1", "2"].forEach((typeKey) => {
          (hist[typeKey] || []).forEach((h) => {
            if (!h || !h.id) return;
            ops.push({
              dst, typeKey, id: h.id, date: (h.usedAt || "").slice(0, 10) || MSC.todayIsoDate(), cid: row.id,
              meta: { text: h.text, suffix: h.suffix, type: h.type, ja: h.ja || "", source_order: h.source_order },
            });
          });
        });
        (((store.nextUse || {})[row.id]) || []).forEach((n) => {
          if (!n || !n.id) return;
          ops.push({
            dst, typeKey: String(n.type || 1), id: n.id, date: "", cid: "",
            meta: { text: n.text, suffix: n.suffix, type: n.type, ja: n.ja || "", source_order: n.source_order },
          });
        });
      }
      if (!dst.class_ids.includes(row.id)) dst.class_ids.push(row.id);
      summary[dst.name] = (summary[dst.name] || 0) + 1;
    });

    ops.sort((a, b) => String(a.date || "9999").localeCompare(String(b.date || "9999")));
    let imported = 0;
    const touchedDst = new Set();
    ops.forEach((op) => {
      const bucket = MSC.ensureCourseBucket(store, op.dst.id);
      const list = bucket.lists[op.typeKey] = bucket.lists[op.typeKey] || [];
      let entry = list.find((e) => MSC.entryTopicId(e) === op.id);
      if (!entry) {
        entry = { topicId: op.id, addedAt: new Date().toISOString(), done: {}, completedAt: null, meta: op.meta };
        list.push(entry);
      }
      touchedDst.add(op.dst.id);
      if (op.cid && !(entry.done || {})[op.cid]) {
        entry.done = entry.done || {};
        entry.done[op.cid] = op.date;
        imported += 1;
      }
    });

    cs.forEach((course) => {
      course.class_ids = course.class_ids
        .slice()
        .sort((a, b) => {
          const ra = all.find((c) => c.id === a);
          const rb = all.find((c) => c.id === b);
          return naturalCompare(ra ? ra.name : "", rb ? rb.name : "");
        });
    });
    cs = window.ToolboxClasses.saveCourses(cs);
    touchedDst.forEach((id) => {
      const course = cs.find((c) => c.id === id);
      const tg = MSC.targetClassIds(course, all);
      const bucket = MSC.ensureCourseBucket(store, id);
      ["1", "2"].forEach((k) => (bucket.lists[k] || []).forEach((e) => { if (!e.completedAt) MSC.recomputeCompletedAt(e, tg); }));
    });
    touchedSources.forEach((id) => {
      const course = cs.find((c) => c.id === id);
      const bucket = (store.courseState || {})[id];
      if (!course || !bucket) return;
      const tg = MSC.targetClassIds(course, all);
      ["1", "2"].forEach((k) => (bucket.lists[k] || []).forEach((e) => MSC.recomputeCompletedAt(e, tg)));
    });
    saveStore();

    courses = window.ToolboxClasses.loadCourses();
    fillCourses();
    const first = cs.find((c) => c.teacher_id === teacher && courseKey(c.name) === ASSIGN_DEFS["1"].key)
      || cs.find((c) => c.teacher_id === teacher && courseKey(c.name) === ASSIGN_DEFS["2"].key);
    if (first && els["ms-course"]) {
      els["ms-course"].value = first.id;
      scopeCourse = first.id;
    }
    fillClasses();
    selectClass((courseBucket() && courseBucket().lastClassId) || "");
    enterScope(teacherId(), classId(), courseId());
    renderTopicList();
    loadCatalog();
    showAssignResult(summary, imported, created, Array.from(touchedSources), assignCandidates());
  }

  function showAssignResult(summary, imported, created, sourceIds, remaining) {
    const box = els["ms-assign-box"];
    box.innerHTML = "<h2>振り分け結果</h2>";
    const lines = Object.keys(summary).map((name) => `${name}: ${summary[name]} クラス`);
    const info = document.createElement("p");
    info.textContent = `${lines.join(" ／ ")}。済の取り込み ${imported} 件。${created.length ? `新規作成: ${created.join("、")}。` : ""}`;
    box.appendChild(info);
    const rest = document.createElement("p");
    rest.className = "tb-note";
    rest.textContent = remaining.length ? `未設定のまま残ったクラス: ${remaining.map((r) => r.name).join("、")}` : "未設定のクラスは残っていません。";
    box.appendChild(rest);
    const cs = window.ToolboxClasses.loadCourses();
    sourceIds.forEach((id) => {
      const course = cs.find((c) => c.id === id);
      if (!course || course.class_ids.length) return;
      const line = document.createElement("div");
      line.className = "ms-chips";
      const label = document.createElement("span");
      label.textContent = `「${course.name}」は空になりました。`;
      const hide = document.createElement("button");
      hide.type = "button";
      hide.className = "tb-btn";
      hide.textContent = "非表示にする";
      hide.addEventListener("click", () => {
        course.hidden_year = String(schoolYear());
        window.ToolboxClasses.saveCourses(cs);
        courses = window.ToolboxClasses.loadCourses();
        fillCourses();
        fillClasses();
        renderTopicList();
        hide.disabled = true;
      });
      line.append(label, hide);
      box.appendChild(line);
    });
    const actions = document.createElement("div");
    actions.className = "ms-chips";
    const close = document.createElement("button");
    close.type = "button";
    close.className = "tb-btn tb-btn-primary";
    close.textContent = "閉じる";
    close.addEventListener("click", closeAssignDialog);
    actions.append(close, undoAssignButton());
    box.appendChild(actions);
  }

  if (els["ms-assign-classes"]) els["ms-assign-classes"].addEventListener("click", openAssignDialog);

  if (els["ms-finalize-migration"]) {
    els["ms-finalize-migration"].addEventListener("click", () => {
      if (!confirm("移行用の旧データを削除します。先に書き出し済みですか？")) return;
      window.MinuteSpeechCourses.finalizeMigration(store);
      saveStore();
      showMigrationNotes();
    });
  }
  document.querySelectorAll("[data-ms-list-filter]").forEach((btn) => {
    btn.addEventListener("click", () => {
      listFilter = btn.dataset.msListFilter || "all";
      document.querySelectorAll("[data-ms-list-filter]").forEach((b) => {
        b.classList.toggle("tb-btn-primary", b.dataset.msListFilter === listFilter);
      });
      renderTopicList();
    });
  });
  if (els["ms-list-type-1"]) {
    els["ms-list-type-1"].addEventListener("click", () => {
      listType = 1;
      els["ms-list-type-1"].classList.add("tb-btn-primary");
      els["ms-list-type-2"].classList.remove("tb-btn-primary");
      renderTopicList();
    });
  }
  if (els["ms-list-type-2"]) {
    els["ms-list-type-2"].addEventListener("click", () => {
      listType = 2;
      els["ms-list-type-2"].classList.add("tb-btn-primary");
      els["ms-list-type-1"].classList.remove("tb-btn-primary");
      renderTopicList();
    });
  }
  els["ms-class-add"].addEventListener("click", () => saveClassRow(null));
  els["ms-class-edit"].addEventListener("click", () => {
    const row = classes.find((item) => item.id === classId());
    if (row) saveClassRow(row);
  });
  els["ms-class-del"].addEventListener("click", async () => {
    const row = classes.find((item) => item.id === classId());
    if (!row) return;
    if (!await confirmDelete(`${row.name} をこの端末から削除しますか？`)) return;
    const deletedId = row.id;
    classes = window.ToolboxClasses.save(classes.filter((item) => item.id !== deletedId));
    if (window.MinuteSpeechCourses) {
      courses = window.MinuteSpeechCourses.purgeClassFromStore(store, deletedId, courses, classes);
    }
    saveStore();
    fillClasses();
    enterScope(teacherId(), classId(), courseId());
    loadCatalog();
    renderTopicList();
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
    catalogPageSnapshot = null;
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
      catalogPageSnapshot = data.results || [];
      renderCatalogCards(catalogItemsWithNextPinned(catalogPageSnapshot, catType));
      paintCatalogPages(catalogCount);
    }).catch((err) => {
      status.textContent = err.message;
    });
  }
})();
