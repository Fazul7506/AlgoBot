/* Trading-terminal AI decision bridge. */
(() => {
  'use strict';
  if (window.__algobotTradingTerminalAI) return;
  window.__algobotTradingTerminalAI = true;
  const $=(s,r=document)=>r.querySelector(s);
  const text=(s,value)=>$(s)?.replaceChildren(document.createTextNode(String(value??'—')));
  const api=(url,options={},timeout=30000)=>window.AlgoBotServices?.request?.('ai',url,{...options,notifyOnError:false},timeout)||window.AlgoBotFrontendData?.request(url,{...options,notifyOnError:false},timeout);
  const selectedAccount=()=>window.AlgoBotAccountContext?.getSelected?.()||null;
  let analysing=false,scheduled=null;
  function show(message){text('[data-ai-explanation]',message)}
  function resetForSymbol(){text('[data-ai-prediction]','Not analysed');text('[data-ai-recommendation]','Not analysed');text('[data-ai-confidence-card]','Not analysed');text('[data-ai-confidence]','Not analysed');text('[data-ai-regime]','Not analysed');show('Market/account context changed. Refreshing the AI decision from the selected broker context…');window.__algobotAiOrderContext=null;window.dispatchEvent(new CustomEvent('algobot:ai-gate-updated',{detail:{actionable:false,reset:true}}))}
  function render(data){
    const prediction=data?.prediction||{},recommendation=data?.recommendation||{},regime=data?.regime||{};
    const raw=prediction.confidence??recommendation.confidence,number=Number(raw),confidence=raw==null?'—':`${(number<=1?number*100:number).toFixed(1)}%`;
    const predictionLabel=prediction.prediction??prediction.direction??prediction.label??prediction.class??'—';
    const recommendationLabel=recommendation.recommendation??recommendation.action??recommendation.signal??recommendation.direction??'—';
    const regimeLabel=regime.regime??regime.name??regime.label??'—';
    text('[data-ai-prediction]',predictionLabel);text('[data-ai-recommendation]',recommendationLabel);text('[data-ai-confidence-card]',confidence);text('[data-ai-confidence]',confidence);text('[data-ai-regime]',regimeLabel);
    const explanation=data?.explainability;if(typeof explanation==='string')show(explanation);else if(explanation&&typeof explanation==='object')show(explanation.summary||explanation.reason||explanation.explanation||`AI analysis completed for ${data.symbol||$('#symbol')?.value||'the selected market'}.`);else show(`AI analysis completed for ${data.symbol||$('#symbol')?.value||'the selected market'}.`);
    const actionable=String(recommendationLabel).toUpperCase()!=='WAIT'&&String(predictionLabel).toUpperCase()!=='AVOID'&&Number.isFinite(number)&&(number<=1?number*100:number)>=65;
    window.__algobotAiOrderContext={...(window.__algobotAiOrderContext||{}),ai_prediction:predictionLabel,ai_recommendation:recommendationLabel,ai_confidence:Number.isFinite(number)?number:null,ai_regime:regimeLabel,ai_actionable:actionable,ai_source:data?.market_context_source?`decision_engine:${data.market_context_source}`:'decision_engine'};
    window.dispatchEvent(new CustomEvent('algobot:ai-gate-updated',{detail:{actionable,confidence:number,recommendation:recommendationLabel,prediction:predictionLabel}}));
  }
  async function analyse(){
    if(analysing)return;const button=$('[data-ai-analyze]'),symbol=$('#symbol')?.value,account=selectedAccount();if(!symbol||!account?.id){show(!symbol?'Select a broker instrument before running AI analysis.':'Select a connected broker account before running AI analysis.');return}
    analysing=true;if(button){button.disabled=true;button.textContent='Analysing…'}show('Running AI inference from the latest persisted broker market feed…');
    try{const data=await api('/api/ai/predict/',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({symbol,timeframe:'M1',account_id:account.id})},30000);render(data);window.dispatchEvent(new CustomEvent('algobot:ai-analysis-updated',{detail:data}))}
    catch(error){text('[data-ai-prediction]','Unavailable');text('[data-ai-recommendation]','Unavailable');text('[data-ai-confidence-card]','Unavailable');text('[data-ai-confidence]','Unavailable');text('[data-ai-regime]','Unavailable');window.__algobotAiOrderContext=null;const code=String(error?.code||'').toUpperCase(),message=String(error?.message||'AI analysis is temporarily unavailable.');if(code==='REQUEST_ABORTED'||code==='API_TIMEOUT')show('AI analysis timed out while waiting for broker data. No trade action was taken.');else if(code==='EDGE_CHALLENGE'||message.includes('<html')||message.includes('Just a moment'))show('AI analysis is temporarily unavailable at the production edge. No trade action was taken.');else show(message);window.dispatchEvent(new CustomEvent('algobot:ai-gate-updated',{detail:{actionable:false,error:true,code:error?.code||null}}))}
    finally{analysing=false;if(button){button.disabled=false;button.textContent='Analyse market'}}
  }
  function scheduleAnalyse(){clearTimeout(scheduled);scheduled=setTimeout(()=>{scheduled=null;resetForSymbol();void analyse()},500)}
  function boot(){if(!$('.terminal-page'))return;$('[data-ai-analyze]')?.addEventListener('click',()=>analyse());window.addEventListener('algobot:market-symbol-changed',scheduleAnalyse);window.addEventListener('algobot:broker-contract-selected',()=>{if(!analysing)show('Broker contract ready. AI context will use the selected account and market.')});window.addEventListener('algobot:account-changed',scheduleAnalyse);window.addEventListener('algobot:account-synced',scheduleAnalyse);if($('#symbol')?.value&&selectedAccount()?.id)scheduleAnalyse()}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
