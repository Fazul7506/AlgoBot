(() => {
  if (window.__algoBotAIUI) return;
  window.__algoBotAIUI = true;
  const $ = (s, r = document) => r.querySelector(s);
  const csrf = () => document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] || '';
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const request = async (url, options = {}, timeout = 10000) => {
    const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const headers = {Accept:'application/json', ...(options.headers || {})};
      if (options.method && options.method !== 'GET') headers['X-CSRFToken'] = csrf();
      const r = await fetch(url, {credentials:'same-origin', ...options, headers, signal:controller.signal});
      const text = await r.text(); let data = {}; try { data = text ? JSON.parse(text) : {}; } catch (_) { data = {detail:text}; }
      if (!r.ok) throw new Error(data.detail || data.message || `Request failed (${r.status})`);
      return data;
    } catch (e) { if (e.name === 'AbortError') throw new Error('AI analysis timed out'); throw e; }
    finally { clearTimeout(timer); }
  };
  function actionBox() {
    const ticket=$('.order-ticket'); if(!ticket)return null;
    let box=$('[data-ai-trade-actions]',ticket);
    if(!box){box=document.createElement('div');box.dataset.aiTradeActions='';box.className='ai-trade-actions';const form=$('[data-order-form]',ticket);form?.prepend(box);}
    if(!$('#algobot-ai-trade-style')){const s=document.createElement('style');s.id='algobot-ai-trade-style';s.textContent=`.ai-trade-actions{display:grid;gap:8px;margin-bottom:10px}.ai-trade-actions .ai-action{width:100%;min-height:44px;display:flex;align-items:center;justify-content:center;text-align:center;text-decoration:none!important;border:0;border-radius:12px;padding:12px;font-weight:800;cursor:pointer}.ai-trade-actions .ai-buy{background:linear-gradient(135deg,#10b981,#0ea5e9);color:#fff}.ai-trade-actions .ai-sell{background:linear-gradient(135deg,#ef4444,#f97316);color:#fff}.ai-trade-actions .ai-wait{padding:10px 12px;border:1px solid var(--line);border-radius:10px;color:var(--muted);font-size:12px;text-align:center}.ai-trade-actions small{color:var(--muted);font-size:10px;text-align:center}`;document.head.appendChild(s);}
    return box;
  }
  function renderAITradeActions(recommendation,prediction){
    const box=actionBox();if(!box)return;
    const confidence=Number(prediction.confidence??recommendation.confidence??0),rec=String(recommendation.recommendation||'WAIT').toUpperCase(),source=String(prediction.payload?.source||'no_trained_model');
    const actionable=source==='trained_ensemble'&&confidence>=65&&(rec==='BUY'||rec==='SELL');
    if(!actionable){box.innerHTML=`<div class="ai-wait">AI trade gate: ${esc(source==='no_trained_model'?'No trained model available':`${rec} at ${confidence.toFixed(1)}% confidence — waiting for ≥65% actionable confidence.`)}</div>`;return;}
    const label=rec==='BUY'?'BUY with AI signal':'SELL with AI signal';
    box.innerHTML=`<button type="button" class="ai-action ${rec==='BUY'?'ai-buy':'ai-sell'}" data-ai-direction="${rec}">${esc(label)}</button><small>Trained-model confidence ${confidence.toFixed(1)}%. Final broker/risk validation still applies.</small>`;
    $('[data-ai-direction]',box)?.addEventListener('click',()=>{const target=document.querySelector(`[data-direction="${rec}"]`);target?.click();window.__algobotAiOrderContext={ai_assisted:true,timeframe:$('#timeframe')?.value||'M1',minimum_ai_confidence:65,ai_decision:{recommendation:rec,confidence}};const form=$('[data-order-form]');if(form)form.requestSubmit();});
  }
  const render=result=>{
    const prediction=result.prediction||{},recommendation=result.recommendation||{},regime=result.regime||{},explanation=result.explainability||{};
    $('[data-ai-prediction]')?.replaceChildren(document.createTextNode(prediction.prediction||'No signal'));
    $('[data-ai-recommendation]')?.replaceChildren(document.createTextNode(recommendation.recommendation||'WAIT'));
    $('[data-ai-confidence-card]')?.replaceChildren(document.createTextNode(prediction.confidence!=null?`${Number(prediction.confidence).toFixed(1)}%`:'Unavailable'));
    $('[data-ai-confidence]')?.replaceChildren(document.createTextNode(prediction.confidence!=null?`${Number(prediction.confidence).toFixed(1)}%`:'Unavailable'));
    $('[data-ai-regime]')?.replaceChildren(document.createTextNode(regime.regime||'Unavailable'));
    $('[data-recommended]')?.replaceChildren(document.createTextNode(recommendation.recommendation||'WAIT'));
    const factors=Array.isArray(explanation.decision_factors)?explanation.decision_factors.join(', '):'',source=prediction.payload?.source||(prediction.payload?.models_used?`${prediction.payload.models_used} trained models`:'no_trained_model'),box=$('[data-ai-explanation]');
    if(box)box.innerHTML=`<strong>AI status:</strong> ${esc(source)}. ${esc(explanation.explanation||'')}${factors?`<br><small>Key factors: ${esc(factors)}</small>`:''}`;
    renderAITradeActions(recommendation,prediction);
  };
  async function analyze(){
    const symbol=$('#symbol')?.value||$('[data-symbol]')?.value,timeframe=$('#timeframe')?.value||$('[data-timeframe]')?.value||'M1',button=$('[data-ai-analyze]');
    if(!symbol){$('[data-ai-explanation]')?.replaceChildren(document.createTextNode('Connect and synchronize a broker market before requesting AI analysis.'));return;}
    if(button){button.disabled=true;button.textContent='Analysing…';}
    try{render(await request('/api/ai/predict/',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({symbol,timeframe})}));}
    catch(e){$('[data-ai-explanation]')?.replaceChildren(document.createTextNode(`AI unavailable: ${e.message}`));renderAITradeActions({recommendation:'WAIT'},{payload:{source:'ai_unavailable'},confidence:0});}
    finally{if(button){button.disabled=false;button.textContent='Analyse market';}}
  }
  window.addEventListener('DOMContentLoaded',()=>{if(!$('[data-ai-panel]'))return;$('[data-ai-analyze]')?.addEventListener('click',analyze);$('#symbol')?.addEventListener('change',()=>{$('[data-ai-explanation]')?.replaceChildren(document.createTextNode('Market changed. Run AI analysis for the selected broker market.'));const box=$('[data-ai-trade-actions]');if(box)box.innerHTML='<div class="ai-wait">Run AI analysis for the selected broker market.</div>';window.__algobotAiOrderContext=null;});},{once:true});
})();
