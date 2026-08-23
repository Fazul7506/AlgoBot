(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const page = $('#trading-terminal') || $('[data-page="trading-terminal"]') || $('#chart')?.closest('.terminal, main, body');
  let selectedSymbol = $('#symbol')?.value || $('[data-symbol]')?.value || '';
  let livePoints = [];
  let busy = false;
  let lastAccounts = [];
  let accountSyncInFlight = false;

  const csrf = () => {
    const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
  };

  const request = async (url, options = {}, timeoutMs = 8000) => {
    const headers = { Accept: 'application/json', ...(options.headers || {}) };
    if (options.method && options.method !== 'GET') headers['X-CSRFToken'] = csrf();
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, { credentials: 'same-origin', ...options, headers, signal: controller.signal });
      const text = await response.text();
      let data = {};
      try { data = text ? JSON.parse(text) : {}; } catch (_) { data = { detail: text }; }
      if (response.status === 401 || response.status === 403) throw new Error('Your broker session is no longer authorised. Reconnect the broker.');
      if (!response.ok) throw new Error(data.detail || data.message || `Request failed (${response.status})`);
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('Broker request timed out');
      throw error;
    } finally {
      window.clearTimeout(timer);
    }
  };

  const list = value => Array.isArray(value)
    ? value
    : (Array.isArray(value?.results) ? value.results : (Array.isArray(value?.data) ? value.data : []));

  const fmt = value => value == null || value === '' || Number.isNaN(Number(value))
    ? '—'
    : Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 8 });

  function setGlobalConnection(text, bad = false) {
    const node = $('[data-global-connection]');
    if (!node) return;
    node.innerHTML = `<i class="${bad ? 'is-bad' : 'is-good'}"></i><span>${String(text).replace(/[&<>]/g, '')}</span>`;
    node.title = text;
  }

  function setStatus(text, bad = false) {
    const node = $('#terminal-status');
    if (!node) return;
    node.innerHTML = `<span class="status-dot${bad ? ' is-bad' : ''}"></span>${String(text).replace(/[&<>]/g, '')}`;
  }

  function renderAccounts(accounts) {
    lastAccounts = accounts.filter(a => a && a.id && a.broker_account_id);
    const select = $('#account');
    if (!select || !lastAccounts.length) return;
    const current = select.value;
    select.innerHTML = lastAccounts.map(account => {
      const type = String(account.account_type || 'demo').toUpperCase();
      const broker = account.broker?.name || 'Broker';
      return `<option value="${account.id}">${broker} · ${account.broker_account_id} · ${type} · ${account.currency || ''} ${fmt(account.balance)}</option>`;
    }).join('');
    if (lastAccounts.some(a => String(a.id) === current)) select.value = current;
    else {
      const preferred = lastAccounts.find(a => a.is_default || a.is_preferred) || lastAccounts[0];
      select.value = String(preferred.id);
    }
    updateAccountCards();
  }

  function updateAccountCards() {
    const select = $('#account');
    const account = lastAccounts.find(a => String(a.id) === String(select?.value))
      || lastAccounts.find(a => a.is_default || a.is_preferred)
      || lastAccounts[0];
    if (!account) return;
    const type = String(account.account_type || 'demo').toUpperCase();
    const label = `${account.broker?.name || 'Broker'} · ${account.broker_account_id} · ${type}`;
    const status = $('#terminal-status');
    if (status && !busy) status.innerHTML = `<span class="status-dot"></span>${label}`;
    const balance = $('#balance');
    const equity = $('#equity');
    const margin = $('#margin');
    if (balance) balance.textContent = `${account.currency || ''} ${fmt(account.balance)}`.trim();
    if (equity) equity.textContent = `${account.currency || ''} ${fmt(account.equity ?? account.balance)}`.trim();
    if (margin) margin.textContent = `${account.currency || ''} ${fmt(account.margin)}`.trim();
    const quoteBalance = $('[data-kpi="balance"]');
    if (quoteBalance) quoteBalance.textContent = `${account.currency || ''} ${fmt(account.balance)}`.trim();
    const accountLabel = $('[data-terminal-account]');
    if (accountLabel) accountLabel.textContent = `Account: ${account.broker_account_id}`;
  }

  async function syncAccounts() {
    if (accountSyncInFlight) return lastAccounts;
    accountSyncInFlight = true;
    try {
      const accounts = list(await request('/api/brokers/accounts/', {}, 6000));
      renderAccounts(accounts);
      const connected = accounts.filter(a => a.is_connected && a.status === 'active');
      if (connected.length) {
        const account = connected.find(a => a.is_default || a.is_preferred) || connected[0];
        setGlobalConnection(`${account.broker?.name || 'Broker'} · ${account.broker_account_id} · ${String(account.account_type || 'demo').toUpperCase()}`);
      } else setGlobalConnection('No broker connected', true);
      return accounts;
    } catch (error) {
      setGlobalConnection(`Broker check failed: ${error.message}`, true);
      setStatus(`Broker account sync unavailable: ${error.message}`, true);
      return [];
    } finally {
      accountSyncInFlight = false;
    }
  }

  async function discoverSymbol() {
    if (selectedSymbol) return selectedSymbol;
    try {
      const symbols = list(await request('/api/markets/symbols/', {}, 6000));
      const first = symbols.find(item => item?.symbol && item.is_active !== false && item.is_tradable !== false);
      selectedSymbol = first?.symbol || '';
      const select = $('#symbol');
      if (select && selectedSymbol) select.value = selectedSymbol;
      return selectedSymbol;
    } catch (_) {
      return '';
    }
  }

  function renderLiveChart() {
    const chart = $('#chart');
    if (!chart || livePoints.length < 2) return;
    const width = 1000, height = 330, pad = 18;
    const values = livePoints.map(point => point.price);
    const min = Math.min(...values), max = Math.max(...values);
    const span = max - min || Math.max(Math.abs(max) * 0.0001, 1);
    const points = livePoints.map((point, index) => {
      const x = pad + (index / Math.max(1, livePoints.length - 1)) * (width - pad * 2);
      const y = height - pad - ((point.price - min) / span) * (height - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    const latest = values[values.length - 1];
    const stroke = latest >= values[0] ? '#43d19a' : '#ff6b7d';
    const area = `${pad},${height - pad} ${points} ${width - pad},${height - pad}`;
    const grid = [0.25, 0.5, 0.75].map(r => {
      const y = pad + r * (height - pad * 2);
      return `<line x1="${pad}" y1="${y}" x2="${width - pad}" y2="${y}" stroke="currentColor" opacity=".08"/>`;
    }).join('');
    const last = points.split(' ').at(-1).split(',');
    chart.innerHTML = `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="Live market price chart" style="width:100%;height:100%;display:block">${grid}<polygon points="${area}" fill="${stroke}" opacity=".06"></polygon><polyline points="${points}" fill="none" stroke="${stroke}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"></polyline><circle cx="${last[0]}" cy="${last[1]}" r="4" fill="${stroke}"></circle><text x="${width - pad}" y="${pad + 2}" text-anchor="end" fill="currentColor" opacity=".7" font-size="13">LIVE ${fmt(latest)}</text></svg>`;
  }

  async function syncLiveTick() {
    const symbol = $('#symbol')?.value || $('[data-symbol]')?.value || selectedSymbol || await discoverSymbol();
    if (!symbol || busy) return;
    selectedSymbol = symbol;
    busy = true;
    try {
      const tick = await request('/api/market/ticks/broker/', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ symbol }) }, 7000);
      const price = Number(tick.quote ?? tick.last ?? tick.price);
      if (!Number.isFinite(price)) throw new Error('Broker returned no usable quote');
      livePoints.push({ epoch: Number(tick.epoch || Date.now() / 1000), price });
      livePoints = livePoints.slice(-120);
      renderLiveChart();
      $('[data-q="price"]')?.replaceChildren(document.createTextNode(fmt(price)));
      $('[data-q="bid"]')?.replaceChildren(document.createTextNode(fmt(tick.bid ?? price)));
      $('[data-q="ask"]')?.replaceChildren(document.createTextNode(fmt(tick.ask ?? price)));
      const title = $('#chart-title');
      if (title) title.textContent = `${symbol} · ${$('#timeframe')?.value || 'M1'} · LIVE`;
      setStatus(`Live market · ${symbol} · ${new Date().toLocaleTimeString()}`);
    } catch (error) {
      setStatus(`Market stream unavailable: ${error.message}`, true);
    } finally {
      busy = false;
    }
  }

  function wireControls() {
    $('#account')?.addEventListener('change', updateAccountCards);
    $('#symbol')?.addEventListener('change', () => { selectedSymbol = $('#symbol').value; livePoints = []; syncLiveTick(); });
  }

  async function boot() {
    if (document.body.dataset.authenticated !== 'true' && !$('#chart')) return;
    wireControls();
    await syncAccounts();
    await discoverSymbol();
    await syncLiveTick();
    window.setInterval(() => { if (document.visibilityState === 'visible') syncLiveTick(); }, 2500);
    window.setInterval(() => { if (document.visibilityState === 'visible') syncAccounts(); }, 20000);
  }

  window.addEventListener('DOMContentLoaded', boot, { once: true });
})();
