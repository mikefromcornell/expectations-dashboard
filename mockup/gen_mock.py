"""Generate deterministic mock data for the design mockup. NOT production code."""
import yaml, json, random, hashlib
from datetime import date, timedelta

TODAY = date(2026,7,30)
wl = yaml.safe_load(open('config/watchlist.yaml'))['tickers']

def seeded(sym, salt=""):
    h = hashlib.md5((sym+salt).encode()).hexdigest()
    return random.Random(int(h[:8],16))

# tickers with <12mo trading history -> no true 52wk range
NEW_LISTINGS = {"AVEX","GEMI","BLSH","FIGR"}
# conservatorship / metrics not meaningful
SUPPRESS_FUND = {"FNMA","FMCC"}
THIN = {"SMEGF"}
ALIAS = {"FISV":"FI"}

SECTORS = {
 "AMZN":"Cons. Disc.","CPRI":"Cons. Disc.","GEMI":"Financials","SRRK":"Healthcare","ADBE":"Technology",
 "AVGO":"Technology","GOOGL":"Comm. Svcs","VIRT":"Financials","CPRT":"Industrials","GPC":"Cons. Disc.",
 "STNG":"Energy","BRK-B":"Financials","FICO":"Technology","LHX":"Industrials","CROX":"Cons. Disc.",
 "EFX":"Industrials","ODFL":"Industrials","BRO":"Financials","ZETA":"Technology","CRM":"Technology",
 "FISV":"Technology","CLH":"Industrials","UBER":"Industrials","ALLE":"Industrials","PFE":"Healthcare",
 "COST":"Cons. Staples","AAPL":"Technology","LAMR":"Real Estate","HEI":"Industrials","COP":"Energy",
 "XOM":"Energy","MIR":"Industrials","DASH":"Cons. Disc.","ZM":"Technology","CVX":"Energy",
 "CARR":"Industrials","ELV":"Healthcare","TECH":"Healthcare","FNMA":"Financials","FMCC":"Financials",
 "UNH":"Healthcare","MA":"Financials","PGY":"Financials","AVEX":"Industrials","INTC":"Technology",
 "AMD":"Technology","MSFT":"Technology","ETN":"Industrials","BLSH":"Financials","IDYA":"Healthcare",
 "FIGR":"Financials","MELI":"Cons. Disc.","IBM":"Technology","V":"Financials","SPGI":"Financials",
 "NVO":"Healthcare","ASML":"Technology","BABA":"Cons. Disc.","JD":"Cons. Disc.","TSM":"Technology",
 "SMEGF":"Industrials","MRAAY":"Technology","EVVTY":"Cons. Disc.",
}

