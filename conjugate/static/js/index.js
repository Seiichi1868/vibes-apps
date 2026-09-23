(() => {
  const openingOverlay = document.getElementById("opening-overlay");
  if (openingOverlay) {
    if (document.documentElement.classList.contains("vsc-skip-opening")) {
      openingOverlay.remove();
    } else {
      const openingMs = Math.max(400, Number(window.CONJUGATE_OPENING_MS || 2000));
      openingOverlay.style.setProperty("--splash-ms", `${openingMs}ms`);
      setTimeout(() => openingOverlay.remove(), openingMs + 40);
    }
  }

  const form = document.getElementById("start-form");
  const btn = document.getElementById("start-btn");
  const errorEl = document.getElementById("start-error");

  if (!form) return;

  function showError(message) {
    errorEl.textContent = message;
    errorEl.classList.remove("hidden");
  }

  function selectedTenses() {
    return Array.from(form.querySelectorAll('input[name="tense"]:checked')).map((el) => el.value);
  }

  function selectedPersonFilter() {
    const checked = form.querySelector('input[name="person_filter"]:checked');
    return checked ? checked.value : "all";
  }

  function selectedCount() {
    const select = form.querySelector('select[name="count"]');
    return parseInt(select.value, 10);
  }

  function selectedCategories() {
    return Array.from(form.querySelectorAll('input[name="category"]:checked')).map((el) => el.value);
  }

  async function startSession({ categories, tenses, count, prioritizeWeak, label }) {
    errorEl.classList.add("hidden");
    if (!categories.length) {
      showError("出題カテゴリを1つ以上選んでください。");
      return;
    }
    if (!tenses.length) {
      showError("出題する文型を1つ以上選んでください。");
      return;
    }

    const original = btn.textContent;
    btn.disabled = true;
    btn.textContent = "準備中...";

    try {
      const res = await fetch("/conjugate/api/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          categories,
          tenses,
          count,
          prioritize_weak_verbs: prioritizeWeak,
          person_filter: selectedPersonFilter(),
        }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || "セッションの作成に失敗しました。");
      if (window.vscNavigate) window.vscNavigate(`/conjugate/session/${data.session_id}`);
      else window.location.href = `/conjugate/session/${data.session_id}`;
    } catch (err) {
      showError(err.message);
      btn.disabled = false;
      btn.textContent = label || original || "今日の練習を始める";
    }
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    await startSession({
      categories: selectedCategories(),
      tenses: selectedTenses(),
      count: selectedCount(),
      prioritizeWeak: form.querySelector('input[name="prioritize_weak_verbs"]').checked,
      label: "今日の練習を始める",
    });
  });

  document.querySelectorAll("[data-start]").forEach((el) => {
    el.addEventListener("click", async () => {
      const mode = el.dataset.start;
      const tenses = selectedTenses();
      const count = selectedCount();
      if (mode === "review") {
        await startSession({
          categories: selectedCategories(),
          tenses,
          count,
          prioritizeWeak: true,
          label: "今日の練習を始める",
        });
        return;
      }
      if (mode === "motion") {
        await startSession({
          categories: ["motion_daily"],
          tenses,
          count,
          prioritizeWeak: false,
          label: "今日の練習を始める",
        });
        return;
      }
      if (mode === "category") {
        await startSession({
          categories: [el.dataset.category],
          tenses,
          count,
          prioritizeWeak: false,
          label: "今日の練習を始める",
        });
      }
    });
  });

  async function startVocab({ direction, button }) {
    errorEl.classList.add("hidden");
    button.disabled = true;
    try {
      const res = await fetch("/conjugate/api/vocab", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ direction, count: 10 }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || "語彙クイズの開始に失敗しました。");
      if (window.vscNavigate) window.vscNavigate(`/conjugate/vocab/${data.session_id}`);
      else window.location.href = `/conjugate/vocab/${data.session_id}`;
    } catch (err) {
      showError(err.message);
      button.disabled = false;
    }
  }

  document.querySelectorAll("[data-vocab-direction]").forEach((el) => {
    el.addEventListener("click", async () => {
      await startVocab({ direction: el.dataset.vocabDirection, button: el });
    });
  });

  const progressState = Object.assign(
    {
      practice_dates: [],
      guardian_dates: [],
      daily_attempts: {},
      daily_goal: 0,
      total_attempts: 0,
      verbs: [],
      vocab_verbs: [],
      conjugation_threshold: 5,
      vocab_threshold: 5,
      vocab_mastered_ja_to_es: 0,
      vocab_mastered_es_to_ja: 0,
    },
    window.CONJUGATE_PROGRESS || {}
  );

  const modal = document.getElementById("stat-modal");
  const modalTitle = document.getElementById("stat-modal-title");
  const modalBody = document.getElementById("stat-modal-body");
  const modalSheet = modal ? modal.querySelector(".vsc-modal-sheet") : null;
  const WEEKDAYS = ["日", "月", "火", "水", "木", "金", "土"];
  let calendarCursor = new Date();
  calendarCursor.setDate(1);
  let modalAnchor = null;

  if (modal && modal.parentElement !== document.body) {
    document.body.appendChild(modal);
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function isoDay(year, month, day) {
    const mm = String(month + 1).padStart(2, "0");
    const dd = String(day).padStart(2, "0");
    return `${year}-${mm}-${dd}`;
  }

  function todayIso() {
    const now = new Date();
    return isoDay(now.getFullYear(), now.getMonth(), now.getDate());
  }

  function renderCalendarHtml(markForDate) {
    const year = calendarCursor.getFullYear();
    const month = calendarCursor.getMonth();
    const firstDow = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const today = todayIso();
    let cells = "";
    for (let i = 0; i < firstDow; i += 1) {
      cells += '<div class="vsc-cal-cell is-empty"></div>';
    }
    for (let day = 1; day <= daysInMonth; day += 1) {
      const iso = isoDay(year, month, day);
      const mark = markForDate(iso) || {};
      const todayClass = iso === today ? " is-today" : "";
      const guardianClass = mark.guardian ? " is-guardian-day" : "";
      const markClass = mark.guardian ? "vsc-cal-mark vsc-cal-mark-guardian" : "vsc-cal-mark";
      cells += `<div class="vsc-cal-cell${todayClass}${guardianClass}">
        <span>${day}</span>
        ${mark.emoji ? `<span class="${markClass}" title="${mark.guardian ? "Guardiánが守った日" : ""}">${mark.emoji}</span>` : ""}
        ${mark.count ? `<span class="vsc-cal-count">${escapeHtml(mark.count)}</span>` : ""}
      </div>`;
    }
    const dow = WEEKDAYS.map((d) => `<div class="vsc-cal-dow">${d}</div>`).join("");
    return `<div class="vsc-cal-nav">
      <button type="button" data-cal-shift="-1" aria-label="前の月">‹</button>
      <div class="vsc-cal-nav-label">${year}年${month + 1}月</div>
      <button type="button" data-cal-shift="1" aria-label="次の月">›</button>
    </div>
    <div class="vsc-cal-grid">${dow}${cells}</div>`;
  }

  function practicedSet() {
    return new Set(progressState.practice_dates || []);
  }

  function guardianSet() {
    return new Set(progressState.guardian_dates || []);
  }

  function renderStreakBody() {
    const dates = practicedSet();
    const guardianDates = guardianSet();
    modalBody.innerHTML = `
      <p class="vsc-modal-lead">練習した日に🔥、Guardiánが守ってくれた日に🛡️がつきます。現在 ${progressState.current_streak || 0} 日連続、最長 ${progressState.longest_streak || 0} 日。</p>
      ${renderCalendarHtml((iso) => {
        if (dates.has(iso)) return { emoji: "🔥" };
        if (guardianDates.has(iso)) return { emoji: "🛡️", guardian: true };
        return null;
      })}
    `;
  }

  function renderTotalBody() {
    const goal = Number(progressState.daily_goal || 0);
    const attempts = progressState.daily_attempts || {};
    const calendar = goal
      ? renderCalendarHtml((iso) => {
          const count = Number(attempts[iso] || 0);
          if (count >= goal) return { emoji: "✅", count: `${count}` };
          if (count > 0) return { count: `${count}` };
          return null;
        })
      : '<p class="vsc-modal-lead">目標を保存すると、達成した日がカレンダーに表示されます。</p>';
    modalBody.innerHTML = `
      <div class="vsc-modal-total">これまでの累計 ${progressState.total_attempts || 0} 問</div>
      <form class="vsc-goal-form" id="daily-goal-form">
        <label for="daily-goal-input">1日の累計目標</label>
        <input id="daily-goal-input" type="number" min="1" max="100" value="${goal || 10}">
        <span>問</span>
        <button type="submit">保存</button>
        <p class="vsc-goal-msg" id="daily-goal-msg" style="color: var(--text-secondary);">${
          goal ? `いまの目標は1日 ${goal} 問です。達成した日に ✅ がつきます。` : "例: 10問。保存後にカレンダーが表示されます。"
        }</p>
      </form>
      ${calendar}
    `;
  }

  function renderMasterList(rows, threshold, emptyText, direction) {
    const studied = (rows || [])
      .map((row) => {
        const side = direction ? row[direction] || {} : row;
        const rawCount = direction ? side.correct_count : row.correct_count;
        const count = Number(rawCount);
        const resolvedCount = Number.isFinite(count) ? count : 0;
        const missRaw = direction ? side.miss_count : row.miss_count;
        const missCount = Number(missRaw);
        const resolvedMiss = Number.isFinite(missCount) ? missCount : 0;
        const mastered = direction
          ? Boolean(side.mastered) || resolvedCount >= threshold
          : Boolean(row.mastered);
        return { ...row, correct_count: resolvedCount, miss_count: resolvedMiss, mastered };
      })
      .filter((row) => {
        if (direction) {
          return Boolean(row.mastered) || Number(row.correct_count || 0) > 0 || Number(row.miss_count || 0) > 0;
        }
        const persons = row.persons || {};
        const tuCount = Number((persons.tu || {}).consecutive_correct || 0);
        const elCount = Number((persons.el_ella_usted || {}).consecutive_correct || 0);
        const tuMastered = Boolean((persons.tu || {}).mastered);
        const elMastered = Boolean((persons.el_ella_usted || {}).mastered);
        return tuMastered || elMastered || tuCount > 0 || elCount > 0 || tenseMissTotal(row) > 0 || Number(row.correct_count || 0) > 0;
      })
      .sort((a, b) => {
        if (direction) {
          return (
            Number(b.miss_count) - Number(a.miss_count) ||
            Number(b.mastered) - Number(a.mastered) ||
            Number(b.correct_count) - Number(a.correct_count) ||
            String(a.infinitive).localeCompare(String(b.infinitive))
          );
        }
        return (
          tenseMissTotal(b) - tenseMissTotal(a) ||
          Number(b.correct_count) - Number(a.correct_count) ||
          String(a.infinitive).localeCompare(String(b.infinitive))
        );
      });
    if (!studied.length) {
      return `<p class="vsc-master-empty">${escapeHtml(emptyText)}</p>`;
    }
    return `<div class="vsc-master-list">${studied
      .map((row) => {
        const count = Number(row.correct_count || 0);
        const missCount = Number(row.miss_count || 0);
        const mastered = Boolean(row.mastered);
        const isWeak = Boolean(direction) && missCount >= 2;
        const countLabel = direction
          ? `${count}/${threshold}${mastered ? " ✓" : ""}`
          : (row.person_badge || `${count}/${threshold}`);
        const missHtml = direction
          ? `<div class="vsc-master-miss">誤 ${missCount}</div>`
          : tenseMissHtml(row);
        return `<article class="vsc-master-item${mastered ? " is-mastered" : ""}${isWeak ? " is-weak" : ""}">
          <div class="vsc-master-name">${escapeHtml(row.infinitive)}</div>
          <div class="vsc-master-count">${escapeHtml(countLabel)}</div>
          <div class="vsc-master-meaning">${escapeHtml(row.meaning_ja)}</div>
          ${missHtml}
        </article>`;
      })
      .join("")}</div>`;
  }

  function tenseMissTotal(row) {
    return (row.tense_misses || []).reduce((sum, item) => sum + Number(item.miss_count || 0), 0);
  }

  function tenseMissHtml(row) {
    const alertOver = Number(progressState.miss_alert_over || 5);
    const misses = row.tense_misses || [];
    if (!misses.length) return "";
    return `<div class="vsc-tense-misses">${misses
      .map((item) => {
        const count = Number(item.miss_count || 0);
        const hot = Boolean(item.alert) || count > alertOver;
        return `<span class="vsc-tense-miss${hot ? " is-alert" : ""}">${escapeHtml(item.label)} 誤${count}</span>`;
      })
      .join("")}</div>`;
  }

  function renderMasteredBody() {
    const threshold = Number(progressState.conjugation_threshold || 5);
    const total = progressState.total_verbs || 0;
    const tuCount = progressState.mastered_tu_count || 0;
    const elCount = progressState.mastered_el_count || 0;
    modalBody.innerHTML = `
      <p class="vsc-modal-lead">tú形とél/ella/usted形は別々に数えます。それぞれ${threshold}回連続正解で、その人称が習得です。間違えるとその人称の連続カウントだけがゼロに戻ります。間違い回数は現在・点過去・線過去で分け、${Number(progressState.miss_alert_over || 5) + 1}回以上は赤く表示します。</p>
      <p class="vsc-master-col-meta">tú ${tuCount}/${total} · él ${elCount}/${total}</p>
      ${renderMasterList(progressState.verbs, threshold, "まだ記録がありません。練習を始めるとここに表示されます。")}
    `;
  }

  function renderVocabBody() {
    const threshold = Number(progressState.vocab_threshold || 5);
    const total = progressState.total_vocab || 0;
    const jaCount = progressState.vocab_mastered_ja_to_es || 0;
    const esCount = progressState.vocab_mastered_es_to_ja || 0;
    modalBody.innerHTML = `
      <p class="vsc-modal-lead">左右の出題方向ごとに${threshold}回連続正解すると暗記マスターです。間違えると連続カウントはゼロに戻ります。累計の間違い回数も出し、2回以上間違えた単語は赤で表示します。</p>
      <div class="vsc-master-split">
        <section>
          <h3 class="vsc-master-col-title">日本語 → スペイン語</h3>
          <p class="vsc-master-col-meta">${jaCount}/${total}語 暗記マスター</p>
          ${renderMasterList(progressState.vocab_verbs, threshold, "まだ記録がありません。", "ja_to_es")}
        </section>
        <section>
          <h3 class="vsc-master-col-title">スペイン語 → 日本語</h3>
          <p class="vsc-master-col-meta">${esCount}/${total}語 暗記マスター</p>
          ${renderMasterList(progressState.vocab_verbs, threshold, "まだ記録がありません。", "es_to_ja")}
        </section>
      </div>
    `;
  }

  const renderers = {
    streak: { title: "ストリーク", render: renderStreakBody },
    total: { title: "累計問題数", render: renderTotalBody },
    mastered: { title: "習得済み", render: renderMasteredBody },
    vocab: { title: "暗記マスターした単語", render: renderVocabBody },
  };

  let activeStat = "streak";

  function renderActive() {
    const spec = renderers[activeStat];
    if (!spec) return;
    modalTitle.textContent = spec.title;
    spec.render();
  }

  function viewportSize() {
    const vp = window.visualViewport;
    return {
      width: vp ? vp.width : window.innerWidth,
      height: vp ? vp.height : window.innerHeight,
      offsetLeft: vp ? vp.offsetLeft : 0,
      offsetTop: vp ? vp.offsetTop : 0,
    };
  }

  function positionSheet(anchor) {
    if (!modalSheet) return;
    const margin = 12;
    const navSpace = 96;
    const vp = viewportSize();
    const maxWidth = Math.min(560, vp.width - margin * 2);
    const maxHeight = Math.max(180, vp.height - navSpace - margin * 2);
    modalSheet.style.width = `${maxWidth}px`;
    modalSheet.style.maxHeight = `${maxHeight}px`;
    modalSheet.style.left = `${vp.offsetLeft + margin}px`;
    modalSheet.style.top = `${vp.offsetTop + margin}px`;

    const sheetW = modalSheet.offsetWidth;
    const sheetH = modalSheet.offsetHeight;
    const rect = anchor && anchor.getBoundingClientRect
      ? anchor.getBoundingClientRect()
      : { left: vp.width / 2, width: 0, top: 80, bottom: 80 };

    let top = rect.bottom + 8;
    const fitsBelow = top + sheetH <= vp.height - navSpace - margin;
    const fitsAbove = rect.top - 8 - sheetH >= margin;
    if (!fitsBelow && fitsAbove) {
      top = rect.top - 8 - sheetH;
    } else if (!fitsBelow) {
      top = Math.max(margin, vp.height - navSpace - margin - sheetH);
    }
    top = Math.min(Math.max(margin, top), Math.max(margin, vp.height - navSpace - margin - sheetH));

    let left = rect.left + rect.width / 2 - sheetW / 2;
    left = Math.min(Math.max(margin, left), Math.max(margin, vp.width - sheetW - margin));

    modalSheet.style.left = `${Math.round(vp.offsetLeft + left)}px`;
    modalSheet.style.top = `${Math.round(vp.offsetTop + top)}px`;
  }

  function schedulePosition() {
    requestAnimationFrame(() => {
      positionSheet(modalAnchor);
      requestAnimationFrame(() => positionSheet(modalAnchor));
    });
  }

  function openStat(name, anchor) {
    if (!renderers[name] || !modal) return;
    activeStat = name;
    modalAnchor = anchor || null;
    calendarCursor = new Date();
    calendarCursor.setDate(1);
    renderActive();
    modal.classList.remove("hidden");
    document.body.classList.add("vsc-modal-open");
    schedulePosition();
  }

  function closeStat() {
    if (!modal) return;
    modal.classList.add("hidden");
    document.body.classList.remove("vsc-modal-open");
    modalAnchor = null;
  }

  document.querySelectorAll("[data-open-stat]").forEach((el) => {
    el.addEventListener("click", () => openStat(el.dataset.openStat, el));
  });
  document.querySelectorAll("[data-close-stat]").forEach((el) => {
    el.addEventListener("click", closeStat);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal && !modal.classList.contains("hidden")) closeStat();
  });

  if (modalBody) {
    modalBody.addEventListener("click", (e) => {
      const shiftBtn = e.target.closest("[data-cal-shift]");
      if (!shiftBtn) return;
      const shift = Number(shiftBtn.dataset.calShift || 0);
      calendarCursor.setMonth(calendarCursor.getMonth() + shift);
      renderActive();
      schedulePosition();
    });
    modalBody.addEventListener("submit", async (e) => {
      const formEl = e.target.closest("#daily-goal-form");
      if (!formEl) return;
      e.preventDefault();
      const input = document.getElementById("daily-goal-input");
      const msg = document.getElementById("daily-goal-msg");
      const goal = parseInt(input && input.value, 10);
      if (!Number.isFinite(goal) || goal < 1 || goal > 100) {
        if (msg) {
          msg.textContent = "1〜100問で入力してください。";
          msg.style.color = "var(--danger-text)";
        }
        return;
      }
      try {
        const res = await fetch("/conjugate/api/progress/daily-goal", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ daily_goal: goal }),
        });
        const data = await res.json();
        if (!res.ok || !data.ok) throw new Error(data.error || "保存に失敗しました。");
        Object.assign(progressState, data.progress || {});
        progressState.daily_goal = goal;
        const totalEl = document.querySelector("[data-total-attempts] [data-count-up]") || document.querySelector("[data-total-attempts]");
        if (totalEl && window.vscCountUp) window.vscCountUp(totalEl, progressState.total_attempts || 0);
        else if (totalEl) totalEl.textContent = String(progressState.total_attempts || 0);
        renderTotalBody();
        schedulePosition();
      } catch (err) {
        if (msg) {
          msg.textContent = err.message;
          msg.style.color = "var(--danger-text)";
        }
      }
    });
  }

  window.addEventListener("resize", () => {
    if (modal && !modal.classList.contains("hidden")) schedulePosition();
  });
  if (window.visualViewport) {
    window.visualViewport.addEventListener("resize", () => {
      if (modal && !modal.classList.contains("hidden")) schedulePosition();
    });
  }
})();
