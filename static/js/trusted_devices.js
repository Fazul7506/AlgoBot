(() => {
  const root = document.querySelector('[data-trusted-devices]');
  if (!root) return;
  const form = root.querySelector('[data-trust-device-form]');
  const list = root.querySelector('[data-trusted-device-list]');
  const status = root.querySelector('[data-trusted-device-status]');
  const csrf = () => form.querySelector('[name="csrfmiddlewaretoken"]')?.value || decodeURIComponent(document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] || '');
  const request = async (url, options = {}) => {
    const response = await fetch(url, {credentials:'same-origin', ...options, headers:{Accept:'application/json', ...(options.body ? {'Content-Type':'application/json'} : {}), ...(options.method && options.method !== 'GET' ? {'X-CSRFToken':csrf()} : {}), ...(options.headers || {})}});
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || 'Request failed. Please try again.');
    return payload;
  };
  const node = (tag, cls, value) => { const el = document.createElement(tag); if (cls) el.className = cls; el.textContent = value; return el; };
  async function load() {
    try {
      const payload = await request('/api/security/trusted-devices/');
      list.replaceChildren();
      if (!payload.devices?.length) list.append(node('p','account-help','No trusted devices have been registered.'));
      payload.devices.forEach(device => {
        const row = node('article','trusted-device-row','');
        const detail = node('div','trusted-device-detail','');
        detail.append(node('strong','',device.name));
        const date = device.last_seen_at || device.created_at;
        detail.append(node('small','',date ? `Recorded ${new Date(date).toLocaleString()}` : 'Last activity unavailable'));
        const state = node('span', device.current ? 'account-state account-state--good' : 'account-state', device.current ? 'This browser' : 'Trusted');
        const revoke = node('button','account-btn trusted-device-revoke','Revoke trust');
        revoke.type = 'button'; revoke.addEventListener('click', async () => {
          revoke.disabled = true; status.textContent = 'Revoking device trust…';
          try { await request(`/api/security/trusted-devices/${encodeURIComponent(device.id)}/`, {method:'DELETE'}); status.textContent = 'Device trust revoked.'; await load(); }
          catch (error) { status.textContent = error.message; revoke.disabled = false; }
        });
        row.append(detail,state,revoke); list.append(row);
      });
      status.textContent = `${payload.devices.length} trusted device${payload.devices.length === 1 ? '' : 's'}.`;
    } catch (error) { list.replaceChildren(node('p','account-help','Trusted-device inventory is unavailable.')); status.textContent = error.message; }
  }
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const submit = form.querySelector('[type="submit"]');
    submit.disabled = true; status.textContent = 'Confirming password and registering browser…';
    try {
      const name = form.elements.namedItem('name').value.trim();
      const current_password = form.elements.namedItem('current_password').value;
      await request('/api/security/trusted-devices/', {method:'POST', body:JSON.stringify({name,current_password})});
      form.elements.namedItem('current_password').value = '';
      status.textContent = 'This browser is now trusted. The trust token is stored in a secure HttpOnly cookie.';
      await load();
    } catch (error) { status.textContent = error.message; }
    finally { submit.disabled = false; }
  });
  async function loadAlerts() {
    const card = document.querySelector('[data-security-alerts-card]');
    const target = card?.querySelector('[data-security-alerts-list]');
    if (!card || !target) return;
    try {
      const payload = await request('/api/security/alerts/');
      target.replaceChildren();
      if (!payload.alerts?.length) { target.append(node('p','account-help profile-activity-empty','No recent failed or blocked sign-in events are recorded.')); return; }
      payload.alerts.slice(0, 10).forEach(alert => {
        const row = node('li','','');
        row.append(node('span','material-symbols-rounded','warning'));
        const detail = node('div','','');
        detail.append(node('strong','',alert.action || 'Authentication alert'));
        const when = alert.created_at ? new Date(alert.created_at).toLocaleString() : 'Time unavailable';
        detail.append(node('small','',`${alert.outcome || 'Recorded'} · ${when}`));
        row.append(detail); target.append(row);
      });
    } catch (_) { /* Keep server-rendered audit-derived alerts visible if refresh fails. */ }
  }
  load();
  loadAlerts();
})();
