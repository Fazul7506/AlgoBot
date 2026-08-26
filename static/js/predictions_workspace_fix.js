(() => {
  const page = document.querySelector('[data-page="core-predictions"]');
  if (!page) return;

  const getJSON = async (url) => {
    const r = await fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
    const text = await r.text();
    let data = {};
    try { data = text ? JSON.parse(text) : {}; } catch { data = { detail: text }; }
    if (!r.ok) throw new Error(data.detail || data.message || `Request failed (${r.status})`);
    return data;
  };
  const list = value => Array.isArray(value) ? value : (Array.isArray(value?.results) ? value.results : (Array.isArray(value?.data) ? value.data : []));
  const money = value => value == null || value === '' ? '—' : Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const pct = value => value == null || value === '' ? '0.0%' : `${Number(value).toFixed(1)}%`;

  async function loadAccount() {
    const [overview, accounts] = await Promise.allSettled([
      getJSON('/api/dashboard/account_overview/'),
      getJSON('/api/brokers/accounts/')
    ]);
    const data = overview.status === 'fulfilled' ? (overview.value.data || {}) : {};
    const stats = data.trading_stats || {};
    const accountRows = accounts.status === 'fulfilled' ? list(accounts.value) : [];
    const selected = accountRows.find(a => a.is_default || a.is_preferred) || accountRows[0];
    const account = selected || data.account || {};
    const set = (name, value) => { const el = page.querySelector(`[data-kpi="${name}"]`); if (el) el.textContent = value; };
    set('balance', account.balance != null ? `${account.currency || data.account?.currency || 'USD'} ${money(account.balance)}` : '—');
    set('positions', stats.open_trades ?? 0);
    set('winrate', pct(stats.win_rate));
    set('pnl', money(stats.total_pnl));
    const banner = page.querySelector('[data-workspace-banner]');
    const status = page.querySelector('[data-workspace-status]');
    const message = page.querySelector('[data-workspace-message]');
    if (status) status.textContent = 'Backend connected';
    if (message) message.textContent = selected || data.account?.account_id ? `Live account ${account.account_id || account.broker_account_id || 'connected'} is available.` : 'No connected broker account is available.';
    if (banner) banner.dataset.backendState = 'connected';
  }

  async function loadPredictions() {
    const table = page.querySelector('[data-enterprise-table]');
    const activity = page.querySelector('[data-activity-list]');
    try {
      const [predictions, recommendations] = await Promise.all([
        getJSON('/api/ai/predictions/'),
        getJSON('/api/ai/recommendations/')
      ]);
      const rows = list(predictions);
      if (table) {
        const body = table.querySelector('tbody');
        const head = table.querySelector('thead');
        if (!rows.length) {
          if (head) head.innerHTML = '';
          if (body) body.innerHTML = '<tr class="empty-row"><td>No AI predictions have been generated yet.</td></tr>';
        } else {
          const keys = [...new Set(rows.flatMap(x => Object.keys(x || {})))].slice(0, 8);
          if (head) head.innerHTML = `<tr>${keys.map(k => `<th>${k.replaceAll('_',' ')}</th>`).join('')}</tr>`;
          if (body) body.innerHTML = rows.slice(0, 50).map(row => `<tr>${keys.map(k => `<td>${String(typeof row[k] === 'object' ? JSON.stringify(row[k]) : row[k] ?? '—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]))}</td>`).join('')}</tr>`).join('');
        }
      }
      const recs = list(recommendations).slice(0, 5);
      if (activity) activity.innerHTML = recs.length ? recs.map(r => `<li><span class="dot ok"></span><div><strong>${r.symbol || r.action || r.recommendation || 'AI recommendation'}</strong><small>${r.created_at || r.updated_at || 'Live'}</small></div></li>`).join('') : '<li class="empty-state">No AI recommendations returned yet.</li>';
    } catch (e) {
      if (activity) activity.innerHTML = `<li class="empty-state">AI records unavailable: ${e.message}</li>`;
    }
  }

  const run = () => Promise.allSettled([loadAccount(), loadPredictions()]);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run, { once: true }); else run();
})();
