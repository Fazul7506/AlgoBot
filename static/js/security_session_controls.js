/* Security Center session inventory; session bearer IDs are never exposed to the browser. */
(() => {
  'use strict';
  if (window.__algoBotSecuritySessionControls) return;
  window.__algoBotSecuritySessionControls = true;
  const $ = (s,r=document) => r.querySelector(s);
  const safe = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const api = (url, options={}) => {
    const fn=window.AlgoBotFrontendData?.request;
    if(typeof fn!=='function') return Promise.reject(new Error('Secure API transport is not ready.'));
    return fn(url,options,7000);
  };
  async function load() {
    const list=$('[data-security-session-list]');
    if(!list)return;
    list.innerHTML='<p class="security-empty">Loading signed-in sessions…</p>';
    try {
      const data=await api('/api/security/sessions/',{notifyOnError:false});
      const sessions=Array.isArray(data?.sessions)?data.sessions:[];
      const others=sessions.filter(s=>!s.current);
      if(!others.length) {
        list.innerHTML='<p class="security-empty">No other active browser sessions were found. Only sessions supported by the configured Django database session backend are listed.</p>';
        return;
      }
      list.innerHTML=others.map(s=>{
        const expires=s.expires_at?new Date(s.expires_at):null;
        const expiry=expires&&!Number.isNaN(expires.getTime())?expires.toLocaleString():'Expiry unavailable';
        return '<article class="security-session-row security-other-session"><span class="material-symbols-rounded security-icon" aria-hidden="true">devices</span><div><strong>'+safe(s.device||'Other signed-in browser')+'</strong><p>Session expires '+safe(expiry)+'</p><small>Device location and sign-in time are not stored for this session.</small></div><button type="button" class="account-btn account-btn--danger" data-security-revoke-session="'+safe(s.id)+'">Revoke</button></article>';
      }).join('');
    } catch(error) {
      list.innerHTML='<p class="security-empty">Session inventory could not be loaded. Check the connection and retry.</p>';
    }
  }
  async function revoke(button) {
    const id=button.dataset.securityRevokeSession;
    if(!id||button.disabled)return;
    if(!window.confirm('Revoke this other signed-in session? It will need to sign in again.'))return;
    button.disabled=true;
    const old=button.textContent;
    button.textContent='Revoking…';
    try {
      await api('/api/security/sessions/'+encodeURIComponent(id)+'/revoke/',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',notifyOnError:false});
      window.AlgoBotMessage?.('The selected session has been revoked.','success');
      await load();
    } catch(error) {
      button.disabled=false;
      button.textContent=old;
      window.AlgoBotMessage?.(error?.message||'Could not revoke that session.','error');
    }
  }
  document.addEventListener('click',event=>{
    const refresh=event.target.closest('[data-security-sessions-refresh]');
    if(refresh){event.preventDefault();load();return}
    const revokeButton=event.target.closest('[data-security-revoke-session]');
    if(revokeButton){event.preventDefault();revoke(revokeButton)}
  });
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',load,{once:true});else load();
})();
