(() => {
  'use strict';

  const state = { connected: false, notifications: [], preferences: [] };
  const byId = (id) => document.getElementById(id);

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' })[char]);
  }

  async function request(url, options = {}) {
    const response = await fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json', ...(options.body ? { 'Content-Type': 'application/json' } : {}) }, ...options });
    if (!response.ok) throw new Error(`Request failed (${response.status})`);
    return response.status === 204 ? null : response.json();
  }

  function render() {
    const status = byId('notification-connection-status');
    const list = byId('notification-list');
    const empty = byId('notification-empty');
    status.textContent = state.connected ? 'Broker connected' : 'No broker connection';
    status.dataset.state = state.connected ? 'ready' : 'disconnected';

    if (!state.notifications.length) {
      list.innerHTML = '';
      empty.hidden = false;
      return;
    }
    empty.hidden = true;
    list.innerHTML = state.notifications.map((notice) => `
      <article class="notification-item" data-id="${escapeHtml(notice.id)}">
        <div class="notification-item__meta">
          <span class="status-badge">${escapeHtml(notice.priority || 'info')}</span>
          <time>${escapeHtml(notice.created_at || notice.created || '')}</time>
        </div>
        <h3>${escapeHtml(notice.title)}</h3>
        <p>${escapeHtml(notice.message)}</p>
        <small>${escapeHtml(notice.category || 'general')} · ${escapeHtml(notice.status || 'received')}</small>
      </article>`).join('');
  }

  async function loadBrokerState() {
    try {
      const data = await request('/api/brokers/accounts/');
      const accounts = Array.isArray(data) ? data : (data.results || data.accounts || []);
      state.connected = accounts.some((account) => account.is_connected === true || account.connected === true || account.status === 'connected');
    } catch (_) {
      state.connected = false;
    }
  }

  async function loadNotifications() {
    const data = await request('/api/notifications/notifications/');
    state.notifications = Array.isArray(data) ? data : (data.results || []);
  }

  async function loadPreferences() {
    const data = await request('/api/notifications/notifications/preferences/');
    state.preferences = Array.isArray(data) ? data : (data.results || []);
  }

  async function savePreference(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = Object.fromEntries(new FormData(form).entries());
    payload.enabled = payload.enabled === 'on';
    try {
      await request('/api/notifications/notifications/preferences/', { method: 'POST', body: JSON.stringify(payload) });
      byId('notification-feedback').textContent = 'Preference saved.';
      await loadPreferences();
    } catch (error) {
      byId('notification-feedback').textContent = error.message;
    }
  }

  async function init() {
    try {
      await Promise.all([loadBrokerState(), loadNotifications(), loadPreferences()]);
      render();
    } catch (error) {
      byId('notification-feedback').textContent = error.message;
      render();
    }
    const form = byId('notification-preference-form');
    if (form) form.addEventListener('submit', savePreference);
    window.addEventListener('broker:state-change', async () => { await loadBrokerState(); render(); });
  }

  document.addEventListener('DOMContentLoaded', init);
})();
