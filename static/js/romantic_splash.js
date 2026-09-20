(() => {
  "use strict";

  const root = document.getElementById("algobot-romantic-splash");
  if (!root) return;

  const repeat = root.dataset.repeat || "session";
  const storageKey = "algobot-romantic-splash-seen-v1";

  const hasSeen = () => {
    try {
      if (repeat === "always") return false;
      const storage = repeat === "once" ? localStorage : sessionStorage;
      return storage.getItem(storageKey) === "1";
    } catch (_) {
      return false;
    }
  };

  const markSeen = () => {
    try {
      const storage = repeat === "once" ? localStorage : sessionStorage;
      storage.setItem(storageKey, "1");
    } catch (_) {}
  };

  if (hasSeen()) {
    root.remove();
    document.body.classList.remove("algobot-splash-active");
    return;
  }

  document.body.classList.add("algobot-splash-active");

  const typed = root.querySelector("[data-splash-typed]");
  const progress = root.querySelector("[data-splash-progress]");
  const label = root.querySelector("[data-splash-progress-label]");
  const duration = Math.max(2500, Number(root.dataset.durationMs || 8200));
  const typeSpeed = Math.max(10, Number(root.dataset.typeSpeedMs || 42));
  const deleteSpeed = Math.max(8, Number(root.dataset.deleteSpeedMs || 22));

  let messages = [];
  try {
    const payload = document.getElementById("algobot-romantic-splash-messages");
    messages = payload ? JSON.parse(payload.textContent || "[]") : [];
  } catch (_) {
    messages = [];
  }
  messages = messages.filter(Boolean);
  if (!messages.length) messages = ["You're my favourite person. ❤️"];

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const sleep = ms => new Promise(resolve => window.setTimeout(resolve, ms));

  async function typeLine(line) {
    typed.textContent = "";
    if (reducedMotion) {
      typed.textContent = line;
      return;
    }
    for (let i = 0; i < line.length; i += 1) {
      typed.textContent += line[i];
      await sleep(typeSpeed);
    }
  }

  async function eraseLine(line) {
    if (reducedMotion) return;
    for (let i = line.length; i >= 0; i -= 1) {
      typed.textContent = line.slice(0, i);
      await sleep(deleteSpeed);
    }
  }

  function setProgress(percent) {
    const value = Math.max(0, Math.min(100, percent));
    if (progress) progress.style.width = value + "%";
    if (label) label.textContent = value >= 99 ? "Almost there… just a little more…" : "Loading something special…";
  }

  function finish() {
    markSeen();
    root.classList.add("is-exiting");
    document.body.classList.remove("algobot-splash-active");
    window.setTimeout(() => root.remove(), 1050);
  }

  async function run() {
    const start = performance.now();
    const messageWindow = Math.max(1600, duration * 0.72);

    for (let i = 0; i < messages.length; i += 1) {
      const line = String(messages[i]);
      await typeLine(line);
      await sleep(reducedMotion ? 100 : Math.min(650, 240 + line.length * 8));
      if (i < messages.length - 1) await eraseLine(line);
    }

    const elapsed = performance.now() - start;
    while (performance.now() - start < messageWindow) {
      const percent = ((performance.now() - start) / messageWindow) * 86;
      setProgress(percent);
      await sleep(80);
    }

    const remaining = Math.max(0, duration - (performance.now() - start));
    const finishAt = performance.now() + remaining;
    while (performance.now() < finishAt) {
      const percent = 86 + ((performance.now() - (finishAt - remaining)) / Math.max(1, remaining)) * 14;
      setProgress(percent);
      await sleep(80);
    }

    setProgress(100);
    await sleep(reducedMotion ? 80 : 260);
    finish();
  }

  setProgress(0);
  run().catch(finish);
})();
