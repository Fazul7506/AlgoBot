(() => {
  'use strict';
  if (window.__algoBotWorkflowTemplates) return;
  window.__algoBotWorkflowTemplates = true;

  const $ = selector => document.querySelector(selector);
  const list = value => window.AlgoBotFrontendData?.list(value) || [];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#039;' })[c]);
  const templates = [
    { type:'strategy_signal', name:'Strategy signal workflow', description:'React to strategy signals and route actions through explicit broker-account selection.', triggerType:'strategy_signal', event:'StrategySignal' },
    { type:'risk_guard', name:'Risk guard workflow', description:'React to risk alerts. Unsupported actions remain visibly pending until their adapters are implemented.', triggerType:'risk_alert', event:'RiskAlert' },
    { type:'market_event', name:'Market event workflow', description:'Start from a market event and define a broker-aware action.', triggerType:'market_event', event:'MarketEvent' },
    { type:'custom', name:'Custom workflow', description:'Build a custom event-triggered automation.', triggerType:'manual', event:'manual' }
  ];
  const triggerTypes = [
    ['manual', 'Manual / API'], ['market_event', 'Market event'], ['strategy_signal', 'Strategy signal'],
    ['trade_executed', 'Trade executed'], ['trade_closed', 'Trade closed'], ['risk_alert', 'Risk alert'],
    ['broker_connected', 'Broker connected'], ['broker_disconnected', 'Broker disconnected'],
    ['margin_warning', 'Margin warning'], ['drawdown_trigger', 'Drawdown trigger'], ['price_level', 'Price level'],
    ['indicator_cross', 'Indicator cross'], ['smc_event', 'Smart Money Concept event'], ['time_schedule', 'Time schedule']
  ];
  const actionTypes = [
    ['execute_trade', 'Execute trade (broker-backed)'], ['close_trade', 'Close trade'], ['pause_strategy', 'Pause strategy'],
    ['resume_strategy', 'Resume strategy'], ['start_strategy', 'Start strategy'], ['stop_strategy', 'Stop strategy'],
    ['activate_risk_profile', 'Activate risk profile'], ['deactivate_risk_profile', 'Deactivate risk profile'],
    ['send_notification', 'Send notification'], ['execute_ai_prediction', 'Execute AI prediction'],
    ['start_backtest', 'Start backtest'], ['deploy_strategy', 'Deploy strategy'], ['retrain_ai_model', 'Retrain AI model'],
    ['export_report', 'Export report'], ['webhook_call', 'Webhook call']
  ];
  let workflows = [];
  let accounts = [];

  function readyAccounts() {
    return accounts.filter(a => a.is_connected && a.status === 'active' && a.credential_status === 'ready');
  }

  function accountOptions() {
    const ready = readyAccounts();
    if (!ready.length) return '<option value="">No connected, credential-ready accounts</option>';
    return '<option value="">Choose a broker account</option>' + ready.map(a => {
      const brokerType = a.broker?.type || '';
      return `<option value="${esc(a.id)}" data-broker-type="${esc(brokerType)}">${esc(a.broker_name || a.broker?.name || 'Broker')} · ${esc(a.account_id || a.broker_account_id || a.id)} · ${esc(a.account_type || 'unknown')}</option>`;
    }).join('');
  }

  function workflowRows() {
    if (!workflows.length) return '<div class="ds-state"><strong>No workflows yet</strong><p>Create a workflow below. Workflow configuration is available before broker onboarding; broker actions require a connected, eligible account.</p></div>';
    return `<div class="mini-table">${workflows.slice(0, 20).map(w => `<div class="mini-row workflow-row"><strong>${esc(w.name)}</strong><span>${esc(w.workflow_type || 'custom')} · ${esc(w.status || 'draft')}</span><b>${w.enabled ? 'Enabled' : 'Paused'}</b><div class="workflow-row__actions"><button class="btn" type="button" data-workflow-action="activate" data-workflow-id="${esc(w.id)}">Activate</button><button class="btn" type="button" data-workflow-action="pause" data-workflow-id="${esc(w.id)}">Pause</button></div></div>`).join('')}</div>`;
  }

  function render() {
    const root = $('[data-workflow-root]');
    if (!root) return;
    root.innerHTML = `
      <section class="automation-safety panel"><strong>Broker and execution safety</strong><p>Every trade action selects an explicit account. The backend rechecks ownership, connection eligibility, live-trading policy, market-data freshness, idempotency and risk approval. No preferred/default account is silently selected.</p></section>
      <section class="command-grid">
        <article class="panel">
          <div class="panel-head"><div><p class="eyebrow">Templates</p><h2>Start a workflow</h2></div></div>
          <div class="workflow-template-list">${templates.map(t => `<article class="ds-card"><h3 class="ds-card__title">${esc(t.name)}</h3><p class="ds-card__description">${esc(t.description)}</p><button class="ds-btn ds-btn--primary" data-use-template="${esc(t.type)}" type="button">Use template</button></article>`).join('')}</div>
        </article>
        <article class="panel">
          <div class="panel-head"><div><p class="eyebrow">Workflow builder</p><h2>Create automation</h2></div></div>
          <form data-workflow-form class="ds-field">
            <label>Name<input name="name" required maxlength="180" placeholder="Workflow name"></label>
            <label>Description<textarea name="description" rows="2" maxlength="2000"></textarea></label>
            <label>Workflow type<select name="workflow_type">${templates.map(t => `<option value="${esc(t.type)}">${esc(t.name)}</option>`).join('')}</select></label>
            <label>Trigger<select name="trigger_type">${triggerTypes.map(t => `<option value="${esc(t[0])}">${esc(t[1])}</option>`).join('')}</select></label>
            <label>Trigger event<input name="trigger_event" required maxlength="120" value="manual"></label>
            <label>Action<select name="action_type">${actionTypes.map(t => `<option value="${esc(t[0])}">${esc(t[1])}</option>`).join('')}</select></label>
            <div data-trade-fields>
              <label>Broker account<select name="account_id">${accountOptions()}</select></label>
              <label>Market symbol<input name="symbol" maxlength="80" value="R_100" placeholder="Broker-supported symbol"></label>
              <label>Direction<select name="direction"><option value="BUY">BUY (CALL contract)</option><option value="SELL">SELL (PUT contract)</option><option value="RISE">RISE</option><option value="FALL">FALL</option></select></label>
              <label>Stake<input name="stake" type="number" min="0.01" step="0.01" value="1"></label>
              <label>Contract type<select name="contract_type"><option value="CALL">CALL</option><option value="PUT">PUT</option><option value="RISE">RISE</option><option value="FALL">FALL</option><option value="ACCU">Accumulator</option><option value="MULTUP">Multiplier up</option><option value="MULTDOWN">Multiplier down</option></select></label>
              <label><input name="use_martingale" type="checkbox"> Enable bounded Martingale progression</label>
              <div data-martingale-fields hidden>
                <label>Martingale base stake<input name="martingale_base_stake" type="number" min="0.01" step="0.01" value="1"></label>
                <label>Loss multiplier<input name="martingale_multiplier" type="number" min="1.01" step="0.1" value="2"></label>
                <label>Maximum consecutive losses<input name="martingale_max_steps" type="number" min="1" max="20" step="1" value="5"></label>
                <label>Maximum stake cap<input name="martingale_max_stake" type="number" min="0.01" step="0.01" value="16"></label>
                <p class="ds-field__help">After a loss, the next stake increases by the configured multiplier. It waits for the previous position to close and its profit/loss to reconcile. It stops at the loss-step limit or stake cap.</p>
              </div>
              <p class="ds-field__help">Trade parameters are sent to the backend for validation. A saved workflow is not proof that a broker order was executed.</p>
            </div>
            <label>Optional one-time run at <input name="schedule_at" type="datetime-local"></label>
            <button class="ds-btn ds-btn--primary" type="submit">Validate and create workflow</button>
            <p class="ds-field__help">Credentials and API secrets are never accepted in this workflow definition. Recurring schedules and unsupported action adapters are not enabled yet.</p>
          </form>
          <div data-workflow-feedback aria-live="polite"></div>
        </article>
      </section>
      <section class="panel"><div class="panel-head"><div><p class="eyebrow">Multi-broker</p><h2>Available broker accounts</h2></div><a href="/brokers/marketplace/">Manage brokers</a></div>${accounts.length ? `<div class="mini-table">${accounts.map(a => `<div class="mini-row"><strong>${esc(a.broker_name || a.broker?.name || 'Broker')} · ${esc(a.account_id || a.broker_account_id || a.id)}</strong><span>${a.is_connected && a.credential_status === 'ready' ? 'Connected & ready' : esc(a.is_connected ? a.credential_status || 'Needs verification' : 'Disconnected')}</span><b>${esc(String(a.account_type || 'unknown').toUpperCase())}</b></div>`).join('')}</div>` : '<div class="ds-state"><strong>No broker accounts found</strong><p>You can still design workflows. Connect a supported broker before executing broker actions.</p><a class="ds-btn ds-btn--primary" href="/brokers/connect/">Connect broker</a></div>'}</section>
      <section class="panel"><div class="panel-head"><div><p class="eyebrow">Existing</p><h2>Your workflows</h2></div></div>${workflowRows()}</section>`;
    const form = root.querySelector('[data-workflow-form]');
    const tradeFields = root.querySelector('[data-trade-fields]');
    const martingaleFields = root.querySelector('[data-martingale-fields]');
    const refreshTradeFields = () => {
      const trade = form.elements.action_type.value === 'execute_trade';
      tradeFields.hidden = !trade;
      martingaleFields.hidden = !trade || !form.elements.use_martingale.checked;
    };
    form.elements.action_type.addEventListener('change', refreshTradeFields);
    form.elements.use_martingale.addEventListener('change', refreshTradeFields);
    refreshTradeFields();

    root.querySelectorAll('[data-use-template]').forEach(button => button.addEventListener('click', () => {
      const template = templates.find(item => item.type === button.dataset.useTemplate);
      if (!template) return;
      form.elements.name.value = template.name;
      form.elements.description.value = template.description;
      form.elements.workflow_type.value = template.type;
      form.elements.trigger_type.value = template.triggerType;
      form.elements.trigger_event.value = template.event;
      form.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }));
    form.addEventListener('submit', createWorkflow);
    root.querySelectorAll('[data-workflow-action]').forEach(button => button.addEventListener('click', () => updateWorkflow(button.dataset.workflowId, button.dataset.workflowAction)));
  }

  async function load() {
    const root = $('[data-workflow-root]');
    if (!root) return;
    root.innerHTML = '<div class="ds-state"><strong>Loading workflow builder…</strong><p>Loading all user-owned workflows and available broker accounts.</p></div>';
    const results = await Promise.allSettled([
      window.AlgoBotFrontendData.request('/api/automation/workflows/'),
      window.AlgoBotFrontendData.request('/api/brokers/accounts/')
    ]);
    if (results[0].status === 'rejected') {
      root.innerHTML = `<div class="ds-state ds-state--error"><strong>Workflow data unavailable</strong><p>${esc(results[0].reason?.message || 'Could not load workflows.')}</p><button class="btn" type="button" data-workflow-retry>Retry</button></div>`;
      root.querySelector('[data-workflow-retry]')?.addEventListener('click', load, { once: true });
      return;
    }
    workflows = list(results[0].value);
    accounts = results[1].status === 'fulfilled' ? list(results[1].value) : [];
    render();
    if (results[1].status === 'rejected') {
      const feedback = $('[data-workflow-feedback]');
      if (feedback) feedback.innerHTML = '<p class="ds-field__help">Broker account data is temporarily unavailable. Non-trading workflow design remains available.</p>';
    }
  }

  function buildDefinition(form) {
    const triggerType = form.elements.trigger_type.value;
    const triggerEvent = form.elements.trigger_event.value.trim();
    const actionType = form.elements.action_type.value;
    const configuration = { type: actionType };
    if (actionType === 'execute_trade') {
      const option = form.elements.account_id.selectedOptions[0];
      if (!form.elements.account_id.value || !option?.dataset.brokerType) throw new Error('Choose a connected, credential-ready broker account for trade execution.');
      const stake = Number(form.elements.stake.value);
      if (!Number.isFinite(stake) || stake <= 0) throw new Error('Stake must be a positive finite number.');
      configuration.account_id = Number(form.elements.account_id.value);
      configuration.broker_type = option.dataset.brokerType;
      configuration.symbol = form.elements.symbol.value.trim();
      configuration.direction = form.elements.direction.value;
      configuration.stake = stake;
      configuration.contract_type = form.elements.contract_type.value;
      if (!configuration.symbol) throw new Error('Market symbol is required for trade execution.');
      configuration.routing_context = { source: 'automation_workflow' };
      if (form.elements.use_martingale.checked) {
        const baseStake = Number(form.elements.martingale_base_stake.value);
        const multiplier = Number(form.elements.martingale_multiplier.value);
        const maxSteps = Number(form.elements.martingale_max_steps.value);
        const maxStake = Number(form.elements.martingale_max_stake.value);
        if (![baseStake, multiplier, maxStake].every(Number.isFinite) || baseStake <= 0 || multiplier <= 1 || maxSteps < 1 || maxSteps > 20 || maxStake < baseStake) {
          throw new Error('Martingale requires a positive base stake, multiplier above 1, 1–20 loss steps, and max stake at least the base stake.');
        }
        configuration.stake = baseStake;
        configuration.martingale = { base_stake: baseStake, multiplier, max_steps: maxSteps, max_stake: maxStake };
      }
    }
    return {
      trigger: { type: triggerType, event: triggerEvent },
      nodes: [{ id: 'action-1', type: 'action', configuration }]
    };
  }

  async function createWorkflow(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const feedback = $('[data-workflow-feedback]');
    try {
      const definition = buildDefinition(form);
      feedback.innerHTML = '<p class="ds-field__help">Validating workflow definition…</p>';
      await window.AlgoBotFrontendData.request('/api/automation/workflows/validate/', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ definition })
      });
      const created = await window.AlgoBotFrontendData.request('/api/automation/workflows/', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: form.elements.name.value.trim(), description: form.elements.description.value.trim(),
          workflow_type: form.elements.workflow_type.value, definition,
          approval_policy: { allow_live_automation: false }
        })
      });
      await window.AlgoBotFrontendData.request(`/api/automation/workflows/${encodeURIComponent(created.id)}/activate/`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      const scheduleValue = form.elements.schedule_at.value;
      if (scheduleValue) {
        const when = new Date(scheduleValue);
        if (Number.isNaN(when.getTime()) || when.getTime() <= Date.now()) throw new Error('Choose a one-time schedule in the future.');
        await window.AlgoBotFrontendData.request('/api/automation/schedule/', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ workflow: created.id, schedule_type: 'one_time', next_execution: when.toISOString() })
        });
      }
      feedback.innerHTML = '<p class="ds-field__help">Workflow validated and saved. Check its execution history for the real broker/action result.</p>';
      form.reset();
      form.elements.trigger_event.value = 'manual';
      form.elements.symbol.value = 'R_100';
      form.elements.stake.value = '1';
      await load();
    } catch (error) {
      feedback.innerHTML = `<div class="ds-state ds-state--error"><strong>Workflow was not fully configured</strong><p>${esc(error.message || 'Request failed')}</p></div>`;
    }
  }

  async function updateWorkflow(id, action) {
    const feedback = $('[data-workflow-feedback]');
    try {
      await window.AlgoBotFrontendData.request(`/api/automation/workflows/${encodeURIComponent(id)}/${action}/`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}'
      });
      if (feedback) feedback.innerHTML = `<p class="ds-field__help">Workflow ${esc(action)} request completed.</p>`;
      await load();
    } catch (error) {
      if (feedback) feedback.innerHTML = `<div class="ds-state ds-state--error"><strong>Workflow action failed</strong><p>${esc(error.message)}</p></div>`;
    }
  }

  function boot() {
    window.AlgoBotBrokerState?.subscribe(() => load());
    load();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
