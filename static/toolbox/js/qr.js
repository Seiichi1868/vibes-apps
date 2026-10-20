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
  const tabUrl = document.getElementById("tb-qr-tab-url");
  const tabFile = document.getElementById("tb-qr-tab-file");
  const panelUrl = document.getElementById("tb-qr-panel-url");
  const panelFile = document.getElementById("tb-qr-panel-file");
  const fileForm = document.getElementById("tb-qr-file-form");
  const fileInput = document.getElementById("tb-qr-file");
  const ttlInput = document.getElementById("tb-qr-ttl");
  const uploadBtn = document.getElementById("tb-qr-upload");
  const progress = document.getElementById("tb-qr-progress");
  const progressBar = document.getElementById("tb-qr-progress-bar");
  const listEl = document.getElementById("tb-qr-list");
  const STORAGE_KEY = "tbQrLastUrl";
  const DEVICE_KEY = "toolbox.qr.device.v1";
  let debounceId = 0;
  let requestSeq = 0;
  let currentLink = "";

  function deviceId() {
    let id = "";
    try { id = localStorage.getItem(DEVICE_KEY) || ""; } catch (_) {}
    if (!id) {
      id = (crypto.randomUUID && crypto.randomUUID()) || String(Date.now());
      try { localStorage.setItem(DEVICE_KEY, id); } catch (_) {}
    }
    return id.replace(/[^A-Za-z0-9_-]/g, "").slice(0, 64);
  }

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

  function showTab(which) {
    const fileMode = which === "file";
    if (panelUrl) panelUrl.hidden = fileMode;
    if (panelFile) panelFile.hidden = !fileMode;
    if (tabUrl) {
      tabUrl.classList.toggle("is-active", !fileMode);
      tabUrl.setAttribute("aria-selected", fileMode ? "false" : "true");
    }
    if (tabFile) {
      tabFile.classList.toggle("is-active", fileMode);
      tabFile.setAttribute("aria-selected", fileMode ? "true" : "false");
    }
    if (fileMode) loadFiles();
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
    try { input.select(); } catch (_) {}
  }

  function formatSize(bytes) {
    const n = Number(bytes) || 0;
    if (n < 1024) return n + " B";
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
    return (n / (1024 * 1024)).toFixed(1) + " MB";
  }

  function formatExpiry(iso) {
    if (!iso) return "";
    const dt = new Date(iso);
    if (Number.isNaN(dt.getTime())) return iso;
    const m = dt.getMonth() + 1;
    const d = dt.getDate();
    const hh = String(dt.getHours()).padStart(2, "0");
    const mm = String(dt.getMinutes()).padStart(2, "0");
    return m + "/" + d + " " + hh + ":" + mm + " まで";
  }

  async function loadFiles() {
    if (!listEl) return;
    try {
      const data = await window.toolboxFetch("/toolbox/api/qr/files", {
        headers: { "X-Toolbox-Device": deviceId() },
      });
      listEl.innerHTML = "";
      const files = data.files || [];
      if (!files.length) {
        const empty = document.createElement("li");
        empty.className = "tb-muted";
        empty.textContent = "まだありません";
        listEl.appendChild(empty);
        return;
      }
      files.forEach((file) => {
        const li = document.createElement("li");
        li.className = "tb-qr-list-item";
        const meta = document.createElement("div");
        meta.className = "tb-qr-list-meta";
        const name = document.createElement("strong");
        name.textContent = file.name || "ファイル";
        const sub = document.createElement("span");
        sub.textContent = formatSize(file.size) + " · " + formatExpiry(file.expires_at);
        meta.appendChild(name);
        meta.appendChild(sub);
        const actions = document.createElement("div");
        actions.className = "tb-actions";
        const show = document.createElement("button");
        show.type = "button";
        show.className = "tb-btn";
        show.textContent = "QRを出す";
        show.addEventListener("click", () => {
          showQr(file.url, file.qr);
          setStatus("生徒が読み取れるように、スクリーンに大きく出してください。", false);
        });
        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "tb-btn";
        remove.textContent = "削除";
        remove.addEventListener("click", () => removeFile(file.id));
        actions.appendChild(show);
        actions.appendChild(remove);
        li.appendChild(meta);
        li.appendChild(actions);
        listEl.appendChild(li);
      });
    } catch (err) {
      setStatus(err.message || "一覧の取得に失敗しました。", true);
    }
  }

  async function removeFile(id) {
    try {
      await window.toolboxFetch("/toolbox/api/qr/files/" + encodeURIComponent(id), {
        method: "DELETE",
        headers: { "X-Toolbox-Device": deviceId() },
      });
      setStatus("削除しました。", false);
      loadFiles();
    } catch (err) {
      setStatus(err.message || "削除に失敗しました。", true);
    }
  }

  function uploadFile(file, ttl) {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("ttl_days", ttl);
    if (progress) progress.hidden = false;
    if (progressBar) progressBar.style.width = "0%";
    if (uploadBtn) uploadBtn.disabled = true;
    setStatus("アップロードしています…", false);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/toolbox/api/qr/files");
    xhr.setRequestHeader("X-CSRF-Token", window.TOOLBOX_CSRF || "");
    xhr.setRequestHeader("X-Toolbox-Device", deviceId());
    xhr.upload.onprogress = (ev) => {
      if (!progressBar || !ev.lengthComputable) return;
      progressBar.style.width = Math.round((ev.loaded / ev.total) * 100) + "%";
    };
    xhr.onload = () => {
      if (uploadBtn) uploadBtn.disabled = false;
      if (progress) progress.hidden = true;
      let data = {};
      try { data = JSON.parse(xhr.responseText || "{}"); } catch (_) {}
      if (xhr.status < 200 || xhr.status >= 300 || !data.ok) {
        setStatus((data && data.error) || "アップロードに失敗しました。", true);
        return;
      }
      showQr(data.file.url, data.qr);
      setStatus("アップロードしました。生徒が読み取れるように、スクリーンに大きく出してください。", false);
      if (fileInput) fileInput.value = "";
      loadFiles();
    };
    xhr.onerror = () => {
      if (uploadBtn) uploadBtn.disabled = false;
      if (progress) progress.hidden = true;
      setStatus("アップロードに失敗しました。", true);
    };
    xhr.send(fd);
  }

  if (tabUrl) tabUrl.addEventListener("click", () => showTab("url"));
  if (tabFile) tabFile.addEventListener("click", () => showTab("file"));

  if (form) {
    form.addEventListener("submit", (ev) => {
      ev.preventDefault();
      clearTimeout(debounceId);
      generate(input ? input.value : "");
    });
  }

  if (fileForm) {
    fileForm.addEventListener("submit", (ev) => {
      ev.preventDefault();
      const file = fileInput && fileInput.files && fileInput.files[0];
      if (!file) {
        setStatus("ファイルを選んでください。", true);
        return;
      }
      uploadFile(file, ttlInput ? ttlInput.value : "7");
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
    try { fromStore = (sessionStorage.getItem(STORAGE_KEY) || "").trim(); } catch (_) {}
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
          throw new Error("clipboard");
        }
        const prev = copyBtn.textContent;
        copyBtn.textContent = "コピーしました";
        setStatus("リンクをコピーしました。", false);
        window.setTimeout(() => { copyBtn.textContent = prev; }, 1600);
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
