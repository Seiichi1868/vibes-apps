// Safari など、フォルダへ直接書き込めないブラウザ向け：
// サーバーにたまった録音を月に一度まとめてダウンロードし、指定フォルダへ移したあとでサーバーの音声を消す。
(function () {
  if (typeof window.showDirectoryPicker === "function") return; // Chrome / Edge はフォルダへ直接保存するので不要
  if (!window.toolboxFetch) return;

  const API = "/toolbox/api/talk/audio-archive";
  const HIDE_KEY = "toolbox.audio_archive.hidden_until";
  let box = null;

  function fmtSize(bytes) {
    const mb = (Number(bytes) || 0) / (1024 * 1024);
    if (mb < 0.1) return `${Math.max(1, Math.round((Number(bytes) || 0) / 1024))}KB`;
    return mb >= 10 ? `${Math.round(mb)}MB` : `${mb.toFixed(1)}MB`;
  }

  function fmtDay(iso) {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? "" : `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()}`;
  }

  function esc(text) {
    return String(text == null ? "" : text).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }

  function mount() {
    if (box) box.remove();
    box = document.createElement("section");
    box.className = "tb-archive-banner";
    box.setAttribute("role", "region");
    box.setAttribute("aria-label", "音声のまとめ保存");
    const host = document.querySelector('[data-view="settings"]') || document.querySelector(".tb-main");
    if (!host) return null;
    host.insertBefore(box, host.firstChild);
    return box;
  }

  function clear() {
    if (box) box.remove();
    box = null;
  }

  function render(status, forced) {
    if (!status.count) {
      if (forced) {
        mount().innerHTML = '<p class="tb-muted">サーバーに残っている音声はありません。</p>';
      } else {
        clear();
      }
      return;
    }
    const folder = esc(status.folder || "ToolboxTalkAudio");
    const el = mount();
    if (!el) return;
    if (status.awaiting) {
      el.innerHTML = `
        <strong>音声をフォルダへ移してください</strong>
        <p>ダウンロードした zip を開き、中の音声ファイル（${status.awaiting}件）を「${folder}」フォルダへ移動してください。移し終えたら下のチェックを入れると、サーバーの音声を削除します。</p>
        <label class="tb-check"><input type="checkbox" id="tb-archive-done"> 「${folder}」フォルダへ移動しました</label>
        <div class="tb-actions">
          <a class="tb-btn" href="${API}.zip" download id="tb-archive-redo">もう一度ダウンロード</a>
        </div>
        <p class="tb-muted" id="tb-archive-msg" aria-live="polite"></p>`;
      el.querySelector("#tb-archive-done").addEventListener("change", onConfirm);
      el.querySelector("#tb-archive-redo").addEventListener("click", () => setTimeout(refresh, 2500));
      return;
    }
    el.innerHTML = `
      <strong>録音の音声を保存する時期です</strong>
      <p>サーバーに音声が${status.count}件（約${fmtSize(status.bytes)}）あります${status.oldest_at ? `（最も古い録音: ${esc(fmtDay(status.oldest_at))}）` : ""}。Safari はフォルダへ直接保存できないため、まとめてダウンロードして「${folder}」フォルダへ移してください。</p>
      <div class="tb-actions">
        <a class="tb-btn tb-btn-primary" href="${API}.zip" download id="tb-archive-dl">まとめてダウンロード</a>
        <button class="tb-btn" type="button" id="tb-archive-later">あとで</button>
      </div>`;
    el.querySelector("#tb-archive-dl").addEventListener("click", () => setTimeout(refresh, 2500));
    el.querySelector("#tb-archive-later").addEventListener("click", () => {
      try { sessionStorage.setItem(HIDE_KEY, "1"); } catch (_) {}
      clear();
    });
  }

  async function onConfirm(ev) {
    const input = ev.target;
    const msg = document.getElementById("tb-archive-msg");
    if (!input.checked) return;
    if (!confirm("サーバーの音声を削除します。フォルダへ移動できていることを確認しましたか？")) {
      input.checked = false;
      return;
    }
    input.disabled = true;
    try {
      const data = await window.toolboxFetch(`${API}/confirm`, { method: "POST", body: "{}" });
      if (msg) msg.textContent = `サーバーの音声を${data.released}件削除しました。`;
      setTimeout(refresh, 1800);
    } catch (err) {
      input.disabled = false;
      input.checked = false;
      if (msg) msg.textContent = err.message;
    }
  }

  async function refresh(forced) {
    try {
      const status = await window.toolboxFetch(API);
      let hidden = false;
      try { hidden = sessionStorage.getItem(HIDE_KEY) === "1"; } catch (_) {}
      if (forced === true) {
        render(status, true);
      } else if (status.due && !(hidden && !status.awaiting)) {
        render(status, false);
      } else {
        clear();
      }
    } catch (_) {
      clear();
    }
  }

  window.ToolboxAudioArchive = {
    show() {
      try { sessionStorage.removeItem(HIDE_KEY); } catch (_) {}
      return refresh(true);
    },
  };

  refresh();
})();
