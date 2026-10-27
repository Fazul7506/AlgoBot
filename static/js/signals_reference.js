(() => {
  "use strict";
  if (window.__algoBotSignalsReference) return;
  window.__algoBotSignalsReference = true;
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? "—").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[c]));
  const state = {rows:[], page:1, size:10, category:"all", loading:false, total:0, pages:1, counts:{}};
  const query = () => {
    const p = new URLSearchParams({page:String(state.page),page_size:String(state.size),category:state.category});
    if ($("signalsMarketFilter").value) p.set("market",$("signalsMarketFilter").value);
    if ($("signalsAssetFilter").value) p.set("symbol",$("signalsAssetFilter").value);
    return p.toString();
  };
  const request = async () => {
    const response = await fetch("/api/market/signals/lifecycle/?"+query(), {credentials:"same-origin",headers:{Accept:"application/json"}});
    let payload = {};
    try { payload = await response.json(); } catch (_) {}
    if (!response.ok) throw new Error(payload.detail || payload.message || "Signal service request failed ("+response.status+").");
    if (!Array.isArray(payload.signals) || !Number.isFinite(Number(payload.total))) throw new Error("Signal service returned an unexpected response.");
    return payload;
  };
  const marketType = row => {
    const raw = String(row.market_type || "").toLowerCase();
    const symbol = String(row.symbol || "").toUpperCase();
    if (raw) {
      if (raw.includes("crypto")) return "Crypto";
      if (raw.includes("forex") || raw.includes("fx")) return "Forex";
      if (raw.includes("commod")) return "Commodity";
      if (raw.includes("index") || raw.includes("indices")) return "Index";
      if (raw.includes("stock") || raw.includes("equity")) return "Stock";
      return raw.charAt(0).toUpperCase()+raw.slice(1);
    }
    // Classification is a display fallback only; the server-side market filter uses the canonical registry.
    if (/^(BTC|ETH|LTC|XRP|BCH|ADA|DOGE|SOL|DOT|BNB|TRX|AVAX|LINK)/.test(symbol)) return "Crypto";
    if (/^(XAU|XAG|WTI|BRENT|UKOIL|USOIL|NGAS)/.test(symbol)) return "Commodity";
    if (/^(NAS|US30|US500|SPX|DJI|DAX|FTSE|R_)/.test(symbol)) return "Index";
    if (/^(FRX)?[A-Z]{6}$/.test(symbol.replace("/",""))) return "Forex";
    return "Market unavailable";
  };
  const dateParts = value => {
    if (!value) return {time:"—",date:"—"};
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return {time:"—",date:"—"};
    return {time:d.toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"}),date:d.toLocaleDateString([], {month:"short",day:"2-digit"})};
  };
  const relative = value => {
    const d = new Date(value), seconds = Math.floor((Date.now()-d.getTime())/1000);
    if (!Number.isFinite(seconds) || seconds < 0) return "Time unavailable";
    if (seconds < 60) return seconds+"s ago";
    if (seconds < 3600) return Math.floor(seconds/60)+"m ago";
    if (seconds < 86400) return Math.floor(seconds/3600)+"h ago";
    return Math.floor(seconds/86400)+"d ago";
  };
  const numeric = value => value == null || value === "" || !Number.isFinite(Number(value)) ? null : Number(value);
  const price = value => {
    const n=numeric(value);
    return n == null ? "—" : n.toLocaleString(undefined,{maximumFractionDigits:8});
  };
  const changePct = (row, value, target) => {
    const entry=numeric(row.entry_price), level=numeric(value);
    if(entry==null || level==null || entry===0) return "—";
    const buy=String(row.direction||"").toUpperCase()==="BUY";
    if(!buy && String(row.direction||"").toUpperCase()!=="SELL") return "—";
    const pct=target ? (buy ? (level-entry)/entry : (entry-level)/entry)*100 : (buy ? (level-entry)/entry : (entry-level)/entry)*100;
    return (pct>0?"+":"")+pct.toFixed(2)+"%";
  };
  const assetIcon = () => '<span class="signals-asset-icon" aria-hidden="true"><span class="material-symbols-rounded">show_chart</span></span>';
  const renderMetrics = payload => {
    $("metricTotal").textContent=String(payload.category_counts?.all ?? payload.total);
    $("metricActive").textContent=String(state.rows.filter(r=>r.lifecycle==="active").length);
    $("countAll").textContent=String(state.counts.all ?? "—");
    $("countHigh").textContent=String(state.counts.high ?? "—");
    $("countScalping").textContent=String(state.counts.scalping ?? "—");
    $("countIntraday").textContent=String(state.counts.intraday ?? "—");
    $("countSwing").textContent=String(state.counts.swing ?? "—");
    $("metricWinRate").textContent="Unavailable";
    $("metricProfitFactor").textContent="Unavailable";
  };
  const renderPagination = () => {
    const pages=Math.max(1,state.pages), page=state.page;
    $("signalsPrev").disabled=page<=1;
    $("signalsNext").disabled=page>=pages;
    const nums=[];
    for(let n=1;n<=pages;n++) if(pages<=5||n===1||n===pages||Math.abs(n-page)<=1) nums.push(n);
    let html="", previous=0;
    nums.forEach(n=>{if(previous&&n-previous>1)html+='<span aria-hidden="true">…</span>';html+='<button type="button" data-page="'+n+'" '+(n===page?'aria-current="page" aria-label="Page '+n+'"':'aria-label="Page '+n+'"')+'>'+n+'</button>';previous=n;});
    $("signalsPageNumbers").innerHTML=html;
    const first=state.total ? (page-1)*state.size+1 : 0, last=Math.min(page*state.size,state.total);
    $("signalsResultSummary").textContent="Showing "+first+"–"+last+" of "+state.total+" signals";
  };
  const showDetails = row => {
    const fields=[["Signal ID",row.id],["Asset",row.symbol],["Direction",row.direction],["Strategy",row.strategy],["Timeframe",row.timeframe],["Entry price",price(row.entry_price)],["Take profit",price(row.take_profit)],["Stop loss",price(row.stop_loss)],["Confidence",row.confidence==null?"Unavailable":row.confidence+"%"],["Created",row.created_at],["Lifecycle",row.lifecycle],["Execution",row.execution_state],["Settlement",row.settlement_state],["Broker order",row.broker_order_id],["Position contract",row.contract_id]];
    $("signalsDetailContent").innerHTML=fields.map(([label,value])=>"<div><dt>"+esc(label)+"</dt><dd>"+esc(value==null||value===""?"Unavailable":value)+"</dd></div>").join("");
    const dialog=$("signalsDetailDialog"); if(typeof dialog.showModal==="function")dialog.showModal();
  };
  const renderTable = () => {
    $("signalsRows").innerHTML=state.rows.length?state.rows.map(row=>{
      const d=dateParts(row.created_at), direction=String(row.direction||"").toUpperCase(), status=String(row.lifecycle||"unknown").toLowerCase();
      const confidence=numeric(row.confidence), strategyType=String(row.strategy_category||"").toLowerCase();
      const classification=/scalp/.test(strategyType+" "+row.strategy)?"Scalping":/swing/.test(strategyType+" "+row.strategy)?"Swing":/intraday/.test(strategyType+" "+row.strategy)?"Intraday":(row.timeframe||"Unclassified");
      const targetPct=changePct(row,row.take_profit,true), stopPct=changePct(row,row.stop_loss,false);
      return '<tr><td><span class="signals-time">'+esc(d.time)+'</span><span class="signals-date">'+esc(d.date)+'</span></td><td><div class="signals-asset">'+assetIcon(row)+'<div><strong>'+esc(row.symbol)+'</strong><small>'+esc(marketType(row))+'</small></div></div></td><td><span class="signals-direction '+(direction==="BUY"?"buy":direction==="SELL"?"sell":"unknown")+'">'+(direction==="BUY"?"↑ ":direction==="SELL"?"↓ ":"")+esc(direction||"Unavailable")+'</span></td><td>'+esc(row.strategy||"Strategy unavailable")+'<br><span class="signals-strategy">'+esc(classification)+'</span></td><td>'+esc(price(row.entry_price))+'</td><td>'+esc(price(row.take_profit))+'<small class="signals-date">'+esc(row.take_profit==null?"":targetPct)+'</small></td><td>'+esc(price(row.stop_loss))+'<small class="signals-date">'+esc(row.stop_loss==null?"":stopPct)+'</small></td><td><div class="signals-confidence"><span>'+(confidence==null?"—":esc(confidence.toFixed(0)+"%"))+'</span><div class="signals-confidence-track"><i class="'+(confidence!=null&&confidence<70?"low":"")+'" style="width:'+(confidence==null?0:Math.max(0,Math.min(100,confidence)))+'%"></i></div></div></td><td><span class="signals-status '+(status==="active"?"active":status==="expired"?"expired":"")+'">'+esc(status.replaceAll("_"," "))+'</span></td><td><button class="signals-row-action" type="button" data-signal-id="'+esc(row.id)+'" aria-label="View signal '+esc(row.symbol)+' details" title="View signal details">›</button></td></tr>';
    }).join(""):'<tr><td colspan="10" class="signals-empty">No signals match these filters.</td></tr>';
    renderPagination();
  };
  const renderFeed = () => {
    $("signalsRecentFeed").innerHTML=state.rows.slice(0,5).map(row=>{
      const direction=String(row.direction||"").toUpperCase();
      return '<div class="signals-feed-item">'+assetIcon(row)+'<div class="signals-feed-copy"><strong>'+esc(row.symbol)+' <span class="signals-direction '+(direction==="BUY"?"buy":direction==="SELL"?"sell":"unknown")+'">'+esc(direction||"—")+'</span></strong><p>'+esc(row.strategy||"Strategy unavailable")+' · '+esc(row.timeframe||"Timeframe unavailable")+'</p></div><span class="signals-feed-time">'+esc(relative(row.created_at))+'</span></div>';
    }).join("")||'<p class="signals-empty">No recent signals available.</p>';
  };
  const refresh = async () => {
    if(state.loading)return;
    state.loading=true; $("signalsRefresh").disabled=true; $("signalsServiceState").textContent="Loading signal data…"; $("signalsLiveDot").classList.remove("is-live"); $("signalsError").hidden=true;
    try{
      const payload=await request();
      state.rows=payload.signals;state.total=Number(payload.total);state.pages=Math.max(1,Number(payload.pages)||1);state.page=Number(payload.page)||1;state.counts=payload.category_counts||{};
      $("signalsServiceState").textContent="Signal service connected";$("signalsLiveDot").classList.add("is-live");$("signalsUpdatedAt").textContent="Updated "+new Date().toLocaleString();
      const select=$("signalsAssetFilter"),current=select.value;
      // Build options from the authenticated account's available signals. Server filtering remains authoritative.
      const symbols=[...new Set([...state.rows.map(r=>r.symbol).filter(Boolean),...(current?[current]:[])])].sort();
      select.innerHTML='<option value="">All Assets</option>'+symbols.map(s=>'<option value="'+esc(s)+'">'+esc(s)+'</option>').join("");
      if(symbols.includes(current))select.value=current;
      renderMetrics(payload);renderTable();renderFeed();
    }catch(error){
      $("signalsServiceState").textContent="Signal service unavailable";$("signalsLiveDot").classList.remove("is-live");$("signalsUpdatedAt").textContent="Last successful update unavailable";
      $("signalsRows").innerHTML='<tr><td colspan="10" class="signals-empty">Signals could not be loaded. Retry when the service is available.</td></tr>';
      $("signalsError").textContent=error.message||"Unable to load signals.";$("signalsError").hidden=false;
    }finally{state.loading=false;$("signalsRefresh").disabled=false;}
  };
  const changePage = page => {state.page=Math.max(1,Math.min(state.pages,page));refresh();};
  document.querySelectorAll("[data-category]").forEach(button=>button.addEventListener("click",()=>{state.category=button.dataset.category;state.page=1;document.querySelectorAll("[data-category]").forEach(item=>item.classList.toggle("is-active",item===button));refresh();}));
  $("signalsMarketFilter").addEventListener("change",()=>{state.page=1;refresh();});
  $("signalsAssetFilter").addEventListener("change",()=>{state.page=1;refresh();});
  $("signalsPrev").addEventListener("click",()=>changePage(state.page-1));
  $("signalsNext").addEventListener("click",()=>changePage(state.page+1));
  $("signalsPageNumbers").addEventListener("click",event=>{const b=event.target.closest("[data-page]");if(b)changePage(Number(b.dataset.page));});
  $("signalsRows").addEventListener("click",event=>{const b=event.target.closest("[data-signal-id]");if(b){const row=state.rows.find(r=>String(r.id)===b.dataset.signalId);if(row)showDetails(row);}});
  $("signalsRefresh").addEventListener("click",refresh);
  $("signalsDetailClose").addEventListener("click",()=>$("signalsDetailDialog").close());
  $("signalsDetailDialog").addEventListener("click",event=>{if(event.target===$("signalsDetailDialog"))$("signalsDetailDialog").close();});
  // Historical time series are not part of the current API contract; do not render illustrative chart lines as data.
  document.querySelectorAll(".signals-spark").forEach(el=>{el.innerHTML='<span class="signals-data-note">Trend history unavailable</span>';el.setAttribute("aria-label","Historical trend data unavailable");});
  refresh();
})();