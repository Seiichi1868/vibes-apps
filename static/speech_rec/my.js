(() => {
  const app = document.getElementById("app");
  const key = "speechrec:history";
  const AXES = [
    ["general_description", "内容", "General Description", "gd"],
    ["delivery", "話し方", "Delivery", "dv"],
    ["language_use", "英語", "Language Use", "lu"],
    ["topic_development", "構成", "Topic Development", "td"],
  ];

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

  function returnPath() {
    const from = new URLSearchParams(location.search).get("from") || "";
    if (!from.startsWith("/rec/") || from.startsWith("/rec/my")) return "";
    if (from.includes("\\") || from.includes("//")) return "";
    return from;
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

  function backLinks() {
    const from = returnPath();
    const today = todayResult();
    return `${from ? `<p><a href="${esc(from)}">受験前の画面に戻る</a></p>` : ""}${today ? `<p><a href="${esc(today)}">今日の結果に戻る</a></p>` : ""}`;
  }

  function bars(level) {
    const n = Math.max(0, Math.min(6, Number(level) || 0));
    return `<span class="ticks" aria-hidden="true">${[1, 2, 3, 4, 5, 6].map((i) => `<i class="${i <= n ? "on" : ""}"></i>`).join("")}</span>`;
  }

  function sheet(row) {
    const saved = row.snapshot && row.snapshot.status === "done" ? row.snapshot : null;
    const data = saved || row;
    const points = (saved && saved.scores && saved.scores.points) || data.points || {};
    const levels = data.levels || {};
    const oreo = (saved && saved.oreo) || data.oreo || {};
    const when = esc(String(data.created_at || "").replace("T", " ").slice(0, 16));
    const show = data.show_points !== false;
    const totalValue = saved && saved.scores ? saved.scores.total : data.total;
    const total = show ? esc(totalValue) : "—";
    const wpm = show ? esc(saved ? saved.wpm_points : data.wpm_points) : "—";
    const rubric = show ? esc(Math.round((Number(totalValue) || 0) - (Number(saved ? saved.wpm_points : data.wpm_points) || 0))) : "—";
    const mark = (on) => `<span class="dot ${on ? "on" : ""}"></span>`;
    const oreoSlots = [
      ["Opinion", oreo.opinion_open],
      ["R1", "reason_1" in oreo ? oreo.reason_1 : oreo.reason],
      ["R2", oreo.reason_2],
      ["E1", "example_1" in oreo ? oreo.example_1 : oreo.example],
      ["E2", oreo.example_2],
      ["結び", oreo.opinion_close],
    ];
    app.className = "app sheet";
    app.innerHTML = `
      <p class="meta">${when} ・ 試行 ${esc(data.attempt)}</p>
      <p class="topic">${esc(data.topic)}</p>
      <p class="total">${total}</p>
      <p class="sub"><span>WPM点 ${wpm}</span><span>ルーブリック ${rubric}</span></p>
      <section class="axes" aria-label="評価項目">
        ${AXES.map(([axis, ja, en, tone]) => `<article class="axis axis-${tone}">
          <header>
            <span class="axis-ja">${ja}</span>
            <span class="axis-en">${en}</span>
            <strong>${levels[axis] ? `Lv ${esc(levels[axis])}` : "—"}</strong>
            <em>${show ? esc(points[axis] || "") : ""}</em>
          </header>
          ${bars(levels[axis])}
        </article>`).join("")}
      </section>
      ${saved ? `<section class="oreo-box" aria-label="OREO">
        <h2>OREO</h2>
        <div class="oreo">
          ${oreoSlots.map(([label, on]) => `<span class="${on ? "hit" : ""}">${mark(on)} ${label}</span>`).join("")}
        </div>
      </section>` : ""}
      <p class="code">${esc(data.verify_code || "")}</p>
      <button type="button" id="back">一覧</button>
      ${backLinks()}`;
    document.getElementById("back").onclick = renderList;
  }

  async function renderList() {
    const saved = loadRows();
    app.className = "app";
    const links = backLinks();
    if (!saved.length) {
      app.innerHTML = `<h1>自分の結果履歴</h1>${links}<p class="status">この端末の結果はまだありません。</p><button type="button" id="clear">この端末の記録を消す</button>`;
      document.getElementById("clear").onclick = clearHistory;
      return;
    }
    const res = await fetch("/rec/api/my", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tokens: saved.map((row) => row.read_token) }),
    });
    const data = await res.json().catch(() => ({ rows: [] }));
    const byToken = new Map(saved.map((row) => [row.read_token, row]));
    const rows = (data.rows || []).map((row) => ({ ...row, snapshot: (byToken.get(row.read_token) || {}).snapshot }));
    app.innerHTML = `<h1>自分の結果履歴</h1>${links}<div id="list"></div><button type="button" id="clear">この端末の記録を消す</button>`;
    const list = document.getElementById("list");
    rows.forEach((row) => {
      const button = document.createElement("button");
      const source = row.snapshot && row.snapshot.status === "done" ? row.snapshot : row;
      const when = String(source.created_at || "").replace("T", " ").slice(0, 16);
      const total = source.scores ? source.scores.total : source.total;
      button.textContent = row.state === "expired" && !row.snapshot
        ? "期限が切れました"
        : `${when} ${shortTopic(source.topic)} ${total ?? ""} ${source.verify_code || ""}`;
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
