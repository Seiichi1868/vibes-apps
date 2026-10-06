(function () {
  const LAST_KEY = "toolbox.random_pick.last.v1";
  let classes = window.ToolboxClasses.load(window.TOOLBOX_CLASSES);
  const select = document.getElementById("tb-class");
  const grid = document.getElementById("tb-grid");
  const result = document.getElementById("tb-result");
  const historyEl = document.getElementById("tb-history");
  const countEl = document.getElementById("tb-count");
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function saveState(row, state) {
    row.pick = {
      absent: state.absent,
      picked: state.picked,
      history: state.history,
    };
    classes = window.ToolboxClasses.save(classes);
    if (select.value) localStorage.setItem(LAST_KEY, select.value);
  }

  function currentClass() {
    return classes.find((row) => row.id === select.value) || null;
  }

  function defaultState() {
    return { absent: [], picked: [], history: [] };
  }

  function stateOf() {
    const row = currentClass();
    if (!row) return defaultState();
    const state = Object.assign(defaultState(), row.pick || {});
    state.absent = state.absent.filter((n) => n >= 1 && n <= row.student_count);
    state.picked = state.picked.filter((n) => n >= 1 && n <= row.student_count && !state.absent.includes(n));
    return state;
  }

  function renderClasses() {
    const keep = select.value;
    select.innerHTML = classes.map((row) => `<option value="${row.id}">${row.name}（${row.student_count}）</option>`).join("");
    if (keep && classes.some((row) => row.id === keep)) select.value = keep;
    renderGrid();
  }

  function renderGrid() {
    const row = currentClass();
    if (!row) {
      grid.innerHTML = "";
      result.textContent = "クラスを作ってください";
      return;
    }
    const state = stateOf();
    grid.innerHTML = "";
    for (let n = 1; n <= row.student_count; n += 1) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = String(n);
      if (state.absent.includes(n)) btn.classList.add("is-absent");
      if (state.picked.includes(n)) btn.classList.add("is-picked");
      btn.addEventListener("click", () => {
        const next = stateOf();
        if (next.absent.includes(n)) next.absent = next.absent.filter((x) => x !== n);
        else {
          next.absent.push(n);
          next.picked = next.picked.filter((x) => x !== n);
          next.history = next.history.filter((x) => x !== n);
        }
        saveState(row, next);
        renderGrid();
      });
      grid.appendChild(btn);
    }
    historyEl.textContent = state.history.length ? `履歴: ${state.history.join(" → ")}` : "履歴: なし";
  }

  function available(state, count) {
    const row = currentClass();
    const nums = [];
    for (let n = 1; n <= row.student_count; n += 1) {
      if (!state.absent.includes(n) && !state.picked.includes(n)) nums.push(n);
    }
    return nums;
  }

  function pickNow() {
    const row = currentClass();
    if (!row) return;
    let state = stateOf();
    let pool = available(state, row.student_count);
    if (!pool.length) {
      alert("全員が当たりました。リセットします。");
      state.picked = [];
      state.history = [];
      saveState(row, state);
      renderGrid();
      pool = available(state, row.student_count);
      if (!pool.length) {
        result.textContent = "指名できる番号がありません";
        return;
      }
    }
    const want = Math.min(Number(countEl.value) || 1, pool.length);
    const chosen = [];
    const work = pool.slice();
    for (let i = 0; i < want; i += 1) {
      const idx = Math.floor(Math.random() * work.length);
      chosen.push(work.splice(idx, 1)[0]);
    }
    const apply = () => {
      state = stateOf();
      state.picked = state.picked.concat(chosen);
      state.history = state.history.concat(chosen);
      saveState(row, state);
      result.textContent = chosen.join("  ");
      renderGrid();
    };
    if (reduce) {
      apply();
      return;
    }
    const start = Date.now();
    const spin = () => {
      const show = [];
      const tmp = pool.slice();
      for (let i = 0; i < want; i += 1) {
        show.push(tmp[Math.floor(Math.random() * tmp.length)]);
      }
      result.textContent = show.join("  ");
      if (Date.now() - start < 1100) requestAnimationFrame(spin);
      else apply();
    };
    spin();
  }

  document.getElementById("tb-pick").addEventListener("click", pickNow);
  document.getElementById("tb-undo").addEventListener("click", () => {
    const row = currentClass();
    if (!row) return;
    const state = stateOf();
    const last = state.history.pop();
    if (last != null) state.picked = state.picked.filter((n) => n !== last);
    saveState(row, state);
    result.textContent = last != null ? `取消: ${last}` : "—";
    renderGrid();
  });
  document.getElementById("tb-clear").addEventListener("click", () => {
    const row = currentClass();
    if (!row) return;
    saveState(row, defaultState());
    result.textContent = "—";
    renderGrid();
  });
  select.addEventListener("change", () => {
    if (select.value) localStorage.setItem(LAST_KEY, select.value);
    renderGrid();
  });

  function newId() {
    return (crypto.randomUUID && crypto.randomUUID()) || String(Date.now());
  }

  function promptClass(existing) {
    const name = prompt("クラス名", existing ? existing.name : "");
    if (!name || !name.trim()) return;
    const count = Number(prompt("人数（1〜60）", existing ? existing.student_count : "30"));
    if (!Number.isFinite(count) || count < 1 || count > 60) {
      alert("人数は1〜60で入力してください。");
      return;
    }
    if (existing) {
      existing.name = name.trim();
      existing.student_count = count;
    } else {
      const layout = window.ToolboxClasses.suggestGrid(count);
      classes.push({
        id: newId(),
        name: name.trim(),
        student_count: count,
        absent: [],
        seats: [],
        rows: layout.rows,
        cols: layout.cols,
        blocked: [],
        pick: { absent: [], picked: [], history: [] },
      });
      select.value = classes[classes.length - 1].id;
    }
    classes = window.ToolboxClasses.save(classes);
    if (select.value) localStorage.setItem(LAST_KEY, select.value);
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
    const copy = Object.assign({}, row, {
      id: newId(),
      name: `${row.name} のコピー`,
      absent: (row.absent || []).slice(),
      seats: (row.seats || []).slice(),
      blocked: (row.blocked || []).slice(),
      pick: {
        absent: ((row.pick || {}).absent || []).slice(),
        picked: ((row.pick || {}).picked || []).slice(),
        history: ((row.pick || {}).history || []).slice(),
      },
    });
    classes.push(copy);
    select.value = copy.id;
    classes = window.ToolboxClasses.save(classes);
    localStorage.setItem(LAST_KEY, copy.id);
    renderClasses();
  });
  document.getElementById("tb-class-del").addEventListener("click", () => {
    const row = currentClass();
    if (!row || !confirm(`${row.name} をこの端末から削除しますか？`)) return;
    classes = classes.filter((item) => item.id !== row.id);
    classes = window.ToolboxClasses.save(classes);
    renderClasses();
  });

  ToolboxDisplay.init({
    onNext: pickNow,
    onPrev: () => document.getElementById("tb-undo").click(),
  });
  const last = localStorage.getItem(LAST_KEY);
  renderClasses();
  if (last && classes.some((row) => row.id === last)) {
    select.value = last;
    renderGrid();
  }
})();
