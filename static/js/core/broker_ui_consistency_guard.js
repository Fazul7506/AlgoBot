/* Canonical UI consistency guard.
 * The backend broker state is the only authority for connection/account display.
 * This also owns the sidebar account-details modal so account UI stays attached
 * to the canonical broker state rather than creating a second broker client.
 */
(() => {
  'use strict';
  if (window.__algoBotBrokerUIConsistencyGuard) return;
  window.__algoBotBrokerUIConsistencyGuard = true;
  const $ = selector => document.querySelector(selector);
  const safe = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const money = value => value == null || value === '' || Number.isNaN(Number(value)) ? 'Unavailable' : Number(value).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:8});
  let currentState = null;
  let modal = null;

  function ensureModalStyles(){
    if($('#algobot-account-modal-style')) return;
    const style=document.createElement('style'); style.id='algobot-account-modal-style'; style.textContent=`
      .algobot-account-modal-backdrop{position:fixed;inset:0;z-index:10050;display:grid;place-items:center;padding:18px;background:rgba(2,8,18,.74);backdrop-filter:blur(7px);-webkit-backdrop-filter:blur(7px)}
      .algobot-account-modal{width:min(460px,calc(100vw - 32px));max-height:min(86vh,680px);overflow:auto;box-sizing:border-box;background:var(--surface,#101722);color:var(--text,#f5f7fb);border:1px solid var(--line,#293345);border-radius:20px;box-shadow:0 28px 100px rgba(0,0,0,.55);padding:20px}
      .algobot-account-modal-head{display:flex;align-items:flex-start;justify-content:space-between;gap:14px}.algobot-account-modal-head h2{margin:0;font-size:18px;line-height:1.25}.algobot-account-modal-close{width:36px;height:36px;flex:0 0 36px;border:1px solid var(--line,#293345);border-radius:10px;background:transparent;color:inherit;display:grid;place-items:center;cursor:pointer}.algobot-account-modal-close:hover{border-color:var(--accent,#2dd4bf)}
      .algobot-account-modal-identity{display:flex;align-items:center;gap:12px;margin-top:18px}.algobot-account-modal-avatar{width:50px;height:50px;flex:0 0 50px;border-radius:50%;display:grid;place-items:center;background:#132a49;border:1px solid var(--line);font-weight:800}.algobot-account-modal-copy{min-width:0;display:grid;gap:4px}.algobot-account-modal-copy strong{font-size:15px;overflow-wrap:anywhere}.algobot-account-modal-copy span{font-size:12px;color:var(--muted,#8d99ad)}
      .algobot-account-modal-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:16px}.algobot-account-modal-stat{padding:12px;border:1px solid var(--line,#293345);border-radius:12px;background:rgba(19,42,73,.35)}.algobot-account-modal-stat span{display:block;font-size:10px;color:var(--muted,#8d99ad);margin-bottom:4px}.algobot-account-modal-stat strong{font-size:13px;overflow-wrap:anywhere}.algobot-account-modal-note{margin:16px 0 0;color:var(--muted,#8d99ad);font-size:12px;line-height:1.5}.algobot-account-modal-actions{display:flex;justify-content:flex-end;margin-top:20px}.algobot-account-modal-actions button{min-width:92px;padding:10px 14px;border-radius:10px;border:1px solid var(--line,#293345);background:#132a49;color:inherit;cursor:pointer;font-weight:600}
      .algobot-account-modal-trigger{cursor:pointer}.algobot-account-modal-trigger:focus-visible{outline:2px solid var(--accent,#2dd4bf);outline-offset:2px}
      @media(max-width:600px){.algobot-account-modal-backdrop{padding:12px;align-items:end}.algobot-account-modal{width:100%;max-height:82vh;border-radius:20px}.algobot-account-modal-grid{grid-template-columns:1fr}.algobot-account-modal-actions button{width:100%}}
    `; document.head.appendChild(style);
  }
  function closeModal(){modal?.remove(); modal=null;}
  function openAccountModal(){
    const account=currentState?.account; if(!account)return; closeModal(); ensureModalStyles();
    const broker=account.broker?.name||account.broker_name||'Broker'; const id=account.broker_account_id||account.account_id||'Unknown account';
    const type=String(account.account_type||account.credentials?.account_type||'unknown').toUpperCase(); const currency=account.currency||'';
    const status=currentState?.status||(account.is_connected?'CONNECTED':'UNAVAILABLE'); const synced=account.last_synced_at?new Date(account.last_synced_at).toLocaleString():'Not available';
    const balance=`${currency} ${money(account.balance)}`.trim(); const equity=`${currency} ${money(account.equity??account.balance)}`.trim(); const margin=`${currency} ${money(account.margin)}`.trim();
    const backdrop=document.createElement('div'); backdrop.className='algobot-account-modal-backdrop';
    backdrop.innerHTML=`<section class="algobot-account-modal" role="dialog" aria-modal="true" aria-labelledby="algobot-account-modal-title"><div class="algobot-account-modal-head"><h2 id="algobot-account-modal-title">Connected broker account</h2><button type="button" class="algobot-account-modal-close" aria-label="Close"><span class="material-symbols-rounded" aria-hidden="true">close</span></button></div><div class="algobot-account-modal-identity"><span class="algobot-account-modal-avatar">${safe(broker[0]?.toUpperCase()||'B')}</span><div class="algobot-account-modal-copy"><strong>${safe(broker)} · ${safe(id)}</strong><span>${safe(type)} · ${safe(currency)} · ${safe(String(status).toUpperCase())}</span></div></div><div class="algobot-account-modal-grid"><div class="algobot-account-modal-stat"><span>Balance</span><strong>${safe(balance)}</strong></div><div class="algobot-account-modal-stat"><span>Equity</span><strong>${safe(equity)}</strong></div><div class="algobot-account-modal-stat"><span>Margin</span><strong>${safe(margin)}</strong></div><div class="algobot-account-modal-stat"><span>Last sync</span><strong>${safe(synced)}</strong></div></div><p class="algobot-account-modal-note">This account display is backed by AlgoBot's canonical broker state. Demo/Real switching remains available from the account control when the broker feature flag allows it.</p><div class="algobot-account-modal-actions"><button type="button">Close</button></div></section>`;
    document.body.appendChild(backdrop); modal=backdrop; const close=()=>closeModal();
    backdrop.querySelector('.algobot-account-modal-close')?.addEventListener('click',close); backdrop.querySelector('.algobot-account-modal-actions button')?.addEventListener('click',close); backdrop.addEventListener('click',e=>{if(e.target===backdrop)close()});
    const esc=e=>{if(e.key==='Escape'){close();document.removeEventListener('keydown',esc)}}; document.addEventListener('keydown',esc);
  }
  function render(state){
    if(!state)return; currentState=state; const account=state.account; const live=!!account&&['CONNECTED','SYNCING','READY'].includes(state.status); const indicator=$('[data-global-connection]');
    if(indicator){const label=account?.broker?.name&&account?.broker_account_id?`${account.broker.name} · ${account.broker_account_id}`:state.status==='DEGRADED'?`Broker degraded${state.lastError?` · ${state.lastError}`:''}`:state.status==='ERROR'?'Broker connection error':'No connected broker account'; indicator.classList.toggle('connected',live); indicator.classList.toggle('error',!live); indicator.innerHTML=`<i></i><span>${safe(label)}</span>`;}
    const card=$('[data-sidebar-account]'); if(!card)return; card.classList.add('algobot-account-modal-trigger'); card.setAttribute('role','button'); card.setAttribute('tabindex','0'); card.setAttribute('aria-label','Open connected broker account details');
    if(!account){card.innerHTML=`<span class="algobot-account-error">${safe(state.lastError||'No connected broker account')}</span>`;return;}
    const broker=account.broker?.name||account.broker_name||'Broker'; const id=account.broker_account_id||account.account_id||'Unknown account'; const type=String(account.account_type||'unknown').toUpperCase(); const currency=account.currency||'';
    const detail=live?`${type} · ${currency} ${money(account.balance)}`:`NOT LIVE · ${state.status}`; const freshness=live?(account.last_synced_at?`Verified ${new Date(account.last_synced_at).toLocaleTimeString()}`:'Broker verified'):(state.lastError||'Waiting for live broker verification');
    card.innerHTML=`<div class="algobot-account-summary"><span class="algobot-account-avatar small">${safe(broker[0]?.toUpperCase()||'B')}</span><div class="algobot-account-copy"><strong>${safe(broker)} · ${safe(id)}</strong><span>${safe(detail)}</span></div></div><div class="algobot-account-fresh">${safe(freshness)}</div>`;
  }
  function boot(){const store=window.AlgoBotBrokerState;if(!store)return;store.subscribe(event=>render(event.detail.state));render(store.get());document.addEventListener('click',event=>{const card=event.target?.closest?.('[data-sidebar-account]');if(!card||event.target.closest('[data-account-switch],button,a,input,select'))return;openAccountModal()},true);document.addEventListener('keydown',event=>{const card=event.target?.closest?.('[data-sidebar-account]');if(card&&(event.key==='Enter'||event.key===' ')){event.preventDefault();openAccountModal()}});}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
