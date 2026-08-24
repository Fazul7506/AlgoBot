(() => {
  'use strict';
  if (window.__algoBotAutomationDashboard) return;
  window.__algoBotAutomationDashboard = true;

  const $ = selector => document.querySelector(selector);
  const list = value => window.AlgoBotFrontendData?.list(value) || [];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#039;' })[c]);

  function connected() {
    const state = window.AlgoBotBrokerState?.get();
    return !!state?.account && ['CONNECTED', 'SYNCING', 'READY', 'DEGRADED'].includes(state.status);
  }

  function blocked(message) {
    const root = $('[data-automation-dashboard]');
    if (!root) return;
    root.innerHTML = `<div class="ds-state"><strong>Broker connection required</strong><p>${esc(message)}</p><a class="ds-btn ds-btn--primary" href="/brokers/connect/">Connect broker</a></div>`;
  }

  async function load() {
    if (!connected()) { blocked('Automation that can affect trading state is withheld until a broker connection is established.'); return; }
    const root = $('[data-automation-dashboard]');
    if (!root) return;
    root.innerHTML = '<div class="ds-state"><strong>Synchronizing automation state…</strong><p>Loading broker-aware workflows and execution history.</p></div>';
    try {
      const [workflowResponse, historyResponse] = await Promise.all([
        window.AlgoBotFrontendData.request('/api/automation/workflows/'),
        window.AlgoBotFrontendData.request('/api/automation/history/')
      ]);
      const workflows = list(workflowResponse), history = list(historyResponse);
      root.innerHTML = `<section class="kpi-grid compact"><article class="kpi-card"><span>Workflows</span><strong>${workflows.length}</strong></article><article class="kpi-card"><span>Enabled</span><strong>${workflows.filter(w => w.enabled).length}</strong></article><article class="kpi-card"><span>Executions</span><strong>${history.length}</strong></article><article class="kpi-card"><span>Broker</span><strong>Connected</strong></article></section><section class="command-grid"><article class="panel"><div class="panel-head"><div><p class="eyebrow">Automation</p><h2>Workflows</h2></div><a href="/workspace/automation/">Manage</a></div>${workflows.length ? `<div class="mini-table">${workflows.slice(0, 12).map(w => `<div class="mini-row"><strong>${esc(w.name || w.slug || w.id)}</strong><span>${w.enabled ? 'Enabled' : 'Disabled'}</span><b>${esc(w.status || 'configured')}</b></div>`).join('')}</div>` : '<div class="ds-state"><strong>No workflows</strong><p>Create a workflow before scheduling or executing automation.</p></div>'}</article><article class="panel"><div class="panel-head"><div><p class="eyebrow">Execution</p><h2>Recent runs</h2></div></div>${history.length ? `<div class="mini-table">${history.slice(0, 12).map(item => `<div class="mini-row"><strong>${esc(item.workflow || item.workflow_id || 'Workflow')}</strong><span>${esc(item.status || 'unknown')}</span><b>${esc(item.created_at ? new Date(item.created_at).toLocaleString() : '')}</b></div>`).join('')}</div>` : '<div class="ds-state"><strong>No executions</strong><p>No automation execution has been recorded for this account.</p></div>'}</article></section>`;
    } catch (error) {
      root.innerHTML = `<div class="ds-state ds-state--error"><strong>Automation unavailable</strong><p>${esc(error.message)}</p></div>`;
    }
  }

  function boot() {
    window.AlgoBotBrokerState?.subscribe(event => {
      if (['NO_BROKER', 'DISCONNECTED'].includes(event.detail.state.status)) blocked('Broker disconnected. Trading-impacting automation is paused from this surface.');
      else if (['READY', 'CONNECTED'].includes(event.detail.state.status)) load();
    });
    load();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once:true });
  else boot();
})();
