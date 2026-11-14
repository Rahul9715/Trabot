import React, {useEffect, useState} from 'react';
import {Activity, ShieldCheck, RadioTower, BrainCircuit, Power, RefreshCw, AlertTriangle, Bot, Globe, LockKeyhole} from 'lucide-react';

const API='http://127.0.0.1:8000';
export default function App(){
  const [status,setStatus]=useState({});
  const [account,setAccount]=useState({});
  const [orders,setOrders]=useState([]);
  const [candidates,setCandidates]=useState([]);
  const [ticks,setTicks]=useState({});
  const [context,setContext]=useState('');
  const [research,setResearch]=useState('');
  const [lossLimit,setLossLimit]=useState('');
  const [auto,setAuto]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [audit,setAudit]=useState([]);
  const [theme,setTheme]=useState(()=>localStorage.getItem('nse-theme')||'dark');
  async function call(path,method='GET',body){
    const r=await fetch(API+path,{method,headers:{'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{})});
    const j=await r.json(); if(!r.ok) throw Error(j.detail||'Request failed'); return j;
  }
  async function refresh(){
    try{
      const [s,a,o,m,i,ev,cs]=await Promise.all([
        call('/api/status'),call('/api/account'),call('/api/orders'),call('/api/market/latest'),call('/api/intelligence/latest'),call('/api/audit/events?limit=30'),call('/api/candidates')
      ]);
      setStatus(s);setAccount(a);setOrders(o);setTicks(m.ticks||{});setResearch(i.brief||'');setAudit(ev||[]);setCandidates(cs||[]);
      setAuto(!!s.autonomous_mode);
    }catch(e){setError('Backend not reachable. Start FastAPI on port 8000.')}
  }
  useEffect(()=>{document.documentElement.dataset.theme=theme;localStorage.setItem('nse-theme',theme)},[theme]);
  useEffect(()=>{refresh();const t=setInterval(refresh,2500);return()=>clearInterval(t)},[]);
  async function startBot(){
    setBusy(true);setError('');setNotice('');
    try{
      const r=await call('/api/bot','POST',{enabled:true});
      setNotice(r.message);
      await refresh();
    }catch(e){setError(e.message)}finally{setBusy(false)}
  }
  async function stopBot(){
    setBusy(true);try{await call('/api/bot','POST',{enabled:false});setAuto(false);setNotice('Bot stopped. Autonomous permission revoked.');await refresh()}catch(e){setError(e.message)}finally{setBusy(false)}
  }
  async function kill(){
    try{await call('/api/kill-switch','POST',{});setAuto(false);setNotice('Kill switch engaged. New orders blocked immediately.');await refresh()}catch(e){setError(e.message)}
  }
  async function refreshIntelligence(){
    setBusy(true);setError('');setNotice('Refreshing global geopolitical and market intelligence…');
    try{
      const r=await call('/api/intelligence/refresh','POST',{extra_context:context});
      setResearch(r.brief);setNotice('Global intelligence updated. Check market-feed status before expecting READY.');await refresh();
    }catch(e){setError(e.message)}finally{setBusy(false)}
  }
  async function connectFeed(){
    setBusy(true);setError('');
    try{
      await call('/api/market/connect','POST',{instrument_keys:['NSE_INDEX|Nifty 50','NSE_INDEX|Nifty Bank']});
      setNotice('Market feed connection requested. Waiting for fresh ticks.');
    }catch(e){setError(e.message)}finally{setBusy(false)}
  }
  async function decideCandidate(id,decision){
    try{await call(`/api/candidates/${id}/decision`,'POST',{decision,reason:decision==='REJECTED'?'Rejected from dashboard':'Approved from dashboard'});setNotice(`Candidate ${id}: ${decision}`);await refresh()}catch(e){setError(e.message)}
  }
  async function resetDailyLock(){
    setError('');setNotice('');
    try{const r=await call('/api/daily-lock/reset','POST',{});setNotice(r.reset?'Daily loss lock reset. Cumulative P&L retained; re-enable autonomy explicitly.':r.message);await refresh()}catch(e){setError(e.message)}
  }
  async function setAutonomy(enabled){
    setError('');setNotice('');
    try{
      const r=await call('/api/autonomy','POST',{enabled,max_daily_loss:enabled?Number(lossLimit):null});
      setAuto(!!r.autonomous_mode);setNotice(r.message);await refresh();
    }catch(e){setError(e.message)}
  }
  const tickRows=Object.entries(ticks).map(([symbol,v])=>({symbol,ltp:v.ltp,received:v.received_at}));
  const ready=status.readiness?.ready;
  return <div className="shell">
    <header><div><div className="eyebrow">LOCAL TRADING TERMINAL · LIVE INTELLIGENCE · PAPER EXECUTION</div><h1>NSE AI Trading Desk</h1><p>Global research · Market data · Approval controls · Risk management</p></div><div className="header-right"><button className="secondary" onClick={()=>setTheme(theme==='dark'?'light':'dark')}>{theme==='dark'?'☀ Light mode':'☾ Dark mode'}</button><span className="pill green">LIVE ORDERS DISABLED</span><span className={'pill '+(ready?'green':'amber')}>{status.readiness?.status||'CHECKING'}</span></div></header>
    {error&&<div className="error"><AlertTriangle size={16}/>{error}</div>}
    {notice&&<div className="notice">{notice}</div>}
    <section className="stats">
      <Metric title="Starting capital" value={'₹'+(account.starting_capital||10000).toLocaleString('en-IN')}/>
      <Metric title="Daily P&L (incl. open)" value={'₹'+(account.daily_pnl||0).toLocaleString('en-IN')}/>
      <Metric title="Open positions" value={account.open_positions??0}/>
      <Metric title="Daily orders" value={account.orders_today??0}/>
    </section>
    <section className="panel control-panel">
      <div className="panel-title"><Bot/> Bot master control</div>
      <div className="control-row">
        <div><b>Bot power</b><p className="muted">Independent of manual or autonomous mode. Turning OFF revokes autonomous permission.</p></div>
        <div className="actions"><button onClick={startBot} disabled={busy||status.bot_enabled}> <Power size={14}/> Start bot</button><button className="secondary" onClick={stopBot} disabled={busy||!status.bot_enabled}>Stop bot</button></div>
      </div>
      <div className="readiness">
        <div className={'ready-dot '+(ready?'on':'')}></div>
        <div><b>System status: {ready?'READY':status.bot_enabled?'STARTING – checks pending':'STOPPED'}</b><p className="muted">READY requires bot ON, fresh market feed, refreshed global intelligence and kill switch released.</p></div>
      </div>
      <div className="checks">
        {Object.entries(status.readiness?.checks||{}).map(([k,v])=><span className={'check '+(v?'ok':'pending')} key={k}>{v?'✓':'○'} {k.replaceAll('_',' ')}</span>)}
      </div>
    </section>
    <section className="grid">
      <div className="panel"><div className="panel-title"><RadioTower/> NSE market feed <button onClick={connectFeed} disabled={busy}>Connect feed</button></div><p className="muted">Upstox V3 stream. READY requires fresh incoming ticks. Subscription permissions and valid instrument keys apply.</p>
        <table><thead><tr><th>Instrument key</th><th>Last price</th><th>Received (UTC)</th></tr></thead><tbody>{tickRows.length?tickRows.map(x=><tr key={x.symbol}><td>{x.symbol}</td><td>{x.ltp}</td><td>{x.received}</td></tr>):<tr><td colSpan="3">No ticks received yet</td></tr>}</tbody></table>
      </div>
      <div className="panel"><div className="panel-title"><ShieldCheck/> Safety controls <button className="danger" onClick={kill}><Power size={14}/> Kill switch</button></div>
        <div className="kv"><span>Execution mode</span><b>Paper only</b></div><div className="kv"><span>Live orders</span><b className="red">Disabled</b></div><div className="kv"><span>Kill switch</span><b>{status.kill_switch?'ACTIVE':'Released'}</b></div><div className="kv"><span>AI configured</span><b>{status.ai_configured?'Yes':'API key missing'}</b></div><div className="kv"><span>Global intelligence</span><b>{status.intelligence_status||'Not refreshed'}</b></div>
      </div>
    </section>
    <section className="panel autonomy">
      <div className="panel-title"><LockKeyhole/> Trading authority</div>
      <div className="control-row">
        <div><b>Fully autonomous paper mode</b><p className="muted">Requires the bot to be READY and a configurable daily loss limit. Reaching it locks autonomous entries until you reset the daily lock. The emergency kill switch remains independent.</p></div>
        <span className={'pill '+(auto?'green':'amber')}>{auto?'AUTONOMOUS ON':'AUTONOMOUS OFF'}</span>
      </div>
      <div className="autonomy-form"><label>Autonomous loss allowance (₹)<input type="number" min="1" step="1" value={lossLimit} onChange={e=>setLossLimit(e.target.value)} placeholder="Set your session limit"/></label><div className="actions"><button onClick={()=>setAutonomy(true)} disabled={busy||auto||!status.bot_enabled||!ready||!lossLimit||Number(lossLimit)<=0||false}>Enable autonomous mode</button><button className="secondary" onClick={()=>setAutonomy(false)} disabled={!auto}>Disable autonomous mode</button></div></div>
      <div className="control-row lock-row"><div><b>Daily loss lock: {status.daily_loss_lock?'ACTIVE':'Clear'}</b><p className="muted small">Reset establishes a fresh allowance baseline from current P&amp;L. It never erases the day's cumulative P&amp;L and does not re-enable autonomy.</p></div><button className="secondary" onClick={resetDailyLock} disabled={!status.daily_loss_lock}>Reset daily lock</button></div><p className="muted small">The current release adds durable audit records and the daily-lock reset control. Full autonomous strategy scheduling and live broker execution remain disabled pending implementation and verification.</p>
    </section>
    <section className="panel research"><div className="panel-title"><Globe/> Global geopolitics & market intelligence <button onClick={refreshIntelligence} disabled={busy}>Refresh intelligence</button></div>
      <p className="muted">Coverage includes all material geopolitical flashpoints, wars, sanctions, shipping routes, oil, gas, metals, commodities, global macro, central banks and direct/indirect sector transmission to Indian markets. Refresh before the session and whenever a major event breaks.</p>
      <textarea value={context} onChange={e=>setContext(e.target.value)} placeholder="Optional: add context, watchlist, or specific concerns…" rows="3"/>
      {research?<pre className="research-output">{research}</pre>:<p className="muted">No global intelligence brief yet. Refresh to establish the news-readiness check.</p>}
      <div className="muted small">Last refresh: {status.readiness?.intelligence_last_update||'Never'} · Freshness window: 60 minutes</div>
    </section>
    <section className="panel"><div className="panel-title"><Activity/> Order book <button onClick={refresh}><RefreshCw size={14}/> Refresh</button></div><table><thead><tr><th>Signal</th><th>Symbol</th><th>Side</th><th>Entry</th><th>SL</th><th>Target</th><th>Qty</th><th>Status</th></tr></thead><tbody>{orders.length?orders.map((o,i)=><tr key={o.signal_id||i}><td>{o.signal_id}</td><td>{o.symbol}</td><td>{o.side}</td><td>{o.entry}</td><td>{o.stop_loss}</td><td>{o.target}</td><td>{o.quantity}</td><td>{o.status}</td></tr>):<tr><td colSpan="8">No orders yet</td></tr>}</tbody></table></section>
    <section className="panel"><div className="panel-title"><BrainCircuit/> Trade candidates & confidence</div><p className="muted small">Every candidate is retained in the audit ledger with its suggested entry, stop-loss, target, confidence, rationale and review evidence. Dashboard decisions do not place orders.</p><table><thead><tr><th>Candidate</th><th>Side</th><th>Entry</th><th>Stop-loss</th><th>Target</th><th>Confidence</th><th>Status</th><th>Decision</th></tr></thead><tbody>{candidates.length?candidates.map(c=><tr key={c.candidate_id}><td>{c.symbol}<div className="muted small">{c.candidate_id}</div></td><td>{c.side}</td><td>{c.entry}</td><td>{c.stop_loss}</td><td>{c.target}</td><td>{c.confidence}/100</td><td>{c.status}</td><td>{c.status==='PENDING'?<div className="actions"><button onClick={()=>decideCandidate(c.candidate_id,'APPROVED')}>Approve</button><button className="secondary" onClick={()=>decideCandidate(c.candidate_id,'REJECTED')}>Reject</button></div>:'—'}</td></tr>):<tr><td colSpan="8">No candidates received. Candidate generation is not yet automated in this release.</td></tr>}</tbody></table></section>
    <section className="panel"><div className="panel-title"><Activity/> Immutable audit ledger <button className="secondary" onClick={async()=>{try{const v=await call('/api/audit/verify');setNotice(v.valid?`Audit chain verified: ${v.verified_events} events.`:`Audit chain integrity failure at sequence ${v.failed_seq}.`)}catch(e){setError(e.message)}}}>Verify chain</button></div><p className="muted small">Append-only SQLite event log with SHA-256 hash chaining. API actions, trade candidates, decisions, order events and safety controls are timestamped.</p><table><thead><tr><th>Time (UTC)</th><th>Event</th><th>Entity</th><th>Hash</th></tr></thead><tbody>{audit.length?audit.map(e=><tr key={e.event_id}><td>{e.occurred_at}</td><td>{e.event_type}</td><td>{e.entity_id||'—'}</td><td>{e.event_hash?.slice(0,14)}…</td></tr>):<tr><td colSpan="4">No audit events yet</td></tr>}</tbody></table></section><footer>Development release v2.0 · Paper mode · Live execution disabled · Not production-cleared.</footer>
  </div>
}
function Metric({title,value}){return <div className="metric"><span>{title}</span><strong>{value}</strong></div>}
