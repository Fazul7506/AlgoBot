(() => {
  'use strict';
  const root = document.querySelector('[data-api-key-list]');
  if (!root) return;
  const dialog = document.querySelector('[data-api-key-dialog]');
  const secretDialog = document.querySelector('[data-api-secret-dialog]');
  const form = document.querySelector('[data-api-key-form]');
  const count = document.querySelector('[data-api-key-count]');
  const keyNode = document.querySelector('[data-api-key-value]');
  const secretNode = document.querySelector('[data-api-secret]');
  const copyKeyButton = document.querySelector('[data-copy-api-key]');
  const copySecretButton = document.querySelector('[data-copy-api-secret]');
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const endpoint = '/api/developer/keys/';
  let keyValue = '';
  let secretValue = '';
  let secretVisible = false;

  const request = async (url, options = {}) => {
    const response = await fetch(url, { credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf, ...(options.headers || {}) }, ...options });
    const data = response.status === 204 ? null : await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data?.detail || 'Request failed');
    return data;
  };
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const statusClass = status => ({active:'ready', revoked:'danger', expired:'danger', inactive:'degraded'}[status] || 'pending');

  const clearSecret = () => {
    keyValue = '';
    secretValue = '';
    secretVisible = false;
    if (keyNode) keyNode.textContent = '—';
    if (secretNode) secretNode.textContent = '••••••••••••••••••••';
    if (copyKeyButton) { copyKeyButton.disabled = true; copyKeyButton.textContent = 'Copy key'; }
    if (copySecretButton) { copySecretButton.disabled = true; copySecretButton.textContent = 'Copy secret'; }
  };

  const load = async () => {
    root.innerHTML = '<div class="ds-state"><strong>Loading keys</strong><p>Fetching your developer credentials securely.</p></div>';
    try {
      const keys = await request(endpoint);
      count.textContent = `${keys.length} key${keys.length === 1 ? '' : 's'}`;
      if (!keys.length) {
        root.innerHTML = '<div class="ds-state"><strong>No API keys yet</strong><p>Create a key when you are ready to connect a bot, script or integration.</p><button class="ds-btn ds-btn--primary" type="button" data-empty-create>Create key</button></div>';
        root.querySelector('[data-empty-create]').onclick = () => dialog?.showModal();
        return;
      }
      root.innerHTML = keys.map(key => `
        <article class="api-key-row" data-key-id="${escapeHtml(key.id)}">
          <div class="api-key-identity"><span class="key-glyph material-symbols-rounded">key</span><div><strong>${escapeHtml(key.name)}</strong><code>${escapeHtml(key.key)}</code></div></div>
          <div class="api-key-meta"><span class="ds-status ds-status--${statusClass(key.status)}">${escapeHtml(key.status)}</span><span>${key.permissions?.map(escapeHtml).join(' · ') || 'read'}</span><small>Created ${new Date(key.created_at).toLocaleDateString()}</small></div>
          <div class="api-key-actions">
            ${key.status === 'active' ? `<button class="ds-btn" type="button" data-rotate="${escapeHtml(key.id)}">Rotate</button>` : ''}
            ${key.status === 'active' ? `<button class="ds-btn ds-btn--danger" type="button" data-revoke="${escapeHtml(key.id)}">Revoke</button>` : ''}
            <button class="ds-btn ds-btn--danger" type="button" data-delete="${escapeHtml(key.id)}" data-name="${escapeHtml(key.name)}">Delete</button>
          </div>
        </article>`).join('');
      root.querySelectorAll('[data-rotate]').forEach(button => button.onclick = () => rotate(button.dataset.rotate));
      root.querySelectorAll('[data-revoke]').forEach(button => button.onclick = () => revoke(button.dataset.revoke));
      root.querySelectorAll('[data-delete]').forEach(button => button.onclick = () => remove(button.dataset.delete, button.dataset.name));
    } catch (error) {
      count.textContent = 'Unavailable';
      root.innerHTML = `<div class="ds-state ds-state--error"><strong>Could not load API keys</strong><p>${escapeHtml(error.message)}</p><button class="ds-btn" type="button" data-retry>Retry</button></div>`;
      root.querySelector('[data-retry]').onclick = load;
    }
  };

  const showCredentials = (key, secret) => {
    clearSecret();
    keyValue = String(key || '');
    secretValue = String(secret || '');
    if (keyNode) keyNode.textContent = keyValue || 'Unavailable';
    if (copyKeyButton) copyKeyButton.disabled = !keyValue;
    if (secretValue) {
      secretVisible = true;
      if (secretNode) secretNode.textContent = secretValue;
      if (copySecretButton) copySecretButton.disabled = false;
    }
    secretDialog?.showModal();
  };

  const rotate = async id => {
    if (!confirm('Rotate this API key? Existing clients using its secret will stop working after the rotation grace period.')) return;
    try { const result = await request(`${endpoint}${encodeURIComponent(id)}/rotate/`, { method: 'POST', body: '{}' }); showCredentials(result.key, result.secret); await load(); }
    catch (error) { alert(error.message); }
  };

  const revoke = async id => {
    if (!confirm('Revoke this API key? Existing clients will stop authenticating.')) return;
    try { await request(`${endpoint}${encodeURIComponent(id)}/revoke/`, { method: 'POST', body: '{}' }); await load(); }
    catch (error) { alert(error.message); }
  };

  const remove = async (id, name) => {
    if (!confirm(`Delete “${name}”? This permanently removes the credential and cannot be undone.`)) return;
    try { await request(`${endpoint}${encodeURIComponent(id)}/delete/`, { method: 'DELETE' }); await load(); }
    catch (error) { alert(error.message); }
  };

  form?.addEventListener('submit', async event => {
    event.preventDefault();
    const data = new FormData(form);
    const permissions = data.getAll('permissions');
    try {
      const result = await request(`${endpoint}create/`, { method: 'POST', body: JSON.stringify({ name: data.get('name'), permissions }) });
      form.reset(); dialog?.close(); showCredentials(result.key, result.secret); await load();
    } catch (error) { alert(error.message); }
  });
  document.querySelectorAll('[data-api-key-create]').forEach(button => button.onclick = () => dialog?.showModal());
  document.querySelectorAll('[data-api-key-close]').forEach(button => button.onclick = () => dialog?.close());
  document.querySelector('[data-api-secret-close]')?.addEventListener('click', () => { clearSecret(); secretDialog?.close(); });
  secretDialog?.addEventListener('close', clearSecret);

  copyKeyButton?.addEventListener('click', async event => {
    if (!keyValue) return;
    try {
      await navigator.clipboard.writeText(keyValue);
      event.currentTarget.textContent = 'Key copied';
      setTimeout(() => { if (event.currentTarget) event.currentTarget.textContent = 'Copy key'; }, 1600);
    } catch (_) {
      alert('Clipboard access was blocked by the browser. The key remains visible so you can retry Copy key.');
    }
  });

  copySecretButton?.addEventListener('click', async event => {
    if (!secretVisible || !secretValue) return;
    const value = secretValue;
    try {
      await navigator.clipboard.writeText(value);
      secretValue = '';
      secretVisible = false;
      if (secretNode) secretNode.textContent = '••••••••••••••••••••';
      event.currentTarget.disabled = true;
      event.currentTarget.textContent = 'Secret copied · masked';
      setTimeout(() => { if (event.currentTarget) event.currentTarget.textContent = 'Copy secret'; }, 1600);
    } catch (_) {
      alert('Clipboard access was blocked by the browser. The secret remains visible so you can retry Copy secret.');
    }
  });
  clearSecret();
  load();
})();
