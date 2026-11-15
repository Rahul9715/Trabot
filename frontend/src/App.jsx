import React, {useEffect, useState} from 'react';
import {Activity, ShieldCheck, RadioTower, BrainCircuit, Power, RefreshCw, AlertTriangle, Bot, Globe, LockKeyhole, FileSpreadsheet, ListFilter, LayoutDashboard} from 'lucide-react';

const API='http://127.0.0.1:8000';
const TABS=[['overview','Overview'],['trades','Trades'],['suggestions','Suggested trades'],['audit','Audit ledger']];

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
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [showLiveConfirm,setShowLiveConfirm]=useState(false);
  const [liveConfirmation,setLiveConfirmation]=useState('');
  const [audit,setAudit]=useState([]);
  const [theme,setTheme]=useState(()=>localStorage.getItem('nse-theme')||'dark');
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

  async function action(fn, success){
    setBusy(true);setError('');setNotice('');
    try{const result=await fn();setNotice(typeof success==='function'?success(result):success);await refresh();return result}
    catch(e){setError(e.message);return null}finally{setBusy(false)}
  }
  const startBot=()=>action(()=>call('/api/bot','POST',{enabled:true}),r=>r.message||'Agent started.');
  const stopBot=()=>action(()=>call('/api/bot','POST',{enabled:false}),'Agent stopped. Autonomous permission revoked.');
  const engageKill=()=>action(()=>call('/api/kill-switch','POST',{}),'Emergency kill switch engaged.');
  const resetKill=()=>action(()=>call('/api/kill-switch/reset','POST',{}),r=>r.message||'Kill switch reset; agent remains stopped.');
  const changeMode=(mode)=>{
    if(mode==='full'&&(!lossLimit||Number(lossLimit)<=0)){setNotice('Set a positive daily loss limit below before enabling full mode.');return}
    return action(()=>call('/api/bot/mode','POST',{mode,max_daily_loss:mode==='full'?Number(lossLimit):null}),r=>r.message||'Operating mode updated.');
  };
  const selectPaperMode=()=>action(()=>call('/api/execution-mode','POST',{mode:'PAPER'}),r=>r.message||'Paper trading selected.');
  const selectLiveMode=async()=>{
    const result=await action(()=>call('/api/execution-mode','POST',{mode:'LIVE',confirmation:liveConfirmation}),r=>r.message||'Live mode selected.');
    if(result){setShowLiveConfirm(false);setLiveConfirmation('')}
  };
  const connectFeed=()=>action(()=>call('/api/market/connect','POST',{instrument_keys:['NSE_INDEX|Nifty 50','NSE_INDEX|Nifty Bank']}),'Market feed connection requested.');
  const resetDailyLock=()=>action(()=>call('/api/daily-lock/reset','POST',{}),r=>r.reset?'Daily loss lock reset. Autonomy remains off.':r.message);
  const decideCandidate=(id,decision)=>action(()=>call(`/api/candidates/${id}/decision`,'POST',{decision,reason:`${decision} from dashboard`}),`Suggestion ${decision.toLowerCase()}.`);
  const verifyAudit=()=>action(()=>call('/api/audit/verify'),r=>r.valid?`Audit chain verified: ${r.verified_events} events.`:`Audit chain integrity failure at sequence ${r.failed_seq}.`);

  async function refreshIntelligence(){
    await action(()=>call('/api/intelligence/refresh','POST',{extra_context:context}),r=>{
      setResearch(r.brief||'');setIntelSources(r.sources||[]);
      return r.sources?.length?`Intelligence updated with ${r.sources.length} source references.`:'Intelligence updated, but no source references were returned; readiness remains blocked.';
    });
  }
  async function runResearch(){
    setBusy(true);setError('');setNotice('Running provider-backed research with source checks…');
    try{
      const result=await call('/api/research','POST',{
        market_context:context,question:analysisQuestion,asset_class:analysisClass,region:analysisRegion,
        instruments:analysisInstruments.split(',').map(x=>x.trim()).filter(Boolean),horizon:analysisHorizon
      });
      setAnalysis(result);setNotice(result.sources?.length?`Research complete with ${result.sources.length} sources.`:'Research returned no structured source references.');
    }catch(e){setError(e.message)}finally{setBusy(false)}
  }

  const ready=status.readiness?.ready;
  const tickRows=Object.entries(ticks).map(([symbol,v])=>({symbol,ltp:v.ltp,received:v.received_at}));
  const filteredTrades=orders.filter(o=>(!tradeFilters.symbol||String(o.symbol||'').toLowerCase().includes(tradeFilters.symbol.toLowerCase()))&&(!tradeFilters.status||o.status===tradeFilters.status)&&(!tradeFilters.side||o.side===tradeFilters.side)&&(!tradeFilters.asset_class||String(o.asset_class||'equity').toLowerCase()===tradeFilters.asset_class)&&(!tradeFilters.market_region||String(o.market_region||'India').toLowerCase()===tradeFilters.market_region.toLowerCase())&&(!tradeFilters.exchange||String(o.exchange||'').toLowerCase().includes(tradeFilters.exchange.toLowerCase()))&&(!tradeFilters.date_from||String(o.created_at||'').slice(0,10)>=tradeFilters.date_from)&&(!tradeFilters.date_to||String(o.created_at||'').slice(0,10)<=tradeFilters.date_to));
  const filteredCandidates=candidates.filter(c=>(!candidateFilters.symbol||String(c.symbol||'').toLowerCase().includes(candidateFilters.symbol.toLowerCase()))&&(!candidateFilters.status||c.status===candidateFilters.status)&&(!candidateFilters.side||c.side===candidateFilters.side)&&(candidateFilters.confidence===''||Number(c.confidence)>=Number(candidateFilters.confidence))&&(!candidateFilters.asset_class||String(c.asset_class||'equity').toLowerCase()===candidateFilters.asset_class)&&(!candidateFilters.market_region||String(c.market_region||'India').toLowerCase()===candidateFilters.market_region.toLowerCase())&&(!candidateFilters.exchange||String(c.exchange||'').toLowerCase().includes(candidateFilters.exchange.toLowerCase()))&&(!candidateFilters.date_from||String(c.created_at||'').slice(0,10)>=candidateFilters.date_from)&&(!candidateFilters.date_to||String(c.created_at||'').slice(0,10)<=candidateFilters.date_to));
  const filteredAudit=audit.filter(e=>{const p=e.payload||{};const nested=p.candidate||p.signal||p.order||{};const category=p.asset_class||nested.asset_class||((p.symbol||nested.symbol)?'equity':'');const region=p.market_region||nested.market_region||((p.symbol||nested.symbol)?'India':'');return (!auditFilters.event_type||String(e.event_type||'').toLowerCase().includes(auditFilters.event_type.toLowerCase()))&&(!auditFilters.q||`${e.entity_id||''} ${e.event_type||''} ${JSON.stringify(p)}`.toLowerCase().includes(auditFilters.q.toLowerCase()))&&(!auditFilters.asset_class||String(category).toLowerCase()===auditFilters.asset_class)&&(!auditFilters.market_region||String(region).toLowerCase()===auditFilters.market_region.toLowerCase())&&(!auditFilters.date_from||String(e.occurred_at||'').slice(0,10)>=auditFilters.date_from)&&(!auditFilters.date_to||String(e.occurred_at||'').slice(0,10)<=auditFilters.date_to)});
  const isBotOn=!!status.bot_enabled;
  const isKillActive=!!status.kill_switch;
  const mode=status.operating_mode==='FULL'?'full':'semi';

  return <div className="shell">
    <div className="sticky-shell">
      <header className="topbar">
        <div className="agent-controls">
          <button onClick={isBotOn?stopBot:startBot} disabled={busy||(!isBotOn&&isKillActive)} className={isBotOn?'secondary':''}>
            <Power size={15}/>{isBotOn?'Stop agent':'Start agent'}
          </button>
          <button onClick={isKillActive?resetKill:engageKill} disabled={busy} className={isKillActive?'danger':'danger'}>
            <ShieldCheck size={15}/>{isKillActive?'Reset kill switch':'Kill switch'}
          </button>
        </div>
        <div className="brand"><div className="eyebrow">PAPER / LIVE MODE SELECTOR · SOURCE-BACKED RESEARCH</div><h1>Trabot</h1></div>
        <div className="execution-switch" aria-label="Trading execution mode">
          <span className="small muted">Execution</span>
          <button className="exec-active" onClick={selectPaperMode} disabled={busy||status.execution_mode==='PAPER'}>Paper money</button>
          <button className={status.execution_mode==='LIVE_SELECTED'?'exec-live-selected':'exec-live'} onClick={()=>{setLiveConfirmation('');setShowLiveConfirm(true)}} disabled={busy}>{status.execution_mode==='LIVE_SELECTED'?'Live selected':'Real money'}</button>
        </div>
        <div className="header-right">
          <button className="secondary" onClick={()=>setTheme(theme==='dark'?'light':'dark')}>{theme==='dark'?'☀ Light':'☾ Dark'}</button>
          <span className={'pill '+(isKillActive?'red-pill':ready?'green':'amber')}>{isKillActive?'KILL SWITCH ACTIVE':ready?'READY':isBotOn?'CHECKS PENDING':'AGENT STOPPED'}</span>
        </div>
      </header>
      <nav className="tab-bar" aria-label="Dashboard sections">
        {TABS.map(([id,label])=><button key={id} className={tab===id?'tab active':'tab'} onClick={()=>setTab(id)}>{label}</button>)}
      </nav>
    </div>
    {error&&<div className="error"><AlertTriangle size={16}/>{error}</div>}
    {notice&&<div className="notice">{notice}</div>}
    {showLiveConfirm&&<div className="modal-backdrop" style={{position:'fixed',inset:0,zIndex:50,background:'#030712c9',display:'grid',placeItems:'center',padding:18}}><section className="panel confirm-modal" style={{width:'min(560px, 100%)',boxShadow:'0 25px 80px #0008'}} role="dialog" aria-modal="true" aria-labelledby="live-confirm-title"><h2 id="live-confirm-title">Confirm LIVE mode selection</h2><p className="muted">Type <b>I AGREEE</b> to record that you intend to select live market mode. This does not enable real-money orders: live broker routing and reconciliation are not implemented in this release. Selecting LIVE blocks paper and sandbox order submission until you switch back.</p><input style={{width:'100%',margin:'10px 0 16px',padding:12}} aria-label="Confirmation phrase" value={liveConfirmation} onChange={e=>setLiveConfirmation(e.target.value)} placeholder="Type I AGREEE exactly"/><div className="actions" style={{justifyContent:'flex-end'}}><button className="danger" onClick={selectLiveMode} disabled={busy||liveConfirmation!=='I AGREEE'}>Confirm LIVE selection</button><button className="secondary" onClick={()=>setShowLiveConfirm(false)}>Cancel</button></div></section></div>}

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
            <label>Operating mode<select value={mode} onChange={e=>changeMode(e.target.value)} disabled={busy||!isBotOn||isKillActive}>
              <option value="semi">Semi-autonomous · human approves</option><option value="full">Full autonomy · paper permission</option>
            </select></label>
            {mode==='full'&&<span className="pill amber">DAILY LOSS LIMIT ₹{status.autonomous_daily_loss_limit??'—'}</span>}
          </div>
        </div>
        <div className="autonomy-form"><label>Daily loss limit (₹)<input type="number" min="1" step="1" value={lossLimit} onChange={e=>setLossLimit(e.target.value)} placeholder="Required for full mode"/></label><button onClick={()=>changeMode('full')} disabled={busy||!isBotOn||isKillActive||!ready||!lossLimit||Number(lossLimit)<=0}>Apply full-autonomy limit</button></div>
        <div className="readiness"><div className={'ready-dot '+(ready?'on':'')}></div><div><b>Readiness: {status.readiness?.status||'CHECKING'}</b><p className="muted">Full mode requires fresh NSE feed data, source-backed global intelligence, a clear kill switch and a healthy audit ledger.</p></div></div>
        <div className="checks">{Object.entries(status.readiness?.checks||{}).map(([k,v])=><span className={'check '+(v?'ok':'pending')} key={k}>{v?'✓':'○'} {k.replaceAll('_',' ')}</span>)}</div>
        <div className="control-row lock-row"><div><b>Daily loss lock: {status.daily_loss_lock?'ACTIVE':'Clear'}</b><p className="muted small">Resetting the daily lock preserves P&amp;L and never re-enables autonomy or releases the kill switch.</p></div><button className="secondary" onClick={resetDailyLock} disabled={!status.daily_loss_lock||busy}>Reset daily loss lock</button></div>
        <p className="muted small">This release controls operating permission; it does not contain an autonomous signal scanner or production order lifecycle.</p>
      </section>
      <section className="grid">
        <div className="panel"><div className="panel-title"><RadioTower/> NSE market feed <button onClick={connectFeed} disabled={busy}>Connect feed</button></div><p className="muted">Upstox V3 stream. A valid local access token and instrument subscription are required.</p>
          <table><thead><tr><th>Instrument key</th><th>Last price</th><th>Received (UTC)</th></tr></thead><tbody>{tickRows.length?tickRows.map(x=><tr key={x.symbol}><td>{x.symbol}</td><td>{x.ltp}</td><td>{x.received}</td></tr>):<tr><td colSpan="3">No ticks received yet</td></tr>}</tbody></table>
        </div>
        <div className="panel"><div className="panel-title"><ShieldCheck/> Safety & provider</div>
          <div className="kv"><span>Execution mode</span><b>{status.execution_mode==='LIVE_SELECTED'?'LIVE SELECTED · ROUTING OFF':'Paper money'}</b></div><div className="kv"><span>Live orders</span><b className="red">Unavailable in this build</b></div>
          <div className="kv"><span>AI provider</span><b>{status.ai_provider||'Not configured'}</b></div><div className="kv"><span>Model</span><b>{status.ai_model||'Not configured'}</b></div>
          <div className="kv"><span>API key</span><b>{status.ai_configured?'Configured':'Missing'}</b></div><div className="kv"><span>Web search</span><b>{status.ai_web_search_enabled?'Requested':'Disabled'}</b></div>
        </div>
      </section>
      <section className="panel research"><div className="panel-title"><Globe/> Global geopolitics & market intelligence <button onClick={refreshIntelligence} disabled={busy}>Refresh intelligence</button></div>
        <p className="muted">The configured model gathers current global events, commodities, macro data and transmission risks using provider search where supported. The field below is optional and treated as an unverified lead.</p>
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
        <div className="control-row"><span className="muted small">Research is advisory only and never places an order.</span><button onClick={runResearch} disabled={busy||analysisQuestion.trim().length<5}>Run research</button></div>
        {analysis&&<><pre className="research-output">{analysis.research}</pre><div className="muted small">{analysis.provider} · {analysis.model} · {analysis.web_search_supported?'Search supported':'No search adapter'} · {analysis.generated_at}</div>{analysis.sources?.length>0&&<ul className="source-list">{analysis.sources.map(s=><li key={s.url}><a href={s.url} target="_blank" rel="noreferrer">{s.title}</a></li>)}</ul>}</>}
      </section>
    </>}

    {tab==='trades'&&<section className="panel">
      <div className="panel-title"><Activity/> Trades</div>
      <p className="muted small">Trade and paper-order records currently held in this runtime session.</p>
      <p className="muted small">Use the filters to separate Indian and US equities, commodities, and currency/FX records. Exchange and market classification is stored with each new record.</p>
      <div className="filter-bar"><FilterInput label="Symbol" value={tradeFilters.symbol} onChange={v=>setTradeFilters({...tradeFilters,symbol:v})}/><FilterSelect label="Market" value={tradeFilters.market_region} onChange={v=>setTradeFilters({...tradeFilters,market_region:v})} options={['India','US','Global']}/><FilterSelect label="Category" value={tradeFilters.asset_class} onChange={v=>setTradeFilters({...tradeFilters,asset_class:v})} options={['equity','commodity','currency']}/><FilterInput label="Exchange" value={tradeFilters.exchange} onChange={v=>setTradeFilters({...tradeFilters,exchange:v})}/><FilterSelect label="Status" value={tradeFilters.status} onChange={v=>setTradeFilters({...tradeFilters,status:v})} options={['OPEN','CLOSED','SUBMITTED_TO_UPSTOX_SANDBOX']}/><FilterSelect label="Side" value={tradeFilters.side} onChange={v=>setTradeFilters({...tradeFilters,side:v})} options={['BUY','SELL']}/><label className="filter-field">From<input type="date" value={tradeFilters.date_from} onChange={e=>setTradeFilters({...tradeFilters,date_from:e.target.value})}/></label><label className="filter-field">To<input type="date" value={tradeFilters.date_to} onChange={e=>setTradeFilters({...tradeFilters,date_to:e.target.value})}/></label><button className="secondary" onClick={refresh}><RefreshCw size={14}/>Refresh</button></div>
      <table><thead><tr><th>Signal</th><th>Market</th><th>Category</th><th>Exchange</th><th>Symbol</th><th>Side</th><th>Entry</th><th>Stop</th><th>Target</th><th>Qty</th><th>Status</th><th>Mode</th></tr></thead><tbody>{filteredTrades.length?filteredTrades.map((o,i)=><tr key={o.signal_id||i}><td>{o.signal_id}</td><td>{o.market_region||'India'}</td><td>{o.asset_class||'equity'}</td><td>{o.exchange||'—'}</td><td>{o.symbol}</td><td>{o.side}</td><td>{o.entry}</td><td>{o.stop_loss}</td><td>{o.target}</td><td>{o.quantity}</td><td>{o.status}</td><td>{o.mode}</td></tr>):<tr><td colSpan="12">No trades match these filters.</td></tr>}</tbody></table>
    </section>}

    {tab==='suggestions'&&<section className="panel">
      <div className="panel-title"><BrainCircuit/> Suggested trades <button className="secondary" onClick={()=>window.location.assign(`${API}/api/candidates/export.xlsx`)}><FileSpreadsheet size={14}/>Download daily Excel log</button></div>
      <p className="muted small">Confidence is a research score, not a measured probability of success. Pending suggestions expire on stale quotes, stop/target invalidation, entry drift, or review TTL. One worksheet per local day is stored in backend/data/suggested_trades.xlsx.</p>
      <div className="filter-bar"><FilterInput label="Symbol" value={candidateFilters.symbol} onChange={v=>setCandidateFilters({...candidateFilters,symbol:v})}/><FilterSelect label="Market" value={candidateFilters.market_region} onChange={v=>setCandidateFilters({...candidateFilters,market_region:v})} options={['India','US','Global']}/><FilterSelect label="Category" value={candidateFilters.asset_class} onChange={v=>setCandidateFilters({...candidateFilters,asset_class:v})} options={['equity','commodity','currency']}/><FilterInput label="Exchange" value={candidateFilters.exchange} onChange={v=>setCandidateFilters({...candidateFilters,exchange:v})}/><FilterSelect label="Status" value={candidateFilters.status} onChange={v=>setCandidateFilters({...candidateFilters,status:v})} options={['PENDING','APPROVED','REJECTED','WATCHLIST','EXPIRED']}/><FilterSelect label="Side" value={candidateFilters.side} onChange={v=>setCandidateFilters({...candidateFilters,side:v})} options={['BUY','SELL']}/><label className="filter-field">Min score %<input type="number" min="0" max="100" value={candidateFilters.confidence} onChange={e=>setCandidateFilters({...candidateFilters,confidence:e.target.value})}/></label><label className="filter-field">From<input type="date" value={candidateFilters.date_from} onChange={e=>setCandidateFilters({...candidateFilters,date_from:e.target.value})}/></label><label className="filter-field">To<input type="date" value={candidateFilters.date_to} onChange={e=>setCandidateFilters({...candidateFilters,date_to:e.target.value})}/></label><button className="secondary" onClick={refresh}><RefreshCw size={14}/>Refresh</button></div>
      <table><thead><tr><th>Created</th><th>Market</th><th>Category</th><th>Exchange</th><th>Candidate</th><th>Side</th><th>Entry</th><th>Stop</th><th>Target</th><th>Score</th><th>Status</th><th>Expiry</th><th>Decision</th></tr></thead><tbody>{filteredCandidates.length?filteredCandidates.map(c=><tr key={c.candidate_id}><td>{c.created_at}</td><td>{c.market_region||'India'}</td><td>{c.asset_class||'equity'}</td><td>{c.exchange||'—'}</td><td>{c.symbol}<div className="muted small">{c.candidate_id}</div></td><td>{c.side}</td><td>{c.entry}</td><td>{c.stop_loss}</td><td>{c.target}</td><td>{c.confidence}%</td><td>{c.status}</td><td>{c.expiry_reason||'—'}</td><td>{c.status==='PENDING'?<div className="actions"><button onClick={()=>decideCandidate(c.candidate_id,'APPROVED')} disabled={busy||mode==='full'}>Approve</button><button className="secondary" onClick={()=>decideCandidate(c.candidate_id,'WATCHLIST')} disabled={busy||mode==='full'}>Watch</button><button className="danger" onClick={()=>decideCandidate(c.candidate_id,'REJECTED')} disabled={busy||mode==='full'}>Reject</button></div>:'—'}</td></tr>):<tr><td colSpan="13">No suggestions match these filters.</td></tr>}</tbody></table>
      {mode==='full'&&<p className="muted small">Manual suggestion decisions are disabled while full-autonomy permission is selected.</p>}
    </section>}

    {tab==='audit'&&<section className="panel">
      <div className="panel-title"><Activity/> Audit ledger <button className="secondary" onClick={verifyAudit}><ShieldCheck size={14}/>Verify chain</button></div>
      <p className="muted small">Append-only SQLite hash-chain events. Filters below apply to the latest 500 loaded entries.</p>
      <div className="filter-bar"><FilterInput label="Text or entity" value={auditFilters.q} onChange={v=>setAuditFilters({...auditFilters,q:v})}/><FilterInput label="Event type" value={auditFilters.event_type} onChange={v=>setAuditFilters({...auditFilters,event_type:v})}/><FilterSelect label="Market" value={auditFilters.market_region} onChange={v=>setAuditFilters({...auditFilters,market_region:v})} options={['India','US','Global']}/><FilterSelect label="Category" value={auditFilters.asset_class} onChange={v=>setAuditFilters({...auditFilters,asset_class:v})} options={['equity','commodity','currency']}/><label className="filter-field">From<input type="date" value={auditFilters.date_from} onChange={e=>setAuditFilters({...auditFilters,date_from:e.target.value})}/></label><label className="filter-field">To<input type="date" value={auditFilters.date_to} onChange={e=>setAuditFilters({...auditFilters,date_to:e.target.value})}/></label><button className="secondary" onClick={refresh}><RefreshCw size={14}/>Refresh</button></div>
      <table><thead><tr><th>Seq</th><th>Time (UTC)</th><th>Event</th><th>Entity</th><th>Details</th><th>Hash</th></tr></thead><tbody>{filteredAudit.length?filteredAudit.map(e=><tr key={e.event_id}><td>{e.seq}</td><td>{e.occurred_at}</td><td>{e.event_type}</td><td>{e.entity_id||'—'}</td><td className="audit-detail">{JSON.stringify(e.payload||{})}</td><td>{e.event_hash?.slice(0,14)}…</td></tr>):<tr><td colSpan="6">No audit events match these filters.</td></tr>}</tbody></table>
    </section>}

    <footer>Trabot 2.2.0 · Paper execution available · Live mode selection only · Development prototype</footer>
  </div>
}

function Metric({title,value}){return <div className="metric"><span>{title}</span><strong>{value}</strong></div>}
function FilterInput({label,value,onChange}){return <label className="filter-field">{label}<input value={value} onChange={e=>onChange(e.target.value)} placeholder="All"/></label>}
function FilterSelect({label,value,onChange,options}){return <label className="filter-field">{label}<select value={value} onChange={e=>onChange(e.target.value)}><option value="">All</option>{options.map(option=><option key={option} value={option}>{option}</option>)}</select></label>}
