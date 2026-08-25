(() => {
  if (window.__algoBotLiveBrokerUI) return;
  window.__algoBotLiveBrokerUI = true;
  const $ = (s, r = document) => r.querySelector(s);
  const list = v => Array.isArray(v) ? v : (Array.isArray(v?.results) ? v.results : (Array.isArray(v?.data) ? v.data : []));
  const safe = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const money = v => v == null || v === '' || Number.isNaN(Number(v)) ? 'Unavailable' : Number(v).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:8});
  const csrf = () => document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] || '';
  let accounts = [], terminalSyncBusy = false;

  function ensureMaterialSymbols() {
    // The base template owns the single, preconnected Material Symbols
    // stylesheet.  Do not inject a competing font URL after page load.
    document.documentElement.classList.add('material-symbols-ready');
  }

  async function request(url, options = {}, timeout = 5000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const headers = {Accept:'application/json', ...(options.headers || {})};
      if (options.method && options.method !== 'GET') headers['X-CSRFToken'] = csrf();
      const r = await fetch(url, {credentials:'same-origin', ...options, headers, signal:controller.signal});
      const text = await r.text();
      let data = {};
      try { data = text ? JSON.parse(text) : {}; } catch { data = {detail:text}; }
      if (!r.ok) throw new Error(data.detail || data.message || `Request failed (${r.status})`);
      return data;
    } catch (e) {
      if (e.name === 'AbortError') throw new Error('Broker request timed out');
      throw e;
    } finally { clearTimeout(timer); }
  }

  const typeOf = a => String(a?.account_type || a?.credentials?.account_type || 'demo').toLowerCase();
  const current = () => accounts.find(a => a.is_default || a.is_preferred) || accounts[0] || null;
  const avatar = (a, small = false) => {
    const url = String(a?.avatar_url || a?.broker?.avatar_url || a?.credentials?.avatar_url || '').trim();
    const name = a?.broker?.name || a?.broker_name || 'Broker';
    const cls = `algobot-account-avatar${small ? ' small' : ''}`;
    return url
      ? `<img class="${cls}" src="${safe(url)}" alt="${safe(name)} avatar" loading="lazy" referrerpolicy="no-referrer">`
      : `<span class="${cls}">${safe(name[0]?.toUpperCase() || 'B')}</span>`;
  };

  function styles() {
    if ($('#algobot-account-style')) return;
    const s = document.createElement('style');
    s.id = 'algobot-account-style';
    s.textContent = `
      .sidebar-user{position:relative!important;display:grid!important;grid-template-columns:minmax(0,1fr) auto!important;gap:10px!important;align-items:center!important;width:100%!important;box-sizing:border-box;padding:14px 0 0!important;margin-top:14px!important;border-top:1px solid var(--line)}
      .algobot-sidebar-account{display:grid;width:100%;min-width:0;box-sizing:border-box;background:linear-gradient(180deg,#10233dcc,#0b1728ee);border:1px solid var(--line);border-radius:16px;padding:14px;position:relative;overflow:visible}
      .algobot-account-summary{display:flex;align-items:center;gap:9px;min-width:0;font-size:12px}.algobot-account-avatar{width:34px;height:34px;flex:0 0 34px;border-radius:50%;object-fit:cover;display:inline-flex;align-items:center;justify-content:center;background:#132a49;border:1px solid var(--line);font-weight:800}.algobot-account-avatar.small{width:32px;height:32px;flex-basis:32px}.algobot-account-copy{display:grid;min-width:0;line-height:1.25}.algobot-account-copy strong,.algobot-account-copy span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.algobot-account-copy span{color:var(--muted);font-size:11px}.algobot-account-fresh{color:var(--muted);font-size:10px;margin-top:6px}.algobot-account-error{color:var(--muted);font-size:11px}
      .algobot-account-switch{display:inline-flex;align-items:center;justify-content:center;gap:6px;width:100%;border:1px solid var(--line);background:#132a49;color:var(--text);border-radius:9px;padding:8px 10px;margin-top:9px;font-size:11px;font-weight:700;cursor:pointer;white-space:nowrap;text-decoration:none}.algobot-account-switch:disabled{opacity:.5;cursor:not-allowed}.algobot-switch-avatar{width:18px;height:18px;border-radius:50%;object-fit:cover;display:inline-flex;align-items:center;justify-content:center;background:#07111f;border:1px solid var(--line);font-size:9px;font-weight:800}
      .sidebar-user-actions{position:static!important;display:flex!important;align-items:center!important;justify-content:center!important;width:40px!important;height:40px!important;padding:0!important;margin:0!important}.sidebar-user-actions form{margin:0!important;width:100%;height:100%}.sidebar-user-actions button{width:40px!important;height:40px!important;box-sizing:border-box;border:1px solid var(--line);background:#132a49;color:var(--text);border-radius:10px;cursor:pointer;display:grid;place-items:center;padding:0!important;text-decoration:none}.sidebar-user-actions button:hover{border-color:var(--accent);filter:brightness(1.12)}.sidebar-user-actions .material-symbols-rounded{font-size:19px;line-height:1}
      .algobot-logout-backdrop{position:fixed;inset:0;z-index:9998;background:rgba(2,8,18,.68);backdrop-filter:blur(5px);display:grid;place-items:center;padding:20px}.algobot-logout-dialog{width:min(420px,calc(100vw - 40px));box-sizing:border-box;background:#0d1a2b;border:1px solid var(--line);border-radius:18px;box-shadow:0 24px 80px rgba(0,0,0,.45);padding:24px;color:var(--text)}.algobot-logout-dialog h2{margin:0 0 8px;font-size:18px}.algobot-logout-dialog p{margin:0;color:var(--muted);font-size:13px;line-height:1.5}.algobot-logout-actions{display:flex;justify-content:flex-end;gap:10px;margin-top:22px}.algobot-logout-actions button{min-width:90px;padding:9px 14px;border-radius:10px;border:1px solid var(--line);background:#132a49;color:var(--text);cursor:pointer;text-decoration:none}.algobot-logout-actions .confirm{background:var(--accent);color:#07111f;border-color:var(--accent);font-weight:700}
      .algobot-sidebar-account a,.algobot-sidebar-account button,.sidebar-user-actions button{text-decoration:none!important}
      @media(max-width:800px){.sidebar-user{grid-template-columns:minmax(0,1fr) auto!important}.sidebar-user-actions{width:38px!important;height:38px!important}.sidebar-user-actions button{width:38px!important;height:38px!important}.algobot-logout-backdrop{padding:16px}}
    `;
    document.head.appendChild(s);
  }

  function placeLogout() {
    const side = $('.sidebar-user');
    const account = $('[data-sidebar-account]', side);
    if (!side || !account) return;
    let actions = $('.sidebar-user-actions', side);
    if (!actions) {
      actions = document.createElement('div');
      actions.className = 'sidebar-user-actions';
      actions.innerHTML = '<form method="post" action="/logout/" data-logout-form><input type="hidden" name="csrfmiddlewaretoken"><button type="submit" aria-label="Log out" title="Log out"><span class="material-symbols-rounded">logout</span></button></form>';
      actions.querySelector('input').value = csrf();
    }
    if (actions.parentElement !== side) side.appendChild(actions);
  }

  function mount() {
    ensureMaterialSymbols();
    styles();
    const side = $('.sidebar-user');
    if (!side) return;
    side.querySelectorAll('[data-top-account],.algobot-top-account,.sidebar-account-duplicate,[data-duplicate-account],[data-legacy-account-card],.legacy-broker-account,.broker-account-duplicate').forEach(n => n.remove());
    let accountNode = $('[data-sidebar-account]', side);
    if (!accountNode) {
      accountNode = document.createElement('div');
      accountNode.className = 'algobot-sidebar-account';
      accountNode.dataset.sidebarAccount = '';
      side.insertBefore(accountNode, side.firstChild);
    }
    side.querySelectorAll('[data-sidebar-account]').forEach((n, i) => { if (i > 0) n.remove(); });
    // Keep the single account card and logout as siblings; never nest logout inside the card.
    placeLogout();
  }

  async function selectAccount(id) {
    const target = accounts.find(a => String(a.id) === String(id));
    if (!target || target.switch_enabled !== true) return;
    const buttons = document.querySelectorAll('[data-account-switch]');
    buttons.forEach(b => b.disabled = true);
    try {
      const r = await request(`/api/brokers/accounts/${target.id}/select/`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({account_type:typeOf(target)})}, 5000);
      if (r.account) {
        accounts = accounts.map(a => a.id === r.account.id ? r.account : {...a, is_preferred:false});
        render();
        window.dispatchEvent(new CustomEvent('algobot:account-changed', {detail:r.account}));
      }
    } catch (e) {
      buttons.forEach(b => { b.title = e.message; b.disabled = false; });
    }
  }

  function render() {
    mount();
    const a = current();
    const side = $('[data-sidebar-account]');
    if (!side) return;
    const t = typeOf(a);
    const opposite = a ? (accounts.find(x => String(x.broker?.id) === String(a.broker?.id) && typeOf(x) !== t) || accounts.find(x => typeOf(x) !== t)) : null;
    const enabled = !!a?.switch_enabled && !!opposite;
    const label = opposite ? `Switch to ${typeOf(opposite).toUpperCase()}` : 'Demo / Real';
    const switchAvatar = opposite ? avatar(opposite, true) : '';
    if (a) {
      side.innerHTML = `<div class="algobot-account-summary">${avatar(a,true)}<div class="algobot-account-copy"><strong>${safe(a.broker?.name || a.broker_name || 'Broker')} · ${safe(a.broker_account_id || a.account_id)}</strong><span>${safe(t.toUpperCase())} · ${safe(a.currency || '')} ${money(a.balance)}</span></div></div><div class="algobot-account-fresh">${safe(a.is_connected ? `Balance ${a.currency || ''} ${money(a.balance)} · ${a.last_synced_at ? 'Synced ' + new Date(a.last_synced_at).toLocaleTimeString() : 'Last known broker data'}` : `Account ${a.status || 'unavailable'}`)}</div><button class="algobot-account-switch" data-account-switch ${enabled ? '' : 'disabled'} title="${safe(enabled ? 'Switch preferred broker account' : 'Demo/real switching is disabled until enabled in Render')}">${switchAvatar}<span>${safe(label)}</span></button>`;
    } else {
      side.innerHTML = '<div class="algobot-account-error">No connected broker account</div>';
    }
    const global = $('[data-global-connection]');
    if (global) {
      const ok = !!a?.is_connected;
      global.classList.toggle('connected', ok); global.classList.toggle('error', !ok);
      global.innerHTML = `<i></i><span>${safe(a ? `${a.broker?.name || a.broker_name || 'Broker'} · ${a.broker_account_id || a.account_id} · ${t.toUpperCase()}` : 'No connected broker account')}</span>`;
    }
    const switchButton = $('[data-account-switch]');
    if (switchButton) switchButton.onclick = () => selectAccount(opposite?.id);
    placeLogout();
  }

  async function syncAccounts() {
    // broker_state_bridge is the only account API client.  Reading its
    // published snapshot keeps the shell, dashboard, and terminal in lockstep.
    const canonical = window.AlgoBotBrokerAccounts;
    const selected = window.AlgoBotBrokerState?.get?.().account;
    accounts = (Array.isArray(canonical) ? canonical : (selected ? [selected] : accounts))
      .filter(a => a?.id && a?.broker_account_id);
    render();
    return accounts;
  }

  async function syncSelectedAccount() {
    if (terminalSyncBusy) return;
    const select = $('#account');
    const a = accounts.find(x => String(x.id) === String(select?.value)) || current();
    if (!a) return;
    terminalSyncBusy = true;
    try {
      const r = await request(`/api/brokers/accounts/${a.id}/sync/`, {method:'POST'}, 8000);
      if (r.account) {
        accounts = accounts.map(x => x.id === r.account.id ? r.account : x);
        render();
        window.dispatchEvent(new CustomEvent('algobot:account-synced', {detail:r.account}));
      }
    } catch (e) {
      window.dispatchEvent(new CustomEvent('algobot:account-sync-error', {detail:{account:a,error:e}}));
    } finally { terminalSyncBusy = false; }
  }

  function updateTerminalAccount(a) {
    if (!a) return;
    const t = typeOf(a).toUpperCase(), c = a.currency || '';
    const s = $('#terminal-status');
    if (s) s.innerHTML = `<span class="status-dot"></span>${safe(a.broker?.name || a.broker_name || 'Broker')} · ${safe(a.broker_account_id || a.account_id)} · ${safe(t)}`;
    $('#balance')?.replaceChildren(document.createTextNode(`${c} ${money(a.balance)}`.trim()));
    $('#equity')?.replaceChildren(document.createTextNode(`${c} ${money(a.equity ?? a.balance)}`.trim()));
    $('#margin')?.replaceChildren(document.createTextNode(`${c} ${money(a.margin)}`.trim()));
    $('[data-kpi="balance"]')?.replaceChildren(document.createTextNode(`${c} ${money(a.balance)}`.trim()));
    $('[data-terminal-account]')?.replaceChildren(document.createTextNode(`Account: ${a.broker_account_id || a.account_id}`));
  }

  function discoverSymbol() {
    return request('/api/markets/symbols/', {}, 5000).then(list).then(rows => {
      const active = rows.filter(x => x?.symbol && x.is_active !== false && x.is_tradable !== false);
      const s = $('[data-symbol]');
      if (s && !s.value) s.innerHTML = active.map(x => `<option value="${safe(x.symbol)}">${safe(x.display_name || x.symbol)}</option>`).join('');
      return s?.value || active[0]?.symbol || '';
    }).catch(() => '');
  }

  async function boot() {
    if (document.body.dataset.authenticated !== 'true') return;
    ensureMaterialSymbols(); mount(); await syncAccounts();
    const chart = $('#chart'); if (!chart) return;
    const select = $('#account');
    if (select) select.addEventListener('change', () => { const a = accounts.find(x => String(x.id) === String(select.value)); updateTerminalAccount(a); syncSelectedAccount(); });
    if (window.AlgoBotBrokerUI) return;
    window.AlgoBotBrokerUI = {getAccounts:() => accounts, getCurrentAccount:current, syncAccounts, syncSelectedAccount, updateTerminalAccount, selectAccount};
    const symbol = await discoverSymbol();
    if (symbol) { const el = $('[data-symbol]'); if (el && el.value !== symbol) el.value = symbol; }
    setInterval(() => { if (document.visibilityState === 'visible') syncAccounts(); }, 30000);
  }
  window.addEventListener('algobot:backend-accounts-loaded', event => {
    accounts = list(event.detail).filter(a => a?.id && a?.broker_account_id);
    render();
  });
  window.addEventListener('algobot:state-changed', event => {
    const account = event.detail?.state?.account;
    if (account && !accounts.some(item => String(item.id) === String(account.id))) {
      accounts = [account];
      render();
    }
  });
  window.addEventListener('DOMContentLoaded', boot, {once:true});
})();

