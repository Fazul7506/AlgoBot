(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const list = v => Array.isArray(v) ? v : (Array.isArray(v?.results) ? v.results : (Array.isArray(v?.data) ? v.data : []));
  const safe = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const money = v => v == null || v === '' || Number.isNaN(Number(v)) ? 'Unavailable' : Number(v).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:8});
  const csrf = () => document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] || '';
  let accounts = [], accountBusy = false, terminalSyncBusy = false, quoteBusy = false, selectedSymbol = $('[data-symbol]')?.value || '', points = [];

  const request = async (url, options = {}, timeout = 5000) => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    const headers = {Accept:'application/json', ...(options.headers || {})};
    if (options.method && options.method !== 'GET') headers['X-CSRFToken'] = csrf();
    try {
      const r = await fetch(url,{credentials:'same-origin',...options,headers,signal:controller.signal});
      const text = await r.text(); let data = {};
      try { data = text ? JSON.parse(text) : {}; } catch (_) { data = {detail:text}; }
      if (r.status === 401 || r.status === 403) throw new Error(data.detail || 'Authentication required');
      if (!r.ok) throw new Error(data.detail || data.message || `Request failed (${r.status})`);
      return data;
    } catch (e) { if (e.name === 'AbortError') throw new Error('Request timed out'); throw e; }
    finally { clearTimeout(timer); }
  };

  const current = () => accounts.find(a => a.is_default || a.is_preferred) || accounts[0] || null;
  const typeOf = a => String(a?.account_type || 'demo').toLowerCase();
  const avatar = (a, small=false) => {
    const url = String(a?.avatar_url || a?.broker?.avatar_url || '').trim();
    const name = a?.broker?.name || a?.broker_name || 'Broker';
    const cls = `algobot-account-avatar${small?' small':''}`;
    return url ? `<img class="${cls}" src="${safe(url)}" alt="${safe(name)} avatar" loading="lazy" referrerpolicy="no-referrer">` : `<span class="${cls}">${safe(name[0]?.toUpperCase() || 'B')}</span>`;
  };

  function styles() {
    if ($('#algobot-account-style')) return;
    const s=document.createElement('style'); s.id='algobot-account-style'; s.textContent=`
      .algobot-account-summary{display:flex;align-items:center;gap:8px;min-width:0;font-size:12px}.algobot-account-avatar{width:34px;height:34px;flex:0 0 34px;border-radius:50%;object-fit:cover;display:inline-flex;align-items:center;justify-content:center;background:#132a49;border:1px solid var(--line);font-weight:800}.algobot-account-avatar.small{width:30px;height:30px;flex-basis:30px;font-size:11px}.algobot-account-copy{display:grid;min-width:0;line-height:1.25}.algobot-account-copy strong,.algobot-account-copy span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.algobot-account-copy span{color:var(--muted);font-size:11px}.algobot-account-actions{display:flex;gap:5px;margin-left:4px}.algobot-account-switch{border:1px solid var(--line);background:#132a49;color:var(--text);border-radius:9px;padding:6px 8px;font-size:11px;cursor:pointer}.algobot-account-switch:disabled{opacity:.55;cursor:not-allowed}.algobot-top-account{max-width:360px}.algobot-sidebar-account{padding:10px;margin:10px 0;border:1px solid var(--line);border-radius:14px;background:#0d1b2e;display:grid;gap:7px}.algobot-account-fresh,.algobot-account-error{color:var(--muted);font-size:10px}.algobot-account-error{color:#ff9aae}.algobot-sidebar-account .algobot-account-switch{width:100%}@media(max-width:980px){.algobot-top-account{display:none!important}}
    `; document.head.appendChild(s);
  }

  function mountSurfaces() {
    styles();
    const actions=$('.topbar-actions');
    if(actions&&!$('.algobot-top-account',actions)){const n=document.createElement('div');n.className='algobot-top-account';n.dataset.topAccount='';actions.insertBefore(n,actions.firstChild);}
    const sidebar=$('#app-sidebar');
    if(sidebar&&!$('.algobot-sidebar-account',sidebar)){const n=document.createElement('div');n.className='algobot-sidebar-account';n.dataset.sidebarAccount='';const target=$('.sidebar-user',sidebar)||sidebar;target.parentNode.insertBefore(n,target);}
  }

  async function selectAccount(id) {
    const target=accounts.find(a=>String(a.id)===String(id));
    if(!target || target.switch_enabled!==true) return;
    try {
      const result=await request(`/api/brokers/accounts/${target.id}/select/`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({account_type:typeOf(target)})},5000);
      if(result.account){accounts=accounts.map(a=>a.id===result.account.id?result.account:{...a,is_preferred:false});renderSurfaces();renderTerminalAccounts();}
    } catch(e) { document.querySelectorAll('[data-account-switch]').forEach(b=>b.title=e.message); }
  }

  function renderSurfaces() {
    mountSurfaces(); const a=current(); const top=$('[data-top-account]'), side=$('[data-sidebar-account]');
    const enabled=a?.switch_enabled===true; const t=typeOf(a); const opposite=a ? accounts.find(x=>x.broker?.id===a.broker?.id&&typeOf(x)!==t) || accounts.find(x=>typeOf(x)!==t) : null;
    const label=opposite?`Switch to ${typeOf(opposite).toUpperCase()}`:'Demo / Real';
    const button=(extra='')=>`<button class="algobot-account-switch" data-account-switch ${enabled&&opposite?'':'disabled'} ${extra}>${safe(label)}</button>`;
    if(top) top.innerHTML=a?`<div class="algobot-account-summary">${avatar(a)}<div class="algobot-account-copy"><strong>${safe(a.broker?.name||a.broker_name||'Broker')} · ${safe(a.broker_account_id)}</strong><span>${safe(t.toUpperCase())} · ${safe(a.currency||'')} ${money(a.balance)}</span></div><div class="algobot-account-actions">${button('title="Switch preferred account"')}</div></div>`:'<span class="algobot-account-error">No canonical broker account</span>';
    if(side) side.innerHTML=a?`<div class="algobot-account-summary">${avatar(a,true)}<div class="algobot-account-copy"><strong>${safe(a.broker?.name||a.broker_name||'Broker')}</strong><span>${safe(a.broker_account_id)} · ${safe(t.toUpperCase())}</span></div></div><div class="algobot-account-fresh">${safe(a.is_connected?`Balance ${a.currency||''} ${money(a.balance)} · ${a.last_synced_at?'Synced '+new Date(a.last_synced_at).toLocaleTimeString():'Last known broker data'}`:`Account ${a.status||'disconnected'}`)}</div>${button()}`:'<div class="algobot-account-error">No canonical broker account</div>';
    const global=$('[data-global-connection]');
    if(global){const text=a?`${a.broker?.name||a.broker_name||'Broker'} · ${a.broker_account_id} · ${t.toUpperCase()}`:'No broker account';global.classList.toggle('connected',!!a?.is_connected);global.classList.toggle('error',!a?.is_connected);global.innerHTML=`<i></i><span>${safe(text)}</span>`;}
    document.querySelectorAll('[data-account-switch]').forEach(b=>b.onclick=()=>selectAccount(opposite?.id));
  }

  function renderTerminalAccounts() {
    const select=$('#account'); if(!select) return;
    if(!accounts.length){select.innerHTML='<option value="">No connected broker account</option>';return;}
    const old=select.value; select.innerHTML=accounts.map(a=>`<option value="${a.id}">${safe(a.broker?.name||a.broker_name||'Broker')} · ${safe(a.broker_account_id)} · ${safe(typeOf(a).toUpperCase())} · ${safe(a.currency||'')} ${money(a.balance)}</option>`).join('');
    select.value=accounts.some(a=>String(a.id)===old)?old:String(current().id); updateTerminalAccount(accounts.find(a=>String(a.id)===String(select.value))||current());
  }

  function updateTerminalAccount(a) {
    if(!a)return; const t=typeOf(a).toUpperCase(), label=`${a.broker?.name||a.broker_name||'Broker'} · ${a.broker_account_id} · ${t}`, c=a.currency||'';
    const s=$('#terminal-status'); if(s&&!quoteBusy)s.innerHTML=`<span class="status-dot"></span>${safe(label)}`;
    $('#balance')?.replaceChildren(document.createTextNode(`${c} ${money(a.balance)}`.trim())); $('#equity')?.replaceChildren(document.createTextNode(`${c} ${money(a.equity??a.balance)}`.trim())); $('#margin')?.replaceChildren(document.createTextNode(`${c} ${money(a.margin)}`.trim())); $('[data-kpi="balance"]')?.replaceChildren(document.createTextNode(`${c} ${money(a.balance)}`.trim())); $('[data-terminal-account]')?.replaceChildren(document.createTextNode(`Account: ${a.broker_account_id}`));
    $('[data-risk-check]')?.replaceChildren(document.createTextNode(a.is_connected ? `Account connected · ${t}` : `Account ${a.status || 'unavailable'}`));
  }

  async function syncAccounts() {
    if(accountBusy)return accounts; accountBusy=true;
    try { accounts=list(await request('/api/brokers/accounts/',{},5000)).filter(a=>a?.id&&a?.broker_account_id); renderSurfaces(); renderTerminalAccounts(); return accounts; }
    catch(e){renderSurfaces();return accounts;} finally{accountBusy=false;}
  }

  async function syncSelectedAccount() {
    if(terminalSyncBusy)return; const select=$('#account'), a=accounts.find(x=>String(x.id)===String(select?.value))||current(); if(!a)return; terminalSyncBusy=true;
    try { const result=await request(`/api/brokers/accounts/${a.id}/sync/`,{method:'POST'},8000); if(result.account){accounts=accounts.map(x=>x.id===result.account.id?result.account:x);renderSurfaces();renderTerminalAccounts();} }
    catch(_){const s=$('#terminal-status');if(s)s.innerHTML=`<span class="status-dot"></span>${safe(a.broker_account_id)} · last known data`;}
    finally{terminalSyncBusy=false;}
  }

  async function discoverSymbol(){
    if(selectedSymbol)return selectedSymbol; try{const symbols=list(await request('/api/markets/symbols/',{},5000)),available=symbols.filter(x=>x?.symbol&&x.is_active!==false&&x.is_tradable!==false);selectedSymbol=available[0]?.symbol||'';const s=$('[data-symbol]');if(s){s.innerHTML=available.map(x=>`<option value="${safe(x.symbol)}">${safe(x.display_name||x.symbol)}</option>`).join('');if(selectedSymbol)s.value=selectedSymbol;}return selectedSymbol;}catch(_){return '';}
  }

  async function loadHistory(symbol){
    try {
      const data=await request(`/api/market/ticks/history/?symbol=${encodeURIComponent(symbol)}&limit=120`,{},5000);
      const history=list(data).map(t=>({price:Number(t.quote),epoch:Number(t.epoch)})).filter(x=>Number.isFinite(x.price)).reverse();
      if(history.length){points=history;renderMarketState();chart();}
    } catch(_) { /* live polling remains authoritative */ }
  }

  function renderMarketState(){
    if(!points.length)return;
    const values=points.map(x=>x.price); const first=values[0], last=values[values.length-1];
    const delta=last-first; const trend=delta>0?'Bullish':delta<0?'Bearish':'Flat';
    const mean=values.reduce((a,b)=>a+b,0)/values.length; const variance=values.reduce((a,b)=>a+(b-mean)**2,0)/values.length; const volatility=Math.sqrt(variance);
    $('[data-q="price"]')?.replaceChildren(document.createTextNode(money(last)));
    $('[data-trend]')?.replaceChildren(document.createTextNode(trend));
    $('[data-volatility]')?.replaceChildren(document.createTextNode(money(volatility)));
    $('[data-structure]')?.replaceChildren(document.createTextNode(points.length>=3?(delta>=0?'Higher-price structure':'Lower-price structure'):'Live quote'));
    $('[data-chart-loading]')?.replaceChildren(document.createTextNode(`Live broker feed · ${points.length} quotes`));
  }

  function chart(){const el=$('#chart');if(!el||points.length<2)return;const w=1000,h=330,p=18,v=points.map(x=>x.price),min=Math.min(...v),max=Math.max(...v),span=max-min||Math.max(Math.abs(max)*.0001,1),pts=points.map((x,i)=>`${(p+i/Math.max(1,points.length-1)*(w-p*2)).toFixed(1)},${(h-p-(x.price-min)/span*(h-p*2)).toFixed(1)}`).join(' '),latest=v.at(-1),stroke=latest>=v[0]?'#43d19a':'#ff6b7d',last=pts.split(' ').at(-1).split(',');el.innerHTML=`<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" style="width:100%;height:100%;display:block"><polyline points="${pts}" fill="none" stroke="${stroke}" stroke-width="2.5"></polyline><circle cx="${last[0]}" cy="${last[1]}" r="4" fill="${stroke}"></circle><text x="${w-p}" y="${p+2}" text-anchor="end" fill="currentColor" opacity=".7" font-size="13">LIVE ${money(latest)}</text></svg>`;}

  async function tick(){const symbol=$('[data-symbol]')?.value||selectedSymbol||await discoverSymbol();if(!symbol||quoteBusy)return;quoteBusy=true;try{const d=await request('/api/market/ticks/broker/',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({symbol})},7000),price=Number(d.quote??d.last??d.price);if(!Number.isFinite(price))throw new Error('No usable quote');points.push({price,epoch:Number(d.epoch)||Date.now()});points=points.slice(-120);renderMarketState();chart();$('[data-q="bid"]')?.replaceChildren(document.createTextNode(money(d.bid??price)));$('[data-q="ask"]')?.replaceChildren(document.createTextNode(money(d.ask??price)));}catch(e){const s=$('#terminal-status');if(s&&accounts.length&&!quoteBusy)s.title=e.message;}finally{quoteBusy=false;}}

  function boot(){
    if(document.body.dataset.authenticated!=='true')return;
    syncAccounts().then(async()=>{
      if(!$('#chart'))return;
      $('#account')?.addEventListener('change',()=>{updateTerminalAccount(accounts.find(a=>String(a.id)===String($('#account').value)));syncSelectedAccount();});
      $('[data-symbol]')?.addEventListener('change',()=>{selectedSymbol=$('[data-symbol]').value;points=[];loadHistory(selectedSymbol);tick();});
      await discoverSymbol();
      await loadHistory(selectedSymbol);
      await tick();
      // Account balance refresh is deliberately background-only so a slow
      // vendor API can never block the live market chart or page controls.
      syncSelectedAccount();
      setInterval(()=>{if(document.visibilityState==='visible')tick();},5000);
      setInterval(()=>{if(document.visibilityState==='visible')syncSelectedAccount();},60000);
    });
    setInterval(()=>{if(document.visibilityState==='visible')syncAccounts();},60000);
  }
  window.addEventListener('DOMContentLoaded',boot,{once:true});
})();
