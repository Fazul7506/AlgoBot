/* Responsive top-right workspace controls backed by canonical account and notification APIs. */
(() => {
  'use strict';
  if (window.__algoBotTopbarSecurityControls) return;
  window.__algoBotTopbarSecurityControls = true;
  const $ = (s, r = document) => r.querySelector(s);
  const safe = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const list = v => Array.isArray(v) ? v : (Array.isArray(v?.results) ? v.results : (Array.isArray(v?.data) ? v.data : []));
  const request = (url, options = {}, timeout = 7000) => {
    const fn = window.AlgoBotFrontendData?.request;
    if (typeof fn !== 'function') return Promise.reject(new Error('AlgoBot secure transport is not ready.'));
    return fn(url, options, timeout);
  };
  const accountContext = () => window.AlgoBotAccountContext;
  const selectedAccount = () => accountContext()?.getSelected?.() || window.AlgoBotBrokerState?.get?.()?.account || null;
  const accountType = a => String(a?.account_type || a?.credentials?.account_type || 'unknown').toUpperCase();
  const accountLabel = a => {
    const broker = a?.broker?.name || a?.broker_name || 'Broker';
    const id = a?.broker_account_id || a?.account_id || a?.id || '';
    return {broker, id, type: accountType(a), currency: a?.currency || 'USD', balance: a?.balance};
  };
  function closeMenus(except) {
    document.querySelectorAll('[data-topbar-account-menu],[data-notification-menu],[data-profile-menu]').forEach(menu => {
      if (menu !== except) menu.hidden = true;
    });
    document.querySelectorAll('[data-topbar-account-trigger],[data-notification-trigger],[data-profile-trigger]').forEach(btn => {
      const owner = btn.closest('[data-topbar-account-control],[data-topbar-notifications],[data-topbar-profile]');
      const menu = owner?.querySelector('[data-topbar-account-menu],[data-notification-menu],[data-profile-menu]');
      if (menu && menu !== except) btn.setAttribute('aria-expanded', 'false');
    });
  }
  function toggleMenu(button, menu) {
    const opening = menu.hidden;
    closeMenus(opening ? menu : null);
    menu.hidden = !opening;
    button.setAttribute('aria-expanded', String(opening));
    if (opening) menu.querySelector('button,a,[role="option"]')?.focus({preventScroll:true});
  }
  function renderAccount() {
    const control = $('[data-topbar-account-control]');
    if (!control) return;
    const current = selectedAccount();
    const name = $('[data-topbar-account-name]', control);
    const meta = $('[data-topbar-account-meta]', control);
    const options = $('[data-topbar-account-options]', control);
    if (!current) {
      if (name) name.textContent = 'No active account';
      if (meta) meta.textContent = 'Connect a broker to continue';
      if (options) options.innerHTML = '<span class="topbar-menu-empty">No active broker account is selected.</span>';
      return;
    }
    const currentLabel = accountLabel(current);
    if (name) name.textContent = currentLabel.broker + (currentLabel.id ? ' · ' + currentLabel.id : '');
    if (meta) meta.textContent = currentLabel.type + ' · ' + currentLabel.currency + ' ' + (currentLabel.balance == null ? 'Balance unavailable' : Number(currentLabel.balance).toLocaleString(undefined,{maximumFractionDigits:8}));
    const accounts = accountContext()?.getAccounts?.() || window.AlgoBotBrokerAccounts || [];
    if (options) {
      const eligible = accounts.filter(a => a?.id);
      options.innerHTML = eligible.length ? eligible.map(a => {
        const label = accountLabel(a), active = String(a.id) === String(current.id);
        return '<button type="button" role="option" aria-selected="' + active + '" data-topbar-select-account="' + safe(a.id) + '"' + (active ? ' disabled' : '') + '><span class="topbar-account-option-icon material-symbols-rounded" aria-hidden="true">' + (active ? 'check_circle' : 'account_balance_wallet') + '</span><span class="topbar-account-option-copy"><strong>' + safe(label.broker + (label.id ? ' · ' + label.id : '')) + '</strong><small>' + safe(label.type + ' · ' + label.currency + ' ' + (label.balance == null ? '—' : Number(label.balance).toLocaleString(undefined,{maximumFractionDigits:8}))) + '</small></span><span class="topbar-account-option-status">' + (active ? 'Selected' : 'Switch') + '</span></button>';
      }).join('') : '<span class="topbar-menu-empty">No broker accounts are available.</span>';
    }
  }
  async function switchAccount(id, button) {
    if (!id || button?.disabled) return;
    const context = accountContext();
    if (!context?.selectAccount) {
      window.AlgoBotMessage?.('Broker account selector is not ready. Refresh and try again.', 'error');
      return;
    }
    const old = button.innerHTML;
    button.disabled = true;
    button.innerHTML = '<span class="topbar-account-option-copy"><strong>Switching account…</strong></span>';
    try {
      await context.selectAccount(id);
      renderAccount();
      const menu = $('[data-topbar-account-menu]');
      const trigger = $('[data-topbar-account-trigger]');
      if (menu) menu.hidden = true;
      trigger?.setAttribute('aria-expanded', 'false');
    } catch (error) {
      button.innerHTML = old;
      window.AlgoBotMessage?.(error?.message || 'Account switch failed.', 'error');
    } finally {
      if (button.isConnected) button.disabled = false;
    }
  }
  let notifications = [];
  function notificationUnread(item) { return !item?.read_at; }
  function renderNotifications(payload) {
    notifications = list(payload);
    const count = notifications.filter(notificationUnread).length;
    const badge = $('[data-notification-count]');
    const trigger = $('[data-notification-trigger]');
    if (badge) { badge.textContent = count > 99 ? '99+' : String(count); badge.hidden = count < 1; }
    if (trigger) trigger.setAttribute('aria-label', count ? 'Notifications, ' + count + ' unread' : 'Notifications, no unread items');
    const target = $('[data-notification-list]');
    if (!target) return;
    if (!notifications.length) {
      target.innerHTML = '<p class="topbar-menu-empty">You are all caught up. New account and trading notifications will appear here.</p>';
      return;
    }
    target.innerHTML = notifications.slice(0,8).map(n => {
      const unread = notificationUnread(n);
      const date = n.created_at ? new Date(n.created_at) : null;
      const when = date && !Number.isNaN(date.getTime()) ? date.toLocaleString() : '';
      return '<article class="topbar-notification-item' + (unread ? ' is-unread' : '') + '"><span class="topbar-notification-dot" aria-hidden="true"></span><div class="topbar-notification-copy"><strong>' + safe(n.title || 'Notification') + '</strong><p>' + safe(n.message || '') + '</p><small>' + safe(when) + (n.category ? ' · ' + safe(n.category) : '') + '</small></div>' + (unread ? '<button type="button" class="topbar-mark-read" data-notification-read="' + safe(n.id) + '" aria-label="Mark ' + safe(n.title || 'notification') + ' as read">Mark read</button>' : '<span class="topbar-read-label">Read</span>') + '</article>';
    }).join('');
  }
  async function loadNotifications() {
    try { renderNotifications(await request('/api/notifications/?page_size=8', {notifyOnError:false}, 6500)); }
    catch (_) {
      const target = $('[data-notification-list]');
      if (target) target.innerHTML = '<p class="topbar-menu-empty">Notifications could not be loaded right now. Open the notification center to retry.</p><a class="topbar-menu-retry" href="/notifications/">Retry in notification center</a>';
    }
  }
  async function markRead(id, all = false) {
    const url = all ? '/api/notifications/mark-all-read/' : '/api/notifications/' + encodeURIComponent(id) + '/read/';
    try {
      const payload = await request(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}', notifyOnError:false}, 6500);
      if (all) notifications = notifications.map(n => ({...n, read_at: n.read_at || new Date().toISOString()}));
      else notifications = notifications.map(n => String(n.id) === String(id) ? {...n, read_at: payload?.read_at || new Date().toISOString()} : n);
      renderNotifications(notifications);
    } catch (error) {
      window.AlgoBotMessage?.(error?.message || 'Could not update notification status.', 'error');
    }
  }
  function bind() {
    const accountTrigger = $('[data-topbar-account-trigger]');
    const accountMenu = $('[data-topbar-account-menu]');
    accountTrigger?.addEventListener('click', () => toggleMenu(accountTrigger, accountMenu));
    const notificationTrigger = $('[data-notification-trigger]');
    const notificationMenu = $('[data-notification-menu]');
    notificationTrigger?.addEventListener('click', () => {
      toggleMenu(notificationTrigger, notificationMenu);
      if (!notificationMenu.hidden) loadNotifications();
    });
    const profileTrigger = $('[data-profile-trigger]');
    const profileMenu = $('[data-profile-menu]');
    profileTrigger?.addEventListener('click', () => toggleMenu(profileTrigger, profileMenu));
    document.addEventListener('click', event => {
      const select = event.target.closest('[data-topbar-select-account]');
      if (select) { event.preventDefault(); switchAccount(select.dataset.topbarSelectAccount, select); return; }
      const read = event.target.closest('[data-notification-read]');
      if (read) { event.preventDefault(); markRead(read.dataset.notificationRead); return; }
      if (event.target.closest('[data-notification-read-all]')) { event.preventDefault(); markRead(null, true); return; }
      if (!event.target.closest('[data-topbar-account-control],[data-topbar-notifications],[data-topbar-profile]')) closeMenus(null);
    });
    document.addEventListener('keydown', event => { if (event.key === 'Escape') { closeMenus(null); document.querySelector('[data-topbar-account-trigger]')?.focus({preventScroll:true}); } });
    window.addEventListener('algobot:account-context-changed', renderAccount);
    window.addEventListener('algobot:backend-accounts-loaded', renderAccount);
    window.addEventListener('algobot:account-changed', renderAccount);
    document.addEventListener('visibilitychange', () => { if (!document.hidden && !($('[data-notification-menu]')?.hidden)) loadNotifications(); });
    renderAccount();
    if (accountContext()?.load) accountContext().load().then(renderAccount).catch(renderAccount);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind, {once:true}); else bind();
})();
