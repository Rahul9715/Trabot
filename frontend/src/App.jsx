import React, {useEffect, useState} from 'react';
import {Activity, ShieldCheck, RadioTower, BrainCircuit, Power, RefreshCw, AlertTriangle, Bot, Globe, LockKeyhole, FileSpreadsheet, ListFilter, LayoutDashboard} from 'lucide-react';
import {Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis} from 'recharts';

const API='http://127.0.0.1:8000';
const TABS=[['overview','Overview'],['trades','Trades'],['suggestions','Suggested trades'],['reports','Reports'],['intelligence','Intelligence'],['audit','Audit ledger']];
const MARKET_DATE_FORMATTER=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Kolkata'});
const MARKET_DATETIME_FORMATTER=new Intl.DateTimeFormat('en-IN',{timeZone:'Asia/Kolkata',year:'numeric',month:'short',day:'numeric',hour:'numeric',minute:'2-digit',timeZoneName:'short'});
function shiftMarketDate(isoDate,days){const d=new Date(`${isoDate}T00:00:00Z`);d.setUTCDate(d.getUTCDate()+days);return d.toISOString().slice(0,10)}
function marketDate(value){const date=new Date(value);return Number.isNaN(date.getTime())?'':MARKET_DATE_FORMATTER.format(date)}
function marketDateTime(value){const date=new Date(value);return Number.isNaN(date.getTime())?'—':MARKET_DATETIME_FORMATTER.format(date)}
function localizeTimestampValues(value){
  if(typeof value==='string')return value.replace(/\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)/g,stamp=>marketDateTime(stamp));
  if(Array.isArray(value))return value.map(localizeTimestampValues);
  if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([key,item])=>[key,localizeTimestampValues(item)]));
  return value;
}

function sortRecords(rows,sort){
  const direction=sort.direction==='desc'?-1:1;
  const value=(row,key)=>{
    if(key==='actual_entry')return row.actual_entry??row.entry;
    if(key==='display_exit_price')return row.display_exit_price;
    if(key==='display_pnl')return row.display_pnl;
    if(key==='actual_stop_loss')return row.actual_stop_loss??row.stop_loss;
    if(key==='actual_target')return row.actual_target??row.target;
    return row[key];
  };
  return [...rows].sort((left,right)=>{
    const a=value(left,sort.key),b=value(right,sort.key);
    if(a==null||a==='')return b==null||b===''?0:1;
    if(b==null||b==='')return -1;
    if(typeof a==='number'&&typeof b==='number')return (a-b)*direction;
    if(sort.key==='created_at')return (Date.parse(a)-Date.parse(b))*direction;
    return String(a).localeCompare(String(b),undefined,{numeric:true,sensitivity:'base'})*direction;
  });
}

function SortHeader({label,column,sort,onSort}){
  const active=sort.key===column;
  return <th aria-sort={active?(sort.direction==='asc'?'ascending':'descending'):'none'}><button className="sort-header" onClick={()=>onSort(column)} title={`Sort by ${label}`}>{label}<span aria-hidden="true">{active?(sort.direction==='asc'?'▲':'▼'):'↕'}</span></button></th>;
}

