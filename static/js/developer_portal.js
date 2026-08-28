/* AlgoBot Developer & API portal. Browser session is used for management; generated credentials are never persisted in the DOM beyond the one-time reveal. */
(() => {
  'use strict';
  if (window.__algoBotDeveloperPortal) return;
  window.__algoBotDeveloperPortal = true;

  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => [...root.querySelectorAll(s)];
  const api = (url, options = {}, timeout = 15000) => window.AlgoBotFrontendData.request(url, options, timeout);
  const csrfHeaders = () => ({'Content-Type':'application/json'});
  const esc = value => String(value ?? '').replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#039;'}[c]));
  const pretty = value => JSON.stringify(value, null, 2);

  let keys = [];
  let webhooks = [];

  function notice(message, kind = 'info') {
    const box = $('[data-dev-notice]');
    if (!box) return;
    box.hidden = false;
    box.dataset.kind = kind;
    box.textContent = message;
  }

  function renderKeys() {
    const target = $('[data-dev-keys]');
    if (!target) return;
    target.innerHTML = keys.length ? keys.map(k => `<div class="dev-row"><div><strong>${esc(k.name)}</strong><small>${esc(k.key)}</small><span class="dev-meta">${esc((k.permissions || []).join(', '))} · ${esc(k.status)}${k.last_used ? ` · used ${esc(new Date(k.last_used).toLocaleString())}` : ''}</span></div><div class="dev-actions"><button type="button" data-rotate="${esc(k.id)}" ${k.status !== 'active' ? 'disabled' : ''}>Rotate</button><button type="button" data-revoke="${esc(k.id)}" ${k.status !== 'active' ? 'disabled' : ''}>Revoke</button><button type="button" data-delete="${esc(k.id)}">Delete</button></div></div>`).join('') : '<div class="dev-empty">No API keys yet. Create one to start integrating AlgoBot.</div>';
    $$('[data-rotate]').forEach(b => b.addEventListener('click', () => rotateKey(b.dataset.rotate)));
    $$('[data-revoke]').forEach(b => b.addEventListener('click', () => revokeKey(b.dataset.revoke)));
    $$('[data-delete]').forEach(b => b.addEventListener('click', () => deleteKey(b.dataset.delete)));
  }

  async function loadKeys() {
    try { keys = await api('/api/developer/keys/'); renderKeys(); }
    catch (error) { notice(`Developer API unavailable: ${error.message}`, 'error'); }
  }

  function revealSecret(data) {
    const panel = $('[data-secret-panel]');
    if (!panel) return;
    panel.hidden = false;
    $('[data-secret-key]', panel).textContent = data.key || '';
    $('[data-secret]', panel).textContent = data.secret || '';
    $('[data-secret-warning]', panel).textContent = data.warning || 'Save this secret now. It will not be shown again.';
    panel.scrollIntoView({behavior:'smooth', block:'nearest'});
  }

  async function createKey(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const name = String($('[name="key_name"]', form)?.value || '').trim();
    const permissions = $$('[name="permission"]:checked', form).map(x => x.value);
    if (!name) return notice('Give the API key a name.', 'error');
    try {
      const data = await api('/api/developer/keys/create/', {method:'POST', headers:csrfHeaders(), body:JSON.stringify({name, permissions})});
      revealSecret(data);
      form.reset();
      $('[value="read"]', form).checked = true;
      await loadKeys();
      notice('API key created. Copy the secret now; it is shown only once.', 'success');
    } catch (error) { notice(error.message, 'error'); }
  }

  async function rotateKey(id) {
    if (!confirm('Rotate this key? The previous secret remains valid for five minutes.')) return;
    try { const data = await api(`/api/developer/keys/${encodeURIComponent(id)}/rotate/`, {method:'POST', headers:csrfHeaders(), body:'{}'}); revealSecret(data); await loadKeys(); notice('API key rotated.', 'success'); }
    catch (error) { notice(error.message, 'error'); }
  }

  async function revokeKey(id) {
    if (!confirm('Revoke this API key? Existing clients using it will stop authenticating.')) return;
    try { await api(`/api/developer/keys/${encodeURIComponent(id)}/revoke/`, {method:'POST', headers:csrfHeaders(), body:'{}'}); await loadKeys(); notice('API key revoked.', 'success'); }
    catch (error) { notice(error.message, 'error'); }
  }

  async function deleteKey(id) {
    const key = keys.find(item => String(item.id) === String(id));
    if (!confirm(`Delete “${key?.name || 'this API key'}”? This permanently removes the credential and cannot be undone.`)) return;
    try { await api(`/api/developer/keys/${encodeURIComponent(id)}/delete/`, {method:'DELETE', headers:csrfHeaders()}); await loadKeys(); notice('API key deleted.', 'success'); }
    catch (error) { notice(error.message, 'error'); }
  }

  function renderWebhooks() {
    const target = $('[data-dev-webhooks]');
    if (!target) return;
    target.innerHTML = webhooks.length ? webhooks.map(w => `<div class="dev-row"><div><strong>${esc(w.url)}</strong><small>${esc((w.events || []).join(', ') || 'all subscribed events')}</small><span class="dev-meta">${esc(w.status)} · created ${esc(new Date(w.created_at).toLocaleString())}</span></div><div class="dev-actions"><button type="button" data-test-webhook="${esc(w.id)}">Send test</button></div></div>`).join('') : '<div class="dev-empty">No webhooks configured.</div>';
    $$('[data-test-webhook]').forEach(b => b.addEventListener('click', () => testWebhook(b.dataset.testWebhook)));
  }

  async function loadWebhooks() {
    try { webhooks = await api('/api/developer/webhooks/'); renderWebhooks(); }
    catch (error) { notice(`Webhooks unavailable: ${error.message}`, 'error'); }
  }

  async function createWebhook(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const url = String($('[name="webhook_url"]', form)?.value || '').trim();
    const events = $$('[name="webhook_event"]:checked', form).map(x => x.value);
    try {
      const data = await api('/api/developer/webhooks/create/', {method:'POST', headers:csrfHeaders(), body:JSON.stringify({url, events})});
      const panel = $('[data-webhook-secret-panel]');
      if (panel) { panel.hidden = false; $('[data-webhook-secret]').textContent = data.secret || ''; }
      form.reset();
      await loadWebhooks();
      notice('Webhook created. Save its signing secret now.', 'success');
    } catch (error) { notice(error.message, 'error'); }
  }

  async function testWebhook(id) {
    try { const result = await api(`/api/developer/webhooks/${encodeURIComponent(id)}/test/`, {method:'POST', headers:csrfHeaders(), body:JSON.stringify({event:'test',payload:{source:'algobot-developer-portal',timestamp:new Date().toISOString()}})}); notice(`Webhook test: ${pretty(result)}`, result.status === 'delivered' ? 'success' : 'info'); }
    catch (error) { notice(`Webhook test failed: ${error.message}`, 'error'); }
  }

  async function loadAnalytics() {
    try {
      const data = await api('/api/developer/analytics/');
      $('[data-metric="calls"]').textContent = Number(data.api_calls_today || 0).toLocaleString();
      $('[data-metric="p95"]').textContent = `${Number(data.latency_p95_ms || 0).toLocaleString()} ms`;
      $('[data-metric="limits"]').textContent = Number(data.rate_limit_events || 0).toLocaleString();
    } catch (error) { notice(`Analytics unavailable: ${error.message}`, 'error'); }
  }

  async function loadDocs() {
    try {
      const data = await api('/api/developer/docs/');
      $('[data-doc-json]').textContent = pretty(data);
      $('[data-api-version]').textContent = data.info?.version || 'v1';
      $('[data-endpoint-count]').textContent = `${Object.keys(data.paths || {}).length} endpoints`;
    } catch (error) { notice(`Documentation unavailable: ${error.message}`, 'error'); }
  }

  async function loadSandbox() {
    try {
      const data = await api('/api/developer/sandbox/');
      $('[data-sandbox-output]').textContent = pretty(data);
    } catch (error) { notice(`Sandbox unavailable: ${error.message}`, 'error'); }
  }

  async function boot() {
    if (!$('[data-developer-page]')) return;
    $('[data-create-key]')?.addEventListener('submit', createKey);
    $('[data-create-webhook]')?.addEventListener('submit', createWebhook);
    $('[data-refresh-developer]')?.addEventListener('click', () => Promise.all([loadKeys(), loadWebhooks(), loadAnalytics(), loadDocs()]));
    $('[data-provision-sandbox]')?.addEventListener('click', loadSandbox);
    $$('[data-copy]').forEach(button => button.addEventListener('click', async () => {
      const source = $(button.dataset.copy);
      try { await navigator.clipboard.writeText(source?.textContent || ''); notice('Copied to clipboard.', 'success'); } catch (_) { notice('Clipboard access was blocked by the browser.', 'error'); }
    }));
    await Promise.all([loadKeys(), loadWebhooks(), loadAnalytics(), loadDocs()]);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once:true}); else boot();
})();
