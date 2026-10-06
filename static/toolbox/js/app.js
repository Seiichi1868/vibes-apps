(function () {
  const csrf = window.TOOLBOX_CSRF || "";

  function jsonHeaders() {
    return {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrf,
    };
  }

  window.toolboxFetch = function (url, options) {
    const next = Object.assign({ credentials: "same-origin" }, options || {});
    next.headers = Object.assign({}, jsonHeaders(), next.headers || {});
    return fetch(url, next).then(async (res) => {
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const err = new Error(data.error || data.message || "通信に失敗しました。もう一度試してください。");
        err.status = res.status;
        err.data = data;
        throw err;
      }
      return data;
    });
  };

  const toggle = document.getElementById("tb-user-toggle");
  const menu = document.getElementById("tb-user-menu");
  if (toggle && menu) {
    const user = toggle.closest(".tb-user");
    const setOpen = (open) => toggle.setAttribute("aria-expanded", open ? "true" : "false");
    if (user) {
      user.addEventListener("mouseenter", () => setOpen(true));
      user.addEventListener("mouseleave", () => setOpen(false));
      user.addEventListener("focusin", () => setOpen(true));
      user.addEventListener("focusout", () => setOpen(false));
      toggle.addEventListener("click", () => {
        const open = user.classList.toggle("is-open");
        setOpen(open);
      });
    }
  }

  const opening = document.getElementById("tb-opening");
  if (opening && document.documentElement.classList.contains("tb-skip-opening")) {
    opening.remove();
    document.dispatchEvent(new CustomEvent("toolbox:opening-done"));
  } else if (opening) {
    window.setTimeout(() => {
      opening.classList.add("is-hide");
      document.dispatchEvent(new CustomEvent("toolbox:opening-done"));
      window.setTimeout(() => opening.remove(), 320);
    }, 1950);
  }

  const blank = document.getElementById("tb-blank");
  const blankBtn = document.getElementById("tb-blank-btn");
  function isBlank() {
    return !!(blank && !blank.hidden);
  }
  function setBlank(on) {
    if (!blank) return;
    blank.hidden = !on;
    if (on && document.activeElement && document.activeElement.blur) {
      document.activeElement.blur();
    }
    if (window.ToolboxDisplay && typeof window.ToolboxDisplay.syncBlank === "function") {
      window.ToolboxDisplay.syncBlank(!!on);
    }
  }
  function toggleBlank() {
    if (!blank) return;
    setBlank(blank.hidden);
  }
  function clearBlank(ev) {
    if (!isBlank()) return false;
    if (ev) {
      ev.preventDefault();
      ev.stopImmediatePropagation();
    }
    setBlank(false);
    return true;
  }
  blankBtn?.addEventListener("click", toggleBlank);
  blank?.addEventListener("click", (ev) => {
    ev.preventDefault();
    setBlank(false);
  });
  window.toolboxToggleBlank = toggleBlank;
  window.toolboxSetBlank = setBlank;
  window.toolboxIsBlank = isBlank;

  document.addEventListener("keydown", (ev) => {
    if (ev.target && /INPUT|TEXTAREA|SELECT/.test(ev.target.tagName)) return;
    if (isBlank() && (ev.key === "Enter" || ev.key === " " || ev.key === "Escape")) {
      clearBlank(ev);
      return;
    }
    if (ev.key === "b" || ev.key === "B") {
      ev.preventDefault();
      toggleBlank();
    }
  });

  document.querySelectorAll(".tb-star").forEach((btn) => {
    btn.addEventListener("click", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      const id = btn.dataset.tool;
      window.toolboxFetch(`/toolbox/api/favorites/${id}`, { method: "POST", body: "{}" })
        .then((data) => btn.classList.toggle("is-on", data.favorite))
        .catch((err) => alert(err.message));
    });
  });

  const tabs = document.querySelectorAll(".tb-tab");
  const cards = document.querySelectorAll("#tb-all-tools .tb-card-tool");
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      tabs.forEach((t) => t.classList.remove("is-active"));
      tab.classList.add("is-active");
      const scene = tab.dataset.scene;
      cards.forEach((card) => {
        card.hidden = scene !== "all" && card.dataset.scene !== scene;
      });
    });
  });
})();
