(() => {
  if (window.__algoBotAIUI) return;
  window.__algoBotAIUI = true;
  const $=(s,r=document)=>r.querySelector(s);
  const esc=v=>String(v??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#039;'}[c]));
  const request=async(url,options={},timeout=10000)=>{
    const canonical=window.AlgoBotFrontendData?.request;
    if(canonical)return canonical(url,options,timeout);
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),timeout);
    try{const r=await fetch(url,{credentials:'same-origin',...options,headers:{Accept:'application/json',...(options.headers||{})},signal:controller.signal});const text=await r.text();let data={};try{data=text?JSON.parse(text):{}}catch(_){data={detail:text}}if(!r.ok){const e=new Error(data.detail||data.message||`Request failed (${r.status})`);e.status=r.status;e.code=data.code;throw e}return data}catch(e){if(e.name==='AbortError'){e.code='AI_ANALYSIS_TIMEOUT';e.message='AI analysis timed out; the broker data was not changed.'}throw e}finally{clearTimeout(timer)}};
  const reset=message=>{
    $('[data-ai-prediction]')?.replaceChildren(document.createTextNode('Not analysed'));
    $('[data-ai-recommendation]')?.replaceChildren(document.createTextNode('Not analysed'));
    $('[data-ai-confidence-card]')?.replaceChildren(document.createTextNode('Not analysed'));
    $('[data-ai-confidence]')?.replaceChildren(document.createTextNode('Not analysed'));
    $('[data-ai-regime]')?.replaceChildren(document.createTextNode('Not analysed'));
    $('[data-recommended]')?.replaceChildren(document.createTextNode('Not analysed'));
    $('[data-ai-explanation]')?.replaceChildren(document.createTextNode(message||'Run AI analysis for the selected broker account and market.'));
    const box=$('[data-ai-trade-actions]');if(box)box.innerHTML='<div class="ai-wait">No actionable AI signal.</div>';
  };
  function actionBox(){const ticket=$('.order-ticket');if(!ticket)return null;let box=$('[data-ai-trade-actions]',ticket);if(!box){box=document.createElement('div');box.dataset.aiTradeActions='';box.className='ai-trade-actions';$('[data-order-form]',ticket)?.prepend(box)}if(!$('#algobot-ai-trade-style')){const s=document.createElement('style');s.id='algobot-ai-trade-style';s.textContent=`.ai-trade-actions{display:grid;gap:8px;margin-bottom:10px}.ai-trade-actions .ai-action{width:100%;min-height:44px;display:flex;align-items:center;justify-content:center;text-align:center;text-decoration:none!important;border:0;border-radius:12px;padding:12px;font-weight:800;cursor:pointer}.ai-trade-actions .ai-buy{background:linear-gradient(135deg,#10b981,#0ea5e9);color:#fff}.ai-trade-actions .ai-sell{background:linear-gradient(135deg,#ef4444,#f97316);color:#fff}.ai-trade-actions .ai-wait{padding:10px 12px;border:1px solid var(--line);border-radius:10px;color:var(--muted);font-size:12px;text-align:center}.ai-trade-actions small{color:var(--muted);font-size:10px;text-align:center}`;document.head.appendChild(s)}return box}
  function renderAITradeActions(recommendation,prediction){const box=actionBox();if(!box)return;const confidence=Number(prediction.confidence??recommendation.confidence??0),rec=String(recommendation.recommendation||'WAIT').toUpperCase(),source=String(prediction.payload?.source||'no_trained_model'),actionable=source==='trained_ensemble'&&confidence>=65&&(rec==='BUY'||rec==='SELL');if(!actionable){box.innerHTML=`<div class="ai-wait">AI trade gate: ${esc(source==='no_trained_model'?'No trained model available':`${rec} at ${confidence.toFixed(1)}% confidence — waiting for ≥65% actionable confidence.`)}</div>`;return}const label=rec==='BUY'?'BUY with AI signal':'SELL with AI signal';box.innerHTML=`<button type="button" class="ai-action ${rec==='BUY'?'ai-buy':'ai-sell'}" data-ai-direction="${rec}">${esc(label)}</button><small>Trained-model confidence ${confidence.toFixed(1)}%. Final broker/risk validation still applies.</small>`;$('[data-ai-direction]',box)?.addEventListener('click',()=>{window.__algobotAiOrderContext={ai_assisted:true,timeframe:$('#timeframe')?.value||'M1',minimum_ai_confidence:65,ai_decision:{recommendation:rec,confidence}};document.querySelector(`[data-direction="${rec}"]`)?.click()})}
  const render=result=>{const prediction=result.prediction||{},recommendation=result.recommendation||{},regime=result.regime||{},explanation=result.explainability||{};$('[data-ai-prediction]')?.replaceChildren(document.createTextNode(prediction.prediction||'Not analysed'));$('[data-ai-recommendation]')?.replaceChildren(document.createTextNode(recommendation.recommendation||'Not analysed'));$('[data-ai-confidence-card]')?.replaceChildren(document.createTextNode(prediction.confidence!=null?`${Number(prediction.confidence).toFixed(1)}%`:'Not analysed'));$('[data-ai-confidence]')?.replaceChildren(document.createTextNode(prediction.confidence!=null?`${Number(prediction.confidence).toFixed(1)}%`:'Not analysed'));$('[data-ai-regime]')?.replaceChildren(document.createTextNode(regime.regime||'Not analysed'));$('[data-recommended]')?.replaceChildren(document.createTextNode(recommendation.recommendation||'Not analysed'));const factors=Array.isArray(explanation.decision_factors)?explanation.decision_factors.join(', '):'',source=prediction.payload?.source||(prediction.payload?.models_used?`${prediction.payload.models_used} trained models`:'no_trained_model'),box=$('[data-ai-explanation]');if(box)box.innerHTML=`<strong>AI status:</strong> ${esc(source)}. ${esc(explanation.explanation||'')}${factors?`<br><small>Key factors: ${esc(factors)}</small>`:''}`;renderAITradeActions(recommendation,prediction)};
  async function analyze(){
    const symbol=$('#symbol')?.value||$('[data-symbol]')?.value,timeframe=$('#timeframe')?.value||$('[data-timeframe]')?.value||'M1',button=$('[data-ai-analyze]'),account=window.AlgoBotAccountContext?.getSelected?.()||window.AlgoBotBrokerState?.get?.()?.account;
    if(!account?.id){reset('Connect and select a broker account before requesting AI analysis.');return}
    if(!symbol){reset('Synchronize a broker market before requesting AI analysis.');return}
    if(button){button.disabled=true;button.textContent='Analysing…'}
    reset(`Running AI inference for ${account.broker?.name||'the selected broker'} account…`);
    try{const result=await request('/api/ai/predict/',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({symbol,timeframe,account_id:account.id})},15000);render(result)}
    catch(e){reset(`AI unavailable: ${e.message||'analysis failed'}`);renderAITradeActions({recommendation:'WAIT'},{payload:{source:'ai_unavailable'},confidence:0})}
    finally{if(button){button.disabled=false;button.textContent='Analyse market'}}
  }
  function boot(){if(!$('[data-ai-panel]')||$('.terminal-page'))return;$('[data-ai-analyze]')?.addEventListener('click',analyze);$('#symbol')?.addEventListener('change',()=>{window.__algobotAiOrderContext=null;reset('Market changed. Run AI analysis for the selected broker market.')})}
  window.addEventListener('algobot:account-context-changed',event=>{window.__algobotAiOrderContext=null;reset(`Account changed to ${event.detail?.account?.broker_account_id||event.detail?.account?.account_id||'the selected broker account'}. Run AI analysis again.`)});
  window.addEventListener('algobot:account-changed',()=>{window.__algobotAiOrderContext=null;reset('Broker account changed. Run AI analysis again for the selected account.')});
  window.addEventListener('algobot:account-context-error',event=>reset(event.detail?.message||'Broker account context is temporarily unavailable.'));
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
