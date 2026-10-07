(function () {
  const modal = document.getElementById("tb-reauth");
  const form = document.getElementById("tb-reauth-form");
  const errorEl = document.getElementById("tb-reauth-error");
  let pending = null;
  let offset = 0;

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

  function filters() {
    const fd = new FormData(document.getElementById("ms-filters"));
    const params = new URLSearchParams();
    fd.forEach((value, key) => { if (value) params.set(key, value); });
    params.set("offset", String(offset));
    return params;
  }

  function renderRows(items, append) {
    const body = document.getElementById("ms-rows");
    if (!append) body.innerHTML = "";
    items.forEach((item) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td></td><td><textarea rows="3"></textarea><p class="tb-muted"></p></td><td><input data-ja type="text"><select data-level><option value="">—</option><option>1</option><option>2</option><option>3</option></select></td><td></td>`;
      const order = Number(item.source_order);
      tr.children[0].textContent = `タイプ${item.type}${order && order <= 10000 ? " No." + order : ""}${item.ai_pending ? " 未確認" : ""}`;
      tr.querySelector("textarea").value = item.text || "";
      tr.querySelector("p").textContent = `${(item.flags || []).join(", ")} ${item.status || ""} ${item.ai_reason || ""}`;
      tr.querySelector("[data-ja]").value = item.ja || "";
      tr.querySelector("[data-level]").value = item.level || "";
      const save = document.createElement("button");
      save.type = "button";
      save.className = "tb-btn";
      save.textContent = "保存";
      save.addEventListener("click", () => {
        toolboxFetch(`/toolbox/admin/api/minute-speech/topics/${item.id}`, {
          method: "POST",
          body: JSON.stringify({
            text: tr.querySelector("textarea").value,
            ja: tr.querySelector("[data-ja]").value,
            level: tr.querySelector("[data-level]").value,
          }),
        }).then(() => alert("保存しました。")).catch((err) => alert(err.message));
      });
      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.className = "tb-btn";
      toggle.textContent = item.status === "hidden" ? "公開" : "非公開";
      toggle.addEventListener("click", () => {
        toolboxFetch(`/toolbox/admin/api/minute-speech/topics/${item.id}`, {
          method: "POST",
          body: JSON.stringify({ status: item.status === "hidden" ? "active" : "hidden" }),
        }).then(() => load(false)).catch((err) => alert(err.message));
      });
      tr.lastElementChild.append(save, toggle);
      body.appendChild(tr);
    });
  }

  function load(reset) {
    if (reset) offset = 0;
    return toolboxFetch(`/toolbox/admin/api/minute-speech/topics?${filters()}`).then((data) => {
      renderRows(data.results || [], !reset);
      offset += (data.results || []).length;
      document.getElementById("ms-more").hidden = !data.has_more;
    });
  }

  function poll(url, target) {
    const node = document.getElementById(target);
    const run = () => toolboxFetch(url).then((data) => {
      node.textContent = data.running ? `実行中 ${data.done || 0} / ${data.total || data.remaining || ""}` : (data.error || "待機中");
      if (data.running) setTimeout(run, 2000);
      else if (data.stale != null) {
        node.textContent = `件数 ${data.count} / 未反映 ${data.stale} / 推定 $${data.est_cost_usd}`;
      }
    }).catch((err) => { node.textContent = err.message; });
    run();
  }

  document.getElementById("ms-filters").addEventListener("submit", (ev) => {
    ev.preventDefault();
    load(true).catch((err) => alert(err.message));
  });
  document.getElementById("ms-more").addEventListener("click", () => load(false).catch((err) => alert(err.message)));
  document.getElementById("ms-embed-refresh").addEventListener("click", () => poll("/toolbox/admin/api/minute-speech/embed/estimate", "ms-embed-job"));
  document.getElementById("ms-classify-refresh").addEventListener("click", () => poll("/toolbox/admin/api/minute-speech/classify/estimate", "ms-classify-job"));
  document.getElementById("ms-embed-start").addEventListener("click", () => {
    if (!confirm("表示された推定費用でインデックスを作成・更新します。")) return;
    withReauth(() => toolboxFetch("/toolbox/admin/api/minute-speech/embed/start", { method: "POST", body: "{}" }).then(() => {
      poll("/toolbox/admin/api/minute-speech/embed/estimate", "ms-embed-job");
    }));
  });
  document.getElementById("ms-classify-start").addEventListener("click", () => {
    if (!confirm("表示された推定費用で、未付与のお題を分類・翻訳します。")) return;
    withReauth(() => toolboxFetch("/toolbox/admin/api/minute-speech/classify/start", { method: "POST", body: "{}" }).then(() => {
      poll("/toolbox/admin/api/minute-speech/classify/estimate", "ms-classify-job");
    }));
  });
  document.getElementById("ms-approve").addEventListener("click", () => {
    withReauth(() => toolboxFetch("/toolbox/admin/api/minute-speech/approve-ai", { method: "POST", body: "{}" }).then((data) => {
      alert(`${data.changed} 件を承認しました。`);
      load(true);
    }));
  });
  document.getElementById("ms-hide-flags").addEventListener("click", () => {
    withReauth(() => toolboxFetch("/toolbox/admin/api/minute-speech/hide-flagged", { method: "POST", body: "{}" }).then((data) => {
      alert(`${data.changed} 件を非公開にしました。`);
      load(true);
    }));
  });
  document.getElementById("ms-add").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const fd = new FormData(ev.target);
    withReauth(() => toolboxFetch("/toolbox/admin/api/minute-speech/topics", {
      method: "POST",
      body: JSON.stringify({
        type: fd.get("type"),
        text: fd.get("text"),
        level: fd.get("level"),
        ja: fd.get("ja"),
      }),
    }).then(() => {
      ev.target.reset();
      load(true);
    }));
  });
  document.getElementById("ms-admin-settings").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const fd = new FormData(ev.target);
    withReauth(() => toolboxFetch("/toolbox/admin/api/minute-speech/settings", {
      method: "POST",
      body: JSON.stringify({
        minute_speech_sim_min: Number(fd.get("minute_speech_sim_min")),
        minute_speech_translate_query: fd.get("minute_speech_translate_query") === "on",
      }),
    }).then(() => alert("保存しました。")));
  });

  load(true).catch((err) => alert(err.message));
})();
