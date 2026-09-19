(() => {
  const STORAGE_KEY = "debate_local_session_ids";
  const MAX_IDS = 20;
  const MODE_LABELS = { batch: "モードA", realtime: "モードB", mixed: "混在" };

  function loadIds() {
    try {
      const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
      if (!Array.isArray(parsed)) return [];
      return parsed.map((id) => String(id || "").trim()).filter(Boolean).slice(0, MAX_IDS);
    } catch (_) {
      return [];
    }
  }

  function saveIds(ids) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(ids.slice(0, MAX_IDS)));
    } catch (_) {
      // プライベートモード等で保存できない場合は再開一覧を出さない
    }
  }

  function remember(sessionId) {
    const id = String(sessionId || "").trim();
    if (!id) return;
    const ids = loadIds().filter((item) => item !== id);
    ids.unshift(id);
    saveIds(ids);
  }

  function forget(sessionId) {
    const id = String(sessionId || "").trim();
    if (!id) return;
    saveIds(loadIds().filter((item) => item !== id));
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function formatSavedAt(iso) {
    const stamp = String(iso || "");
    if (stamp.length < 16) return "";
    return `最終保存: ${stamp.slice(0, 10)} ${stamp.slice(11, 16)}`;
  }

  function renderRow(session) {
    const savedAt = formatSavedAt(session.updated_at || session.created_at);
    const mode = session.transcription_mode
      ? ` · 文字起こし: ${MODE_LABELS[session.transcription_mode] || session.transcription_mode}`
      : "";
    const solo = session.mode === "solo"
      ? ` · Solo Practice ${session.user_side || ""} / ${session.ai_difficulty || ""}`
      : "";
    const meta = savedAt
      ? `<p class="text-[0.68rem] text-slate-400 mt-0.5">${escapeHtml(savedAt)}${escapeHtml(mode)}${escapeHtml(solo)}</p>`
      : "";
    return `
      <li>
        <a
          href="/debate/session/${encodeURIComponent(session.session_id)}"
          class="panel-soft flex items-center justify-between rounded-xl px-4 py-3 text-sm hover:border-teal-200/80 hover:bg-emerald-50/40 transition-colors"
        >
          <div class="min-w-0 pr-4">
            <p class="truncate text-slate-700">${escapeHtml(session.motion || "（論題なし）")}</p>
            ${meta}
          </div>
          <span class="shrink-0 text-xs font-semibold text-slate-500">
            ${Number(session.confirmed_parts) || 0}/${Number(session.total_parts) || 0} パート完了
          </span>
        </a>
      </li>
    `;
  }

  async function renderResumeList() {
    const section = document.getElementById("resume-section");
    const list = document.getElementById("resume-list");
    if (!section || !list) return;

    const ids = loadIds();
    if (!ids.length) {
      section.classList.add("hidden");
      return;
    }

    try {
      const response = await fetch("/debate/api/sessions/lookup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_ids: ids }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "再開一覧の取得に失敗しました。");
      }

      const sessions = Array.isArray(data.sessions) ? data.sessions : [];
      const found = new Set(sessions.map((session) => session.session_id).filter(Boolean));
      const nextIds = ids.filter((id) => found.has(id));
      if (nextIds.length !== ids.length) saveIds(nextIds);

      if (!sessions.length) {
        section.classList.add("hidden");
        list.innerHTML = "";
        return;
      }

      list.innerHTML = sessions.map(renderRow).join("");
      section.classList.remove("hidden");
    } catch (err) {
      list.innerHTML = `<li class="text-sm text-rose-600">${escapeHtml(err.message || "再開一覧を読み込めませんでした。")}</li>`;
      section.classList.remove("hidden");
    }
  }

  window.DebateLocalSessions = {
    remember,
    forget,
    getIds: loadIds,
  };

  if (window.DEBATE_SESSION_ID) {
    remember(window.DEBATE_SESSION_ID);
  }

  renderResumeList();
})();
