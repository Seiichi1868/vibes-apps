(function () {
  const face = document.getElementById("tb-timer-face");
  const startBtn = document.getElementById("tb-start");
  const resetBtn = document.getElementById("tb-reset");
  const muteBtn = document.getElementById("tb-mute");
  const minInput = document.getElementById("tb-min");
  const secInput = document.getElementById("tb-sec");
  let durationMs = 60000;
  let remainingMs = durationMs;
  let running = false;
  let endAt = 0;
  let tickId = 0;
  let muted = false;
  let audio = null;
  let wakeLock = null;
  let ringing = false;

  function pad(n) {
    return String(n).padStart(2, "0");
  }

  function render() {
    const total = Math.max(0, Math.ceil(remainingMs / 1000));
    const m = Math.floor(total / 60);
    const s = total % 60;
    face.textContent = `${pad(m)}:${pad(s)}`;
    face.classList.toggle("is-warn", running && remainingMs > 0 && remainingMs <= 10000);
    face.classList.toggle("is-end", remainingMs <= 0);
  }

  function setDuration(ms) {
    durationMs = Math.max(1000, ms);
    remainingMs = durationMs;
    running = false;
    startBtn.textContent = "開始";
    render();
  }

  function unlockAudio() {
    if (audio) return;
    audio = new Audio("/static/toolbox/sounds/timer_end.wav");
    audio.preload = "auto";
    audio.volume = 0.35;
    audio.play().then(() => {
      audio.pause();
      audio.currentTime = 0;
    }).catch(() => {});
  }

  function stopEnd() {
    ringing = false;
    document.body.classList.remove("tb-timer-ringing");
    if (!audio) return;
    audio.pause();
    audio.currentTime = 0;
  }

  function playEnd() {
    if (muted || !audio) return;
    audio.loop = true;
    audio.currentTime = 0;
    ringing = true;
    document.body.classList.add("tb-timer-ringing");
    audio.play().catch(() => {});
  }

  async function requestWake() {
    try {
      if (navigator.wakeLock) wakeLock = await navigator.wakeLock.request("screen");
    } catch (_) {}
  }

  function releaseWake() {
    if (wakeLock) {
      wakeLock.release().catch(() => {});
      wakeLock = null;
    }
  }

  function finish() {
    running = false;
    remainingMs = 0;
    startBtn.textContent = "開始";
    releaseWake();
    playEnd();
    render();
  }

  function tick() {
    remainingMs = Math.max(0, endAt - Date.now());
    render();
    if (remainingMs <= 0) {
      clearInterval(tickId);
      finish();
    }
  }

  function startPause() {
    unlockAudio();
    stopEnd();
    if (remainingMs <= 0) remainingMs = durationMs;
    if (running) {
      running = false;
      remainingMs = Math.max(0, endAt - Date.now());
      startBtn.textContent = "開始";
      clearInterval(tickId);
      releaseWake();
      render();
      return;
    }
    running = true;
    endAt = Date.now() + remainingMs;
    startBtn.textContent = "一時停止";
    requestWake();
    clearInterval(tickId);
    tickId = setInterval(tick, 100);
    tick();
  }

  document.querySelectorAll(".tb-presets [data-sec]").forEach((btn) => {
    btn.addEventListener("click", () => setDuration(Number(btn.dataset.sec) * 1000));
  });
  document.getElementById("tb-set").addEventListener("click", () => {
    const m = Math.max(0, Number(minInput.value) || 0);
    const s = Math.max(0, Math.min(59, Number(secInput.value) || 0));
    setDuration((m * 60 + s) * 1000);
  });
  startBtn.addEventListener("click", startPause);
  resetBtn.addEventListener("click", () => {
    clearInterval(tickId);
    releaseWake();
    stopEnd();
    setDuration(durationMs);
  });
  muteBtn.addEventListener("click", () => {
    muted = !muted;
    muteBtn.textContent = muted ? "ミュート解除" : "ミュート";
    if (muted) stopEnd();
  });
  function stopRingOnPointer(ev) {
    if (!ringing) return;
    ev.preventDefault();
    ev.stopPropagation();
    stopEnd();
  }
  document.addEventListener("pointerdown", stopRingOnPointer, true);
  document.addEventListener("visibilitychange", () => {
    if (running) tick();
  });
  ToolboxDisplay.init({
    onNext: startPause,
    onPrev: () => {
      clearInterval(tickId);
      releaseWake();
      setDuration(durationMs);
    },
  });
  render();
})();
