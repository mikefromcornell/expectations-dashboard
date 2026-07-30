"""Keyless fundamentals from Nasdaq's public API.

Yahoo's quoteSummary rate-limits aggressively, so this is the primary
fundamentals source with Yahoo kept as a fallback. ROIC is computed here from
raw statement lines rather than taken from a vendor, so the formula is
auditable (PRD §4).
"""
from __future__ import annotations

from .http import FetchError, get_json

FINANCIALS = "https://api.nasdaq.com/api/company/{sym}/financials?frequency=1"
INFO = "https://api.nasdaq.com/api/quote/{sym}/info?assetclass={cls}"
SUMMARY = "https://api.nasdaq.com/api/quote/{sym}/summary?assetclass={cls}"

TAX_RATE = 0.21  # US statutory, used when effective rate is unavailable


def _money(v) -> float | None:
    if v in (None, "", "--", "N/A"):
        return None
    s = str(v).strip().replace("$", "").replace(",", "")
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        f = float(s)
    except ValueError:
        return None
    return -f if neg else f


def _rows(table: dict) -> dict[str, list[float | None]]:
    """{'Total Revenue': [latest, prior, ...]} — values are in thousands."""
    out: dict[str, list[float | None]] = {}
    for r in (table or {}).get("rows") or []:
        vals = list(r.values())
        if not vals:
            continue
        label = str(vals[0]).strip()
        out[label] = [_money(v) for v in vals[1:]]
    return out


def _first(d: dict, *names: str) -> float | None:
    for n in names:
        if n in d and d[n] and d[n][0] is not None:
            return d[n][0]
    for n in names:
        for k, v in d.items():
            if n.lower() in k.lower() and v and v[0] is not None:
                return v[0]
    return None


def fetch(sym: str, price: float | None = None, is_etf: bool = False) -> dict:
    cls = "etf" if is_etf else "stocks"
    out: dict = {"source": "nasdaq"}

    try:
        s = get_json(SUMMARY.format(sym=sym.upper(), cls=cls), cache_s=12 * 3600)
        sd = ((s or {}).get("data") or {}).get("summaryData") or {}
        out["sector"] = (sd.get("Sector") or {}).get("value")
        out["industry"] = (sd.get("Industry") or {}).get("value")
        mc = _money((sd.get("MarketCap") or {}).get("value"))
        out["market_cap"] = mc
    except Exception:
        pass

    d = get_json(FINANCIALS.format(sym=sym.upper()), cache_s=24 * 3600)
    data = (d or {}).get("data")
    if not data:
        raise FetchError("nasdaq financials: no data")

    inc = _rows(data.get("incomeStatementTable") or {})
    bal = _rows(data.get("balanceSheetTable") or {})
    cf = _rows(data.get("cashFlowTable") or {})
    if not inc:
        raise FetchError("nasdaq financials: empty income statement")

    K = 1000.0  # statements are reported in thousands
    revenue = (_first(inc, "Total Revenue") or 0) * K
    op_income = (_first(inc, "Operating Income") or 0) * K
    net_income = (_first(inc, "Net Income") or 0) * K
    tax = (_first(inc, "Income Tax") or 0) * K
    pretax = (_first(inc, "Pre-Tax Income", "Income Before Tax") or 0) * K

    cash = (_first(bal, "Cash and Cash Equivalents") or 0) * K
    sti = (_first(bal, "Short-Term Investments") or 0) * K
    equity = (_first(bal, "Total Equity") or 0) * K
    st_debt = (_first(bal, "Short-Term Debt") or 0) * K
    lt_debt = (_first(bal, "Long-Term Debt") or 0) * K
    total_debt = st_debt + lt_debt

    dep = (_first(cf, "Depreciation") or 0) * K
    capex = abs((_first(cf, "Capital Expenditures") or 0) * K)

    # ---- ROIC = NOPAT / invested capital ----
    if op_income and equity:
        eff_tax = (tax / pretax) if (pretax and tax) else TAX_RATE
        eff_tax = min(max(eff_tax, 0.0), 0.5)
        nopat = op_income * (1 - eff_tax)
        invested = total_debt + equity - cash - sti
        if invested > 0:
            out["roic"] = nopat / invested * 100.0
            out["roic_detail"] = (
                f"NOPAT ${nopat/1e9:.2f}B (op income ${op_income/1e9:.2f}B × "
                f"{1-eff_tax:.0%}) ÷ invested capital ${invested/1e9:.2f}B"
            )

    if revenue:
        fcf = (op_income + dep - capex) if op_income else None
        if fcf is not None:
            out["fcf_margin"] = fcf / revenue * 100.0
        ebitda = op_income + dep
        out["_ebitda"] = ebitda
        if out.get("market_cap") and ebitda > 0:
            ev = out["market_cap"] + total_debt - cash - sti
            out["ev_ebitda"] = ev / ebitda

    if equity:
        out["debt_equity"] = total_debt / equity if equity > 0 else None

    # P/E from EPS when a price is known
    shares = None
    eps = _first(inc, "Basic EPS", "EPS")
    if eps and price:
        try:
            out["pe_ltm"] = price / float(eps)
        except Exception:
            pass
    elif net_income and out.get("market_cap") and net_income > 0:
        out["pe_ltm"] = out["market_cap"] / net_income

    return out
