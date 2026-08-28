/* Trading-terminal AI decision bridge. */
(() => {
  'use strict';
  if (window.__algoBotTradingTerminalAI) return;
  window.__algoBotTradingTerminalAI = true;

  const $ = (s, r = document) => r.querySelector(s);
  const text = (s, value) => $(s)?.replaceChildren(document.createTextNode(String(value ?? '—')));
  const api = (url, options = {}, timeout = 15000) => window.AlgoBotFrontendData?.request(url, options, timeout);

  function show(message) { text('[data-ai-explanation]', message); }

  function render(data) {
    const prediction = data?.prediction || {};
    const recommendation = data?.recommendation || {};
    const regime = data?.regime || {};
    const confidenceRaw = prediction.confidence ?? recommendation.confidence;
    const confidence = confidenceRaw == null ? '—' : `${(Number(confidenceRaw) <= 1 ? Number(confidenceRaw) * 100 : Number(confidenceRaw)).toFixed(1)}%`;
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

    window.__algobotAiOrderContext = {
      ...(window.__algobotAiOrderContext || {}),
      ai_prediction: predictionLabel,
      ai_recommendation: recommendationLabel,
      ai_confidence: Number.isFinite(Number(confidenceRaw)) ? Number(confidenceRaw) : null,
      ai_regime: regimeLabel,
      ai_source: data?.market_context_source ? `decision_engine:${data.market_context_source}` : 'decision_engine',
    };
  }

  async function analyse() {
    const button = $('[data-ai-analyze]');
    const symbol = $('#symbol')?.value;
    if (!symbol) { show('Select a broker instrument before running AI analysis.'); return; }
    if (button) { button.disabled = true; button.textContent = 'Analysing…'; }
    show('Running AI inference from the latest persisted broker market feed…');
    try {
      const data = await api('/api/ai/predict/', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({symbol, timeframe: 'M1'})
      }, 15000);
      render(data);
      window.dispatchEvent(new CustomEvent('algobot:ai-analysis-updated', {detail: data}));
    } catch (error) {
      text('[data-ai-prediction]', 'Unavailable');
      text('[data-ai-recommendation]', 'Unavailable');
      text('[data-ai-confidence-card]', 'Unavailable');
      text('[data-ai-confidence]', 'Unavailable');
      text('[data-ai-regime]', 'Unavailable');
      const message = String(error?.message || 'AI analysis is temporarily unavailable.');
      show(message.includes('<html') || message.includes('Just a moment') ? 'Production edge security blocked the AI request. Market data remains broker-authoritative; no signal was fabricated.' : message);
    } finally {
      if (button) { button.disabled = false; button.textContent = 'Analyse market'; }
    }
  }

  function boot() {
    if (!$('.terminal-page')) return;
    $('[data-ai-analyze]')?.addEventListener('click', analyse);
    window.addEventListener('algobot:market-symbol-changed', () => {
      text('[data-ai-prediction]', 'No analysis');
      text('[data-ai-recommendation]', 'No analysis');
      text('[data-ai-confidence-card]', 'No analysis');
      text('[data-ai-confidence]', 'Not analysed');
      text('[data-ai-regime]', 'No analysis');
      show('Run market analysis to request an AI decision.');
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once: true});
  else boot();
})();
