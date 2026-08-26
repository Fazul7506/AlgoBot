(() => {
  'use strict';

  const $ = (selector, root = document) => root.querySelector(selector);
  const table = $('[data-backtest-table]');
  if (!table) return;

  const json = async (url, options = {}) => {
    const response = await fetch(url, {
      credentials: 'same-origin',
      headers: { Accept: 'application/json', ...(options.headers || {}) },
      ...options,
    });
    const text = await response.text();
    let data = {};
    try { data = text ? JSON.parse(text) : {}; } catch { data = { detail: text }; }
    if (!response.ok) throw new Error(data.detail || data.message || `Request failed (${response.status})`);
    return data;
  };

  const arrayFrom = value => Array.isArray(value) ? value : (value?.results || value?.data || []);
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, ch => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#039;' }[ch]));
  const csrf = () => decodeURIComponent((document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/) || [])[1] || '');

  const setTableMessage = message => {
    table.innerHTML = `<tbody><tr><td colspan="7">${escapeHtml(message)}</td></tr></tbody>`;
  };

  async function loadBacktests() {
    setTableMessage('Loading backtests…');
    try {
      const rows = arrayFrom(await json('/api/backtests/'));
      const keys = ['strategy', 'symbol', 'timeframe', 'start_date', 'end_date', 'status', 'created_at'];
      table.innerHTML = `<thead><tr>${keys.map(k => `<th>${escapeHtml(k.replaceAll('_', ' '))}</th>`).join('')}</tr></thead><tbody></tbody>`;
      const body = $('tbody', table);
      if (!rows.length) {
        body.innerHTML = '<tr><td colspan="7">No backtests yet. Configure a test above and create your first run.</td></tr>';
      } else {
        body.innerHTML = rows.map(row => `<tr data-search="${escapeHtml(`${row.strategy || ''} ${row.symbol || ''}`.toLowerCase())}">${keys.map(k => `<td>${escapeHtml(row[k])}</td>`).join('')}</tr>`).join('');
      }
    } catch (error) {
      console.error('Backtest history failed', error);
      setTableMessage(`Unable to load backtest history: ${error.message}`);
    }
  }

  async function loadPaperAccount() {
    const balance = $('[data-paper-balance]');
    const equity = $('[data-paper-equity]');
    try {
      const data = await json('/api/paper/account/');
      balance.textContent = Number(data.balance ?? 0).toLocaleString();
      equity.textContent = Number(data.equity ?? data.balance ?? 0).toLocaleString();
    } catch (error) {
      console.error('Paper account failed', error);
      balance.textContent = 'Unavailable';
      equity.textContent = 'Unavailable';
    }
  }

  $('[data-backtest-search]')?.addEventListener('input', event => {
    const query = event.target.value.trim().toLowerCase();
    table.querySelectorAll('[data-search]').forEach(row => {
      row.hidden = !row.dataset.search.includes(query);
    });
  });

  $('[data-backtest-form]')?.addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const start = new Date(form.elements.start_date.value);
    const end = new Date(form.elements.end_date.value);
    if (!Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime()) || end <= start) {
      alert('End date/time must be later than start date/time.');
      return;
    }
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    try {
      const payload = Object.fromEntries(new FormData(form).entries());
      await json('/api/backtests/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
        body: JSON.stringify(payload),
      });
      alert('Backtest created and queued for processing.');
      form.reset();
      await loadBacktests();
    } catch (error) {
      alert(`Could not create backtest: ${error.message}`);
    } finally {
      button.disabled = false;
    }
  });

  $('[data-paper-start]')?.addEventListener('click', async event => {
    event.currentTarget.disabled = true;
    try {
      const result = await json('/api/paper/start/', { method: 'POST', headers: { 'X-CSRFToken': csrf() } });
      alert(`Paper trading ${result.status || 'started'}.`);
      await loadPaperAccount();
    } catch (error) {
      alert(`Could not start paper trading: ${error.message}`);
    } finally { event.currentTarget.disabled = false; }
  });

  $('[data-paper-stop]')?.addEventListener('click', async event => {
    event.currentTarget.disabled = true;
    try {
      const result = await json('/api/paper/stop/', { method: 'POST', headers: { 'X-CSRFToken': csrf() } });
      alert(`Paper trading ${result.status || 'stopped'}.`);
      await loadPaperAccount();
    } catch (error) {
      alert(`Could not stop paper trading: ${error.message}`);
    } finally { event.currentTarget.disabled = false; }
  });

  $('[data-paper-refresh]')?.addEventListener('click', loadPaperAccount);

  loadBacktests();
  loadPaperAccount();
})();
