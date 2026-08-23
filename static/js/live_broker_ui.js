(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const page = $('[data-page="trading-terminal"]');
  const connection = $('[data-global-connection]');
  let selectedSymbol = $('[data-symbol]')?.value || 'R_75';
  let busy = false;

  const csrf = () => {
    const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
  };
  const request = async (url, options = {}) => {
    const headers = { Accept: 'application/json', ...(options.headers || {}) };
    if (options.method && options.method !== 'GET') headers['X-CSRFToken'] = csrf();
    const response = await fetch(url, { credentials: 'same-origin', ...options, headers });
    const text = await response.text();
    let data = {};
    try { data = text ? JSON.parse(text) : {}; } catch (_) { data = { detail: text }; }
    if (!response.ok) throw new Error(data.detail || data.message || `Request failed (${response.status})`);
    return data;
  };
  const list = value => Array.isArray(value) ? value : (Array.isArray(value?.results) ? value.results : (Array.isArray(value?.data) ? value.data : []));
  const setText = (selector, value, root = document) => { const node = $(selector, root); if (node) node.textContent = value ?? '—'; };

  function setGlobalState(state, label) {
    if (!connection) return;
    connection.classList.toggle('connected', state === 'connected');
    connection.classList.toggle('error', state === 'error');
    const text = $('span', connection);
    if (text) text.textContent = label;
  }

  function renderAccount(account) {
    if (!account) {
      setGlobalState('error', 'No broker connected');
      setText('[data-terminal-status]', 'No broker connected', page || document);
      setText('[data-terminal-account]', 'Account: —', page || document);
      return;
    }
    const brokerName = account.broker?.name || 'Broker';
    const accountId = account.broker_account_id || account.account_id || '—';
    const type = account.account_type ? ` · ${account.account_type}` : '';
    setGlobalState('connected', `${brokerName} · ${accountId}`);
    setText('[data-terminal-status]', `Live · ${brokerName}`, page || document);
    setText('[data-terminal-account]', `Account: ${accountId}${type}`, page || document);

    const balance = $('[data-kpi="balance"]');
    if (balance) balance.textContent = `${account.currency || ''} ${Number(account.balance || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`.trim();
  }

  async function syncAccounts() {
    try {
      const accounts = list(await request('/api/brokers/accounts/'));
      const connected = accounts.filter(account => account.is_connected === true);
      const account = connected.find(item => item.is_default) || connected[0] || accounts.find(item => item.is_default) || accounts[0];
      renderAccount(account && account.is_connected !== false ? account : null);
      return account && account.is_connected !== false ? account : null;
    } catch (error) {
      setGlobalState('error', 'Broker status unavailable');
      setText('[data-terminal-status]', 'Broker status unavailable', page || document);
      return null;
    }
  }

  async function syncSymbols() {
    const select = $('[data-symbol]', page || document);
    if (!select) return;
    try {
      const symbols = list(await request('/api/market/symbols/'));
      if (!symbols.length) return;
      const current = select.value || selectedSymbol;
      select.innerHTML = '';
      symbols.slice(0, 200).forEach(item => {
        const value = item.symbol || item.underlying_symbol;
        if (!value) return;
        const option = document.createElement('option');
        option.value = value;
        option.textContent = item.display_name && item.display_name !== value ? `${item.display_name} (${value})` : value;
        select.appendChild(option);
      });
      if ([...select.options].some(option => option.value === current)) select.value = current;
      selectedSymbol = select.value || selectedSymbol;
    } catch (_) {}
  }

  async function syncLiveTick() {
    if (!page || busy) return;
    busy = true;
    const symbol = $('[data-symbol]', page)?.value || selectedSymbol;
    selectedSymbol = symbol;
    try {
      const tick = await request('/api/market/ticks/broker/', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ symbol }) });
      const quote = tick.quote ?? tick.last;
      setText('[data-bid]', tick.bid ?? quote);
      setText('[data-ask]', tick.ask ?? quote);
      const title = $('[data-chart-title]', page);
      if (title) title.textContent = `${symbol} · ${$('[data-timeframe]', page)?.value || 'M1'}`;
      const overlay = $('[data-chart-loading]', page);
      if (overlay) overlay.textContent = `Live · ${new Date().toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', second:'2-digit'})}`;
      const regime = $('[data-regime]', page);
      if (regime && regime.textContent === '—') regime.textContent = 'Live';
    } catch (_) {
      // Account state remains authoritative; a temporary public tick failure must not mark the broker disconnected.
    } finally { busy = false; }
  }

  function improveTerminalControls() {
    if (!page) return;
    const symbol = $('[data-symbol]', page);
    const timeframe = $('[data-timeframe]', page);
    symbol?.addEventListener('change', () => { selectedSymbol = symbol.value; syncLiveTick(); });
    timeframe?.addEventListener('change', () => {
      setText('[data-chart-title]', `${symbol?.value || selectedSymbol} · ${timeframe.value}`, page);
    });
    $('[data-action="terminal-refresh"]', page)?.addEventListener('click', async event => {
      const button = event.currentTarget;
      button.disabled = true;
      try { await syncAccounts(); await syncLiveTick(); } finally { button.disabled = false; }
    });
  }

  async function boot() {
    if (document.body.dataset.authenticated !== 'true') return;
    improveTerminalControls();
    await syncAccounts();
    if (page) {
      await syncSymbols();
      await syncLiveTick();
      window.setInterval(syncLiveTick, 3000);
      window.setInterval(syncAccounts, 5000);
    } else {
      window.setInterval(syncAccounts, 7000);
    }
  }

  window.addEventListener('DOMContentLoaded', boot, { once: true });
})();
