(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const page = $('#trading-terminal') || $('[data-page="trading-terminal"]') || $('#chart')?.closest('.terminal, main, body');
  let selectedSymbol = $('#symbol')?.value || $('[data-symbol]')?.value || 'R_75';
  let livePoints = [];
  let busy = false;
  let lastAccounts = [];

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

  const list = value => Array.isArray(value)
    ? value
    : (Array.isArray(value?.results) ? value.results : (Array.isArray(value?.data) ? value.data : []));

  const fmt = value => value == null || value === '' || Number.isNaN(Number(value))
    ? '—'
    : Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 8 });

  function setStatus(text, bad = false) {
    const node = $('#terminal-status');
    if (!node) return;
    node.innerHTML = `<span class="status-dot" style="${bad ? 'background:#ff6b7d' : ''}"></span>${text}`;
  }

  function renderAccounts(accounts) {
    lastAccounts = accounts.filter(a => a && a.broker_account_id);
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
      const preferred = lastAccounts.find(a => a.is_default) || lastAccounts[0];
      select.value = String(preferred.id);
    }
    updateAccountCards();
  }

  function updateAccountCards() {
    const select = $('#account');
    const account = lastAccounts.find(a => String(a.id) === String(select?.value))
      || lastAccounts.find(a => a.is_default)
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
  }

  async function syncAccounts() {
    try {
      const accounts = list(await request('/api/brokers/accounts/'));
      renderAccounts(accounts);
      return accounts;
    } catch (error) {
      setStatus(`Broker account sync unavailable: ${error.message}`, true);
      return [];
    }
  }

  function renderLiveChart() {
    const chart = $('#chart');
    if (!chart || livePoints.length < 2) return;

    const width = 1000;
    const height = 330;
    const pad = 18;
    const values = livePoints.map(point => point.price);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || Math.max(Math.abs(max) * 0.0001, 1);
    const points = livePoints.map((point, index) => {
      const x = pad + (index / Math.max(1, livePoints.length - 1)) * (width - pad * 2);
      const y = height - pad - ((point.price - min) / span) * (height - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');

    const latest = values[values.length - 1];
    const first = values[0];
    const up = latest >= first;
    const stroke = up ? '#43d19a' : '#ff6b7d';
    const area = `${pad},${height - pad} ${points} ${width - pad},${height - pad}`;
    const grid = [0.25, 0.5, 0.75].map(r => {
      const y = pad + r * (height - pad * 2);
      return `<line x1="${pad}" y1="${y}" x2="${width - pad}" y2="${y}" stroke="currentColor" opacity=".08"/>`;
    }).join('');

    chart.innerHTML = `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="Live market price chart" style="width:100%;height:100%;display:block">
      ${grid}
      <polygon points="${area}" fill="${stroke}" opacity=".06"></polygon>
      <polyline points="${points}" fill="none" stroke="${stroke}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"></polyline>
      <circle cx="${points.split(' ').at(-1).split(',')[0]}" cy="${points.split(' ').at(-1).split(',')[1]}" r="4" fill="${stroke}"></circle>
      <text x="${width - pad}" y="${pad + 2}" text-anchor="end" fill="currentColor" opacity=".7" font-size="13">LIVE ${fmt(latest)}</text>
    </svg>`;
  }

  async function syncLiveTick() {
    const symbol = $('#symbol')?.value || $('[data-symbol]')?.value || selectedSymbol;
    if (!symbol || busy) return;
    selectedSymbol = symbol;
    busy = true;
    try {
      const tick = await request('/api/market/ticks/broker/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol })
      });
      const price = Number(tick.quote ?? tick.last ?? tick.price);
      if (!Number.isFinite(price)) throw new Error('Deriv returned no usable quote');
      livePoints.push({ epoch: Number(tick.epoch || Date.now() / 1000), price });
      livePoints = livePoints.slice(-120);
      renderLiveChart();

      const priceNode = $('[data-q="price"]');
      const bidNode = $('[data-q="bid"]');
      const askNode = $('[data-q="ask"]');
      if (priceNode) priceNode.textContent = fmt(price);
      if (bidNode) bidNode.textContent = fmt(tick.bid ?? price);
      if (askNode) askNode.textContent = fmt(tick.ask ?? price);

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
    $('#symbol')?.addEventListener('change', () => {
      selectedSymbol = $('#symbol').value;
      livePoints = [];
      syncLiveTick();
    });
  }

  async function boot() {
    if (document.body.dataset.authenticated !== 'true' && !$('#chart')) return;
    wireControls();
    await syncAccounts();
    await syncLiveTick();
    window.setInterval(syncLiveTick, 1500);
    window.setInterval(syncAccounts, 5000);
  }

  window.addEventListener('DOMContentLoaded', boot, { once: true });
})();
