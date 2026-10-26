(() => {
  const panel = document.querySelector("[data-mission-logger]");
  if (!panel) return;

  const body = panel.querySelector("[data-mission-log-body]");
  const count = panel.querySelector("[data-mission-log-count]");
  const status = panel.querySelector("[data-mission-log-status]");
  const search = panel.querySelector("[data-mission-log-search]");
  const tailButton = panel.querySelector("[data-mission-log-tail]");
  const expandButton = panel.querySelector("[data-mission-log-expand]");
  const copyButton = panel.querySelector("[data-mission-log-copy]");
  let liveTail = true;
  let busy = false;
  let searchTimer = null;
  let searchTerm = "";
  let timer = null;

  const setStatus = (message) => { if (status) status.textContent = message; };
  const severityClass = (level) => String(level || "info").toLowerCase().replace(/[^a-z0-9_-]/g, "-");

  const appendLog = (event) => {
    const row = document.createElement("div");
    row.className = "rb-log-line";
    const timestamp = document.createElement("span");
    timestamp.className = "rb-log-time";
    const date = event.timestamp || event.created_at || event.time;
    timestamp.textContent = date ? new Date(date).toLocaleTimeString() : "—";

    const level = document.createElement("span");
    level.className = "rb-log-level " + severityClass(event.level || event.severity);
    level.textContent = String(event.level || event.severity || "INFO").toLowerCase();

    const message = document.createElement("span");
    message.className = "rb-log-message";
    message.textContent = String(event.message || event.summary || event.event || "");

    const metadata = [event.stream, event.source, event.symbol, event.timeframe].filter(Boolean);
    if (metadata.length) {
      const meta = document.createElement("span");
      meta.className = "rb-log-meta";
      meta.textContent = metadata.join(" · ");
      message.appendChild(meta);
    }
    row.append(timestamp, level, message);
    body.appendChild(row);
  };

  const refresh = async () => {
    if (busy || document.visibilityState === "hidden") return;
    busy = true;
    try {
      const params = new URLSearchParams({limit: "200"});
      if (searchTerm) params.set("search", searchTerm);
      const client = window.AlgoBotFrontendData;
      if (!client || typeof client.request !== "function") throw new Error("Log feed client unavailable");
      const response = await client.request("/api/monitoring/mission-events/?" + params.toString(), {}, 10000);
      const payload = response?.data && typeof response.data === "object" ? response.data : response;
      const events = Array.isArray(payload) ? payload : (payload.results || payload.events || payload.logs || []);
      if (!Array.isArray(events)) throw new Error("Unexpected log feed response");
      body.replaceChildren();
      events.slice().reverse().forEach(appendLog);
      if (count) count.textContent = body.querySelectorAll(".rb-log-line").length + " lines";
      setStatus(events.length ? "Live · updated " + new Date().toLocaleTimeString() : "No log entries returned");
      if (liveTail) body.scrollTop = body.scrollHeight;
    } catch (error) {
      setStatus("Log feed unavailable");
    } finally {
      busy = false;
    }
  };

  if (search) search.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => { searchTerm = search.value.trim(); refresh(); }, 250);
  });
  if (tailButton) tailButton.addEventListener("click", () => {
    liveTail = !liveTail;
    tailButton.classList.toggle("rb-tail-active", liveTail);
    tailButton.setAttribute("aria-pressed", String(liveTail));
    if (liveTail) body.scrollTop = body.scrollHeight;
  });
  if (expandButton) expandButton.addEventListener("click", () => {
    const expanded = panel.classList.toggle("is-fullscreen");
    expandButton.textContent = expanded ? "Close" : "Expand";
    expandButton.setAttribute("aria-label", expanded ? "Close expanded logs" : "Expand logs");
  });
  if (copyButton) copyButton.addEventListener("click", async () => {
    const lines = Array.from(body.querySelectorAll(".rb-log-line"), (line) => line.innerText);
    try {
      await navigator.clipboard.writeText(lines.join("\n"));
      copyButton.textContent = "Copied";
      setTimeout(() => { copyButton.textContent = "Copy"; }, 1200);
    } catch (_) {
      setStatus("Clipboard unavailable");
    }
  });

  refresh();
  timer = window.setInterval(refresh, 1500);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") refresh();
  });
  window.addEventListener("pagehide", () => { if (timer) window.clearInterval(timer); });
})();
