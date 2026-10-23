(() => {
  const app = document.getElementById("app");
  const key = "speechrec:history";

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
  }

  function loadRows() {
    const now = Date.now();
    const keep = 60 * 24 * 60 * 60 * 1000;
    let rows = [];
    try { rows = JSON.parse(localStorage.getItem(key) || "[]"); } catch (error) { rows = []; }
    if (!Array.isArray(rows)) rows = [];
    rows = rows.filter((row) => row && row.read_token && now - Number(row.saved_at) < keep);
    localStorage.setItem(key, JSON.stringify(rows.slice(-30)));
    return rows.slice(-30).reverse();
  }

  function shortTopic(text) {
    return String(text || "").trim().split(/\s+/).filter(Boolean).slice(0, 10).join(" ");
  }

  function todayResult() {
    let current = null;
    try { current = JSON.parse(sessionStorage.getItem("speechrec:current") || "null"); } catch (error) { current = null; }
    if (!current || !current.path || !current.read_token) return null;
    const day = (ms) => new Date(ms + 9 * 60 * 60 * 1000).toISOString().slice(0, 10);
    if (day(Number(current.saved_at)) !== day(Date.now())) return null;
    const join = current.path.includes("?") ? "&" : "?";
    return `${current.path}${join}resume=${encodeURIComponent(current.read_token)}`;
  }

  function sheet(data) {
    const points = data.points || {};
    const levels = data.levels || {};
    const when = esc(String(data.created_at || "").replace("T", " ").slice(0, 16));
    const total = data.show_points ? esc(data.total) : "—";
    app.className = "app sheet";
    app.innerHTML = `
      <p class="meta">${when} ・ 試行 ${esc(data.attempt)}</p>
      <p class="topic">${esc(shortTopic(data.topic))}</p>
      <p class="total">${total}</p>
      <div class="bars">
        <div class="bar-row"><span>General Description</span><span>${esc(levels.general_description || "")}</span><span>${esc(points.general_description || "")}</span></div>
        <div class="bar-row"><span>Delivery（流暢さ）</span><span>${esc(levels.delivery || "")}</span><span>${esc(points.delivery || "")}</span></div>
        <div class="bar-row"><span>Language Use</span><span>${esc(levels.language_use || "")}</span><span>${esc(points.language_use || "")}</span></div>
        <div class="bar-row"><span>Topic Development</span><span>${esc(levels.topic_development || "")}</span><span>${esc(points.topic_development || "")}</span></div>
      </div>
      <p class="code">${esc(data.verify_code || "")}</p>
      <button type="button" id="back">一覧</button>
      ${todayResult() ? `<p><a id="today" href="${esc(todayResult())}">今日の結果に戻る</a></p>` : ""}`;
    document.getElementById("back").onclick = renderList;
  }

  async function renderList() {
    const saved = loadRows();
    app.className = "app";
    if (!saved.length) {
      app.innerHTML = `<p class="status">この端末の結果はまだありません。</p><button type="button" id="clear">この端末の記録を消す</button>`;
      document.getElementById("clear").onclick = clearHistory;
      return;
    }
    const res = await fetch("/rec/api/my", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tokens: saved.map((row) => row.read_token) }),
    });
    const data = await res.json().catch(() => ({ rows: [] }));
    const rows = data.rows || [];
    const back = todayResult();
    app.innerHTML = `<h1>自分の結果</h1>${back ? `<p><a href="${esc(back)}">今日の結果に戻る</a></p>` : ""}<div id="list"></div><button type="button" id="clear">この端末の記録を消す</button>`;
    const list = document.getElementById("list");
    rows.forEach((row) => {
      const button = document.createElement("button");
      const when = String(row.created_at || "").replace("T", " ").slice(0, 16);
      button.textContent = row.state === "expired"
        ? "期限が切れました"
        : `${when} ${shortTopic(row.topic)} ${row.total ?? ""} ${row.verify_code || ""}`;
      button.onclick = () => sheet(row);
      list.appendChild(button);
    });
    document.getElementById("clear").onclick = clearHistory;
  }

  function clearHistory() {
    localStorage.removeItem(key);
    renderList();
  }

  renderList();
})();
