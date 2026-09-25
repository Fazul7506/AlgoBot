(() => {
  'use strict';
  if (window.__algoBotTradeHistoryV2) return;
  window.__algoBotTradeHistoryV2 = true;

  const root = document.querySelector('[data-trade-history-page]');
  if (!root || !window.AlgoBotAPI?.apiClient) return;

  const $ = selector => root.querySelector(selector);
  const tbody = $('[data-history-table] tbody');
  const state = $('[data-history-state]');
  const syncTime = $('[data-history-sync-time]');
  const currency = $('[data-history-currency]');
  const message = $('[data-history-message]');
  const prev = $('[data-history-prev]');
  const next = $('[data-history-next]');
  const pageLabel = $('[data-history-page]');
  const refresh = $('[data-history-refresh]');
  const apply = $('[data-history-apply]');
  const exportButton = $('[data-history-export]');
  let page = 1;
  let lastPayload = null;

  const esc = value => String(value ?? '—').replace(/[&<>'"]/g, ch => ({
    '&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'
  }[ch]));
  const money = (value, code) => value == null ? '—' : `${esc(value)} ${esc(code || '')}`.trim();
  const time = value => {
    if (!value) return '—';
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString();
  };

  function params(pageNumber = 1, refreshBroker = true) {
    const p = new URLSearchParams({page: String(pageNumber), page_size: '25'});
    const q = $('[data-history-search]').value.trim();
    const symbol = $('[data-history-symbol]').value.trim();
    const status = $('[data-history-status-filter]').value;
    const direction = $('[data-history-direction-filter]').value;
    const dateFrom = $('[data-history-date-from]').value;
    const dateTo = $('[data-history-date-to]').value;
    if (q) p.set('q', q);
    if (symbol) p.set('symbol', symbol);
    if (status) p.set('status', status);
    if (direction) p.set('direction', direction);
    if (dateFrom) p.set('date_from', dateFrom);
    if (dateTo) p.set('date_to', dateTo);
    if (!refreshBroker) p.set('refresh', '0');
    return p;
  }

  function renderRows(rows) {
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="12">No broker trades match the current filters.</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map((row, index) => {
      const detailId = `trade-detail-${row.id}-${index}`;
      return `
        <tr>
          <td>${esc(time(row.broker_timestamp || row.purchase_time))}</td>
          <td><strong>${esc(row.display_name || row.symbol)}</strong><br><small>${esc(row.symbol)}</small></td>
          <td>${esc(row.contract_type)}</td>
          <td>${esc(row.direction)}</td>
          <td class="num">${money(row.stake, row.currency)}</td>
          <td class="num">${money(row.entry_price ?? row.buy_price, row.currency)}</td>
          <td class="num">${money(row.exit_price ?? row.sell_price, row.currency)}</td>
          <td class="num">${money(row.payout, row.currency)}</td>
          <td class="num">${money(row.profit_loss, row.currency)}</td>
          <td><span class="trade-history-status">${esc(row.status)}</span></td>
          <td class="id">${esc(row.broker_contract_id || row.broker_transaction_id)}</td>
          <td><button class="btn" type="button" data-expand="${esc(detailId)}" aria-expanded="false" aria-controls="${esc(detailId)}">View</button></td>
        </tr>
        <tr id="${esc(detailId)}" class="trade-history-detail">
          <td colspan="12">
            <div class="trade-history-detail-grid">
              <div><span>Contract ID</span><strong>${esc(row.broker_contract_id)}</strong></div>
              <div><span>Transaction ID</span><strong>${esc(row.broker_transaction_id)}</strong></div>
              <div><span>Reference ID</span><strong>${esc(row.reference_id)}</strong></div>
              <div><span>Currency</span><strong>${esc(row.currency)}</strong></div>
              <div><span>Purchase</span><strong>${esc(time(row.purchase_time))}</strong></div>
              <div><span>Settlement</span><strong>${esc(time(row.settlement_time))}</strong></div>
              <div><span>Expiry</span><strong>${esc(time(row.expiry_time))}</strong></div>
              <div><span>AI analysis</span><strong>${row.ai ? `${esc(row.ai.prediction)} · ${esc(row.ai.confidence)}% · AI only` : 'No linked AI analysis'}</strong></div>
            </div>
          </td>
        </tr>`;
    }).join('');
    root.querySelectorAll('[data-expand]').forEach(button => {
      button.addEventListener('click', () => {
        const target = document.getElementById(button.dataset.expand);
        const expanded = button.getAttribute('aria-expanded') === 'true';
        button.setAttribute('aria-expanded', String(!expanded));
        target?.classList.toggle('is-expanded', !expanded);
      });
    });
  }

  function renderMeta(payload) {
    const stateValue = payload.state || 'unknown';
    state.textContent = stateValue === 'success' ? 'Broker synchronized' :
      stateValue === 'partial' ? 'Partial broker data' :
      stateValue === 'cached' ? 'Cached broker data' :
      stateValue === 'stale' ? 'Stale · broker unavailable' :
      stateValue === 'empty' ? 'No broker trades' :
      stateValue === 'authentication_failed' ? 'Authentication required' :
      stateValue === 'unavailable' ? 'Broker unavailable' : stateValue;
    if (payload.account) {
      currency.textContent = `Currency: ${payload.account.currency || '—'}`;
      syncTime.textContent = `Last synchronization: ${time(payload.account.last_synced_at)}`;
    }
    message.textContent = payload.error
      ? `${payload.error.detail || 'Broker history synchronization failed.'} Existing rows, if any, are explicitly marked stale.`
      : stateValue === 'empty' ? 'Deriv confirmed that no matching trade records are available.' : '';
    const current = payload.results || [];
    const currentPage = Number(payload.current_page || page);
    const totalPages = Number(payload.total_pages || 1);
    pageLabel.textContent = `Page ${currentPage} of ${totalPages}`;
    prev.disabled = !payload.previous;
    next.disabled = !payload.next;
  }

  async function load(targetPage = 1, refreshBroker = true) {
    page = targetPage;
    refresh.disabled = true;
    state.textContent = 'Synchronizing…';
    message.textContent = '';
    tbody.innerHTML = '<tr><td colspan="12">Retrieving authoritative Deriv history…</td></tr>';
    try {
      const payload = await window.AlgoBotAPI.apiClient.get(`/api/trade-history/?${params(page, refreshBroker).toString()}`);
      lastPayload = payload;
      renderRows(payload.results || []);
      renderMeta(payload);
    } catch (error) {
      const payload = error?.payload || {};
      state.textContent = error?.status === 401 ? 'Authentication required' : 'Broker unavailable';
      message.textContent = payload.detail || payload.error?.detail || 'Broker Trade History could not be retrieved. No fabricated records were generated.';
      tbody.innerHTML = '<tr><td colspan="12">Trade history is unavailable.</td></tr>';
      prev.disabled = true;
      next.disabled = true;
    } finally {
      refresh.disabled = false;
    }
  }

  function exportCsv() {
    const rows = lastPayload?.results || [];
    if (!rows.length) return;
    const header = ['time','symbol','contract','direction','stake','entry','exit','payout','profit_loss','status','contract_id','transaction_id'];
    const data = rows.map(row => [
      time(row.broker_timestamp || row.purchase_time), row.symbol, row.contract_type, row.direction,
      row.stake ?? '', row.entry_price ?? row.buy_price ?? '', row.exit_price ?? row.sell_price ?? '',
      row.payout ?? '', row.profit_loss ?? '', row.status, row.broker_contract_id ?? '', row.broker_transaction_id ?? ''
    ]);
    const csv = [header, ...data].map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(',')).join('\n');
    const url = URL.createObjectURL(new Blob([csv], {type:'text/csv;charset=utf-8'}));
    const link = document.createElement('a');
    link.href = url;
    link.download = `algobot-deriv-trade-history-${new Date().toISOString().slice(0,10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  [refresh, apply].forEach(control => control.addEventListener('click', () => load(1, true)));
  prev.addEventListener('click', () => load(Math.max(1, page - 1), false));
  next.addEventListener('click', () => load(page + 1, false));
  exportButton.addEventListener('click', exportCsv);
  load();
})();
