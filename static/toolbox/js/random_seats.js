(function () {
  let classes = Array.isArray(window.TOOLBOX_CLASSES) ? window.TOOLBOX_CLASSES.slice() : [];
  const select = document.getElementById("tb-class");
  const grid = document.getElementById("tb-grid");
  const board = document.getElementById("tb-seats");
  const rowsEl = document.getElementById("tb-rows");
  const colsEl = document.getElementById("tb-cols");

  function storageKey(id) {
    return `toolbox.random_seats.${id}`;
  }

  function loadState(id) {
    try {
      return JSON.parse(localStorage.getItem(storageKey(id)) || "{}");
    } catch (_) {
      return {};
    }
  }

  function saveState(id, state) {
    localStorage.setItem(storageKey(id), JSON.stringify(state));
  }

  function currentClass() {
    return classes.find((row) => row.id === select.value) || null;
  }

  function suggestGrid(count) {
    const cols = count <= 20 ? 5 : count <= 36 ? 6 : 7;
    return { rows: Math.max(1, Math.ceil(count / cols)), cols };
  }

  function defaultState(row) {
    const suggested = suggestGrid(row ? row.student_count : 30);
    return { absent: [], seats: [], rows: suggested.rows, cols: suggested.cols };
  }

  function stateOf() {
    const row = currentClass();
    if (!row) return defaultState(null);
    const state = Object.assign(defaultState(row), loadState(row.id));
    state.absent = state.absent.filter((n) => n >= 1 && n <= row.student_count);
    state.rows = Math.max(1, Math.min(12, Number(state.rows) || defaultState(row).rows));
    state.cols = Math.max(1, Math.min(12, Number(state.cols) || defaultState(row).cols));
    const maxSeats = state.rows * state.cols;
    if (!Array.isArray(state.seats)) state.seats = [];
    if (state.seats.length > maxSeats) state.seats = state.seats.slice(0, maxSeats);
    return state;
  }

  function renderClasses() {
    const keep = select.value;
    select.innerHTML = classes.map((row) => `<option value="${row.id}">${row.name}（${row.student_count}）</option>`).join("");
    if (keep && classes.some((row) => row.id === keep)) select.value = keep;
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
        saveState(row.id, next);
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
      const num = state.seats[i];
      if (num) {
        cell.textContent = String(num);
      } else {
        cell.classList.add("is-empty");
        cell.textContent = "";
      }
      board.appendChild(cell);
    }
    if (!row) {
      board.innerHTML = `<p class="tb-seat-empty">クラスを作ってください</p>`;
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
    const capacity = state.rows * state.cols;
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
    state.seats = Array.from({ length: capacity }, (_, i) => pool[i] || null);
    saveState(row.id, state);
    renderAll();
  }

  document.getElementById("tb-shuffle").addEventListener("click", shuffle);
  document.getElementById("tb-clear").addEventListener("click", () => {
    const row = currentClass();
    if (!row) return;
    const next = defaultState(row);
    next.rows = Math.max(1, Math.min(12, Number(rowsEl.value) || next.rows));
    next.cols = Math.max(1, Math.min(12, Number(colsEl.value) || next.cols));
    saveState(row.id, next);
    renderAll();
  });
  rowsEl.addEventListener("change", () => {
    const row = currentClass();
    if (!row) return;
    const state = stateOf();
    state.rows = Math.max(1, Math.min(12, Number(rowsEl.value) || state.rows));
    saveState(row.id, state);
    renderBoard();
  });
  colsEl.addEventListener("change", () => {
    const row = currentClass();
    if (!row) return;
    const state = stateOf();
    state.cols = Math.max(1, Math.min(12, Number(colsEl.value) || state.cols));
    saveState(row.id, state);
    renderBoard();
  });
  select.addEventListener("change", renderAll);

  async function promptClass(existing) {
    const name = prompt("クラス名", existing ? existing.name : "");
    if (!name) return;
    const count = Number(prompt("人数（1〜60）", existing ? existing.student_count : "30"));
    const body = JSON.stringify({ name, student_count: count });
    if (existing) {
      const data = await toolboxFetch(`/toolbox/api/classes/${existing.id}`, { method: "PUT", body });
      classes = classes.map((row) => (row.id === existing.id ? data.class : row));
    } else {
      const data = await toolboxFetch("/toolbox/api/classes", { method: "POST", body });
      classes.push(data.class);
      select.value = data.class.id;
    }
    renderClasses();
  }

  document.getElementById("tb-class-new").addEventListener("click", () => promptClass(null).catch((e) => alert(e.message)));
  document.getElementById("tb-class-edit").addEventListener("click", () => {
    const row = currentClass();
    if (row) promptClass(row).catch((e) => alert(e.message));
  });
  document.getElementById("tb-class-dup").addEventListener("click", async () => {
    const row = currentClass();
    if (!row) return;
    try {
      const data = await toolboxFetch(`/toolbox/api/classes/${row.id}/duplicate`, { method: "POST", body: "{}" });
      classes.push(data.class);
      select.value = data.class.id;
      renderClasses();
    } catch (e) {
      alert(e.message);
    }
  });
  document.getElementById("tb-class-del").addEventListener("click", async () => {
    const row = currentClass();
    if (!row || !confirm(`${row.name} を削除しますか？`)) return;
    try {
      await toolboxFetch(`/toolbox/api/classes/${row.id}`, { method: "DELETE" });
      classes = classes.filter((item) => item.id !== row.id);
      renderClasses();
    } catch (e) {
      alert(e.message);
    }
  });

  ToolboxDisplay.init({
    onNext: shuffle,
    onPrev: () => document.getElementById("tb-clear").click(),
  });
  renderClasses();
})();
