(function () {
  const KEY = "toolbox.local_classes.v1";
  const TEACHERS_KEY = "toolbox.local_teachers.v1";
  const COURSES_KEY = "toolbox.local_courses.v1";
  const SEATS_KEY = "toolbox.random_seats.rooms.v1";

  function read(key) {
    try {
      return JSON.parse(localStorage.getItem(key) || "null");
    } catch (_) {
      return null;
    }
  }

  function suggestGrid(count) {
    const cols = count <= 20 ? 5 : count <= 36 ? 6 : 7;
    return { rows: Math.max(1, Math.ceil((Number(count) || 1) / cols)), cols };
  }

  function nums(value) {
    return Array.isArray(value) ? value.map((n) => Number(n)).filter((n) => Number.isFinite(n)) : [];
  }

  function normalize(row) {
    const count = Math.max(1, Math.min(60, Number(row.student_count) || 1));
    const layout = suggestGrid(count);
    const pick = row.pick && typeof row.pick === "object" ? row.pick : {};
    return {
      id: String(row.id || ""),
      name: String(row.name || "クラス").slice(0, 40),
      student_count: count,
      absent: nums(row.absent),
      seats: Array.isArray(row.seats) ? row.seats : [],
      rows: Math.max(1, Math.min(12, Number(row.rows) || layout.rows)),
      cols: Math.max(1, Math.min(12, Number(row.cols) || layout.cols)),
      blocked: nums(row.blocked),
      pick: {
        absent: nums(pick.absent),
        picked: nums(pick.picked),
        history: nums(pick.history),
      },
      teacher_id: String(row.teacher_id || ""),
      hidden_year: /^\d{4}$/.test(String(row.hidden_year || "")) ? String(row.hidden_year) : "",
    };
  }

  function load(serverSeed) {
    const stored = read(KEY);
    if (Array.isArray(stored)) return stored.map(normalize);
    const rooms = read(SEATS_KEY);
    let rows = [];
    if (Array.isArray(rooms) && rooms.length) {
      rows = rooms.map(normalize);
    } else if (Array.isArray(serverSeed) && serverSeed.length) {
      rows = serverSeed.map((row) => {
        const seatLegacy = read(`toolbox.random_seats.${row.id}`) || {};
        const pickLegacy = read(`toolbox.random_pick.${row.id}`) || {};
        return normalize(Object.assign({}, row, seatLegacy, { pick: pickLegacy }));
      });
    }
    if (rows.length) localStorage.setItem(KEY, JSON.stringify(rows));
    return rows;
  }

  function save(rows) {
    const next = (rows || []).map(normalize);
    localStorage.setItem(KEY, JSON.stringify(next));
    return next;
  }

  function loadTeachers() {
    const stored = read(TEACHERS_KEY);
    if (!Array.isArray(stored)) return [];
    return stored
      .map((row) => ({
        id: String((row && row.id) || ""),
        name: String((row && row.name) || "教員").slice(0, 40),
      }))
      .filter((row) => row.id);
  }

  function saveTeachers(rows) {
    const next = (rows || [])
      .map((row) => ({
        id: String((row && row.id) || ""),
        name: String((row && row.name) || "教員").slice(0, 40),
      }))
      .filter((row) => row.id);
    localStorage.setItem(TEACHERS_KEY, JSON.stringify(next));
    return next;
  }

  function normalizeCourse(row) {
    const classIds = Array.isArray(row.class_ids)
      ? row.class_ids.map((id) => String(id)).filter(Boolean)
      : [];
    return {
      id: String(row.id || ""),
      name: String(row.name || "授業").slice(0, 40),
      teacher_id: String(row.teacher_id || ""),
      class_ids: classIds,
      year: /^\d{4}$/.test(String(row.year || "")) ? String(row.year) : "",
      hidden_year: /^\d{4}$/.test(String(row.hidden_year || "")) ? String(row.hidden_year) : "",
      order: Number.isFinite(Number(row.order)) ? Number(row.order) : 0,
    };
  }

  function loadCourses() {
    const stored = read(COURSES_KEY);
    if (!Array.isArray(stored)) return [];
    return stored.map(normalizeCourse).filter((row) => row.id);
  }

  function saveCourses(rows) {
    const next = (rows || []).map(normalizeCourse).filter((row) => row.id);
    next.sort((a, b) => a.order - b.order || a.name.localeCompare(b.name));
    localStorage.setItem(COURSES_KEY, JSON.stringify(next));
    return next;
  }

  function coursesForTeacher(teacherId, courses) {
    const list = courses || loadCourses();
    const tid = String(teacherId || "");
    return list
      .filter((c) => !c.hidden_year && (!tid || c.teacher_id === tid))
      .sort((a, b) => a.order - b.order || a.name.localeCompare(b.name));
  }

  function removeClassFromAllCourses(classId, courses) {
    const id = String(classId || "");
    if (!id) return courses || loadCourses();
    return saveCourses((courses || loadCourses()).map((c) => {
      if (!c.class_ids.includes(id)) return c;
      return Object.assign({}, c, { class_ids: c.class_ids.filter((x) => x !== id) });
    }));
  }

  function addClassToCourse(courseId, classId, courses) {
    const cid = String(courseId || "");
    const cl = String(classId || "");
    return saveCourses((courses || loadCourses()).map((c) => {
      if (c.id !== cid) return c;
      if (c.class_ids.includes(cl)) return c;
      return Object.assign({}, c, { class_ids: c.class_ids.concat(cl) });
    }));
  }

  window.ToolboxClasses = {
    load,
    save,
    normalize,
    suggestGrid,
    loadTeachers,
    saveTeachers,
    COURSES_KEY,
    loadCourses,
    saveCourses,
    normalizeCourse,
    coursesForTeacher,
    removeClassFromAllCourses,
    addClassToCourse,
  };
})();
