(() => {
  const root = document.querySelector("[data-module-workspace]");
  if (!root) return;

  const csrf = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] || "";
  const cards = [...root.querySelectorAll("[data-resource-card]")];
  const endpoints = JSON.parse(document.getElementById("module-endpoints")?.textContent || "[]");

  const notify = (message, type = "info") => {
    let stack = document.querySelector(".toast-stack");
    if (!stack) {
      stack = document.createElement("div");
      stack.className = "toast-stack";
      stack.setAttribute("aria-live", "polite");
      document.body.appendChild(stack);
    }
    const node = document.createElement("div");
    node.className = `toast ${type}`;
    node.setAttribute("role", "status");
    node.textContent = message;
    stack.appendChild(node);
    window.setTimeout(() => node.remove(), 4500);
  };

  const csrfHeaders = () => ({ Accept: "application/json", "X-CSRFToken": csrf });

  async function request(url, options = {}) {
    const response = await fetch(url, {
      credentials: "same-origin",
      ...options,
      headers: { ...csrfHeaders(), ...(options.headers || {}) },
    });
    const text = await response.text();
    let data = {};
    try { data = text ? JSON.parse(text) : {}; } catch { data = {}; }
    if (response.status === 401 || response.status === 403) {
      window.location.assign(`/login/?next=${encodeURIComponent(window.location.pathname)}`);
      throw new Error("Authentication required");
    }
    if (!response.ok) throw new Error(data.detail || data.message || `Service unavailable (${response.status})`);
    return data;
  }

  const recordCount = value => {
    if (Array.isArray(value)) return value.length;
    if (Array.isArray(value?.results)) return value.results.length;
    if (Array.isArray(value?.data)) return value.data.length;
    if (value && typeof value === "object") return Object.keys(value).length;
    return 0;
  };

  async function loadCard(card, endpoint) {
    const status = card.querySelector("[data-resource-status]");
    const output = card.querySelector("[data-resource-output]");
    if (!status || !output || !endpoint) return;
    status.textContent = "Checking…";
    output.textContent = "Connecting to the service…";
    try {
      const data = await request(endpoint[0]);
      const count = recordCount(data);
      status.textContent = "Healthy";
      output.textContent = count ? `${count} live record${count === 1 ? "" : "s"} available.` : "Service responded successfully. No records are currently available.";
    } catch (error) {
      status.textContent = "Unavailable";
      output.textContent = "This service is temporarily unavailable. The rest of the workspace remains usable.";
    }
  }

  endpoints.forEach((endpoint, index) => loadCard(cards[index], endpoint));

  const filter = root.querySelector("[data-module-filter]");
  filter?.addEventListener("input", () => {
    const q = filter.value.toLowerCase().trim();
    cards.forEach(card => { card.hidden = !card.dataset.label.includes(q); });
  });

  root.querySelectorAll("[data-module-action]").forEach(button => {
    button.addEventListener("click", async () => {
      const url = button.dataset.moduleAction;
      const method = (button.dataset.actionMethod || "post").toUpperCase();
      let body = {};
      if (root.dataset.module === "ai" && url.endsWith("/predict/")) body = { symbol: "R_100", timeframe: "M1", context: {} };
      else if (root.dataset.module === "notifications") body = { channel: "in_app", subject: "AlgoBot test alert", message: "Test notification from the operations center." };
      else if (root.dataset.module === "automation") body = { event: "manual", source: "operations-center" };
      button.disabled = true;
      try {
        await request(url, { method, body: method === "GET" ? undefined : JSON.stringify(body), headers: method === "GET" ? {} : { "Content-Type": "application/json" } });
        notify("Action completed successfully.", "success");
      } catch (error) {
        notify(error.message || "Action could not be completed.", "error");
      } finally {
        button.disabled = false;
      }
    });
  });
})();
