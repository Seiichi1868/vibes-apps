(function () {
  const display = {
    on: false,
    blank: false,
    onNext: null,
    onPrev: null,
    bar: null,
    hideTimer: 0,
  };

  function ensureBar() {
    if (display.bar) return display.bar;
    const bar = document.createElement("div");
    bar.className = "tb-display-bar";
    bar.hidden = true;
    bar.innerHTML = `
      <button type="button" data-act="prev" aria-label="前へ">←</button>
      <button type="button" data-act="next" aria-label="次へ">→</button>
      <button type="button" data-act="blank" aria-label="Blank">B</button>
      <button type="button" data-act="full" aria-label="全画面">F</button>
      <button type="button" data-act="exit" aria-label="終了">Esc</button>
    `;
    bar.addEventListener("click", (ev) => {
      const act = ev.target.closest("button")?.dataset.act;
      if (act === "prev") display.onPrev && display.onPrev();
      if (act === "next") display.onNext && display.onNext();
      if (act === "blank") toggleBlank();
      if (act === "full") toggleFullscreen();
      if (act === "exit") exit();
      poke();
    });
    document.body.appendChild(bar);
    display.bar = bar;
    return bar;
  }

  function poke() {
    const bar = ensureBar();
    bar.classList.add("is-hot");
    clearTimeout(display.hideTimer);
    display.hideTimer = setTimeout(() => bar.classList.remove("is-hot"), 2400);
  }

  function enter() {
    display.on = true;
    document.body.classList.add("tb-display-on");
    const bar = ensureBar();
    bar.hidden = false;
    poke();
    if (document.documentElement.requestFullscreen) {
      document.documentElement.requestFullscreen().catch(() => {});
    }
  }

  function exit() {
    display.on = false;
    document.body.classList.remove("tb-display-on");
    if (display.bar) display.bar.hidden = true;
    if (document.fullscreenElement && document.exitFullscreen) {
      document.exitFullscreen().catch(() => {});
    }
    window.toolboxSetBlank && window.toolboxSetBlank(false);
    display.blank = false;
  }

  function toggleFullscreen() {
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => {});
    } else if (document.documentElement.requestFullscreen) {
      document.documentElement.requestFullscreen().catch(() => {});
    }
  }

  function syncBlank(on) {
    display.blank = !!on;
  }

  function toggleBlank() {
    syncBlank(!(window.toolboxIsBlank ? window.toolboxIsBlank() : display.blank));
    window.toolboxSetBlank && window.toolboxSetBlank(display.blank);
  }

  function init(options) {
    display.onNext = options.onNext || null;
    display.onPrev = options.onPrev || null;
    document.querySelectorAll("[data-display-enter]").forEach((btn) => {
      btn.addEventListener("click", enter);
    });
    document.addEventListener("keydown", (ev) => {
      if (ev.target && /INPUT|TEXTAREA|SELECT/.test(ev.target.tagName)) return;
      if (window.toolboxIsBlank && window.toolboxIsBlank()) return;
      if (ev.key === "f" || ev.key === "F") {
        ev.preventDefault();
        if (display.on) toggleFullscreen();
        else enter();
      }
      if (ev.key === "Escape") {
        if (display.on) exit();
      }
      if (!display.on) return;
      if (ev.key === " " || ev.key === "Enter" || ev.key === "ArrowRight" || ev.key === "ArrowDown") {
        ev.preventDefault();
        display.onNext && display.onNext();
      }
      if (ev.key === "ArrowLeft" || ev.key === "ArrowUp") {
        ev.preventDefault();
        display.onPrev && display.onPrev();
      }
    });
    const root = document.querySelector("[data-display-root]");
    if (root) {
      root.addEventListener("click", (ev) => {
        if (!display.on) return;
        if (window.toolboxIsBlank && window.toolboxIsBlank()) return;
        if (ev.target.closest("button, a, input, select, textarea, label")) return;
        display.onNext && display.onNext();
      });
    }
    document.addEventListener("mousemove", () => {
      if (display.on) poke();
    });
    document.addEventListener("touchstart", () => {
      if (display.on) poke();
    }, { passive: true });
  }

  window.ToolboxDisplay = {
    init,
    enter,
    exit,
    toggleBlank,
    syncBlank,
    isOn() { return display.on; },
  };
})();
