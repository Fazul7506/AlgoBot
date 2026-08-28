(() => {
  'use strict';
  if (window.__algoBotTradeHistory) return;
  window.__algoBotTradeHistory = true;

  const root = document.querySelector('[data-trade-history-page]');
  if (!root || !document.querySelector('[data-journal-workspace]')) return;
  const tableBody = root.querySelector('[data-history-table] tbody');
  const search = root.querySelector('[data-history-search]');
  const statusFilter = root.querySelector('[data-history-status-filter]');
  const directionFilter = root.querySelector('[data-history-direction-filter]');
  const count = root.querySelector('[data-history-count]');
  const status = root.querySelector('[data-history-status]');
  const updated = root.querySelector('[data-history-updated]');
  const message = root.querySelector('[data-history-message]');
  const exportButton = root.querySelector('[data-history-export]');
  let orders = [];
  let logs = [];

  const asList = payload => Array.isArray(payload) ? payload : (Array.isArray(payload.results) ? payload.results : []);
  const escapeHtml = value => String(value ?? '—').replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
  const formatTime = value => { const date = new Date(value); return Number.isNaN(date.getTime()) ? (value || '—') : date.toLocaleString(); };

  async function getJson(url) {
    const response = await fetch(url, {credentials: 'same-origin', headers: {Accept: 'application/json'}});
    if (!response.ok) throw new Error(`Request failed (${response.status})`);
    return response.json();
  }

  function render() {
    const needle = (search.value || '').trim().toLowerCase();
    const wantedStatus = (statusFilter.value || '').toLowerCase();
    const wantedDirection = (directionFilter.value || '').toLowerCase();
    const filtered = orders.filter(order => {
      const haystack = [order.symbol, order.strategy, order.id, order.client_order_id, order.broker_order_id].join(' ').toLowerCase();
      return (!needle || haystack.includes(needle)) && (!wantedStatus || String(order.status).toLowerCase() === wantedStatus) && (!wantedDirection || String(order.direction).toLowerCase() === wantedDirection);
    });
    count.textContent = String(orders.length);
    if (!filtered.length) { tableBody.innerHTML = '<tr><td colspan="8">No backend trade records match the current filters.</td></tr>'; return; }
    tableBody.innerHTML = filtered.map(order => {
      const latest = logs.find(log => String(log.order) === String(order.id));
      const state = latest?.status || order.status || '—';
      return `<tr><td>${escapeHtml(formatTime(order.executed_at || order.created_at))}</td><td><strong>${escapeHtml(order.symbol)}</strong></td><td>${escapeHtml(order.direction)}</td><td>${escapeHtml(order.strategy || '—')}</td><td>${escapeHtml(order.stake)}</td><td>${escapeHtml(order.price ?? '—')}</td><td><span class="status-pill">${escapeHtml(state)}</span></td><td>${escapeHtml(order.broker_order_id || order.client_order_id || '—')}</td></tr>`;
    }).join('');
  }

  function exportCsv() {
    const rows = [['time','symbol','direction','strategy','stake','price','status','broker_reference']];
    orders.forEach(order => rows.push([formatTime(order.executed_at || order.created_at), order.symbol, order.direction, order.strategy || '', order.stake, order.price ?? '', order.status, order.broker_order_id || order.client_order_id || '']));
    const csv = rows.map(row => row.map(value => `"${String(value).replace(/"/g, '""')}"`).join(',')).join('\n');
    const link = document.createElement('a');
    link.href = URL.createObjectURL(new Blob([csv], {type: 'text/csv;charset=utf-8'}));
    link.download = `algobot-trade-journal-${new Date().toISOString().slice(0,10)}.csv`;
    link.click();
    URL.revokeObjectURL(link.href);
  }

  async function load() {
    status.textContent = 'Loading';
    message.textContent = '';
    try {
      const [orderPayload, logPayload] = await Promise.all([getJson('/api/orders/?limit=250'), getJson('/api/execution/logs/?limit=250')]);
      orders = asList(orderPayload); logs = asList(logPayload);
      status.textContent = 'Connected';
      updated.textContent = new Date().toLocaleTimeString();
      render();
    } catch (error) {
      status.textContent = 'Unavailable';
      message.textContent = 'Unable to load broker-backed trade records. The journal did not fabricate fallback data.';
      tableBody.innerHTML = '<tr><td colspan="8">Trade records are temporarily unavailable.</td></tr>';
    }
  }

  [search, statusFilter, directionFilter].forEach(control => control.addEventListener('input', render));
  exportButton.addEventListener('click', exportCsv);
  load();
})();
