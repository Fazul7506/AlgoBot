(() => {
  "use strict";
  if (window.__algoBotAnalysisWorkspace) return;
  window.__algoBotAnalysisWorkspace = true;
  const $ = id => document.getElementById(id);
  const esc = v => String(v ?? "—").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const num = (v,d=5) => v==null || v==="" || !Number.isFinite(Number(v)) ? "—" : Number(v).toLocaleString(undefined,{maximumFractionDigits:d});
  const pct = v => v==null || v==="" || !Number.isFinite(Number(v)) ? "—" : Number(v).toFixed(1)+"%";
  const pctNorm = v => v==null || v==="" || !Number.isFinite(Number(v)) ? "—" : pct(Number(v)<=1?Number(v)*100:Number(v));
  const money = (v,c) => v==null || v==="" || !Number.isFinite(Number(v)) ? "—" : (c ? c+" " : "")+Number(v).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
  const state = v => String(v ?? "UNAVAILABLE").replaceAll("_"," ");
  const tone = v => ["BUY","BULLISH","STRONG BULLISH"].includes(String(v||"").toUpperCase()) ? "positive" : ["SELL","BEARISH","STRONG BEARISH"].includes(String(v||"").toUpperCase()) ? "negative" : "neutral";
  const A = {markets:[],data:null,contract:null,timer:null,loadGeneration:0,overviewKey:'',overviewCache:[],predictionCache:[],overviewFetchedAt:0,overviewPending:false,cachedData:null,cacheKey:''};

  async function request(path, options={}) {
    return window.AlgoBotFrontendData.request(path, options, 12000);
  }
  function set(id,v){const e=$(id);if(e)e.textContent=v==null||v===""?"—":v}
  function marketName(row){
    if(!row)return "Market instrument";
    const symbol=String(row.symbol||row.underlying_symbol||row.code||"").trim();
    const supplied=String(row.display_name||row.displayName||row.name||row.underlying_symbol_name||"").trim();
    if(supplied&&supplied.toUpperCase()!==symbol.toUpperCase())return supplied;
    const resolved=window.AlgoBotMarketAssets?.resolve?.({...row,symbol});
    if(resolved?.status==="verified"&&resolved.asset?.label)return resolved.asset.label;
    const key=symbol.toUpperCase().replace(/^CRY/,"");
    const known={R_10:"Volatility 10 Index",R_25:"Volatility 25 Index",R_50:"Volatility 50 Index",R_75:"Volatility 75 Index",R_100:"Volatility 100 Index",BOOM50:"Boom 50 Index",BOOM100:"Boom 100 Index",BOOM150:"Boom 150 Index",BOOM200:"Boom 200 Index",BOOM300:"Boom 300 Index",BOOM500:"Boom 500 Index",BOOM600:"Boom 600 Index",BOOM900:"Boom 900 Index",BOOM1000:"Boom 1000 Index",CRASH50:"Crash 50 Index",CRASH150:"Crash 150 Index",CRASH300:"Crash 300 Index",CRASH500:"Crash 500 Index",CRASH600:"Crash 600 Index",CRASH900:"Crash 900 Index",CRASH1000:"Crash 1000 Index",STPRNG:"Step Index 100",STP100:"Step Index 100",STP200:"Step Index 200",STP300:"Step Index 300",STP400:"Step Index 400",STP500:"Step Index 500",JD10:"Jump 10 Index",JD25:"Jump 25 Index",JD50:"Jump 50 Index",JD75:"Jump 75 Index",JD100:"Jump 100 Index",RB100:"Range Break 100 Index",RB200:"Range Break 200 Index",RDBEAR:"Bear Market Index",RDBULL:"Bull Market Index",BTCUSD:"BTC/USD",ETHUSD:"ETH/USD"};
    if(known[key])return known[key];
    const fast=/^1HZ(\d+)V$/.exec(key);if(fast)return "Volatility "+fast[1]+" (1s) Index";
    const fx=/^FRX([A-Z]{6})$/.exec(key);if(fx)return fx[1].slice(0,3)+"/"+fx[1].slice(3);
    return "Market instrument";
  }
  function iconFor(row){return window.AlgoBotMarketAssets?.renderIcon?.({...row,display_name:marketName(row)})||'<span class="market-avatar market-avatar-unmapped" aria-hidden="true">•</span>';}
  function updateSelectedMarketIcon(){const select=$("symbol"),icon=$("analysisMarketIcon");if(!select||!icon)return;const row=A.markets.find(item=>String(item.symbol)===String(select.value));icon.innerHTML=row?iconFor(row):"";}
  function cacheKey(symbol,tf,limit){return "algobot:analysis:snapshot:v1:"+[symbol,tf,limit].join(":");}
  function restoreCached(symbol,tf,limit){A.cachedData=null;try{const raw=sessionStorage.getItem(cacheKey(symbol,tf,limit));const data=raw?JSON.parse(raw):null;if(data&&data.symbol===symbol&&Array.isArray(data.last_candles)){A.cachedData=data;A.data=data;render(data);setHealth(false,"SAVED DATA · REFRESHING");set("aFresh","SAVED DATA · NOT LIVE");const hero=$("heroFeedState");if(hero)hero.textContent="Showing saved analysis while refreshing";const stateNode=$("loadState");if(stateNode)stateNode.textContent="Showing last saved analysis; checking for current broker data…";return true;}}catch(_){}return false;}
  function list(id,items,fn,empty="No observed evidence."){const e=$(id);if(e)e.innerHTML=items?.length?items.map(fn).join(""):'<span class="muted">'+esc(empty)+"</span>"}
  function setHealth(ok,text){const feed=$("aFeed");if(feed){feed.className="health-dot "+(ok?"live":"");feed.textContent=text}set("aFeedText",text)}
  function resetUnavailable(){
    const values={
      aResearchState:"UNAVAILABLE",aBrokerState:"UNAVAILABLE",aSymbol:"—",aTf:"—",aPrice:"—",aSignal:"UNAVAILABLE",aTechnical:"—",aConfidence:"—",aRegime:"—",aFresh:"DATA UNAVAILABLE",
      liveQuote:"—",liveQuoteAge:"Live quote freshness unavailable",liveQuoteSource:"—",sentimentState:"Unavailable",sentimentScore:"No verified score",sentimentSummary:"No verified sentiment feed supplied",
      trendState:"Unavailable",trendScore:"—",momentumState:"—",volatilityState:"Unavailable",strategyState:"No verified strategy evidence",strategyDirection:"WAIT",strategyEvidence:"No verified strategy evidence",
      aiState:"UNAVAILABLE",aiDecision:"UNAVAILABLE",aiConfidence:"—",aiModels:"0",aiAgreement:"—",confluenceState:"UNAVAILABLE",confluenceDirection:"WAIT",confluenceScore:"—",
      validationState:"UNAVAILABLE",validationDirection:"WAIT",validationExpiry:"—",noLookAhead:"UNCONFIRMED",marketState:"UNAVAILABLE",marketSource:"—",marketAge:"—",candleCount:"—",
      keyCurrentPrice:"—",resistance1:"—",resistance2:"—",support1:"—",support2:"—",sma20:"—",sma50:"—",sma200:"—",ema:"— / —",rsi:"—",atr:"—",macd:"—",bb:"—",
      account:"NO VERIFIED ACCOUNT CONTEXT",accountType:"—",currency:"—",balance:"—",riskBudget:"—",stake:"—",provenanceMarket:"—",provenanceCandles:"—",provenanceAnalysis:"—",provenanceExecution:"—",
      gateState:"BLOCKED",gateReason:"Fresh analysis evidence could not be confirmed.",heroFeedState:"Market feed unavailable",referenceUpdatedAt:"Last update unavailable",aiReason:"No verified AI analysis available"
    };
    Object.entries(values).forEach(([id,value])=>set(id,value));
    const fill=$("confidenceFill");if(fill)fill.style.width="0%";
    const pulse=document.querySelector(".reference-live-dot");if(pulse)pulse.style.background="#eab44d";
    const statusPulse=document.querySelector(".status-pulse");if(statusPulse)statusPulse.classList.remove("is-live");
    list("marketOverviewRows",[],()=>"", "No verified market data available.");
    list("predictionRows",[],()=>"", "No verified AI prediction is available.");
    list("sentimentNewsRows",[],()=>"", "No verified sentiment or news feed is available.");
    list("factorList",[],()=>"", "No verified technical factors.");
    ["events","sweeps","fvgs","zones","patterns"].forEach(id=>list(id,[],()=>"", "No verified evidence available."));
    drawChart([]);drawIndicators([]);
  }

  function drawChart(candles){
    const canvas=$("analysisChart"),empty=$("chartEmpty");if(!canvas)return;
    const valid=(candles||[]).filter(c=>[c.open,c.high,c.low,c.close].every(v=>Number.isFinite(Number(v))));
    if(!valid.length){canvas.hidden=true;if(empty)empty.hidden=false;return}
    canvas.hidden=false;if(empty)empty.hidden=true;
    const box=canvas.getBoundingClientRect(),q=window.devicePixelRatio||1,w=Math.max(320,box.width),h=Math.max(250,box.height);
    canvas.width=Math.round(w*q);canvas.height=Math.round(h*q);const ctx=canvas.getContext("2d");ctx.setTransform(q,0,0,q,0,0);ctx.clearRect(0,0,w,h);
    const pad={l:8,r:54,t:12,b:20},closes=valid.map(c=>Number(c.close));
    const bands=closes.map((_,i)=>{if(i<19)return null;const a=closes.slice(i-19,i+1),mean=a.reduce((x,y)=>x+y,0)/a.length,sd=Math.sqrt(a.reduce((x,y)=>x+(y-mean)**2,0)/a.length);return {mid:mean,upper:mean+2*sd,lower:mean-2*sd}});
    const lows=valid.map(c=>Number(c.low)),highs=valid.map(c=>Number(c.high));
    bands.forEach(b=>{if(b){lows.push(b.lower);highs.push(b.upper)}});
    let lo=Math.min(...lows),hi=Math.max(...highs);if(!Number.isFinite(lo)||!Number.isFinite(hi)){lo=Math.min(...valid.map(c=>Number(c.low)));hi=Math.max(...valid.map(c=>Number(c.high)))}
    const span=hi-lo||Math.max(Math.abs(hi)*.001,1),x=i=>pad.l+i/Math.max(1,valid.length-1)*(w-pad.l-pad.r),y=v=>h-pad.b-(Number(v)-lo)/span*(h-pad.t-pad.b);
    ctx.font="10px system-ui";ctx.textAlign="left";ctx.textBaseline="middle";ctx.strokeStyle="rgba(148,177,211,.17)";ctx.fillStyle="#8faacc";
    for(let i=0;i<=5;i++){const val=hi-(hi-lo)*i/5,yy=y(val);ctx.beginPath();ctx.moveTo(pad.l,yy);ctx.lineTo(w-pad.r,yy);ctx.stroke();ctx.fillText(val.toFixed(Math.abs(val)<10?4:2),w-pad.r+5,yy)}
    const plotLine=(key,color,width=1.1)=>{ctx.beginPath();ctx.strokeStyle=color;ctx.lineWidth=width;let begun=false;bands.forEach((b,i)=>{if(!b){begun=false;return}const v=b[key];if(!begun){ctx.moveTo(x(i),y(v));begun=true}else ctx.lineTo(x(i),y(v))});ctx.stroke()};
    plotLine("upper","#2689f4",1);plotLine("mid","#8b72ff",1);plotLine("lower","#2689f4",1);
    const step=(w-pad.l-pad.r)/Math.max(1,valid.length),body=Math.max(1,Math.min(7,step*.68));
    valid.forEach((c,i)=>{const xx=x(i),up=Number(c.close)>=Number(c.open);ctx.strokeStyle=up?"#21d6a0":"#ff526d";ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(xx,y(c.high));ctx.lineTo(xx,y(c.low));ctx.stroke();const top=Math.min(y(c.open),y(c.close)),bh=Math.max(1,Math.abs(y(c.close)-y(c.open)));ctx.fillStyle=up?"#21d6a0":"#ff526d";ctx.fillRect(xx-body/2,top,body,bh)});
    ctx.fillStyle="#8faacc";ctx.textAlign="center";ctx.textBaseline="top";
    [0,.25,.5,.75,1].forEach(f=>{const i=Math.min(valid.length-1,Math.round((valid.length-1)*f)),stamp=valid[i]?.time??valid[i]?.timestamp??valid[i]?.datetime;if(stamp!=null){let label=String(stamp);const dt=new Date(typeof stamp==="number"&&stamp<1e12?stamp*1000:stamp);if(!Number.isNaN(dt.getTime()))label=dt.toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"});ctx.fillText(label,x(i),h-pad.b+5,w/5)}});
  }

  function emaSeries(values, period){
    const out=Array(values.length).fill(null); if(values.length<period)return out;
    const k=2/(period+1); let current=values.slice(0,period).reduce((a,b)=>a+b,0)/period; out[period-1]=current;
    for(let i=period;i<values.length;i++){current=values[i]*k+current*(1-k);out[i]=current}
    return out;
  }
  function drawLinePanel(canvasId,emptyId,series,opts={}){
    const canvas=$(canvasId), empty=$(emptyId); if(!canvas)return;
    const valid=series.filter(s=>Array.isArray(s.values)&&s.values.some(Number.isFinite));
    if(!valid.length){canvas.hidden=true;if(empty)empty.hidden=false;return}
    canvas.hidden=false;if(empty)empty.hidden=true;
    const box=canvas.getBoundingClientRect(),q=window.devicePixelRatio||1,w=Math.max(240,box.width),h=Math.max(90,box.height);
    canvas.width=Math.round(w*q);canvas.height=Math.round(h*q);const ctx=canvas.getContext("2d");ctx.setTransform(q,0,0,q,0,0);ctx.clearRect(0,0,w,h);
    const pad={l:8,r:8,t:8,b:8},n=Math.max(...valid.map(s=>s.values.length));
    let lo=opts.min??Math.min(...valid.flatMap(s=>s.values.filter(Number.isFinite))),hi=opts.max??Math.max(...valid.flatMap(s=>s.values.filter(Number.isFinite)));
    if(opts.min==null){const span=hi-lo||1;lo-=span*.12;hi+=span*.12}
    if(hi===lo)hi=lo+1;
    const px=i=>pad.l+i/Math.max(1,n-1)*(w-pad.l-pad.r),py=v=>h-pad.b-(v-lo)/(hi-lo)*(h-pad.t-pad.b);
    ctx.lineWidth=1;ctx.strokeStyle="rgba(148,177,211,.18)";
    for(let i=1;i<4;i++){const y=pad.t+(h-pad.t-pad.b)*i/4;ctx.beginPath();ctx.moveTo(pad.l,y);ctx.lineTo(w-pad.r,y);ctx.stroke()}
    (opts.levels||[]).forEach(level=>{ctx.save();ctx.setLineDash([4,4]);ctx.strokeStyle="rgba(167,186,215,.55)";ctx.beginPath();ctx.moveTo(pad.l,py(level));ctx.lineTo(w-pad.r,py(level));ctx.stroke();ctx.restore()});
    if(opts.histogram){const values=opts.histogram.filter(Number.isFinite),base=opts.zero?py(0):h-pad.b,bw=Math.max(1,(w-pad.l-pad.r)/Math.max(1,opts.histogram.length)*.72);opts.histogram.forEach((v,i)=>{if(!Number.isFinite(v))return;ctx.fillStyle=v>=0?"#25d3a0":"#f05270";const yy=py(v),xx=pad.l+i/Math.max(1,n-1)*(w-pad.l-pad.r);ctx.fillRect(xx-bw/2,Math.min(yy,base),bw,Math.max(1,Math.abs(base-yy)))});}
    valid.forEach(s=>{ctx.beginPath();ctx.strokeStyle=s.color;ctx.lineWidth=1.6;let started=false;s.values.forEach((v,i)=>{if(!Number.isFinite(v)){started=false;return}if(!started){ctx.moveTo(px(i),py(v));started=true}else ctx.lineTo(px(i),py(v))});ctx.stroke()});
    if(opts.zero){ctx.strokeStyle="rgba(167,186,215,.55)";ctx.beginPath();ctx.moveTo(pad.l,py(0));ctx.lineTo(w-pad.r,py(0));ctx.stroke()}
  }
  function drawIndicators(candles){
    const closes=(candles||[]).map(c=>Number(c.close)).filter(Number.isFinite);
    if(closes.length<2){drawLinePanel("macdChart","macdEmpty",[]);drawLinePanel("rsiChart","rsiEmpty",[]);return}
    const fast=emaSeries(closes,12),slow=emaSeries(closes,26);
    const macd=closes.map((_,i)=>fast[i]!=null&&slow[i]!=null?fast[i]-slow[i]:null);
    const macdValues=macd.filter(Number.isFinite),signalCompact=emaSeries(macdValues,9);
    const signal=Array(macd.length).fill(null);let si=0;macd.forEach((v,i)=>{if(Number.isFinite(v)){signal[i]=signalCompact[si++]}});
    const histogram=macd.map((v,i)=>Number.isFinite(v)&&Number.isFinite(signal[i])?v-signal[i]:null);
    drawLinePanel("macdChart","macdEmpty",[
      {values:macd,color:"#a78bfa"},{values:signal,color:"#f6ad45"}
    ],{zero:true,histogram});
    const rsi=Array(closes.length).fill(null);
    if(closes.length>=15){let gains=0,losses=0;for(let i=1;i<=14;i++){const d=closes[i]-closes[i-1];if(d>=0)gains+=d;else losses-=d}
      let avgGain=gains/14,avgLoss=losses/14;rsi[14]=avgLoss===0?100:100-100/(1+avgGain/avgLoss);
      for(let i=15;i<closes.length;i++){const d=closes[i]-closes[i-1];avgGain=(avgGain*13+Math.max(d,0))/14;avgLoss=(avgLoss*13+Math.max(-d,0))/14;rsi[i]=avgLoss===0?100:100-100/(1+avgGain/avgLoss)}
    }
    drawLinePanel("rsiChart","rsiEmpty",[{values:rsi,color:"#a78bfa"}],{min:0,max:100,levels:[30,50,70]});
  }

  function render(d){
    A.data=d;
    const gate=d.execution_gate||{}, ai=d.ai||{}, layers=d.analysis_layers||{}, conf=d.confluence||{}, acct=d.account_context||{};
    const aiModelsUsed=Number(layers.ai?.models_used??ai.models_used??0);
    const aiConfidenceValue=layers.ai?.confidence??ai.confidence??d.confidence;
    const aiDecisionValue=layers.ai?.decision||ai.decision||layers.ai?.direction||ai.direction;
    const hasModelEvidence=aiModelsUsed>0&&aiConfidenceValue!=null&&Boolean(aiDecisionValue)&&!['UNAVAILABLE','NO_MODEL','NO PREDICTION'].includes(String(aiDecisionValue).toUpperCase());
    set("aResearchState",state(d.research_state)); set("aBrokerState",state(d.broker_state)); set("aSymbol",marketName(A.markets.find(m=>m.symbol===d.symbol)||{symbol:d.symbol})); set("aTf",String(d.timeframe||"M1").toUpperCase()); set("aPrice",num(d.price)); set("aSignal",d.signal==null?"UNAVAILABLE":d.signal); $("aSignal").className="value "+tone(d.signal); set("aTechnical",d.score!=null?num(d.score,1)+"/100":"Technical score —"); set("aFresh",d.data_provenance?.fresh?"FRESH DATA":"DATA UNVERIFIED"); set("liveQuote",num(d.live_quote?.price)); set("liveQuoteAge",d.live_quote?.age_seconds!=null?"Live quote age "+d.live_quote.age_seconds+"s":"Live quote freshness unavailable"); set("liveQuoteSource",d.live_quote?.source||"Deriv live quote");
    set("aTechnical",d.score!=null?num(d.score,1)+"/100":"—"); set("aConfidence",hasModelEvidence?pctNorm(aiConfidenceValue):"Unavailable"); const confidenceValue=Number(aiConfidenceValue);const confidenceFill=$("confidenceFill");if(confidenceFill)confidenceFill.style.width=hasModelEvidence&&Number.isFinite(confidenceValue)?Math.max(0,Math.min(100,confidenceValue<=1?confidenceValue*100:confidenceValue))+"%":"0%"; set("aRegime",d.volatility_regime);
    const sentiment=d.sentiment&&typeof d.sentiment==="object"?d.sentiment:null;
    const sentimentLabel=sentiment?.label||sentiment?.sentiment||sentiment?.classification;
    set("sentimentState",sentimentLabel?state(sentimentLabel):"Unavailable");
    set("sentimentScore",sentiment?.score!=null?("Score "+num(sentiment.score,1)):"No verified score");
    set("sentimentSummary",sentiment?.summary||sentiment?.source||"No sentiment feed supplied"); set("aFresh",d.data_provenance?.fresh?"FRESH":"STALE");
    const quoteFresh=Boolean(d.data_provenance?.fresh && d.live_quote?.fresh); setHealth(quoteFresh,quoteFresh?"DERIV LIVE":"DATA NOT FRESH"); const heroState=$("heroFeedState"); if(heroState)heroState.textContent=quoteFresh?"Live Analysis":"Market data needs verification"; const updated=$("referenceUpdatedAt");if(updated)updated.textContent="Last updated: "+new Date().toLocaleString();const pulse=document.querySelector(".reference-live-dot");if(pulse)pulse.style.background=quoteFresh?"#20d6a0":"#eab44d";
    const regime=String(d.volatility_regime||"").toLowerCase();const volatilityFill=$("volatilityFill");if(volatilityFill)volatilityFill.style.width=/high|extreme|highly/.test(regime)?"85%":/low|quiet/.test(regime)?"28%":/moderate|normal|medium/.test(regime)?"50%":"0%";
    set("marketState",state(layers.market_data?.state)); set("marketSource",layers.market_data?.source||d.data_provenance?.broker); set("marketAge",d.data_provenance?.age_seconds!=null?d.data_provenance.age_seconds+"s":"—"); set("candleCount",d.candles??d.last_candles?.length);
    set("trendState",layers.technical?.structure||d.structure); set("trendScore",layers.technical?.score!=null?num(layers.technical.score,1)+"/100":"—"); set("momentumState",d.indicators?.rsi14!=null?"RSI "+num(d.indicators.rsi14,1):"—"); set("volatilityState",d.volatility_regime);
    set("strategyState",state(layers.strategy?.state)); set("strategyDirection",layers.strategy?.direction||"WAIT"); set("strategyEvidence",(layers.strategy?.evidence||[]).join(" · ")||"No persisted strategy evidence");
    set("aiState",state(layers.ai?.state)); set("aiDecision",hasModelEvidence?aiDecisionValue:"UNAVAILABLE"); set("aiConfidence",hasModelEvidence?pctNorm(aiConfidenceValue):"Unavailable"); set("aiModels",aiModelsUsed>0?String(aiModelsUsed):"0"); set("aiAgreement",layers.ai?.agreement!=null?pct(Number(layers.ai.agreement)*100):"—");
    set("confluenceState",state(conf.state)); set("confluenceDirection",conf.direction||"WAIT"); set("confluenceScore",conf.score!=null?num(conf.score,1)+"/100":"—");
    list("confluenceEvidence", conf.evidence, e => { const cls = e.passed ? "pass" : "fail"; const label = e.passed ? "PASS" : "WAIT"; return '<div class="evidence-row"><span>' + esc(e.layer) + '</span><strong>' + esc(e.condition) + '</strong><b class="' + cls + '">' + label + '</b></div>'; });
    set("gateState",gate.ready?"EXECUTION ELIGIBLE":"BLOCKED"); set("gateReason",gate.reason|| (gate.ready?"All configured gates passed.":"One or more execution gates are not confirmed.")); set("validationState",state(d.signal_validation?.state)); set("validationDirection",d.signal_validation?.signal||"WAIT"); set("validationExpiry",d.signal_validation?.expires_after_seconds!=null?d.signal_validation.expires_after_seconds+" seconds":"—"); set("noLookAhead",d.signal_validation?.no_look_ahead===true?"CONFIRMED":"UNCONFIRMED");
    const gateRows=[["Market data",gate.data_fresh],["History",gate.sufficient_history],["AI",gate.ai_ready],["Broker contracts",gate.broker_contracts_confirmed],["Account scope",gate.account_scope_confirmed],["Account ready",gate.account_ready],["Risk",gate.risk_ready],["Live quote",gate.live_quote_confirmed&&gate.live_quote_fresh]];
    list("gateList", gateRows, e => { const cls = e[1] ? "pass" : "fail"; const label = e[1] ? "PASS" : "BLOCKED"; return '<div class="gate-row"><span>' + esc(e[0]) + '</span><b class="' + cls + '">' + label + '</b></div>'; });
    set("support",num(d.levels?.support));set("resistance",num(d.levels?.resistance));set("range",num(d.levels?.range));set("change",d.change_pct!=null?num(d.change_pct,2)+"%":"—");
    set("keyCurrentPrice",num(d.price));set("resistance1",num(d.levels?.resistance));set("support1",num(d.levels?.support));
    set("resistance2",num(d.levels?.resistance2));set("support2",num(d.levels?.support2));
    const signalText=hasModelEvidence?String(aiDecisionValue).toUpperCase():"UNAVAILABLE";
    const confText=hasModelEvidence?pctNorm(aiConfidenceValue):"—";
    const overviewRow=x=>{const market=A.markets.find(m=>m.symbol===x.symbol)||{symbol:x.symbol};return '<tr><td><span class="analysis-market-cell">'+iconFor(market)+'<span>'+esc(marketName(market))+'</span></span></td><td>'+esc(num(x.price))+'</td><td><span class="signal-pill '+tone(x.signal)+'">'+esc(x.signal)+'</span></td><td>'+esc(x.confidence)+'</td></tr>';};
    list("marketOverviewRows",[{symbol:d.symbol,price:d.price,signal:signalText,confidence:confText}],overviewRow,"No verified market data available.");
    const overviewKey=[d.symbol,d.timeframe||"M1",$("limit")?.value||300].join("|");
    if(A.overviewKey!==overviewKey){A.overviewKey=overviewKey;A.overviewCache=[];A.predictionCache=[];A.overviewFetchedAt=0;A.overviewPending=false;}
    A.overviewCache=[{symbol:d.symbol,price:d.price,signal:signalText,confidence:confText},...A.overviewCache.filter(x=>x.symbol!==d.symbol)].slice(0,5);
    const predictionDirection=hasModelEvidence?(layers.ai?.direction||layers.ai?.prediction||ai.direction||ai.prediction||aiDecisionValue):null;
    const predictionProbability=hasModelEvidence?(layers.ai?.probability??layers.ai?.probability_pct??ai.probability??ai.probability_pct??d.prediction_probability):null;
    A.predictionCache=[...(predictionDirection?[{symbol:d.symbol,direction:predictionDirection,probability:predictionProbability}]:[]),...A.predictionCache.filter(x=>x.symbol!==d.symbol)].slice(0,5);
    list("marketOverviewRows",A.overviewCache,overviewRow,"No verified market data available.");
    const predictionRow=x=>{const market=A.markets.find(m=>m.symbol===x.symbol)||{symbol:x.symbol};return '<tr><td><span class="analysis-market-cell">'+iconFor(market)+'<span>'+esc(marketName(market))+'</span></span></td><td><span class="prediction-direction '+tone(x.direction)+'">'+esc(state(x.direction))+'</span></td><td>'+esc(x.probability==null?"—":pct(Number(x.probability)>1?Number(x.probability):Number(x.probability)*100))+'</td></tr>';};
    list("predictionRows",A.predictionCache,predictionRow,"No verified AI prediction is available.");
    // Avoid firing multiple full AI/database analysis requests for overview rows.
    // Only the selected market is fetched here; overview data must not exhaust the DB pool.
    const newsItems=Array.isArray(d.news)?d.news:(Array.isArray(d.sentiment?.news)?d.sentiment.news:[]);
    const sentimentItems=Array.isArray(d.sentiment?.items)?d.sentiment.items:[];
    const combinedNews=[...newsItems,...sentimentItems].slice(0,8);
    list("sentimentNewsRows",combinedNews,item=>'<div class="news-row"><span class="news-dot '+(tone(item.sentiment||item.direction)==="positive"?"positive":tone(item.sentiment||item.direction)==="negative"?"negative":"neutral")+'"></span><div class="news-copy"><strong>'+esc(item.title||item.headline||item.label||"Market update")+'</strong><p>'+esc(item.summary||item.description||item.source||"")+'</p></div><time>'+esc(item.time_ago||item.published_at||item.timestamp||"")+'</time></div>',"No verified sentiment or news feed is available.");
    set("sma20",num(d.indicators?.sma20));set("sma50",num(d.indicators?.sma50));set("sma200",num(d.indicators?.sma200));set("ema",num(d.indicators?.ema9)+" / "+num(d.indicators?.ema21));set("rsi",num(d.indicators?.rsi14,2));set("atr",num(d.indicators?.atr14));set("macd",num(d.indicators?.macd?.histogram));set("bb",d.indicators?.bollinger?.width!=null?num(d.indicators.bollinger.width,2)+"%":"—");
    const fs=d.factors||[]; list("factorList",fs,x=>'<span class="tag">'+esc(x)+"</span>","No additional technical factors.");
    list("events",d.events,x=>'<div class="evidence-row"><span>'+esc(x.type)+"</span><strong>"+num(x.price)+"</strong></div>");
    list("sweeps",d.liquidity_sweeps,x=>'<div class="evidence-row"><span>'+esc(x.type)+"</span><strong>"+num(x.level)+"</strong></div>");
    list("fvgs",d.fair_value_gaps,x=>'<div class="evidence-row"><span>'+esc(x.type)+" FVG</span><strong>"+num(x.low)+"–"+num(x.high)+"</strong></div>");
    list("zones",d.supply_demand,x=>'<div class="evidence-row"><span>'+esc(x.type)+"</span><strong>"+num(x.low)+"–"+num(x.high)+"</strong></div>");
    list("patterns",d.candlestick_patterns,x=>'<div class="evidence-row"><span>'+esc(x.type)+"</span><strong>"+esc(x.bias)+"</strong></div>");
    set("account",acct.account_id||"NO ACTIVE ACCOUNT");set("accountType",acct.account_type||"—");set("currency",acct.currency||"—");set("balance",money(acct.balance,acct.currency));set("riskBudget",money(acct.risk_budget,acct.currency));set("stake",money(acct.recommended_stake,acct.currency));
    set("provenanceMarket",d.data_provenance?.broker||"—");set("provenanceCandles",d.data_provenance?.candle_source||"—");set("provenanceAnalysis","AlgoBot technical + AI pipeline");set("provenanceExecution","Broker only");
    drawChart(d.last_candles||[]); drawIndicators(d.last_candles||[]);
  }

  async function load(options={}){
    const generation=++A.loadGeneration;
    const symbol=$("symbol").value, tf=$("timeframe").value, limit=$("limit").value;
    if(!symbol){$("loadState").textContent="No active market is available.";return}
    if(A.data&&String(A.data.symbol||"")!==String(symbol)&&!A.cachedData){A.data=null;resetUnavailable();}
    $("loadState").textContent="Loading available market analysis…";
    const refreshAccount=options.refreshAccount===true;
    const refreshMarket=options.refreshMarket===true;
    const endpoint="/analysis/data/?symbol="+encodeURIComponent(symbol)+"&timeframe="+encodeURIComponent(tf)+"&limit="+limit+"&refresh="+(refreshMarket?"1":"0")+"&refresh_account="+(refreshAccount?"1":"0");
    try{
      const d=await request(endpoint);
      if(generation!==A.loadGeneration||symbol!==$("symbol").value||tf!==$("timeframe").value||limit!==$("limit").value)return;
      if(d.status==="error")throw new Error(d.message||"Analysis unavailable");
      render(d);A.cachedData=null;try{sessionStorage.setItem(cacheKey(symbol,tf,limit),JSON.stringify(d));}catch(_){}$("loadState").textContent="Updated "+new Date().toLocaleTimeString();
      // Show persisted research immediately, then refresh broker candles in the background
      // when the API marks the current snapshot stale. A refresh failure never upgrades stale data.
      if(!refreshMarket&&!options.backgroundRefresh&&d.data_provenance?.fresh!==true){void load({refreshMarket:true,backgroundRefresh:true,refreshAccount:false});}
    }catch(e){
      if(generation!==A.loadGeneration)return;
      // A first visit may have no persisted candles yet. Try the broker-backed
      // refresh once, without making the initial catalogue/data read serial.
      if(!refreshMarket&&!options.backgroundRefresh&&!A.cachedData&&Number(e?.status)===503){
        $("loadState").textContent="No saved candles yet · requesting broker-authoritative market data…";
        try{
          const refreshed=await request(endpoint.replace("&refresh=0","&refresh=1"));
          if(generation!==A.loadGeneration||symbol!==$("symbol").value||tf!==$("timeframe").value||limit!==$("limit").value)return;
          if(refreshed.status==="error")throw new Error(refreshed.message||"Broker candle refresh unavailable");
          render(refreshed);A.cachedData=null;try{sessionStorage.setItem(cacheKey(symbol,tf,limit),JSON.stringify(refreshed));}catch(_){}$("loadState").textContent="Updated "+new Date().toLocaleTimeString();return;
        }catch(refreshError){e=refreshError;if(generation!==A.loadGeneration)return;}
      }
      const fallback=A.cachedData||(A.data&&String(A.data.symbol||"")===String(symbol)?A.data:null);if(fallback){A.data=fallback;setHealth(false,"SAVED DATA · NOT LIVE");set("aFresh","SAVED DATA · NOT LIVE");const hero=$("heroFeedState");if(hero)hero.textContent="Current analysis unavailable · saved data shown";$("loadState").textContent=(e?.message||"Analysis unavailable")+" · saved data is not live";return;}
      A.data=null;
      resetUnavailable();
      $("loadState").textContent=e?.message||"Analysis unavailable";setHealth(false,"UNAVAILABLE");
      set("aResearchState","UNAVAILABLE");set("aBrokerState","UNAVAILABLE");set("aPrice","—");set("aSignal","UNAVAILABLE");set("aTechnical","Technical score —");set("aFresh","DATA UNAVAILABLE");set("liveQuote","UNAVAILABLE");set("liveQuoteAge","Live quote freshness unavailable");set("liveQuoteSource","—");set("validationState","UNAVAILABLE");set("validationDirection","WAIT");set("validationExpiry","—");set("noLookAhead","UNCONFIRMED");const heroState=$("heroFeedState");if(heroState)heroState.textContent="Market feed unavailable";const pulse=document.querySelector(".status-pulse");if(pulse)pulse.classList.remove("is-live");
      set("marketState","UNAVAILABLE");set("marketSource","—");set("marketAge","—");set("candleCount","—");
      set("liveQuote","UNAVAILABLE");set("liveQuoteAge","—");set("liveQuoteSource","—");
      set("gateState","BLOCKED");set("gateReason","Fresh analysis evidence could not be confirmed.");
      list("marketOverviewRows",[],()=>"", "No verified market data available.");
      list("predictionRows",[],()=>"", "No verified AI prediction is available.");
      list("sentimentNewsRows",[],()=>"", "No verified sentiment or news feed is available.");
      set("keyCurrentPrice","—");set("resistance1","—");set("resistance2","—");set("support1","—");set("support2","—");
      set("account","NO VERIFIED ACCOUNT CONTEXT");set("accountType","—");set("currency","—");set("balance","—");set("riskBudget","—");set("stake","—");
      drawChart([]); drawIndicators([]);
    }
  }
  async function markets(){
    const select=$("symbol");
    try{const node=$("analysis-markets-data");const bootstrapped=node?JSON.parse(node.textContent||"[]"):[];if(Array.isArray(bootstrapped)&&bootstrapped.length)A.markets=bootstrapped;}catch(_){}
    if(!A.markets.length){try{const d=await request("/analysis/markets/");A.markets=Array.isArray(d.markets)?d.markets:[];}catch(e){$("loadState").textContent=e.message||"Markets unavailable";}}
    if(!select)return;
    select.innerHTML=A.markets.map(m=>'<option value="'+esc(m.symbol)+'">'+esc(marketName(m))+'</option>').join("");
    if(!A.markets.length){select.innerHTML='<option value="">No markets available</option>';$("loadState").textContent="No active markets are available.";setHealth(false,"UNAVAILABLE");return;}
    const requested=new URLSearchParams(location.search).get("symbol");const preferred=[requested,A.markets[0].symbol].find(value=>A.markets.some(m=>m.symbol===value));select.value=preferred||A.markets[0].symbol;updateSelectedMarketIcon();
    const tf=$("timeframe").value,limit=$("limit").value;const restored=restoreCached(select.value,tf,limit);
    // Start the broker refresh immediately when a saved snapshot is already visible.
    void load(restored?{refreshMarket:true,backgroundRefresh:true,refreshAccount:false}:{});
  }
  async function prepare(){
    if(!A.data)return;
    $("prepareState").textContent="Revalidation is performed on the selected Analysis data. Open Terminal only after review.";
    if(A.data.execution_gate?.ready){window.location.href="/trading/?symbol="+encodeURIComponent(A.data.symbol)+"&timeframe="+encodeURIComponent(A.data.timeframe)+"&direction="+encodeURIComponent(A.data.trade_spec?.direction||"");return}
    $("prepareState").textContent="BLOCKED: "+(A.data.execution_gate?.reason||"Execution gates are not confirmed.");
  }
  function boot(){
    ["symbol","timeframe","limit"].forEach(id=>$(id)?.addEventListener("change",()=>{updateSelectedMarketIcon();const restored=restoreCached($("symbol").value,$("timeframe").value,$("limit").value);void load(restored?{refreshMarket:true,backgroundRefresh:true,refreshAccount:false}:{});}));
    $("refresh")?.addEventListener("click",()=>load({refreshAccount:true,refreshMarket:true}));$("prepare")?.addEventListener("click",prepare);
    $("auto")?.addEventListener("change",()=>{clearInterval(A.timer);if($("auto").checked)A.timer=setInterval(()=>load({refreshAccount:false}),30000)});
    window.addEventListener("resize",()=>{if(A.data){drawChart(A.data.last_candles||[]);drawIndicators(A.data.last_candles||[])}});markets();
  }
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",boot,{once:true});else boot();
})();