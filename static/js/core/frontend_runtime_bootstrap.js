/* Runtime safety net for pages that depend on the shared frontend data contract. */
(() => {
  'use strict';
  if (window.AlgoBotFrontendData?.request) return;

  const list = value => {
    if (Array.isArray(value)) return value;
    for (const key of ['results','data','items','markets','strategies','symbols','instruments','candles','trades']) {
      if (Array.isArray(value?.[key])) return value[key];
    }
    return [];
  };

  const configuredApiBase = (document.querySelector('meta[name="algobot-api-base"]')?.content || '').trim();
  const defaultApiBase = window.location.hostname === 'algobot.dpdns.org' ? 'https://api.algobot.dpdns.org' : '';
  const apiBase = (configuredApiBase || defaultApiBase).replace(/\/+$/, '');
  const resolveUrl = url => /^https?:\/\//i.test(url) ? url : `${apiBase}${url.startsWith('/') ? url : `/${url}`}`;
  const isCloudflareChallenge = (response, text) => { const body=String(text||'').toLowerCase(),type=String(response?.headers?.get('content-type')||'').toLowerCase(); return [400,403,429,503,520,521,522,524].includes(response?.status)&&(body.includes('just a moment')||body.includes('cf_chl_opt')||body.includes('challenge-platform')||body.includes('challenges.cloudflare.com')||body.includes('enable javascript and cookies to continue')||(body.includes('cloudflare')&&type.includes('text/html'))); };
  const parse = (response,text) => { try{return text?JSON.parse(text):{};}catch(_){return {detail:isCloudflareChallenge(response,text)?'Production edge security challenged this API request.':`Backend returned an unexpected response (${response?.status||'unknown'}).`};} };
  async function requestOnce(url,options,timeout){const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),Math.max(1000,timeout));try{const target=resolveUrl(url),headers={Accept:'application/json',...(options.headers||{})},crossOrigin=new URL(target,window.location.origin).origin!==window.location.origin;const response=await fetch(target,{credentials:crossOrigin?'include':'same-origin',...options,headers,signal:controller.signal});return {response,text:await response.text()};}finally{clearTimeout(timer);}}
  async function request(url,options={},timeout=25000){if(!url)throw new Error('No API endpoint configured');const {response,text}=await requestOnce(url,options,timeout),payload=parse(response,text);if(!response.ok){const error=new Error(payload.detail||payload.message||`Request failed (${response.status})`);error.status=response.status;error.code=isCloudflareChallenge(response,text)?'EDGE_CHALLENGE':'API_ERROR';error.isEdgeChallenge=error.code==='EDGE_CHALLENGE';throw error;}return payload;}
  window.AlgoBotFrontendData=Object.freeze({request,list});
})();
