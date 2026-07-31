"""Orchestrator: fetch -> compute -> write data/*.json

Stages are independent so a failure in one never blocks the others, and every
ticker isolates its own errors (PRD §5.7).

    python -m src.build --stage quotes
    python -m src.build --stage fundamentals
    python -m src.build --stage ownership
    python -m src.build --stage all
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone

from .config import (DATA, load_auto_fv, load_buffett, load_expectations, load_scoring,
                     load_watchlist)
from .metrics.buffett import apply_buffett, portfolio_observations
from .metrics.portfolio import compute as compute_portfolio
from .metrics.scoring import apply_score, rating
from .models import TickerResult
from .providers import fundamentals as fund
from .providers import earnings as earn
from .providers import ownership as own
from .providers.quotes import (
    annualised_return, annualised_vol, beta_vs, downside_deviation, fetch_quote, from_yahoo,
)

DATA.mkdir(exist_ok=True)
STAMP = lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")  # noqa: E731


def _write(name: str, payload) -> None:
    p = DATA / name
    p.write_text(json.dumps(payload, indent=1, default=str))
    print(f"  wrote {p.relative_to(DATA.parent)} ({p.stat().st_size:,} bytes)")


def _load_previous() -> dict[str, dict]:
    """Previous tickers.json keyed by symbol.

    Partial stages MUST merge onto this. Without it the 15-minute quotes job
    would blank out fundamentals and ownership on every run.
    """
    p = DATA / "tickers.json"
    if not p.exists():
        return {}
    try:
        return {r["symbol"]: r for r in json.loads(p.read_text())}
    except Exception:
        return {}


# fields owned by each stage — used to carry values forward when a stage is skipped
_FUND_FIELDS = (
    "pe_ltm", "pe_fwd", "ev_ebitda", "ps_ratio", "revenue", "roic", "roic_trend",
    "debt_equity", "fcf_margin",
    "market_cap", "sector", "earnings_date", "earnings_days", "earnings_confirmed",
)
_OWN_FIELDS = (
    "insider", "insider_detail", "politician", "politician_detail",
    "superinv", "superinv_detail",
)


def build(stage: str = "all", limit: int | None = None) -> int:
    wl = load_watchlist()
    if limit:
        wl = wl[:limit]
    prev = _load_previous()
    if stage != "all" and prev:
        print(f"  merging onto {len(prev)} previously built tickers")
    scoring, buff_cfg, expectations = load_scoring(), load_buffett(), load_expectations()
    auto_fv = load_auto_fv()
    print(f"» {len(wl)} tickers · stage={stage}")

    results: list[TickerResult] = []
    bench_closes: list[float] = []
    try:
        from .providers.quotes import fetch_quote as _fq
        _b, _ = _fq("SPY", True)
        bench_closes = (_b.closes if _b else [])
    except Exception as exc:  # noqa: BLE001
        print(f"  ! benchmark SPY unavailable ({str(exc)[:80]}) — beta will be null")

    earn_map: dict = {}
    if stage in ("all", "fundamentals"):
        try:
            eq_syms = {t.symbol for t in wl if t.type != "etf"}
            earn_map = earn.sweep(eq_syms)
            print(f"  Earnings calendar: {len(earn_map)}/{len(eq_syms)} dated")
        except Exception as exc:  # noqa: BLE001
            print(f"  ! earnings sweep failed: {str(exc)[:80]}")

    cik_map = {}
    dataroma_acts: dict = {}
    pol: dict = {}
    if stage in ("all", "ownership"):
        try:
            cik_map = own.load_cik_map()
            print(f"  EDGAR registry: {len(cik_map):,} tickers")
        except Exception as exc:  # noqa: BLE001
            print(f"  ! EDGAR registry failed: {str(exc)[:80]}")
        try:
            payload, how = own.fetch_dataroma()
            dataroma_acts = payload.get("activity", {})
            _write("discovery.json", {
                "generated": STAMP(),
                "fetched": payload.get("fetched"),
                "how": how,
                "clusters": payload.get("clusters", []),
                "recent": payload.get("recent", []),
                "watchlist": sorted({t.symbol for t in wl}),
            })
            print(f"  Dataroma: {len(dataroma_acts)} names, "
                  f"{len(payload.get('clusters', []))} clusters ({how})")
        except Exception as exc:  # noqa: BLE001
            print(f"  ! Dataroma failed: {str(exc)[:80]}")
        try:
            pol = own.politician_trades({t.symbol for t in wl})
            print(f"  Politician ticker-level trades: {len(pol)}")
        except Exception as exc:  # noqa: BLE001
            print(f"  ! politician feed failed: {str(exc)[:80]}")
        try:
            house_idx = own.house_filing_index()
            _write("politicians.json", {
                "generated": STAMP(),
                "ticker_level_available": bool(pol),
                "note": (
                    "Ticker-level STOCK Act mirrors (House/Senate Stock Watcher) returned 403 as of "
                    "2026-07-30, so this is the official House Clerk filing index: it shows that new "
                    "periodic transaction reports exist and links the source PDFs, but does not claim "
                    "which tickers were traded. Enable a ticker-level source to populate the badges."
                ),
                **house_idx,
            })
            print(f"  House Clerk filings (120d): {len(house_idx.get('filings', []))}")
        except Exception as exc:  # noqa: BLE001
            print(f"  ! house index failed: {str(exc)[:80]}")

    for i, t in enumerate(wl, 1):
        r = TickerResult(symbol=t.symbol, name=t.name, type=t.type, sector=t.sector)
        r.weight_pct = t.weight
        r.alias = t.historical_alias
        r.thin = t.thin_liquidity
        r.suppressed = t.suppress_fundamentals

        # ---- quotes ----
        q, errs = fetch_quote(t.quote_symbol, t.is_fund)
        for e in errs:
            r.add_error("quote", e)
        if q:
            r.price, r.change_pct = q.price, q.change_pct
            r.high52, r.low52 = q.high52, q.low52
            r.currency = q.currency
            r.sources["quote"] = q.source
            if q.high52 and q.low52 and q.price and q.high52 > q.low52:
                r.pct_from_high = (q.price - q.high52) / q.high52 * 100
                r.pct_from_low = (q.price - q.low52) / q.low52 * 100
                r.pos52 = (q.price - q.low52) / (q.high52 - q.low52) * 100
            if q.closes:
                r.new_listing = q.history_days < 252
                r.vol30 = annualised_vol(q.closes)
                r.downdev = downside_deviation(q.closes)
                r.ret1y = annualised_return(q.closes)
                if bench_closes:
                    r.beta = beta_vs(q.closes, bench_closes)
            if r.new_listing:
                r.pct_from_high = r.pct_from_low = r.pos52 = None
        else:
            r.stale = True

        # ---- fundamentals ----
        if stage in ("all", "fundamentals") and t.type != "etf" and not t.suppress_fundamentals:
            f, ferrs = fund.fetch_fundamentals(t.quote_symbol, r.price)
            for e in ferrs:
                r.add_error("fundamentals", e)
            r.pe_ltm, r.pe_fwd = f.get("pe_ltm"), f.get("pe_fwd")
            r.ev_ebitda, r.roic = f.get("ev_ebitda"), f.get("roic")
            r.ps_ratio, r.revenue = f.get("ps_ratio"), f.get("revenue")
            r.debt_equity, r.fcf_margin = f.get("debt_equity"), f.get("fcf_margin")
            r.market_cap = f.get("market_cap")
            r.sector = r.sector or f.get("sector")
            e = earn_map.get(t.symbol)
            if e:
                r.earnings_date, r.earnings_confirmed = e["date"], e["confirmed"]
            else:
                r.earnings_date = f.get("earnings_date")
                r.earnings_confirmed = bool(f.get("earnings_confirmed"))
            if f.get("source"):
                r.sources["fundamentals"] = f["source"]
        days, bucket = fund.earnings_bucket(r.earnings_date)
        r.earnings_days = days
        r.sources["earnings_bucket"] = bucket

        if t.catalyst:
            r.catalyst_date = str(t.catalyst.get("date")) if t.catalyst.get("date") else None
            r.catalyst_note = t.catalyst.get("note")

        # ---- ownership ----
        if stage in ("all", "ownership") and t.type != "etf":
            try:
                act, detail = own.insider_activity(t.symbol, cik_map)
                r.insider, r.insider_detail = act, detail
            except Exception as exc:  # noqa: BLE001
                r.add_error("insider", exc)
            p = pol.get(t.symbol)
            if p:
                r.politician, r.politician_detail = p["action"], p["detail"]
            d = dataroma_acts.get(t.symbol)
            if d:
                r.superinv, r.superinv_detail = d["action"], d["detail"]

        # ---- expectations ----
        # Precedence: explicit per-ticker fair_value  >  auto rule  >  none.
        exp = expectations.get(t.symbol) or {}
        r.fair_value = exp.get("fair_value", t.fair_value)
        r.fair_value_source = "manual" if r.fair_value else None

        if r.fair_value is None and auto_fv.get("enabled") and t.type != "etf" \
                and not t.suppress_fundamentals:
            # fair value = target P/E x LTM EPS.
            # EPS is not published directly by the provider, so derive it from
            # price / P/E — algebraically identical and uses data we already have.
            target_pe = float(auto_fv.get("target_pe", 20))
            if r.pe_ltm and r.pe_ltm > 0 and r.price:
                eps = r.price / r.pe_ltm
                if eps > 0:
                    r.fair_value = round(target_pe * eps, 2)
                    r.fair_value_source = f"auto: {target_pe:g}× LTM EPS ${eps:,.2f}"

        if r.fair_value and r.price:
            r.gap_pct = (r.fair_value - r.price) / r.price * 100

        # carry forward anything this stage did not refresh
        old = prev.get(t.symbol)
        if old:
            if stage not in ("all", "fundamentals"):
                for k in _FUND_FIELDS:
                    if getattr(r, k, None) in (None, "", False) and old.get(k) is not None:
                        setattr(r, k, old[k])
            if stage not in ("all", "ownership"):
                for k in _OWN_FIELDS:
                    ov = old.get(k)
                    if ov and getattr(r, k, None) in (None, "", "No Form 4 activity in 90d",
                                                      "No disclosures", "No Dataroma change"):
                        setattr(r, k, ov)
            # a failed quote should show the last good price, marked stale
            if r.price is None and old.get("price"):
                for k in ("price", "change_pct", "high52", "low52", "pct_from_high",
                          "pct_from_low", "pos52", "beta", "vol30", "downdev", "ret1y"):
                    if old.get(k) is not None:
                        setattr(r, k, old[k])
                r.stale = True
                r.sources["quote"] = (old.get("sources") or {}).get("quote", "cached") + " (stale)"

        apply_score(r, scoring)
        apply_buffett(r, buff_cfg, t.tags)
        results.append(r)

        flag = "!" if r.errors else " "
        sc = f"{r.score*100:>3.0f}%" if r.score is not None else "  — "
        print(f"  [{i:>2}/{len(wl)}]{flag} {t.symbol:<7} {sc}  "
              f"{'$%.2f' % r.price if r.price else 'no price':>10}")
        time.sleep(0.25)  # polite throttle

    # ---- outputs ----
    meta = {
        "generated": STAMP(),
        "tickers": len(results),
        "errors": sum(len(r.errors) for r in results),
        "quote_delay_note": "Quotes are delayed ~15 minutes. Sources: Yahoo → Stooq → Finnhub.",
        "sources": {
            "quotes": "Yahoo Finance (unofficial) with Stooq + Finnhub fallback",
            "fundamentals": "Yahoo quoteSummary; ROIC computed in-repo",
            "insiders": "SEC EDGAR Form 4",
            "politicians": "House/Senate Stock Watcher (STOCK Act, 45-day lag)",
            "superinvestors": "Dataroma (fetched at most every 72h)",
            "risk_free": "FRED DGS3MO",
        },
    }
    # --limit must never truncate the published dataset; keep untouched tickers
    payload = [r.to_dict() for r in results]
    if limit and prev:
        built = {r.symbol for r in results}
        payload += [v for k, v in prev.items() if k not in built]
    _write("tickers.json", payload)
    _write("meta.json", meta)
    _write("portfolio.json", compute_portfolio(results))
    _write("buffett.json", {
        "observations": portfolio_observations(results),
        "generated": STAMP(),
        "disclaimer": (
            "Deterministic checklist derived from Buffett's published criteria. Not affiliated "
            "with Berkshire Hathaway, not a prediction of his actions, not investment advice."
        ),
    })
    ranked = sorted([r for r in results if r.score is not None],
                    key=lambda r: r.score, reverse=True)
    _write("summary.json", {
        "generated": STAMP(),
        "top": [{"symbol": r.symbol, "score": r.score, "rating": rating(r.score, scoring)}
                for r in ranked[:10]],
        "errors": {r.symbol: r.errors for r in results if r.errors},
    })
    bad = [r.symbol for r in results if not r.price]
    print(f"» done · {len(results)} tickers · {len(bad)} without a price"
          + (f" ({', '.join(bad)})" if bad else ""))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all",
                    choices=["all", "quotes", "fundamentals", "ownership"])
    ap.add_argument("--limit", type=int, default=None)
    ns = ap.parse_args()
    sys.exit(build(ns.stage, ns.limit))
