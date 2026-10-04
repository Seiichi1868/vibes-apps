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
