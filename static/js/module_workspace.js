(() => {
  const root = document.querySelector("[data-module-workspace]");
  if (!root) return;
  const csrf = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] || "";
  const cards = [...root.querySelectorAll("[data-resource-card]")];

  const pretty = value => JSON.stringify(value, null, 2);

  async function request(url, options = {}) {
    const response = await fetch(url, {
      credentials: "same-origin",
      headers: {"Accept": "application/json", ...(options.body ? {"Content-Type":"application/json"} : {})},
      ...options,
    });
    const text = await response.text();
    let data;
    try { data = JSON.parse(text); } catch { data = text; }
    if (!response.ok) throw new Error(typeof data === "string" ? data : (data.detail || `HTTP ${response.status}`));
    return data;
  }

  async function loadCard(card) {
    const url = card.querySelector("[data-resource-status]")?.closest(".module-card")
      ? card.querySelector("[data-resource-status]").closest(".module-card").dataset.url
      : null;
    return url;
  }

  // URLs are injected from the server as data attributes without trusting client input.
  const endpointData = [...cards].map((card, index) => {
    const endpoints = root.querySelectorAll("[data-resource-card]");
    const url = JSON.parse(document.getElementById("module-endpoints")?.textContent || "[]")[index]?.[0];
    return {card, url};
  });

  // Fallback: derive endpoint order from server-rendered script JSON.
  endpointData.forEach(({card,url}) => {
    if (!url) {
      const status = card.querySelector("[data-resource-status]");
      if (status) status.textContent = "Endpoint unavailable";
      return;
    }
    fetch(url, {credentials:"same-origin", headers:{Accept:"application/json"}})
      .then(async r => {
        const text = await r.text();
        let data; try { data = JSON.parse(text); } catch { data = text; }
        if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
        card.querySelector("[data-resource-status]").textContent = "Connected";
        card.querySelector("[data-resource-output]").textContent = pretty(data);
      })
      .catch(err => {
        card.querySelector("[data-resource-status]").textContent = "Unavailable";
        card.querySelector("[data-resource-output]").textContent = err.message;
      });
  });

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
      if (root.dataset.module === "ai" && url.endsWith("/predict/")) {
        body = {symbol:"R_100", timeframe:"M1", context:{}};
      } else if (root.dataset.module === "notifications") {
        body = {channel:"in_app", subject:"AlgoBot test alert", message:"Test notification from the operations center."};
      } else if (root.dataset.module === "automation") {
        body = {event:"manual", source:"operations-center"};
      }
      button.disabled = true;
      try {
        const result = await request(url, {
          method,
          body: method === "GET" ? undefined : JSON.stringify(body),
          headers: {"X-CSRFToken": csrf},
        });
        alert(`Action completed:\n${pretty(result).slice(0, 1500)}`);
      } catch (error) {
        alert(`Action failed: ${error.message}`);
      } finally { button.disabled = false; }
    });
  });
})();