rows=[]
for t in wl:
    s=t['symbol']; r=seeded(s)
    price = round(r.uniform(12, 640),2)
    is_new = s in NEW_LISTINGS
    if is_new:
        lo = round(price*r.uniform(0.72,0.92),2); hi=round(price*r.uniform(1.05,1.35),2)
    else:
        lo = round(price*r.uniform(0.55,0.93),2); hi=round(price*r.uniform(1.03,1.75),2)
    pct_hi = round((price-hi)/hi*100,1)
    pct_lo = round((price-lo)/lo*100,1)
    pos = round((price-lo)/(hi-lo)*100,1) if hi>lo else 50.0
    chg = round(r.uniform(-4.2,4.2),2)

    etf = t['type']=='etf'
    supp = s in SUPPRESS_FUND

    # earnings bucket
    if etf:
        edays=None
    else:
        edays = r.choice([-3,-2,-1,0,1,2,3,5,7,9,12,18,25,34,47,61])
    ed = (TODAY+timedelta(days=edays)).isoformat() if edays is not None else None

    def m(lo_,hi_,nd=1):
        return None if (etf or supp) else round(r.uniform(lo_,hi_),nd)

    row = dict(
        symbol=s, name=t['name'], type=t['type'], sector=SECTORS.get(s,"—" if etf else "Other"),
        price=price, change_pct=chg, high52=hi, low52=lo,
        pct_from_high=pct_hi, pct_from_low=pct_lo, pos52=pos,
        earnings_date=ed, earnings_days=edays, earnings_confirmed=(r.random()>0.4),
        pe_ltm=m(8,62), pe_fwd=m(7,48), ev_ebitda=m(4,34), roic=m(-4,38),
        insider=r.choice([None,None,None,"buy","buy","sell"]) if not etf else None,
        politician=r.choice([None,None,None,None,"buy","sell"]) if not etf else None,
        superinv=r.choice([None,None,None,"add","new","trim"]) if not etf else None,
        fair_value=None, new_listing=is_new, suppressed=supp, thin=s in THIN,
        alias=ALIAS.get(s),
        stale=(s in {"SMEGF","MRAAY"}),
    )
    # a subset has user-entered fair value -> expectations gap
    if not etf and not supp and r.random()<0.55:
        row['fair_value']=round(price*r.uniform(0.6,1.7),2)
        row['gap_pct']=round((row['fair_value']-price)/price*100,1)
    else:
        row['gap_pct']=None

    # ---- Expectations Score (mock, mirrors PRD 5.6 weights) ----
    if etf or supp:
        row['score']=None; row['score_parts']=[]
    else:
        parts=[]
        def add(k,label,w,v,detail):
            parts.append(dict(key=k,label=label,weight=w,score=(round(v,2) if v is not None else None),detail=detail))
        g=row['gap_pct']
        if g is None:
            add('expectations_gap','Expectations gap',0.35,None,'No fair value set — add one in expectations.yaml')
        else:
            v=max(0,min(1,0.5+g/120))
            add('expectations_gap','Expectations gap',0.35,v,
                f"Your fair value ${row['fair_value']:.2f} vs price ${price:.2f} → {g:+.1f}%")
        v=max(0,min(1,1-pos/100))
        add('position_52wk','52-week position',0.20,v,
            f"{pct_lo:+.1f}% above 52-wk low, {pct_hi:+.1f}% from high — {pos:.0f}th pct of range")
        if row['pe_ltm']:
            pct=r.uniform(0,100); v=max(0,min(1,1-pct/100))
            add('valuation_vs_history','Valuation vs own history',0.15,v,
                f"LTM P/E {row['pe_ltm']} — {pct:.0f}th percentile of its own 5-yr range")
        else:
            add('valuation_vs_history','Valuation vs own history',0.15,None,'No P/E available')
        if row['roic'] is not None:
            tr=r.choice(['improving','stable','deteriorating'])
            v={'improving':0.8,'stable':0.55,'deteriorating':0.25}[tr]
            add('roic_trend','ROIC trend',0.10,v,f"ROIC {row['roic']}% and {tr} over 3 yrs")
        else:
            add('roic_trend','ROIC trend',0.10,None,'ROIC not computable')
        ins=row['insider']
        v={'buy':0.85,'sell':0.2,None:0.5}[ins]
        add('insider_activity','Insider activity',0.10,v,
            {'buy':'Net open-market buying in last 90d','sell':'Net insider selling in last 90d',None:'No Form 4 activity in 90d'}[ins])
        sv=row['superinv']
        v={'add':0.8,'new':0.9,'trim':0.25,None:0.5}[sv]
        add('superinvestor_flow','Superinvestor flow',0.10,v,
            {'add':'2 managers added last quarter','new':'New position initiated by a tracked manager','trim':'Position trimmed by a tracked manager',None:'No Dataroma change'}[sv])
        avail=[p for p in parts if p['score'] is not None]
        tw=sum(p['weight'] for p in avail)
        row['score']=round(sum(p['score']*p['weight'] for p in avail)/tw,3) if tw else None
        row['score_partial']=len(avail)<len(parts)
        row['score_n']=f"{len(avail)} of {len(parts)}"
        row['score_parts']=parts
    rows.append(row)

json.dump(rows, open('mockup/mock_data.json','w'), indent=1)
print("rows:",len(rows))
print("with score:",sum(1 for r in rows if r['score'] is not None))
print("etfs:",sum(1 for r in rows if r['type']=='etf'))
