(() => {
  'use strict';
  if (window.__algoBotWorkflowTemplates) return;
  window.__algoBotWorkflowTemplates = true;

  const $ = selector => document.querySelector(selector);
  const list = value => window.AlgoBotFrontendData?.list(value) || [];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#039;' })[c]);
  const templates = [
    { type:'strategy_signal', name:'Strategy signal workflow', description:'Start from a strategy-signal trigger and connect broker-aware actions in the builder.' },
    { type:'risk_guard', name:'Risk guard workflow', description:'Start from a risk event and define approval/action steps without embedding broker credentials.' },
    { type:'market_event', name:'Market event workflow', description:'Start from a broker market event and add conditions/actions in the workflow definition.' }
  ];
  let workflows = [];

  function connected() {
    const state = window.AlgoBotBrokerState?.get();
    return !!state?.account && ['CONNECTED', 'SYNCING', 'READY', 'DEGRADED'].includes(state.status);
  }

  function renderBlocked(message) {
    $('[data-workflow-root]').innerHTML = `<div class="ds-state"><strong>Broker connection required</strong><p>${esc(message)}</p><a class="ds-btn ds-btn--primary" href="/brokers/connect/">Connect broker</a></div>`;
  }

  function render() {
    const root = $('[data-workflow-root]');
    if (!root) return;
    root.innerHTML = `<section class="command-grid"><article class="panel"><div class="panel-head"><div><p class="eyebrow">Templates</p><h2>Start a workflow</h2></div></div><div class="workflow-template-list">${templates.map(template => `<article class="ds-card"><h3 class="ds-card__title">${esc(template.name)}</h3><p class="ds-card__description">${esc(template.description)}</p><button class="ds-btn ds-btn--primary" data-use-template="${esc(template.type)}" type="button">Use template</button></article>`).join('')}</div></article><article class="panel"><div class="panel-head"><div><p class="eyebrow">Builder</p><h2>Create workflow</h2></div></div><form data-workflow-form class="ds-field"><label>Name<input name="name" required maxlength="180" placeholder="Workflow name"></label><label>Description<textarea name="description" rows="3"></textarea></label><label>Workflow type<select name="workflow_type">${templates.map(t => `<option value="${esc(t.type)}">${esc(t.type)}</option>`).join('')}<option value="custom">custom</option></select></label><label>Definition JSON<textarea name="definition" rows="8">{}</textarea></label><button class="ds-btn ds-btn--primary" type="submit">Create workflow</button><p class="ds-field__help">Credentials and secrets are not accepted by this browser form.</p></form></article></section><section class="panel"><div class="panel-head"><div><p class="eyebrow">Existing</p><h2>Your workflows</h2></div></div>${workflows.length ? `<div class="mini-table">${workflows.slice(0, 20).map(w => `<div class="mini-row"><strong>${esc(w.name)}</strong><span>${esc(w.workflow_type || 'custom')}</span><b>${esc(w.status || 'draft')}</b></div>`).join('')}</div>` : '<div class="ds-state"><strong>No workflows yet</strong><p>Create the first workflow from a safe template or the builder.</p></div>'}</section>`;
    root.querySelectorAll('[data-use-template]').forEach(button => button.addEventListener('click', () => {
      const template = templates.find(item => item.type === button.dataset.useTemplate);
      const form = root.querySelector('[data-workflow-form]');
      if (!form || !template) return;
      form.elements.name.value = template.name;
      form.elements.description.value = template.description;
      form.elements.workflow_type.value = template.type;
      form.elements.definition.value = '{}';
      form.elements.name.focus();
    }));
    root.querySelector('[data-workflow-form]')?.addEventListener('submit', createWorkflow);
  }

  async function load() {
    if (!connected()) { renderBlocked('Workflow creation and trading-impacting automation require an active broker connection.'); return; }
    try { workflows = list(await window.AlgoBotFrontendData.request('/api/automation/workflows/')); render(); }
    catch (error) { $('[data-workflow-root]').innerHTML = `<div class="ds-state ds-state--error"><strong>Workflow data unavailable</strong><p>${esc(error.message)}</p></div>`; }
  }

  async function createWorkflow(event) {
    event.preventDefault();
    if (!connected()) { renderBlocked('Connect a broker before creating executable workflows.'); return; }
    const form = event.currentTarget;
    let definition;
    try { definition = JSON.parse(form.elements.definition.value || '{}'); }
    catch (_) { window.alert('Definition must be valid JSON.'); return; }
    try {
      await window.AlgoBotFrontendData.request('/api/automation/workflows/', { method:'POST', headers:{ 'Content-Type':'application/json' }, body:JSON.stringify({ name:form.elements.name.value, description:form.elements.description.value, workflow_type:form.elements.workflow_type.value, definition }) });
      window.alert('Workflow created and confirmed by the backend.');
      await load();
    } catch (error) { window.alert(error.message); }
  }

  function boot() {
    window.AlgoBotBrokerState?.subscribe(event => {
      if (['NO_BROKER', 'DISCONNECTED'].includes(event.detail.state.status)) renderBlocked('Broker disconnected. Workflow builder is paused.');
      else if (['READY', 'CONNECTED'].includes(event.detail.state.status)) load();
    });
    load();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once:true });
  else boot();
})();
