from __future__ import annotations
import argparse,json,math,time,zipfile
from dataclasses import dataclass,asdict
from datetime import datetime,timezone
from pathlib import Path
import numpy as np,pandas as pd,requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

U=['BTCUSDT','ETHUSDT','BNBUSDT','SOLUSDT','XRPUSDT','DOGEUSDT','ADAUSDT','LINKUSDT','AVAXUSDT','DOTUSDT','LTCUSDT','BCHUSDT','TRXUSDT','NEARUSDT','ETCUSDT']
START=pd.Timestamp('2021-01-01',tz='UTC'); SPLIT=pd.Timestamp('2024-01-01',tz='UTC'); END=pd.Timestamp('2026-07-25',tz='UTC')
BASE=.0006; STRESS=.0012; RISK=.002; MAXPOS=.25; MAXGROSS=1.2; MAXOPEN=6; MAXDAY=10

def sess():
 s=requests.Session(); r=Retry(total=8,backoff_factor=.7,status_forcelist=[418,429,500,502,503,504],allowed_methods=['GET']); s.mount('https://',HTTPAdapter(max_retries=r,pool_connections=30,pool_maxsize=30)); return s

def getbars(sym,s):
 out=[]; cur=int(START.timestamp()*1000); end=int(END.timestamp()*1000)
 while cur<end:
  x=s.get('https://fapi.binance.com/fapi/v1/klines',params={'symbol':sym,'interval':'1h','startTime':cur,'endTime':end-1,'limit':1500},timeout=30); x.raise_for_status(); b=x.json()
  if not b: break
  out+=b; nxt=int(b[-1][0])+3600000
  if nxt<=cur: break
  cur=nxt; time.sleep(.04)
 if not out:return pd.DataFrame()
 d=pd.DataFrame(out,columns=['ot','open','high','low','close','volume','ct','qv','n','tb','tq','ig']); d['time']=pd.to_datetime(d.ot,unit='ms',utc=True)
 for c in ['open','high','low','close','volume','qv']:d[c]=pd.to_numeric(d[c],errors='coerce')
 return d[['time','open','high','low','close','volume','qv']].drop_duplicates('time').sort_values('time').query('time<@END').reset_index(drop=True)

def getfund(sym,s):
 out=[];cur=int(START.timestamp()*1000);end=int(END.timestamp()*1000)
 while cur<end:
  x=s.get('https://fapi.binance.com/fapi/v1/fundingRate',params={'symbol':sym,'startTime':cur,'endTime':end-1,'limit':1000},timeout=30)
  if x.status_code==400:break
  x.raise_for_status();b=x.json()
  if not b:break
  out+=b;nxt=int(b[-1]['fundingTime'])+1
  if nxt<=cur:break
  cur=nxt;time.sleep(.04)
 if not out:return {}
 d=pd.DataFrame(out);d['time']=pd.to_datetime(d.fundingTime,unit='ms',utc=True).dt.floor('h');d['rate']=pd.to_numeric(d.fundingRate)
 return dict(zip(d.time,d.rate))

def wild(x,n):return x.ewm(alpha=1/n,adjust=False,min_periods=n).mean()
def feat(d,sym):
 x=d.copy();pc=x.close.shift();tr=pd.concat([x.high-x.low,(x.high-pc).abs(),(x.low-pc).abs()],axis=1).max(axis=1);x['atr']=wild(tr,14)
 up=x.high.diff();dn=-x.low.diff();p=pd.Series(np.where((up>dn)&(up>0),up,0),index=x.index);m=pd.Series(np.where((dn>up)&(dn>0),dn,0),index=x.index)
 pdi=100*wild(p,14)/x.atr;mdi=100*wild(m,14)/x.atr;x['adx']=wild(100*(pdi-mdi).abs()/(pdi+mdi),14)
 for n in [20,50,200]:x[f'e{n}']=x.close.ewm(span=n,adjust=False,min_periods=n).mean()
 for n in [12,24,48]:x[f'hi{n}']=x.high.rolling(n).max().shift();x[f'lo{n}']=x.low.rolling(n).min().shift()
 x['mom24']=x.close.pct_change(24);x['mom72']=x.close.pct_change(72);x['atrp']=x.atr/x.close;x['rv']=x.volume/x.volume.rolling(20).mean();x['q24']=x.qv.rolling(24).sum();x['rank']=np.nan;x['sym']=sym;x['hist']=np.arange(len(x))>=4320
 x['cp']=(x.close-x.low)/(x.high-x.low).replace(0,np.nan);return x