export default function App(){
  const [tab,setTab]=useState('overview');
  const [status,setStatus]=useState({});
  const [account,setAccount]=useState({});
  const [tradeLimits,setTradeLimits]=useState({max_open_positions:'10',max_trades_per_day:'15',max_risk_per_trade:''});
  const [tradeLimitsDirty,setTradeLimitsDirty]=useState(false);
  const [profitExit,setProfitExit]=useState({enabled:false,target_percent:'8'});
  const [profitExitDirty,setProfitExitDirty]=useState(false);
  const [learning,setLearning]=useState({closed_trades:0,strategies:[],learning_policy:''});
  const [orders,setOrders]=useState([]);
  const [candidates,setCandidates]=useState([]);
  const [ticks,setTicks]=useState({});
  const [marketDataMaxAge,setMarketDataMaxAge]=useState(5);
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
  const [tradeSort,setTradeSort]=useState({key:'created_at',direction:'desc'});
  const [candidateSort,setCandidateSort]=useState({key:'created_at',direction:'desc'});
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
      const [s,a,o,i,ev,cs,l,exit]=await Promise.all([
        call('/api/status'),call('/api/account'),call('/api/orders'),
        call('/api/intelligence/latest'),call('/api/audit/events?limit=500'),call('/api/candidates'),call('/api/strategy-learning'),call('/api/paper-exit-settings')
      ]);
      setStatus(s);setAccount(a);setOrders(o);
      setResearch(i.brief||'');setIntelSources(i.sources||[]);setAudit(ev||[]);setCandidates(cs||[]);setLearning(l||{});
      if(!profitExitDirty)setProfitExit({enabled:Boolean(exit.enabled),target_percent:String(exit.target_percent??8)});
    }catch(e){setError('Backend not reachable. Start FastAPI on port 8000.')}
  }
  async function refreshMarket(){
    try{const market=await call('/api/market/latest');setTicks(market.ticks||{});setMarketDataMaxAge(market.market_data_max_age_seconds||5)}catch{}
  }
  useEffect(()=>{document.documentElement.dataset.theme=theme;localStorage.setItem('nse-theme',theme)},[theme]);
  useEffect(()=>{refresh();const t=setInterval(refresh,5000);return()=>clearInterval(t)},[]);
  useEffect(()=>{refreshMarket();const t=setInterval(refreshMarket,1000);return()=>clearInterval(t)},[]);
  useEffect(()=>{if(!tradeLimitsDirty&&account.max_open_positions!=null&&account.max_trades_per_day!=null)setTradeLimits({max_open_positions:String(account.max_open_positions),max_trades_per_day:String(account.max_trades_per_day),max_risk_per_trade:account.max_risk_per_trade==null?'':String(account.max_risk_per_trade)})},[account.max_open_positions,account.max_trades_per_day,account.max_risk_per_trade,tradeLimitsDirty]);

  async function action(key, fn, success){
    setPending(current=>({...current,[key]:true}));setError('');setNotice('');
    try{const result=await fn();setNotice(typeof success==='function'?success(result):success);await refresh();return result}
    catch(e){setError(e.message);return null}
    finally{setPending(current=>{const next={...current};delete next[key];return next})}
  }
  const startBot=()=>action('bot',()=>call('/api/bot','POST',{enabled:true}),r=>r.message||'Agent started.');
  const startAutonomous=()=>action('autonomy-start',()=>call('/api/bot/start-autonomous','POST',{max_daily_loss:Number(lossLimit)}),r=>r.message||'Agent started and paper autonomy armed.');
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
  const applyTradeLimits=async()=>{
    const result=await action('trade-limits',()=>call('/api/paper-trade-limits','POST',{
      max_open_positions:Number(tradeLimits.max_open_positions),max_trades_per_day:Number(tradeLimits.max_trades_per_day),
      max_risk_per_trade:tradeLimits.max_risk_per_trade===''?null:Number(tradeLimits.max_risk_per_trade)
    }),r=>`Paper limits saved: ${r.max_open_positions} open positions, ${r.max_trades_per_day} daily entries, and ₹${Number(r.effective_risk_per_trade).toFixed(2)} per-trade risk.`);
    if(result){setTradeLimits({max_open_positions:String(result.max_open_positions),max_trades_per_day:String(result.max_trades_per_day),max_risk_per_trade:result.max_risk_per_trade==null?'':String(result.max_risk_per_trade)});setTradeLimitsDirty(false)}
  };
  const saveProfitExit=async()=>{
    const result=await action('profit-exit',()=>call('/api/paper-exit-settings','POST',{
      enabled:profitExit.enabled,target_percent:Number(profitExit.target_percent)
    }),r=>r.enabled?`Net-gain exit enabled at ${Number(r.target_percent).toFixed(1)}% of allocated trade capital after modeled costs.`:'Net-gain exit disabled; standard strategy exits remain active.');
    if(result){setProfitExit({enabled:Boolean(result.enabled),target_percent:String(result.target_percent)});setProfitExitDirty(false)}
  };
  const decideCandidate=(id,decision)=>action(`candidate:${id}`,()=>call(`/api/candidates/${id}/decision`,'POST',{decision,reason:`${decision} from dashboard`}),`Suggestion ${decision.toLowerCase()}.`);
  const verifyAudit=()=>action('audit',()=>call('/api/audit/verify'),r=>r.valid?`Audit chain verified: ${r.verified_events} events.`:`Audit chain integrity failure at sequence ${r.failed_seq}.`);
  const trainPaperModel=()=>action('model-training',()=>call('/api/model-training/train','POST',{}),r=>r.message||'Model-training status refreshed.');

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
  const tickRows=Object.entries(ticks).map(([key,v])=>({symbol:status.paper_strategy_engine?.symbol_by_instrument_key?.[key]||key,ltp:v.ltp,received:v.received_at,providerReceived:v.provider_received_at,lastTraded:v.last_traded_at,age:v.quote_age_seconds,fresh:v.quote_fresh}));
  const filteredTrades=orders.filter(o=>(!tradeFilters.symbol||String(o.symbol||'').toLowerCase().includes(tradeFilters.symbol.toLowerCase()))&&(!tradeFilters.status||o.status===tradeFilters.status)&&(!tradeFilters.side||o.side===tradeFilters.side)&&(!tradeFilters.asset_class||String(o.asset_class||'equity').toLowerCase()===tradeFilters.asset_class)&&(!tradeFilters.market_region||String(o.market_region||'India').toLowerCase()===tradeFilters.market_region.toLowerCase())&&(!tradeFilters.exchange||String(o.exchange||'').toLowerCase().includes(tradeFilters.exchange.toLowerCase()))&&(!tradeFilters.date_from||marketDate(o.created_at)>=tradeFilters.date_from)&&(!tradeFilters.date_to||marketDate(o.created_at)<=tradeFilters.date_to));
  const filteredCandidates=candidates.filter(c=>(!candidateFilters.symbol||String(c.symbol||'').toLowerCase().includes(candidateFilters.symbol.toLowerCase()))&&(!candidateFilters.status||c.status===candidateFilters.status)&&(!candidateFilters.side||c.side===candidateFilters.side)&&(candidateFilters.confidence===''||Number(c.confidence)>=Number(candidateFilters.confidence))&&(!candidateFilters.asset_class||String(c.asset_class||'equity').toLowerCase()===candidateFilters.asset_class)&&(!candidateFilters.market_region||String(c.market_region||'India').toLowerCase()===candidateFilters.market_region.toLowerCase())&&(!candidateFilters.exchange||String(c.exchange||'').toLowerCase().includes(candidateFilters.exchange.toLowerCase()))&&(!candidateFilters.date_from||marketDate(c.created_at)>=candidateFilters.date_from)&&(!candidateFilters.date_to||marketDate(c.created_at)<=candidateFilters.date_to));
  const sortedTrades=sortRecords(filteredTrades,tradeSort);
  const sortedCandidates=sortRecords(filteredCandidates,candidateSort);
  const onTradeSort=(key)=>setTradeSort(current=>({key,direction:current.key===key&&current.direction==='asc'?'desc':'asc'}));
  const onCandidateSort=(key)=>setCandidateSort(current=>({key,direction:current.key===key&&current.direction==='asc'?'desc':'asc'}));
  const filteredAudit=audit.filter(e=>{const p=e.payload||{};const nested=p.candidate||p.signal||p.order||{};const category=p.asset_class||nested.asset_class||((p.symbol||nested.symbol)?'equity':'');const region=p.market_region||nested.market_region||((p.symbol||nested.symbol)?'India':'');return (!auditFilters.event_type||String(e.event_type||'').toLowerCase().includes(auditFilters.event_type.toLowerCase()))&&(!auditFilters.q||`${e.entity_id||''} ${e.event_type||''} ${JSON.stringify(p)}`.toLowerCase().includes(auditFilters.q.toLowerCase()))&&(!auditFilters.asset_class||String(category).toLowerCase()===auditFilters.asset_class)&&(!auditFilters.market_region||String(region).toLowerCase()===auditFilters.market_region.toLowerCase())&&(!auditFilters.date_from||marketDate(e.occurred_at)>=auditFilters.date_from)&&(!auditFilters.date_to||marketDate(e.occurred_at)<=auditFilters.date_to)});
  const isBotOn=!!status.bot_enabled;
  const isKillActive=!!status.kill_switch;
  const paperEngine=status.paper_strategy_engine||{};
  const mode=status.operating_mode==='FULL'?'full':'semi';
  const reportToday=MARKET_DATE_FORMATTER.format(new Date());
  const reportUtcDay=new Date(`${reportToday}T00:00:00Z`);
  const reportWeekStart=shiftMarketDate(reportToday,-((reportUtcDay.getUTCDay()+6)%7));
  const reportMonthStart=`${reportToday.slice(0,7)}-01`;
  const reportStartDate=reportFrom||(reportWindow==='day'?reportToday:reportWindow==='week'?reportWeekStart:reportMonthStart);
  const reportEndDate=reportTo||reportToday;
  const reportStart=new Date(`${reportStartDate}T00:00:00+05:30`);
  const reportEnd=new Date(`${reportEndDate}T23:59:59.999+05:30`);
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
  let runningPnl=0,peakPnl=0,maxDrawdown=0;
  const reportCurve=reportByDay.map(row=>{runningPnl+=row.pnl;peakPnl=Math.max(peakPnl,runningPnl);maxDrawdown=Math.max(maxDrawdown,peakPnl-runningPnl);return {...row,cumulative:Math.round(runningPnl*100)/100}});
  const grossWins=reportTrades.filter(o=>o.realised_pnl>0).reduce((sum,o)=>sum+o.realised_pnl,0);
  const grossLosses=Math.abs(reportTrades.filter(o=>o.realised_pnl<0).reduce((sum,o)=>sum+o.realised_pnl,0));
  const averageWin=winCount?grossWins/winCount:0,averageLoss=lossCount?grossLosses/lossCount:0;
  const profitFactor=grossLosses?grossWins/grossLosses:null;
  const outcomes=[{name:'Wins',value:winCount,color:'#2dd4a3'},{name:'Losses',value:lossCount,color:'#fb7185'},{name:'Breakeven',value:evenCount,color:'#9ca3af'}].filter(x=>x.value);

  return <div className={`shell${tab==='trades'?' trades-shell':''}${tab==='suggestions'?' suggestions-shell':''}`}>
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
        <Metric title="Current capital" value={'₹'+Number(account.current_capital??account.starting_capital??10000).toLocaleString('en-IN')}/>
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
        <div className="autonomy-form"><label>India paper daily loss limit (₹)<input type="number" min="1" step="1" value={lossLimit} onChange={e=>setLossLimit(e.target.value)} placeholder="Required for full mode"/></label><button onClick={startAutonomous} disabled={isPending('autonomy-start')||isKillActive||!lossLimit||Number(lossLimit)<=0}>{isPending('autonomy-start')?'Arming…':isBotOn?'Arm full autonomy':'Start agent + arm autonomy'}</button></div>
        <div className="autonomy-form trade-limit-form">
          <label>Maximum simultaneous open trades (1–50)<input type="number" min="1" max="50" step="1" value={tradeLimits.max_open_positions} onChange={e=>{setTradeLimits({...tradeLimits,max_open_positions:e.target.value});setTradeLimitsDirty(true)}}/></label>
          <label>Maximum trade entries per day (1–100)<input type="number" min="1" max="100" step="1" value={tradeLimits.max_trades_per_day} onChange={e=>{setTradeLimits({...tradeLimits,max_trades_per_day:e.target.value});setTradeLimitsDirty(true)}}/></label>
          <label>Per-trade risk limit (₹; blank uses 5% of starting capital)<input type="number" min="1" step="1" value={tradeLimits.max_risk_per_trade} onChange={e=>{setTradeLimits({...tradeLimits,max_risk_per_trade:e.target.value});setTradeLimitsDirty(true)}} placeholder={`Default ₹${account.effective_risk_per_trade??'—'}`}/></label>
          <button onClick={applyTradeLimits} disabled={isPending('trade-limits')||!tradeLimitsDirty||!tradeLimits.max_open_positions||!tradeLimits.max_trades_per_day||(tradeLimits.max_risk_per_trade!==''&&Number(tradeLimits.max_risk_per_trade)<=0)}>Save paper trade limits</button>
          <p className="muted small">Defaults are 10 open positions, 15 entries per day, and 5% of starting capital per trade. An explicit per-trade risk amount overrides the 5% default. The daily loss limit remains a separate account-level stop. Limits are saved locally and apply to the INR paper account.</p>
        </div>
        <div className="autonomy-form profit-exit-form">
          <label className="profit-exit-toggle"><input type="checkbox" checked={profitExit.enabled} onChange={e=>{setProfitExit({...profitExit,enabled:e.target.checked});setProfitExitDirty(true)}}/> Enable net-gain exit</label>
          <label>Exit after net gain (% of allocated trade capital)<input type="number" min="0.1" max="100" step="0.1" value={profitExit.target_percent} onChange={e=>{setProfitExit({...profitExit,target_percent:e.target.value});setProfitExitDirty(true)}}/></label>
          <button onClick={saveProfitExit} disabled={isPending('profit-exit')||!profitExitDirty||Number(profitExit.target_percent)<0.1||Number(profitExit.target_percent)>100}>{isPending('profit-exit')?'Saving…':'Save gain-exit rule'}</button>
          <p className="muted small">Off by default. When enabled, Trabot closes a paper position after estimated net P&amp;L reaches this share of its allocated capital. Re-entry is considered only if the remaining strategy target can still support another cycle. Existing stop-loss, strategy target, and two-minute market-close exits remain active.</p>
        </div>
        <div className="readiness"><div className={'ready-dot '+(ready?'on':'')}></div><div><b>Readiness: {status.readiness?.status||'CHECKING'}</b><p className="muted">You can arm paper autonomy before readiness. It will not consider entries until fresh in-session quotes, source-backed intelligence, a clear kill switch, and a healthy audit ledger are available. NSE warm-up starts with each new session and requires 30 completed one-minute bars per instrument.</p></div></div>
        <div className="checks">{Object.entries(status.readiness?.checks||{}).map(([k,v])=><span className={'check '+(v?'ok':'pending')} key={k}>{v?'✓':'○'} {k.replaceAll('_',' ')}</span>)}</div>
        <div className="control-row lock-row"><div><b>Daily loss lock: {status.daily_loss_lock?'ACTIVE':'Clear'}</b><p className="muted small">Resetting the daily lock preserves P&amp;L and never re-enables autonomy or releases the kill switch.</p></div><button className="secondary" onClick={resetDailyLock} disabled={!status.daily_loss_lock||isPending('daily-lock')}>Reset daily loss lock</button></div>
        <p className="muted small">Rule signals scan configured NSE cash equities and option-enabled underlyings. Index or stock direction maps to long calls or long puts using live option-chain liquidity filters. Live order routing remains locked pending broker and safety validation.</p>
      </section>
      <section className="panel">
        <div className="panel-title"><Bot/> Autonomous paper engine</div>
        <div className="kv"><span>Engine</span><b>{paperEngine.status||'STARTING'} · paper only</b></div>
        <div className="kv"><span>Eligible NSE equities</span><b>{paperEngine.eligible_equity_instruments??0}</b></div>
        {paperEngine.configured_equity_universe>paperEngine.eligible_equity_instruments&&<div className="kv"><span>Configured equity universe</span><b>{paperEngine.configured_equity_universe}</b></div>}
        <div className="kv"><span>Option-enabled underlyings</span><b>{paperEngine.eligible_option_underlyings??0} · {(paperEngine.option_underlyings||[]).map(x=>x.split('|').pop()).join(', ')||'None'}</b></div>
        <div className="kv"><span>Option chain scanner</span><b>{paperEngine.option_scan_status||'NOT CONFIGURED'}{paperEngine.option_scan_last_at?` · ${marketDateTime(paperEngine.option_scan_last_at)}`:''}</b></div>
        <div className="kv"><span>Strategy warm-up</span><b>{paperEngine.minimum_warmup_bars??30} completed 1m bars per instrument · stored locally</b></div>
        <div className="kv"><span>Warm-up bars by instrument</span><b>{Object.entries(paperEngine.warmup_bars_by_symbol||paperEngine.warmup_bars_by_instrument||{}).map(([key,count])=>`${key.includes('|')?key.split('|').pop():key}: ${count}`).join(' · ')||'Collecting live bars'}</b></div>
        {paperEngine.option_scan_error&&<p className="error">Option scanner: {paperEngine.option_scan_error}</p>}
        <div className="kv"><span>Rules</span><b>{(paperEngine.strategies||[]).join(' · ')||'Loading'}</b></div>
        <p className="muted">{paperEngine.last_action||'Waiting for live market ticks.'}</p>
        {paperEngine.feed_universe_note&&<p className="muted small">{paperEngine.feed_universe_note}</p>}
        {paperEngine.error&&<p className="error">Paper engine: {paperEngine.error}</p>}
        {!!paperEngine.stale_open_positions?.length&&<p className="error">Open paper positions are not receiving fresh exit quotes: {paperEngine.stale_open_positions.join(', ')}. The simulator will not fabricate an exit price.</p>}
        {!paperEngine.eligible_equity_instruments&&<p className="error">Current default subscriptions are Nifty indices. Add NSE_EQ stock instrument keys to UPSTOX_INSTRUMENT_KEYS in backend/.env and restart FastAPI. Index quotes cannot be submitted as stock orders.</p>}
        <p className="muted small">Signal scores are rule-strength labels, not win probabilities. Paper fills use streamed bid/ask where available, otherwise configurable spread and slippage estimates. India statutory costs and broker charges are estimated; holidays, queue position, partial fills, market impact, and exact broker fills are not simulated.</p>
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
          <div className="kv"><span>Current USD paper capital</span><b>${Number(ga.current_capital??ga.starting_capital??0).toLocaleString('en-US')}</b></div>
          <div className="kv"><span>USD daily P&amp;L · realised + open</span><b>${Number(ga.daily_pnl||0).toFixed(2)}</b></div>
          <div className="kv"><span>Open USD positions / daily entries</span><b>{ga.open_positions??0} / {ga.orders_today??0} · limits {ga.max_open_positions??10} / {ga.max_trades_per_day??15}</b></div>
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
      <section className="panel">
        <div className="panel-title"><Activity/> Strategy decisions &amp; paper-trade learning</div>
        <p className="muted">Suggestions and orders record their trigger rule, entry/stop/target distances, risk/reward, quote and bar timestamps, strategy version, and approval or rejection reason. Closed paper outcomes and model artifacts use the configured local data directory, which can later be moved to a shared folder.</p>
        <p className="muted">{learning.learning_policy||'Learning policy loads from the local paper outcome ledger.'}</p>
        <div className="kv"><span>Closed outcomes recorded</span><b>{learning.closed_trades??0}</b></div>
        <table><thead><tr><th>Strategy</th><th>Asset</th><th>Account</th><th>Closed</th><th>Win rate</th><th>Net P&amp;L</th><th>Average R</th><th>Review</th></tr></thead><tbody>
          {learning.strategies?.length?learning.strategies.map((row,index)=><tr key={`${row.strategy}-${row.asset_class}-${row.currency}-${index}`}><td>{row.strategy}</td><td>{row.asset_class}</td><td>{row.currency}</td><td>{row.closed_trades}</td><td>{row.win_rate_pct}%</td><td>{row.currency==='USD'?'$':'₹'}{Number(row.net_pnl).toFixed(2)}</td><td>{row.average_r==null?'—':row.average_r}</td><td>{row.adaptive_status}</td></tr>):<tr><td colSpan="8">No completed strategy outcomes have been recorded in this build yet.</td></tr>}
        </tbody></table>
        <p className="muted small">After at least 20 outcomes for a strategy, a non-positive historical average R pauses its autonomous entries while leaving suggestions visible. This cautious guard uses a limited historical sample and cannot predict future results. Paper history will inform future live-mode review; live routing remains unavailable.</p>
        {(()=>{const model= status.model_training||{}, latest=model.latest_model;return <div className="model-lab">
          <div className="panel-title"><BrainCircuit/> Paper model training <span className={'pill '+(model.training_available?'green':'amber')}>{model.status||'CHECKING'}</span><button className="secondary" onClick={trainPaperModel} disabled={isPending('model-training')}>{isPending('model-training')?'Training…':'Train baseline'}</button></div>
          <p className="muted">Offline logistic-regression baseline using signal-time price features and completed paper-trade outcomes. It trains on the oldest 80% and evaluates on the newest 20%. The result is shadow-only and never changes suggestions, approvals, sizing, or orders.</p>
          <div className="kv"><span>Feature-complete outcomes</span><b>{model.sample_count??0} / {model.minimum_samples??40} required · {model.wins??0} wins / {model.losses??0} losses</b></div>
          <div className="kv"><span>Model memory</span><b className="model-path">{model.model_dir||'backend/data/model'}</b></div>
          <div className="kv"><span>Settings source</span><b>{status.configuration_storage?.shared_env_loaded?'shared env file loaded':'local backend/.env'}</b></div>
          {model.dependency_error&&<p className="muted small">{model.dependency_error}</p>}
          {(model.sample_count||0)<(model.minimum_samples||40)&&<p className="muted small">Earlier paper trades do not contain saved indicator snapshots, so Trabot cannot reconstruct their features after the fact. New closed trades will add them. Training also waits for at least {model.minimum_per_outcome||10} wins and {model.minimum_per_outcome||10} losses.</p>}
          {latest?.metrics&&<div className="model-metrics"><span>Holdout trades: <b>{latest.metrics.holdout_samples}</b></span><span>Accuracy: <b>{latest.metrics.accuracy}</b></span><span>Brier score: <b>{latest.metrics.brier_score}</b></span><span>ROC AUC: <b>{latest.metrics.roc_auc??'not available'}</b></span><span>Trained: <b>{marketDateTime(latest.created_at)}</b></span></div>}
          {latest&&<p className="muted small">Latest model {latest.model_id} · Shadow only · Not used for trade decisions.</p>}
        </div>})()}
      </section>
      <section className="grid">
        <div className="panel"><div className="panel-title"><RadioTower/> NSE market feed <button onClick={connectFeed} disabled={isPending('feed')}>Connect feed</button></div><p className="muted">Upstox V3 &middot; Feed status: {status.feed_status||'CHECKING'} &middot; {status.feed_instrument_count||0} instrument keys.</p>{status.feed_error&&<p className="error">{status.feed_error}</p>}{!status.feed_token_configured&&<p className="muted">To connect: complete Upstox OAuth, place the current token in backend/.env as UPSTOX_ACCESS_TOKEN, then restart FastAPI. Set subscriptions with UPSTOX_INSTRUMENT_KEYS. The feed starts automatically once both are configured.</p>}
          <p className="muted small">Dashboard prices refresh every second. New decisions require feed timestamps no older than {marketDataMaxAge} seconds.</p><table><thead><tr><th>Instrument</th><th>Last price</th><th>Feed tick (IST)</th><th>Last trade (IST)</th><th>Quote age</th></tr></thead><tbody>{tickRows.length?tickRows.map(x=><tr key={x.symbol}><td>{x.symbol}</td><td>{x.ltp}</td><td>{marketDateTime(x.providerReceived||x.received)}</td><td>{marketDateTime(x.lastTraded)}</td><td className={x.fresh?'positive':'negative'}>{x.age==null?'—':`${x.fresh?'Fresh':'Stale'} · ${x.age}s`}</td></tr>):<tr><td colSpan="5">No ticks received yet</td></tr>}</tbody></table>
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
        <div className="muted small">Last refresh: {status.readiness?.intelligence_last_update?marketDateTime(status.readiness.intelligence_last_update):'Never'} · Provider: {status.ai_provider||'unconfigured'}</div>
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
        {analysis&&<><pre className="research-output">{analysis.research}</pre><div className="muted small">{analysis.provider} · {analysis.model} · {analysis.web_search_supported?'Search supported':'No search adapter'} · {marketDateTime(analysis.generated_at)}</div>{analysis.sources?.length>0&&<ul className="source-list">{analysis.sources.map(s=><li key={s.url}><a href={s.url} target="_blank" rel="noreferrer">{s.title}</a></li>)}</ul>}</>}
      </section>
    </>}

    {tab==='reports'&&<>
      <section className="panel">
        <div className="panel-title"><Activity/> Performance reports</div>
        <p className="muted small">Reports use durable closed-trade history reconstructed from the audit ledger. Net paper P&amp;L includes estimated execution costs; older trades may not include fill and fee detail if those fields were not recorded at the time.</p>
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
          <Metric title={`Net paper P&L (${reportCurrency})`} value={`${reportCurrency==='USD'?'$':'₹'}${reportPnl.toLocaleString(reportCurrency==='USD'?'en-US':'en-IN',{maximumFractionDigits:2})}`}/>
          <Metric title="Wins / losses" value={`${winCount} / ${lossCount}`}/>
          <Metric title={`Average win (${reportCurrency})`} value={winCount?`${reportCurrency==='USD'?'$':'₹'}${averageWin.toLocaleString(reportCurrency==='USD'?'en-US':'en-IN',{maximumFractionDigits:2})}`:'—'}/>
          <Metric title={`Average loss (${reportCurrency})`} value={lossCount?`${reportCurrency==='USD'?'$':'₹'}${averageLoss.toLocaleString(reportCurrency==='USD'?'en-US':'en-IN',{maximumFractionDigits:2})}`:'—'}/>
          <Metric title="Profit factor" value={profitFactor==null?(grossWins?'∞':'—'):profitFactor.toFixed(2)}/>
          <Metric title={`Max drawdown (${reportCurrency})`} value={`${reportCurrency==='USD'?'$':'₹'}${maxDrawdown.toLocaleString(reportCurrency==='USD'?'en-US':'en-IN',{maximumFractionDigits:2})}`}/>
        </div>
        <div className="report-grid">
          <div className="chart-card report-equity"><h3>Cumulative realised P&amp;L ({reportCurrency})</h3>{reportCurve.length?<ResponsiveContainer width="100%" height={230}><AreaChart data={reportCurve}><CartesianGrid strokeDasharray="3 3" stroke="var(--border)"/><XAxis dataKey="date" tick={{fill:'var(--muted)',fontSize:11}}/><YAxis tick={{fill:'var(--muted)',fontSize:11}}/><Tooltip contentStyle={{background:'var(--surface)',borderColor:'var(--border)',color:'var(--text)'}}/><Area type="monotone" dataKey="cumulative" name={`Cumulative P&L (${reportCurrency})`} stroke="var(--chart-accent)" fill="var(--chart-accent)" fillOpacity={0.18}/></AreaChart></ResponsiveContainer>:<div className="chart-empty">No realised P&amp;L history for this window.</div>}</div>
          <div className="chart-card"><h3>Daily net P&amp;L ({reportCurrency})</h3>{reportByDay.length?<ResponsiveContainer width="100%" height={280}><BarChart data={reportByDay}><CartesianGrid strokeDasharray="3 3" stroke="var(--border)"/><XAxis dataKey="date" tick={{fill:'var(--muted)',fontSize:11}}/><YAxis tick={{fill:'var(--muted)',fontSize:11}}/><Tooltip contentStyle={{background:'var(--surface)',borderColor:'var(--border)',color:'var(--text)'}}/><Legend/><Bar dataKey="pnl" name={`Net P&L (${reportCurrency})`} fill="var(--chart-accent)" radius={[4,4,0,0]}/></BarChart></ResponsiveContainer>:<div className="chart-empty">No realised P&amp;L history for this window.</div>}</div>
          <div className="chart-card"><h3>Trade outcomes</h3>{outcomes.length?<ResponsiveContainer width="100%" height={280}><PieChart><Pie data={outcomes} dataKey="value" nameKey="name" innerRadius={58} outerRadius={92} paddingAngle={3} label>{outcomes.map(entry=><Cell key={entry.name} fill={entry.color}/>)}</Pie><Tooltip contentStyle={{background:'var(--surface)',borderColor:'var(--border)',color:'var(--text)'}}/><Legend/></PieChart></ResponsiveContainer>:<div className="chart-empty">No closed trades in this window.</div>}</div>
        </div>
      </section>
    </>}

    {tab==='trades'&&<section className="panel">
      <div className="panel-title"><Activity/> Trades</div>
      <p className="muted small">Trade records are recovered from the local append-only audit ledger across backend restarts. Displayed paper exits and P&amp;L for open positions use estimated marketable fills, spread, slippage, and costs.</p>
      <p className="muted small">Use the filters to separate Indian and US equities, commodities, and currency/FX records. Exchange and market classification is stored with each new record.</p>
      <div className="filter-bar"><FilterInput label="Symbol" value={tradeFilters.symbol} onChange={v=>setTradeFilters({...tradeFilters,symbol:v})}/><FilterSelect label="Market" value={tradeFilters.market_region} onChange={v=>setTradeFilters({...tradeFilters,market_region:v})} options={['India','US','Global']}/><FilterSelect label="Category" value={tradeFilters.asset_class} onChange={v=>setTradeFilters({...tradeFilters,asset_class:v})} options={['equity','options','commodity','currency']}/><FilterInput label="Exchange" value={tradeFilters.exchange} onChange={v=>setTradeFilters({...tradeFilters,exchange:v})}/><FilterSelect label="Status" value={tradeFilters.status} onChange={v=>setTradeFilters({...tradeFilters,status:v})} options={['OPEN','CLOSED','SUBMITTED_TO_UPSTOX_SANDBOX']}/><FilterSelect label="Side" value={tradeFilters.side} onChange={v=>setTradeFilters({...tradeFilters,side:v})} options={['BUY','SELL']}/><label className="filter-field">From<input type="date" value={tradeFilters.date_from} onChange={e=>setTradeFilters({...tradeFilters,date_from:e.target.value})}/></label><label className="filter-field">To<input type="date" value={tradeFilters.date_to} onChange={e=>setTradeFilters({...tradeFilters,date_to:e.target.value})}/></label><button className="secondary" onClick={refresh}><RefreshCw size={14}/>Refresh</button></div>
      <table className="trade-table"><thead><tr><SortHeader label="Signal" column="signal_id" sort={tradeSort} onSort={onTradeSort}/><SortHeader label="Market" column="market_region" sort={tradeSort} onSort={onTradeSort}/><SortHeader label="Category" column="asset_class" sort={tradeSort} onSort={onTradeSort}/><SortHeader label="Exchange" column="exchange" sort={tradeSort} onSort={onTradeSort}/><SortHeader label="Symbol" column="symbol" sort={tradeSort} onSort={onTradeSort}/><SortHeader label="Currency" column="currency" sort={tradeSort} onSort={onTradeSort}/><SortHeader label="Side" column="side" sort={tradeSort} onSort={onTradeSort}/><SortHeader label="Actual entry" column="actual_entry" sort={tradeSort} onSort={onTradeSort}/><SortHeader label="Actual exit / mark" column="display_exit_price" sort={tradeSort} onSort={onTradeSort}/><SortHeader label="Trade P&amp;L" column="display_pnl" sort={tradeSort} onSort={onTradeSort}/><SortHeader label="Stop" column="actual_stop_loss" sort={tradeSort} onSort={onTradeSort}/><SortHeader label="Target" column="actual_target" sort={tradeSort} onSort={onTradeSort}/><SortHeader label="Qty" column="quantity" sort={tradeSort} onSort={onTradeSort}/><SortHeader label="Status" column="status" sort={tradeSort} onSort={onTradeSort}/><SortHeader label="Latest action" column="last_action_at" sort={tradeSort} onSort={onTradeSort}/><SortHeader label="Mode" column="mode" sort={tradeSort} onSort={onTradeSort}/></tr></thead><tbody>{sortedTrades.length?sortedTrades.map((o,i)=>{const currency=o.currency||'INR';const sign=currency==='USD'?'$':'₹';return <tr key={o.signal_id||i}><td title={o.signal_id}>{o.signal_id}</td><td>{o.market_region||'India'}</td><td>{o.asset_class||'equity'}</td><td>{o.exchange||'—'}</td><td>{o.symbol}</td><td>{currency}</td><td>{o.side}</td><td>{o.actual_entry??o.entry}</td><td>{o.display_exit_price??'—'}</td><td>{o.display_pnl==null?'—':`${sign}${Number(o.display_pnl).toLocaleString(currency==='USD'?'en-US':'en-IN',{minimumFractionDigits:2,maximumFractionDigits:2})}`}</td><td>{o.actual_stop_loss??o.stop_loss}</td><td>{o.actual_target??o.target}</td><td>{o.quantity}</td><td>{o.status}</td><td className="trade-action-time">{marketDateTime(o.last_action_at||o.closed_at||o.created_at)}</td><td>{o.mode}</td></tr>}):<tr><td colSpan="16">No trades match these filters.</td></tr>}</tbody></table>
    </section>}

    {tab==='suggestions'&&<section className="panel">
      <div className="panel-title"><BrainCircuit/> Suggested trades <button className="secondary" onClick={()=>window.location.assign(`${API}/api/candidates/export.xlsx`)}><FileSpreadsheet size={14}/>Download daily Excel log</button></div>
      <p className="muted small">Confidence is a research score, not a measured probability of success. Pending suggestions expire on stale quotes, stop/target invalidation, entry drift, or review TTL. One worksheet per local day is stored in backend/data/suggested_trades.xlsx.</p>
      <div className="filter-bar"><FilterInput label="Symbol" value={candidateFilters.symbol} onChange={v=>setCandidateFilters({...candidateFilters,symbol:v})}/><FilterSelect label="Market" value={candidateFilters.market_region} onChange={v=>setCandidateFilters({...candidateFilters,market_region:v})} options={['India','US','Global']}/><FilterSelect label="Category" value={candidateFilters.asset_class} onChange={v=>setCandidateFilters({...candidateFilters,asset_class:v})} options={['equity','options','commodity','currency']}/><FilterInput label="Exchange" value={candidateFilters.exchange} onChange={v=>setCandidateFilters({...candidateFilters,exchange:v})}/><FilterSelect label="Status" value={candidateFilters.status} onChange={v=>setCandidateFilters({...candidateFilters,status:v})} options={['PENDING','PENDING_OPTION_QUOTE','AUTO_EXECUTED','AUTO_REJECTED','EXECUTED_PAPER','APPROVAL_ORDER_REJECTED','APPROVED','REJECTED','WATCHLIST','EXPIRED']}/><FilterSelect label="Side" value={candidateFilters.side} onChange={v=>setCandidateFilters({...candidateFilters,side:v})} options={['BUY','SELL']}/><label className="filter-field">Min score %<input type="number" min="0" max="100" value={candidateFilters.confidence} onChange={e=>setCandidateFilters({...candidateFilters,confidence:e.target.value})}/></label><label className="filter-field">From<input type="date" value={candidateFilters.date_from} onChange={e=>setCandidateFilters({...candidateFilters,date_from:e.target.value})}/></label><label className="filter-field">To<input type="date" value={candidateFilters.date_to} onChange={e=>setCandidateFilters({...candidateFilters,date_to:e.target.value})}/></label><button className="secondary" onClick={refresh}><RefreshCw size={14}/>Refresh</button></div>
      <table><thead><tr><SortHeader label="Created" column="created_at" sort={candidateSort} onSort={onCandidateSort}/><SortHeader label="Market" column="market_region" sort={candidateSort} onSort={onCandidateSort}/><SortHeader label="Category" column="asset_class" sort={candidateSort} onSort={onCandidateSort}/><SortHeader label="Exchange" column="exchange" sort={candidateSort} onSort={onCandidateSort}/><SortHeader label="Candidate" column="symbol" sort={candidateSort} onSort={onCandidateSort}/><SortHeader label="Side" column="side" sort={candidateSort} onSort={onCandidateSort}/><SortHeader label="Entry" column="entry" sort={candidateSort} onSort={onCandidateSort}/><SortHeader label="Stop" column="stop_loss" sort={candidateSort} onSort={onCandidateSort}/><SortHeader label="Target" column="target" sort={candidateSort} onSort={onCandidateSort}/><SortHeader label="Rule score" column="confidence" sort={candidateSort} onSort={onCandidateSort}/><SortHeader label="Status" column="status" sort={candidateSort} onSort={onCandidateSort}/><SortHeader label="Decision reason" column="decision_reason" sort={candidateSort} onSort={onCandidateSort}/><SortHeader label="Expiry" column="expiry_reason" sort={candidateSort} onSort={onCandidateSort}/><th>Decision</th></tr></thead><tbody>{sortedCandidates.length?sortedCandidates.map(c=><tr key={c.candidate_id}><td>{marketDateTime(c.created_at)}</td><td>{c.market_region||'India'}</td><td>{c.asset_class||'equity'}</td><td>{c.exchange||'—'}</td><td>{c.symbol}<div className="muted small">{c.candidate_id}</div><details><summary>Why suggested?</summary><p>{c.rationale}</p><ul>{(c.evidence?.decision_factors||[]).map((reason,index)=><li key={index}>{reason}</li>)}</ul><p>Strategy: {c.evidence?.strategy||'not recorded'} · Historical review: {c.evidence?.historical_strategy_review?.adaptive_status||'not enough closed trades yet'}</p></details></td><td>{c.side}</td><td>{c.entry}</td><td>{c.stop_loss}</td><td>{c.target}</td><td>{c.confidence}%<div className="muted small">Rule strength, not probability</div></td><td>{c.status}</td><td>{c.decision_reason||c.expiry_reason||'No execution decision; suggestion awaits review.'}</td><td>{c.expiry_reason||'—'}</td><td>{c.status==='PENDING'?<div className="actions"><button onClick={()=>decideCandidate(c.candidate_id,'APPROVED')} disabled={isPending(`candidate:${c.candidate_id}`)||mode==='full'}>Approve</button><button className="secondary" onClick={()=>decideCandidate(c.candidate_id,'WATCHLIST')} disabled={isPending(`candidate:${c.candidate_id}`)||mode==='full'}>Watch</button><button className="danger" onClick={()=>decideCandidate(c.candidate_id,'REJECTED')} disabled={isPending(`candidate:${c.candidate_id}`)||mode==='full'}>Reject</button></div>:'—'}</td></tr>):<tr><td colSpan="14">No suggestions match these filters.</td></tr>}</tbody></table>
      {mode==='full'&&<p className="muted small">Manual suggestion decisions are disabled while full-autonomy permission is selected.</p>}
    </section>}

    {tab==='audit'&&<section className="panel">
      <div className="panel-title"><Activity/> Audit ledger <button className="secondary" onClick={verifyAudit}><ShieldCheck size={14}/>Verify chain</button></div>
      <p className="muted small">Append-only SQLite hash-chain events. Filters below apply to the latest 500 loaded entries.</p>
      <div className="filter-bar"><FilterInput label="Text or entity" value={auditFilters.q} onChange={v=>setAuditFilters({...auditFilters,q:v})}/><FilterInput label="Event type" value={auditFilters.event_type} onChange={v=>setAuditFilters({...auditFilters,event_type:v})}/><FilterSelect label="Market" value={auditFilters.market_region} onChange={v=>setAuditFilters({...auditFilters,market_region:v})} options={['India','US','Global']}/><FilterSelect label="Category" value={auditFilters.asset_class} onChange={v=>setAuditFilters({...auditFilters,asset_class:v})} options={['equity','commodity','currency']}/><label className="filter-field">From<input type="date" value={auditFilters.date_from} onChange={e=>setAuditFilters({...auditFilters,date_from:e.target.value})}/></label><label className="filter-field">To<input type="date" value={auditFilters.date_to} onChange={e=>setAuditFilters({...auditFilters,date_to:e.target.value})}/></label><button className="secondary" onClick={refresh}><RefreshCw size={14}/>Refresh</button></div>
      <table><thead><tr><th>Seq</th><th>Time (IST)</th><th>Event</th><th>Entity</th><th>Details</th><th>Hash</th></tr></thead><tbody>{filteredAudit.length?filteredAudit.map(e=><tr key={e.event_id}><td>{e.seq}</td><td>{marketDateTime(e.occurred_at)}</td><td>{e.event_type}</td><td>{e.entity_id||'—'}</td><td className="audit-detail">{JSON.stringify(localizeTimestampValues(e.payload||{}))}</td><td>{e.event_hash?.slice(0,14)}…</td></tr>):<tr><td colSpan="6">No audit events match these filters.</td></tr>}</tbody></table>
    </section>}

    <footer>Trabot · Paper trading only · Live order routing locked · Development prototype</footer>
  </div>
}

function Metric({title,value}){return <div className="metric"><span>{title}</span><strong>{value}</strong></div>}
function FilterInput({label,value,onChange}){return <label className="filter-field">{label}<input value={value} onChange={e=>onChange(e.target.value)} placeholder="All"/></label>}
function FilterSelect({label,value,onChange,options}){return <label className="filter-field">{label}<select value={value} onChange={e=>onChange(e.target.value)}><option value="">All</option>{options.map(option=><option key={option} value={option}>{option}</option>)}</select></label>}

