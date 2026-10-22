(function () {
  const ROOMS_KEY = "toolbox.random_seats.rooms.v1";
  const LAST_KEY = "toolbox.random_seats.last.v1";
  const QUICK_KEY = "toolbox.random_seats.quick.v1";
  const QUICK_ID = "__quick__";
  let classes = [];
  let activeId = "";
  let holdSeat = null;
  let quickGridManual = false;
  let syncingQuick = false;
  const tabs = document.getElementById("tb-room-tabs");
  const quickTab = document.getElementById("tb-quick-tab");
  const quickPanel = document.querySelector(".tb-stage-setup #tb-quick");
  const grid = document.getElementById("tb-grid");
  const board = document.getElementById("tb-seats");
  const rowsEl = document.getElementById("tb-rows");
  const colsEl = document.getElementById("tb-cols");
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function storageKey(id) {
    return `toolbox.random_seats.${id}`;
  }

  function loadLegacy(id) {
    try {
      return JSON.parse(localStorage.getItem(storageKey(id)) || "{}");
    } catch (_) {
      return {};
    }
  }

  function readRooms() {
    try {
      const rows = JSON.parse(localStorage.getItem(ROOMS_KEY) || "[]");
      return Array.isArray(rows) ? rows : [];
    } catch (_) {
      return [];
    }
  }

  function clampInt(value, min, max, fallback) {
    const n = Number(value);
    if (!Number.isFinite(n)) return fallback;
    return Math.max(min, Math.min(max, Math.round(n)));
  }

  function defaultQuick() {
    const layout = suggestGrid(30);
    return {
      id: QUICK_ID,
      name: "クイック（保存なし）",
      count: 30,
      student_count: 30,
      absent: [],
      seats: [],
      rows: layout.rows,
      cols: layout.cols,
      blocked: [],
      mode: "random",
    };
  }

  function loadQuick() {
    let raw = {};
    try {
      raw = JSON.parse(localStorage.getItem(QUICK_KEY) || "{}") || {};
    } catch (_) {
      raw = {};
    }
    const count = clampInt(raw.count, 1, 60, 30);
    const layout = suggestGrid(count);
    const rows = clampInt(raw.rows, 1, 12, layout.rows);
    const cols = clampInt(raw.cols, 1, 12, layout.cols);
    if (rows !== layout.rows || cols !== layout.cols) quickGridManual = true;
    return {
      id: QUICK_ID,
      name: "クイック（保存なし）",
      count: count,
      student_count: count,
      absent: Array.isArray(raw.absent) ? raw.absent.map(Number).filter((n) => Number.isFinite(n)) : [],
      seats: Array.isArray(raw.seats) ? raw.seats.slice() : [],
      rows: rows,
      cols: cols,
      blocked: Array.isArray(raw.blocked) ? raw.blocked.map(Number).filter((n) => Number.isFinite(n)) : [],
      mode: raw.mode === "test" ? "test" : "random",
    };
  }

  let quickState = loadQuick();

  let saveToastTimer = 0;

  function showSaveToast() {
    let el = document.getElementById("tb-save-toast");
    if (!el) {
      el = document.createElement("div");
      el.id = "tb-save-toast";
      el.className = "tb-save-toast";
      el.setAttribute("role", "status");
      el.setAttribute("aria-live", "polite");
      el.textContent = "保存しました";
      document.body.appendChild(el);
    }
    el.classList.add("is-show");
    window.clearTimeout(saveToastTimer);
    saveToastTimer = window.setTimeout(() => el.classList.remove("is-show"), 1600);
  }

  function persistQuick() {
    const saved = {
      count: quickState.count,
      rows: quickState.rows,
      cols: quickState.cols,
      blocked: (quickState.blocked || []).slice(),
      absent: (quickState.absent || []).slice(),
      seats: (quickState.seats || []).slice(),
      mode: quickState.mode === "test" ? "test" : "random",
    };
    localStorage.setItem(QUICK_KEY, JSON.stringify(saved));
  }

  function writeRooms(confirmSave) {
    if (activeId === QUICK_ID) {
      persistQuick();
      localStorage.setItem(LAST_KEY, activeId);
      if (confirmSave) showSaveToast();
      return;
    }
    classes = window.ToolboxClasses.save(classes);
    if (activeId) localStorage.setItem(LAST_KEY, activeId);
    if (confirmSave) showSaveToast();
  }

  function cloneRoom(row, id, name) {
    return {
      id: id,
      name: name,
      student_count: row.student_count,
      absent: (row.absent || []).slice(),
      seats: (row.seats || []).slice(),
      rows: row.rows,
      cols: row.cols,
      blocked: (row.blocked || []).slice(),
      mode: row.mode === "test" ? "test" : "random",
      pick: {
        absent: ((row.pick || {}).absent || []).slice(),
        picked: ((row.pick || {}).picked || []).slice(),
        history: ((row.pick || {}).history || []).slice(),
      },
    };
  }

  function newId() {
    return (crypto.randomUUID && crypto.randomUUID()) || String(Date.now());
  }

  function suggestGrid(count) {
    const cols = count <= 20 ? 5 : count <= 36 ? 6 : 7;
    return { rows: Math.max(1, Math.ceil(count / cols)), cols };
  }

  function bootRooms() {
    classes = window.ToolboxClasses.load(window.TOOLBOX_CLASSES);
  }

  function isQuick(row) {
    return !!(row && row.id === QUICK_ID);
  }

  function currentClass() {
    if (activeId === QUICK_ID) return quickState;
    return classes.find((row) => row.id === activeId) || null;
  }

  function numbersOf(row) {
    if (!row) return [];
    const count = Math.max(0, Math.min(60, Number(row.student_count) || row.count || 0));
    const nums = [];
    for (let n = 1; n <= count; n += 1) nums.push(n);
    return nums;
  }

  function effectiveNumbers(row) {
    return numbersOf(row);
  }

  function seatLabel(n) {
    return String(n);
  }

  function defaultState(row) {
    const suggested = suggestGrid(row ? (effectiveNumbers(row).length || row.student_count) : 30);
    return { absent: [], seats: [], rows: suggested.rows, cols: suggested.cols, blocked: [], mode: "random" };
  }

  function stateOf() {
    const row = currentClass();
    if (!row) return defaultState(null);
    const state = Object.assign(defaultState(row), row);
    const allowed = new Set(effectiveNumbers(row));
    state.absent = (state.absent || []).filter((n) => allowed.has(n));
    state.rows = Math.max(1, Math.min(12, Number(state.rows) || defaultState(row).rows));
    state.cols = Math.max(1, Math.min(12, Number(state.cols) || defaultState(row).cols));
    const maxSeats = state.rows * state.cols;
    if (!Array.isArray(state.seats)) state.seats = [];
    if (state.seats.length > maxSeats) state.seats = state.seats.slice(0, maxSeats);
    if (isQuick(row)) {
      state.seats = state.seats.map((seat) => (seat && allowed.has(seat) ? seat : null));
    }
    state.blocked = (state.blocked || []).filter((n) => n >= 0 && n < maxSeats);
    state.mode = state.mode === "test" ? "test" : "random";
    return state;
  }

  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function syncQuickForm() {
    if (!quickPanel) return;
    syncingQuick = true;
    const countEl = document.getElementById("tb-quick-count");
    if (countEl) countEl.value = String(quickState.count);
    syncingQuick = false;
  }

  function syncQuickChrome() {
    const quick = activeId === QUICK_ID;
    if (quickPanel) quickPanel.hidden = !quick;
    ["tb-class-edit", "tb-class-dup", "tb-class-del", "tb-room-save"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.hidden = quick;
    });
    const saveAs = document.getElementById("tb-quick-save");
    if (saveAs) saveAs.hidden = !quick;
    if (quickTab) {
      quickTab.classList.toggle("is-active", quick);
      quickTab.setAttribute("aria-selected", quick ? "true" : "false");
    }
    if (quick) syncQuickForm();
  }

  function renderClasses() {
    if (activeId !== QUICK_ID && !classes.some((row) => row.id === activeId)) {
      activeId = classes[0] ? classes[0].id : QUICK_ID;
    }
    tabs.innerHTML = classes.map((row) => (
      `<button class="tb-tab${row.id === activeId ? " is-active" : ""}" type="button" role="tab" aria-selected="${row.id === activeId}" data-room="${esc(row.id)}">${esc(row.name)}（${row.student_count}）</button>`
    )).join("");
    syncQuickChrome();
    renderAll();
  }

  function renderGrid() {
    const row = currentClass();
    if (!row) {
      grid.innerHTML = "";
      return;
    }
    const state = stateOf();
    const nums = effectiveNumbers(row);
    grid.innerHTML = "";
    nums.forEach((n) => {
      const btn = document.createElement("button");
      btn.type = "button";
      const label = seatLabel(n);
      btn.textContent = label;
      if (label !== String(n)) btn.classList.add("is-named");
      if (state.absent.includes(n)) btn.classList.add("is-absent");
      btn.addEventListener("click", () => {
        const next = stateOf();
        if (next.absent.includes(n)) next.absent = next.absent.filter((x) => x !== n);
        else next.absent.push(n);
        next.seats = next.seats.map((seat) => (seat === n ? null : seat));
        Object.assign(row, next);
        writeRooms();
        renderAll();
      });
      grid.appendChild(btn);
    });
  }

  function renderBoard(previewState) {
    const row = currentClass();
    const state = previewState || stateOf();
    rowsEl.value = String(state.rows);
    colsEl.value = String(state.cols);
    const modeEl = document.getElementById("tb-seat-mode");
    if (modeEl) modeEl.value = state.mode === "test" ? "test" : "random";
    board.style.gridTemplateColumns = `repeat(${state.cols}, minmax(0, 1fr))`;
    board.style.gridTemplateRows = `repeat(${state.rows}, minmax(0, 1fr))`;
    board.innerHTML = "";
    const total = state.rows * state.cols;
    for (let i = 0; i < total; i += 1) {
      const cell = document.createElement("div");
      cell.className = "tb-seat-cell";
      cell.setAttribute("role", "gridcell");
      const blocked = (state.blocked || []).includes(i);
      const num = state.seats[i];
      if (blocked) {
        cell.classList.add("is-blocked");
        cell.textContent = "";
        cell.title = "使えない席。タップすると使えます";
      } else if (num) {
        const label = seatLabel(num);
        cell.textContent = label;
        if (label !== String(num)) cell.classList.add("is-named");
        cell.title = "タップしてから別の席をタップすると移動できます";
        if (holdSeat === i) cell.classList.add("is-picked");
      } else {
        cell.classList.add("is-empty");
        cell.textContent = "";
        cell.title = "番号を置ける席。空のままタップすると使えない席になります";
      }
      cell.addEventListener("click", () => {
        if (window.ToolboxDisplay && window.ToolboxDisplay.isOn()) return;
        if (!row) return;
        const next = stateOf();
        const set = new Set(next.blocked || []);
        if (!Array.isArray(next.seats)) next.seats = [];
        if (set.has(i)) {
          set.delete(i);
          holdSeat = null;
        } else if (holdSeat == null) {
          if (next.seats[i]) holdSeat = i;
          else {
            set.add(i);
          }
        } else if (holdSeat === i) {
          holdSeat = null;
        } else {
          const from = next.seats[holdSeat];
          next.seats[holdSeat] = next.seats[i] || null;
          next.seats[i] = from || null;
          set.delete(i);
          holdSeat = null;
        }
        next.blocked = Array.from(set);
        Object.assign(row, next);
        writeRooms();
        renderBoard();
      });
      board.appendChild(cell);
    }
    if (!row) {
      board.innerHTML = `<p class="tb-seat-empty">教室を作ってください</p>`;
    }
  }

  function renderAll() {
    renderGrid();
    renderBoard();
  }

  function shuffle() {
    const row = currentClass();
    if (!row) return;
    const state = stateOf();
    state.rows = Math.max(1, Math.min(12, Number(rowsEl.value) || state.rows));
    state.cols = Math.max(1, Math.min(12, Number(colsEl.value) || state.cols));
    const blocked = new Set(state.blocked || []);
    const capacity = state.rows * state.cols - blocked.size;
    const pool = effectiveNumbers(row).filter((n) => !state.absent.includes(n));
    if (pool.length > capacity) {
      alert(`席が足りません。${pool.length}人に対して席は${capacity}です。`);
      return;
    }
    const total = state.rows * state.cols;

    function shuffleInPlace(list) {
      for (let i = list.length - 1; i > 0; i -= 1) {
        const j = Math.floor(Math.random() * (i + 1));
        const tmp = list[i];
        list[i] = list[j];
        list[j] = tmp;
      }
      return list;
    }

    function arrange(list) {
      const seats = [];
      let placed = 0;
      for (let i = 0; i < total; i += 1) {
        if (blocked.has(i)) seats.push(null);
        else seats.push(list[placed++] || null);
      }
      return seats;
    }

    function orthoNeighbors(index) {
      const rowIndex = Math.floor(index / state.cols);
      const colIndex = index % state.cols;
      const near = [];
      if (rowIndex > 0) near.push(index - state.cols);
      if (rowIndex + 1 < state.rows) near.push(index + state.cols);
      if (colIndex > 0) near.push(index - 1);
      if (colIndex + 1 < state.cols) near.push(index + 1);
      return near;
    }

    function arrangeTest(list) {
      const open = [];
      for (let i = 0; i < total; i += 1) {
        if (!blocked.has(i)) open.push(i);
      }
      const groups = [[], []];
      open.forEach((index) => {
        const rowIndex = Math.floor(index / state.cols);
        const colIndex = index % state.cols;
        groups[(rowIndex + colIndex) % 2].push(index);
      });
      const primary = groups[0].length >= groups[1].length ? groups[0] : groups[1];
      const secondary = primary === groups[0] ? groups[1] : groups[0];
      shuffleInPlace(primary);
      const chosen = [];
      if (list.length <= primary.length) {
        chosen.push(...primary.slice(0, list.length));
      } else {
        chosen.push(...primary);
        const filled = new Set(primary);
        const remain = secondary.slice();
        let rest = list.length - primary.length;
        while (rest > 0 && remain.length) {
          let best = 0;
          let bestScore = Infinity;
          const ties = [];
          remain.forEach((index, at) => {
            const score = orthoNeighbors(index).filter((near) => filled.has(near)).length;
            if (score < bestScore) {
              bestScore = score;
              ties.length = 0;
              ties.push(at);
            } else if (score === bestScore) ties.push(at);
          });
          best = ties[Math.floor(Math.random() * ties.length)];
          const pick = remain.splice(best, 1)[0];
          filled.add(pick);
          chosen.push(pick);
          rest -= 1;
        }
      }
      const seats = new Array(total).fill(null);
      chosen.forEach((index, at) => {
        seats[index] = list[at];
      });
      return seats;
    }

    function shuffledPool() {
      const copy = pool.slice();
      for (let i = copy.length - 1; i > 0; i -= 1) {
        const j = Math.floor(Math.random() * (i + 1));
        const tmp = copy[i];
        copy[i] = copy[j];
        copy[j] = tmp;
      }
      return copy;
    }

    const modeEl = document.getElementById("tb-seat-mode");
    state.mode = modeEl && modeEl.value === "test" ? "test" : "random";
    const place = state.mode === "test" ? arrangeTest : arrange;

    const apply = () => {
      state.seats = place(shuffledPool());
      Object.assign(row, state);
      writeRooms();
      renderAll();
    };

    if (reduceMotion) {
      apply();
      return;
    }

    const start = Date.now();
    const spin = () => {
      const preview = Object.assign({}, state, { seats: place(shuffledPool()) });
      renderBoard(preview);
      if (Date.now() - start < 1100) requestAnimationFrame(spin);
      else apply();
    };
    spin();
  }

  document.getElementById("tb-shuffle").addEventListener("click", shuffle);
  document.getElementById("tb-clear").addEventListener("click", () => {
    const row = currentClass();
    if (!row) return;
    const prev = stateOf();
    const next = defaultState(row);
    next.rows = Math.max(1, Math.min(12, Number(rowsEl.value) || next.rows));
    next.cols = Math.max(1, Math.min(12, Number(colsEl.value) || next.cols));
    next.blocked = prev.blocked || [];
    next.mode = prev.mode === "test" ? "test" : "random";
    Object.assign(row, next);
    writeRooms();
    renderAll();
  });
  rowsEl.addEventListener("change", () => {
    const row = currentClass();
    if (!row) return;
    if (isQuick(row)) quickGridManual = true;
    const state = stateOf();
    state.rows = Math.max(1, Math.min(12, Number(rowsEl.value) || state.rows));
    Object.assign(row, state);
    writeRooms();
    renderBoard();
  });
  document.getElementById("tb-seat-mode").addEventListener("change", () => {
    const row = currentClass();
    if (!row) return;
    const state = stateOf();
    const modeEl = document.getElementById("tb-seat-mode");
    state.mode = modeEl && modeEl.value === "test" ? "test" : "random";
    Object.assign(row, state);
    writeRooms();
  });
  colsEl.addEventListener("change", () => {
    const row = currentClass();
    if (!row) return;
    if (isQuick(row)) quickGridManual = true;
    const state = stateOf();
    state.cols = Math.max(1, Math.min(12, Number(colsEl.value) || state.cols));
    Object.assign(row, state);
    writeRooms();
    renderBoard();
  });
  tabs.addEventListener("click", (ev) => {
    const button = ev.target.closest ? ev.target.closest("[data-room]") : null;
    const id = button ? button.dataset.room : "";
    if (!id) return;
    activeId = id;
    holdSeat = null;
    localStorage.setItem(LAST_KEY, activeId);
    renderClasses();
  });
  if (quickTab) {
    quickTab.addEventListener("click", () => {
      activeId = QUICK_ID;
      holdSeat = null;
      localStorage.setItem(LAST_KEY, activeId);
      renderClasses();
    });
  }

  function refreshQuickSize(applyGrid) {
    const count = clampInt(document.getElementById("tb-quick-count").value, 1, 60, quickState.count);
    quickState.count = count;
    quickState.student_count = count;
    if (applyGrid && !quickGridManual) {
      const layout = suggestGrid(count);
      quickState.rows = layout.rows;
      quickState.cols = layout.cols;
    }
    const allowed = new Set(effectiveNumbers(quickState));
    quickState.absent = (quickState.absent || []).filter((n) => allowed.has(n));
    quickState.seats = (quickState.seats || []).map((seat) => (seat && allowed.has(seat) ? seat : null));
    writeRooms();
    syncQuickChrome();
    renderAll();
  }

  document.getElementById("tb-quick-count").addEventListener("change", () => {
    if (syncingQuick) return;
    refreshQuickSize(true);
  });

  document.getElementById("tb-room-save").addEventListener("click", () => {
    writeRooms(true);
  });

  document.getElementById("tb-quick-save").addEventListener("click", () => {
    const name = prompt("教室の名前", "");
    if (!name || !name.trim()) return;
    const span = quickState.count;
    const room = {
      id: newId(),
      name: name.trim(),
      student_count: span,
      absent: (quickState.absent || []).filter((n) => n >= 1 && n <= span),
      seats: (quickState.seats || []).slice(),
      rows: quickState.rows,
      cols: quickState.cols,
      blocked: (quickState.blocked || []).slice(),
      mode: quickState.mode === "test" ? "test" : "random",
    };
    classes.push(room);
    activeId = room.id;
    holdSeat = null;
    writeRooms();
    renderClasses();
  });

  function promptClass(existing) {
    const name = prompt("教室の名前", existing ? existing.name : "");
    if (!name || !name.trim()) return;
    const count = Number(prompt("人数（1〜60）", existing ? existing.student_count : "30"));
    if (!Number.isFinite(count) || count < 1 || count > 60) {
      alert("人数は1〜60で入力してください。");
      return;
    }
    if (existing) {
      existing.name = name.trim();
      existing.student_count = count;
      existing.absent = (existing.absent || []).filter((n) => n >= 1 && n <= count);
    } else {
      const layout = suggestGrid(count);
      const room = {
        id: newId(),
        name: name.trim(),
        student_count: count,
        absent: [],
        seats: [],
        rows: layout.rows,
        cols: layout.cols,
      };
      classes.push(room);
      activeId = room.id;
    }
    writeRooms();
    renderClasses();
  }

  document.getElementById("tb-class-new").addEventListener("click", () => promptClass(null));
  document.getElementById("tb-class-edit").addEventListener("click", () => {
    const row = currentClass();
    if (row && !isQuick(row)) promptClass(row);
  });
  document.getElementById("tb-class-dup").addEventListener("click", () => {
    const row = currentClass();
    if (!row || isQuick(row)) return;
    const copy = cloneRoom(row, newId(), `${row.name} のコピー`);
    classes.push(copy);
    activeId = copy.id;
    writeRooms();
    renderClasses();
  });
  document.getElementById("tb-class-del").addEventListener("click", () => {
    const row = currentClass();
    if (!row || isQuick(row) || !confirm(`${row.name} をこの端末から削除しますか？`)) return;
    classes = classes.filter((item) => item.id !== row.id);
    if (classes.length) {
      activeId = classes[0].id;
      writeRooms();
    } else {
      classes = window.ToolboxClasses.save(classes);
      activeId = QUICK_ID;
      localStorage.setItem(LAST_KEY, activeId);
    }
    renderClasses();
  });

  ToolboxDisplay.init({
    onNext: shuffle,
    onPrev: () => document.getElementById("tb-clear").click(),
  });
  bootRooms();
  const last = localStorage.getItem(LAST_KEY) || "";
  if (!classes.length || !last) activeId = QUICK_ID;
  else activeId = last;
  renderClasses();
})();
