(function () {
  const modal = document.getElementById("tb-reauth");
  const form = document.getElementById("tb-reauth-form");
  const errorEl = document.getElementById("tb-reauth-error");
  let pending = null;

  function withReauth(fn) {
    return fn().catch((err) => {
      if (err.data && err.data.error === "confirm_required") {
        pending = fn;
        errorEl.hidden = true;
        modal.hidden = false;
        form.password.focus();
        return;
      }
      alert(err.message);
    });
  }

  form.addEventListener("submit", (ev) => {
    ev.preventDefault();
    toolboxFetch("/toolbox/admin/api/reauth", {
      method: "POST",
      body: JSON.stringify({ password: form.password.value }),
    }).then(() => {
      modal.hidden = true;
      form.reset();
      if (pending) {
        const next = pending;
        pending = null;
        next().catch((err) => alert(err.message));
      }
    }).catch((err) => {
      errorEl.textContent = err.message;
      errorEl.hidden = false;
    });
  });
  document.getElementById("tb-reauth-cancel").addEventListener("click", () => {
    modal.hidden = true;
    pending = null;
  });

  document.getElementById("tb-user-form").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const fd = new FormData(ev.target);
    withReauth(() => toolboxFetch("/toolbox/admin/api/users", {
      method: "POST",
      body: JSON.stringify({
        username: fd.get("username"),
        password: fd.get("password"),
        role: fd.get("role"),
      }),
    }).then(() => location.reload()));
  });

  document.getElementById("tb-user-table").addEventListener("click", (ev) => {
    const btn = ev.target.closest("button");
    const tr = ev.target.closest("tr");
    if (!btn || !tr) return;
    const id = tr.dataset.user;
    const act = btn.dataset.act;
    if (act === "toggle") {
      const next = btn.dataset.active !== "1";
      withReauth(() => toolboxFetch(`/toolbox/admin/api/users/${id}/active`, {
        method: "POST",
        body: JSON.stringify({ is_active: next }),
      }).then(() => location.reload()));
    }
    if (act === "reset") {
      withReauth(() => toolboxFetch(`/toolbox/admin/api/users/${id}/reset-password`, {
        method: "POST",
        body: "{}",
      }).then((data) => {
        alert(`新しいパスワード: ${data.password}`);
      }));
    }
    if (act === "delete" && confirm("このユーザーを削除しますか？")) {
      withReauth(() => toolboxFetch(`/toolbox/admin/api/users/${id}`, { method: "DELETE" }).then(() => location.reload()));
    }
  });

  document.querySelectorAll(".tb-tool-toggles input[data-tool]").forEach((input) => {
    input.addEventListener("change", () => {
      withReauth(() => toolboxFetch(`/toolbox/admin/api/tools/${input.dataset.tool}/enabled`, {
        method: "POST",
        body: JSON.stringify({ enabled: input.checked }),
      }));
    });
  });

  document.getElementById("tb-limit-form").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const fd = new FormData(ev.target);
    withReauth(() => toolboxFetch("/toolbox/admin/api/settings", {
      method: "POST",
      body: JSON.stringify({
        daily_limit_usd: Number(fd.get("daily_limit_usd")),
        login_required_enabled: fd.get("login_required_enabled") === "on",
        parallel_browser_stt: fd.get("parallel_browser_stt") === "on",
      }),
    }).then(() => alert("保存しました。")));
  });

  document.querySelectorAll(".tb-model-table").forEach((table) => {
    table.addEventListener("change", (ev) => {
      const input = ev.target;
      if (input.name && input.name.startsWith("model-")) {
        withReauth(() => toolboxFetch("/toolbox/admin/api/models", {
          method: "POST",
          body: JSON.stringify({ kind: table.dataset.kind, model_id: input.value }),
        }).then(() => location.reload()));
      }
    });
  });

  document.querySelectorAll("[data-edit-model]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const score = prompt("性能スコア（1〜5・参考値）", btn.dataset.score);
      if (!score) return;
      const note = prompt("性能メモ（参考値）", btn.dataset.note || "");
      withReauth(() => toolboxFetch(`/toolbox/admin/api/models/${btn.dataset.editModel}/meta`, {
        method: "POST",
        body: JSON.stringify({ quality_score: Number(score), quality_note: note }),
      }).then(() => location.reload()));
    });
  });

  const dirSupported = typeof window.showDirectoryPicker === "function";
  function idbOpen() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open("toolbox-talk-check", 1);
      req.onupgradeneeded = () => {
        if (!req.result.objectStoreNames.contains("kv")) req.result.createObjectStore("kv");
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }
  function idbGet(key) {
    return idbOpen().then((db) => new Promise((resolve, reject) => {
      const req = db.transaction("kv").objectStore("kv").get(key);
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    }));
  }
  function idbSet(key, value) {
    return idbOpen().then((db) => new Promise((resolve, reject) => {
      const tx = db.transaction("kv", "readwrite");
      tx.objectStore("kv").put(value, key);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    }));
  }
  async function updateDirStatus() {
    const el = document.getElementById("tb-dir-status");
    const btn = document.getElementById("tb-dir-pick");
    if (!el || !btn) return;
    if (!dirSupported) {
      el.textContent = "このブラウザはフォルダへ直接保存できません。音声はいったんサーバーに保存され、月に一度まとめてダウンロードできます。";
      btn.textContent = "このブラウザでは選べません";
      btn.disabled = true;
      return;
    }
    let handle = null;
    try { handle = await idbGet("dir"); } catch (_) {}
    if (!handle) {
      el.textContent = "未設定です。選ぶまでは音声がサーバーに保存されます。";
      btn.textContent = "保存先フォルダを選ぶ";
      return;
    }
    let ok = false;
    try { ok = (await handle.queryPermission({ mode: "readwrite" })) === "granted"; } catch (_) {}
    el.textContent = ok
      ? `保存先: ${handle.name}（使用できます）`
      : `保存先: ${handle.name}（アクセス許可が必要です。録音を始めるときに許可を求めます）`;
    btn.textContent = "保存先フォルダを変更";
  }
  const dirPick = document.getElementById("tb-dir-pick");
  if (dirPick) {
    dirPick.addEventListener("click", async () => {
      try {
        const handle = await window.showDirectoryPicker({ id: "toolbox-talk-audio", mode: "readwrite", startIn: "documents" });
        await idbSet("dir", handle);
      } catch (err) {
        if (err && err.name !== "AbortError") alert(`フォルダを選べませんでした: ${err.message}`);
      }
      updateDirStatus();
    });
    updateDirStatus();
  }

  const talkBody = document.querySelector("#tb-talk-archives tbody");
  const talkEmpty = document.getElementById("tb-talk-archives-empty");
  const talkSort = { key: "created_at", order: "desc" };
  const STATUS_LABEL = { recorded: "文字起こし未完了", transcribed: "問題未作成", ready: "問題あり" };

  function fmtDate(iso) {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso || "";
    const p = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}/${p(d.getMonth() + 1)}/${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
  }

  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function loadTalkArchives() {
    if (!talkBody) return;
    const params = new URLSearchParams({ sort: talkSort.key, order: talkSort.order });
    toolboxFetch(`/toolbox/admin/api/talk/sessions?${params}`).then((data) => {
      const rows = data.sessions || [];
      if (talkEmpty) talkEmpty.hidden = rows.length > 0;
      talkBody.innerHTML = rows.map((s) => `
        <tr>
          <td>${esc(s.user)}</td>
          <td>${esc(fmtDate(s.created_at))}</td>
          <td>${esc(s.title)}</td>
          <td>${esc(s.level || "—")}</td>
          <td>${esc(s.question_count || 0)}</td>
          <td>${esc(STATUS_LABEL[s.status] || s.status || "—")}</td>
        </tr>`).join("");
    }).catch((err) => {
      talkBody.innerHTML = `<tr><td colspan="6">${err.message}</td></tr>`;
    });
  }

  document.querySelectorAll("[data-talk-sort]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const key = btn.dataset.talkSort;
      talkSort.order = talkSort.key === key && talkSort.order === "desc" ? "asc" : "desc";
      talkSort.key = key;
      loadTalkArchives();
    });
  });
  loadTalkArchives();

  document.querySelectorAll("[data-sort]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const key = btn.dataset.sort;
      document.querySelectorAll(".tb-model-table tbody").forEach((tbody) => {
        const rows = Array.from(tbody.querySelectorAll("tr"));
        rows.sort((a, b) => Number(a.dataset[key]) - Number(b.dataset[key]));
        if (key === "quality") rows.reverse();
        rows.forEach((row) => tbody.appendChild(row));
      });
    });
  });
})();
