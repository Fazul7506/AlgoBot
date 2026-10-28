/* Canonical application-shell navigation and Django-message notification UI. */
(() => {
  'use strict';
  if (window.__algoBotBaseShell) return;
  window.__algoBotBaseShell = true;

  const $ = (selector, root = document) => root.querySelector(selector);
  const stack = () => $('#django-message-stack');
  const MESSAGE_LIMIT = 5;
  const MESSAGE_TTL = 6500;
  const SIDEBAR_SCROLL_KEY = 'algobot.sidebar.scroll.position';

  function setBrokerStateAttribute(event) {
    const state = event?.detail?.state || window.AlgoBotBrokerState?.get() || {};
    const status = state.status || 'NO_BROKER';
    document.body.dataset.brokerState = status;
    const indicator = $('[data-global-connection]');
    if (!indicator) return;
    const labels = {NO_BROKER:'No connected broker account',CONNECTING:'Connecting broker…',CONNECTED:'Broker connected',SYNCING:'Synchronizing broker…',READY:'Broker ready',DEGRADED:'Broker connection degraded',DISCONNECTED:'Broker disconnected',RECONNECTING:'Reconnecting broker…',ERROR:'Broker connection error'};
    const account = state.account;
    const label = account?.broker?.name && account?.broker_account_id ? `${account.broker.name} · ${account.broker_account_id}` : labels[status] || 'Broker status unavailable';
    const span = indicator.querySelector('span');
    if (span) span.textContent = label;
    indicator.classList.toggle('connected', status === 'CONNECTED' || status === 'READY');
    indicator.classList.toggle('error', status === 'ERROR' || status === 'DISCONNECTED');
  }

  function removeToast(node) { if (!node || node.dataset.removing === 'true') return; node.dataset.removing='true'; node.classList.add('is-leaving'); window.setTimeout(() => node.remove(), 220); }
  function trimToastStack(target) { const nodes=[...target.querySelectorAll('.toast')]; while(nodes.length>MESSAGE_LIMIT) removeToast(nodes.shift()); }
  function wireToast(node,lifetime=MESSAGE_TTL) { if(!node||node.dataset.toastBound==='true')return; node.dataset.toastBound='true'; const close=node.querySelector('[data-toast-close]'); if(close){close.type='button';close.style.pointerEvents='auto';close.addEventListener('click',event=>{event.preventDefault();event.stopPropagation();removeToast(node);});} if(lifetime>0)window.setTimeout(()=>removeToast(node),lifetime); }
  function ensureStack() { let target=stack(); if(target)return target; target=document.createElement('div'); target.id='django-message-stack'; target.className='toast-stack'; target.setAttribute('aria-live','polite'); target.setAttribute('aria-atomic','false'); document.body.appendChild(target); return target; }
  function showDjangoMessage(text,level='info') { if(!text||typeof text!=='string')return; let clean=text.replace(/\s+/g,' ').trim().slice(0,500); if(/^failed to fetch$/i.test(clean)||/^networkerror:?\s*failed to fetch$/i.test(clean))clean='The data connection is temporarily unavailable. Use Retry when you want to try again.'; if(!clean||/^\s*[[{]/.test(clean))return; const normalizedLevel=['success','warning','error','info'].includes(level)?level:'info'; const target=ensureStack(); const existing=[...target.querySelectorAll('.toast')].find(node=>node.dataset.messageText===clean&&node.dataset.toastLevel===normalizedLevel&&node.dataset.removing!=='true'); if(existing)return; const node=document.createElement('div'); node.className=`toast ${normalizedLevel}`; node.dataset.toastLevel=normalizedLevel; node.dataset.messageText=clean; node.setAttribute('role',normalizedLevel==='error'?'alert':'status'); const message=document.createElement('span'); message.className='toast-message'; message.textContent=clean; const button=document.createElement('button'); button.type='button'; button.className='toast-close'; button.dataset.toastClose='1'; button.setAttribute('aria-label','Close notification'); button.title='Close notification'; button.textContent='×'; node.append(message,button); target.appendChild(node); wireToast(node); trimToastStack(target); }
  window.AlgoBotMessage=showDjangoMessage;
  window.alert=message=>showDjangoMessage(String(message??''),'info');

  function friendlyApiMessage(detail) {
    if(!detail)return'The requested operation could not be completed.';
    const code=String(detail.code||'').toUpperCase(),status=Number(detail.status||0);
    if(code==='API_TIMEOUT'||status===504)return'The service took too long to respond. Check your connection and retry if the operation has not already completed.';
    if(code==='NETWORK_ERROR'||status===0)return'The data connection is temporarily unavailable. Check your internet connection and try again.';
    if(code==='EDGE_CHALLENGE')return'The production connection is temporarily unavailable. Please try again shortly.';
    if(status>=500)return'AlgoBot encountered an unexpected problem. Your action may not have completed. Check the activity log or contact support before repeating a trading action.';
    const message=String(detail.message||'').replace(/\s+/g,' ').trim();
    if(!message||/^[[{]/.test(message)||message.length>500)return status===400?'Some information is missing or invalid. Review your selections and try again.':'The requested operation could not be completed.';
    return message;
  }
  // Polling can legitimately repeat the same failing request. Keep the console/UI
  // useful by coalescing identical transport errors across overlapping page widgets.
  const recentApiErrors = new Map();
  const API_ERROR_DEDUPE_MS = 10000;
  function bindApiMessages() { window.addEventListener('algobot:api-error',event=>{const detail=event.detail||{}; if(['SERVICE_TIMEOUT','EDGE_CHALLENGE'].includes(String(detail.code||'')))return; const signature=[detail.code||'',detail.status||0,detail.method||'GET',detail.url||'',detail.message||''].join('|'); const now=Date.now(); const previous=recentApiErrors.get(signature)||0; if(now-previous<API_ERROR_DEDUPE_MS)return; recentApiErrors.set(signature,now); if(recentApiErrors.size>100){for(const [key,at] of recentApiErrors)if(now-at>API_ERROR_DEDUPE_MS)recentApiErrors.delete(key);if(recentApiErrors.size>100)recentApiErrors.clear();} const level=Number(detail.status)>=500||['API_TIMEOUT','NETWORK_ERROR'].includes(detail.code)?'error':'warning'; showDjangoMessage(friendlyApiMessage(detail),level);}); }

  function currentPath() { return window.location.pathname.replace(/\/+$/,'')||'/'; }
  function navigationLinks() { return [...document.querySelectorAll('#app-sidebar nav a, #app-sidebar .sidebar-new-trade')]; }
  function routeMatches(path,href) { if(!href||href==='#')return false; try { const url=new URL(href,window.location.origin); const target=url.pathname.replace(/\/+$/,'')||'/'; if(target==='/')return path==='/'; return path===target||path.startsWith(`${target}/`); } catch(_){return false;} }

  function syncActiveNavigation({anchor=false}={}) {
    const path=currentPath(); const links=navigationLinks(); let active=null; let activeLength=-1;
    links.forEach(link=>{const href=link.getAttribute('href'); const matched=routeMatches(path,href); link.classList.remove('active','is-current-page'); link.removeAttribute('aria-current'); if(matched&&href&&href.length>activeLength){active=link;activeLength=href.length;}});
    if(active){active.classList.add('active','is-current-page');active.setAttribute('aria-current','page');}
    return active;
  }

  function bindSidebarScrollState(sidebar, scrollHost = sidebar.querySelector('nav')) {
    if (!scrollHost || scrollHost.dataset.scrollStateBound === 'true') return;
    scrollHost.dataset.scrollStateBound = 'true';

    const saveKey = SIDEBAR_SCROLL_KEY;
    let lastKnownTop = Math.max(0, scrollHost.scrollTop || 0);

    const savePosition = () => {
      const maxScroll = Math.max(0, scrollHost.scrollHeight - scrollHost.clientHeight);
      const top = Math.min(Math.max(0, lastKnownTop), maxScroll);
      try {
        sessionStorage.setItem(saveKey, JSON.stringify({
          top,
          atBottom: maxScroll > 0 && top >= maxScroll - 4
        }));
      } catch (_) {}
    };

    const restorePosition = () => {
      let saved = null;
      try { saved = JSON.parse(sessionStorage.getItem(saveKey) || 'null'); } catch (_) {}
      if (!saved) return;

      const apply = () => {
        const maxScroll = Math.max(0, scrollHost.scrollHeight - scrollHost.clientHeight);
        const target = saved.atBottom ? maxScroll : Math.min(Math.max(0, Number(saved.top) || 0), maxScroll);
        scrollHost.scrollTop = target;
        lastKnownTop = scrollHost.scrollTop;
      };

      window.requestAnimationFrame(() => {
        apply();
        window.requestAnimationFrame(apply);
      });
    };

    const recordScroll = () => {
      lastKnownTop = Math.max(0, scrollHost.scrollTop || 0);
      savePosition();
    };

    scrollHost.addEventListener('scroll', recordScroll, {passive:true});
    // Keep sidebar scrolling isolated by CSS: document scrolling must not
    // write to nav.scrollTop, which can jump the navigation unexpectedly.
    sidebar.querySelectorAll('nav a, .sidebar-new-trade').forEach(link => {
      link.addEventListener('click', savePosition, {capture:true});
    });
    window.addEventListener('pagehide', savePosition);
    window.addEventListener('beforeunload', savePosition);
    window.addEventListener('pageshow', restorePosition);
    restorePosition();
  }

  const prefetchedNavigation = new Set();
  function bindNavigationPrefetch(links) {
    // Warm only likely user-initiated same-origin page navigations. This is a
    // low-priority hint (never a blocking fetch), capped to avoid spraying the
    // free production service with requests and disabled for data-saver/2G.
    const connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    if (connection?.saveData || /(^|-)2g$/i.test(connection?.effectiveType || '')) return;
    links.forEach(link => {
      const prefetch = () => {
        if (prefetchedNavigation.size >= 5) return;
        const href = link.getAttribute('href');
        if (!href || href === '#' || link.target && link.target !== '_self' || link.hasAttribute('download')) return;
        let url;
        try { url = new URL(href, window.location.href); } catch (_) { return; }
        if (url.origin !== window.location.origin || url.pathname === currentPath()) return;
        if (/(?:logout|disconnect|delete|remove)(?:\/|$)/i.test(url.pathname)) return;
        const key = url.pathname + url.search;
        if (prefetchedNavigation.has(key)) return;
        const hint = document.createElement('link');
        hint.rel = 'prefetch';
        hint.href = url.href;
        hint.as = 'document';
        document.head.appendChild(hint);
        prefetchedNavigation.add(key);
      };
      link.addEventListener('pointerenter', prefetch, {once: true, passive: true});
      link.addEventListener('focus', prefetch, {once: true});
    });
  }

  function bindNavigation() {
    const sidebar=$('#app-sidebar'); if(!sidebar||sidebar.dataset.navigationBound==='true')return; sidebar.dataset.navigationBound='true'; const nav=sidebar.querySelector('nav'); const backdrop=$('[data-sidebar-backdrop]');const mobile=$('[data-mobile-menu]');const toggle=$('[data-sidebar-toggle]');const shell=$('.app-shell');const storageKey='algobot.sidebar.collapsed';
    syncActiveNavigation({anchor:false}); bindNavigationPrefetch(navigationLinks()); bindSidebarScrollState(sidebar, nav);
    if(window.MutationObserver&&!sidebar.dataset.activeAnchorObserver){sidebar.dataset.activeAnchorObserver='true';const observer=new MutationObserver(()=>syncActiveNavigation({anchor:true}));observer.observe(sidebar,{childList:true,subtree:true});}
    let mobileScrollLocked=false;let mobileScrollY=0;let previousBodyPosition='';let previousBodyTop='';let previousBodyLeft='';let previousBodyRight='';let previousBodyWidth='';
    const lockMobilePage=()=>{if(window.innerWidth>900||mobileScrollLocked)return;mobileScrollY=window.scrollY||window.pageYOffset||document.documentElement.scrollTop||0;previousBodyPosition=document.body.style.position;previousBodyTop=document.body.style.top;previousBodyLeft=document.body.style.left;previousBodyRight=document.body.style.right;previousBodyWidth=document.body.style.width;document.documentElement.classList.add('mobile-drawer-locked');document.body.classList.add('mobile-drawer-locked');document.body.style.position='fixed';document.body.style.top=`-${mobileScrollY}px`;document.body.style.left='0';document.body.style.right='0';document.body.style.width='100%';mobileScrollLocked=true;};
    const unlockMobilePage=()=>{if(!mobileScrollLocked)return;document.documentElement.classList.remove('mobile-drawer-locked');document.body.classList.remove('mobile-drawer-locked');document.body.style.position=previousBodyPosition;document.body.style.top=previousBodyTop;document.body.style.left=previousBodyLeft;document.body.style.right=previousBodyRight;document.body.style.width=previousBodyWidth;mobileScrollLocked=false;window.scrollTo(0,mobileScrollY);};
    const setMobileOpen=open=>{const next=!!open;if(next&&window.innerWidth<=900)lockMobilePage();if(!next)unlockMobilePage();sidebar.classList.toggle('is-open',next);if(backdrop)backdrop.hidden=!next;if(mobile){mobile.setAttribute('aria-expanded',String(next));mobile.setAttribute('aria-label',next?'Navigation open':'Open navigation');const icon=mobile.querySelector('.material-symbols-rounded');if(icon)icon.textContent='menu';}document.body.classList.toggle('mobile-nav-open',next);document.documentElement.classList.toggle('mobile-nav-open',next);};
    setMobileOpen(false);
    document.addEventListener('click',event=>{const target=event.target?.closest?.('[data-mobile-menu]');if(target){event.preventDefault();event.stopPropagation();setMobileOpen(!sidebar.classList.contains('is-open'));return;}if(backdrop&&(event.target===backdrop||event.target?.closest?.('[data-sidebar-backdrop]'))){event.preventDefault();setMobileOpen(false);return;}if(sidebar.classList.contains('is-open')&&event.target?.closest?.('#app-sidebar nav a,#app-sidebar .sidebar-new-trade'))setMobileOpen(false);},true);
    if(toggle){const setCollapsed=collapsed=>{if(window.innerWidth<=900)return;sidebar.classList.toggle('is-collapsed',!!collapsed);shell?.classList.toggle('sidebar-collapsed',!!collapsed);document.body.classList.toggle('sidebar-collapsed',!!collapsed);toggle.setAttribute('aria-expanded',String(!collapsed));toggle.setAttribute('aria-label',collapsed?'Expand navigation':'Collapse navigation');toggle.setAttribute('title',collapsed?'Expand navigation':'Collapse navigation');const icon=toggle.querySelector('.material-symbols-rounded');if(icon)icon.textContent=collapsed?'left_panel_open':'left_panel_close';sidebar.querySelectorAll('nav a,.sidebar-new-trade').forEach(link=>{const label=(link.querySelector('span:not(.material-symbols-rounded)')?.textContent||link.getAttribute('aria-label')||'').trim();if(label){link.setAttribute('aria-label',label);link.setAttribute('title',collapsed?label:'');}});try{localStorage.setItem(storageKey,collapsed?'1':'0');}catch(_){} };try{if(window.innerWidth>900&&localStorage.getItem(storageKey)==='1')setCollapsed(true);}catch(_){}toggle.addEventListener('click',event=>{event.preventDefault();event.stopPropagation();setCollapsed(!sidebar.classList.contains('is-collapsed'));syncActiveNavigation({anchor:false});});}
    
    document.addEventListener('keydown',event=>{if(event.key==='Escape')setMobileOpen(false);}); window.addEventListener('resize',()=>{if(window.innerWidth>900)setMobileOpen(false);syncActiveNavigation({anchor:false});});
  }

  function bindTheme(){const button=$('[data-theme-toggle]');if(!button||button.dataset.themeBound==='true')return;button.dataset.themeBound='true';const storageKey='algobot-theme';const apply=theme=>{document.documentElement.dataset.theme=theme;button.setAttribute('aria-pressed',String(theme==='light'));};const applyPreferences=prefs=>{if(!prefs||typeof prefs!=='object')return;const theme=['light','dark','system'].includes(prefs.theme)?prefs.theme:'dark';document.documentElement.dataset.themePreference=theme;let resolved=theme;if(theme==='system'){try{localStorage.removeItem(storageKey);}catch(_){}resolved=window.matchMedia&&window.matchMedia('(prefers-color-scheme: light)').matches?'light':'dark';}else{try{localStorage.setItem(storageKey,resolved);}catch(_){}}apply(resolved);if(['compact','default','comfortable'].includes(prefs.density))document.documentElement.dataset.density=prefs.density;if(['cyan','blue','teal','violet','amber'].includes(prefs.accent))document.documentElement.dataset.accent=prefs.accent;};let stored=null;try{stored=localStorage.getItem(storageKey);}catch(_){}if(stored==='light'||stored==='dark')apply(stored);button.addEventListener('click',()=>{const html=document.documentElement;const previous=html.dataset.themePreference||html.dataset.theme||'dark';const next=html.dataset.theme==='dark'?'light':'dark';html.dataset.themePreference=next;try{localStorage.setItem(storageKey,next);}catch(_){}apply(next);if(document.body.dataset.authenticated!=='true')return;const token=(()=>{const input=$('input[name="csrfmiddlewaretoken"]');if(input?.value)return input.value;const match=document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);return match?decodeURIComponent(match[1]):'';})();fetch('/api/settings/',{method:'PATCH',credentials:'same-origin',headers:{'Accept':'application/json','Content-Type':'application/json',...(token?{'X-CSRFToken':token}:{})},body:JSON.stringify({preferences:{theme:next}})}).then(response=>{if(!response.ok)throw new Error('Could not save theme preference');return response.json();}).then(()=>{html.dataset.themePreference=next;}).catch(()=>{html.dataset.themePreference=previous;apply(previous==='system'?(window.matchMedia?.('(prefers-color-scheme: light)').matches?'light':'dark'):previous);window.AlgoBotBaseShell?.showDjangoMessage?.('Theme changed for this page, but the account preference could not be saved.','warning');});});if(document.body.dataset.authenticated==='true'&&!document.documentElement.dataset.accountPreferencesLoaded){document.documentElement.dataset.accountPreferencesLoaded='pending';fetch('/api/settings/',{method:'GET',credentials:'same-origin',headers:{Accept:'application/json'}}).then(response=>{if(!response.ok)throw new Error('Account preferences unavailable');return response.json();}).then(data=>{applyPreferences(data?.profile?.account_preferences);document.documentElement.dataset.accountPreferencesLoaded='true';}).catch(()=>{delete document.documentElement.dataset.accountPreferencesLoaded;});}window.addEventListener('storage',event=>{if(event.key===storageKey&&(event.newValue==='light'||event.newValue==='dark'))apply(event.newValue);});const systemQuery=window.matchMedia?.('(prefers-color-scheme: light)');systemQuery?.addEventListener?.('change',()=>{if(document.documentElement.dataset.themePreference==='system')apply(systemQuery.matches?'light':'dark');});}
  function boot(){bindNavigation();bindTheme();bindApiMessages();if(window.AlgoBotBrokerState)window.AlgoBotBrokerState.subscribe(setBrokerStateAttribute);const target=stack();target?.querySelectorAll('.toast').forEach(node=>wireToast(node,MESSAGE_TTL));if(target)trimToastStack(target);}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
  window.AlgoBotBaseShell=Object.freeze({syncActiveNavigation,showDjangoMessage});
})();
