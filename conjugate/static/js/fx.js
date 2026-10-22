(() => {
  const COLORS = ["#7CB342", "#689F38", "#C8E6A0", "#FFFFFF", "#F4F7EE", "#D7EFC3"];
  const PARTICLE_COUNT = 28;
  const CONFETTI_MS = 1800;
  const COUNT_MS = 600;
  const LEAVE_MS = 520;
  const GUARDIAN_TOAST_MS = 2600;
  const GUARDIAN_TOAST_FADE_MS = 450;

  function prefersReducedMotion() {
    return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function easeOutCubic(t) {
    return 1 - (1 - t) ** 3;
  }

  function celebrate() {
    if (prefersReducedMotion()) return;
    const root = document.createElement("div");
    root.className = "vsc-confetti";
    root.setAttribute("aria-hidden", "true");
    const fragment = document.createDocumentFragment();
    for (let i = 0; i < PARTICLE_COUNT; i += 1) {
      const piece = document.createElement("span");
      piece.className = "vsc-confetti-piece";
      const x = 8 + Math.random() * 84;
      const delay = Math.random() * 220;
      const duration = 1200 + Math.random() * 600;
      const drift = (Math.random() - 0.5) * 120;
      const rot = 180 + Math.random() * 540;
      const w = 5 + Math.random() * 5;
      const h = 8 + Math.random() * 7;
      piece.style.left = `${x}vw`;
      piece.style.width = `${w}px`;
      piece.style.height = `${h}px`;
      piece.style.background = COLORS[i % COLORS.length];
      piece.style.animationDelay = `${delay}ms`;
      piece.style.animationDuration = `${duration}ms`;
      piece.style.setProperty("--vsc-drift", `${drift}px`);
      piece.style.setProperty("--vsc-rot", `${rot}deg`);
      fragment.appendChild(piece);
    }
    root.appendChild(fragment);
    document.body.appendChild(root);
    window.setTimeout(() => root.remove(), CONFETTI_MS + 80);
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  let guardianToastEl = null;
  let guardianToastHideTimer = null;
  let guardianToastRemoveTimer = null;

  function celebrateGuardian(progress) {
    if (window.SoundFX) window.SoundFX.guardian();
    if (prefersReducedMotion()) return;
    if (guardianToastHideTimer) window.clearTimeout(guardianToastHideTimer);
    if (guardianToastRemoveTimer) window.clearTimeout(guardianToastRemoveTimer);
    if (guardianToastEl) guardianToastEl.remove();

    const titleJa = progress.guardian_title_ja || "見習い";
    const quoteJa = progress.guardian_quote_ja || "";
    const color = progress.guardian_color || "#8BC34A";

    const root = document.createElement("div");
    root.className = "vsc-guardian-toast";
    root.setAttribute("role", "status");
    root.setAttribute("aria-live", "polite");
    root.innerHTML = `
      <span class="vsc-guardian-toast-icon" style="color:${escapeHtml(color)};">🛡️</span>
      <div class="vsc-guardian-toast-copy">
        <div class="vsc-guardian-toast-title">Guardián（${escapeHtml(titleJa)}）がストリークを守った！</div>
        ${quoteJa ? `<div class="vsc-guardian-toast-quote">「${escapeHtml(quoteJa)}」</div>` : ""}
      </div>
    `;
    document.body.appendChild(root);
    guardianToastEl = root;
    requestAnimationFrame(() => {
      requestAnimationFrame(() => root.classList.add("is-visible"));
    });
    guardianToastHideTimer = window.setTimeout(() => {
      root.classList.remove("is-visible");
      guardianToastRemoveTimer = window.setTimeout(() => {
        root.remove();
        if (guardianToastEl === root) guardianToastEl = null;
      }, GUARDIAN_TOAST_FADE_MS);
    }, GUARDIAN_TOAST_MS);
  }

  function isoFromParts(year, monthIndex, day) {
    return `${year}-${String(monthIndex + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
  }

  function shiftIso(iso, deltaDays) {
    const [year, month, day] = String(iso).split("-").map(Number);
    const dt = new Date(Date.UTC(year, month - 1, day + deltaDays));
    return dt.toISOString().slice(0, 10);
  }

  function jstNowParts() {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: "Asia/Tokyo",
      year: "numeric",
      month: "numeric",
      day: "numeric",
      weekday: "short",
    }).formatToParts(new Date());
    const get = (type) => parts.find((p) => p.type === type)?.value;
    const weekdayMap = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
    return {
      year: Number(get("year")),
      monthIndex: Number(get("month")) - 1,
      day: Number(get("day")),
      weekday: weekdayMap[get("weekday")] ?? 0,
    };
  }

  function weekDayStates(progress, streak) {
    const labels = ["月", "火", "水", "木", "金", "土", "日"];
    const practiced = new Set((progress && progress.practice_dates) || []);
    if (practiced.size) {
      const now = jstNowParts();
      const todayIso = isoFromParts(now.year, now.monthIndex, now.day);
      const mondayOffset = now.weekday === 0 ? -6 : 1 - now.weekday;
      const mondayIso = shiftIso(todayIso, mondayOffset);
      return labels.map((label, i) => {
        const iso = shiftIso(mondayIso, i);
        const done = practiced.has(iso) || iso === todayIso;
        return { label, done, isToday: iso === todayIso };
      });
    }
    const count = Number(streak) || 0;
    const filledCount = count > 0 && count % 7 === 0 ? 7 : count % 7;
    return labels.map((label, i) => {
      const done = i < filledCount;
      return { label, done, isToday: done && i === filledCount - 1 };
    });
  }

  let celebrationEl = null;
  let celebrationOnKey = null;

  function showStreakCelebration(streak, previousStreak = null, message = "今日の練習、いいスタート！", options = {}) {
    if (window.SoundFX) window.SoundFX.streakUpdate();
    const to = Math.max(0, Number(streak) || 0);
    const from = previousStreak == null ? Math.max(to - 1, 0) : Math.max(0, Number(previousStreak) || 0);
    const progress = (options && options.progress) || {};
    const reduced = prefersReducedMotion();
    const PARTICLE_COUNT = 22;

    if (celebrationEl) celebrationEl.remove();
    if (celebrationOnKey) document.removeEventListener("keydown", celebrationOnKey);
    celebrationOnKey = null;

    const particles = reduced
      ? []
      : Array.from({ length: PARTICLE_COUNT }, (_, i) => {
          const angle = (i / PARTICLE_COUNT) * Math.PI * 2;
          const distance = 90 + ((i * 37) % 70);
          return {
            x: Math.cos(angle) * distance,
            y: Math.sin(angle) * distance,
            delay: (i % 6) * 60,
            size: 6 + ((i * 13) % 9),
            tone: i % 3,
          };
        });

    const particlesHtml = particles
      .map(
        (p) =>
          `<span class="celebrate-particle celebrate-particle--${p.tone}" style="width:${p.size}px;height:${p.size}px;animation-delay:${p.delay}ms;--px:${p.x}px;--py:${p.y}px;"></span>`
      )
      .join("");

    const daysHtml = weekDayStates(progress, to)
      .map((day) => {
        const classes = ["celebrate-day"];
        if (day.done) classes.push("done");
        if (day.isToday && day.done) classes.push("today");
        return `<div class="${classes.join(" ")}">${day.done ? "★" : day.label}</div>`;
      })
      .join("");

    const backdrop = document.createElement("div");
    backdrop.className = "celebrate-backdrop";
    backdrop.setAttribute("role", "dialog");
    backdrop.setAttribute("aria-modal", "true");
    backdrop.setAttribute("aria-labelledby", "celebrate-message");
    backdrop.innerHTML = `
      <div class="celebrate-card">
        <div class="celebrate-flame-wrap">
          <div class="celebrate-flame-stage">
            <span class="celebrate-glow"></span>
            <span class="celebrate-ring"></span>
            <span class="celebrate-ring celebrate-ring--delay"></span>
            <span class="celebrate-flame-badge">
              <svg class="celebrate-flame-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true">
                <path d="M12 2c1 3-2 4-2 7a4 4 0 0 0 8 0c0-1-.5-2-1-3 2 1 4 4 4 7a7 7 0 1 1-14 0c0-4 3-7 5-11z"/>
              </svg>
            </span>
            ${particlesHtml}
          </div>
        </div>
        <p class="celebrate-eyebrow">Streak updated</p>
        <div class="celebrate-number-row">
          <span class="celebrate-number" id="celebrate-number">${reduced ? to : from}</span>
          <span class="celebrate-unit">日</span>
        </div>
        <p class="celebrate-message" id="celebrate-message">${escapeHtml(message)}</p>
        <p class="celebrate-submessage">連続記録が伸びました。明日も続けましょう。</p>
        <div class="celebrate-week">${daysHtml}</div>
        <button type="button" class="celebrate-button" id="celebrate-close-btn">続ける</button>
      </div>
    `;
    document.body.appendChild(backdrop);
    document.body.classList.add("celebrate-open");
    celebrationEl = backdrop;

    const numberEl = backdrop.querySelector("#celebrate-number");
    const closeBtn = backdrop.querySelector("#celebrate-close-btn");
    const previousFocus = document.activeElement;
    if (closeBtn && closeBtn.focus) closeBtn.focus();

    if (!reduced && numberEl && from !== to) {
      const start = performance.now();
      const delay = 520;
      const duration = 700;
      const tick = (now) => {
        if (celebrationEl !== backdrop) return;
        const t = Math.min(Math.max(now - start - delay, 0) / duration, 1);
        numberEl.textContent = String(Math.round(from + (to - from) * easeOutCubic(t)));
        if (t < 1) {
          requestAnimationFrame(tick);
        } else {
          numberEl.classList.add("pop");
        }
      };
      requestAnimationFrame(tick);
    } else if (numberEl) {
      numberEl.textContent = String(to);
    }

    function close() {
      if (window.SoundFX && window.SoundFX.stop) window.SoundFX.stop("streak");
      if (celebrationEl === backdrop) celebrationEl = null;
      if (celebrationOnKey === onKey) celebrationOnKey = null;
      backdrop.remove();
      document.body.classList.remove("celebrate-open");
      document.removeEventListener("keydown", onKey);
      if (previousFocus && previousFocus.focus) {
        try {
          previousFocus.focus();
        } catch (_) {
          /* ignore */
        }
      }
    }
    function onKey(e) {
      if (e.key === "Escape") close();
    }
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) close();
    });
    if (closeBtn) closeBtn.addEventListener("click", close);
    celebrationOnKey = onKey;
    document.addEventListener("keydown", onKey);
  }

  function isGradedCorrect(result) {
    if (result.level) return result.level === "correct";
    if (typeof result.correct === "boolean") return result.correct;
    return false;
  }

  function hasGrade(result) {
    return Boolean(result.level) || typeof result.correct === "boolean";
  }

  function celebrateFromResult(result) {
    if (!result) return;
    const progress = result.progress || {};
    const streakUp = Boolean(progress.streak_incremented);
    const guardianUsed = Number(progress.guardian_used || 0) > 0;
    if (window.SoundFX && hasGrade(result)) {
      if (isGradedCorrect(result)) {
        if (!streakUp && !guardianUsed) {
          window.SoundFX.correct();
        }
      } else {
        window.SoundFX.incorrect();
      }
    }
    if (guardianUsed) {
      celebrateGuardian(progress);
    }
    if (result.newly_mastered || progress.newly_mastered) {
      celebrate();
    }
    if (streakUp) {
      const streak = Number(progress.current_streak || 0);
      const broken = Boolean(progress.streak_broken);
      const previous = broken ? 0 : Math.max(streak - 1, 0);
      showStreakCelebration(streak, previous, "今日の練習、いいスタート！", { progress });
    }
  }

  function countUp(el, toValue, duration) {
    if (!el) return;
    const to = Number(toValue);
    if (!Number.isFinite(to)) return;
    if (prefersReducedMotion()) {
      el.textContent = String(to);
      return;
    }
    const from = Number(el.textContent);
    const start = Number.isFinite(from) ? from : 0;
    if (start === to) {
      el.textContent = String(to);
      return;
    }
    const ms = duration || COUNT_MS;
    const begun = performance.now();
    const tick = (now) => {
      const t = Math.min(1, (now - begun) / ms);
      const value = Math.round(start + (to - start) * easeOutCubic(t));
      el.textContent = String(value);
      if (t < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }

  function setProgressRing(el, percent) {
    if (!el) return;
    const value = Math.max(0, Math.min(100, Number(percent) || 0));
    const offset = 100 - value;
    if (prefersReducedMotion()) {
      el.style.transition = "none";
    }
    requestAnimationFrame(() => {
      el.style.strokeDashoffset = String(offset);
    });
  }

  function navigate(url) {
    if (!url) return;
    if (prefersReducedMotion() || document.body.classList.contains("vsc-page-leave")) {
      window.location.href = url;
      return;
    }
    document.body.classList.add("vsc-page-leave");
    window.setTimeout(() => {
      window.location.href = url;
    }, LEAVE_MS);
  }

  function initCountUps() {
    document.querySelectorAll("[data-count-up]").forEach((el) => {
      const to = el.getAttribute("data-count-to");
      countUp(el, to);
    });
  }

  function initProgressRings() {
    document.querySelectorAll("[data-progress-ring]").forEach((el) => {
      setProgressRing(el, el.getAttribute("data-progress-ring"));
    });
  }

  function isInternalConjugateLink(anchor) {
    if (!anchor || !anchor.getAttribute) return false;
    if (anchor.target && anchor.target !== "_self") return false;
    if (anchor.hasAttribute("download")) return false;
    const href = anchor.getAttribute("href");
    if (!href || href.startsWith("#") || href.startsWith("javascript:")) return false;
    let url;
    try {
      url = new URL(anchor.href, window.location.href);
    } catch (_) {
      return false;
    }
    if (url.origin !== window.location.origin) return false;
    if (url.pathname.indexOf("/conjugate") !== 0) return false;
    if (url.pathname === window.location.pathname && url.search === window.location.search) return false;
    return true;
  }

  document.addEventListener("click", (event) => {
    if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const anchor = event.target.closest("a[href]");
    if (!isInternalConjugateLink(anchor)) return;
    event.preventDefault();
    navigate(anchor.href);
  });

  function startVisualFx() {
    initCountUps();
    initProgressRings();
  }

  function scheduleVisualFx() {
    const overlay = document.getElementById("opening-overlay");
    const skip = document.documentElement.classList.contains("vsc-skip-opening");
    if (overlay && !skip) {
      const ms = Math.max(400, Number(window.CONJUGATE_OPENING_MS || 2000));
      window.setTimeout(startVisualFx, ms);
      return;
    }
    startVisualFx();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", scheduleVisualFx);
  } else {
    scheduleVisualFx();
  }

  window.vscCelebrate = celebrate;
  window.vscCelebrateFromResult = celebrateFromResult;
  window.showStreakCelebration = showStreakCelebration;
  window.vscShowStreakCelebration = showStreakCelebration;
  window.vscCountUp = countUp;
  window.vscSetProgressRing = setProgressRing;
  window.vscNavigate = navigate;
})();
