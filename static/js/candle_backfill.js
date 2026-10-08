(() => {
  const page = document.querySelector("[data-backfill-page]");
  if (!page) return;

  const $ = (selector) => page.querySelector(selector);
  const body = $("[data-log-body]");
  // Server-rendered durable events are the first paint. Continue polling strictly
  // after the newest rendered event so live polling never duplicates those rows.
  let lastEventId = Number(body?.querySelector("[data-event-id]:last-child")?.dataset.eventId || 0);
  let selectedRunId = new URLSearchParams(window.location.search).get("run_id") || "";
  let historyLimit = 50;
  let polling = false;
  let tail = true;
  let query = "";
  let level = "";
  let searchTimer = null;
  let telemetryFailures = 0;
  let refreshGeneration = 0;
  let activeController = null;

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
      text("[data-status-sub]", "No backfill execution exists");
      text("[data-duration]", "—");
      text("[data-requested]", "—");
      text("[data-started]", "—");
      text("[data-source]", "—");
      text("[data-delivery]", "—");
      text("[data-task-id]", "—");
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
        empty.textContent = "No backfill execution exists. Start one above to create durable dispatch and worker log events.";
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
      pill.dataset.renderState = run.render_status || "";
      pill.title = run.render_status_label ? "Render-aligned task state: " + run.render_status_label : "";
    }
    text("[data-status-large]", run.status_label || state);
    text("[data-start-state]",
      state === "completed" ? ((run.scope || "Backfill") + " execution completed.")
      : state === "failed" ? ((run.scope || "Backfill") + " execution failed.")
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
    text("[data-source]", run.accepted_at ? "Deriv · Celery worker" : "Celery queue");
    text("[data-delivery]", run.delivery_queue || "—");
    text("[data-task-id]", run.task_id || "—");
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


  const renderHistory = (history, hasMore) => {
    const table = $("[data-history-body]");
    if (!table) return;
    table.replaceChildren();
    const rows = Array.isArray(history) ? history : [];
    const total = Number.isFinite(Number(window.__backfillHistoryTotal)) ? Number(window.__backfillHistoryTotal) : rows.length;
    text("[data-history-count]", total + (total === 1 ? " run" : " runs"));
    const more = $("[data-history-more]");
    if (more) more.hidden = !hasMore;
    if (!rows.length) {
      const row = document.createElement("tr");
      const cell = document.createElement("td");
      cell.colSpan = 8;
      cell.className = "rb-history-empty";
      cell.textContent = "No candle backfill executions have been recorded yet.";
      row.appendChild(cell);
      table.appendChild(row);
      return;
    }
    rows.forEach((run) => {
      const row = document.createElement("tr");
      row.dataset.runId = String(run.id);
      row.tabIndex = 0;
      if (String(run.id) === String(selectedRunId)) row.classList.add("is-selected");
      const progress = run.progress || {};
      const cells = [
        "<strong>#" + run.id + "</strong><small>" + (run.task_id || "No task ID") + "</small>",
        run.scope || "—",
        (run.trigger || "manual").replace(/^./, (m) => m.toUpperCase()),
        "<span class=\"rb-history-status\" data-state=\"" + (run.status || "") + "\">" + (run.status_label || run.status || "—") + "</span>",
        formatDate(run.requested_at),
        run.started_at ? formatDuration(run.duration_seconds) : "—",
        (Number(progress.percent) || 0) + "%",
        run.worker_hostname || "—",
      ];
      const identity = document.createElement("td");
      const idStrong = document.createElement("strong");
      idStrong.textContent = "#" + run.id;
      const taskSmall = document.createElement("small");
      taskSmall.textContent = run.task_id || "No task ID";
      identity.append(idStrong, taskSmall);
      row.appendChild(identity);
      cells.slice(1).forEach((value, index) => {
        const cell = document.createElement("td");
        if (index === 2) {
          const status = document.createElement("span");
          status.className = "rb-history-status";
          status.dataset.state = run.status || "";
          status.textContent = run.status_label || run.status || "—";
          cell.appendChild(status);
        } else {
          cell.textContent = value.replace(/<[^>]+>/g, "");
        }
        row.appendChild(cell);
      });
      const select = () => selectRun(run.id);
      row.addEventListener("click", select);
      row.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          select();
        }
      });
      table.appendChild(row);
    });
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

  const refresh = async ({force = false} = {}) => {
    if (polling && !force) return;
    const generation = ++refreshGeneration;
    if (force && activeController) activeController.abort();
    polling = true;
    try {
      const params = new URLSearchParams({
        format: "json",
        run_id: selectedRunId,
        after: String(lastEventId),
        limit: "200",
        history_limit: String(historyLimit),
      });
      if (query) params.set("q", query);
      if (level) params.set("level", level);
      // Never allow one stalled HTTP request to freeze the telemetry loop.
      // The durable Django run/event records remain authoritative; the browser
      // is only a live observer.
      const controller = new AbortController();
      activeController = controller;
      const requestedRunId = selectedRunId;
      const timeout = window.setTimeout(() => controller.abort(), 4500);
      let response;
      try {
        response = await fetch(location.pathname + "?" + params.toString(), {
          credentials: "same-origin",
          cache: "no-store",
          signal: controller.signal,
          headers: {"X-Requested-With": "XMLHttpRequest", "Cache-Control": "no-cache"},
        });
      } finally {
        window.clearTimeout(timeout);
      }
      if (!response.ok) throw new Error("status " + response.status);
      const data = await response.json();
      if (generation !== refreshGeneration || requestedRunId !== selectedRunId) return;
      telemetryFailures = 0;
      const telemetryNotice = $("[data-telemetry-error]");
      if (telemetryNotice) telemetryNotice.remove();
      if (!selectedRunId && data.selected) {
        selectedRunId = String(data.selected.id);
        const url = new URL(window.location.href);
        url.searchParams.set("run_id", selectedRunId);
        window.history.replaceState({}, "", url);
      }
      renderRun(data.selected);
      renderHistory(data.history || [], Boolean(data.history_has_more));
      if (query && lastEventId === 0) {
        renderEvents(data.events || [], true);
      } else {
        renderEvents(data.events || [], false);
      }
      if (data.events_last_id) lastEventId = Number(data.events_last_id) || lastEventId;
      window.__backfillHistoryTotal = Number(data.history_total) || (data.history || []).length;
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
      if (activeController === controller) activeController = null;
      polling = false;
    }
  };

  const selectRun = (runId) => {
    const nextId = String(runId);
    if (!nextId) return;
    selectedRunId = nextId;
    lastEventId = 0;
    refreshGeneration += 1;
    if (activeController) activeController.abort();

    const url = new URL(window.location.href);
    url.searchParams.set("run_id", selectedRunId);
    window.history.replaceState({}, "", url);

    page.querySelectorAll("[data-history-body] [data-run-id]").forEach((row) => {
      row.classList.toggle("is-selected", String(row.dataset.runId) === selectedRunId);
    });

    if (body) {
      body.replaceChildren();
      const loading = document.createElement("div");
      loading.className = "rb-log-empty";
      loading.textContent = "Loading durable logs for execution #" + selectedRunId + "…";
      body.appendChild(loading);
    }
    text("[data-log-count]", "Loading…");
    refresh({force: true});
  };

  // Server-rendered rows must remain interactive even when the first telemetry
  // request fails. Delegate selection from the stable table body.
  const initialHistoryBody = $("[data-history-body]");
  if (initialHistoryBody) {
    initialHistoryBody.addEventListener("click", (event) => {
      const row = event.target.closest("[data-run-id]");
      if (row && initialHistoryBody.contains(row)) selectRun(row.dataset.runId);
    });
    initialHistoryBody.addEventListener("keydown", (event) => {
      const row = event.target.closest("[data-run-id]");
      if (row && initialHistoryBody.contains(row) && (event.key === "Enter" || event.key === " ")) {
        event.preventDefault();
        selectRun(row.dataset.runId);
      }
    });
  }

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

  const logFilter = $("[data-log-filter]");
  if (logFilter) {
    logFilter.addEventListener("change", () => {
      level = logFilter.value || "";
      resetSearch();
    });
  }

  const historyRefresh = $("[data-history-refresh]");
  if (historyRefresh) historyRefresh.addEventListener("click", () => {
    historyLimit = 50;
    lastEventId = 0;
    refresh({force: true});
  });

  const historyMore = $("[data-history-more]");
  if (historyMore) historyMore.addEventListener("click", () => {
    historyLimit += 50;
    refresh();
  });

  const refreshButton = $("[data-refresh]");
  if (refreshButton) {
    refreshButton.addEventListener("click", () => {
      refresh();
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

  let refreshTimer = null;
  let destroyed = false;

  const scheduleRefresh = (delay = 1500) => {
    if (destroyed || document.visibilityState !== "visible") return;
    if (refreshTimer) window.clearTimeout(refreshTimer);
    refreshTimer = window.setTimeout(async () => {
      refreshTimer = null;
      await refresh();
      const backoff = telemetryFailures
        ? Math.min(30000, 1500 * Math.pow(2, Math.min(telemetryFailures - 1, 4)))
        : 1500;
      scheduleRefresh(backoff);
    }, Math.max(250, delay));
  };

  const refreshNow = () => {
    if (refreshTimer) {
      window.clearTimeout(refreshTimer);
      refreshTimer = null;
    }
    void refresh().finally(() => scheduleRefresh(1500));
  };

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      telemetryFailures = 0;
      refreshNow();
    } else if (refreshTimer) {
      window.clearTimeout(refreshTimer);
      refreshTimer = null;
    }
  });

  window.addEventListener("pagehide", () => {
    destroyed = true;
    if (refreshTimer) window.clearTimeout(refreshTimer);
    refreshTimer = null;
  }, {once: true});

  refreshNow();
})();
