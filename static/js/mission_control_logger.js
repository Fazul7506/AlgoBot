(() => {
  const panel = document.querySelector("[data-mission-logger]");
  if (!panel) return;
  const body = panel.querySelector("[data-mission-log-body]");
  const count = panel.querySelector("[data-mission-log-count]");
  const status = panel.querySelector("[data-mission-log-status]");
  const connection = document.querySelector("[data-mission-connection]");
  const search = panel.querySelector("[data-mission-log-search]");
  const tailButton = panel.querySelector("[data-mission-log-tail]");
  const expandButton = panel.querySelector("[data-mission-log-expand]");
  const menuToggle = panel.querySelector("[data-mission-menu-toggle]");
  const menu = panel.querySelector("[data-mission-log-menu]");
  const range = panel.querySelector("[data-mission-range]");
  const customRange = panel.querySelector("[data-mission-custom-range]");
  const startInput = panel.querySelector("[data-mission-start]");
  const endInput = panel.querySelector("[data-mission-end]");
  const sourceSelect = panel.querySelector("[data-mission-log-source]");
  const displayLabel = panel.querySelector("[data-mission-display-label]");
  const themeLabel = panel.querySelector("[data-mission-theme-label]");
  let liveTail = true, busy = false, searchTimer = null, searchTerm = "", timer = null;
  let order = "desc", expanded = false, lightTheme = false, customStart = "", customEnd = "";

  const setStatus = (message) => { if (status) status.textContent = message; };
  const setConnection = (message) => { if (connection) connection.textContent = message; };
  const severityClass = (level) => String(level || "info").toLowerCase().replace(/[^a-z0-9_-]/g, "-");
  const escText = (value) => String(value == null ? "" : value);
  const setMenuOpen = (open) => {
    if (!menu || !menuToggle) return;
    menu.hidden = !open;
    menuToggle.setAttribute("aria-expanded", String(open));
  };

  const appendLog = (event) => {
    const row = document.createElement("div");
    row.className = "rb-log-line";
    const dateValue = event.timestamp || event.created_at || event.time;
    const date = dateValue ? new Date(dateValue) : null;
    const timestamp = document.createElement("span");
    timestamp.className = "rb-log-time";
    timestamp.textContent = date && !Number.isNaN(date.getTime()) ? date.toLocaleTimeString([], {hour:"2-digit",minute:"2-digit",second:"2-digit",hour12:true}) : "—";
    const level = document.createElement("span");
    level.className = "rb-log-level " + severityClass(event.level || event.severity);
    level.textContent = escText(event.level || event.severity || "INFO").toLowerCase();
    const message = document.createElement("span");
    message.className = "rb-log-message";
    message.textContent = escText(event.message || event.summary || event.event);
    const metadata = [event.stream, event.source, event.category, event.status, event.operation_id].filter(Boolean);
    if (metadata.length) {
      const meta = document.createElement("span");
      meta.className = "rb-log-meta";
      meta.textContent = metadata.join(" · ") + (event.duration_ms != null ? " · " + event.duration_ms + " ms" : "");
      message.appendChild(meta);
    }
    if (event.details || event.resolution || event.error_category) {
      const details = document.createElement("details");
      const summary = document.createElement("summary");
      summary.textContent = "Details";
      const content = document.createElement("pre");
      content.className = "mc-log-details";
      content.textContent = [event.error_category && "Error: " + event.error_category, event.details && "Details: " + event.details, event.resolution && "Resolution: " + event.resolution].filter(Boolean).join("\n");
      details.append(summary, content);
      message.appendChild(details);
    }
    row.append(timestamp, level, message);
    body.appendChild(row);
  };

  const refresh = async () => {
    if (busy || document.visibilityState === "hidden") return;
    busy = true;
    try {
      const params = new URLSearchParams({limit:"100", since_minutes:"60"});
      if (searchTerm) params.set("search", searchTerm);
      if (range && range.value !== "custom" && range.value !== "live") params.set("since_minutes", range.value);
      if (customStart && customEnd) {
        params.set("since_minutes", "all");
        params.set("start", new Date(customStart).toISOString());
        params.set("end", new Date(customEnd).toISOString());
      }
      const source = sourceSelect ? sourceSelect.value : "all";
      if (source === "application") params.set("stream", "application");
      const client = window.AlgoBotFrontendData;
      if (!client || typeof client.request !== "function") throw new Error("Log feed client unavailable");
      const response = await client.request("/api/monitoring/mission-events/?" + params.toString(), {}, 20000);
      const payload = response?.data && typeof response.data === "object" ? response.data : response;
      let events = Array.isArray(payload) ? payload : (payload.results || payload.events || payload.logs || []);
      if (!Array.isArray(events)) throw new Error("Unexpected log feed response");
      if (order === "asc") events = events.slice().reverse();
      body.replaceChildren();
      events.forEach(appendLog);
      if (count) count.textContent = body.querySelectorAll(".rb-log-line").length + " lines";
      const message = events.length ? "Updated " + new Date().toLocaleTimeString() : "No log entries returned";
      setStatus((liveTail ? "Live · " : "Paused · ") + message);
      setConnection("Connected");
      panel.classList.toggle("mc-expanded-lines", expanded);
      if (liveTail) body.scrollTop = body.scrollHeight;
    } catch (error) {
      const reason = error && error.message ? String(error.message).slice(0, 180) : "Unknown request error";
      setStatus(/timeout|timed out|abort/i.test(reason) ? "Request timed out · retrying automatically" : "Log feed unavailable · " + reason);
      setConnection(/timeout|timed out|abort/i.test(reason) ? "Log request timed out" : "Log feed unavailable");
    } finally { busy = false; }
  };

  if (search) search.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => { searchTerm = search.value.trim(); refresh(); }, 250);
  });
  if (tailButton) tailButton.addEventListener("click", () => {
    liveTail = !liveTail;
    tailButton.classList.toggle("rb-tail-active", liveTail);
    tailButton.setAttribute("aria-pressed", String(liveTail));
    tailButton.innerHTML = (liveTail ? '<span class="material-symbols-rounded mc-action-icon" aria-hidden="true">bolt</span> Live tail' : '<span class="material-symbols-rounded mc-action-icon" aria-hidden="true">pause</span> Paused');
    if (liveTail) { refresh(); body.scrollTop = body.scrollHeight; }
  });
  if (expandButton) expandButton.addEventListener("click", () => {
    const isFull = panel.classList.toggle("is-fullscreen");
    expandButton.setAttribute("aria-label", isFull ? "Close expanded logs" : "Expand logs");
    expandButton.innerHTML = isFull ? '<span class="material-symbols-rounded mc-action-icon" aria-hidden="true">close_fullscreen</span>' : '<span class="material-symbols-rounded mc-action-icon" aria-hidden="true">open_in_full</span>';
  });
  if (menuToggle) menuToggle.addEventListener("click", () => setMenuOpen(menu && menu.hidden));
  if (menu) menu.addEventListener("click", async (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    if (button.hasAttribute("data-mission-order")) {
      order = button.getAttribute("data-mission-order");
      menu.querySelectorAll("[data-mission-order]").forEach((item) => {
        item.classList.toggle("is-selected", item === button);
        const check = item.querySelector("[data-order-check]");
        if (check) check.textContent = item === button ? "✓" : "";
      });
      refresh();
    } else if (button.hasAttribute("data-mission-display")) {
      expanded = !expanded;
      if (displayLabel) displayLabel.textContent = expanded ? "Expand everything" : "Compact";
      panel.classList.toggle("mc-expanded-lines", expanded);
    } else if (button.hasAttribute("data-mission-theme")) {
      lightTheme = !lightTheme;
      panel.classList.toggle("mc-light-theme", lightTheme);
      if (themeLabel) themeLabel.textContent = lightTheme ? "Light" : "Dark";
    } else if (button.hasAttribute("data-mission-log-copy")) {
      const lines = Array.from(body.querySelectorAll(".rb-log-line"), (line) => line.innerText);
      try { await navigator.clipboard.writeText(lines.join("\n")); button.textContent = "✓　Copied"; }
      catch (_) { setStatus("Clipboard unavailable"); }
    } else if (button.hasAttribute("data-mission-log-download")) {
      const lines = Array.from(body.querySelectorAll(".rb-log-line"), (line) => line.innerText);
      const blob = new Blob([lines.join("\n") + "\n"], {type:"text/plain;charset=utf-8"});
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "algobot-mission-control-logs.txt";
      document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url);
    }
    if (!button.hasAttribute("data-mission-display") && !button.hasAttribute("data-mission-theme")) setMenuOpen(false);
  });
  document.addEventListener("click", (event) => {
    if (menu && !menu.hidden && !menu.contains(event.target) && !menuToggle.contains(event.target)) setMenuOpen(false);
  });
  if (range) range.addEventListener("change", () => {
    customRange.hidden = range.value !== "custom";
    customStart = ""; customEnd = "";
    const rangeLabels = {live:"Live tail", "60":"Last hour", "240":"Last 4 hours", "1440":"Last 24 hours", "2880":"Last 2 days", "10080":"Last 7 days", custom:"Custom"};
    const label = panel.querySelector("[data-mc-range-label]");
    if (label) label.textContent = rangeLabels[range.value] || "Custom";
    panel.querySelectorAll("[data-mc-range-option]").forEach((option) => {
      const selected = option.getAttribute("data-mc-range-option") === range.value;
      option.setAttribute("aria-checked", String(selected));
      const check = option.querySelector(".mc-option-check"); if (check) check.textContent = selected ? "✓" : "";
    });
    if (range.value !== "custom") refresh();
    liveTail = range.value === "live";
    tailButton.classList.toggle("rb-tail-active", liveTail);
    tailButton.setAttribute("aria-pressed", String(liveTail));
  });
  const applyRange = panel.querySelector("[data-mission-apply-range]");
  const rangeError = panel.querySelector("[data-mission-range-error]");
  if (applyRange) applyRange.addEventListener("click", () => {
    if (!startInput.value || !endInput.value || new Date(startInput.value) >= new Date(endInput.value)) {
      if (rangeError) rangeError.textContent = "Choose a valid start and end time.";
      return;
    }
    customStart = startInput.value; customEnd = endInput.value;
    if (rangeError) rangeError.textContent = "";
    liveTail = false; tailButton.classList.remove("rb-tail-active"); refresh();
  });
  if (sourceSelect) sourceSelect.addEventListener("change", () => {
    const label = panel.querySelector("[data-mc-source-label]");
    if (label) label.textContent = sourceSelect.value === "application" ? "Application logs" : "All logs";
    panel.querySelectorAll("[data-mc-source-option]").forEach((option) => {
      const selected = option.getAttribute("data-mc-source-option") === sourceSelect.value;
      option.setAttribute("aria-checked", String(selected));
      const check = option.querySelector(".mc-option-check"); if (check) check.textContent = selected ? "✓" : "";
    });
    refresh();
  });
  panel.querySelectorAll("[data-mc-dropdown]").forEach((dropdown) => {
    const trigger = dropdown.querySelector("[data-mc-dropdown-toggle]");
    const popup = dropdown.querySelector(".mc-dropdown-menu");
    if (!trigger || !popup) return;
    trigger.addEventListener("click", (event) => {
      event.stopPropagation();
      const opening = popup.hidden;
      panel.querySelectorAll(".mc-dropdown-menu").forEach((other) => { other.hidden = true; });
      panel.querySelectorAll("[data-mc-dropdown-toggle]").forEach((other) => other.setAttribute("aria-expanded", "false"));
      popup.hidden = !opening;
      trigger.setAttribute("aria-expanded", String(opening));
    });
    popup.addEventListener("click", (event) => {
      const option = event.target.closest("[data-mc-source-option], [data-mc-range-option]");
      if (!option) return;
      if (option.hasAttribute("data-mc-source-option") && sourceSelect) {
        sourceSelect.value = option.getAttribute("data-mc-source-option");
        sourceSelect.dispatchEvent(new Event("change", {bubbles:true}));
      } else if (option.hasAttribute("data-mc-range-option") && range) {
        range.value = option.getAttribute("data-mc-range-option");
        range.dispatchEvent(new Event("change", {bubbles:true}));
      }
      popup.hidden = true; trigger.setAttribute("aria-expanded", "false");
    });
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest("[data-mc-dropdown]")) {
      panel.querySelectorAll(".mc-dropdown-menu").forEach((popup) => { popup.hidden = true; });
      panel.querySelectorAll("[data-mc-dropdown-toggle]").forEach((trigger) => trigger.setAttribute("aria-expanded", "false"));
    }
  });
  const topButton = panel.querySelector("[data-mission-log-top]");
  if (topButton) topButton.addEventListener("click", () => { body.scrollTop = body.scrollHeight; liveTail = true; tailButton.classList.add("rb-tail-active"); });
  refresh();
  timer = window.setInterval(() => { if (liveTail) refresh(); }, 15000);
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") refresh(); });
  window.addEventListener("pagehide", () => { if (timer) window.clearInterval(timer); });
})();