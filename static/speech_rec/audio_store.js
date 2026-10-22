/* 出題トークンをキーに、採点結果が出るまで音声を端末内へ残す。 */
(function () {
  const DB = "speech_rec";
  const STORE = "clips";
  const TTL_MS = 72 * 60 * 60 * 1000;

  function open() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB, 1);
      req.onupgradeneeded = () => req.result.createObjectStore(STORE);
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  async function withStore(mode, fn) {
    const db = await open();
    try {
      return await new Promise((resolve, reject) => {
        const tx = db.transaction(STORE, mode);
        const store = tx.objectStore(STORE);
        Promise.resolve(fn(store)).then(resolve, reject);
        tx.onerror = () => reject(tx.error);
      });
    } finally {
      db.close();
    }
  }

  async function saveClip(token, blob, meta) {
    const row = { blob, savedAt: Date.now(), meta: meta || {} };
    await withStore("readwrite", (store) => {
      store.put(row, token);
    });
  }

  async function loadClip(token) {
    const row = await new Promise((resolve, reject) => {
      open().then((db) => {
        const tx = db.transaction(STORE, "readonly");
        const req = tx.objectStore(STORE).get(token);
        req.onsuccess = () => {
          db.close();
          resolve(req.result || null);
        };
        req.onerror = () => {
          db.close();
          reject(req.error);
        };
      }, reject);
    });
    if (!row) return null;
    if (Date.now() - row.savedAt > TTL_MS) {
      await deleteClip(token);
      return null;
    }
    return row;
  }

  async function deleteClip(token) {
    await withStore("readwrite", (store) => store.delete(token));
  }

  async function purgeExpired() {
    const db = await open();
    const keys = await new Promise((resolve) => {
      const req = db.transaction(STORE, "readonly").objectStore(STORE).getAllKeys();
      req.onsuccess = () => resolve(req.result || []);
      req.onerror = () => resolve([]);
    });
    db.close();
    for (const key of keys) {
      await loadClip(key);
    }
  }

  window.SpeechRecAudio = { saveClip, loadClip, deleteClip, purgeExpired };
})();
