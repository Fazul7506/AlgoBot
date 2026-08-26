/* Canonical mobile/sidebar account + logout modal manager. */
(() => {
  'use strict';
  if (window.__algoBotSidebarModalManager) return;
  window.__algoBotSidebarModalManager = true;

  const $ = (s, r = document) => r.querySelector(s);
  const safe = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const money = v => v == null || v === '' || Number.isNaN(Number(v)) ? 'Unavailable' : Number(v).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:8});
  let activeModal = null;
  let pendingLogoutForm = null;

  function ensureStyles() {
    if ($('#algobot-sidebar-modal-style')) return;
    const style = document.createElement('style');
    style.id = 'algobot-sidebar-modal-style';
    style.textContent = `
      .algobot-modal-backdrop{position:fixed;inset:0;z-index:10050;display:grid;place-items:center;padding:18px;background:rgba(2,8,18,.74);backdrop-filter:blur(7px);-webkit-backdrop-filter:blur(7px)}
      .algobot-modal{width:min(460px,calc(100vw - 32px));max-height:min(86vh,680px);overflow:auto;box-sizing:border-box;background:var(--surface,#101722);color:var(--text,#f5f7fb);border:1px solid var(--line,#293345);border-radius:20px;box-shadow:0 28px 100px rgba(0,0,0,.55);padding:20px}
      .algobot-modal-head{display:flex;align-items:flex-start;justify-content:space-between;gap:14px}.algobot-modal-head h2{margin:0;font-size:18px;line-height:1.25}.algobot-modal-close{width:36px;height:36px;flex:0 0 36px;border:1px solid var(--line,#293345);border-radius:10px;background:transparent;color:inherit;display:grid;place-items:center;cursor:pointer}.algobot-modal-close:hover{border-color:var(--accent,#2dd4bf)}
      .algobot-modal-account{display:grid;gap:14px;margin-top:18px}.algobot-modal-identity{display:flex;align-items:center;gap:12px}.algobot-modal-avatar{width:48px;height:48px;border-radius:50%;object-fit:cover;display:grid;place-items:center;background:#132a49;border:1px solid var(--line);font-weight:800}.algobot-modal-copy{min-width:0;display:grid;gap:3px}.algobot-modal-copy strong{font-size:15px}.algobot-modal-copy span{font-size:12px;color:var(--muted,#8d99ad)}
      .algobot-modal-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.algobot-modal-stat{padding:12px;border:1px solid var(--line,#293345);border-radius:12px;background:rgba(19,42,73,.35)}.algobot-modal-stat span{display:block;font-size:10px;color:var(--muted,#8d99ad);margin-bottom:4px}.algobot-modal-stat strong{font-size:13px;overflow-wrap:anywhere}
      .algobot-modal-note{font-size:12px;line-height:1.5;color:var(--muted,#8d99ad);margin:0}.algobot-modal-actions{display:flex;justify-content:flex-end;gap:9px;margin-top:20px}.algobot-modal-actions button{min-width:92px;padding:10px 14px;border-radius:10px;border:1px solid var(--line,#293345);background:#132a49;color:inherit;cursor:pointer;font-weight:600}.algobot-modal-actions .primary{background:var(--accent,#2dd4bf);color:#07111f;border-color:var(--accent,#2dd4bf)}.algobot-modal-actions .danger{background:#ef4444;color:#fff;border-color:#ef4444}
      .algobot-account-modal-trigger{cursor:pointer}.algobot-account-modal-trigger:focus-visible{outline:2px solid var(--accent,#2dd4bf);outline-offset:2px}
      @media(max-width:600px){.algobot-modal-backdrop{padding:12px;align-items:end}.algobot-modal{width:100%;max-height:82vh;border-radius:20px}.algobot-modal-grid{grid-template-columns:1fr}.algobot-modal-actions{flex-direction:column-reverse}.algobot-modal-actions button{width:100%}}
    `;
    document.head.appendChild(style);
  }

  function closeModal() {
    if (!activeModal) return;
    activeModal.remove();
    activeModal = null;
    document.body.classList.remove('algobot-modal-open');
    pendingLogoutForm = null;
  }

  function createModal(title, bodyHtml, actionsHtml = '') {
    closeModal();
    ensureStyles();
    const backdrop = document.createElement('div');
    backdrop.className = 'algobot-modal-backdrop';
    backdrop.setAttribute('role', 'presentation');
    backdrop.innerHTML = `<section class="algobot-modal" role="dialog" aria-modal="true" aria-labelledby="algobot-modal-title"><div class="algobot-modal-head"><h2 id="algobot-modal-title">${safe(title)}</h2><button type="button" class="algobot-modal-close" data-modal-close aria-label="Close"><span class="material-symbols-rounded" aria-hidden="true">close</span></button></div>${bodyHtml}${actionsHtml ? `<div class="algobot-modal-actions">${actionsHtml}</div>` : ''}</section>`;
    document.body.appendChild(backdrop);
    activeModal = backdrop;
    document.body.classList.add('algobot-modal-open');
    backdrop.addEventListener('click', e => {
      if (e.target === backdrop || e.target.closest('[data-modal-close]')) closeModal();
    });
    return backdrop;
  }

  function currentAccount() {
    const stateAccount = window.AlgoBotBrokerState?.get?.().account;
    if (stateAccount) return stateAccount;
    const list = window.AlgoBotBrokerAccounts;
    return Array.isArray(list) ? list.find(a => a?.is_default || a?.is_preferred) || list[0] || null : null;
  }

  function accountModal() {
    const account = currentAccount();
    if (!account) {
      createModal('Broker account', '<p class="algobot-modal-note">No connected broker account is currently available.</p>', '<button type="button" data-modal-close>Close</button>');
      return;
    }
    const broker = account.broker?.name || account.broker_name || 'Broker';
    const id = account.broker_account_id || account.account_id || 'Unknown account';
    const type = String(account.account_type || account.credentials?.account_type || 'unknown').toUpperCase();
    const currency = account.currency || '';
    const status = account.status || (account.is_connected ? 'connected' : 'disconnected');
    const avatarUrl = String(account.avatar_url || account.broker?.avatar_url || account.credentials?.avatar_url || '').trim();
    const avatar = avatarUrl ? `<img class="algobot-modal-avatar" src="${safe(avatarUrl)}" alt="${safe(broker)} avatar" loading="lazy" referrerpolicy="no-referrer">` : `<span class="algobot-modal-avatar">${safe(broker[0]?.toUpperCase() || 'B')}</span>`;
    const synced = account.last_synced_at ? new Date(account.last_synced_at).toLocaleString() : 'Not available';
    createModal('Connected broker account', `<div class="algobot-modal-account"><div class="algobot-modal-identity">${avatar}<div class="algobot-modal-copy"><strong>${safe(broker)} · ${safe(id)}</strong><span>${safe(type)} · ${safe(currency)}</span></div></div><div class="algobot-modal-grid"><div class="algobot-modal-stat"><span>Balance</span><strong>${safe(currency)} ${money(account.balance)}</strong></div><div class="algobot-modal-stat"><span>Equity</span><strong>${safe(currency)} ${money(account.equity ?? account.balance)}</strong></div><div class="algobot-modal-stat"><span>Connection</span><strong>${safe(String(status).toUpperCase())}</strong></div><div class="algobot-modal-stat"><span>Last sync</span><strong>${safe(synced)}</strong></div></div><p class="algobot-modal-note">Broker balances and connection status are read from AlgoBot's authoritative broker state. Use the account switch control in the sidebar to change the preferred demo/real account when enabled.</p></div>`, '<button type="button" data-modal-close>Close</button>');
  }

  function logoutModal(form) {
    pendingLogoutForm = form;
    createModal('Confirm logout', '<p class="algobot-modal-note">Are you sure you want to log out of AlgoBot? Your broker account remains connected on the server; this action only ends your current AlgoBot session.</p>', '<button type="button" data-modal-close>Cancel</button><button type="button" class="danger" data-confirm-logout>Log out</button>');
    $('[data-confirm-logout]', activeModal)?.addEventListener('click', () => {
      const target = pendingLogoutForm;
      closeModal();
      if (target) {
        target.dataset.logoutConfirmed = 'true';
        target.submit();
      }
    });
  }

  function bind() {
    ensureStyles();
    document.addEventListener('click', event => {
      const account = event.target?.closest?.('[data-sidebar-account]');
      if (account && !event.target.closest('[data-account-switch],a,button')) {
        event.preventDefault();
        event.stopPropagation();
        accountModal();
        return;
      }
      const logout = event.target?.closest?.('[data-logout-form] button');
      if (logout) {
        const form = logout.closest('form');
        if (form?.dataset.logoutConfirmed === 'true') {
          delete form.dataset.logoutConfirmed;
          return;
        }
        event.preventDefault();
        event.stopPropagation();
        logoutModal(form);
      }
    }, true);
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && activeModal) closeModal();
    });
  }

  function decorateAccountCard() {
    const card = $('[data-sidebar-account]');
    if (!card) return;
    card.classList.add('algobot-account-modal-trigger');
    card.setAttribute('role', 'button');
    card.setAttribute('tabindex', '0');
    card.setAttribute('aria-label', 'Open broker account details');
  }

  function boot() {
    bind();
    decorateAccountCard();
    const observer = new MutationObserver(decorateAccountCard);
    observer.observe(document.body, {subtree:true, childList:true});
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once:true}); else boot();
})();
