(function () {
  let classes = Array.isArray(window.TOOLBOX_CLASSES) ? window.TOOLBOX_CLASSES.slice() : [];
  const select = document.getElementById("tb-class");
  const grid = document.getElementById("tb-grid");
  const result = document.getElementById("tb-result");
  const historyEl = document.getElementById("tb-history");
  const countEl = document.getElementById("tb-count");
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function storageKey(id) {
    return `toolbox.random_pick.${id}`;
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

  function defaultState() {
    return { absent: [], picked: [], history: [] };
  }

  function stateOf() {
    const row = currentClass();
    if (!row) return defaultState();
    const state = Object.assign(defaultState(), loadState(row.id));
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
        saveState(row.id, next);
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
      saveState(row.id, state);
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
      saveState(row.id, state);
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
    saveState(row.id, state);
    result.textContent = last != null ? `取消: ${last}` : "—";
    renderGrid();
  });
  document.getElementById("tb-clear").addEventListener("click", () => {
    const row = currentClass();
    if (!row) return;
    saveState(row.id, defaultState());
    result.textContent = "—";
    renderGrid();
  });
  select.addEventListener("change", renderGrid);

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
    onNext: pickNow,
    onPrev: () => document.getElementById("tb-undo").click(),
  });
  renderClasses();
})();
