(() => {
  "use strict";
  if (window.__algoBotSignalsReference) return;
  window.__algoBotSignalsReference = true;
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? "—").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[c]));
  const state = {rows:[], page:1, size:10, category:"all", loading:false, lastUpdated:null};
  const request = async () => {
    const response = await fetch("/api/market/signals/lifecycle/?limit=100", {credentials:"same-origin", headers:{Accept:"application/json"}});
    let payload = {};
    try { payload = await response.json(); } catch (_) {}
    if (!response.ok) throw new Error(payload.detail || payload.message || "Signal service request failed (" + response.status + ").");
    if (!Array.isArray(payload.signals)) throw new Error("Signal service returned an unexpected response.");
    return payload;
  };
  const strategyType = row => {
    const text = String(row.strategy || "").toLowerCase() + " " + String(row.timeframe || "").toLowerCase();
    if (text.includes("scalp")) return "scalping";
    if (text.includes("swing")) return "swing";
    if (text.includes("intraday") || /\b(m1|m5|m15|m30|h1|h4)\b/.test(text)) return "intraday";
    return "other";
  };
  const marketType = symbol => {
    const s = String(symbol || "").toUpperCase();
    if (/^(BTC|ETH|LTC|XRP|BCH|ADA|DOGE|SOL|DOT|BNB|TRX|AVAX|LINK|CRY)/.test(s)) return "crypto";
    if (/^(FRX)?[A-Z]{6}$/.test(s.replace("/", ""))) return "forex";
    if (/^(XAU|XAG|WTI|BRENT|UKOIL|USOIL|NGAS)/.test(s)) return "commodity";
    if (/^(NAS|US30|US500|SPX|DJI|DAX|FTSE|R_)/.test(s)) return "index";
    if (/^[A-Z]{1,5}(\.[A-Z]+)?$/.test(s)) return "stock";
    return "other";
  };
  const dateParts = value => {
    if (!value) return {time:"—",date:"—"};
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return {time:"—",date:"—"};
    return {time:d.toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"}),date:d.toLocaleDateString([], {month:"short",day:"2-digit"})};
  };
  const relative = value => {
    const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000));
    if (!Number.isFinite(seconds)) return "Time unavailable";
    if (seconds < 60) return seconds + "s ago";
    if (seconds < 3600) return Math.floor(seconds/60) + "m ago";
    if (seconds < 86400) return Math.floor(seconds/3600) + "h ago";
    return Math.floor(seconds/86400) + "d ago";
  };
  const visibleRows = () => {
    let rows = state.rows.slice();
    const category = state.category;
    if (category === "high") rows = rows.filter(r => r.confidence != null && Number(r.confidence) >= 80);
    else if (["scalping","intraday","swing"].includes(category)) rows = rows.filter(r => strategyType(r) === category);
    const market = $("signalsMarketFilter").value;
    const asset = $("signalsAssetFilter").value;
    if (market) rows = rows.filter(r => marketType(r.symbol) === market);
    if (asset) rows = rows.filter(r => r.symbol === asset);
    return rows;
  };
  const renderMetrics = () => {
    $("metricTotal").textContent = String(state.rows.length);
    $("metricActive").textContent = String(state.rows.filter(r => r.lifecycle === "active").length);
    $("countAll").textContent = state.rows.length;
    $("countHigh").textContent = state.rows.filter(r => r.confidence != null && Number(r.confidence) >= 80).length;
    $("countScalping").textContent = state.rows.filter(r => strategyType(r) === "scalping").length;
    $("countIntraday").textContent = state.rows.filter(r => strategyType(r) === "intraday").length;
    $("countSwing").textContent = state.rows.filter(r => strategyType(r) === "swing").length;
    $("metricWinRate").textContent = "Unavailable";
    $("metricProfitFactor").textContent = "Unavailable";
  };
  const assetIcon = row => '<span class="signals-asset-icon" aria-hidden="true"><span class="material-symbols-rounded">show_chart</span></span>';
  const renderTable = () => {
    const rows = visibleRows();
    const pages = Math.max(1, Math.ceil(rows.length / state.size));
    state.page = Math.min(state.page, pages);
    const start = (state.page - 1) * state.size;
    const pageRows = rows.slice(start, start + state.size);
    $("signalsRows").innerHTML = pageRows.length ? pageRows.map(row => {
      const d = dateParts(row.created_at);
      const direction = String(row.direction || "").toUpperCase();
      const status = String(row.lifecycle || "unknown").toLowerCase();
      const confidence = row.confidence == null ? null : Math.max(0,Math.min(100,Number(row.confidence)));
      const strategy = row.strategy || "Strategy unavailable";
      return '<tr><td><span class="signals-time">'+esc(d.time)+'</span><span class="signals-date">'+esc(d.date)+'</span></td><td><div class="signals-asset">'+assetIcon(row)+'<div><strong>'+esc(row.symbol)+'</strong><small>'+esc(marketType(row.symbol))+'</small></div></div></td><td><span class="signals-direction '+(direction==="BUY"?"buy":direction==="SELL"?"sell":"unknown")+'">'+(direction==="BUY"?"↑ ":direction==="SELL"?"↓ ":"") + esc(direction || "Unavailable")+'</span></td><td>'+esc(strategy)+'<br><span class="signals-strategy">'+esc(strategyType(row)==="other"?(row.timeframe||"Unclassified"):strategyType(row))+'</span></td><td>—</td><td>—</td><td>—</td><td><div class="signals-confidence"><span>'+ (confidence == null ? "—" : esc(confidence.toFixed(0)+"%"))+'</span><div class="signals-confidence-track"><i class="'+(confidence!=null&&confidence<70?"low":"")+'" style="width:'+(confidence==null?0:confidence)+'%"></i></div></div></td><td><span class="signals-status '+(status==="active"?"active":status==="expired"?"expired":"")+'">'+esc(status.replaceAll("_"," "))+'</span></td><td><button class="signals-row-action" type="button" data-signal-id="'+esc(row.id)+'" aria-label="View signal '+esc(row.symbol)+' details" title="View signal details">›</button></td></tr>';
    }).join("") : '<tr><td colspan="10" class="signals-empty">No signals match these filters.</td></tr>';
    $("signalsPrev").disabled = state.page <= 1;
    $("signalsNext").disabled = state.page >= pages;
    $("signalsPageNumbers").innerHTML = Array.from({length:pages},(_,i)=>i+1).filter(n=>pages<=5||n===1||n===pages||Math.abs(n-state.page)<=1).map(n=>'<button type="button" data-page="'+n+'" '+(n===state.page?'aria-current="page"':'')+'>'+n+'</button>').join(pages>5&&state.page<pages-2?'<span>…</span>':"");
    $("signalsResultSummary").textContent = rows.length ? "Showing "+(start+1)+"–"+Math.min(start+state.size,rows.length)+" of "+rows.length+" loaded signals" : "Showing 0 signals";
    $("signalsRows").querySelectorAll("[data-signal-id]").forEach(button => button.addEventListener("click",()=> {
      const row = state.rows.find(item => String(item.id) === button.dataset.signalId);
      if (!row) return;
      const dialog = $("signalsDetailDialog");
      const fields = [["Signal ID",row.id],["Asset",row.symbol],["Direction",row.direction],["Strategy",row.strategy],["Timeframe",row.timeframe],["Confidence",row.confidence == null ? "Unavailable" : row.confidence + "%"],["Created",row.created_at],["Lifecycle",row.lifecycle],["Execution",row.execution_state],["Settlement",row.settlement_state],["Broker order",row.broker_order_id],["Position contract",row.contract_id]];
      $("signalsDetailContent").innerHTML = fields.map(([label,value]) => "<div><dt>"+esc(label)+"</dt><dd>"+esc(value == null || value === "" ? "Unavailable" : value)+"</dd></div>").join("");
      if (typeof dialog.showModal === "function") dialog.showModal();
    }));
  };
  const renderFeed = () => {
    $("signalsRecentFeed").innerHTML = state.rows.slice(0,5).map(row => {
      const direction = String(row.direction || "").toUpperCase();
      return '<div class="signals-feed-item">'+assetIcon(row)+'<div class="signals-feed-copy"><strong>'+esc(row.symbol)+' <span class="signals-direction '+(direction==="BUY"?"buy":direction==="SELL"?"sell":"unknown")+'">'+esc(direction||"—")+'</span></strong><p>'+esc(row.strategy)+' · '+esc(row.timeframe||"Timeframe unavailable")+'</p></div><span class="signals-feed-time">'+esc(relative(row.created_at))+'</span></div>';
    }).join("") || '<p class="signals-empty">No recent signals available.</p>';
  };
  const refresh = async () => {
    if (state.loading) return;
    state.loading = true;
    $("signalsRefresh").disabled = true;
    $("signalsServiceState").textContent = "Refreshing signals…";
    $("signalsError").hidden = true;
    try {
      const payload = await request();
      state.rows = payload.signals;
      state.lastUpdated = new Date();
      $("signalsServiceState").textContent = "Signal service connected";
      $("signalsLiveDot").classList.add("is-live");
      $("signalsUpdatedAt").textContent = "Updated " + state.lastUpdated.toLocaleString();
      const assetSelect = $("signalsAssetFilter"), current = assetSelect.value;
      const symbols = [...new Set(state.rows.map(r=>r.symbol).filter(Boolean))].sort();
      assetSelect.innerHTML = '<option value="">All Assets</option>'+symbols.map(s=>'<option value="'+esc(s)+'">'+esc(s)+'</option>').join("");
      if (symbols.includes(current)) assetSelect.value = current;
      renderMetrics(); renderTable(); renderFeed();
    } catch (error) {
      $("signalsServiceState").textContent = "Signal service unavailable";
      $("signalsLiveDot").classList.remove("is-live");
      $("signalsUpdatedAt").textContent = "Last successful update unavailable";
      $("signalsRows").innerHTML = '<tr><td colspan="10" class="signals-empty">Signals could not be loaded. Retry when the service is available.</td></tr>';
      $("signalsError").textContent = error.message || "Unable to load signals.";
      $("signalsError").hidden = false;
    } finally {
      state.loading = false;
      $("signalsRefresh").disabled = false;
    }
  };
  document.querySelectorAll("[data-category]").forEach(button => button.addEventListener("click",()=>{
    state.category = button.dataset.category; state.page = 1;
    document.querySelectorAll("[data-category]").forEach(item=>item.classList.toggle("is-active",item===button));
    renderTable();
  }));
  $("signalsMarketFilter").addEventListener("change",()=>{state.page=1;renderTable()});
  $("signalsAssetFilter").addEventListener("change",()=>{state.page=1;renderTable()});
  $("signalsPrev").addEventListener("click",()=>{state.page=Math.max(1,state.page-1);renderTable()});
  $("signalsNext").addEventListener("click",()=>{state.page+=1;renderTable()});
  $("signalsPageNumbers").addEventListener("click",event=>{const button=event.target.closest("[data-page]");if(button){state.page=Number(button.dataset.page);renderTable()}});
  $("signalsRefresh").addEventListener("click",refresh);
  $("signalsDetailClose").addEventListener("click",()=> $("signalsDetailDialog").close());
  $("signalsDetailDialog").addEventListener("click",event=>{if(event.target === $("signalsDetailDialog")) $("signalsDetailDialog").close();});
  refresh();
})();