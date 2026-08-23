(() => {
  if (window.__algoBotAIUI) return;
  window.__algoBotAIUI = true;
  const $ = (s, r = document) => r.querySelector(s);
  const list = v => Array.isArray(v) ? v : (Array.isArray(v?.results) ? v.results : []);
  const csrf = () => document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] || '';
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const request = async (url, options = {}, timeout = 10000) => {
    const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const headers = { Accept: 'application/json', ...(options.headers || {}) };
      if (options.method && options.method !== 'GET') headers['X-CSRFToken'] = csrf();
      const r = await fetch(url, { credentials: 'same-origin', ...options, headers, signal: controller.signal });
      const text = await r.text(); let data = {}; try { data = text ? JSON.parse(text) : {}; } catch (_) { data = { detail: text }; }
      if (!r.ok) throw new Error(data.detail || data.message || `Request failed (${r.status})`);
      return data;
    } catch (e) { if (e.name === 'AbortError') throw new Error('AI analysis timed out'); throw e; } finally { clearTimeout(timer); }
  };
  const render = result => {
    const prediction = result.prediction || {}, recommendation = result.recommendation || {}, regime = result.regime || {}, explanation = result.explainability || {};
    $('[data-ai-prediction]')?.replaceChildren(document.createTextNode(prediction.prediction || '—'));
    $('[data-ai-recommendation]')?.replaceChildren(document.createTextNode(recommendation.recommendation || '—'));
    $('[data-ai-confidence-card]')?.replaceChildren(document.createTextNode(prediction.confidence != null ? `${Number(prediction.confidence).toFixed(1)}%` : '—'));
    $('[data-ai-confidence]')?.replaceChildren(document.createTextNode(prediction.confidence != null ? `${Number(prediction.confidence).toFixed(1)}%` : '—'));
    $('[data-ai-regime]')?.replaceChildren(document.createTextNode(regime.regime || '—'));
    $('[data-recommended]')?.replaceChildren(document.createTextNode(recommendation.recommendation || '—'));
    const factors = Array.isArray(explanation.decision_factors) ? explanation.decision_factors.join(', ') : '';
    const source = prediction.payload?.source || (prediction.payload?.models_used ? `${prediction.payload.models_used} trained models` : 'no trained model');
    const box = $('[data-ai-explanation]');
    if (box) box.innerHTML = `<strong>AI status:</strong> ${esc(source)}. ${esc(explanation.explanation || '')}${factors ? `<br><small>Key factors: ${esc(factors)}</small>` : ''}`;
  };
  async function analyze() {
    const symbol = $('#symbol')?.value || $('[data-symbol]')?.value;
    const timeframe = $('#timeframe')?.value || $('[data-timeframe]')?.value || 'M1';
    const button = $('[data-ai-analyze]'); if (!symbol) { $('[data-ai-explanation]')?.replaceChildren(document.createTextNode('Connect and synchronize a broker market before requesting AI analysis.')); return; }
    if (button) { button.disabled = true; button.textContent = 'Analysing…'; }
    try { render(await request('/api/ai/predict/', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ symbol, timeframe }) })); }
    catch (e) { $('[data-ai-explanation]')?.replaceChildren(document.createTextNode(`AI unavailable: ${e.message}`)); }
    finally { if (button) { button.disabled = false; button.textContent = 'Analyse market'; } }
  }
  window.addEventListener('DOMContentLoaded', () => {
    if (!$('[data-ai-panel]')) return;
    $('[data-ai-analyze]')?.addEventListener('click', analyze);
    $('#symbol')?.addEventListener('change', () => { $('[data-ai-explanation]')?.replaceChildren(document.createTextNode('Market changed. Run AI analysis for the selected broker instrument.')); });
  }, { once: true });
})();
