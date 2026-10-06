/* Debate: PWAインストール制御（論題画面専用） */
(function () {
  "use strict";

  const DISMISS_KEY = "debate.pwa.dismissedAt";
  const DISMISS_DAYS = 14;

  const ua = navigator.userAgent || "";
  const isIOS =
    /iPhone|iPad|iPod/i.test(ua) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const isInAppBrowser = /Line\/|FBAN|FBAV|Instagram/i.test(ua);
  const standaloneQuery = window.matchMedia("(display-mode: standalone)");

  const isStandalone = () => standaloneQuery.matches || window.navigator.standalone === true;

  const els = {
    banner: document.getElementById("pwa-install-banner"),
    installBtn: document.getElementById("pwa-install-btn"),
    dismissBtn: document.getElementById("pwa-install-dismiss"),
    iosDialog: document.getElementById("pwa-ios-dialog"),
    iosClose: document.getElementById("pwa-ios-close"),
    menuItem: document.getElementById("pwa-menu-install"),
  };

  let deferredPrompt = null;
  let bannerWanted = false;

  function recentlyDismissed() {
    try {
      const t = Number(localStorage.getItem(DISMISS_KEY) || 0);
      return t && Date.now() - t < DISMISS_DAYS * 86400000;
    } catch (e) {
      return false;
    }
  }
  function rememberDismiss() {
    try {
      localStorage.setItem(DISMISS_KEY, String(Date.now()));
    } catch (e) {}
  }

  function show(el) {
    if (el) el.hidden = false;
  }
  function hide(el) {
    if (el) el.hidden = true;
  }

  function hideAllInstallUI() {
    hide(els.banner);
    hide(els.menuItem);
    if (els.iosDialog && els.iosDialog.open) els.iosDialog.close();
  }

  function syncVisibility() {
    if (isStandalone()) {
      hideAllInstallUI();
      return;
    }
    if (bannerWanted && !recentlyDismissed()) show(els.banner);
    else hide(els.banner);
    if (isIOS || isInAppBrowser || deferredPrompt) show(els.menuItem);
  }

  function openGuide(mode) {
    if (!els.iosDialog) return;
    els.iosDialog.classList.toggle("is-inapp", mode === "inapp");
    els.iosDialog.classList.toggle("is-other", mode === "other");
    if (typeof els.iosDialog.showModal === "function") els.iosDialog.showModal();
  }

  async function runInstall() {
    if (isInAppBrowser) {
      openGuide("inapp");
      return;
    }
    if (isIOS) {
      openGuide("ios");
      return;
    }
    if (!deferredPrompt) {
      openGuide("other");
      return;
    }
    deferredPrompt.prompt();
    const choice = await deferredPrompt.userChoice;
    deferredPrompt = null;
    hide(els.banner);
    bannerWanted = false;
    if (choice.outcome === "dismissed") rememberDismiss();
  }

  function init() {
    if (isStandalone()) {
      hideAllInstallUI();
      return;
    }

    if (els.installBtn) els.installBtn.addEventListener("click", runInstall);
    if (els.menuItem) els.menuItem.addEventListener("click", runInstall);
    if (els.dismissBtn) {
      els.dismissBtn.addEventListener("click", () => {
        rememberDismiss();
        bannerWanted = false;
        hide(els.banner);
      });
    }
    if (els.iosClose) els.iosClose.addEventListener("click", () => els.iosDialog.close());

    if (isIOS || isInAppBrowser) {
      show(els.menuItem);
      bannerWanted = true;
      syncVisibility();
      return;
    }

    window.addEventListener("beforeinstallprompt", (e) => {
      e.preventDefault();
      deferredPrompt = e;
      bannerWanted = !recentlyDismissed();
      syncVisibility();
    });

    window.setTimeout(() => {
      if (deferredPrompt || isStandalone()) return;
      show(els.menuItem);
    }, 1500);
  }

  window.addEventListener("appinstalled", () => {
    deferredPrompt = null;
    bannerWanted = false;
    hideAllInstallUI();
  });
  standaloneQuery.addEventListener("change", (e) => {
    if (e.matches) hideAllInstallUI();
  });

  let started = false;
  function start() {
    if (started) return;
    started = true;
    init();
  }
  document.addEventListener("debate:opening-done", start);
  window.setTimeout(start, 2600);
})();
