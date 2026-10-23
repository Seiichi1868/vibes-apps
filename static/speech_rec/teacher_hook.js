/* 1分スピーチのお題カードから QR を作る。speech_rec を外しても本体はイベントを投げるだけ。 */
(function () {
  const headers = { "Content-Type": "application/json", "X-Speech-Rec-Request": "1" };
  let root = null;

  function close() {
    if (root) root.remove();
    root = null;
  }

  function overlay(html) {
    close();
    root = document.createElement("div");
    root.className = "sr-overlay";
    root.innerHTML = html;
    document.body.appendChild(root);
    root.querySelector("[data-close]").onclick = close;
  }

  async function unlock(password) {
    const res = await fetch("/rec/admin/unlock", {
      method: "POST",
      headers,
      body: JSON.stringify({ password }),
    });
    return res.ok;
  }

  function formHtml(detail) {
    const text = String(detail.text || "").replace(/[&<>]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[ch]));
    return `<div class="sr-sheet">
      <section class="sr-card">
        <button type="button" class="tb-btn" data-close>閉じる</button>
        <h2>スピーチ評価のQR</h2>
        <p class="sr-topic">${text}</p>
        <label class="sr-field">管理パスワード（ログイン済みなら空でよい）<input id="sr-pass" type="password" autocomplete="current-password"></label>
        <label class="tb-switch"><input id="sr-on" type="checkbox"><span>生徒に公開する</span></label>
        <div class="sr-row">
          <label class="sr-field">準備（秒・0で準備なし）<input id="sr-prep" type="number" min="0" max="180" value="${Number(detail.prep) || 0}"></label>
          <label class="sr-field">発話（秒）<input id="sr-speak" type="number" min="10" max="180" value="${Number(detail.speak) || 60}"></label>
        </div>
        <label class="sr-field">メモ（生徒には出ません）<input id="sr-label" placeholder="1年3組"></label>
        <p class="tb-error" id="sr-err" hidden></p>
        <button type="button" class="tb-btn tb-btn-primary" id="sr-make">QRを作る</button>
      </section>
    </div>`;
  }

  function showQr(data) {
    overlay(`<div class="sr-qr">
      <button type="button" class="tb-btn" data-close>閉じる</button>
      <img alt="提出用QR" src="${data.qr}">
      <p>${data.url}</p>
    </div>`);
  }

  document.addEventListener("speechrec:open", (event) => {
    const detail = event.detail || {};
    overlay(formHtml(detail));
    document.getElementById("sr-make").onclick = async () => {
      const err = document.getElementById("sr-err");
      err.hidden = true;
      err.textContent = "";
      const password = document.getElementById("sr-pass").value;
      if (password) {
        const ok = await unlock(password);
        if (!ok) {
          err.hidden = false;
          err.textContent = "パスワードが違います。";
          return;
        }
      }
      const enabled = document.getElementById("sr-on").checked;
      const saved = await fetch("/rec/api/t/settings", {
        method: "POST",
        headers,
        body: JSON.stringify({ student_enabled: enabled }),
      });
      if (saved.status === 401) {
        err.hidden = false;
        err.textContent = "管理パスワードを入れてください。";
        return;
      }
      const made = await fetch("/rec/api/t/assignments", {
        method: "POST",
        headers,
        body: JSON.stringify({
          text: detail.text,
          source_id: detail.id || "",
          prep_sec: Number(document.getElementById("sr-prep").value),
          speak_sec: Number(document.getElementById("sr-speak").value),
          label: document.getElementById("sr-label").value,
          ttl_hours: 24,
          max_submissions: 40,
        }),
      });
      const body = await made.json().catch(() => ({}));
      if (!made.ok) {
        err.hidden = false;
        err.textContent = "QRを作れませんでした。";
        return;
      }
      showQr(body);
    };
  });
})();
