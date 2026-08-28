(() => {
  const root = document.querySelector('[data-api-key-list]');
  if (!root) return;
  const dialog = document.querySelector('[data-api-key-dialog]');
  const secretDialog = document.querySelector('[data-api-secret-dialog]');
  const form = document.querySelector('[data-api-key-form]');
  const count = document.querySelector('[data-api-key-count]');
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const endpoint = '/api/developer/keys/';
  let secretValue = '';

  const request = async (url, options = {}) => {
    const response = await fetch(url, { credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf, ...(options.headers || {}) }, ...options });
    const data = response.status === 204 ? null : await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data?.detail || 'Request failed');
    return data;
  };

  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const statusClass = status => ({active:'ready', revoked:'danger', expired:'danger', inactive:'degraded'}[status] || 'pending');

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
        <article class="api-key-row" data-key-id="${key.id}">
          <div class="api-key-identity"><span class="key-glyph material-symbols-rounded">key</span><div><strong>${escapeHtml(key.name)}</strong><code>${escapeHtml(key.key)}</code></div></div>
          <div class="api-key-meta"><span class="ds-status ds-status--${statusClass(key.status)}">${escapeHtml(key.status)}</span><span>${key.permissions?.map(escapeHtml).join(' · ') || 'read'}</span><small>Created ${new Date(key.created_at).toLocaleDateString()}</small></div>
          <div class="api-key-actions">
            ${key.status === 'active' ? `<button class="ds-btn" type="button" data-rotate="${key.id}">Rotate</button>` : ''}
            ${key.status === 'active' ? `<button class="ds-btn ds-btn--danger" type="button" data-revoke="${key.id}">Revoke</button>` : ''}
            <button class="ds-btn ds-btn--danger" type="button" data-delete="${key.id}" data-name="${escapeHtml(key.name)}">Delete</button>
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

  const showSecret = secret => {
    secretValue = secret || '';
    document.querySelector('[data-api-secret]').textContent = secretValue;
    secretDialog?.showModal();
  };

  const rotate = async id => {
    if (!confirm('Rotate this API key? Existing clients using its secret will stop working after the rotation grace period.')) return;
    try { const result = await request(`${endpoint}${id}/rotate/`, { method: 'POST', body: '{}' }); showSecret(result.secret); await load(); }
    catch (error) { alert(error.message); }
  };

  const revoke = async id => {
    if (!confirm('Revoke this API key? Existing clients will stop authenticating.')) return;
    try { await request(`${endpoint}${id}/revoke/`, { method: 'POST', body: '{}' }); await load(); }
    catch (error) { alert(error.message); }
  };

  const remove = async (id, name) => {
    if (!confirm(`Delete “${name}”? This permanently removes the credential and cannot be undone.`)) return;
    try { await request(`${endpoint}${id}/delete/`, { method: 'DELETE' }); await load(); }
    catch (error) { alert(error.message); }
  };

  form?.addEventListener('submit', async event => {
    event.preventDefault();
    const data = new FormData(form);
    const permissions = data.getAll('permissions');
    try {
      const result = await request(`${endpoint}create/`, { method: 'POST', body: JSON.stringify({ name: data.get('name'), permissions }) });
      form.reset(); dialog?.close(); showSecret(result.secret); await load();
    } catch (error) { alert(error.message); }
  });
  document.querySelectorAll('[data-api-key-create]').forEach(button => button.onclick = () => dialog?.showModal());
  document.querySelectorAll('[data-api-key-close]').forEach(button => button.onclick = () => dialog?.close());
  document.querySelector('[data-api-secret-close]')?.addEventListener('click', () => secretDialog?.close());
  document.querySelector('[data-copy-api-secret]')?.addEventListener('click', async event => { try { await navigator.clipboard.writeText(secretValue); event.currentTarget.textContent = 'Copied'; setTimeout(() => event.currentTarget.textContent = 'Copy', 1400); } catch (_) { alert('Clipboard access was blocked by the browser.'); } });
  load();
})();
