(() => {
  'use strict';
  if (window.__algoBotSignalsRebuild) return;
  window.__algoBotSignalsRebuild = true;
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '—').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const state = {category:'all', market:'', asset:'', search:'', page:1, pageSize:10, loading:false, lastData:null};
  const fmt = (v, digits=5) => v == null || v === '' || !Number.isFinite(Number(v)) ? '—' : Number(v).toLocaleString(undefined,{maximumFractionDigits:digits});
  const pct = v => v == null || !Number.isFinite(Number(v)) ? 'Unavailable' : Number(v).toFixed(1)+'%';
  const title = v => String(v || 'unknown').replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase());
  const icon = row => { const verified=window.AlgoBotMarketAssets?.renderIcon?.(row); if(verified) return verified; return '<span class="asset-neutral-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"/><path d="M4 12h16M12 4a12 12 0 0 1 0 16M12 4a12 12 0 0 0 0 16"/></svg></span>'; };
  const time = value => { if(!value) return ['—','']; const d=new Date(value); if(Number.isNaN(d.getTime())) return ['—','']; return [d.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}),d.toLocaleDateString([], {month:'short',day:'numeric',year:'numeric'})]; };
  const relative = value => {const d=new Date(value);if(Number.isNaN(d.getTime()))return 'time unavailable';const seconds=Math.max(0,Math.floor((Date.now()-d.getTime())/1000));if(seconds<60)return 'just now';if(seconds<3600)return Math.floor(seconds/60)+'m ago';if(seconds<86400)return Math.floor(seconds/3600)+'h ago';return Math.floor(seconds/86400)+'d ago';};
  async function load() {
    if(state.loading) return;
    state.loading=true; $('signals-refresh').disabled=true; $('signals-loading').hidden=false; $('signals-error').hidden=true;
    $('signals-live-label').textContent='Loading signals'; $('signals-live-dot').className='signals-live-dot';
    const query=new URLSearchParams({category:state.category,page:String(state.page),page_size:String(state.pageSize)});
    if(state.market)query.set('market',state.market);if(state.asset)query.set('asset',state.asset);if(state.search)query.set('q',state.search);
    try {
      const response=await fetch('/api/signals/workspace/?'+query.toString(),{credentials:'same-origin',headers:{Accept:'application/json'}});
      const data=await response.json();
      if(!response.ok)throw new Error(data.message||data.detail||'Signals could not be loaded ('+response.status+').');
      state.lastData=data; render(data);
      const generated=data.metrics?.last_updated?new Date(data.metrics.last_updated):null;
      const signalAge=generated&&!Number.isNaN(generated.getTime())?Date.now()-generated.getTime():null;
      const stale=signalAge==null||signalAge>15*60*1000;
      $('signals-live-label').textContent=data.metrics?.service_state==='empty'?'No signal records':data.metrics?.service_state==='available'?(stale?'Latest signal is stale':'Recent signal data available'):'Signal service status unknown';
      $('signals-live-dot').className='signals-live-dot'+(data.metrics?.service_state==='available'&&!stale?' is-live':' is-stale');
      $('signals-updated').textContent=generated&&!Number.isNaN(generated.getTime())?'Latest signal '+generated.toLocaleString([], {dateStyle:'short',timeStyle:'short'})+(stale?' · stale':''):'No signal timestamp available';
      $('signals-error').hidden=true;
    } catch(error) {
      $('signals-error').textContent=error.message||'Signal service unavailable. Retry to load current data.'; $('signals-error').hidden=false;
      $('signals-live-label').textContent='Signals unavailable';$('signals-live-dot').className='signals-live-dot is-stale';$('signals-updated').textContent='Last successful update is not confirmed';
      if(!state.lastData){$('signals-rows').innerHTML='';$('signals-empty').hidden=true;$('signals-recent').innerHTML='<p class="panel-note">Recent signals unavailable.</p>';}
    } finally {state.loading=false;$('signals-loading').hidden=true;$('signals-refresh').disabled=false;}
  }
  function render(data) {
    const metrics=data.metrics||{}, performance=data.performance||{};
    $('metric-total').textContent=fmt(metrics.total_signals,0);
    $('metric-total-change').textContent=metrics.total_signals_change==null?'Comparison unavailable':(metrics.total_signals_change>0?'+':'')+fmt(metrics.total_signals_change,0)+' vs previous 7 days';
    $('metric-winrate').textContent=pct(metrics.win_rate);
    $('metric-winrate-change').textContent=metrics.win_rate_change==null?'Completed-outcome comparison unavailable':(metrics.win_rate_change>0?'+':'')+Number(metrics.win_rate_change).toFixed(1)+' pp vs previous 7 days';
    $('metric-active').textContent=fmt(metrics.active_signals,0);
    $('metric-active-change').textContent=metrics.active_signals_change==null?'Comparison unavailable':(metrics.active_signals_change>0?'+':'')+fmt(metrics.active_signals_change,0)+' vs previous 7 days';
    $('metric-profitfactor').textContent=metrics.profit_factor==null?'Unavailable':fmt(metrics.profit_factor,2);
    $('metric-profitfactor-change').textContent=metrics.profit_factor_change==null?'Realized-loss comparison unavailable':(metrics.profit_factor_change>0?'+':'')+Number(metrics.profit_factor_change).toFixed(2)+' vs previous 7 days';
    const trendSeries={total:metrics.trend?.daily_counts,active:metrics.trend?.daily_active_counts,winrate:metrics.trend?.daily_win_rates,profitfactor:metrics.trend?.daily_profit_factors};
    ['total','active','winrate','profitfactor'].forEach(id=>{const el=$('trend-'+id);if(!el)return;const vals=(trendSeries[id]||[]).map(v=>v==null?NaN:Number(v)).filter(Number.isFinite);if(vals.length<2){el.innerHTML='';return;}const max=Math.max(...vals,1),min=Math.min(...vals,0),range=max-min||1;const points=vals.map((v,i)=>(i/(vals.length-1)*96+2)+','+(24-(v-min)/range*19)).join(' ');el.innerHTML='<polyline points="'+points+'"/>';});
    Object.entries(data.category_counts||{}).forEach(([key,value])=>{const el=$('count-'+key);if(el)el.textContent=fmt(value,0);});
    const ring=$('performance-ring'), winRate=performance.win_rate;
    ring.style.setProperty('--win-angle',winRate==null?'0deg':(Math.max(0,Math.min(100,Number(winRate)))*3.6)+'deg');
    ring.setAttribute('aria-label',winRate==null?'Win rate unavailable':('Win rate '+pct(winRate)));
    $('performance-winrate').textContent=winRate==null?'—':pct(winRate);
    $('performance-wins').textContent=fmt(performance.wins,0);$('performance-losses').textContent=fmt(performance.losses,0);$('performance-flat').textContent=fmt(performance.breakeven,0);
    $('performance-pnl').textContent=performance.realized_pnl==null?'Unavailable':fmt(performance.realized_pnl,2)+(data.account?.currency?' '+esc(data.account.currency):'');
    $('performance-average-profit').textContent=performance.average_profit==null?'Unavailable':fmt(performance.average_profit,2);
    $('performance-average-loss').textContent=performance.average_loss==null?'Unavailable':fmt(performance.average_loss,2);
    $('performance-note').textContent=performance.performance_available?'Calculated from persisted outcome/P&L metadata; open signals are not included.':'No persisted completed outcomes or realized P&L are available for this account.';
    fillSelect($('signals-market'),data.markets||[],'All Markets',state.market);
    fillSelect($('signals-asset'),data.assets||[],'All Assets',state.asset);
    renderRows(data.signals||[]);
    $('signals-result-summary').textContent=data.count?('Showing '+data.start+'–'+data.end+' of '+data.count+' signals'):'Showing 0 signals';
    $('signals-prev').disabled=data.page<=1;$('signals-next').disabled=!data.pages||data.page>=data.pages;
    const nums=$('signals-page-numbers');nums.innerHTML='';
    const pages=Number(data.pages)||0;const chosen=Number(data.page)||1;const values=new Set([1,pages,chosen-1,chosen,chosen+1].filter(n=>n>=1&&n<=pages));
    let prior=0;[...values].sort((a,b)=>a-b).forEach(n=>{if(prior&&n-prior>1){const ell=document.createElement('span');ell.className='signals-page-ellipsis';ell.textContent='…';nums.appendChild(ell);}const b=document.createElement('button');b.type='button';b.className='signals-page-number'+(n===chosen?' is-current':'');b.textContent=String(n);b.setAttribute('aria-label','Page '+n);if(n===chosen)b.setAttribute('aria-current','page');b.addEventListener('click',()=>{state.page=n;load();});nums.appendChild(b);prior=n;});
    $('signals-empty').hidden=Boolean((data.signals||[]).length);$('signals-empty').textContent=data.count?'No signals are on this page.':'No signals match these filters.';
    renderRecent(data.recent||[]);renderSentiment(data.sentiment||{status:'unavailable'});
  }
  function fillSelect(el,values,labelText,current){const prev=current;el.innerHTML='<option value="">'+labelText+'</option>'+[...new Set(values.filter(Boolean))].map(v=>'<option value="'+esc(v)+'">'+esc(v)+'</option>').join('');if([...el.options].some(o=>o.value===prev))el.value=prev;}
  function renderRows(rows) {
    $('signals-rows').innerHTML=rows.map(r=>{
      const [clock,date]=time(r.created_at);const entry=Number(r.entry_price),target=Number(r.take_profit),stop=Number(r.stop_loss);
      const targetPct=r.entry_price!=null&&r.take_profit!=null&&entry!==0?((String(r.direction).toUpperCase()==='SELL'?(entry-target):(target-entry))/Math.abs(entry))*100:null;
      const stopPct=r.entry_price!=null&&r.stop_loss!=null&&entry!==0?((String(r.direction).toUpperCase()==='SELL'?(entry-stop):(stop-entry))/Math.abs(entry))*100:null;
      const direction=String(r.direction||'').toUpperCase(),dirClass=direction==='BUY'?'buy':direction==='SELL'?'sell':'unknown';
      const conf=r.confidence==null?null:Math.max(0,Math.min(100,Number(r.confidence)));
      return '<tr data-signal-id="'+esc(r.id)+'"><td><span class="signal-time"><strong>'+esc(clock)+'</strong><small>'+esc(date)+'</small></span></td><td><span class="signal-asset">'+icon(r)+'<span><strong>'+esc(r.symbol)+'</strong><small>'+esc(r.market||'Unclassified')+'</small></span></span></td><td><span class="direction-badge '+dirClass+'">'+(direction==='BUY'?'↑ ':direction==='SELL'?'↓ ':'')+esc(direction||'Unavailable')+'</span></td><td><span class="signal-strategy"><strong>'+esc(r.strategy)+'</strong><small><span class="strategy-class">'+esc(title(r.strategy_category))+'</span></small></span></td><td>'+esc(fmt(r.entry_price))+'</td><td>'+esc(fmt(r.take_profit))+'<small class="sub-percentage">'+(targetPct==null?'':(targetPct>=0?'+':'')+targetPct.toFixed(2)+'%')+'</small></td><td>'+esc(fmt(r.stop_loss))+'<small class="sub-percentage">'+(stopPct==null?'':(stopPct>=0?'+':'')+stopPct.toFixed(2)+'%')+'</small></td><td class="confidence-cell"><strong>'+(conf==null?'—':conf.toFixed(1)+'%')+'</strong><div class="confidence-track" role="progressbar" aria-label="Confidence" aria-valuemin="0" aria-valuemax="100" aria-valuenow="'+(conf==null?'0':conf)+'"><span style="width:'+(conf==null?0:conf)+'%"></span></div></td><td><span class="status-badge '+esc(String(r.status||'').toLowerCase())+'">'+esc(title(r.status))+'</span></td><td><button class="signal-row-action" type="button" data-open-signal="'+esc(r.id)+'" aria-label="Open details for '+esc(r.symbol)+'" title="Open signal details">↗</button></td></tr>';
    }).join('');
  }
  function renderRecent(rows){$('signals-recent').innerHTML=rows.length?rows.map(r=>'<button type="button" class="recent-entry" data-open-signal="'+esc(r.id)+'">'+icon(r)+'<span class="recent-entry-copy"><span class="recent-entry-top"><strong>'+esc(r.symbol)+'</strong><span class="direction-badge '+(String(r.direction).toUpperCase()==='BUY'?'buy':'sell')+'">'+esc(r.direction||'Unavailable')+'</span></span><small>'+esc(r.strategy)+' · '+esc(title(r.strategy_category))+'</small></span><time datetime="'+esc(r.created_at)+'">'+esc(relative(r.created_at))+'</time></button>').join(''):'<p class="panel-note">No recent signals are available.</p>';}
  function renderSentiment(sentiment){$('signals-sentiment').innerHTML='<span class="sentiment-neutral-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M4 18V6m0 12h16M7 14l4-4 3 2 5-6"/></svg></span><div><strong>Sentiment unavailable</strong><p>'+esc(sentiment.reason||'No verified sentiment source is connected.')+'</p></div>';}
  document.querySelectorAll('[data-category]').forEach(button=>button.addEventListener('click',()=>{state.category=button.dataset.category;state.page=1;document.querySelectorAll('[data-category]').forEach(b=>{const active=b===button;b.classList.toggle('is-active',active);b.setAttribute('aria-selected',String(active));});load();}));
  $('signals-market').addEventListener('change',e=>{state.market=e.target.value;state.page=1;load();});
  $('signals-asset').addEventListener('change',e=>{state.asset=e.target.value;state.page=1;load();});
  let searchTimer=null; $('signals-search').addEventListener('input',e=>{state.search=e.target.value.trim();state.page=1;clearTimeout(searchTimer);searchTimer=setTimeout(load,250);});
  $('signals-prev').addEventListener('click',()=>{if(state.page>1){state.page--;load();}});
  $('signals-next').addEventListener('click',()=>{state.page++;load();});
  async function refreshNow(){
    if(state.loading)return;
    const button=$('signals-refresh');button.disabled=true;
    $('signals-live-label').textContent='Refreshing live market data';$('signals-live-dot').className='signals-live-dot is-stale';
    try{
      const response=await fetch('/api/strategy-signals/?limit=40&timeframe=M1',{credentials:'same-origin',headers:{Accept:'application/json'}});
      const live=await response.json();
      if(!response.ok||live.status!=='ok')throw new Error(live.message||'Live signal service did not confirm a successful refresh.');
      await load();
      const checkedAt=new Date();
      const hasLiveQuotes=Number(live.live_data_available_count||0)>0;
      $('signals-live-label').textContent=hasLiveQuotes?'Live market scan completed':'Scan completed; live quotes unavailable';
      $('signals-live-dot').className='signals-live-dot'+(hasLiveQuotes?' is-live':' is-stale');
      $('signals-updated').textContent='Live scan checked '+checkedAt.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'});
    }catch(error){
      await load();
      $('signals-live-label').textContent='Live refresh unavailable';$('signals-live-dot').className='signals-live-dot is-stale';
      $('signals-updated').textContent='Showing persisted records; live scan failed';
      $('signals-error').textContent=error.message||'Live market refresh failed.';$('signals-error').hidden=false;
    }finally{button.disabled=false;}
  }
  $('signals-refresh').addEventListener('click',refreshNow);
  async function openSignalDetail(id){const dialog=$('signal-detail-dialog');if(!dialog)return; $('signal-detail-title').textContent='Signal details';$('signal-detail-status').textContent='Loading authorized signal details…';$('signal-detail-fields').innerHTML='';if(!dialog.open)dialog.showModal();try{const response=await fetch('/api/signals/workspace/?detail_id='+encodeURIComponent(id),{credentials:'same-origin',headers:{Accept:'application/json'}});const data=await response.json();if(!response.ok)throw new Error(data.message||'Signal details unavailable.');const r=data.detail; $('signal-detail-title').textContent=(r.symbol||'Signal')+' · '+(r.direction||'Direction unavailable');$('signal-detail-status').textContent='Persisted signal facts · '+(r.created_at?new Date(r.created_at).toLocaleString():'timestamp unavailable');const fields=[['Market',r.market],['Strategy',r.strategy],['Classification',title(r.strategy_category)],['Entry price',r.entry_price],['Take profit',r.take_profit],['Stop loss',r.stop_loss],['Confidence',r.confidence==null?'Unavailable':r.confidence+'%'],['Lifecycle',title(r.status)],['Outcome',r.metadata_outcome||'Not recorded']];$('signal-detail-fields').innerHTML=fields.map(([label,value])=>'<div><dt>'+esc(label)+'</dt><dd>'+esc(value==null||value===''?'Unavailable':value)+'</dd></div>').join('');}catch(error){$('signal-detail-status').textContent=error.message||'Signal details unavailable.';}}
  document.addEventListener('click',event=>{const button=event.target.closest('[data-open-signal]');if(button)openSignalDetail(button.dataset.openSignal);});
  $('signal-detail-close')?.addEventListener('click',()=>$('signal-detail-dialog').close());
  $('signal-detail-dialog')?.addEventListener('click',event=>{if(event.target===$('signal-detail-dialog'))$('signal-detail-dialog').close();});
  const params=new URLSearchParams(location.search);if(params.get('signal'))openSignalDetail(params.get('signal'));
  load();
})();
