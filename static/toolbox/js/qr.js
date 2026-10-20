(function () {
  const form = document.getElementById("tb-qr-form");
  const input = document.getElementById("tb-qr-input");
  const statusEl = document.getElementById("tb-qr-status");
  const emptyEl = document.getElementById("tb-qr-empty");
  const frame = document.getElementById("tb-qr-frame");
  const image = document.getElementById("tb-qr-image");
  const urlEl = document.getElementById("tb-qr-url");
  const copyBtn = document.getElementById("tb-qr-copy");
  const downloadBtn = document.getElementById("tb-qr-download");
  const STORAGE_KEY = "tbQrLastUrl";
  let debounceId = 0;
  let requestSeq = 0;
  let currentLink = "";

  function setStatus(text, isError) {
    if (!statusEl) return;
    statusEl.textContent = text;
    statusEl.classList.toggle("tb-error", !!isError);
    statusEl.classList.toggle("tb-muted", !isError);
  }

  function hideQr() {
    currentLink = "";
    if (emptyEl) emptyEl.hidden = false;
    if (frame) frame.hidden = true;
    if (urlEl) {
      urlEl.hidden = true;
      urlEl.textContent = "";
    }
    if (downloadBtn) {
      downloadBtn.hidden = true;
      downloadBtn.removeAttribute("href");
    }
    if (image) image.removeAttribute("src");
  }

  function showQr(link, dataUri) {
    currentLink = link;
    if (emptyEl) emptyEl.hidden = true;
    if (frame) frame.hidden = false;
    if (image) image.src = dataUri;
    if (urlEl) {
      urlEl.hidden = false;
      urlEl.textContent = link;
    }
    if (downloadBtn) {
      downloadBtn.hidden = false;
      downloadBtn.href = dataUri;
    }
    try {
      sessionStorage.setItem(STORAGE_KEY, link);
    } catch (_) {}
  }

  async function generate(raw) {
    const text = String(raw || "").trim();
    if (!text) {
      hideQr();
      setStatus("URLを入力または貼り付けるとQRコードが出ます。", false);
      return;
    }
    const seq = ++requestSeq;
    setStatus("QRを作成しています…", false);
    try {
      const data = await window.toolboxFetch("/toolbox/api/qr", {
        method: "POST",
        body: JSON.stringify({ url: text }),
      });
      if (seq !== requestSeq) return;
      if (!data.ok) throw new Error(data.error || "QRの取得に失敗しました");
      showQr(data.link, data.qr);
      setStatus("生徒が読み取れるように、スクリーンに大きく出してください。", false);
    } catch (err) {
      if (seq !== requestSeq) return;
      hideQr();
      setStatus(err.message || "QRの作成に失敗しました。", true);
    }
  }

  function scheduleGenerate() {
    clearTimeout(debounceId);
    debounceId = window.setTimeout(() => generate(input ? input.value : ""), 280);
  }

  function selectInput() {
    if (!input) return;
    try {
      input.select();
    } catch (_) {}
  }

  if (form) {
    form.addEventListener("submit", (ev) => {
      ev.preventDefault();
      clearTimeout(debounceId);
      generate(input ? input.value : "");
    });
  }

  if (input) {
    input.addEventListener("input", scheduleGenerate);
    input.addEventListener("paste", () => {
      window.setTimeout(() => {
        clearTimeout(debounceId);
        generate(input.value);
      }, 0);
    });
    input.addEventListener("focus", selectInput);
    input.addEventListener("click", selectInput);
    input.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") {
        ev.preventDefault();
        clearTimeout(debounceId);
        generate(input.value);
      }
    });
    const params = new URLSearchParams(window.location.search);
    const fromQuery = (params.get("url") || "").trim();
    let fromStore = "";
    try {
      fromStore = (sessionStorage.getItem(STORAGE_KEY) || "").trim();
    } catch (_) {}
    if (fromQuery) {
      input.value = fromQuery;
      generate(fromQuery);
    } else if (fromStore) {
      input.value = fromStore;
      generate(fromStore);
    }
  }

  if (copyBtn) {
    copyBtn.addEventListener("click", async () => {
      const link = currentLink || (input ? input.value.trim() : "");
      if (!link) return;
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(link);
        } else {
          window.prompt("リンク:", link);
          return;
        }
        const prev = copyBtn.textContent;
        copyBtn.textContent = "コピーしました";
        window.setTimeout(() => {
          copyBtn.textContent = prev;
        }, 1200);
      } catch (_) {
        window.prompt("リンク:", link);
      }
    });
  }

  if (frame) {
    frame.addEventListener("click", () => {
      if (window.ToolboxDisplay) window.ToolboxDisplay.enter();
    });
  }

  if (window.ToolboxDisplay) {
    ToolboxDisplay.init({});
  }
})();
