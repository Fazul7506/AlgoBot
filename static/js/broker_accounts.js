(() => {
  const grid = document.querySelector('[data-account-grid]');
  if (!grid) return;
  const count = document.querySelector('[data-account-count]');
  const connected = document.querySelector('[data-connected-count]');
  const preferred = document.querySelector('[data-preferred-account]');
  const ready = document.querySelector('[data-ready-count]');
  const refresh = document.querySelector('[data-refresh-accounts]');
  const esc = v => String(v ?? '').replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#039;'}[c]));
  const money = (v, currency) => `${esc(currency || '')} ${Number(v || 0).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})}`;
  const api = (url, options = {}) => {
    if (window.AlgoBotFrontendData?.request) return window.AlgoBotFrontendData.request(url, options, 15000);
    return fetch(url,{credentials:'include',headers:{'Accept':'application/json','Content-Type':'application/json',...(options.headers||{})},...options}).then(async r=>{const data=await r.json().catch(()=>({}));if(!r.ok)throw new Error(data.detail||data.message||`Request failed (${r.status})`);return data;});
  };
  const list = value => window.AlgoBotFrontendData?.list(value) || (Array.isArray(value)?value:(value?.results||value?.accounts||[]));
  let accounts=[];
  function render(rows){
    accounts=list(rows).filter(a=>a?.id);
    count.textContent=accounts.length; connected.textContent=accounts.filter(a=>a.is_connected || a.connection_status==='connected').length; ready.textContent=accounts.filter(a=>a.credential_status==='ready').length;
    const p=accounts.find(a=>a.is_active || a.is_preferred); preferred.textContent=p ? esc(p.broker_name || p.broker?.name || p.account_id) : 'None';
    if(!accounts.length){grid.innerHTML='<div class="account-empty">No broker accounts are connected to this profile.</div>';return;}
    grid.innerHTML=accounts.map(a=>{const isConn=a.is_connected || a.connection_status==='connected'; const cred=a.credential_status || 'unknown'; const status=isConn?'connected':(cred==='credentials_expired'?'expired':'disconnected'); const name=a.broker_name || a.broker?.name || 'Broker'; const id=a.account_id || a.id; const selectable=isConn && a.status==='active' && cred==='ready'; return `<article class="account-card"><div class="account-head"><div><div class="account-name">${esc(name)}</div><div class="account-id">Account ${esc(id)}</div></div><div class="account-status ${status}">${esc(status)}</div></div><div class="account-stats"><div class="account-stat"><span>Balance</span><strong>${money(a.balance,a.currency)}</strong></div><div class="account-stat"><span>Equity</span><strong>${money(a.equity,a.currency)}</strong></div><div class="account-stat"><span>Free margin</span><strong>${money(a.free_margin,a.currency)}</strong></div></div><div class="account-actions"><button class="btn" data-sync="${esc(a.id)}">Sync</button>${!isConn?`<button class="btn primary" data-connect="${esc(a.id)}" data-broker="${esc(a.broker_id || a.broker?.id)}">Connect</button>`:`<button class="btn" data-disconnect="${esc(a.id)}" data-broker="${esc(a.broker_id || a.broker?.id)}">Disconnect</button>`}${!a.is_active&&!a.is_preferred?(selectable?`<button class="btn" data-select="${esc(a.id)}">Set active</button>`:'<span class="preferred-badge">Connect and verify to switch</span>'):'<span class="preferred-badge">Active routing account</span>'}</div></article>`}).join('');
  }
  async function load(){grid.innerHTML='<div class="account-empty">Loading broker accounts…</div>';try{const data=await api('/api/brokers/accounts/');render(data);}catch(e){grid.innerHTML=`<div class="account-empty">Unable to load accounts: ${esc(e.message)}</div>`;}}
  grid.addEventListener('click', async e=>{const b=e.target.closest('button');if(!b)return;try{b.disabled=true; if(b.dataset.sync) await api(`/api/brokers/accounts/${b.dataset.sync}/sync/`,{method:'POST'}); else if(b.dataset.select){const accountId=b.dataset.select;const account=accounts.find(a=>String(a.id)===String(accountId));await api(`/api/brokers/accounts/${accountId}/select/`,{method:'POST',body:JSON.stringify({account_type:account?.account_type||''})});const selected=await api(`/api/brokers/accounts/${accountId}/`);window.dispatchEvent(new CustomEvent('algobot:account-changed',{detail:selected}));} else if(b.dataset.connect) await api('/api/brokers/connect/',{method:'POST',body:JSON.stringify({broker_id:b.dataset.broker,account_id:b.dataset.connect})}); else if(b.dataset.disconnect) await api('/api/brokers/disconnect/',{method:'POST',body:JSON.stringify({broker_id:b.dataset.broker,account_id:b.dataset.disconnect})}); await load();}catch(err){alert(err.message);}finally{b.disabled=false;}});
  refresh?.addEventListener('click',load); load();
})();
