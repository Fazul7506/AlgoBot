/* Trading-terminal AI decision bridge. */
(() => {
  'use strict';
  if (window.__algobotTradingTerminalAI) return;
  window.__algobotTradingTerminalAI = true;

  const $ = (s, r = document) => r.querySelector(s);
  const text = (s, value) => $(s)?.replaceChildren(document.createTextNode(String(value ?? '—')));
  const api = (url, options = {}, timeout = 15000) => window.AlgoBotFrontendData?.request(url, options, timeout);
  let analysing = false;
  let scheduledSymbol = '';
  let autoTimer = null;

  function show(message) { text('[data-ai-explanation]', message); }

  function render(data) {
    const prediction = data?.prediction || {};
    const recommendation = data?.recommendation || {};
    const regime = data?.regime || {};
    const confidenceRaw = prediction.confidence ?? recommendation.confidence;
    const confidenceNumber = Number(confidenceRaw);
    const confidence = confidenceRaw == null ? '—' : `${(confidenceNumber <= 1 ? confidenceNumber * 100 : confidenceNumber).toFixed(1)}%`;
    const predictionLabel = prediction.prediction ?? prediction.direction ?? prediction.label ?? prediction.class ?? '—';
    const recommendationLabel = recommendation.recommendation ?? recommendation.action ?? recommendation.signal ?? recommendation.direction ?? '—';
    const regimeLabel = regime.regime ?? regime.name ?? regime.label ?? '—';

    text('[data-ai-prediction]', predictionLabel);
    text('[data-ai-recommendation]', recommendationLabel);
    text('[data-ai-confidence-card]', confidence);
    text('[data-ai-confidence]', confidence);
    text('[data-ai-regime]', regimeLabel);

    const explanation = data?.explainability;
    if (typeof explanation === 'string') show(explanation);
    else if (explanation && typeof explanation === 'object') {
      const summary = explanation.summary || explanation.reason || explanation.explanation;
      show(summary || `AI analysis completed for ${data.symbol || $('#symbol')?.value || 'the selected market'}.`);
    } else show(`AI analysis completed for ${data.symbol || $('#symbol')?.value || 'the selected market'}.`);

    const actionable = String(recommendationLabel).toUpperCase() !== 'WAIT' && String(predictionLabel).toUpperCase() !== 'AVOID' && Number.isFinite(confidenceNumber) && (confidenceNumber <= 1 ? confidenceNumber * 100 : confidenceNumber) >= 65;
    window.__algobotAiOrderContext = {
      ...(window.__algobotAiOrderContext || {}),
      ai_prediction: predictionLabel,
      ai_recommendation: recommendationLabel,
      ai_confidence: Number.isFinite(confidenceNumber) ? confidenceNumber : null,
      ai_regime: regimeLabel,
      ai_actionable: actionable,
      ai_source: data?.market_context_source ? `decision_engine:${data.market_context_source}` : 'decision_engine',
    };
    window.dispatchEvent(new CustomEvent('algobot:ai-gate-updated', {detail:{actionable, confidence:confidenceNumber, recommendation:recommendationLabel, prediction:predictionLabel}}));
  }

  async function analyse({silent = false} = {}) {
    if (analysing) return;
    const button = $('[data-ai-analyze]');
    const symbol = $('#symbol')?.value;
    if (!symbol) { if (!silent) show('Select a broker instrument before running AI analysis.'); return; }
    analysing = true;
    if (button && !silent) { button.disabled = true; button.textContent = 'Analysing…'; }
    if (!silent) show('Running AI inference from the latest persisted broker market feed…');
    try {
      const data = await api('/api/ai/predict/', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({symbol, timeframe: 'M1'})
      }, 15000);
      render(data);
      scheduledSymbol = symbol;
      window.dispatchEvent(new CustomEvent('algobot:ai-analysis-updated', {detail: data}));
    } catch (error) {
      text('[data-ai-prediction]', 'Unavailable');
      text('[data-ai-recommendation]', 'Unavailable');
      text('[data-ai-confidence-card]', 'Unavailable');
      text('[data-ai-confidence]', 'Unavailable');
      text('[data-ai-regime]', 'Unavailable');
      window.__algobotAiOrderContext = null;
      const message = String(error?.message || 'AI analysis is temporarily unavailable.');
      show(message.includes('EDGE_CHALLENGE') || error?.code === 'EDGE_CHALLENGE' || message.includes('<html') || message.includes('Just a moment') ? 'AI analysis is temporarily unavailable at the production edge. Live execution remains blocked until a verified AI decision is available.' : message);
      window.dispatchEvent(new CustomEvent('algobot:ai-gate-updated', {detail:{actionable:false, error:true, code:error?.code || null}}));
    } finally {
      analysing = false;
      if (button && !silent) { button.disabled = false; button.textContent = 'Analyse market'; }
    }
  }

  function scheduleAutoAnalysis() {
    const symbol = $('#symbol')?.value;
    if (!symbol || symbol === scheduledSymbol) return;
    clearTimeout(autoTimer);
    autoTimer = setTimeout(() => analyse({silent:true}), 250);
  }

  function boot() {
    if (!$('.terminal-page')) return;
    $('[data-ai-analyze]')?.addEventListener('click', () => analyse());
    window.addEventListener('algobot:broker-symbols-loaded', scheduleAutoAnalysis);
    window.addEventListener('algobot:market-symbol-changed', () => {
      scheduledSymbol = '';
      text('[data-ai-prediction]', 'Analysing…');
      text('[data-ai-recommendation]', 'Waiting for decision');
      text('[data-ai-confidence-card]', '—');
      text('[data-ai-confidence]', 'Not analysed');
      text('[data-ai-regime]', 'Waiting for analysis');
      show('Refreshing the AI decision for the selected broker market…');
      scheduleAutoAnalysis();
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once: true});
  else boot();
})();