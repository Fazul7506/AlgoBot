(() => {
  'use strict';
  if (window.__algoBotBacktestSubmitRecovery) return;
  window.__algoBotBacktestSubmitRecovery = true;
  const form = document.querySelector('[data-backtest-form]');
  if (!form) return;
  const apiBase = (document.querySelector('meta[name="algobot-api-base"]')?.content || ((location.hostname === 'algobot.dpdns.org' || location.hostname === 'www.algobot.dpdns.org') ? 'https://api.algobot.dpdns.org' : location.origin)).replace(/\/+$/, '');
  const csrf = () => { const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/); return m ? decodeURIComponent(m[1]) : (document.querySelector('meta[name="csrf-token"]')?.content || ''); };
  const message = (text, kind = 'info') => { let el = form.querySelector('[data-backtest-submit-status]'); if (!el) { el = document.createElement('div'); el.dataset.backtestSubmitStatus = '1'; el.setAttribute('role', 'status'); el.style.cssText = 'grid-column:1/-1;padding:12px 14px;border-radius:10px;background:rgba(127,127,127,.10);'; form.appendChild(el); } el.dataset.state = kind; el.textContent = text; };
  const parse = async response => { const text = await response.text(); let payload = {}; try { payload = text ? JSON.parse(text) : {}; } catch (_) { payload = {detail: text}; } if (!response.ok) { const values = []; Object.entries(payload || {}).forEach(([k,v]) => { if (v == null || v === '') return; if (Array.isArray(v)) values.push(`${k}: ${v.join(', ')}`); else if (typeof v === 'object') values.push(`${k}: ${JSON.stringify(v)}`); else values.push(k === 'detail' ? String(v) : `${k}: ${v}`); }); const error = new Error(values.join(' | ') || `HTTP ${response.status}`); error.status = response.status; error.payload = payload; throw error; } return payload; };
  async function post(payload) { const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), 12000); try { const response = await fetch(`${apiBase}/api/backtests/`, {method:'POST',credentials:'include',headers:{Accept:'application/json','Content-Type':'application/json','X-CSRFToken':csrf(),'X-Requested-With':'XMLHttpRequest'},body:JSON.stringify(payload),signal:controller.signal}); return await parse(response); } catch (error) { if (controller.signal.aborted) throw new Error('Backtest submission timed out while contacting the API.'); throw error; } finally { clearTimeout(timer); } }
  form.addEventListener('submit', async event => {
    event.preventDefault();
    event.stopImmediatePropagation();
    const fd = new FormData(form), data = Object.fromEntries(fd.entries()), strategy = form.elements.strategy_id?.selectedOptions?.[0];
    const start = new Date(data.start_date), end = new Date(data.end_date);
    if (!data.strategy_id || !data.symbol || !data.timeframe || !data.start_date || !data.end_date) return message('Select a strategy, broker instrument, timeframe, start and end before running the backtest.', 'error');
    if (!Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime()) || end <= start) return message('End date/time must be later than start date/time.', 'error');
    if (end > new Date()) return message('Backtests are historical only. End date/time cannot be in the future.', 'error');
    const payload = {strategy_id:Number(data.strategy_id),strategy:strategy?.dataset?.name || strategy?.textContent?.replace(/\s+v\S+$/,'').trim() || '',symbol:String(data.symbol).trim().toUpperCase(),timeframe:String(data.timeframe).trim().toLowerCase(),start_date:data.start_date,end_date:data.end_date,mode:data.mode || 'candle_close'};
    const button = form.querySelector('button[type="submit"]');
    if (button) { button.disabled = true; button.setAttribute('aria-busy','true'); button.textContent = 'Submitting…'; }
    message('Submitting backtest to the research queue…');
    try { const result = await post(payload); if (!result?.id) throw new Error('The API accepted the request but did not return a backtest job id.'); message(`Backtest #${result.id} submitted successfully. Status: ${String(result.status || 'pending')}. Results will appear in Backtest history.`, 'success'); window.dispatchEvent(new CustomEvent('algobot:backtest-submitted',{detail:result})); document.querySelector('[data-backtest-refresh]')?.click(); }
    catch (error) { message(`Backtest was not submitted${error.status ? ` (HTTP ${error.status})` : ''}: ${error.message || 'Unknown API error'}`, 'error'); console.error('[AlgoBot] backtest submission failed', error); }
    finally { if (button) { button.disabled = false; button.removeAttribute('aria-busy'); button.textContent = 'Run backtest'; } }
  }, true);
})();
