import React, {useEffect, useState} from 'react';
import {Activity, ShieldCheck, RadioTower, BrainCircuit, Power, RefreshCw, AlertTriangle, Bot, Globe, LockKeyhole, FileSpreadsheet, ListFilter, LayoutDashboard} from 'lucide-react';
import {Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis} from 'recharts';

const API='http://127.0.0.1:8000';
const TABS=[['overview','Overview'],['trades','Trades'],['suggestions','Suggested trades'],['reports','Reports'],['intelligence','Intelligence'],['audit','Audit ledger']];
const MARKET_DATE_FORMATTER=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Kolkata'});

export default function App(){
  const [tab,setTab]=useState('overview');
  const [status,setStatus]=useState({});
  const [account,setAccount]=useState({});
  const [orders,setOrders]=useState([]);
  const [candidates,setCandidates]=useState([]);
  const [ticks,setTicks]=useState({});
  const [context,setContext]=useState('');
  const [research,setResearch]=useState('');
  const [intelSources,setIntelSources]=useState([]);
  const [analysis,setAnalysis]=useState(null);
  const [analysisClass,setAnalysisClass]=useState('both');
  const [analysisRegion,setAnalysisRegion]=useState('global');
  const [analysisInstruments,setAnalysisInstruments]=useState('');
  const [analysisHorizon,setAnalysisHorizon]=useState('swing');
  const [analysisQuestion,setAnalysisQuestion]=useState('Assess current market evidence, regime, risks and conditional scenarios.');
  const [lossLimit,setLossLimit]=useState('');
  const [pending,setPending]=useState({});
  const isPending=(key)=>Boolean(pending[key]);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [showLiveConfirm,setShowLiveConfirm]=useState(false);
  const [liveConfirmation,setLiveConfirmation]=useState('');
  const [audit,setAudit]=useState([]);
  const [theme,setTheme]=useState(()=>localStorage.getItem('nse-theme')||'dark');
  const [reportWindow,setReportWindow]=useState('month');
  const [reportRegion,setReportRegion]=useState('');
  const [reportAsset,setReportAsset]=useState('');
  const [reportCurrency,setReportCurrency]=useState('INR');
  const [reportSymbol,setReportSymbol]=useState('');
  const [reportFrom,setReportFrom]=useState('');
  const [reportTo,setReportTo]=useState('');
  const [tradeFilters,setTradeFilters]=useState({symbol:'',status:'',side:'',asset_class:'',market_region:'',exchange:'',date_from:'',date_to:''});
  const [candidateFilters,setCandidateFilters]=useState({symbol:'',status:'',side:'',confidence:'',asset_class:'',market_region:'',exchange:'',date_from:'',date_to:''});
  const [auditFilters,setAuditFilters]=useState({q:'',event_type:'',asset_class:'',market_region:'',date_from:'',date_to:''});

  async function call(path,method='GET',body){
    const r=await fetch(API+path,{method,headers:{'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{})});
    const contentType=r.headers.get('content-type')||'';
    const result=contentType.includes('application/json')?await r.json():await r.text();
    if(!r.ok) throw Error(result?.detail||result||'Request failed');
    return result;
  }
  async function refresh(){
    try{
      const [s,a,o,m,i,ev,cs]=await Promise.all([
        call('/api/status'),call('/api/account'),call('/api/orders'),call('/api/market/latest'),
        call('/api/intelligence/latest'),call('/api/audit/events?limit=500'),call('/api/candidates')
      ]);
      setStatus(s);setAccount(a);setOrders(o);setTicks(m.ticks||{});
      setResearch(i.brief||'');setIntelSources(i.sources||[]);setAudit(ev||[]);setCandidates(cs||[]);
    }catch(e){setError('Backend not reachable. Start FastAPI on port 8000.')}
  }
  useEffect(()=>{document.documentElement.dataset.theme=theme;localStorage.setItem('nse-theme',theme)},[theme]);
  useEffect(()=>{refresh();const t=setInterval(refresh,5000);return()=>clearInterval(t)},[]);

  async function action(key, fn, success){
    setPending(current=>({...current,[key]:true}));setError('');setNotice('');
    try{const result=await fn();setNotice(typeof success==='function'?success(result):success);await refresh();return result}
    catch(e){setError(e.message);return null}
    finally{setPending(current=>{const next={...current};delete next[key];return next})}
  }
  const startBot=()=>action('bot',()=>call('/api/bot','POST',{enabled:true}),r=>r.message||'Agent started.');
  const stopBot=()=>action('bot',()=>call('/api/bot','POST',{enabled:false}),'Agent stopped. Autonomous permission revoked.');
  const engageKill=()=>action('kill',()=>call('/api/kill-switch','POST',{}),'Emergency kill switch engaged.');
  const resetKill=()=>action('kill',()=>call('/api/kill-switch/reset','POST',{}),r=>r.message||'Kill switch reset; agent remains stopped.');
  const changeMode=(mode)=>{
    if(mode==='full'&&(!lossLimit||Number(lossLimit)<=0)){setNotice('Set a positive daily loss limit below before enabling full mode.');return}
    return action('mode',()=>call('/api/bot/mode','POST',{mode,max_daily_loss:mode==='full'?Number(lossLimit):null}),r=>r.message||'Operating mode updated.');
  };
  const selectPaperMode=()=>action('execution',()=>call('/api/execution-mode','POST',{mode:'PAPER'}),r=>r.message||'Paper trading selected.');
  const selectLiveMode=async()=>{
    const result=await action('execution',()=>call('/api/execution-mode','POST',{mode:'LIVE',confirmation:liveConfirmation}),r=>r.message||'Live mode selected.');
    if(result){setShowLiveConfirm(false);setLiveConfirmation('')}
  };
  const connectFeed=()=>action('feed',()=>call('/api/market/connect','POST',{}),'Market feed connection requested.');
  const connectGlobalFeed=()=>action('global-feed',()=>call('/api/market/global/connect','POST',{}),'Twelve Data global feed connection requested.');
  const resetDailyLock=()=>action('daily-lock',()=>call('/api/daily-lock/reset','POST',{}),r=>r.reset?'Daily loss lock reset. Autonomy remains off.':r.message);
  const resetGlobalDailyLock=()=>action('global-daily-lock',()=>call('/api/global-daily-lock/reset','POST',{}),r=>r.reset?'USD daily loss lock reset. Autonomy remains as configured.':r.message);
  const decideCandidate=(id,decision)=>action(`candidate:${id}`,()=>call(`/api/candidates/${id}/decision`,'POST',{decision,reason:`${decision} from dashboard`}),`Suggestion ${decision.toLowerCase()}.`);
  const verifyAudit=()=>action('audit',()=>call('/api/audit/verify'),r=>r.valid?`Audit chain verified: ${r.verified_events} events.`:`Audit chain integrity failure at sequence ${r.failed_seq}.`);

  async function refreshIntelligence(){
    await action('intelligence',()=>call('/api/intelligence/refresh','POST',{extra_context:context}),r=>{
      setResearch(r.brief||'');setIntelSources(r.sources||[]);
      return r.sources?.length?`Intelligence updated with ${r.sources.length} source references.`:'Intelligence updated, but no source references were returned; readiness remains blocked.';
    });
  }
  async function runResearch(){
    setPending(current=>({...current,research:true}));setError('');setNotice('Running provider-backed research with source checks…');
    try{
      const result=await call('/api/research','POST',{
        market_context:context,question:analysisQuestion,asset_class:analysisClass,region:analysisRegion,
        instruments:analysisInstruments.split(',').map(x=>x.trim()).filter(Boolean),horizon:analysisHorizon
      });
      setAnalysis(result);setNotice(result.sources?.length?`Research complete with ${result.sources.length} sources.`:'Research returned no structured source references.');
    }catch(e){setError(e.message)}finally{setPending(current=>{const next={...current};delete next.research;return next})}
  }

  const ready=status.readiness?.ready;
  const tickRows=Object.entries(ticks).map(([symbol,v])=>({symbol,ltp:v.ltp,received:v.received_at}));
  const filteredTrades=orders.filter(o=>(!tradeFilters.symbol||String(o.symbol||'').toLowerCase().includes(tradeFilters.symbol.toLowerCase()))&&(!tradeFilters.status||o.status===tradeFilters.status)&&(!tradeFilters.side||o.side===tradeFilters.side)&&(!tradeFilters.asset_class||String(o.asset_class||'equity').toLowerCase()===tradeFilters.asset_class)&&(!tradeFilters.market_region||String(o.market_region||'India').toLowerCase()===tradeFilters.market_region.toLowerCase())&&(!tradeFilters.exchange||String(o.exchange||'').toLowerCase().includes(tradeFilters.exchange.toLowerCase()))&&(!tradeFilters.date_from||String(o.created_at||'').slice(0,10)>=tradeFilters.date_from)&&(!tradeFilters.date_to||String(o.created_at||'').slice(0,10)<=tradeFilters.date_to));
  const filteredCandidates=candidates.filter(c=>(!candidateFilters.symbol||String(c.symbol||'').toLowerCase().includes(candidateFilters.symbol.toLowerCase()))&&(!candidateFilters.status||c.status===candidateFilters.status)&&(!candidateFilters.side||c.side===candidateFilters.side)&&(candidateFilters.confidence===''||Number(c.confidence)>=Number(candidateFilters.confidence))&&(!candidateFilters.asset_class||String(c.asset_class||'equity').toLowerCase()===candidateFilters.asset_class)&&(!candidateFilters.market_region||String(c.market_region||'India').toLowerCase()===candidateFilters.market_region.toLowerCase())&&(!candidateFilters.exchange||String(c.exchange||'').toLowerCase().includes(candidateFilters.exchange.toLowerCase()))&&(!candidateFilters.date_from||String(c.created_at||'').slice(0,10)>=candidateFilters.date_from)&&(!candidateFilters.date_to||String(c.created_at||'').slice(0,10)<=candidateFilters.date_to));
  const filteredAudit=audit.filter(e=>{const p=e.payload||{};const nested=p.candidate||p.signal||p.order||{};const category=p.asset_class||nested.asset_class||((p.symbol||nested.symbol)?'equity':'');const region=p.market_region||nested.market_region||((p.symbol||nested.symbol)?'India':'');return (!auditFilters.event_type||String(e.event_type||'').toLowerCase().includes(auditFilters.event_type.toLowerCase()))&&(!auditFilters.q||`${e.entity_id||''} ${e.event_type||''} ${JSON.stringify(p)}`.toLowerCase().includes(auditFilters.q.toLowerCase()))&&(!auditFilters.asset_class||String(category).toLowerCase()===auditFilters.asset_class)&&(!auditFilters.market_region||String(region).toLowerCase()===auditFilters.market_region.toLowerCase())&&(!auditFilters.date_from||String(e.occurred_at||'').slice(0,10)>=auditFilters.date_from)&&(!auditFilters.date_to||String(e.occurred_at||'').slice(0,10)<=auditFilters.date_to)});
  const isBotOn=!!status.bot_enabled;
  const isKillActive=!!status.kill_switch;
  const paperEngine=status.paper_strategy_engine||{};
  const mode=status.operating_mode==='FULL'?'full':'semi';
  const reportNow=new Date();
  const reportStart=new Date(reportNow);
  if(reportWindow==='day') reportStart.setHours(0,0,0,0);
  else if(reportWindow==='week'){reportStart.setDate(reportStart.getDate()-((reportStart.getDay()+6)%7));reportStart.setHours(0,0,0,0)}
  else {reportStart.setDate(1);reportStart.setHours(0,0,0,0)}
  if(reportFrom) reportStart.setTime(new Date(`${reportFrom}T00:00:00`).getTime());
  const reportEnd=reportTo?new Date(`${reportTo}T23:59:59.999`):reportNow;
  const reportTrades=orders.filter(o=>{
    if(o.status!=='CLOSED'||typeof o.realised_pnl!=='number')return false;
    const closedAt=new Date(o.closed_at||o.created_at);
    return closedAt>=reportStart&&closedAt<=reportEnd&&String(o.currency||'INR')===reportCurrency&&(!reportRegion||String(o.market_region||'India')===reportRegion)&&(!reportAsset||String(o.asset_class||'equity')===reportAsset)&&(!reportSymbol||String(o.symbol||'').toLowerCase().includes(reportSymbol.toLowerCase()));
  });
  const winCount=reportTrades.filter(o=>o.realised_pnl>0).length;
  const lossCount=reportTrades.filter(o=>o.realised_pnl<0).length;
  const evenCount=reportTrades.length-winCount-lossCount;
  const reportPnl=reportTrades.reduce((sum,o)=>sum+o.realised_pnl,0);
  const reportByDay=Object.values(reportTrades.reduce((acc,o)=>{const d=MARKET_DATE_FORMATTER.format(new Date(o.closed_at||o.created_at));if(!d)return acc;acc[d]??={date:d,pnl:0,trades:0};acc[d].pnl+=o.realised_pnl;acc[d].trades++;return acc;},{})).sort((a,b)=>a.date.localeCompare(b.date));
  const outcomes=[{name:'Wins',value:winCount,color:'#2dd4a3'},{name:'Losses',value:lossCount,color:'#fb7185'},{name:'Breakeven',value:evenCount,color:'#9ca3af'}].filter(x=>x.value);

  return <div className="shell">
    <div className="sticky-shell">
      <header className="topbar">
        <div className="agent-controls">
          <button onClick={isBotOn?stopBot:startBot} disabled={isPending('bot')||(!isBotOn&&isKillActive)} className={isBotOn?'secondary':''}>
            <Power size={15}/>{isBotOn?'Stop agent':'Start agent'}
          </button>
          <button onClick={isKillActive?resetKill:engageKill} disabled={isPending('kill')} className={isKillActive?'danger':'danger'}>
            <ShieldCheck size={15}/>{isKillActive?'Reset kill switch':'Kill switch'}
          </button>
        </div>
        <div className="brand"><div className="eyebrow">PAPER / LIVE MODE SELECTOR · SOURCE-BACKED RESEARCH</div><h1>Trabot</h1></div>
        <div className="execution-switch" aria-label="Trading execution mode">
          <span className="small muted">Execution</span>
          <button className="exec-active" onClick={selectPaperMode} disabled={isPending('execution')||status.execution_mode==='PAPER'}>Paper money</button>
          <button className={status.execution_mode==='LIVE_SELECTED'?'exec-live-selected':'exec-live'} onClick={()=>{setLiveConfirmation('');setShowLiveConfirm(true)}} disabled={isPending('execution')}>{status.execution_mode==='LIVE_SELECTED'?'Live mode · routing OFF':'Real money · routing OFF'}</button>
        </div>
        <div className="header-right">
          <button className="secondary" onClick={()=>setTheme(theme==='dark'?'contrast':theme==='contrast'?'light':'dark')}>{theme==='dark'?'◐ Contrast':theme==='contrast'?'☀ Light':'● Dark'}</button>
          <span className={'pill '+(isKillActive?'red-pill':ready?'green':'amber')}>{isKillActive?'KILL SWITCH ACTIVE':ready?'READY':isBotOn?'CHECKS PENDING':'AGENT STOPPED'}</span>
        </div>
      </header>
      <nav className="tab-bar" aria-label="Dashboard sections">
        {TABS.map(([id,label])=><button key={id} className={tab===id?'tab active':'tab'} onClick={()=>setTab(id)}>{label}</button>)}
      </nav>
    </div>
    {error&&<div className="error"><AlertTriangle size={16}/>{error}</div>}
    {notice&&<div className="notice">{notice}</div>}
    {showLiveConfirm&&<div className="modal-backdrop" style={{position:'fixed',inset:0,zIndex:50,background:'#030712c9',display:'grid',placeItems:'center',padding:18}}><section className="panel confirm-modal" style={{width:'min(560px, 100%)',boxShadow:'0 25px 80px #0008'}} role="dialog" aria-modal="true" aria-labelledby="live-confirm-title"><h2 id="live-confirm-title">Live trading is locked in this build</h2><p className="muted">Type <b>I AGREE</b> to record a LIVE mode selection. This confirmation does not enable live orders. Broker order-state tracking, fill reconciliation, restart recovery, and independent safety validation are still required. Selecting LIVE blocks paper and sandbox orders until you switch back.</p><input style={{width:'100%',margin:'10px 0 16px',padding:12}} aria-label="Confirmation phrase" value={liveConfirmation} onChange={e=>setLiveConfirmation(e.target.value)} placeholder="Type I AGREE exactly"/><div className="actions" style={{justifyContent:'flex-end'}}><button className="danger" onClick={selectLiveMode} disabled={isPending('execution')||liveConfirmation!=='I AGREE'}>Confirm LIVE mode selection</button><button className="secondary" onClick={()=>setShowLiveConfirm(false)}>Cancel</button></div></section></div>}

    {tab==='overview'&&<>
      <section className="stats">
        <Metric title="Starting capital" value={'₹'+(account.starting_capital||10000).toLocaleString('en-IN')}/>
        <Metric title="Daily P&L (incl. open)" value={'₹'+(account.daily_pnl||0).toLocaleString('en-IN')}/>
        <Metric title="Open positions" value={account.open_positions??0}/>
        <Metric title="Orders in session" value={account.orders_today??0}/>
      </section>
      <section className="panel control-panel">
        <div className="panel-title"><Bot/> Agent controls & operating mode</div>
        <div className="control-row">
          <div><b>Master agent: {isBotOn?'ON':'OFF'}</b><p className="muted">Master start/stop is independent of the emergency kill switch and the semi/full mode selection.</p></div>
          <div className="mode-control">
            <label>Operating mode<select value={mode} onChange={e=>changeMode(e.target.value)} disabled={isPending('mode')||!isBotOn||isKillActive}>
              <option value="semi">Semi-autonomous · human approves</option><option value="full">Full autonomy · paper permission</option>
            </select></label>
            {mode==='full'&&<span className="pill amber">DAILY LOSS LIMIT ₹{status.autonomous_daily_loss_limit??'—'}</span>}
          </div>
        </div>
        <div className="autonomy-form"><label>India paper daily loss limit (₹)<input type="number" min="1" step="1" value={lossLimit} onChange={e=>setLossLimit(e.target.value)} placeholder="Required for full mode"/></label><button onClick={()=>changeMode('full')} disabled={isPending('mode')||!isBotOn||isKillActive||!ready||!lossLimit||Number(lossLimit)<=0}>Apply full-autonomy limit</button></div>
        <div className="readiness"><div className={'ready-dot '+(ready?'on':'')}></div><div><b>Readiness: {status.readiness?.status||'CHECKING'}</b><p className="muted">Full mode requires a fresh NSE or configured global-market quote, source-backed intelligence, a clear kill switch and a healthy audit ledger.</p></div></div>
        <div className="checks">{Object.entries(status.readiness?.checks||{}).map(([k,v])=><span className={'check '+(v?'ok':'pending')} key={k}>{v?'✓':'○'} {k.replaceAll('_',' ')}</span>)}</div>
        <div className="control-row lock-row"><div><b>Daily loss lock: {status.daily_loss_lock?'ACTIVE':'Clear'}</b><p className="muted small">Resetting the daily lock preserves P&amp;L and never re-enables autonomy or releases the kill switch.</p></div><button className="secondary" onClick={resetDailyLock} disabled={!status.daily_loss_lock||isPending('daily-lock')}>Reset daily loss lock</button></div>
        <p className="muted small">Autonomous rule signals and paper exits run only from configured NSE cash-equity feed instruments. Live order routing remains locked pending broker and safety validation.</p>
      </section>
      <section className="panel">
        <div className="panel-title"><Bot/> Autonomous paper engine</div>
        <div className="kv"><span>Engine</span><b>{paperEngine.status||'STARTING'} · paper only</b></div>
        <div className="kv"><span>Eligible NSE equities</span><b>{paperEngine.eligible_equity_instruments??0}</b></div>
        <div className="kv"><span>Strategy warm-up</span><b>{paperEngine.minimum_warmup_bars??30} completed 1m bars per instrument</b></div>
        <div className="kv"><span>Rules</span><b>{(paperEngine.strategies||[]).join(' · ')||'Loading'}</b></div>
        <p className="muted">{paperEngine.last_action||'Waiting for live market ticks.'}</p>
        {paperEngine.error&&<p className="error">Paper engine: {paperEngine.error}</p>}
        {!!paperEngine.stale_open_positions?.length&&<p className="error">Open paper positions are not receiving fresh exit quotes: {paperEngine.stale_open_positions.join(', ')}. The simulator will not fabricate an exit price.</p>}
        {!paperEngine.eligible_equity_instruments&&<p className="error">Current default subscriptions are Nifty indices. Add NSE_EQ stock instrument keys to UPSTOX_INSTRUMENT_KEYS in backend/.env and restart FastAPI. Index quotes cannot be submitted as stock orders.</p>}
        <p className="muted small">Signal scores are rule-strength labels, not win probabilities. This paper simulator does not model fees, taxes, slippage, exchange holidays, or broker fills.</p>
      </section>
      <section className="panel">
        {(()=>{const gf=status.global_market_feed||{}, ge=status.global_paper_engine||{}, ga=ge.account||{};return <>
          <div className="panel-title"><Globe/> Global markets paper engine <span className={'pill '+(gf.connected?'green':'amber')}>{gf.status||'NOT CONFIGURED'}</span><button className="secondary" onClick={connectGlobalFeed} disabled={isPending('global-feed')||gf.status==='CONNECTING'}>Connect Twelve Data</button></div>
          <p className="muted">Twelve Data quote feed · US equities trade regular NYSE/Nasdaq hours; FX and spot commodity pairs use a conservative 24/5 session approximation. Instruments and venue holidays vary. All orders stay in Trabot’s local paper simulator; live routing is disabled.</p>
          {gf.error&&<p className="error">{gf.error}</p>}
          <div className="kv"><span>Paper engine</span><b>{ge.status||'STARTING'} · USD paper only</b></div>
          <div className="kv"><span>Global full-autonomy permission</span><b>{ge.autonomous_enabled?'ON · USD risk controls active':'OFF · suggestions only'}</b></div>
          <div className="kv"><span>Configured instruments</span><b>{(gf.symbols||[]).map(x=>x.symbol).join(', ')||'None'}</b></div>
          <div className="kv"><span>Strategy warm-up</span><b>{ge.warmup_bars||30} completed 1m bars per instrument</b></div>
          <div className="kv"><span>USD paper balance</span><b>${Number(ga.starting_capital||0).toLocaleString('en-US')}</b></div>
          <div className="kv"><span>USD daily P&amp;L · realised + open</span><b>${Number(ga.daily_pnl||0).toFixed(2)}</b></div>
          <div className="kv"><span>Open USD positions / orders today</span><b>{ga.open_positions??0} / {ga.orders_today??0}</b></div>
          <div className="kv"><span>USD risk per trade / daily loss lock</span><b>${Number(ga.max_risk_per_trade||0).toFixed(2)} / ${Number(ga.daily_loss_limit||0).toFixed(2)} · {ga.daily_loss_lock?'LOCKED':'Clear'}</b></div>
          {ga.daily_loss_lock&&<div className="control-row"><span className="muted small">Resetting the USD lock preserves P&amp;L and does not change the agent mode.</span><button className="secondary" onClick={resetGlobalDailyLock} disabled={isPending('global-daily-lock')}>Reset USD daily loss lock</button></div>}
          <div className="kv"><span>Strategies</span><b>{(ge.strategies||[]).join(' · ')}</b></div>
          <p className="muted">{ge.last_action||'Waiting for Twelve Data quotes.'}</p>
          {ge.error&&<p className="error">Global paper engine: {ge.error}</p>}
          {!!ga.stale_open_positions?.length&&<p className="error">Exit monitoring is waiting for fresh quotes on: {ga.stale_open_positions.join(', ')}. The simulator will not fabricate an exit price.</p>}
          {!gf.configured&&<p className="muted small">Set TWELVE_DATA_API_KEY and opt-in symbols in backend/.env (TWELVE_DATA_US_EQUITIES, TWELVE_DATA_FOREX, TWELVE_DATA_COMMODITIES), then restart FastAPI. Streaming and real-time commodity access are plan- and symbol-dependent; trial plans may limit subscriptions. The scanner needs 30 completed real-time one-minute bars before it can suggest a setup.</p>}
          <p className="muted small">FX is generally open 24 hours a day, five days a week, not 24/7. Many commodity markets have daily maintenance breaks and holiday closures; this first paper version requires fresh provider quotes and uses a broad 24/5 window for configured FX/spot-commodity pairs. No future or overnight quote is synthesized.</p>
        </>})()}
      </section>
      <section className="grid">
        <div className="panel"><div className="panel-title"><RadioTower/> NSE market feed <button onClick={connectFeed} disabled={isPending('feed')}>Connect feed</button></div><p className="muted">Upstox V3 &middot; Feed status: {status.feed_status||'CHECKING'} &middot; {status.feed_instrument_count||0} instrument keys.</p>{status.feed_error&&<p className="error">{status.feed_error}</p>}{!status.feed_token_configured&&<p className="muted">To connect: complete Upstox OAuth, place the current token in backend/.env as UPSTOX_ACCESS_TOKEN, then restart FastAPI. Set subscriptions with UPSTOX_INSTRUMENT_KEYS. The feed starts automatically once both are configured.</p>}
          <table><thead><tr><th>Instrument key</th><th>Last price</th><th>Received (UTC)</th></tr></thead><tbody>{tickRows.length?tickRows.map(x=><tr key={x.symbol}><td>{x.symbol}</td><td>{x.ltp}</td><td>{x.received}</td></tr>):<tr><td colSpan="3">No ticks received yet</td></tr>}</tbody></table>
        </div>
        <div className="panel"><div className="panel-title"><ShieldCheck/> Safety & provider</div>
          <div className="kv"><span>Execution mode</span><b>{status.execution_mode==='LIVE_SELECTED'?'LIVE SELECTED · ROUTING OFF':'Paper money'}</b></div><div className="kv"><span>Live orders</span><b className="red">Unavailable in this build</b></div>
          <div className="kv"><span>Live trading switch</span><button type="button" className="exec-locked" role="switch" aria-checked="false" disabled title="Live order routing is not implemented in this build">OFF · LOCKED</button></div>
          <div className="kv"><span>AI provider</span><b>{status.ai_provider||'Not configured'}</b></div><div className="kv"><span>Model</span><b>{status.ai_model||'Not configured'}</b></div>
          <div className="kv"><span>API key</span><b>{status.ai_configured?'Configured':'Missing'}</b></div><div className="kv"><span>Web search</span><b>{status.ai_web_search_enabled?'Requested':'Disabled'}</b></div>
        </div>
      </section>
      </>}
    {tab==='intelligence'&&<>
      <section className="panel research"><div className="panel-title"><Globe/> Global geopolitics & market intelligence <button onClick={refreshIntelligence} disabled={isPending('intelligence')||status.intelligence_status==='UPDATING'}>{status.intelligence_status==='UPDATING'?'Refreshing...':'Refresh intelligence'}</button></div>
        <p className="muted">The background worker refreshes the brief automatically every {status.intelligence_refresh_interval_minutes||30} minutes. Search provider: {status.research_search_provider||'native'}; worker status: {status.intelligence_worker_status||'STARTING'}. SearXNG runs as a separate Docker service; keep it running for external web evidence. The field below is optional and treated as an unverified lead.</p>{status.intelligence_worker_error&&<p className="error">Background research worker: {status.intelligence_worker_error}</p>}
        <textarea value={context} onChange={e=>setContext(e.target.value)} placeholder="Optional additional context, watchlist, or specific question…" rows="3"/>
        {research?<pre className="research-output">{research}</pre>:<p className="muted">No intelligence brief yet. Refresh to create a source-backed brief.</p>}
        {intelSources.length>0&&<ul className="source-list">{intelSources.map(s=><li key={s.url}><a href={s.url} target="_blank" rel="noreferrer">{s.title}</a></li>)}</ul>}
        <div className="muted small">Last refresh: {status.readiness?.intelligence_last_update||'Never'} · Provider: {status.ai_provider||'unconfigured'}</div>
      </section>
      <section className="panel analysis-panel">
        <div className="panel-title"><BrainCircuit/> Multi-asset research</div>
        <div className="analysis-form">
          <label>Asset class<select value={analysisClass} onChange={e=>setAnalysisClass(e.target.value)}><option value="both">Equities, commodities & currencies</option><option value="equities">Equities</option><option value="commodities">Commodities</option><option value="currencies">Currencies / FX</option></select></label>
          <label>Region or venues<input value={analysisRegion} onChange={e=>setAnalysisRegion(e.target.value)} placeholder="Global, US, India, LME…"/></label>
          <label>Instruments<input value={analysisInstruments} onChange={e=>setAnalysisInstruments(e.target.value)} placeholder="Optional, comma-separated symbols"/></label>
          <label>Horizon<select value={analysisHorizon} onChange={e=>setAnalysisHorizon(e.target.value)}><option value="intraday">Intraday</option><option value="swing">Swing</option><option value="position">Position</option></select></label>
        </div>
        <textarea value={analysisQuestion} onChange={e=>setAnalysisQuestion(e.target.value)} rows="2" placeholder="Research question…"/>
        <div className="control-row"><span className="muted small">Research is advisory only and never places an order.</span><button onClick={runResearch} disabled={isPending('research')||analysisQuestion.trim().length<5}>Run research</button></div>
        {analysis&&<><pre className="research-output">{analysis.research}</pre><div className="muted small">{analysis.provider} · {analysis.model} · {analysis.web_search_supported?'Search supported':'No search adapter'} · {analysis.generated_at}</div>{analysis.sources?.length>0&&<ul className="source-list">{analysis.sources.map(s=><li key={s.url}><a href={s.url} target="_blank" rel="noreferrer">{s.title}</a></li>)}</ul>}</>}
      </section>
    </>}

    {tab==='reports'&&<>
      <section className="panel">
        <div className="panel-title"><Activity/> Performance reports</div>
        <p className="muted small">Reports use closed trades and paper P&amp;L before broker fees, taxes, and slippage. No trade history is persisted across restarts in this build; empty results mean there is no recorded sample, not zero risk.</p>
        <div className="filter-bar report-filters">
          <label className="filter-field">Window<select value={reportWindow} onChange={e=>setReportWindow(e.target.value)}><option value="day">Today</option><option value="week">This week</option><option value="month">This month</option></select></label>
          <FilterSelect label="Market" value={reportRegion} onChange={setReportRegion} options={['India','US','Global']}/>
          <FilterSelect label="Currency" value={reportCurrency} onChange={setReportCurrency} options={['INR','USD']}/>
          <FilterSelect label="Asset class" value={reportAsset} onChange={setReportAsset} options={['equity','commodity','currency']}/>
          <FilterInput label="Symbol" value={reportSymbol} onChange={setReportSymbol}/>
          <label className="filter-field">From<input type="date" value={reportFrom} onChange={e=>setReportFrom(e.target.value)}/></label>
          <label className="filter-field">To<input type="date" value={reportTo} onChange={e=>setReportTo(e.target.value)}/></label>
        </div>
        <div className="stats report-stats">
          <Metric title="Closed trades" value={reportTrades.length}/>
          <Metric title="Win rate · sample only" value={reportTrades.length?`${((winCount/reportTrades.length)*100).toFixed(1)}%`:'—'}/>
          <Metric title={`Paper P&L before costs (${reportCurrency})`} value={`${reportCurrency==='USD'?'$':'₹'}${reportPnl.toLocaleString(reportCurrency==='USD'?'en-US':'en-IN',{maximumFractionDigits:2})}`}/>
          <Metric title="Wins / losses" value={`${winCount} / ${lossCount}`}/>
        </div>
        <div className="report-grid">
          <div className="chart-card"><h3>Daily paper P&amp;L before costs ({reportCurrency})</h3>{reportByDay.length?<ResponsiveContainer width="100%" height={280}><BarChart data={reportByDay}><CartesianGrid strokeDasharray="3 3" stroke="var(--border)"/><XAxis dataKey="date" tick={{fill:'var(--muted)',fontSize:11}}/><YAxis tick={{fill:'var(--muted)',fontSize:11}}/><Tooltip contentStyle={{background:'var(--surface)',borderColor:'var(--border)',color:'var(--text)'}}/><Legend/><Bar dataKey="pnl" name={`Paper P&L (${reportCurrency})`} fill="var(--chart-accent)" radius={[4,4,0,0]}/></BarChart></ResponsiveContainer>:<div className="chart-empty">Close paper trades to build the daily P&amp;L chart.</div>}</div>
          <div className="chart-card"><h3>Trade outcomes</h3>{outcomes.length?<ResponsiveContainer width="100%" height={280}><PieChart><Pie data={outcomes} dataKey="value" nameKey="name" innerRadius={58} outerRadius={92} paddingAngle={3} label>{outcomes.map(entry=><Cell key={entry.name} fill={entry.color}/>)}</Pie><Tooltip contentStyle={{background:'var(--surface)',borderColor:'var(--border)',color:'var(--text)'}}/><Legend/></PieChart></ResponsiveContainer>:<div className="chart-empty">No closed trades in this window.</div>}</div>
        </div>
      </section>
    </>}

    {tab==='trades'&&<section className="panel">
      <div className="panel-title"><Activity/> Trades</div>
      <p className="muted small">Trade and paper-order records currently held in this runtime session.</p>
      <p className="muted small">Use the filters to separate Indian and US equities, commodities, and currency/FX records. Exchange and market classification is stored with each new record.</p>
      <div className="filter-bar"><FilterInput label="Symbol" value={tradeFilters.symbol} onChange={v=>setTradeFilters({...tradeFilters,symbol:v})}/><FilterSelect label="Market" value={tradeFilters.market_region} onChange={v=>setTradeFilters({...tradeFilters,market_region:v})} options={['India','US','Global']}/><FilterSelect label="Category" value={tradeFilters.asset_class} onChange={v=>setTradeFilters({...tradeFilters,asset_class:v})} options={['equity','commodity','currency']}/><FilterInput label="Exchange" value={tradeFilters.exchange} onChange={v=>setTradeFilters({...tradeFilters,exchange:v})}/><FilterSelect label="Status" value={tradeFilters.status} onChange={v=>setTradeFilters({...tradeFilters,status:v})} options={['OPEN','CLOSED','SUBMITTED_TO_UPSTOX_SANDBOX']}/><FilterSelect label="Side" value={tradeFilters.side} onChange={v=>setTradeFilters({...tradeFilters,side:v})} options={['BUY','SELL']}/><label className="filter-field">From<input type="date" value={tradeFilters.date_from} onChange={e=>setTradeFilters({...tradeFilters,date_from:e.target.value})}/></label><label className="filter-field">To<input type="date" value={tradeFilters.date_to} onChange={e=>setTradeFilters({...tradeFilters,date_to:e.target.value})}/></label><button className="secondary" onClick={refresh}><RefreshCw size={14}/>Refresh</button></div>
      <table><thead><tr><th>Signal</th><th>Market</th><th>Category</th><th>Exchange</th><th>Symbol</th><th>Currency</th><th>Side</th><th>Entry</th><th>Stop</th><th>Target</th><th>Qty</th><th>Status</th><th>Mode</th></tr></thead><tbody>{filteredTrades.length?filteredTrades.map((o,i)=><tr key={o.signal_id||i}><td>{o.signal_id}</td><td>{o.market_region||'India'}</td><td>{o.asset_class||'equity'}</td><td>{o.exchange||'—'}</td><td>{o.symbol}</td><td>{o.currency||'INR'}</td><td>{o.side}</td><td>{o.entry}</td><td>{o.stop_loss}</td><td>{o.target}</td><td>{o.quantity}</td><td>{o.status}</td><td>{o.mode}</td></tr>):<tr><td colSpan="13">No trades match these filters.</td></tr>}</tbody></table>
    </section>}

    {tab==='suggestions'&&<section className="panel">
      <div className="panel-title"><BrainCircuit/> Suggested trades <button className="secondary" onClick={()=>window.location.assign(`${API}/api/candidates/export.xlsx`)}><FileSpreadsheet size={14}/>Download daily Excel log</button></div>
      <p className="muted small">Confidence is a research score, not a measured probability of success. Pending suggestions expire on stale quotes, stop/target invalidation, entry drift, or review TTL. One worksheet per local day is stored in backend/data/suggested_trades.xlsx.</p>
      <div className="filter-bar"><FilterInput label="Symbol" value={candidateFilters.symbol} onChange={v=>setCandidateFilters({...candidateFilters,symbol:v})}/><FilterSelect label="Market" value={candidateFilters.market_region} onChange={v=>setCandidateFilters({...candidateFilters,market_region:v})} options={['India','US','Global']}/><FilterSelect label="Category" value={candidateFilters.asset_class} onChange={v=>setCandidateFilters({...candidateFilters,asset_class:v})} options={['equity','commodity','currency']}/><FilterInput label="Exchange" value={candidateFilters.exchange} onChange={v=>setCandidateFilters({...candidateFilters,exchange:v})}/><FilterSelect label="Status" value={candidateFilters.status} onChange={v=>setCandidateFilters({...candidateFilters,status:v})} options={['PENDING','APPROVED','REJECTED','WATCHLIST','EXPIRED']}/><FilterSelect label="Side" value={candidateFilters.side} onChange={v=>setCandidateFilters({...candidateFilters,side:v})} options={['BUY','SELL']}/><label className="filter-field">Min score %<input type="number" min="0" max="100" value={candidateFilters.confidence} onChange={e=>setCandidateFilters({...candidateFilters,confidence:e.target.value})}/></label><label className="filter-field">From<input type="date" value={candidateFilters.date_from} onChange={e=>setCandidateFilters({...candidateFilters,date_from:e.target.value})}/></label><label className="filter-field">To<input type="date" value={candidateFilters.date_to} onChange={e=>setCandidateFilters({...candidateFilters,date_to:e.target.value})}/></label><button className="secondary" onClick={refresh}><RefreshCw size={14}/>Refresh</button></div>
      <table><thead><tr><th>Created</th><th>Market</th><th>Category</th><th>Exchange</th><th>Candidate</th><th>Side</th><th>Entry</th><th>Stop</th><th>Target</th><th>Score</th><th>Status</th><th>Expiry</th><th>Decision</th></tr></thead><tbody>{filteredCandidates.length?filteredCandidates.map(c=><tr key={c.candidate_id}><td>{c.created_at}</td><td>{c.market_region||'India'}</td><td>{c.asset_class||'equity'}</td><td>{c.exchange||'—'}</td><td>{c.symbol}<div className="muted small">{c.candidate_id}</div></td><td>{c.side}</td><td>{c.entry}</td><td>{c.stop_loss}</td><td>{c.target}</td><td>{c.confidence}%</td><td>{c.status}</td><td>{c.expiry_reason||'—'}</td><td>{c.status==='PENDING'?<div className="actions"><button onClick={()=>decideCandidate(c.candidate_id,'APPROVED')} disabled={isPending(`candidate:${c.candidate_id}`)||mode==='full'}>Approve</button><button className="secondary" onClick={()=>decideCandidate(c.candidate_id,'WATCHLIST')} disabled={isPending(`candidate:${c.candidate_id}`)||mode==='full'}>Watch</button><button className="danger" onClick={()=>decideCandidate(c.candidate_id,'REJECTED')} disabled={isPending(`candidate:${c.candidate_id}`)||mode==='full'}>Reject</button></div>:'—'}</td></tr>):<tr><td colSpan="13">No suggestions match these filters.</td></tr>}</tbody></table>
      {mode==='full'&&<p className="muted small">Manual suggestion decisions are disabled while full-autonomy permission is selected.</p>}
    </section>}

    {tab==='audit'&&<section className="panel">
      <div className="panel-title"><Activity/> Audit ledger <button className="secondary" onClick={verifyAudit}><ShieldCheck size={14}/>Verify chain</button></div>
      <p className="muted small">Append-only SQLite hash-chain events. Filters below apply to the latest 500 loaded entries.</p>
      <div className="filter-bar"><FilterInput label="Text or entity" value={auditFilters.q} onChange={v=>setAuditFilters({...auditFilters,q:v})}/><FilterInput label="Event type" value={auditFilters.event_type} onChange={v=>setAuditFilters({...auditFilters,event_type:v})}/><FilterSelect label="Market" value={auditFilters.market_region} onChange={v=>setAuditFilters({...auditFilters,market_region:v})} options={['India','US','Global']}/><FilterSelect label="Category" value={auditFilters.asset_class} onChange={v=>setAuditFilters({...auditFilters,asset_class:v})} options={['equity','commodity','currency']}/><label className="filter-field">From<input type="date" value={auditFilters.date_from} onChange={e=>setAuditFilters({...auditFilters,date_from:e.target.value})}/></label><label className="filter-field">To<input type="date" value={auditFilters.date_to} onChange={e=>setAuditFilters({...auditFilters,date_to:e.target.value})}/></label><button className="secondary" onClick={refresh}><RefreshCw size={14}/>Refresh</button></div>
      <table><thead><tr><th>Seq</th><th>Time (UTC)</th><th>Event</th><th>Entity</th><th>Details</th><th>Hash</th></tr></thead><tbody>{filteredAudit.length?filteredAudit.map(e=><tr key={e.event_id}><td>{e.seq}</td><td>{e.occurred_at}</td><td>{e.event_type}</td><td>{e.entity_id||'—'}</td><td className="audit-detail">{JSON.stringify(e.payload||{})}</td><td>{e.event_hash?.slice(0,14)}…</td></tr>):<tr><td colSpan="6">No audit events match these filters.</td></tr>}</tbody></table>
    </section>}

    <footer>Trabot · Paper trading only · Live order routing locked · Development prototype</footer>
  </div>
}

function Metric({title,value}){return <div className="metric"><span>{title}</span><strong>{value}</strong></div>}
function FilterInput({label,value,onChange}){return <label className="filter-field">{label}<input value={value} onChange={e=>onChange(e.target.value)} placeholder="All"/></label>}
function FilterSelect({label,value,onChange,options}){return <label className="filter-field">{label}<select value={value} onChange={e=>onChange(e.target.value)}><option value="">All</option>{options.map(option=><option key={option} value={option}>{option}</option>)}</select></label>}

