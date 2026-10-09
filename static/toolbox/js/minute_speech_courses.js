(function () {
  const SPEECH_KEY = "toolbox.minuteSpeech.v1";
  const SCHEMA_VERSION = 2;
  const BACKUP_PREFIX = "toolbox.minuteSpeech.migrationBackup.";

  function readJson(key) {
    try {
      return JSON.parse(localStorage.getItem(key) || "null");
    } catch (_) {
      return null;
    }
  }

  function writeJson(key, value) {
    localStorage.setItem(key, JSON.stringify(value));
  }

  function todayIsoDate() {
    return new Date().toISOString().slice(0, 10);
  }

  function newId() {
    return (crypto.randomUUID && crypto.randomUUID()) || String(Date.now()) + Math.random().toString(16).slice(2);
  }

  function defaultStore() {
    return {
      schemaVersion: SCHEMA_VERSION,
      courseState: {},
      prefs: { teacherId: "", courseId: "", classId: "" },
      lastCourse: {},
      hiddenTopicIds: [],
      recentQueries: [],
      lastBackupAt: null,
      migrationNotes: [],
      migrationPending: false,
    };
  }

  function normalizeSettings(raw) {
    if (!raw || typeof raw !== "object") return null;
    return Object.assign({}, raw);
  }

  function targetClassIds(course, classes) {
    if (!course || !Array.isArray(course.class_ids)) return [];
    const set = new Set((classes || []).filter((c) => c && c.id && !c.hidden_year).map((c) => c.id));
    return course.class_ids.filter((id) => set.has(id));
  }

  function entryDoneCount(entry, targetIds) {
    const done = (entry && entry.done) || {};
    return targetIds.filter((id) => done[id]).length;
  }

  function recomputeCompletedAt(entry, targetIds) {
    if (!entry || !targetIds.length) {
      if (entry) entry.completedAt = null;
      return false;
    }
    const all = targetIds.every((id) => entry.done && entry.done[id]);
    if (all) {
      if (!entry.completedAt) entry.completedAt = new Date().toISOString();
      return true;
    }
    entry.completedAt = null;
    return false;
  }

  function snapshotFromHistoryRow(row) {
    return {
      topicId: row.id,
      addedAt: row.usedAt || new Date().toISOString(),
      done: {},
      completedAt: null,
      meta: {
        text: row.text,
        suffix: row.suffix,
        type: row.type,
        ja: row.ja || "",
        source_order: row.source_order,
      },
    };
  }

  function entryTopicId(entry) {
    return entry && (entry.topicId || entry.id);
  }

  function ensureCourseBucket(store, courseId) {
    store.courseState = store.courseState || {};
    if (!store.courseState[courseId]) {
      store.courseState[courseId] = {
        settings: null,
        lastClassId: "",
        lists: { 1: [], 2: [] },
        rounds: { 1: 1, 2: 1 },
        archived: {},
      };
    }
    const bucket = store.courseState[courseId];
    bucket.lists = bucket.lists || { 1: [], 2: [] };
    bucket.lists["1"] = Array.isArray(bucket.lists["1"]) ? bucket.lists["1"] : [];
    bucket.lists["2"] = Array.isArray(bucket.lists["2"]) ? bucket.lists["2"] : [];
    bucket.rounds = bucket.rounds || { 1: 1, 2: 1 };
    bucket.archived = bucket.archived || {};
    return bucket;
  }

  function sortEntriesByFirstUse(entries) {
    return entries.slice().sort((a, b) => {
      const datesA = Object.values(a.done || {});
      const datesB = Object.values(b.done || {});
      const minA = datesA.length ? datesA.sort()[0] : a.addedAt || "";
      const minB = datesB.length ? datesB.sort()[0] : b.addedAt || "";
      return String(minA).localeCompare(String(minB));
    });
  }

  function backupKeys() {
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    writeJson(`${BACKUP_PREFIX}${stamp}.minuteSpeech`, localStorage.getItem(SPEECH_KEY));
    writeJson(`${BACKUP_PREFIX}${stamp}.classes`, localStorage.getItem("toolbox.local_classes.v1"));
    writeJson(`${BACKUP_PREFIX}${stamp}.teachers`, localStorage.getItem("toolbox.local_teachers.v1"));
    writeJson(`${BACKUP_PREFIX}${stamp}.courses`, localStorage.getItem("toolbox.local_courses.v1"));
  }

  function pickScopeSettings(store, teacherId, classes) {
    const scopes = store.scopes || {};
    const lastClass = (store.lastClass || {})[teacherId];
    if (lastClass && scopes[`${teacherId}::${lastClass}`]) return scopes[`${teacherId}::${lastClass}`];
    const mine = (classes || []).filter((c) => c.teacher_id === teacherId);
    let best = null;
    let bestAt = "";
    mine.forEach((c) => {
      const s = scopes[`${teacherId}::${c.id}`];
      if (!s) return;
      const key = `${teacherId}::${c.id}`;
      if (!best) best = s;
      if (c.id === lastClass) best = s;
    });
    Object.keys(scopes).forEach((key) => {
      if (!key.startsWith(`${teacherId}::`)) return;
      const s = scopes[key];
      if (!s) return;
      if (!best) best = s;
    });
    return best;
  }

  function scopeSettingsDiffer(scopes, teacherId, classes) {
    const base = pickScopeSettings({ scopes, lastClass: {} }, teacherId, classes);
    if (!base) return [];
    const notes = [];
    (classes || []).filter((c) => c.teacher_id === teacherId).forEach((c) => {
      const s = scopes[`${teacherId}::${c.id}`];
      if (!s) return;
      if (JSON.stringify(s) !== JSON.stringify(base)) {
        notes.push(`${c.name} の設定が代表設定と異なります（移行後に授業設定で確認してください）。`);
      }
    });
    return notes;
  }

  function runMigration(store, teachers, classes, courses) {
    if (store._migrationDone || (store.schemaVersion >= SCHEMA_VERSION && store.courseState && Object.keys(store.courseState).length)) {
      return { store, courses, notes: store.migrationNotes || [] };
    }

    backupKeys();
    const notes = [];
    store.migrationNotes = notes;
    store.migrationPending = true;

    const nextCourses = Array.isArray(courses) ? courses.slice() : [];
    const courseByTeacher = {};

    teachers.forEach((t) => {
      const classIds = (classes || []).filter((c) => c.teacher_id === t.id).map((c) => c.id);
      if (!classIds.length) return;
      const courseId = newId();
      nextCourses.push({
        id: courseId,
        name: `（移行）${t.name}の授業`.slice(0, 40),
        teacher_id: t.id,
        class_ids: classIds,
        year: "",
        hidden_year: "",
        order: nextCourses.length,
      });
      courseByTeacher[t.id] = courseId;
      const bucket = ensureCourseBucket(store, courseId);
      bucket.settings = pickScopeSettings(store, t.id, classes) || bucket.settings;
      bucket.lastClassId = (store.lastClass || {})[t.id] || classIds[0] || "";

      notes.push(...scopeSettingsDiffer(store.scopes || {}, t.id, classes));

      const lists = { 1: [], 2: [] };
      const byType = { 1: new Map(), 2: new Map() };

      classIds.forEach((classId) => {
        const hist = (store.history || {})[classId] || {};
        ["1", "2"].forEach((typeKey) => {
          (hist[typeKey] || []).forEach((row) => {
            if (!row || !row.id) return;
            let entry = byType[typeKey].get(row.id);
            if (!entry) {
              entry = snapshotFromHistoryRow(row);
              entry.topicId = row.id;
              byType[typeKey].set(row.id, entry);
            }
            const usedDay = (row.usedAt || "").slice(0, 10) || todayIsoDate();
            entry.done[classId] = usedDay;
          });
        });
      });

      ["1", "2"].forEach((typeKey) => {
        const entries = sortEntriesByFirstUse(Array.from(byType[typeKey].values()));
        entries.forEach((entry) => {
          recomputeCompletedAt(entry, classIds);
        });
        lists[typeKey] = entries;
      });

      bucket.lists = lists;

      const rounds = { 1: 1, 2: 1 };
      classIds.forEach((classId) => {
        const r = (store.rounds || {})[classId] || {};
        ["1", "2"].forEach((typeKey) => {
          rounds[typeKey] = Math.max(rounds[typeKey], Number(r[typeKey]) || 1);
        });
      });
      bucket.rounds = rounds;

      const archived = {};
      classIds.forEach((classId) => {
        const years = (store.archived || {})[classId] || {};
        Object.keys(years).forEach((year) => {
          archived[year] = archived[year] || { 1: [], 2: [] };
          (years[year] || []).forEach((row) => {
            if (!row || !row.id) return;
            const typeKey = String(row.type || 1);
            if (!archived[year][typeKey].some((x) => x.id === row.id)) {
              archived[year][typeKey].push(row);
            }
          });
        });
      });
      bucket.archived = archived;

      (classIds || []).forEach((classId) => {
        const nu = (store.nextUse || {})[classId] || [];
        nu.forEach((row) => {
          if (!row || !row.id) return;
          const typeKey = String(row.type || 1);
          const list = bucket.lists[typeKey];
          if (list.some((e) => entryTopicId(e) === row.id)) return;
          list.push({
            topicId: row.id,
            addedAt: new Date().toISOString(),
            done: {},
            completedAt: null,
            meta: {
              text: row.text,
              suffix: row.suffix,
              type: row.type,
              ja: row.ja || "",
              source_order: row.source_order,
            },
          });
        });
      });
    });

    store.lastCourse = store.lastCourse || {};
    Object.keys(courseByTeacher).forEach((tid) => {
      store.lastCourse[tid] = courseByTeacher[tid];
    });

    const prefs = store.prefs || {};
    if (prefs.teacherId && courseByTeacher[prefs.teacherId]) {
      prefs.courseId = courseByTeacher[prefs.teacherId];
      if (!prefs.classId) prefs.classId = (store.lastClass || {})[prefs.teacherId] || "";
    }
    store.prefs = Object.assign({ teacherId: "", courseId: "", classId: "" }, prefs);

    store.schemaVersion = SCHEMA_VERSION;
    store.courseState = store.courseState || {};
    Object.assign(store.courseState, store.courseState);
    store._migrationDone = true;

    if (window.ToolboxClasses && window.ToolboxClasses.saveCourses) {
      window.ToolboxClasses.saveCourses(nextCourses);
    }
    return { store, courses: nextCourses, notes };
  }

  function purgeClassFromStore(store, classId, courses, classes) {
    if (!classId) return courses;
    let nextCourses = courses;
    if (window.ToolboxClasses) {
      nextCourses = window.ToolboxClasses.removeClassFromAllCourses(classId, courses);
    }
    const classRows = classes || (window.ToolboxClasses ? window.ToolboxClasses.load() : []);
    Object.entries(store.courseState || {}).forEach(([courseId, bucket]) => {
      const course = (nextCourses || []).find((c) => c.id === courseId);
      const targets = targetClassIds(course, classRows);
      ["1", "2"].forEach((typeKey) => {
        (bucket.lists[typeKey] || []).forEach((entry) => {
          if (entry.done && entry.done[classId]) delete entry.done[classId];
          recomputeCompletedAt(entry, targets);
        });
      });
      if (bucket.lastClassId === classId) bucket.lastClassId = "";
    });
    return nextCourses;
  }

  function mergeSave(mutator) {
    const raw = readJson(SPEECH_KEY);
    let store = raw && typeof raw === "object" ? raw : defaultStore();
    const teachers = window.ToolboxClasses ? window.ToolboxClasses.loadTeachers() : [];
    const classes = window.ToolboxClasses ? window.ToolboxClasses.load() : [];
    let courses = window.ToolboxClasses ? window.ToolboxClasses.loadCourses() : [];
    const migrated = runMigration(store, teachers, classes, courses);
    store = migrated.store;
    courses = migrated.courses;
    mutator(store, { teachers, classes, courses });
    writeJson(SPEECH_KEY, store);
    return store;
  }

  function ensureLoaded(store) {
    const teachers = window.ToolboxClasses ? window.ToolboxClasses.loadTeachers() : [];
    const classes = window.ToolboxClasses ? window.ToolboxClasses.load() : [];
    let courses = window.ToolboxClasses ? window.ToolboxClasses.loadCourses() : [];
    const result = runMigration(store, teachers, classes, courses);
    if (result.courses !== courses && window.ToolboxClasses.saveCourses) {
      window.ToolboxClasses.saveCourses(result.courses);
    }
    return result;
  }

  function listTopicIdsForCourse(store, courseId, typeNum) {
    const bucket = ensureCourseBucket(store, courseId);
    const key = String(typeNum);
    return (bucket.lists[key] || []).map(entryTopicId).filter(Boolean);
  }

  function findListEntry(store, courseId, topicId, typeNum) {
    const bucket = ensureCourseBucket(store, courseId);
    const key = typeNum != null ? String(typeNum) : null;
    const types = key ? [key] : ["1", "2"];
    for (let i = 0; i < types.length; i += 1) {
      const list = bucket.lists[types[i]] || [];
      const found = list.find((e) => entryTopicId(e) === topicId);
      if (found) return { entry: found, typeKey: types[i], bucket };
    }
    return null;
  }

  function markClassDone(store, courseId, classId, topic, typeNum) {
    if (!courseId || !classId || !topic || !topic.id) return;
    const bucket = ensureCourseBucket(store, courseId);
    const typeKey = String(typeNum || topic.type || 1);
    let entry = (bucket.lists[typeKey] || []).find((e) => entryTopicId(e) === topic.id);
    if (!entry) {
      entry = {
        topicId: topic.id,
        addedAt: new Date().toISOString(),
        done: {},
        completedAt: null,
        meta: {
          text: topic.text,
          suffix: topic.suffix,
          type: topic.type,
          ja: topic.ja || "",
          source_order: topic.source_order,
        },
      };
      bucket.lists[typeKey].push(entry);
    }
    entry.done = entry.done || {};
    entry.done[classId] = todayIsoDate();
    const course = window.ToolboxClasses.loadCourses().find((c) => c.id === courseId);
    const classes = window.ToolboxClasses.load();
    recomputeCompletedAt(entry, targetClassIds(course, classes));
  }

  function toggleClassDone(store, courseId, classId, topicId, typeNum) {
    const hit = findListEntry(store, courseId, topicId, typeNum);
    if (!hit) return false;
    hit.entry.done = hit.entry.done || {};
    if (hit.entry.done[classId]) delete hit.entry.done[classId];
    else hit.entry.done[classId] = todayIsoDate();
    const course = window.ToolboxClasses.loadCourses().find((c) => c.id === courseId);
    recomputeCompletedAt(hit.entry, targetClassIds(course, window.ToolboxClasses.load()));
    return true;
  }

  function firstPendingTopic(store, courseId, classId, typeNum) {
    const bucket = ensureCourseBucket(store, courseId);
    const list = bucket.lists[String(typeNum)] || [];
    const course = window.ToolboxClasses.loadCourses().find((c) => c.id === courseId);
    const targets = targetClassIds(course, window.ToolboxClasses.load());
    for (let i = 0; i < list.length; i += 1) {
      const entry = list[i];
      if (entry.completedAt) continue;
      if (!entry.done || !entry.done[classId]) {
        return entry;
      }
    }
    return null;
  }

  function appendTopicToList(store, courseId, topic) {
    const typeKey = String(topic.type || 1);
    const bucket = ensureCourseBucket(store, courseId);
    if ((bucket.lists[typeKey] || []).some((e) => entryTopicId(e) === topic.id)) return false;
    bucket.lists[typeKey].push({
      topicId: topic.id,
      addedAt: new Date().toISOString(),
      done: {},
      completedAt: null,
      meta: {
        text: topic.text,
        suffix: topic.suffix,
        type: topic.type,
        ja: topic.ja || "",
        source_order: topic.source_order,
      },
    });
    return true;
  }

  function allListTopicIds(store, courseId) {
    const bucket = ensureCourseBucket(store, courseId);
    const ids = [];
    ["1", "2"].forEach((key) => {
      (bucket.lists[key] || []).forEach((e) => {
        const id = entryTopicId(e);
        if (id) ids.push(id);
      });
    });
    return ids;
  }

  function entryAsTopic(entry) {
    const meta = entry.meta || {};
    return {
      id: entryTopicId(entry),
      text: meta.text || "",
      suffix: meta.suffix,
      type: meta.type,
      ja: meta.ja || "",
      source_order: meta.source_order,
    };
  }

  function finalizeMigration(store) {
    delete store.scopes;
    delete store.history;
    delete store.rounds;
    delete store.nextUse;
    delete store.archived;
    delete store.lastClass;
    store.migrationPending = false;
    store.migrationFinalizedAt = new Date().toISOString();
  }

  window.MinuteSpeechCourses = {
    SPEECH_KEY,
    SCHEMA_VERSION,
    defaultStore,
    ensureLoaded,
    mergeSave,
    ensureCourseBucket,
    targetClassIds,
    entryDoneCount,
    recomputeCompletedAt,
    listTopicIdsForCourse,
    findListEntry,
    markClassDone,
    toggleClassDone,
    firstPendingTopic,
    appendTopicToList,
    allListTopicIds,
    entryAsTopic,
    entryTopicId,
    purgeClassFromStore,
    finalizeMigration,
    todayIsoDate,
    sortEntriesByFirstUse,
    backupKeys,
  };
})();
