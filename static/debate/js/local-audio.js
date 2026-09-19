(() => {
  const DB_NAME = "debate_local_audio";
  const STORE = "clips";
  const MAX_CLIPS = 24;

  function clipId(sessionId, part) {
    return `${sessionId}:${part}`;
  }

  function openDb() {
    return new Promise((resolve, reject) => {
      if (!window.indexedDB) {
        reject(new Error("IndexedDB unavailable"));
        return;
      }
      const request = indexedDB.open(DB_NAME, 1);
      request.onupgradeneeded = () => {
        const db = request.result;
        if (!db.objectStoreNames.contains(STORE)) {
          db.createObjectStore(STORE, { keyPath: "id" });
        }
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  function withStore(mode, fn) {
    return openDb().then(
      (db) =>
        new Promise((resolve, reject) => {
          const tx = db.transaction(STORE, mode);
          const store = tx.objectStore(STORE);
          const result = fn(store);
          tx.onerror = () => reject(tx.error);
          if (result instanceof IDBRequest) {
            result.onsuccess = () => resolve(result.result);
            result.onerror = () => reject(result.error);
            return;
          }
          tx.oncomplete = () => resolve(result);
        })
    );
  }

  async function put(sessionId, part, blob, mimeType) {
    const id = clipId(sessionId, part);
    if (!sessionId || !part || !blob) return;
    try {
      await withStore("readwrite", (store) =>
        store.put({
          id,
          sessionId,
          part,
          blob,
          mimeType: mimeType || blob.type || "audio/webm",
          savedAt: Date.now(),
        })
      );
      await prune();
    } catch (_) {
      // プライベートモード等では端末キャッシュを諦める
    }
  }

  async function get(sessionId, part) {
    if (!sessionId || !part) return null;
    try {
      return (await withStore("readonly", (store) => store.get(clipId(sessionId, part)))) || null;
    } catch (_) {
      return null;
    }
  }

  async function remove(sessionId, part) {
    if (!sessionId || !part) return;
    try {
      await withStore("readwrite", (store) => store.delete(clipId(sessionId, part)));
    } catch (_) {
      // 削除できなくても再生の致命傷にはしない
    }
  }

  async function prune() {
    try {
      const items = (await withStore("readonly", (store) => store.getAll())) || [];
      const keep = new Set(window.DebateLocalSessions?.getIds?.() || []);
      const newest = [...items].sort((a, b) => (b.savedAt || 0) - (a.savedAt || 0));
      const overflow = newest.slice(MAX_CLIPS);
      const otherSessions = keep.size ? items.filter((item) => !keep.has(item.sessionId)) : [];
      const staleIds = new Set([...overflow, ...otherSessions].map((item) => item.id).filter(Boolean));
      if (!staleIds.size) return;
      await withStore("readwrite", (store) => {
        staleIds.forEach((id) => store.delete(id));
      });
    } catch (_) {
      // 古いキャッシュが残っても問題ない
    }
  }

  async function attachPlayer(audioEl, { sessionId, part, fallbackUrl, statusEl, emptyEl } = {}) {
    if (!audioEl) return;

    const local = await get(sessionId, part);
    if (local?.blob && local.blob.size > 0) {
      if (audioEl.dataset.objectUrl) URL.revokeObjectURL(audioEl.dataset.objectUrl);
      const url = URL.createObjectURL(local.blob);
      audioEl.dataset.objectUrl = url;
      audioEl.src = url;
      audioEl.preload = "auto";
      audioEl.classList.remove("hidden");
      emptyEl?.classList.add("hidden");
      if (statusEl) statusEl.textContent = "この端末の録音";
      audioEl.load();
      return;
    }

    if (fallbackUrl) {
      audioEl.src = fallbackUrl;
      audioEl.preload = "auto";
      audioEl.classList.remove("hidden");
      emptyEl?.classList.add("hidden");
      if (statusEl) statusEl.textContent = "サーバーから読み込み中…";
      audioEl.addEventListener(
        "canplay",
        () => {
          if (statusEl) statusEl.textContent = "";
        },
        { once: true }
      );
      audioEl.addEventListener("error", () => {
        if (statusEl) {
          statusEl.textContent = "音声を再生できません。別の端末の録音は通信が必要です。";
        }
      });
      audioEl.load();
      return;
    }

    audioEl.classList.add("hidden");
    emptyEl?.classList.remove("hidden");
    if (statusEl) statusEl.textContent = "";
  }

  window.DebateLocalAudio = { put, get, remove, attachPlayer };

  const reviewAudio = document.getElementById("review-audio");
  if (reviewAudio) {
    attachPlayer(reviewAudio, {
      sessionId: window.DEBATE_SESSION_ID,
      part: window.DEBATE_PART,
      fallbackUrl: window.DEBATE_AUDIO_URL || "",
      statusEl: document.getElementById("review-audio-status"),
      emptyEl: document.getElementById("review-audio-empty"),
    });
  }
})();
