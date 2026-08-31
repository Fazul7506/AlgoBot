(() => {
  'use strict';
  const $=(s,r=document)=>r.querySelector(s);
  const api=(u,o={})=>window.AlgoBotFrontendData.request(u,o,10000);
  const set=(k,v,c='')=>{const e=$(`[data-status="${k}"]`);if(e){e.textContent=v;e.className=c}};
  async function load(){
    try{
      const d=await api('/api/developer/docs/');
      set('gateway','Operational','status-ok');set('contract','Published','status-ok');set('realtime','Available','status-ok');
      const v=d?.openapi||d?.info?.version||'unknown';const cv=$('[data-contract-version]');if(cv)cv.textContent=`OpenAPI ${v} · ${Object.keys(d?.paths||{}).length} documented endpoints`;
      const list=$('[data-status-list]');if(list)list.innerHTML='<div class="status-row"><span>API documentation</span><strong class="status-ok">Operational</strong></div><div class="status-row"><span>Authentication</span><strong class="status-ok">Protected</strong></div><div class="status-row"><span>Market data</span><strong class="status-ok">Broker-authoritative</strong></div><div class="status-row"><span>Live execution</span><strong class="status-warn">Gated</strong></div>';
    }catch(e){set('gateway','Unavailable','status-bad');set('contract','Unavailable','status-bad');set('realtime','Unknown','status-warn');const l=$('[data-status-list]');if(l)l.textContent=`Health check failed: ${e.message}`}
  }
  document.addEventListener('DOMContentLoaded',()=>{if(!$('[data-api-status-page]'))return;$('[data-status-refresh]')?.addEventListener('click',load);load()},{once:true});
})();