@dataclass(frozen=True)
class C:
 fam:str;lb:int;adx:int;rv:float;sl:float;rr:float;hold:int;extra:float=0
 @property
 def name(self):return f'{self.fam}_lb{self.lb}_a{self.adx}_v{self.rv}_s{self.sl}_r{self.rr}_h{self.hold}_x{self.extra}'

def configs():
 z=[]
 for lb in [12,24,48]:
  for a in [18,22]:
   for v in [1,1.2]:z+=[C('break',lb,a,v,1.5,2,12),C('break',lb,a,v,2,2,24)]
 for lb in [20,50]:
  for a in [18,22]:
   for v in [1,1.2]:z+=[C('pull',lb,a,v,1.5,2,12),C('pull',lb,a,v,2,2,24)]
 for interval in [6,12]:
  for q in [.15,.2]:
   for a in [18,22]:z+=[C('xsec',interval,a,.8,1.5,2,12,q),C('xsec',interval,a,.8,2,2,24,q)]
 return z

def signals(x,c):
 ok=x['hist']&(x.q24>=5e6)&x.atr.notna()&x.adx.notna();up=(x.close>x.e200)&(x.e50>x.e200)&(x.mom72>0);dn=(x.close<x.e200)&(x.e50<x.e200)&(x.mom72<0)
 if c.fam=='break':
  L=ok&up&(x.close>x[f'hi{c.lb}'])&(x.adx>=c.adx)&(x.rv>=c.rv);S=ok&dn&(x.close<x[f'lo{c.lb}'])&(x.adx>=c.adx)&(x.rv>=c.rv);strength=((x.close-x[f'hi{c.lb}']).abs()/x.atr).clip(0,4)
 elif c.fam=='pull':
  e=x[f'e{c.lb}'];L=ok&up&(x.low<=e+.15*x.atr)&(x.close>e)&(x.cp>=.6)&(x.adx>=c.adx)&(x.rv>=c.rv);S=ok&dn&(x.high>=e-.15*x.atr)&(x.close<e)&(x.cp<=.4)&(x.adx>=c.adx)&(x.rv>=c.rv);strength=((x.close-e).abs()/x.atr).clip(0,4)
 else:
  fixed=(x.time.dt.hour%c.lb)==0;L=ok&fixed&up&(x['rank']>=1-c.extra)&(x.adx>=c.adx)&(x.rv>=c.rv);S=ok&fixed&dn&(x['rank']<=c.extra)&(x.adx>=c.adx)&(x.rv>=c.rv);strength=((x['rank']-.5).abs()*4).clip(0,4)
 side=np.where(L,1,np.where(S,-1,0));mask=side!=0;score=(x.adx/25).clip(0,3)+x.rv.clip(0,3)+(x.mom24.abs()/x.atrp).clip(0,4)*.25+strength
 o=x.loc[mask,['time','sym','atr']].copy();o['entry_time']=o.time+pd.Timedelta(hours=1);o['signal_time']=o.time;o['side']=side[mask];o['score']=score[mask].to_numpy();o['sl']=c.sl;o['rr']=c.rr;o['hold']=c.hold;o['config']=c.name
 return o[['entry_time','signal_time','sym','side','score','atr','sl','rr','hold','config']]

def pf(v):
 g=v[v>0].sum();l=-v[v<0].sum();return float(g/l) if l>0 else (math.inf if g>0 else math.nan)
def dd(v):
 a=np.asarray(v,float);return float(np.min(a/np.maximum.accumulate(a)-1)) if len(a) else 0

