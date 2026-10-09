(() => {
  const page = document.querySelector('[data-page="core-predictions"]');
  if (!page) return;
  const esc = v => String(v ?? '—').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const list = v => Array.isArray(v) ? v : (Array.isArray(v?.results) ? v.results : (Array.isArray(v?.data) ? v.data : []));
  const getJSON = async url => { const request=window.AlgoBotFrontendData?.request; if(typeof request!=='function') throw new Error('Authenticated API transport is not ready. Refresh the page and try again.'); return request(url,{headers:{Accept:'application/json'}},10000); };
  const inject = () => { if(document.getElementById('algobot-ai-lab-style')) return; const s=document.createElement('style'); s.id='algobot-ai-lab-style'; s.textContent='.ai-lab{display:grid;gap:18px;margin-top:18px}.ai-lab-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.ai-lab-card{padding:18px;border:1px solid var(--border-color,#e5e7eb);border-radius:14px;background:var(--panel-bg,#fff)}.ai-lab-card h2,.ai-lab-card h3{margin:0 0 8px}.ai-lab-value{font-size:1.45rem;font-weight:800}.ai-lab-controls{display:flex;gap:10px;flex-wrap:wrap}.ai-lab-controls input,.ai-lab-controls select{padding:10px;border:1px solid var(--border-color,#d1d5db);border-radius:9px;background:inherit}.ai-lab-table{width:100%;border-collapse:collapse}.ai-lab-table th,.ai-lab-table td{text-align:left;padding:10px;border-bottom:1px solid var(--border-color,#eee);font-size:.88rem}.ai-badge{display:inline-block;padding:4px 8px;border-radius:999px;background:#eef2ff}.ai-model-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}.ai-model{padding:14px;border:1px solid var(--border-color,#e5e7eb);border-radius:12px}.ai-note{opacity:.7;font-size:.86rem}.ai-result{margin-top:14px;padding:14px;border-radius:12px;background:var(--surface-muted,#f8fafc)}.ai-error{padding:12px;border-radius:10px;background:#fff1f2}.ai-scroll{overflow:auto}@media(max-width:900px){.ai-lab-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:600px){.ai-lab-grid{grid-template-columns:1fr}.ai-lab-table{min-width:720px}}'; document.head.appendChild(s); };
  const mount = () => { inject(); let root=page.querySelector('[data-ai-lab]'); if(root) return root; root=document.createElement('div'); root.setAttribute('data-ai-lab',''); root.className='ai-lab'; root.innerHTML='<div class="ai-lab-grid"><article class="ai-lab-card"><h3>Predictions</h3><div class="ai-lab-value" data-ai-count>—</div></article><article class="ai-lab-card"><h3>Avg confidence</h3><div class="ai-lab-value" data-ai-confidence>—</div></article><article class="ai-lab-card"><h3>Registered models</h3><div class="ai-lab-value" data-ai-model-count>—</div></article><article class="ai-lab-card"><h3>Training jobs</h3><div class="ai-lab-value" data-ai-job-count>—</div></article></div><section class="ai-lab-card"><h2>AI Model Lab</h2><p class="ai-note">Model registry, validation metrics and training state. Predictions remain advisory and cannot bypass risk or broker execution controls.</p><div class="ai-model-grid" data-ai-models></div></section><section class="ai-lab-card"><h2>Run broker-backed prediction</h2><div class="ai-lab-controls"><input data-ai-symbol placeholder="Active broker symbol, e.g. R_75" aria-label="Prediction symbol"><select data-ai-timeframe aria-label="Prediction timeframe"><option>M1</option><option>M5</option><option>M15</option><option>H1</option></select><button class="btn primary" data-ai-run>Run prediction</button><a class="btn" href="/backtesting/">Open backtesting</a></div><div data-ai-result></div></section><section class="ai-lab-card"><h2>Prediction history</h2><div class="ai-scroll"><table class="ai-lab-table"><thead><tr><th>Symbol</th><th>Timeframe</th><th>Prediction</th><th>Probability</th><th>Confidence</th><th>Risk</th><th>Created</th></tr></thead><tbody data-ai-history><tr><td colspan="7">Loading…</td></tr></tbody></table></div></section></div>'; const target=page.querySelector('.enterprise-page-body')||page; target.appendChild(root); return root; };
  const load = async root => {
    const [models, preds, jobs] = await Promise.allSettled([
      getJSON('/api/ai/models/'),
      getJSON('/api/ai/predictions/'),
      getJSON('/api/ai/training-jobs/')
    ]);
    const modelOk = models.status === 'fulfilled';
    const predictionOk = preds.status === 'fulfilled';
    const jobsOk = jobs.status === 'fulfilled';
    const ms = modelOk ? list(models.value) : [];
    const ps = predictionOk ? list(preds.value) : [];
    const js = jobsOk ? list(jobs.value) : [];
    const set = (q, v) => { const e = root.querySelector(q); if (e) e.textContent = v; };
    set('[data-ai-count]', predictionOk ? String(ps.length) : 'Unavailable');
    set('[data-ai-model-count]', modelOk ? String(ms.length) : 'Unavailable');
    set('[data-ai-job-count]', jobsOk ? String(js.length) : 'Unavailable');
    const calibrated = ps.filter(p => Number(p.payload?.models_used || 0) > 0 && Number.isFinite(Number(p.confidence)));
    set('[data-ai-confidence]', !predictionOk || !calibrated.length
      ? 'Unavailable'
      : (calibrated.reduce((sum, p) => sum + Number(p.confidence), 0) / calibrated.length).toFixed(1) + '%');
    const mg = root.querySelector('[data-ai-models]');
    if (!modelOk) {
      mg.innerHTML = '<p class="ai-note">Model registry unavailable. Model count and validation metrics have not been inferred.</p>';
    } else {
      mg.innerHTML = ms.length ? ms.slice(0, 12).map(m => {
        const validated = ['active', 'champion'].includes(String(m.status || '').toLowerCase());
        const metric = value => validated && Number.isFinite(Number(value)) ? esc(Number(value).toFixed(3)) : 'Not validated';
        return `<article class="ai-model"><strong>${esc(m.name)}</strong><div>v${esc(m.version)} · ${esc(m.algorithm)}</div><div>Status: <span class="ai-badge">${esc(m.status)}</span></div><div>Accuracy: ${metric(m.accuracy)}</div><div>Precision: ${metric(m.precision)}</div><div>Recall: ${metric(m.recall)}</div><div>F1: ${metric(m.f1_score)}</div><div>AUC: ${metric(m.auc)}</div></article>`;
      }).join('') : '<p class="ai-note">No registered models yet. Train and validate a model before treating predictions as actionable.</p>';
    }
    const hb = root.querySelector('[data-ai-history]');
    if (!predictionOk) {
      hb.innerHTML = '<tr><td colspan="7">Prediction history unavailable.</td></tr>';
    } else {
      hb.innerHTML = ps.length ? ps.slice(0, 50).map(p => {
        const hasModel = Number(p.payload?.models_used || 0) > 0;
        const probability = hasModel && Number.isFinite(Number(p.probability)) ? (Number(p.probability) * 100).toFixed(1) + '%' : '—';
        const confidence = hasModel && Number.isFinite(Number(p.confidence)) ? Number(p.confidence).toFixed(1) + '%' : '—';
        return `<tr><td>${esc(p.symbol)}</td><td>${esc(p.timeframe)}</td><td>${esc(p.prediction)}</td><td>${probability}</td><td>${confidence}</td><td>${Number.isFinite(Number(p.risk_score)) ? Number(p.risk_score).toFixed(2) : '—'}</td><td>${esc(p.created_at)}</td></tr>`;
      }).join('') : '<tr><td colspan="7">No predictions recorded.</td></tr>';
    }
  };
  const bind = root => {
    const button = root.querySelector('[data-ai-run]');
    button?.addEventListener('click', async () => {
      const symbol = root.querySelector('[data-ai-symbol]').value.trim();
      const timeframe = root.querySelector('[data-ai-timeframe]').value;
      const out = root.querySelector('[data-ai-result]');
      if (!symbol) { out.innerHTML = '<div class="ai-error">Enter an active broker symbol.</div>'; return; }
      button.disabled = true;
      out.innerHTML = '<div class="ai-result">Requesting broker-backed market data and running the configured AI engine…</div>';
      try {
        const request = window.AlgoBotFrontendData?.request;
        if (typeof request !== 'function') throw new Error('Authenticated API transport is not ready. Refresh the page and try again.');
        const d = await request('/api/ai/predict/', {method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json'},body:JSON.stringify({symbol,timeframe})});
        const p = d.prediction || {}, rec = d.recommendation || {}, reg = d.regime || {}, cons = p.payload?.consensus || {};
        const hasModel = Number(cons.models_used || p.payload?.models_used || 0) > 0;
        out.innerHTML = `<div class="ai-result"><h3>${esc(d.symbol)} · ${esc(d.timeframe)}</h3><div class="ai-lab-grid"><div>Prediction<br><strong>${esc(p.prediction)}</strong></div><div>Confidence<br><strong>${hasModel && Number.isFinite(Number(p.confidence)) ? Number(p.confidence).toFixed(1)+'%' : 'Unavailable'}</strong></div><div>Recommendation<br><strong>${esc(rec.recommendation)}</strong></div><div>Regime<br><strong>${esc(reg.regime)}</strong></div></div><p class="ai-note">Models used: ${esc(cons.models_used ?? p.payload?.models_used ?? 0)} · Source: ${esc(p.payload?.source || 'configured AI engine')} · Broker: ${esc(d.broker)}.</p><p class="ai-note">AI output is advisory and remains subject to configured consensus, risk and execution gates.</p></div>`;
        await load(root);
      } catch (e) {
        out.innerHTML = `<div class="ai-error">${esc(e.message)}</div>`;
      } finally {
        button.disabled = false;
      }
    });
  };
  const run = async () => { const root=mount(); try{await load(root);}catch(e){const h=root.querySelector('[data-ai-history]');if(h)h.innerHTML=`<tr><td colspan="7">AI data unavailable: ${esc(e.message)}</td></tr>`;} bind(root); };
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',run,{once:true}); else run();
})();