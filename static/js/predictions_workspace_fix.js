(() => {
  const page = document.querySelector('[data-page="core-predictions"]');
  if (!page) return;
  const esc = v => String(v ?? '—').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const list = v => Array.isArray(v) ? v : (Array.isArray(v?.results) ? v.results : (Array.isArray(v?.data) ? v.data : []));
  const getJSON = async url => { const request=window.AlgoBotFrontendData?.request; if(typeof request!=='function') throw new Error('Authenticated API transport is not ready. Refresh the page and try again.'); return request(url,{headers:{Accept:'application/json'}},10000); };
  const inject = () => { if(document.getElementById('algobot-ai-lab-style')) return; const s=document.createElement('style'); s.id='algobot-ai-lab-style'; s.textContent=`
  [data-page="core-predictions"]{color:#e6f1ff}.ai-lab{display:grid;gap:18px;margin:18px auto 32px;max-width:1440px;color:#dbeafe}.ai-hero{display:flex;align-items:center;gap:16px;padding:4px 4px 12px}.ai-hero-icon{display:grid;place-items:center;flex:0 0 64px;height:64px;border-radius:20px;background:linear-gradient(145deg,#163e9b,#652fe3);font-size:32px}.ai-hero h1{font-size:clamp(1.65rem,3vw,2.5rem);margin:0;color:#f4f8ff;letter-spacing:-.03em}.ai-hero p{margin:5px 0 0;color:#9bbce7}.ai-pill-row{display:flex;gap:8px;flex-wrap:wrap;margin-left:auto}.ai-pill,.ai-badge{display:inline-flex;align-items:center;gap:6px;padding:5px 10px;border:1px solid #173c69;border-radius:999px;background:#082443;color:#6dd7ff;font-size:.78rem;font-weight:700}.ai-pill.live{color:#34e4b0;background:#06362f;border-color:#075b4b}.ai-lab-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.ai-lab-card{min-width:0;padding:18px;border:1px solid #173b66;border-radius:14px;background:linear-gradient(145deg,#071d39,#06152c);box-shadow:0 8px 24px #0002}.ai-lab-card h2,.ai-lab-card h3{margin:0 0 10px;color:#f2f7ff}.ai-stat-label{color:#a9c7ed;font-size:.9rem}.ai-lab-value{font-size:clamp(1.4rem,2.4vw,2rem);font-weight:800;color:#f5f9ff;margin:10px 0 2px}.ai-stat-note{color:#25d6a2;font-size:.82rem}.ai-section-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px}.ai-section-head h2{margin:0;font-size:1.05rem}.ai-lab-controls{display:flex;gap:10px;flex-wrap:wrap}.ai-lab-controls input,.ai-lab-controls select{min-width:0;padding:11px 12px;border:1px solid #214b78;border-radius:9px;background:#071a33;color:#e5f1ff}.ai-lab-controls button,.ai-action{padding:11px 16px;border:0;border-radius:9px;background:linear-gradient(100deg,#078e7a,#0db78b);color:white;font-weight:800;cursor:pointer;text-decoration:none}.ai-scroll{overflow:auto;border:1px solid #173b66;border-radius:10px}.ai-lab-table{width:100%;border-collapse:collapse;min-width:760px}.ai-lab-table th,.ai-lab-table td{text-align:left;padding:12px 10px;border-bottom:1px solid #142f51;font-size:.86rem}.ai-lab-table th{background:#0a2547;color:#a9c7ed;font-weight:600}.ai-lab-table td{color:#d6e8ff}.ai-lab-table tr:last-child td{border-bottom:0}.ai-badge.up{color:#2ce0ac;background:#063d36;border-color:#07584a}.ai-badge.down{color:#ff8392;background:#401b2c;border-color:#6d2a40}.ai-badge.mid{color:#5cc9ff;background:#082d52}.ai-model-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.ai-model{padding:14px;border:1px solid #183d67;border-radius:12px;background:#071a33}.ai-note{color:#9bb8df;font-size:.86rem}.ai-result{margin-top:14px;padding:14px;border:1px solid #1b4978;border-radius:12px;background:#081d37}.ai-error{padding:12px;border-radius:10px;background:#351c2a;color:#ffc4ce}.ai-panels{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(280px,1fr);gap:16px}.ai-chart{min-height:230px;display:grid;place-items:center;border:1px solid #173b66;border-radius:10px;background:repeating-linear-gradient(0deg,transparent 0 43px,#102b4a 44px),repeating-linear-gradient(90deg,transparent 0 64px,#102b4a 65px);color:#9bb8df;text-align:center;padding:18px}.ai-detail-list{display:grid;gap:10px}.ai-detail-row{display:flex;justify-content:space-between;gap:12px;padding-bottom:9px;border-bottom:1px solid #173654}.ai-detail-row strong{color:#f1f7ff;text-align:right}.ai-insight-list{display:grid;gap:12px}.ai-insight{display:grid;grid-template-columns:90px minmax(0,1fr) auto;gap:10px;align-items:center;color:#b9d1f1;font-size:.86rem}.ai-footer{display:flex;align-items:center;gap:12px;padding:16px;border:1px solid #173b66;border-radius:12px;background:#071c37;color:#b5d2f4}.ai-empty{color:#9bb8df;padding:12px 4px}.ai-lab button:disabled{opacity:.6;cursor:wait}@media(max-width:900px){.ai-lab-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.ai-panels{grid-template-columns:1fr}.ai-pill-row{margin-left:0}}@media(max-width:560px){.ai-lab-grid{grid-template-columns:1fr 1fr;gap:9px}.ai-lab-card{padding:13px}.ai-hero{align-items:flex-start;flex-wrap:wrap}.ai-hero-icon{flex-basis:52px;height:52px}.ai-pill-row{width:100%}.ai-model-grid{grid-template-columns:1fr}.ai-insight{grid-template-columns:70px minmax(0,1fr)}.ai-insight .ai-badge{grid-column:2}.ai-lab-controls>*{flex:1 1 100%}.ai-stat-label{font-size:.8rem}}`; document.head.appendChild(s); };
  const mount = () => { inject(); let root=page.querySelector('[data-ai-lab]'); if(root) return root; root=document.createElement('div'); root.setAttribute('data-ai-lab',''); root.className='ai-lab'; root.innerHTML='<header class="ai-hero"><div class="ai-hero-icon" aria-hidden="true">♧</div><div><h1>AI Predictions</h1><p>Next 24 hours · model-backed outputs only</p><p>AI insights from real market data and validated models — no guessed signals.</p></div><div class="ai-pill-row"><span class="ai-pill">✦ AI Powered</span><span class="ai-pill live">● Live data when available</span></div></header><div class="ai-lab-grid"><article class="ai-lab-card"><div class="ai-stat-label">▥ Total Predictions</div><div class="ai-lab-value" data-ai-count>—</div><div class="ai-stat-note">Recorded predictions</div></article><article class="ai-lab-card"><div class="ai-stat-label">◉ High Confidence (≥70%)</div><div class="ai-lab-value" data-ai-high>—</div><div class="ai-stat-note" data-ai-high-note>Based on recorded outputs</div></article><article class="ai-lab-card"><div class="ai-stat-label">◎ Accuracy Rate (last 7d)</div><div class="ai-lab-value" data-ai-accuracy>Unavailable</div><div class="ai-stat-note">Only if verified outcome labels exist</div></article><article class="ai-lab-card"><div class="ai-stat-label">▦ Model Status</div><div class="ai-lab-value" data-ai-status>—</div><div class="ai-stat-note" data-ai-status-note>Checking registered models</div></article></div><section class="ai-lab-card"><div class="ai-section-head"><h2>⭐ Top AI Predictions</h2><span class="ai-note">Verified model outputs only</span></div><div class="ai-scroll"><table class="ai-lab-table"><thead><tr><th>Asset</th><th>Direction</th><th>Probability</th><th>Confidence</th><th>Timeframe</th><th>AI Insight</th></tr></thead><tbody data-ai-history><tr><td colspan="6">Loading recorded predictions…</td></tr></tbody></table></div></section><div class="ai-panels"><section class="ai-lab-card"><div class="ai-section-head"><h2>▧ AI Forecast &amp; Chart</h2><span class="ai-note" data-ai-chart-symbol>Choose a recorded prediction</span></div><div class="ai-chart" data-ai-chart>No verified historical candles or forecast series are available to plot yet.</div><p class="ai-note">Chart lines and forecast ranges appear only when the API supplies actual candle and model forecast points.</p></section><section class="ai-lab-card"><h2>₿ Selected Prediction</h2><p class="ai-note" data-ai-selected>Choose a prediction row to inspect its details.</p><div class="ai-detail-list" data-ai-details><div class="ai-empty">No prediction selected.</div></div><a class="ai-action" href="/analysis/">View Full Analysis →</a></section></div><div class="ai-panels"><section class="ai-lab-card"><h2>◈ AI Model Performance</h2><p class="ai-note">Last 7 days · metrics shown only when supplied by validated models.</p><div class="ai-lab-grid" style="grid-template-columns:repeat(2,minmax(0,1fr))"><div><div class="ai-stat-label">Registered models</div><div class="ai-lab-value" data-ai-model-count>—</div></div><div><div class="ai-stat-label">Training jobs</div><div class="ai-lab-value" data-ai-job-count>—</div></div><div><div class="ai-stat-label">Average confidence</div><div class="ai-lab-value" data-ai-confidence>—</div></div><div><div class="ai-stat-label">Validated accuracy</div><div class="ai-lab-value" data-ai-accuracy-small>—</div></div></div><div class="ai-model-grid" data-ai-models></div></section><section class="ai-lab-card"><div class="ai-section-head"><h2>♧ Recent AI Insights</h2><span class="ai-note">From prediction records</span></div><div class="ai-insight-list" data-ai-insights><p class="ai-empty">No verified insights recorded.</p></div></section></div><section class="ai-lab-card"><h2>Run a model-backed prediction</h2><p class="ai-note">Use a symbol available to your connected broker. Results remain advisory and do not bypass risk or execution controls.</p><div class="ai-lab-controls"><input data-ai-symbol placeholder="Broker symbol, e.g. R_75" aria-label="Prediction symbol"><select data-ai-timeframe aria-label="Prediction timeframe"><option value="M1">1 minute</option><option value="M5">5 minutes</option><option value="M15">15 minutes</option><option value="H1" selected>1 hour</option><option value="H4">4 hours</option><option value="D1">1 day</option></select><button class="ai-action" data-ai-run>Run prediction</button><a class="ai-action" href="/strategies/">Explore Strategies →</a></div><div data-ai-result></div></section><footer class="ai-footer"><span class="ai-hero-icon" style="width:40px;height:40px;flex-basis:40px;font-size:20px">♧</span><span>AI Predictions are advisory. Trade smarter with verified data, validated models, and risk controls — not guesswork.</span></footer>'; const target=page.querySelector('.enterprise-page-body')||page; target.appendChild(root); return root; };
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
    const calibrated = ps.filter(p => Number(p.payload?.models_used || 0) > 0 && p.confidence != null && p.confidence !== '' && Number.isFinite(Number(p.confidence)));
    set('[data-ai-confidence]', !predictionOk || !calibrated.length
      ? 'Unavailable'
      : (calibrated.reduce((sum, p) => sum + Number(p.confidence), 0) / calibrated.length).toFixed(1) + '%');
    const mg = root.querySelector('[data-ai-models]');
    if (!modelOk) {
      mg.innerHTML = '<p class="ai-note">Model registry unavailable. Model count and validation metrics have not been inferred.</p>';
    } else {
      mg.innerHTML = ms.length ? ms.slice(0, 12).map(m => {
        const validated = ['active', 'champion'].includes(String(m.status || '').toLowerCase());
        const metric = value => validated && value != null && value !== '' && Number.isFinite(Number(value)) ? esc(Number(value).toFixed(3)) : 'Not validated';
        return `<article class="ai-model"><strong>${esc(m.name)}</strong><div>v${esc(m.version)} · ${esc(m.algorithm)}</div><div>Status: <span class="ai-badge">${esc(m.status)}</span></div><div>Accuracy: ${metric(m.accuracy)}</div><div>Precision: ${metric(m.precision)}</div><div>Recall: ${metric(m.recall)}</div><div>F1: ${metric(m.f1_score)}</div><div>AUC: ${metric(m.auc)}</div></article>`;
      }).join('') : '<p class="ai-note">No registered models yet. Train and validate a model before treating predictions as actionable.</p>';
    }
    const validConfidence = p => p.confidence != null && p.confidence !== '' && Number.isFinite(Number(p.confidence));
    const modeled = ps.filter(p => Number(p.payload?.models_used || 0) > 0);
    const high = modeled.filter(p => validConfidence(p) && Number(p.confidence) >= 70);
    set('[data-ai-high]', predictionOk ? String(high.length) : 'Unavailable');
    set('[data-ai-high-note]', predictionOk ? (modeled.length ? Math.round(high.length / modeled.length * 100) + '% of model-backed outputs' : 'No model-backed outputs yet') : 'Prediction API unavailable');
    set('[data-ai-accuracy]', 'Unavailable');
    set('[data-ai-accuracy-small]', 'Unavailable');
    const activeModels = ms.filter(m => ['active','champion'].includes(String(m.status || '').toLowerCase()));
    set('[data-ai-status]', !modelOk ? 'Unavailable' : activeModels.length ? 'Online' : 'Not validated');
    set('[data-ai-status-note]', !modelOk ? 'Model registry could not be reached' : activeModels.length ? activeModels.length + ' active/champion model(s)' : 'No active validated model');
    set('[data-ai-chart-symbol]', 'Model forecast · selected asset');
    const hb = root.querySelector('[data-ai-history]');
    if (!predictionOk) {
      hb.innerHTML = '<tr><td colspan="6">Prediction history unavailable. Check the authenticated AI API and server logs.</td></tr>';
    } else {
      hb.innerHTML = ps.length ? ps.slice(0, 20).map((p, i) => {
        const hasModel = Number(p.payload?.models_used || 0) > 0;
        const probability = hasModel && p.probability != null && p.probability !== '' && Number.isFinite(Number(p.probability)) ? (Number(p.probability) <= 1 ? Number(p.probability) * 100 : Number(p.probability)).toFixed(1) + '%' : '—';
        const confidence = hasModel && validConfidence(p) ? Number(p.confidence).toFixed(1) + '%' : '—';
        const direction = String(p.prediction || '').toLowerCase();
        const up = /up|bull|buy|rise|long/.test(direction), down = /down|bear|sell|fall|short/.test(direction);
        const badge = up ? 'up' : down ? 'down' : 'mid';
        const symbol = esc(p.symbol || 'Unknown asset');
        return '<tr data-ai-row="' + i + '" tabindex="0" role="button"><td><strong>' + symbol + '</strong></td><td><span class="ai-badge ' + badge + '">' + (up ? '↑ UP' : down ? '↓ DOWN' : esc(p.prediction || 'UNAVAILABLE')) + '</span></td><td>' + probability + '</td><td>' + (confidence === '—' ? '<span class="ai-badge mid">Unverified</span>' : '<span class="ai-badge ' + (Number(p.confidence) >= 70 ? 'up' : 'mid') + '">' + confidence + '</span>') + '</td><td>' + esc(p.timeframe || '—') + '</td><td>' + esc(p.payload?.insight || p.payload?.explanation || (hasModel ? 'Model-backed output recorded.' : 'No verified strategy evidence')) + '</td></tr>';
      }).join('') : '<tr><td colspan="6">No predictions recorded yet. Run a model-backed prediction below when market data and a validated model are available.</td></tr>';
    }
    const renderSelected = p => {
      if (!p) return;
      const hasModel = Number(p.payload?.models_used || 0) > 0;
      set('[data-ai-selected]', (p.symbol || 'Asset') + ' · ' + (p.timeframe || 'timeframe'));
      const details = root.querySelector('[data-ai-details]');
      const confidence = hasModel && validConfidence(p) ? Number(p.confidence).toFixed(1) + '%' : 'Unavailable';
      const probability = hasModel && p.probability != null && p.probability !== '' && Number.isFinite(Number(p.probability)) ? (Number(p.probability) <= 1 ? Number(p.probability) * 100 : Number(p.probability)).toFixed(1) + '%' : 'Unavailable';
      details.innerHTML = [['Direction',esc(p.prediction || 'Unavailable')],['Probability',probability],['Confidence',confidence],['Timeframe',esc(p.timeframe || '—')],['Recorded',esc(p.created_at || '—')],['Risk score',p.risk_score != null && Number.isFinite(Number(p.risk_score)) ? Number(p.risk_score).toFixed(2) : 'Unavailable']].map(([k,v]) => '<div class="ai-detail-row"><span>' + k + '</span><strong>' + v + '</strong></div>').join('');
      const chart = root.querySelector('[data-ai-chart]');
      const series = p.payload?.forecast_points || p.payload?.forecast || [];
      if (Array.isArray(series) && series.length) chart.textContent = 'Forecast data received (' + series.length + ' points). Chart rendering requires numeric price values from the model response.';
      else chart.textContent = 'No verified candle/forecast series supplied for ' + (p.symbol || 'this asset') + '. The chart will not invent prices.';
    };
    hb.querySelectorAll('[data-ai-row]').forEach(row => {
      const selectRow = () => renderSelected(ps[Number(row.getAttribute('data-ai-row'))]);
      row.addEventListener('click', selectRow);
      row.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); selectRow(); } });
    });
    const insights = root.querySelector('[data-ai-insights]');
    insights.innerHTML = ps.length ? ps.slice(0, 6).map(p => {
      const direction = String(p.prediction || '').toLowerCase();
      const up = /up|bull|buy|rise|long/.test(direction), down = /down|bear|sell|fall|short/.test(direction);
      return '<div class="ai-insight"><span>' + esc(p.created_at || 'Recorded') + '</span><span><strong>' + esc(p.symbol || 'Asset') + '</strong> · ' + esc(p.payload?.insight || p.payload?.explanation || 'No verified insight supplied by model') + '</span><span class="ai-badge ' + (up ? 'up' : down ? 'down' : 'mid') + '">' + (up ? 'UP' : down ? 'DOWN' : 'UNAVAILABLE') + '</span></div>';
    }).join('') : '<p class="ai-empty">No verified insights recorded.</p>';
    if (ps.length) renderSelected(ps[0]);
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
        out.innerHTML = `<div class="ai-result"><h3>${esc(d.symbol)} · ${esc(d.timeframe)}</h3><div class="ai-lab-grid"><div>Prediction<br><strong>${esc(p.prediction)}</strong></div><div>Confidence<br><strong>${hasModel && p.confidence != null && p.confidence !== '' && Number.isFinite(Number(p.confidence)) ? Number(p.confidence).toFixed(1)+'%' : 'Unavailable'}</strong></div><div>Recommendation<br><strong>${esc(rec.recommendation)}</strong></div><div>Regime<br><strong>${esc(reg.regime)}</strong></div></div><p class="ai-note">Models used: ${esc(cons.models_used ?? p.payload?.models_used ?? 0)} · Source: ${esc(p.payload?.source || 'configured AI engine')} · Broker: ${esc(d.broker)}.</p><p class="ai-note">AI output is advisory and remains subject to configured consensus, risk and execution gates.</p></div>`;
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