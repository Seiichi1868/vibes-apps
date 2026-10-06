(function () {
  const ROOMS_KEY = "toolbox.random_seats.rooms.v1";
  const LAST_KEY = "toolbox.random_seats.last.v1";
  let classes = [];
  let activeId = "";
  let holdSeat = null;
  const tabs = document.getElementById("tb-room-tabs");
  const grid = document.getElementById("tb-grid");
  const board = document.getElementById("tb-seats");
  const rowsEl = document.getElementById("tb-rows");
  const colsEl = document.getElementById("tb-cols");

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

  function writeRooms(confirmSave) {
    classes = window.ToolboxClasses.save(classes);
    if (activeId) localStorage.setItem(LAST_KEY, activeId);
    if (!confirmSave) return;
    const btn = document.getElementById("tb-room-save");
    if (!btn) return;
    btn.textContent = "保存しました";
    window.setTimeout(() => {
      if (btn.textContent === "保存しました") btn.textContent = "保存";
    }, 1200);
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

  function currentClass() {
    return classes.find((row) => row.id === activeId) || null;
  }

  function defaultState(row) {
    const suggested = suggestGrid(row ? row.student_count : 30);
    return { absent: [], seats: [], rows: suggested.rows, cols: suggested.cols, blocked: [] };
  }

  function stateOf() {
    const row = currentClass();
    if (!row) return defaultState(null);
    const state = Object.assign(defaultState(row), row);
    state.absent = state.absent.filter((n) => n >= 1 && n <= row.student_count);
    state.rows = Math.max(1, Math.min(12, Number(state.rows) || defaultState(row).rows));
    state.cols = Math.max(1, Math.min(12, Number(state.cols) || defaultState(row).cols));
    const maxSeats = state.rows * state.cols;
    if (!Array.isArray(state.seats)) state.seats = [];
    if (state.seats.length > maxSeats) state.seats = state.seats.slice(0, maxSeats);
    state.blocked = (state.blocked || []).filter((n) => n >= 0 && n < maxSeats);
    return state;
  }

  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function renderClasses() {
    if (!classes.some((row) => row.id === activeId)) activeId = classes[0] ? classes[0].id : "";
    tabs.innerHTML = classes.map((row) => (
      `<button class="tb-tab${row.id === activeId ? " is-active" : ""}" type="button" role="tab" aria-selected="${row.id === activeId}" data-room="${esc(row.id)}">${esc(row.name)}（${row.student_count}）</button>`
    )).join("") || '<span class="tb-muted">保存はまだありません。「教室を追加」でタブを作れます。</span>';
    renderAll();
  }

  function renderGrid() {
    const row = currentClass();
    if (!row) {
      grid.innerHTML = "";
      return;
    }
    const state = stateOf();
    grid.innerHTML = "";
    for (let n = 1; n <= row.student_count; n += 1) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = String(n);
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
    }
  }

  function renderBoard() {
    const row = currentClass();
    const state = stateOf();
    rowsEl.value = String(state.rows);
    colsEl.value = String(state.cols);
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
        cell.textContent = String(num);
        cell.title = "タップしてから別の席をタップすると移動できます";
        if (holdSeat === i) cell.classList.add("is-picked");
      } else {
        cell.classList.add("is-empty");
        cell.textContent = "";
        cell.title = "番号を置ける席。空のままタップすると使えない席になります";
      }
      cell.addEventListener("click", () => {
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
    const pool = [];
    for (let n = 1; n <= row.student_count; n += 1) {
      if (!state.absent.includes(n)) pool.push(n);
    }
    if (pool.length > capacity) {
      alert(`席が足りません。${pool.length}人に対して席は${capacity}です。`);
      return;
    }
    for (let i = pool.length - 1; i > 0; i -= 1) {
      const j = Math.floor(Math.random() * (i + 1));
      const tmp = pool[i];
      pool[i] = pool[j];
      pool[j] = tmp;
    }
    const total = state.rows * state.cols;
    state.seats = [];
    let placed = 0;
    for (let i = 0; i < total; i += 1) {
      if (blocked.has(i)) state.seats.push(null);
      else state.seats.push(pool[placed++] || null);
    }
    Object.assign(row, state);
    writeRooms();
    renderAll();
  }

  document.getElementById("tb-shuffle").addEventListener("click", shuffle);
  document.getElementById("tb-clear").addEventListener("click", () => {
    const row = currentClass();
    if (!row) return;
    const next = defaultState(row);
    next.rows = Math.max(1, Math.min(12, Number(rowsEl.value) || next.rows));
    next.cols = Math.max(1, Math.min(12, Number(colsEl.value) || next.cols));
    next.blocked = stateOf().blocked || [];
    Object.assign(row, next);
    writeRooms();
    renderAll();
  });
  rowsEl.addEventListener("change", () => {
    const row = currentClass();
    if (!row) return;
    const state = stateOf();
    state.rows = Math.max(1, Math.min(12, Number(rowsEl.value) || state.rows));
    Object.assign(row, state);
    writeRooms();
    renderBoard();
  });
  colsEl.addEventListener("change", () => {
    const row = currentClass();
    if (!row) return;
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

  document.getElementById("tb-room-save").addEventListener("click", () => {
    writeRooms();
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
    if (row) promptClass(row);
  });
  document.getElementById("tb-class-dup").addEventListener("click", () => {
    const row = currentClass();
    if (!row) return;
    const copy = cloneRoom(row, newId(), `${row.name} のコピー`);
    classes.push(copy);
    activeId = copy.id;
    writeRooms();
    renderClasses();
  });
  document.getElementById("tb-class-del").addEventListener("click", () => {
    const row = currentClass();
    if (!row || !confirm(`${row.name} をこの端末から削除しますか？`)) return;
    classes = classes.filter((item) => item.id !== row.id);
    activeId = classes[0] ? classes[0].id : "";
    writeRooms();
    renderClasses();
  });

  ToolboxDisplay.init({
    onNext: shuffle,
    onPrev: () => document.getElementById("tb-clear").click(),
  });
  bootRooms();
  activeId = localStorage.getItem(LAST_KEY) || "";
  renderClasses();
})();