(() => {
  const openLogout = form => {
    if (document.querySelector('.algobot-logout-backdrop')) return;
    const backdrop = document.createElement('div');
    backdrop.className = 'algobot-logout-backdrop';
    backdrop.innerHTML = '<div class="algobot-logout-dialog" role="dialog" aria-modal="true" aria-labelledby="algobot-logout-title"><h2 id="algobot-logout-title">Log out of AlgoBot?</h2><p>Your current workspace session will be ended. You can sign back in at any time.</p><div class="algobot-logout-actions"><button type="button" class="cancel">Cancel</button><button type="button" class="confirm">Log out</button></div></div>';
    document.body.appendChild(backdrop);
    const close = () => backdrop.remove(), cancel = backdrop.querySelector('.cancel'), confirm = backdrop.querySelector('.confirm');
    cancel.addEventListener('click', close);
    backdrop.addEventListener('click', e => { if (e.target === backdrop) close(); });
    confirm.addEventListener('click', () => { close(); form.dataset.logoutConfirmed = 'true'; if (typeof form.requestSubmit === 'function') form.requestSubmit(); else form.submit(); });
    const esc = e => { if (e.key === 'Escape') { close(); document.removeEventListener('keydown', esc); } };
    document.addEventListener('keydown', esc); cancel.focus();
  };
  document.addEventListener('submit', e => {
    const form = e.target?.closest?.('[data-logout-form]');
    if (!form) return;
    if (form.dataset.logoutConfirmed === 'true') { delete form.dataset.logoutConfirmed; return; }
    e.preventDefault(); openLogout(form);
  });
})();