def simulate(cands,frames,funds,start,end,cost,fscale=1):
 c=cands[(cands.entry_time>=start)&(cands.entry_time<end)].sort_values(['entry_time','score'],ascending=[True,False]);groups={t:g for t,g in c.groupby('entry_time')};times=pd.date_range(start,end-pd.Timedelta(hours=1),freq='1h',tz='UTC')
 bars={s:{r.time:(r.open,r.high,r.low,r.close) for r in f.query('time>=@start and time<@end')[['time','open','high','low','close']].itertuples(index=False)} for s,f in frames.items()};eq=1.;pos={};tr=[];curve=[];day=None;day0=1.;new=0;losses=0;block=False
 def close(s,t,raw,why):
  nonlocal eq,losses
  p=pos.pop(s);ex=raw*(1-p['side']*cost*.35);gross=p['side']*(ex-p['entry'])*p['qty'];fees=cost*.65*(p['entry']+ex)*p['qty'];net=gross-fees+p['fund'];eq+=gross-fees;R=net/p['risk'] if p['risk'] else np.nan
  if net<=0:losses+=1
  tr.append(dict(config=p['config'],symbol=s,side=p['side'],signal_time=p['signal'],entry_time=p['time'],exit_time=t,entry=p['entry'],stop=p['stop'],target=p['target'],exit=ex,reason=why,notional=p['notional'],risk_cash=p['risk'],gross_pnl=gross,fees=fees,funding_pnl=p['fund'],net_pnl=net,r=R,hold_hours=int((t-p['time']).total_seconds()/3600)))
 for t in times:
  if t.date()!=day:day=t.date();day0=eq;new=0;losses=0;block=False
  for s,p in list(pos.items()):
   rate=funds.get(s,{}).get(t,0)*fscale
   if rate:fp=-p['side']*rate*p['notional'];p['fund']+=fp;eq+=fp
  for s in list(pos):
   b=bars.get(s,{}).get(t)
   if not b:continue
   o,h,l,cl=b;p=pos[s];q=p['side']
   if t>=p['expiry']:close(s,t,o,'TIME');continue
   if q==1:
    if o<=p['stop']:close(s,t,o,'STOP_GAP')
    elif o>=p['target']:close(s,t,o,'TP_GAP')
    elif l<=p['stop']:close(s,t,p['stop'],'STOP')
    elif h>=p['target']:close(s,t,p['target'],'TP')
   else:
    if o>=p['stop']:close(s,t,o,'STOP_GAP')
    elif o<=p['target']:close(s,t,o,'TP_GAP')
    elif h>=p['stop']:close(s,t,p['stop'],'STOP')
    elif l<=p['target']:close(s,t,p['target'],'TP')
  marked=eq;gross_open=0;lc=sc=0
  for s,p in pos.items():
   b=bars.get(s,{}).get(t)
   if b:marked+=p['side']*(b[3]-p['entry'])*p['qty']-cost*.65*p['entry']*p['qty']
   gross_open+=p['notional'];lc+=p['side']==1;sc+=p['side']==-1
  block=block or marked<=day0*(1-.015) or losses>=3
  if not block and new<MAXDAY and len(pos)<MAXOPEN and t in groups:
   opened=0
   for r in groups[t].itertuples(index=False):
    if opened>=3 or new>=MAXDAY or len(pos)>=MAXOPEN:break
    if r.sym in pos or (r.side==1 and lc>=4) or (r.side==-1 and sc>=4):continue
    b=bars.get(r.sym,{}).get(t)
    if not b:continue
    entry=b[0]*(1+r.side*cost*.35);dist=r.sl*r.atr;sp=dist/entry
    if not .004<=sp<=.10:continue
    qty=eq*RISK/dist;room=max(0,MAXGROSS*eq-gross_open);notional=min(qty*entry,MAXPOS*eq,room)
    if notional<.02*eq:continue
    qty=notional/entry;pos[r.sym]=dict(config=r.config,side=int(r.side),signal=r.signal_time,time=t,entry=entry,stop=entry-r.side*dist,target=entry+r.side*r.rr*dist,expiry=t+pd.Timedelta(hours=int(r.hold)),qty=qty,notional=notional,risk=qty*dist,fund=0.)
    gross_open+=notional;new+=1;opened+=1;lc+=r.side==1;sc+=r.side==-1
  marked=eq
  for s,p in pos.items():
   b=bars.get(s,{}).get(t)
   if b:marked+=p['side']*(b[3]-p['entry'])*p['qty']-cost*.65*p['entry']*p['qty']
  curve.append((t,marked,eq,len(pos)))
 if len(times):
  t=times[-1]
  for s in list(pos):
   b=bars.get(s,{}).get(t)
   if b:close(s,t,b[3],'END')
  if curve:curve[-1]=(t,eq,eq,0)
 T=pd.DataFrame(tr);E=pd.DataFrame(curve,columns=['time','equity','realized_equity','positions']);days=max(1,(end-start).total_seconds()/86400);years=days/365.25;ret=E.equity.iloc[-1]-1 if len(E) else 0;mdd=dd(E.equity) if len(E) else 0;daily=E.set_index('time').equity.resample('1d').last().pct_change().dropna() if len(E) else pd.Series(dtype=float);sh=float(np.sqrt(365)*daily.mean()/daily.std()) if len(daily)>1 and daily.std()>0 else np.nan
 if len(T):
  pnl=T.net_pnl;rv=T.r;T['exit_time']=pd.to_datetime(T.exit_time,utc=True);wk=T.set_index('exit_time').net_pnl.resample('W-MON').sum();mo=T.set_index('exit_time').net_pnl.resample('MS').sum();active=pd.to_datetime(T.entry_time,utc=True).dt.date.nunique();ls=cur=0
  for v in pnl:cur=cur+1 if v<=0 else 0;ls=max(ls,cur)
  M=dict(trades=len(T),trades_per_day=len(T)/days,active_days=active,win_rate=float((pnl>0).mean()),profit_factor=pf(pnl),expectancy_r=float(rv.mean()),median_r=float(rv.median()),total_return=float(ret),cagr=float((1+ret)**(1/years)-1) if ret>-1 else -1,max_drawdown=mdd,sharpe=sh,positive_weeks=float((wk>0).mean()),positive_months=float((mo>0).mean()),longest_loss_streak=ls,fees=float(T.fees.sum()),funding_pnl=float(T.funding_pnl.sum()))
 else:M=dict(trades=0,trades_per_day=0,active_days=0,win_rate=np.nan,profit_factor=np.nan,expectancy_r=np.nan,median_r=np.nan,total_return=float(ret),cagr=0,max_drawdown=mdd,sharpe=sh,positive_weeks=np.nan,positive_months=np.nan,longest_loss_streak=0,fees=0,funding_pnl=0)
 return T,E,M

