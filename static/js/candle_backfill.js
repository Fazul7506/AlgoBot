(() => {
  const page = document.querySelector("[data-backfill-page]");
  if (!page) return;

  const $ = (selector) => page.querySelector(selector);
  const body = $("[data-log-body]");
  let lastEventId = 0;
  let polling = false;
  let tail = true;
  let query = "";
  let searchTimer = null;
  let telemetryFailures = 0;

  const text = (selector, value) => {
    const node = $(selector);
    if (node) node.textContent = value == null || value === "" ? "—" : value;
  };

  const formatDate = (value) => value ? new Date(value).toLocaleString() : "—";

  const formatDuration = (seconds) => {
    const total = Math.max(0, Number(seconds) || 0);
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    return h ? h + "h " + m + "m " + s + "s" : m ? m + "m " + s + "s" : s + "s";
  };

  const renderNotices = (notices) => {
    const box = $("[data-notices]");
    if (!box) return;
    box.replaceChildren();
    (notices || []).forEach((notice) => {
      const row = document.createElement("div");
      row.className = "rb-notice " + (notice.level || "");
      const icon = document.createElement("span");
      icon.className = "material-symbols-rounded";
      icon.textContent = notice.level === "error" ? "error" : "info";
      const message = document.createElement("span");
      message.textContent = notice.message || "";
      row.append(icon, message);
      box.appendChild(row);
    });
  };

  const renderRun = (run) => {
    if (!run) {
      text("[data-status]", "Not started");
      text("[data-status-large]", "Not started");
      text("[data-status-sub]", "No initial backfill run exists");
      text("[data-duration]", "—");
      text("[data-requested]", "—");
      text("[data-started]", "—");
      text("[data-source]", "—");
      text("[data-worker-state]", "NOT STARTED");
      text("[data-heartbeat]", "Heartbeat —");
      text("[data-progress-count]", "— / —");
      text("[data-progress-percent]", "—");
      text("[data-work-progress]", "No worker work has been confirmed");
      text("[data-current-operation]", "Start the backfill to begin broker ingestion");
      const bar = $("[data-progress-bar]");
      if (bar) bar.style.width = "0%";
      const live = $("[data-live]");
      if (live) live.hidden = true;
      renderNotices([]);
      if (body) {
        body.replaceChildren();
        const empty = document.createElement("div");
        empty.className = "rb-log-empty";
        empty.textContent = "No initial run exists. Start the backfill above to create durable dispatch and worker log events.";
        body.appendChild(empty);
      }
      lastEventId = 0;
      text("[data-log-count]", "0 lines");
      return;
    }
    const state = run.status || "running";
    const pill = $("[data-status]");
    if (pill) {
      pill.textContent = run.status_label || state;
      pill.dataset.state = state;
    }
    text("[data-status-large]", run.status_label || state);
    text("[data-start-state]",
      state === "completed" ? "Initial backfill completed."
      : state === "failed" ? "Initial backfill failed."
      : run.accepted_at ? "Worker received the backfill task."
      : "Backfill is being dispatched to the market-data worker."
    );
    text("[data-status-sub]",
      state === "completed" ? "Backfill is live and persisted"
      : state === "failed" ? "Worker stopped with an error"
      : run.started_at ? "Worker is processing broker history" : "Waiting for worker confirmation"
    );
    // Duration is calculated by the server from confirmed worker timestamps;
    // never infer it from the phone/browser clock.
    text("[data-duration]", run.started_at ? formatDuration(run.duration_seconds) : "—");
    text("[data-requested]", formatDate(run.requested_at));
    text("[data-started]", formatDate(run.started_at));
    text("[data-source]", run.accepted_at ? "Deriv · market_data worker" : "market_data queue");
    text("[data-worker-state]", run.worker_state || run.celery_state || "DISPATCHING");
    text("[data-heartbeat]", run.last_heartbeat_at ? "Heartbeat " + formatDate(run.last_heartbeat_at) : "Heartbeat —");
    const progress = run.progress || {};
    const percent = Math.max(0, Math.min(100, Number(progress.percent) || 0));
    const hasTotal = Number.isFinite(Number(progress.total)) && Number(progress.total) > 0;
    const hasWorkTotal = Number.isFinite(Number(progress.work_total)) && Number(progress.work_total) > 0;
    text("[data-progress-count]", hasTotal ? (progress.completed || 0) + " / " + progress.total : "— / —");
    text("[data-progress-percent]", hasWorkTotal ? percent + "%" : "—");
    text("[data-work-progress]", hasWorkTotal
      ? (progress.work_completed || 0) + " / " + progress.work_total + " broker series"
      : "No worker work has been confirmed");
    const bar = $("[data-progress-bar]");
    if (bar) bar.style.width = hasWorkTotal ? percent + "%" : "0%";
    const current = [run.current_symbol, run.current_timeframe].filter(Boolean).join(" · ");
    text("[data-current-operation]", current || (run.started_at ? "Processing broker history" : run.accepted_at ? "Worker received the task" : "Waiting for worker receipt"));
    renderNotices(run.notices || []);
    const live = $("[data-live]");
    if (live) live.hidden = !run.live;
    const logEmpty = body && body.querySelector(".rb-log-empty");
    if (logEmpty && Number(run.event_count || 0) > 0) logEmpty.remove();
  };

  const appendEvent = (event) => {
    const row = document.createElement("div");
    row.className = "rb-log-line";
    const time = document.createElement("span");
    time.className = "rb-log-time";
    time.textContent = new Date(event.timestamp).toLocaleTimeString();
    const level = document.createElement("span");
    level.className = "rb-log-level " + (event.level || "");
    level.textContent = event.level || "info";
    const message = document.createElement("span");
    message.className = "rb-log-message";
    message.textContent = event.message || "";
    if (event.symbol || event.timeframe) {
      const meta = document.createElement("span");
      meta.className = "rb-log-meta";
      meta.textContent = [event.symbol, event.timeframe].filter(Boolean).join(" · ");
      message.appendChild(meta);
    }
    row.append(time, level, message);
    body.appendChild(row);
  };

  const renderEvents = (events, replace) => {
    if (!body) return;
    if (replace) {
      body.replaceChildren();
      lastEventId = 0;
    }
    (events || []).forEach(appendEvent);
    const lineCount = body.querySelectorAll(".rb-log-line").length;
    if (!lineCount && !body.querySelector(".rb-log-empty")) {
      const empty = document.createElement("div");
      empty.className = "rb-log-empty";
      empty.textContent = query
        ? "No durable operator events match this search."
        : "No durable operator events have been recorded for this run.";
      body.appendChild(empty);
    }
    text("[data-log-count]", lineCount + " lines");
    if (tail) body.scrollTop = body.scrollHeight;
  };

  const refresh = async () => {
    if (polling) return;
    polling = true;
    try {
      const params = new URLSearchParams({
        format: "json",
        scope: "initial",
        after: String(lastEventId),
        limit: "200",
      });
      if (query) params.set("q", query);
      const response = await fetch(location.pathname + "?" + params.toString(), {
        credentials: "same-origin",
        cache: "no-store",
        headers: {"X-Requested-With": "XMLHttpRequest", "Cache-Control": "no-cache"},
      });
      if (!response.ok) throw new Error("status " + response.status);
      const data = await response.json();
      telemetryFailures = 0;
      const telemetryNotice = $("[data-telemetry-error]");
      if (telemetryNotice) telemetryNotice.remove();
      renderRun(data.initial);
      if (query && lastEventId === 0) {
        renderEvents(data.events || [], true);
      } else {
        renderEvents(data.events || [], false);
      }
      if (data.events_last_id) lastEventId = Number(data.events_last_id) || lastEventId;
    } catch (error) {
      telemetryFailures += 1;
      // A single mobile-network hiccup must not look like a broker failure.
      // Show the reconnect warning only after several consecutive failures.
      if (telemetryFailures < 3) return;
      const notices = $("[data-notices]");
      if (notices) {
        let row = notices.querySelector("[data-telemetry-error]");
        if (!row) {
          row = document.createElement("div");
          row.className = "rb-notice error";
          row.dataset.telemetryError = "true";
          notices.appendChild(row);
        }
        row.textContent = "Live telemetry is temporarily unavailable; the durable server state remains authoritative and the page will keep retrying.";
      }
    } finally {
      polling = false;
    }
  };

  const resetSearch = () => {
    lastEventId = 0;
    body.replaceChildren();
    refresh();
  };

  const search = $("[data-log-search]");
  if (search) {
    search.addEventListener("input", () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        query = search.value.trim();
        resetSearch();
      }, 250);
    });
  }

  const tailButton = $("[data-tail]");
  if (tailButton) {
    tailButton.addEventListener("click", () => {
      tail = !tail;
      tailButton.classList.toggle("rb-tail-active", tail);
      if (tail) body.scrollTop = body.scrollHeight;
    });
  }

  const expand = $("[data-expand]");
  if (expand) {
    expand.addEventListener("click", () => {
      const panel = $("[data-log-panel]");
      panel.classList.toggle("is-fullscreen");
      const icon = expand.querySelector(".material-symbols-rounded");
      if (icon) icon.textContent = panel.classList.contains("is-fullscreen") ? "close_fullscreen" : "open_in_full";
    });
  }

  const copy = $("[data-copy]");
  if (copy) {
    copy.addEventListener("click", async () => {
      const lines = [...body.querySelectorAll(".rb-log-line")].map((line) => line.innerText);
      try {
        await navigator.clipboard.writeText(lines.join("\n"));
        copy.title = "Copied";
        setTimeout(() => { copy.title = "Copy visible logs"; }, 1200);
      } catch (_) {}
    });
  }

  refresh();
  window.setInterval(refresh, 1500);
})();
