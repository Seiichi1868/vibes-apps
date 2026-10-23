(() => {
  const choices = JSON.parse(document.getElementById("choices").textContent || "[]");
  const assignment = document.getElementById("assignment");
  choices.forEach((row) => {
    const option = document.createElement("option");
    option.value = row.id;
    option.textContent = `${row.created_at || ""} ${row.label || row.id}`;
    assignment.appendChild(option);
  });
  const params = new URLSearchParams(location.search);
  if (params.get("assignment_id")) assignment.value = params.get("assignment_id");
  if (params.get("code")) document.getElementById("code").value = params.get("code");
  let rows = [];
  let summary = {};
  let sortKey = "created_at";
  let sortDir = 1;

  const headers = [
    ["time", "時刻"], ["student_id", "ID"], ["attempt", "試"], ["status", "状"],
    ["words", "語"], ["wpm_points", "WPM"], ["general_description", "GD"], ["delivery", "DEL"],
    ["language_use", "LU"], ["topic_development", "TD"], ["rubric", "計"], ["total", "合計"],
    ["oreo", "OREO"], ["pauses", "間"], ["snr_db", "雑"], ["flags", "旗"], ["code", "コード"], ["yen", "円"],
  ];

  function mark(status, error) {
    if (status === "done") return "✓";
    if (status === "error") return "×";
    return "…";
  }

  function shown() {
    const code = document.getElementById("code").value.trim().toUpperCase();
    const status = document.getElementById("status").value;
    return rows.filter((row) => {
      if (status && row.status !== status) return false;
      if (code && String(row.code || "").toUpperCase().indexOf(code) === -1) return false;
      return true;
    }).sort((a, b) => {
      const left = a[sortKey] ?? "";
      const right = b[sortKey] ?? "";
      return (left > right ? 1 : left < right ? -1 : 0) * sortDir;
    });
  }

  function cell(text, className) {
    const td = document.createElement("td");
    td.textContent = text == null ? "" : String(text);
    if (className) td.className = className;
    return td;
  }

  function render() {
    const table = document.getElementById("grid");
    table.innerHTML = "";
    const head = document.createElement("tr");
    headers.forEach(([key, label], index) => {
      const th = document.createElement("th");
      th.textContent = label;
      if (index < 2) th.className = index === 0 ? "sticky" : "sticky2";
      th.onclick = () => {
        sortDir = sortKey === key ? -sortDir : 1;
        sortKey = key;
        render();
      };
      head.appendChild(th);
    });
    const del = document.createElement("th");
    del.textContent = "";
    head.appendChild(del);
    table.appendChild(head);
    shown().forEach((row) => {
      const tr = document.createElement("tr");
      const points = row.points || {};
      const levels = row.levels || {};
      const values = [
        row.time, row.student_id, row.attempt, mark(row.status), row.words, row.wpm_points,
        points.general_description, points.delivery, points.language_use, points.topic_development,
        row.rubric, row.total,
        ["opinion_open", "reason", "example", "opinion_close"].map((key) => (row.oreo || {})[key] ? "●" : "○").join(""),
        row.pauses, row.snr_db, (row.flags || []).join(" "), row.code, row.yen,
      ];
      values.forEach((value, index) => {
        const key = headers[index][0];
        const td = cell(value, index < 2 ? (index === 0 ? "sticky" : "sticky2") : "num");
        if (["general_description", "delivery", "language_use", "topic_development"].includes(key)) {
          td.className += ` lv${levels[key] || ""}`;
        }
        if (key === "status" && row.error_code) td.title = row.error_code;
        if (key === "code") td.className = "code";
        if (key === "snr_db" && Number(value) < 15) td.className += " flag";
        tr.appendChild(td);
      });
      const drop = document.createElement("td");
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = "削除";
      button.onclick = async () => {
        await fetch("/rec/api/t/results/delete", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Speech-Rec-Request": "1" },
          body: JSON.stringify({ assignment_id: assignment.value, record_id: row.id }),
        });
        load();
      };
      drop.appendChild(button);
      tr.appendChild(drop);
      table.appendChild(tr);
    });
    if (summary.n) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 12;
      td.className = "mean";
      td.textContent = `平均 ${summary.mean} / 中央値 ${summary.median}（${summary.n}件）`;
      tr.appendChild(td);
      table.appendChild(tr);
    }
  }

  async function load() {
    if (!assignment.value) return;
    const res = await fetch(`/rec/api/t/results?assignment_id=${encodeURIComponent(assignment.value)}`, {
      headers: { "X-Speech-Rec-Request": "1" },
    });
    const data = await res.json();
    rows = data.rows || [];
    summary = data.summary || {};
    render();
  }

  document.getElementById("reload").onclick = load;
  assignment.onchange = load;
  document.getElementById("code").oninput = render;
  document.getElementById("status").onchange = render;
  document.getElementById("csv").onclick = () => {
    location.href = `/rec/api/t/results.csv?assignment_id=${encodeURIComponent(assignment.value)}`;
  };
  document.getElementById("recalc").onclick = async () => {
    await fetch("/rec/api/t/results/recalc", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Speech-Rec-Request": "1" },
      body: JSON.stringify({ assignment_id: assignment.value }),
    });
    load();
  };
  document.getElementById("drop-all").onclick = async () => {
    if (!window.confirm("この出題の記録を削除します。")) return;
    await fetch("/rec/api/t/results/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Speech-Rec-Request": "1" },
      body: JSON.stringify({ assignment_id: assignment.value, all: true }),
    });
    load();
  };
  load();
})();