def score(m):
 if not np.isfinite(m.get('expectancy_r',np.nan)) or not np.isfinite(m.get('profit_factor',np.nan)):return -1e9
 return 3*m['expectancy_r']+.35*math.log(max(m['profit_factor'],1e-6))+.2*min(m['trades_per_day'],4)/4+.15*(m['sharpe'] if np.isfinite(m['sharpe']) else 0)+.5*m['max_drawdown']

def boot(T,n=5000):
 if not len(T):return{}
 v=T.r.to_numpy(float);g=np.random.default_rng(20260725);means=[];tot=[]
 for _ in range(n):s=g.choice(v,len(v),replace=True);means.append(s.mean());tot.append(s.sum())
 return dict(sims=n,mean_r_ci95_low=float(np.quantile(means,.025)),mean_r_ci95_high=float(np.quantile(means,.975)),prob_total_positive=float((np.array(tot)>0).mean()))

def ser(o):
 if isinstance(o,(np.integer,)):return int(o)
 if isinstance(o,(np.floating,)):return float(o)
 if isinstance(o,pd.Timestamp):return o.isoformat()
 if isinstance(o,dict):return {str(k):ser(v) for k,v in o.items()}
 if isinstance(o,list):return [ser(v) for v in o]
 return o

def main(out):
 out.mkdir(parents=True,exist_ok=True);cache=out/'cache';cache.mkdir(exist_ok=True);s=sess();frames={};funds={};audit=[]
 for sym in U:
  bp=cache/f'{sym}.csv.gz';fp=cache/f'{sym}_fund.csv.gz'
  if bp.exists():d=pd.read_csv(bp);d['time']=pd.to_datetime(d.time,utc=True)
  else:print('download',sym,flush=True);d=getbars(sym,s);d.to_csv(bp,index=False,compression='gzip') if len(d) else None
  if len(d)<1000:continue
  if fp.exists():f=pd.read_csv(fp);f['time']=pd.to_datetime(f.time,utc=True);fm=dict(zip(f.time,f.rate))
  else:fm=getfund(sym,s);pd.DataFrame({'time':list(fm),'rate':list(fm.values())}).to_csv(fp,index=False,compression='gzip')
  x=feat(d,sym);frames[sym]=x;funds[sym]=fm;expected=int((x.time.max()-x.time.min()).total_seconds()/3600)+1;audit.append(dict(symbol=sym,rows=len(x),start=x.time.min(),end=x.time.max(),coverage=len(x)/expected,funding_rows=len(fm),latest_quote24=float(x.q24.dropna().iloc[-1])))
 if len(frames)<8:raise RuntimeError('insufficient universe')
 allm=pd.concat([x[['time','sym','mom24']] for x in frames.values()]);ranks=allm.groupby('time').mom24.rank(pct=True)
 allm['rank']=ranks
 for sym,g in allm.groupby('sym'):
  rank_map=dict(zip(g.time,g['rank']))
  frames[sym]['rank']=frames[sym].time.map(rank_map)
 CAND={};lead=[]
 for i,c in enumerate(configs(),1):
  p=[signals(x,c) for x in frames.values()];cand=pd.concat([q for q in p if len(q)],ignore_index=True) if any(len(q) for q in p) else pd.DataFrame();CAND[c.name]=cand;T,E,M=simulate(cand,frames,funds,START,SPLIT,BASE);lead.append({**asdict(c),'name':c.name,**M,'selection_score':score(M)});print(i,len(configs()),flush=True) if i%10==0 else None
 L=pd.DataFrame(lead).sort_values('selection_score',ascending=False);V=L[(L.trades>=200)&(L.expectancy_r>0)&(L.profit_factor>1)&(L.trades_per_day<=10)];row=(V.iloc[0] if len(V) else L.iloc[0]);base=next(c for c in configs() if c.name==row['name']);ov=[];OC={}
 for rr in [1.5,2,2.5,3]:
  q=CAND[base.name].copy();q['rr']=rr;q['config']=f'{base.name}_rr{rr}';T,E,M=simulate(q,frames,funds,START,SPLIT,BASE);ov.append(dict(rr=rr,**M,selection_score=score(M)));OC[rr]=q
 O=pd.DataFrame(ov).sort_values('selection_score',ascending=False);rr=float(O.iloc[0].rr);final=OC[rr];DT,DE,DM=simulate(final,frames,funds,START,SPLIT,BASE);TT,TE,TM=simulate(final,frames,funds,SPLIT,END,BASE);ST,SE,SM=simulate(final,frames,funds,SPLIT,END,STRESS,1.5);B=boot(TT)
 if len(TT):SS=TT.groupby('symbol').agg(trades=('r','size'),win_rate=('net_pnl',lambda z:(z>0).mean()),net_pnl=('net_pnl','sum'),expectancy_r=('r','mean')).reset_index().sort_values('net_pnl',ascending=False);TT['entry_day']=pd.to_datetime(TT.entry_time,utc=True).dt.strftime('%Y-%m-%d');DS=TT.groupby('entry_day').agg(trades=('r','size'),net_pnl=('net_pnl','sum'),wins=('net_pnl',lambda z:(z>0).sum())).reset_index()
 else:SS=pd.DataFrame();DS=pd.DataFrame()
 latest=max(x.time.max() for x in frames.values());cur=final[final.signal_time==latest].sort_values('score',ascending=False).head(10)
 gates=dict(test_pf_ge_1_20=TM.get('profit_factor',0)>=1.2,test_expectancy_positive=TM.get('expectancy_r',-1)>0,stress_pf_gt_1=SM.get('profit_factor',0)>1,stress_expectancy_positive=SM.get('expectancy_r',-1)>0,frequency_4_to_10=4<=TM.get('trades_per_day',0)<=10,max_dd_under_20pct=TM.get('max_drawdown',-1)>=-.2,positive_months_ge_55pct=TM.get('positive_months',0)>=.55,bootstrap_prob_ge_90pct=B.get('prob_total_positive',0)>=.9,bootstrap_ci_low_positive=B.get('mean_r_ci95_low',-1)>0);verdict='PILOT_LIVE_1X' if all(gates.values()) else 'PAPER_ONLY_NO_LIVE';name=f'{base.name}_rr{rr}'
 S=dict(generated_at_utc=datetime.now(timezone.utc).isoformat(),universe=list(frames),development=[START.isoformat(),SPLIT.isoformat()],test=[SPLIT.isoformat(),END.isoformat()],selected_config={**asdict(base),'rr':rr,'name':name},dev=DM,test_base=TM,test_stress=SM,bootstrap=B,gates=gates,verdict=verdict,current_signal_time=latest,current_signal_count=len(cur),caveat='Current-liquid fixed basket creates survivorship bias; development tournament creates multiple-testing risk.')
 pd.DataFrame(audit).to_csv(out/'data_audit.csv',index=False);L.to_csv(out/'development_leaderboard.csv',index=False);O.to_csv(out/'rr_overlay.csv',index=False);TT.to_csv(out/'test_trades.csv',index=False);ST.to_csv(out/'stress_trades.csv',index=False);TE.to_csv(out/'test_equity.csv',index=False);SE.to_csv(out/'stress_equity.csv',index=False);SS.to_csv(out/'symbol_stats.csv',index=False);DS.to_csv(out/'daily_stats.csv',index=False);cur.to_csv(out/'current_signals.csv',index=False);(out/'summary.json').write_text(json.dumps(ser(S),indent=2,ensure_ascii=False))
 lines=['# COIN V12 — MULTI-ASSET STRONG-SETUP PORTFOLIO','',f'**Verdict: {verdict}**','',f'Universe: {", ".join(frames)}',f'Selected: `{name}`','','## Test results','','|Metric|Base|Stress|','|---|---:|---:|']
 for lab,k,fmt in [('Trades','trades','d'),('Trades/day','trades_per_day','.3f'),('Win rate','win_rate','.2%'),('PF','profit_factor','.3f'),('Expectancy R','expectancy_r','.3f'),('Return','total_return','.2%'),('CAGR','cagr','.2%'),('Max DD','max_drawdown','.2%'),('Positive months','positive_months','.2%')]:
  a=TM.get(k,np.nan);b=SM.get(k,np.nan);lines.append(f'|{lab}|{int(a) if fmt=="d" else format(a,fmt)}|{int(b) if fmt=="d" else format(b,fmt)}|')
 lines+=['','## Gates','','|Gate|Result|','|---|---|']+[f'|{k}|{"PASS" if v else "FAIL"}|' for k,v in gates.items()]+['','## Current signals']
 if len(cur):
  lines+=['','|Symbol|Side|Score|Time|','|---|---:|---:|---|']+[f'|{r.sym}|{"LONG" if r.side==1 else "SHORT"}|{r.score:.2f}|{r.signal_time}|' for r in cur.itertuples()]
 else:lines+=['','No strong setup on the latest completed hour.']
 lines+=['','## Caveat','','The universe is fixed from coins liquid today, so survivorship bias remains. Each coin still needs 180 days of history and $5m rolling 24h quote volume. Selection uses development only; test is locked. Fees, slippage and actual funding are included.']
 (out/'REPORT.md').write_text('\n'.join(lines))
 import matplotlib.pyplot as plt
 plt.figure(figsize=(12,6));plt.plot(TE.time,TE.equity,label='Base');plt.plot(SE.time,SE.equity,label='Stress');plt.legend();plt.title('COIN V12 Equity');plt.tight_layout();plt.savefig(out/'equity.png',dpi=150);plt.close()
 def xsafe(d):
  y=d.copy()
  for c in y.columns:
   if pd.api.types.is_datetime64_any_dtype(y[c]):y[c]=y[c].astype(str)
  return y
 with pd.ExcelWriter(out/'COIN_V12_MULTI_ASSET_BACKTEST.xlsx',engine='openpyxl') as w:
  xsafe(pd.DataFrame([{'verdict':verdict,'selected':name,**{f'base_{k}':v for k,v in TM.items()},**{f'stress_{k}':v for k,v in SM.items()}}])).to_excel(w,'00_Dashboard',index=False);xsafe(pd.DataFrame(audit)).to_excel(w,'01_Data_Audit',index=False);xsafe(L.head(100)).to_excel(w,'02_Leaderboard',index=False);xsafe(O).to_excel(w,'03_RR_Overlay',index=False);xsafe(TT).to_excel(w,'04_Test_Trades',index=False);xsafe(SS).to_excel(w,'05_Symbol_Stats',index=False);xsafe(DS).to_excel(w,'06_Daily_Stats',index=False);xsafe(cur).to_excel(w,'07_Current',index=False);xsafe(TE).to_excel(w,'08_Equity',index=False)
 with zipfile.ZipFile(out/'COIN_V12_MULTI_ASSET_PACKAGE.zip','w',zipfile.ZIP_DEFLATED) as z:
  for p in out.iterdir():
   if p.is_file() and p.name!='COIN_V12_MULTI_ASSET_PACKAGE.zip':z.write(p,p.name)
 print(json.dumps(ser(S),indent=2,ensure_ascii=False))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('coin_research/v12/results'));a=p.parse_args();main(a.output)
