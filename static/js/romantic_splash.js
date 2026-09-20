(() => {
  "use strict";

  const root = document.getElementById("algobot-romantic-splash");
  if (!root) return;

  const repeat = root.dataset.repeat || "session";
  const storageKey = "algobot-romantic-splash-seen-v2";

  const getStorage = () => repeat === "once" ? localStorage : sessionStorage;
  const hasSeen = () => {
    try {
      return repeat !== "always" && getStorage().getItem(storageKey) === "1";
    } catch (_) {
      return false;
    }
  };
  const markSeen = () => {
    try { getStorage().setItem(storageKey, "1"); } catch (_) {}
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
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  let config = {};
  try {
    const payload = document.getElementById("algobot-romantic-splash-config");
    config = payload ? JSON.parse(payload.textContent || "{}") : {};
  } catch (_) {}

  let messages = [];
  try {
    const payload = document.getElementById("algobot-romantic-splash-messages");
    messages = payload ? JSON.parse(payload.textContent || "[]") : [];
  } catch (_) {}
  messages = messages.filter(Boolean);
  if (!messages.length) messages = ["You're my favourite person. ❤️"];

  const intensityMap = { low: 0.55, medium: 0.78, high: 1, cinematic: 1.12 };
  const intensity = intensityMap[String(config.intensity || root.dataset.intensity || "high").toLowerCase()] || 1;
  const celebrationDuration = Math.max(800, Number(config.celebration_duration_ms || 3200));
  const soundEnabled = Boolean(config.sound_enabled);
  const confettiEnabled = config.confetti_enabled !== false;
  const particlesEnabled = config.particles_enabled !== false;
  const rosesEnabled = config.roses_enabled !== false;
  const countdownEnabled = config.countdown_enabled !== false;
  const autoProceed = config.auto_proceed !== false;
  const transitionName = String(config.transition_style || root.dataset.transition || "cinematic").replace(/[^a-z0-9_-]/gi, "").toLowerCase() || "cinematic";
  root.classList.add("is-transition-" + transitionName);

  const sleep = ms => new Promise(resolve => window.setTimeout(resolve, ms));
  const setProgress = (percent, text) => {
    const value = Math.max(0, Math.min(100, percent));
    if (progress) progress.style.width = value + "%";
    if (label && text) label.textContent = text;
  };

  const ensureStage = () => root.querySelector(".algobot-romantic-splash__stage");

  function createOverlayContent() {
    const stage = ensureStage();
    if (!stage) return {};

    const section = stage.querySelector("section");
    if (!section) return {};

    const memory = document.createElement("p");
    memory.className = "algobot-romantic-splash__memory";
    memory.textContent = config.memory_message || "Before the charts. Before the strategies. Before the trades. There was you. ❤️";
    memory.hidden = true;

    const final = document.createElement("p");
    final.className = "algobot-romantic-splash__final";
    final.textContent = config.final_message || "This little world was made just for you.";
    final.hidden = true;

    const ready = document.createElement("p");
    ready.className = "algobot-romantic-splash__ready";
    ready.textContent = config.ready_message || "Ready, my queen?";
    ready.hidden = true;

    const countdown = document.createElement("div");
    countdown.className = "algobot-romantic-splash__countdown";
    countdown.setAttribute("aria-live", "assertive");
    countdown.setAttribute("aria-label", "Countdown");
    countdown.hidden = true;

    const proceed = document.createElement("button");
    proceed.type = "button";
    proceed.className = "algobot-romantic-splash__proceed";
    proceed.textContent = config.proceed_label || "ENTER ALGOBOT ❤️";
    proceed.hidden = true;

    const celebration = document.createElement("div");
    celebration.className = "algobot-romantic-splash__celebration";
    celebration.setAttribute("aria-hidden", "true");

    section.insertBefore(memory, section.firstChild);
    section.appendChild(final);
    section.appendChild(ready);
    section.appendChild(countdown);
    section.appendChild(proceed);
    root.appendChild(celebration);

    return { memory, final, ready, countdown, proceed, celebration };
  }

  const ui = createOverlayContent();

  function setMessage(line) {
    typed.textContent = line;
    typed.classList.remove("is-message-reveal");
    void typed.offsetWidth;
    typed.classList.add("is-message-reveal");
  }

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
    if (reducedMotion) {
      typed.textContent = "";
      return;
    }
    for (let i = line.length; i >= 0; i -= 1) {
      typed.textContent = line.slice(0, i);
      await sleep(deleteSpeed);
    }
  }

  function spawnAmbientParticles() {
    if (!particlesEnabled) return;
    const count = Math.round(18 * intensity);
    for (let i = 0; i < count; i += 1) {
      const p = document.createElement("span");
      p.className = "algobot-romantic-splash__particle";
      p.textContent = i % 3 === 0 ? "✦" : "·";
      p.style.left = (5 + Math.random() * 90) + "%";
      p.style.top = (8 + Math.random() * 84) + "%";
      p.style.setProperty("--particle-delay", (Math.random() * 4) + "s");
      p.style.setProperty("--particle-duration", (5 + Math.random() * 5) + "s");
      p.style.setProperty("--particle-drift", ((Math.random() * 60) - 30) + "px");
      root.appendChild(p);
    }
  }

  function spawnBurst(strength = 1) {
    if (!confettiEnabled) return;
    const host = ui.celebration;
    if (!host) return;

    const particleCount = Math.round(58 * intensity * strength);
    const origins = [
      { x: "8%", y: "-2%" },
      { x: "50%", y: "-4%" },
      { x: "92%", y: "-2%" }
    ];
    const symbols = ["🎉", "❤️", "💕", "🌹", "✨", "💖", "👑", "✦"];

    origins.forEach(origin => {
      for (let i = 0; i < particleCount / origins.length; i += 1) {
        const p = document.createElement("span");
        p.className = "algobot-romantic-splash__confetti";
        p.textContent = symbols[Math.floor(Math.random() * symbols.length)];
        p.style.left = origin.x;
        p.style.top = origin.y;
        p.style.setProperty("--dx", ((Math.random() - 0.5) * 70) + "vw");
        p.style.setProperty("--dy", (28 + Math.random() * 74) + "vh");
        p.style.setProperty("--rotate", ((Math.random() - 0.5) * 900) + "deg");
        p.style.setProperty("--delay", (Math.random() * 180) + "ms");
        p.style.setProperty("--fall", (1.35 + Math.random() * 1.35) + "s");
        host.appendChild(p);
        window.setTimeout(() => p.remove(), 4200);
      }
    });
  }

  function roseClimax() {
    if (!rosesEnabled) return;
    root.classList.add("is-rose-climax");
    for (let i = 0; i < Math.round(16 * intensity); i += 1) {
      const petal = document.createElement("span");
      petal.className = "algobot-romantic-splash__petal";
      petal.textContent = i % 2 ? "🌹" : "🌸";
      petal.style.left = (Math.random() * 100) + "%";
      petal.style.setProperty("--fall-x", ((Math.random() - 0.5) * 34) + "vw");
      petal.style.setProperty("--fall-time", (2.8 + Math.random() * 2.2) + "s");
      petal.style.setProperty("--fall-delay", (Math.random() * 1.2) + "s");
      root.appendChild(petal);
      window.setTimeout(() => petal.remove(), 6200);
    }
  }

  let audioContext;
  function celebrationChime() {
    if (!soundEnabled || reducedMotion) return;
    try {
      audioContext ||= new (window.AudioContext || window.webkitAudioContext)();
      const now = audioContext.currentTime;
      [523.25, 659.25, 783.99].forEach((frequency, index) => {
        const oscillator = audioContext.createOscillator();
        const gain = audioContext.createGain();
        oscillator.type = "sine";
        oscillator.frequency.value = frequency;
        gain.gain.setValueAtTime(0.0001, now + index * 0.09);
        gain.gain.exponentialRampToValueAtTime(0.045, now + index * 0.09 + 0.025);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + index * 0.09 + 0.32);
        oscillator.connect(gain).connect(audioContext.destination);
        oscillator.start(now + index * 0.09);
        oscillator.stop(now + index * 0.09 + 0.34);
      });
    } catch (_) {}
  }

  async function showCountdown() {
    if (!ui.countdown) return;
    ui.countdown.hidden = false;
    const values = countdownEnabled ? ["3", "2", "1"] : ["❤️"];
    for (const value of values) {
      ui.countdown.textContent = value;
      ui.countdown.classList.remove("is-counting");
      void ui.countdown.offsetWidth;
      ui.countdown.classList.add("is-counting");
      if (!reducedMotion) await sleep(850);
    }
  }

  function revealFinalState() {
    if (ui.memory) ui.memory.hidden = false;
    if (ui.final) ui.final.hidden = false;
    if (ui.ready) ui.ready.hidden = false;
    if (ui.proceed) ui.proceed.hidden = false;
    root.classList.add("is-celebrating");
  }

  function finish() {
    markSeen();
    spawnBurst(0.65);
    celebrationChime();
    root.classList.add("is-exiting");
    document.body.classList.remove("algobot-splash-active");
    window.setTimeout(() => root.remove(), 1150);
  }

  async function run() {
    spawnAmbientParticles();
    setProgress(0, "Just a moment…");

    const messageWindow = Math.max(1800, duration * 0.68);
    for (let i = 0; i < messages.length; i += 1) {
      const line = String(messages[i]);
      await typeLine(line);
      setProgress(Math.min(62, ((i + 1) / messages.length) * 62), "Something special is unfolding…");
      await sleep(reducedMotion ? 120 : Math.min(850, 260 + line.length * 8));
      if (i < messages.length - 1) await eraseLine(line);
    }

    if (ui.memory) {
      typed.textContent = "";
      ui.memory.hidden = false;
      root.classList.add("is-memory-moment");
      setProgress(70, "One more thing…");
      if (!reducedMotion) await sleep(2100);
      ui.memory.hidden = true;
      root.classList.remove("is-memory-moment");
    }

    if (ui.final) {
      ui.final.hidden = false;
      setProgress(78, "Almost ready…");
      if (!reducedMotion) await sleep(1500);
    }

    roseClimax();
    spawnBurst(1);
    celebrationChime();
    setProgress(88, "A little celebration…");
    root.classList.add("is-celebrating");

    await showCountdown();

    revealFinalState();
    setProgress(100, "Welcome, my queen. ❤️");

    if (autoProceed) {
      if (!reducedMotion) await sleep(celebrationDuration);
      finish();
    }
  }

  if (ui.proceed) {
    ui.proceed.addEventListener("click", () => {
      finish();
    }, { once: true });
  }

  document.addEventListener("pointerdown", () => {
    if (!soundEnabled) return;
    try {
      audioContext ||= new (window.AudioContext || window.webkitAudioContext)();
      if (audioContext.state === "suspended") audioContext.resume();
    } catch (_) {}
  }, { once: true, passive: true });

  setProgress(0, "A little surprise is loading…");
  run().catch(() => finish());
})();
