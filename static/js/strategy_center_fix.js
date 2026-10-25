(() => {
  'use strict';
  if (window.__algoBotStrategyCenterFix) return;
  window.__algoBotStrategyCenterFix = true;

  const $ = s => document.querySelector(s);
  const list = v => Array.isArray(v) ? v : (v?.results || v?.data || v?.items || []);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const activeState = s => s.active_configuration || (Array.isArray(s.configurations) ? s.configurations.find(c => c.is_active) : null);
  const tradeUrl = s => `/trading/?strategy=${encodeURIComponent(s.slug || s.name || '')}${activeState(s)?.symbol ? `&symbol=${encodeURIComponent(activeState(s).symbol)}` : ''}`;
  const backtestUrl = s => { const c = activeState(s); const q = new URLSearchParams({strategy_id:String(s.id || ''),strategy:String(s.slug || s.name || '')}); if(c?.symbol) q.set('symbol', c.symbol); if(c?.timeframe) q.set('timeframe', c.timeframe); return `/backtesting/?${q.toString()}`; };
  const builderUrl = s => `/strategies/builder/?strategy=${encodeURIComponent(s.slug || '')}`;
  let strategies = [];
  let performanceRows = [];
  let selectedStrategyId = null;
  let activeFilter = 'all';
  let selectedRange = '30d';
  const strategyMetrics = s => s?.metrics || s?.statistics || s?.performance || {};
  const metric = (s, ...keys) => { const sources=[s,strategyMetrics(s),activeState(s),activeState(s)?.metrics||{}]; for(const key of keys) for(const source of sources){const v=source?.[key];if(v!==null&&v!==undefined&&v!=='')return v;} return null; };
  const displayMetric = (v,suffix='') => v===null||v===undefined||v===''?'—':`${Number.isFinite(Number(v))?Number(v).toLocaleString(undefined,{maximumFractionDigits:2}):esc(v)}${suffix}`;
  const percentMetric = v => {if(v===null||v===undefined||v==='')return '—';const n=Number(v);return Number.isFinite(n)?`${(Math.abs(n)<=1?n*100:n).toFixed(1)}%`:esc(v);};
  const strategyIcon = s => { const cat=strategyCategory(s); const paths={ai:'<path d="M12 3a3 3 0 0 0-3 3v.5a4 4 0 0 0-3 3.8A3.5 3.5 0 0 0 5.5 17H6a3 3 0 0 0 3 3h6a3 3 0 0 0 3-3h.5a3.5 3.5 0 0 0-.5-6.7 4 4 0 0 0-3-3.8V6a3 3 0 0 0-3-3Z"/><path d="M9 10h.01M15 10h.01M9 15c1.8 1.4 4.2 1.4 6 0M12 7v10"/>',trend:'<path d="M3 17 9 11l4 3 8-9"/><path d="M15 5h6v6"/>',mean:'<path d="M4 7h16M4 17h16"/><path d="m8 4-4 3 4 3m8 4 4 3-4 3"/>',scalping:'<circle cx="12" cy="12" r="8"/><path d="m12 7 2.5 5-2.5 5-2.5-5 2.5-5Z"/>',other:'<path d="M4 18V6m0 12h16"/><path d="m7 14 4-4 3 2 5-6"/>'}; return '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">'+(paths[cat]||paths.other)+'</svg>'; };
  const strategyCategory = s => {const t=String(s.category||s.strategy_type||s.type||'').toLowerCase(),name=String(s.name||s.slug||'').toLowerCase(),tags=Array.isArray(s.tags)?s.tags.join(' ').toLowerCase():'';if(s.ai_powered||/ai|momentum|sentiment|machine/.test(`${t} ${name} ${tags}`))return 'ai';if(/mean|reversion|rsi/.test(`${t} ${name} ${tags}`))return 'mean';if(/scalp/.test(`${t} ${name} ${tags}`))return 'scalping';if(/trend|breakout/.test(`${t} ${name} ${tags}`))return 'trend';return 'other';};

  function counts(data, signals) {
    const total=$('[data-s-total]'),enabled=$('[data-s-enabled]'),running=$('[data-s-running]'),signalCount=$('[data-s-signals]');
    if(total)total.textContent = strategies.length;
    if(enabled)enabled.textContent = Number.isFinite(Number(data?.configured_count)) ? Number(data.configured_count) : strategies.filter(s => s.configured).length;
    if(running)running.textContent = Number.isFinite(Number(data?.running_count)) ? Number(data.running_count) : strategies.filter(s => s.running).length;
    if(signalCount)signalCount.textContent = signals.length;
  }

  function renderList() {
    const q = String($('[data-s-search]')?.value || '').trim().toLowerCase();
    const visible = strategies.filter(s => {
      const text = `${s.name||s.slug||''} ${s.description||''} ${s.category||''} ${(s.tags||[]).join?.(' ')||''}`.toLowerCase();
      return text.includes(q) && (activeFilter==='all'||strategyCategory(s)===activeFilter);
    });
    const categoryCounts={all:strategies.length,ai:0,trend:0,mean:0,scalping:0};
    strategies.forEach(s=>{const cat=strategyCategory(s);if(Object.prototype.hasOwnProperty.call(categoryCounts,cat))categoryCounts[cat]++;});
    Object.entries(categoryCounts).forEach(([k,v])=>{const n=$(`[data-filter-count="${k}"]`);if(n)n.textContent=v;});
    $('[data-s-list]').innerHTML = visible.length ? visible.map(s => {
      const configs=Array.isArray(s.configurations)?s.configurations:[],active=activeState(s);
      const connected=Boolean(s.connected||active),running=Boolean(s.running||(active&&active.enabled)),paused=Boolean(s.paused||(connected&&!running)),configured=Boolean(s.configured||configs.length);
      const state=running?'RUNNING':paused?'PAUSED':configured?'CONFIGURED':'AVAILABLE';
      const stateClass=running?'active':paused?'paused':configured?'configured':'available';
      const category=esc(s.category||s.strategy_type||'Strategy');
      const icon=strategyIcon(s);
      const description=esc(s.description||s.summary||'Configure this strategy to inspect supported markets, execution settings and available metrics.');
      const detail=active?`${esc(window.AlgoBotMarketPicker?.marketName({value:active.symbol||'',textContent:active.display_name||active.symbol||''})||active.display_name||active.symbol||'Market instrument')} · ${esc(active.timeframe||'Timeframe not set')}`:configured?`${configs.length} saved configuration${configs.length===1?'':'s'}`:'Not configured';
      const win=percentMetric(metric(s,'win_rate','winRate')),trades=displayMetric(metric(s,'total_trades','trade_count','trades_count')),pf=displayMetric(metric(s,'profit_factor','profitFactor'));
      const selected=String(s.id)===String(selectedStrategyId);
      const action=connected?`<button class="btn small ghost" type="button" data-strategy-disconnect data-strategy-id="${esc(s.id)}" data-config-id="${esc(active?.id||'')}">Disconnect</button>`:configured?`<button class="btn small primary" type="button" data-strategy-switch data-strategy-id="${esc(s.id)}" data-config-id="${esc((configs.find(c=>c.enabled)||configs[0])?.id||'')}">Use strategy</button>`:`<a class="btn small ghost" href="${builderUrl(s)}">Configure</a>`;
      const research=configured?`<a class="btn small ghost" href="${backtestUrl(s)}">Backtest</a>`:'';
      return `<article class="strategy-control-row ${selected?'is-selected':''}" data-strategy-card data-strategy-id="${esc(s.id)}">
        <div class="strategy-row-main"><strong>${esc(s.name||s.slug||'Strategy')}</strong><small>${category}${s.version?' · v'+esc(s.version):''}</small><small class="strategy-config-detail">${detail}</small></div>
        <span class="state-badge ${stateClass}">${state}</span><p class="strategy-card-description">${description}</p>
        <div class="strategy-tags">${(Array.isArray(s.tags)?s.tags:[]).slice(0,3).map(t=>'<span>'+esc(t)+'</span>').join('')||'<span>'+category+'</span>'}</div>
        <div class="strategy-card-metrics"><div><span>Win Rate</span><strong>${win}</strong><small>Saved metric</small></div><div><span>Total Trades</span><strong>${trades}</strong><small>Available records</small></div><div><span>Profit Factor</span><strong>${pf}</strong><small>Saved metric</small></div></div>
        <div class="strategy-actions-inline"><span class="strategy-active-indicator">${running?'● Running':paused?'● Paused':configured?'● Configured':'● Available'}</span><button class="btn small ghost" type="button" data-strategy-select="${esc(s.id)}">View Details</button>${action}${research}<a class="btn small ghost" href="${tradeUrl(s)}">Trade</a></div>
      </article>`;
    }).join('') : '<div class="empty-state">No strategies match this category or search.</div>';
    renderComparison();
    const selected=strategies.find(s=>String(s.id)===String(selectedStrategyId))||visible[0]||strategies[0]||null;
    if(selected && String(selected.id)!==String(selectedStrategyId)) selectedStrategyId=selected.id;
    renderSelected(selected);
  }

  function renderComparison(){
    const body=$('[data-s-comparison]');if(!body)return;
    body.innerHTML=strategies.slice(0,12).map(s=>{
      const running=Boolean(s.running||(activeState(s)&&activeState(s).enabled)),configured=Boolean(s.configured||(s.configurations||[]).length);
      return `<tr><td>${esc(s.name||s.slug||'Strategy')}</td><td>${percentMetric(metric(s,'win_rate','winRate'))}</td><td>${displayMetric(metric(s,'profit_factor','profitFactor'))}</td><td>${displayMetric(metric(s,'total_trades','trade_count','trades_count'))}</td><td>${percentMetric(metric(s,'total_return_pct','total_return','return_pct'))}</td><td><span class="comparison-status">${running?'Running':configured?'Configured':'Available'}</span></td><td><button class="btn small ghost" type="button" data-strategy-select="${esc(s.id)}">Details</button></td></tr>`;
    }).join('')||'<tr><td class="empty-cell" colspan="7">No strategy records are available.</td></tr>';
  }

  function renderSelected(s){
    const panel=$('[data-s-selected-panel]');if(!panel)return;
    const set=(selector,value)=>{const n=$(selector);if(n)n.textContent=value;};
    if(!s){set('[data-s-selected-name]','No strategy selected');set('[data-s-selected-description]','Strategy information will appear when the registry is available.');return;}
    const active=activeState(s),configs=Array.isArray(s.configurations)?s.configurations:[],connected=Boolean(s.connected||active),configured=Boolean(s.configured||configs.length);
    set('[data-s-selected-name]',s.name||s.slug||'Strategy');set('[data-s-selected-description]',s.description||s.summary||'No strategy description is available.');
    set('[data-s-selected-win]',percentMetric(metric(s,'win_rate','winRate')));set('[data-s-selected-pf]',displayMetric(metric(s,'profit_factor','profitFactor')));set('[data-s-selected-trades]',displayMetric(metric(s,'total_trades','trade_count','trades_count')));set('[data-s-selected-win-change]','Saved strategy metric');
    const deploy=$('[data-s-selected-deploy]');if(deploy){deploy.disabled=!configured;deploy.dataset.strategyId=s.id;deploy.dataset.configId=(configs.find(c=>c.enabled)||configs[0])?.id||'';deploy.textContent=connected?'Strategy Connected':'Use Strategy';}
    const edit=$('[data-s-selected-edit]');if(edit)edit.href=builderUrl(s);
    set('[data-s-setting-timeframe]',active?.timeframe||'Not configured');set('[data-s-setting-markets]',active?.display_name||active?.symbol||'All supported');set('[data-s-setting-risk]',active?.risk_per_trade!=null?displayMetric(active.risk_per_trade,'%'):'Not configured');set('[data-s-setting-stop]',active?.stop_loss!=null?displayMetric(active.stop_loss,'%'):'Not configured');set('[data-s-setting-take]',active?.take_profit!=null?displayMetric(active.take_profit,'%'):'Not configured');
    const p=performanceRows.find(x=>String(x.strategy_id??x.strategyId??x.id??'')===String(s.id))||performanceRows.find(x=>String(x.strategy_name||x.strategy||'').toLowerCase()===String(s.name||s.slug||'').toLowerCase())||{};
    set('[data-s-period-7]',percentMetric(p.last_7_days_return??p.return_7d??p.period_7d));set('[data-s-period-30]',percentMetric(p.last_30_days_return??p.return_30d??p.period_30d));set('[data-s-period-90]',percentMetric(p.last_90_days_return??p.return_90d??p.period_90d));set('[data-s-max-drawdown]',percentMetric(p.max_drawdown_pct??p.max_drawdown));renderPerformanceChart(p);
  }

  function renderPerformanceChart(p){
    const svg=$('[data-s-performance-chart]'),empty=$('[data-s-chart-empty]');if(!svg||!empty)return;
    const keys=selectedRange==='90d'?['equity_90d','series_90d']:selectedRange==='1y'?['equity_1y','series_1y']:selectedRange==='all'?['equity_curve','equity_series','history']:['equity_30d','series_30d','equity_curve','equity_series'];
    let series=null;for(const key of keys){if(Array.isArray(p?.[key])&&p[key].length>1){series=p[key];break;}}
    if(!series){svg.hidden=true;empty.hidden=false;return;}
    const values=series.map(x=>Number(typeof x==='object'?(x.value??x.equity??x.balance??x.return_pct??x.y):x)).filter(Number.isFinite);
    if(values.length<2){svg.hidden=true;empty.hidden=false;return;}
    const min=Math.min(...values,0),max=Math.max(...values,0),span=max-min||1,w=480,h=170,pad=28,pw=w-pad-8,ph=h-26;let out='';
    for(let i=0;i<=4;i++){const y=8+i*ph/4;out+=`<path d="M${pad} ${y}H${w-8}" stroke="#15385b" stroke-width="1"/><text x="${pad-6}" y="${y+3}" text-anchor="end" fill="#9db6d6" font-size="9">${(max-i*span/4).toFixed(0)}%</text>`;}
    const points=values.map((v,i)=>[pad+i*pw/(values.length-1),8+(max-v)*ph/span]);const path=points.map((v,i)=>(i?'L':'M')+v[0].toFixed(1)+' '+v[1].toFixed(1)).join(' ');
    out+=`<path d="${path}" fill="none" stroke="#08d4a4" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>`;svg.innerHTML=out;svg.hidden=false;empty.hidden=true;
  }

  async function load() {
    const data = window.AlgoBotFrontendData;
    if (!data?.request) return;
    $('[data-s-list]').innerHTML = '<div class="empty-state">Loading strategy control plane…</div>';
    try {
      const [sr, sig, perf] = await Promise.allSettled([
        data.request('/api/strategies/available/'),
        data.request('/api/strategies/signals/'),
        data.request('/api/strategies/performance/')
      ]);
      if (sr.status === 'rejected') throw sr.reason;
      const payload = sr.value || {};
      strategies = list(payload.strategies || payload);
      const signals = sig.status === 'fulfilled' ? list(sig.value) : [];
      const performance = perf.status === 'fulfilled' ? list(perf.value) : null;
      performanceRows = Array.isArray(performance) ? performance : [];
      counts(payload, signals);
      selectedStrategyId = selectedStrategyId ?? strategies[0]?.id ?? null;
      renderList();
      $('[data-s-strategy-signals]').innerHTML = signals.length ? signals.slice(0,8).map(s => `<div class="signal-row"><span class="market-inline-label">${window.AlgoBotMarketPicker?.marketIcon(s)||''}<strong>${esc(window.AlgoBotMarketPicker?.marketName({value:s.symbol||'',textContent:s.display_name||s.symbol||''})||s.display_name||'Market instrument')}</strong></span><span>${esc(s.signal || 'HOLD')}</span><b>${s.confidence != null ? Number(s.confidence).toFixed(0) + '%' : '—'}</b></div>`).join('') : '<div class="empty-state">No strategy signals have been generated yet.</div>';
      $('[data-s-performance]').innerHTML = performance === null
        ? '<div class="empty-state">Account-level performance is unavailable until strategy executions are reconciled with settled broker trades. No personal P&amp;L is inferred from global strategy totals.</div>'
        : (performance.length ? performance.slice(0,8).map(p => `<div class="mini-row"><strong>${esc(p.strategy_name || p.strategy || 'Strategy')}</strong><span>${p.win_rate != null ? Number(p.win_rate).toFixed(1) + '%' : '—'}</span><b>${esc(p.net_profit ?? 'Unavailable')}</b></div>`).join('') : '<div class="empty-state">No settled account-level strategy performance records yet.</div>');
    } catch (e) {
      const msg = esc(e?.message || 'Unable to load strategy data.');
      $('[data-s-list]').innerHTML = `<div class="empty-state">Strategy control plane unavailable: ${msg} <button class="btn small ghost" type="button" data-s-retry>Retry</button></div>`;
      $('[data-s-strategy-signals]').innerHTML = '<div class="empty-state">Strategy signals unavailable.</div>';
      $('[data-s-performance]').innerHTML = '<div class="empty-state">Strategy performance unavailable.</div>';
      ['[data-s-total]','[data-s-enabled]','[data-s-running]','[data-s-signals]'].forEach(s => { const n=$(s); if(n) n.textContent='—'; });
      $('[data-s-retry]')?.addEventListener('click', load, {once:true});
    }
  }

  async function post(path, body, successMessage) {
    const data = window.AlgoBotFrontendData;
    if (!data?.request) throw new Error('Strategy service is not ready.');
    const result = await data.request(path, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body || {})});
    window.alert(result?.detail || result?.message || successMessage);
    await load();
    return result;
  }
  async function useStrategy(id, configId) { try { await post(`/api/strategies/${encodeURIComponent(id)}/switch/`, configId ? {configuration_id:Number(configId)} : {}, 'Strategy is now the active configured strategy.'); } catch(e) { window.alert(e?.message || 'Unable to switch strategy.'); } }
  async function disconnectStrategy(id, configId) { try { await post(`/api/strategies/${encodeURIComponent(id)}/disconnect/`, configId ? {configuration_id:Number(configId)} : {}, 'Strategy disconnected. Its configuration was preserved.'); } catch(e) { window.alert(e?.message || 'Unable to disconnect strategy.'); } }
  async function action(path, requireBroker=false) { try { if(requireBroker) window.AlgoBotFrontendData.requireConnected('run executable strategies'); await post(path, {}, 'Strategy action completed.'); } catch(e) { window.alert(e?.message || 'Strategy action failed.'); } }

  function boot() {
    document.querySelectorAll('[data-strategy-run]').forEach(b => b.addEventListener('click', () => action('/api/strategies/run/', true)));
    $('[data-strategy-pause]')?.addEventListener('click', () => action('/api/strategies/pause/'));
    $('[data-strategy-stop]')?.addEventListener('click', () => { if(confirm('Stop and disconnect the currently connected strategies? Saved configurations will remain available.')) action('/api/strategies/stop/'); });
    $('[data-s-search]')?.addEventListener('input', renderList);
    document.querySelectorAll('[data-strategy-filter]').forEach(b=>b.addEventListener('click',()=>{activeFilter=b.dataset.strategyFilter;document.querySelectorAll('[data-strategy-filter]').forEach(x=>x.classList.toggle('is-active',x===b));renderList();}));
    document.querySelectorAll('[data-s-range]').forEach(b=>b.addEventListener('click',()=>{selectedRange=b.dataset.sRange;document.querySelectorAll('[data-s-range]').forEach(x=>x.classList.toggle('is-active',x===b));const s=strategies.find(x=>String(x.id)===String(selectedStrategyId));const p=performanceRows.find(x=>String(x.strategy_id??x.strategyId??x.id??'')===String(s?.id))||{};renderPerformanceChart(p);}));
    $('[data-s-list]')?.addEventListener('click',e=>{const card=e.target.closest('[data-strategy-card]');if(!card||e.target.closest('button,a'))return;selectedStrategyId=card.dataset.strategyId;renderList();});
    document.addEventListener('click',e=>{const select=e.target.closest('[data-strategy-select]');if(select){selectedStrategyId=select.dataset.strategySelect;renderList();}const deploy=e.target.closest('[data-s-selected-deploy]');if(deploy&&!deploy.disabled)useStrategy(deploy.dataset.strategyId,deploy.dataset.configId);});
    $('[data-s-list]')?.addEventListener('click', e => { const sw=e.target.closest('[data-strategy-switch]'),dc=e.target.closest('[data-strategy-disconnect]'); if(sw)useStrategy(sw.dataset.strategyId,sw.dataset.configId); if(dc&&confirm('Disconnect this strategy? Its saved configuration will remain available for later use.'))disconnectStrategy(dc.dataset.strategyId,dc.dataset.configId); });
    load();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
