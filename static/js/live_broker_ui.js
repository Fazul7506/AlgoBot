(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const list = value => Array.isArray(value) ? value : (Array.isArray(value?.results) ? value.results : (Array.isArray(value?.data) ? value.data : []));
  const safe = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const money = value => value == null || value === '' || Number.isNaN(Number(value)) ? 'Unavailable' : Number(value).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 8});
  const csrf = () => document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] || '';
  let accounts = [];
  let accountRequestInFlight = false;
  let accountRefreshTimer = null;
  let terminalSyncInFlight = false;
  let selectedSymbol = $('[data-symbol]')?.value || '';
  let livePoints = [];
  let quoteBusy = false;

  const request = async (url, options = {}, timeoutMs = 5000) => {
    const headers = {Accept: 'application/json', ...(options.headers || {})};
    if (options.method && options.method !== 'GET') headers['X-CSRFToken'] = csrf();
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, {credentials: 'same-origin', ...options, headers, signal: controller.signal});
      const text = await response.text();
      let data = {};
      try { data = text ? JSON.parse(text) : {}; } catch (_) { data = {detail: text}; }
      if (response.status === 401 || response.status === 403) throw new Error('Authentication required');
      if (!response.ok) throw new Error(data.detail || data.message || `Request failed (${response.status})`);
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('Request timed out');
      throw error;
    } finally { clearTimeout(timer); }
  };

  function currentAccount() {
    return accounts.find(a => a.is_default || a.is_preferred) || accounts[0] || null;
  }

  function accountType(account) {
    return String(account?.account_type || 'demo').toLowerCase();
  }

  function avatarMarkup(account, size = '') {
    const url = String(account?.avatar_url || account?.broker?.avatar_url || '').trim();
    const label = account?.broker?.name || account?.broker_name || 'Broker';
    const initial = safe(String(label).trim().charAt(0).toUpperCase() || 'B');
    const cls = `algobot-account-avatar ${size}`.trim();
    return url ? `<img class="${cls}" src="${safe(url)}" alt="${safe(label)} avatar" loading="lazy" referrerpolicy="no-referrer">` : `<span class="${cls}" aria-hidden="true">${initial}</span>`;
  }

  function ensureAccountStyles() {
    if ($('#algobot-account-ui-style')) return;
    const style = document.createElement('style');
    style.id = 'algobot-account-ui-style';
    style.textContent = `
      .algobot-account-summary{display:flex;align-items:center;gap:9px;min-width:0;color:var(--text);font-size:12px}
      .algobot-account-avatar{width:34px;height:34px;flex:0 0 34px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;object-fit:cover;background:#132a49;border:1px solid var(--line);color:var(--text);font-weight:800}
      .algobot-account-avatar.small{width:30px;height:30px;flex-basis:30px;font-size:11px}
      .algobot-account-copy{display:grid;min-width:0;line-height:1.25}.algobot-account-copy strong,.algobot-account-copy span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.algobot-account-copy span{color:var(--muted);font-size:11px}
      .algobot-account-actions{display:flex;align-items:center;gap:6px;margin-left:4px}.algobot-account-switch{border:1px solid var(--line);background:#132a49;color:var(--text);border-radius:9px;padding:6px 8px;font-size:11px;cursor:pointer}.algobot-account-switch:disabled{opacity:.55;cursor:not-allowed}
      .algobot-sidebar-account{padding:10px;margin:10px 0;border:1px solid var(--line);border-radius:14px;background:#0d1b2e;display:grid;gap:8px}.algobot-sidebar-account .algobot-account-summary{width:100%}
      .algobot-account-fresh{color:var(--muted);font-size:10px;margin-left:40px}.algobot-account-error{color:#ff9aae;font-size:11px}
      @media(max-width:980px){.algobot-top-account{display:none!important}}
    `;
    document.head.appendChild(style);
  }

  function setGlobalConnection(account) {
    const node = $('[data-global-connection]');
    if (!node) return;
    if (!account) {
      node.classList.remove('connected'); node.classList.add('error');
      node.innerHTML = '<i></i><span>No broker account</span>';
      node.title = 'No canonical broker account is available';
      return;
    }
    const type = accountType(account).toUpperCase();
    const connected = account.is_connected;
    const text = `${account.broker?.name || account.broker_name || 'Broker'} · ${account.broker_account_id} · ${type}`;
    node.classList.toggle('connected', !!connected); node.classList.toggle('error', !connected);
    node.innerHTML = `<i></i><span>${safe(text)}</span>`;
    node.title = connected ? `${text} · last sync ${safe(account.last_synced_at || 'not recorded')}` : `${text} · ${safe(account.status || 'disconnected')}`;
  }

  function ensureTopAccount() {
    const actions = $('.topbar-actions');
    if (!actions || $('.algobot-top-account', actions)) return;
    const node = document.createElement('div');
    node.className = 'algobot-top-account';
    node.setAttribute('data-top-account', '');
    actions.insertBefore(node, actions.firstChild);
  }

  function ensureSidebarAccount() {
    const sidebar = $('#app-sidebar');
    if (!sidebar || $('.algobot-sidebar-account', sidebar)) return;
    const target = $('.sidebar-user', sidebar) || sidebar;
    const node = document.createElement('div');
    node.className = 'algobot-sidebar-account';
    node.setAttribute('data-sidebar-account', '');
    target.parentNode.insertBefore(node, target);
  }

  function renderAccountSurfaces(errorMessage = '') {
    ensureAccountStyles(); ensureTopAccount(); ensureSidebarAccount();
    const account = currentAccount();
    setGlobalConnection(account);
    const switchEnabled = window.__algoBotBrokerSwitchEnabled === true;
    const type = accountType(account);
    const opposite = accounts.find(a => a.broker_id === account?.broker?.id && accountType(a) !== type) || accounts.find(a => accountType(a) !== type);
    const freshness = account?.data_freshness?.seconds != null ? `${account.data_freshness.seconds}s ago` : 'Not synced yet';
    const switchLabel = opposite ? `Switch to ${accountType(opposite).toUpperCase()}` : 'Demo / Real';
    const top = $('[data-top-account]');
    if (top) top.innerHTML = account ? `<div class="algobot-account-summary">${avatarMarkup(account)}<div class="algobot-account-copy"><strong>${safe(account.broker?.name || account.broker_name || 'Broker')} · ${safe(account.broker_account_id)}</strong><span>${safe(type.toUpperCase())} · ${safe(account.currency || '')} ${money(account.balance)}</span></div><div class="algobot-account-actions"><button class="algobot-account-switch" data-account-switch ${switchEnabled && !!opposite ? '' : 'disabled'} title="${safe(switchEnabled ? (opposite ? 'Switch preferred account' : 'No opposite account is connected') : 'Enable ENABLE_BROKER_ACCOUNT_SWITCH in Render to use this control')}">${safe(switchLabel)}</button></div></div>` : '<span class="algobot-account-error">Broker account unavailable</span>';
    const side = $('[data-sidebar-account]');
    if (side) side.innerHTML = account ? `<div class="algobot-account-summary">${avatarMarkup(account, 'small')}<div class="algobot-account-copy"><strong>${safe(account.broker?.name || account.broker_name || 'Broker')}</strong><span>${safe(account.broker_account_id)} · ${safe(type.toUpperCase())}</span></div></div><div class="algobot-account-fresh">${safe(account.is_connected ? `Balance ${account.currency || ''} ${money(account.balance)} · ${freshness}` : `Account ${account.status || 'disconnected'}`)}</div><button class="algobot-account-switch" data-account-switch ${switchEnabled && !!opposite ? '' : 'disabled'}>${safe(switchLabel)}</button>` : '<div class="algobot-account-error">No canonical broker account available</div>';
    if (errorMessage && !account) {
      document.querySelectorAll('[data-top-account],[data-sidebar-account]').forEach(node => node.insertAdjacentHTML('beforeend', `<div class="algobot-account-error">${safe(errorMessage)}</div>`));
    }
    document.querySelectorAll('[data-account-switch]').forEach(button => button.onclick = () => selectAccount(opposite?.id));
  }

  async function selectAccount(id) {
    if (!id || window.__algoBotBrokerSwitchEnabled !== true) return;
    const target = accounts.find(a => String(a.id) === String(id));
    if (!target) return;
    document.querySelectorAll('[data-account-switch]').forEach(button => button.disabled = true);
    try {
      const result = await request(`/api/brokers/accounts/${target.id}/select/`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({account_type: accountType(target)})}, 5000);
      if (result.account) {
        accounts = accounts.map(a => a.id === result.account.id ? result.account : {...a, is_preferred:false});
        renderAccountSurfaces();
        if ($('#account')) { $('#account').value = String(result.account.id); updateTerminalAccount(result.account); }
      }
    } catch (error) {
      document.querySelectorAll('[data-account-switch]').forEach(button => button.disabled = false);
      const top = $('[data-top-account]'); if (top) top.insertAdjacentHTML('beforeend', `<div class="algobot-account-error">${safe(error.message)}</div>`);
    }
  }

  function renderTerminalAccounts() {
    const select = $('#account');
    if (!select) return;
    const current = select.value;
    if (!accounts.length) { select.innerHTML = '<option value="">No connected broker account</option>'; return; }
    select.innerHTML = accounts.map(a => `<option value="${a.id}">${safe(a.broker?.name || a.broker_name || 'Broker')} · ${safe(a.broker_account_id)} · ${safe(accountType(a).toUpperCase())} · ${safe(a.currency || '')} ${money(a.balance)}</option>`).join('');
    const preferred = current && accounts.some(a => String(a.id) === String(current)) ? current : String(currentAccount().id);
    select.value = preferred;
    updateTerminalAccount(accounts.find(a => String(a.id) === String(select.value)) || currentAccount());
  }

  function updateTerminalAccount(account) {
    if (!account) return;
    const type = accountType(account).toUpperCase();
    const label = `${account.broker?.name || account.broker_name || 'Broker'} · ${account.broker_account_id} · ${type}`;
    const status = $('#terminal-status');
    if (status && !quoteBusy) status.innerHTML = `<span class="status-dot"></span>${safe(label)}`;
    const currency = account.currency || '';
    const balance = $('#balance'); if (balance) balance.textContent = `${currency} ${money(account.balance)}`.trim();
    const equity = $('#equity'); if (equity) equity.textContent = `${currency} ${money(account.equity ?? account.balance)}`.trim();
    const margin = $('#margin'); if (margin) margin.textContent = `${currency} ${money(account.margin)}`.trim();
    const kpiBalance = $('[data-kpi="balance"]'); if (kpiBalance) kpiBalance.textContent = `${currency} ${money(account.balance)}`.trim();
    const accountLabel = $('[data-terminal-account]'); if (accountLabel) accountLabel.textContent = `Account: ${account.broker_account_id}`;
    setGlobalConnection(account);
  }

  async function syncSelectedAccount() {
    if (terminalSyncInFlight) return;
    const select = $('#account');
    const account = accounts.find(a => String(a.id) === String(select?.value)) || currentAccount();
    if (!account) return;
    terminalSyncInFlight = true;
    try {
      const result = await request(`/api/brokers/accounts/${account.id}/sync/`, {method:'POST'}, 8000);
      if (result.account) {
        accounts = accounts.map(a => a.id === result.account.id ? result.account : a);
        renderTerminalAccounts(); renderAccountSurfaces();
      }
    } catch (error) {
      // A failed vendor request never invalidates the persisted credentials or the
      // last known account state. Keep the account visible and report freshness.
      const status = $('#terminal-status');
      if (status) status.innerHTML = `<span class="status-dot"></span>${safe(account.broker?.name || account.broker_name || 'Broker')} · ${safe(account.broker_account_id)} · last known data`;
    } finally { terminalSyncInFlight = false; }
  }

  async function syncAccounts() {
    if (accountRequestInFlight) return accounts;
    accountRequestInFlight = true;
    try {
      const data = await request('/api/brokers/accounts/', {}, 5000);
      accounts = list(data).filter(a => a && a.id && a.broker_account_id);
      renderAccountSurfaces(); renderTerminalAccounts();
      return accounts;
    } catch (error) {
      renderAccountSurfaces(error.message);
      return accounts;
    } finally { accountRequestInFlight = false; }
  }

  async function discoverSymbol() {
    if (selectedSymbol) return selectedSymbol;
    try {
      const symbols = list(await request('/api/markets/symbols/', {}, 5000));
      const available = symbols.filter(x => x?.symbol && x.is_active !== false && x.is_tradable !== false);
      selectedSymbol = available[0]?.symbol || '';
      const select = $('[data-symbol]');
      if (select) { select.innerHTML = available.map(x => `<option value="${safe(x.symbol)}">${safe(x.display_name || x.symbol)}</option>`).join(''); if (selectedSymbol) select.value = selectedSymbol; }
      return selectedSymbol;
    } catch (_) { return ''; }
  }

  function renderLiveChart() {
    const chart = $('#chart'); if (!chart || livePoints.length < 2) return;
    const width=1000,height=330,pad=18,values=livePoints.map(p=>p.price),min=Math.min(...values),max=Math.max(...values),span=max-min||Math.max(Math.abs(max)*.0001,1);
    const points=livePoints.map((p,i)=>`${(pad+(i/Math.max(1,livePoints.length-1))*(width-pad*2)).toFixed(1)},${(height-pad-((p.price-min)/span)*(height-pad*2)).toFixed(1)}`).join(' ');
    const latest=values.at(-1),stroke=latest>=values[0]?'#43d19a':'#ff6b7d',last=points.split(' ').at(-1).split(',');
    chart.innerHTML=`<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="Live market price chart" style="width:100%;height:100%;display:block"><polyline points="${points}" fill="none" stroke="${stroke}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"></polyline><circle cx="${last[0]}" cy="${last[1]}" r="4" fill="${stroke}"></circle><text x="${width-pad}" y="${pad+2}" text-anchor="end" fill="currentColor" opacity=".7" font-size="13">LIVE ${money(latest)}</text></svg>`;
  }

  async function syncLiveTick() {
    const symbol = $('[data-symbol]')?.value || selectedSymbol || await discoverSymbol();
    if (!symbol || quoteBusy) return;
    selectedSymbol = symbol; quoteBusy = true;
    try {
      const tick = await request('/api/market/ticks/broker/', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({symbol})}, 5000);
      const price = Number(tick.quote ?? tick.last ?? tick.price);
      if (!Number.isFinite(price)) throw new Error('Broker returned no usable quote');
      livePoints.push({epoch:Number(tick.epoch || Date.now()/1000),price}); livePoints=livePoints.slice(-120); renderLiveChart();
      $('[data-q="price"]')?.replaceChildren(document.createTextNode(money(price)));
      $('[data-q="bid"]')?.replaceChildren(document.createTextNode(money(tick.bid ?? price)));
      $('[data-q="ask"]')?.replaceChildren(document.createTextNode(money(tick.ask ?? price)));
      const title=$('#chart-title'); if(title) title.textContent=`${symbol} · ${$('[data-timeframe]')?.value||'M1'} · LIVE`;
      const status=$('#terminal-status'); if(status) status.innerHTML=`<span class="status-dot"></span>Live market · ${safe(symbol)} · ${new Date().toLocaleTimeString()}`;
    } catch (_) {
      const status=$('#terminal-status'); if(status && currentAccount()) status.innerHTML=`<span class="status-dot"></span>${safe(currentAccount().broker_account_id)} · live quote temporarily unavailable`;
    } finally { quoteBusy=false; }
  }

  function wireTerminal() {
    $('#account')?.addEventListener('change', () => { updateTerminalAccount(accounts.find(a => String(a.id) === String($('#account').value))); syncSelectedAccount(); });
    $('[data-symbol]')?.addEventListener('change', () => { selectedSymbol=$('[data-symbol]').value; livePoints=[]; syncLiveTick(); });
  }

  async function boot() {
    if (document.body.dataset.authenticated !== 'true') return;
    window.__algoBotBrokerSwitchEnabled = false;
    await syncAccounts();
    if ($('#chart')) {
      wireTerminal();
      await discoverSymbol();
      await syncSelectedAccount();
      await syncLiveTick();
      window.setInterval(() => { if (document.visibilityState === 'visible') syncLiveTick(); }, 5000);
      window.setInterval(() => { if (document.visibilityState === 'visible') syncSelectedAccount(); }, 60000);
    }
    accountRefreshTimer = window.setInterval(() => { if (document.visibilityState === 'visible') syncAccounts(); }, 60000);
  }

  window.addEventListener('DOMContentLoaded', boot, {once:true});
})();
