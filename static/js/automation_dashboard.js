(() => {
  'use strict';
  if (window.__algoBotAutomationDashboard) return;
  window.__algoBotAutomationDashboard = true;

  const $ = selector => document.querySelector(selector);
  const list = value => window.AlgoBotFrontendData?.list(value) || [];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#039;' })[c]);

  function renderAccounts(accounts) {
    if (!accounts.length) {
      return '<div class="ds-state"><strong>No broker accounts connected yet</strong><p>You can design and validate workflows now. Connect a supported broker account before enabling broker actions.</p><a class="ds-btn ds-btn--primary" href="/brokers/connect/">Connect broker</a></div>';
    }
    return `<div class="mini-table">${accounts.slice(0, 20).map(account => {
      const ready = account.is_connected && account.status === 'active' && account.credential_status === 'ready';
      const broker = account.broker_name || account.broker?.name || 'Broker';
      const accountId = account.account_id || account.broker_account_id || account.id;
      const environment = String(account.account_type || 'unknown').toUpperCase();
      const freshness = account.data_freshness?.state || 'unknown';
      return `<div class="mini-row"><strong>${esc(broker)} · ${esc(accountId)}</strong><span>${ready ? 'Connected & ready' : esc(account.is_connected ? account.credential_status || 'Needs verification' : 'Disconnected')}</span><b>${esc(environment)} · ${esc(freshness)}</b></div>`;
    }).join('')}</div>`;
  }

  async function load() {
    const root = $('[data-automation-dashboard]');
    if (!root) return;
    root.innerHTML = '<div class="ds-state"><strong>Synchronizing automation state…</strong><p>Loading workflows, execution history and every broker account available to this user.</p></div>';
    try {
      const responses = await Promise.allSettled([
        window.AlgoBotFrontendData.request('/api/automation/workflows/'),
        window.AlgoBotFrontendData.request('/api/automation/history/'),
        window.AlgoBotFrontendData.request('/api/brokers/accounts/')
      ]);
      const workflows = responses[0].status === 'fulfilled' ? list(responses[0].value) : [];
      const history = responses[1].status === 'fulfilled' ? list(responses[1].value) : [];
      const accounts = responses[2].status === 'fulfilled' ? list(responses[2].value) : [];
      const connectedAccounts = accounts.filter(a => a.is_connected && a.status === 'active' && a.credential_status === 'ready');
      const failures = responses.map((r, i) => r.status === 'rejected' ? ['workflows', 'history', 'broker accounts'][i] : null).filter(Boolean);
      root.innerHTML = `
        <section class="kpi-grid compact">
          <article class="kpi-card"><span>Workflows</span><strong>${workflows.length}</strong></article>
          <article class="kpi-card"><span>Enabled</span><strong>${workflows.filter(w => w.enabled).length}</strong></article>
          <article class="kpi-card"><span>Executions</span><strong>${history.length}</strong></article>
          <article class="kpi-card"><span>Connected accounts</span><strong>${connectedAccounts.length} / ${accounts.length}</strong></article>
        </section>
        ${failures.length ? `<div class="ds-state ds-state--error"><strong>Some automation data could not be loaded</strong><p>Unavailable: ${esc(failures.join(', '))}. Other sections remain available.</p></div>` : ''}
        <section class="command-grid">
          <article class="panel">
            <div class="panel-head"><div><p class="eyebrow">Automation</p><h2>Workflows</h2></div><a href="/workspace/automation/">Manage</a></div>
            ${workflows.length ? `<div class="mini-table">${workflows.slice(0, 12).map(w => `<div class="mini-row"><strong>${esc(w.name || w.slug || w.id)}</strong><span>${w.enabled ? 'Enabled' : 'Disabled'}</span><b>${esc(w.status || 'configured')}</b></div>`).join('')}</div>` : '<div class="ds-state"><strong>No workflows</strong><p>Create and validate a workflow before scheduling or executing automation.</p><a class="ds-btn ds-btn--primary" href="/workspace/automation/">Open workflow designer</a></div>'}
          </article>
          <article class="panel">
            <div class="panel-head"><div><p class="eyebrow">Multi-broker</p><h2>Broker accounts</h2></div><a href="/brokers/marketplace/">Manage brokers</a></div>
            ${renderAccounts(accounts)}
          </article>
          <article class="panel">
            <div class="panel-head"><div><p class="eyebrow">Execution</p><h2>Recent runs</h2></div></div>
            ${history.length ? `<div class="mini-table">${history.slice(0, 12).map(item => `<div class="mini-row"><strong>${esc(item.workflow || item.workflow_id || 'Workflow')}</strong><span>${esc(item.status || 'unknown')}</span><b>${esc(item.created_at ? new Date(item.created_at).toLocaleString() : item.started_at ? new Date(item.started_at).toLocaleString() : '')}</b></div>`).join('')}</div>` : '<div class="ds-state"><strong>No executions</strong><p>No automation execution has been recorded for this account.</p></div>'}
          </article>
        </section>`;
    } catch (error) {
      root.innerHTML = `<div class="ds-state ds-state--error"><strong>Automation unavailable</strong><p>${esc(error.message)}</p><button class="btn" type="button" data-automation-retry>Retry</button></div>`;
      root.querySelector('[data-automation-retry]')?.addEventListener('click', load, { once: true });
    }
  }

  function boot() {
    document.querySelector('[data-automation-refresh]')?.addEventListener('click', load);
    window.AlgoBotBrokerState?.subscribe(() => load());
    load();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once:true });
  else boot();
})();
