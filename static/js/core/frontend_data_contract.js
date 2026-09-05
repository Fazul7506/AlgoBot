/* AlgoBot frontend data contract: pages consume broker/backend state, never invent it. */
(() => {
  'use strict';
  if (window.AlgoBotFrontendData) return;

  const brokerState=()=>window.AlgoBotBrokerState;
  const list=value=>Array.isArray(value)?value:(Array.isArray(value?.results)?value.results:(Array.isArray(value?.data)?value.data:(Array.isArray(value?.accounts)?value.accounts:[])));
  const inflight=new Map(),cache=new Map(),GET_CACHE_MS=1200;
  const configuredApiBase=(document.querySelector('meta[name="algobot-api-base"]')?.content||'').trim();
  // Never force the browser onto a second API origin unless deployment explicitly configures one.
  // The Django application is the canonical authenticated API origin.
  const apiBase=configuredApiBase.replace(/\/+$/,'');
  const nativeFetch=window.fetch.bind(window),safeMethods=new Set(['GET','HEAD','OPTIONS']);
  // Account selection is idempotent. It may safely fall back to the Django
  // origin when the optional dedicated API hostname is unreachable. Execution
  // POSTs are deliberately excluded because a timeout can leave a trade unknown.
  const sameOriginRetryPath=path=>/^\/api\/brokers\/accounts\/[^/]+\/select\/$/.test(path);
  const resolveUrl=url=>/^https?:\/\//i.test(url)?url:`${apiBase}${url.startsWith('/')?url:`/${url}`}`;
  const normalizeEndpoint=url=>url==='/api/market/snapshots/all_snapshots/'?'/api/market/snapshots/?page_size=8':url;
  const isCloudflareChallenge=(response,text)=>{if(!response||!text)return false;const body=String(text).toLowerCase();return[400,403,429,503,520,521,522,524].includes(response.status)&&(body.includes('just a moment')||body.includes('challenge-platform')||body.includes('cf_chl_opt')||body.includes('cf_chl-')||body.includes('challenges.cloudflare.com')||body.includes('enable javascript and cookies to continue')||(body.includes('cloudflare')&&String(response.headers?.get('content-type')||'').toLowerCase().includes('text/html')))};
  const parseDjangoResponse=(response,text)=>{const ct=String(response?.headers?.get('content-type')||'').toLowerCase();if(!ct.includes('text/html')||!text)return null;try{const doc=new DOMParser().parseFromString(text,'text/html'),env=doc.querySelector('[data-django-response]');if(!env)return null;const payloadNode=doc.querySelector('#django-response-payload'),messageNode=doc.querySelector('[data-response-message], [data-django-message]');let payload={};if(payloadNode?.textContent)payload=JSON.parse(payloadNode.textContent);return{django:true,status:Number(env.dataset.status||response.status||200),kind:env.dataset.kind||'info',message:messageNode?.textContent?.trim()||'',payload}}catch(_){return null}};
  const parsePayload=(response,text)=>{const django=parseDjangoResponse(response,text);if(django)return django;try{return text?JSON.parse(text):{}}catch(_){if(isCloudflareChallenge(response,text))return{detail:'Production API edge challenge encountered.',code:'EDGE_CHALLENGE'};const ct=String(response?.headers?.get('content-type')||'').toLowerCase();return{detail:ct.includes('text/html')?`Backend returned an unexpected HTML response (${response.status}).`:String(text||`HTTP ${response?.status||'unknown'} request failure`)}}};
  const statusMessage=(status,payload)=>payload?.detail||payload?.message||({401:'Your session has expired. Sign in again.',403:'You are not authorized to perform this action.',404:'The requested API endpoint was not found.',405:'The API endpoint does not accept this HTTP method.',409:'The requested operation conflicts with the current account state.',429:'The request limit or plan quota has been reached.',500:'The server encountered an internal error.',502:'The broker/API gateway returned an invalid response.',503:'The backend service is temporarily unavailable.',504:'The backend service timed out.'}[status]||`HTTP ${status} request failure`);
  const notifyApiError=(options,detail)=>{if(options?.notifyOnError===false)return;window.dispatchEvent(new CustomEvent('algobot:api-error',{detail}))};

  async function fetchOnce(url,options,controller){
    const method=(options.method||'GET').toUpperCase();
    const headers=new Headers({Accept:'application/json, text/html',...(options.headers||{})});
    const target=resolveUrl(url);
    const targetOrigin=new URL(target,window.location.origin).origin;
    const sameOrigin=targetOrigin===window.location.origin;
    const selectedId=brokerState()?.get?.()?.account?.id;
    // The account context is part of the canonical request contract on both the
    // Django web origin and an explicitly configured API origin. Without this,
    // a cross-origin API host can see the user's session but not the selected
    // account context, producing the terminal-only "no connected account" state.
    if(selectedId && !headers.has('X-Algobot-Account-ID')) headers.set('X-Algobot-Account-ID',String(selectedId));
    const crossOrigin=!sameOrigin;
    const response=await nativeFetch(target,{credentials:crossOrigin?'include':'same-origin',...options,headers,cache:'no-store',signal:controller.signal});
    return{response,text:await response.text()};
  }

  async function request(rawUrl,options={},timeout=25000){
    const url=normalizeEndpoint(rawUrl),method=(options.method||'GET').toUpperCase();
    if(!url)throw Error('No API endpoint configured');
    const selectedId=brokerState()?.get?.()?.account?.id||'';
    const key=`${method} ${url} account=${selectedId}`;
    if(method==='GET'){
      if(inflight.has(key))return inflight.get(key);
      const recent=cache.get(key);if(recent&&Date.now()-recent.at<=GET_CACHE_MS)return recent.payload;
    }
    const retry=()=>request(rawUrl,{...options,notifyOnError:true},timeout);
    const promise=(async()=>{
      let controller=new AbortController(),timer=setTimeout(()=>controller.abort(),Math.max(1000,timeout)),result,firstError=null;
      try{
        result=await fetchOnce(url,options,controller);
        const fallbackAllowed=apiBase && !/^https?:\/\//i.test(url) && (safeMethods.has(method)||sameOriginRetryPath(url));
        const edgeOrServerFailure=result?.response && (isCloudflareChallenge(result.response,result.text)||result.response.status>=500);
        if(fallbackAllowed && edgeOrServerFailure){
          try{
            controller=new AbortController();
            clearTimeout(timer);
            timer=setTimeout(()=>controller.abort(),Math.max(1000,timeout));
            const fallback=await fetchOnce(url,options,controller,true);
            if(!isCloudflareChallenge(fallback.response,fallback.text) && fallback.response.ok) result=fallback;
          }catch(_){}
        }
      }catch(error){
        firstError=error;
        const fallbackAllowed=apiBase && !/^https?:\/\//i.test(url) && (safeMethods.has(method)||sameOriginRetryPath(url));
        if(!result && fallbackAllowed){
          try{
            controller=new AbortController();
            clearTimeout(timer);
            timer=setTimeout(()=>controller.abort(),Math.max(1000,timeout));
            result=await fetchOnce(url,options,controller,true);
          }catch(fallbackError){firstError=fallbackError;result=null}
        }
        if(!result){
          const e=new Error(firstError?.name==='AbortError'?'Backend request timed out':(firstError?.message||'Network request failed'));
          e.code=firstError?.name==='AbortError'?'API_TIMEOUT':'NETWORK_ERROR';
          e.status=0;
          e.retryable=safeMethods.has(method)||sameOriginRetryPath(url);
          notifyApiError(options,{url:rawUrl,method,status:0,code:e.code,message:e.message,retryable:e.retryable,retry});
          throw e;
        }
      }finally{clearTimeout(timer)}
      const{response,text}=result,parsed=parsePayload(response,text),payload=parsed?.django?parsed.payload:parsed;
      if(!response.ok){const error=new Error(parsed?.django?parsed.message||statusMessage(response.status,payload):statusMessage(response.status,payload));error.status=response.status;error.code=payload.code||(isCloudflareChallenge(response,text)?'EDGE_CHALLENGE':'API_ERROR');error.isEdgeChallenge=error.code==='EDGE_CHALLENGE';error.retryable=safeMethods.has(method)&&response.status>=500;notifyApiError(options,{url:rawUrl,method,status:response.status,code:error.code,message:error.message,retryable:error.retryable,edgeChallenge:error.isEdgeChallenge,retry});throw error}
      if(method==='GET')cache.set(key,{payload,at:Date.now()});
      return payload;
    })();
    if(method==='GET')inflight.set(key,promise);
    try{return await promise}finally{if(inflight.get(key)===promise)inflight.delete(key)}
  }

  function cached(url,maxAge=120000){const selectedId=brokerState()?.get?.()?.account?.id||'';const item=cache.get(`${'GET'} ${normalizeEndpoint(url)} account=${selectedId}`);return item&&Date.now()-item.at<=maxAge?item.payload:null}
  async function getBrokerAccounts(){return list(await request('/api/brokers/accounts/'))}
  async function syncBrokerAccount(accountId){if(!accountId)throw Error('A broker account is required');if(typeof window.AlgoBotBrokerSync==='function')return window.AlgoBotBrokerSync(accountId);if(brokerState())brokerState().transition(brokerState().STATES.SYNCING,{},'account-sync-started');try{const result=await request(`/api/brokers/accounts/${encodeURIComponent(accountId)}/sync/`,{method:'POST'},25000);if(brokerState()&&result.account)brokerState().setAccount(result.account,'account-sync-complete');return result}catch(error){if(brokerState())brokerState().transition(brokerState().STATES.ERROR,{lastError:error.message},'account-sync-failed');throw error}}
  function requireConnected(action='perform this action'){const state=brokerState()?.get();if(!state?.account||state.status===brokerState().STATES.NO_BROKER||state.status===brokerState().STATES.DISCONNECTED){const error=new Error(`Connect a broker before you ${action}.`);error.code='BROKER_NOT_CONNECTED';throw error}return state}
  function applyBrokerEvent(event={}){if(!brokerState())return;const type=String(event.type||event.event||'').toLowerCase(),payload=event.data||event.payload||event;if(['broker_connected','connection.connected','connected'].includes(type))return brokerState().transition(brokerState().STATES.CONNECTED,{connection:payload},'broker-event-connected');if(['broker_disconnected','connection.disconnected','disconnected'].includes(type))return brokerState().transition(brokerState().STATES.DISCONNECTED,{connection:payload},'broker-event-disconnected');if(['account.updated','account_update','account'].includes(type))return brokerState().setAccount(payload.account||payload,'broker-event-account');if(['positions.updated','positions'].includes(type))return brokerState().patch({positions:list(payload.positions||payload)},'broker-event-positions');if(['orders.updated','orders'].includes(type))return brokerState().patch({orders:list(payload.orders||payload)},'broker-event-orders');if(['trades.updated','trades'].includes(type))return brokerState().patch({trades:list(payload.trades||payload)},'broker-event-trades');if(['market.updated','quote','market'].includes(type))return brokerState().patch({market:payload},'broker-event-market');return brokerState().patch({},`broker-event:${type||'unknown'}`)}
  window.AlgoBotFrontendData=Object.freeze({request,cached,getBrokerAccounts,syncBrokerAccount,requireConnected,applyBrokerEvent,list});
  window.addEventListener('algobot:account-context-changed',()=>{cache.clear();inflight.clear();});
  window.addEventListener('algobot:account-changed',()=>{cache.clear();});
})();
