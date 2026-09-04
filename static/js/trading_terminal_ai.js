/* Trading-terminal AI decision bridge. */
(() => {
  'use strict';
  if (window.__algobotTradingTerminalAI) return;
  window.__algobotTradingTerminalAI = true;

  const $ = (s, r = document) => r.querySelector(s);
  const text = (s, value) => $(s)?.replaceChildren(document.createTextNode(String(value ?? '—')));
  const api = (url, options = {}, timeout = 30000) => window.AlgoBotFrontendData?.request(url, options, timeout);
  let analysing = false;

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

  async function analyse() {
    if (analysing) return;
    const button = $('[data-ai-analyze]');
    const symbol = $('#symbol')?.value;
    if (!symbol) { show('Select a broker instrument before running AI analysis.'); return; }
    analysing = true;
    if (button) { button.disabled = true; button.textContent = 'Analysing…'; }
    show('Running AI inference from the latest persisted broker market feed…');
    try {
      const data = await api('/api/ai/predict/', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({symbol, timeframe: 'M1'})
      }, 30000);
      render(data);
      window.dispatchEvent(new CustomEvent('algobot:ai-analysis-updated', {detail: data}));
    } catch (error) {
      text('[data-ai-prediction]', 'Unavailable');
      text('[data-ai-recommendation]', 'Unavailable');
      text('[data-ai-confidence-card]', 'Unavailable');
      text('[data-ai-confidence]', 'Unavailable');
      text('[data-ai-regime]', 'Unavailable');
      window.__algobotAiOrderContext = null;
      const code = String(error?.code || '').toUpperCase();
      const message = String(error?.message || 'AI analysis is temporarily unavailable.');
      if (code === 'REQUEST_ABORTED' || code === 'API_TIMEOUT') {
        show('AI analysis timed out while waiting for broker data. No trade action was taken.');
      } else if (code === 'EDGE_CHALLENGE' || message.includes('<html') || message.includes('Just a moment')) {
        show('AI analysis is temporarily unavailable at the production edge. No trade action was taken.');
      } else {
        show(message);
      }
      window.dispatchEvent(new CustomEvent('algobot:ai-gate-updated', {detail:{actionable:false, error:true, code:error?.code || null}}));
    } finally {
      analysing = false;
      if (button) { button.disabled = false; button.textContent = 'Analyse market'; }
    }
  }

  function resetForSymbol() {
    text('[data-ai-prediction]', 'Not analysed');
    text('[data-ai-recommendation]', 'Not analysed');
    text('[data-ai-confidence-card]', 'Not analysed');
    text('[data-ai-confidence]', 'Not analysed');
    text('[data-ai-regime]', 'Not analysed');
    show('Choose Analyse market when you want a fresh AI decision. AI analysis never places an order.');
    window.__algobotAiOrderContext = null;
    window.dispatchEvent(new CustomEvent('algobot:ai-gate-updated', {detail:{actionable:false, reset:true}}));
  }

  function boot() {
    if (!$('.terminal-page')) return;
    $('[data-ai-analyze]')?.addEventListener('click', () => analyse());
    window.addEventListener('algobot:market-symbol-changed', resetForSymbol);
    window.addEventListener('algobot:broker-contract-selected', () => {
      if (!analysing) show('Broker contract ready. Run Analyse market when needed.');
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once: true});
  else boot();
})();