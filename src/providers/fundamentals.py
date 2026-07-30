"""Fundamentals + earnings dates.

ROIC is computed in-repo rather than taken from a vendor, because vendors
disagree wildly and an auditable formula beats a black box (PRD §4).
"""
from __future__ import annotations

import os
from datetime import date, datetime

from .http import FetchError, get_json

YAHOO_QS = (
    "https://query2.finance.yahoo.com/v10/finance/quoteSummary/{sym}"
    "?modules=defaultKeyStatistics,financialData,summaryProfile,calendarEvents,price"
)
FINNHUB_CAL = (
    "https://finnhub.io/api/v1/calendar/earnings?from={frm}&to={to}&symbol={sym}&token={key}"
)
FINNHUB_METRIC = "https://finnhub.io/api/v1/stock/metric?symbol={sym}&metric=all&token={key}"


def _num(v):
    if isinstance(v, dict):
        v = v.get("raw")
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def compute_roic(financial: dict, key_stats: dict) -> tuple[float | None, str]:
    """NOPAT / invested capital.

    invested capital = total debt + total equity - cash
    NOPAT approximated as EBIT * (1 - 21% statutory rate) when tax detail absent.
    """
    ebit = _num(financial.get("ebitda")) 
    if ebit is None:
        return None, "EBIT unavailable"
    da = _num(financial.get("depreciation")) or 0.0
    ebit = ebit - da if da else ebit
    debt = _num(financial.get("totalDebt")) or 0.0
    cash = _num(financial.get("totalCash")) or 0.0
    equity = _num(key_stats.get("bookValue"))
    shares = _num(key_stats.get("sharesOutstanding"))
    total_equity = (equity * shares) if (equity and shares) else None
    if not total_equity:
        return None, "book equity unavailable"
    invested = debt + total_equity - cash
    if invested <= 0:
        return None, "invested capital non-positive"
    nopat = ebit * (1 - 0.21)
    roic = nopat / invested * 100.0
    return roic, f"NOPAT {nopat/1e9:.2f}B ÷ invested capital {invested/1e9:.2f}B"


def from_yahoo(sym: str) -> dict:
    d = get_json(YAHOO_QS.format(sym=sym), cache_s=6 * 3600)
    res = (d or {}).get("quoteSummary", {}).get("result")
    if not res:
        raise FetchError("yahoo quoteSummary: no result")
    r = res[0]
    ks = r.get("defaultKeyStatistics", {}) or {}
    fd = r.get("financialData", {}) or {}
    prof = r.get("summaryProfile", {}) or {}
    cal = r.get("calendarEvents", {}) or {}
    price = r.get("price", {}) or {}

    roic, roic_detail = compute_roic(fd, ks)

    ev = _num(ks.get("enterpriseValue"))
    ebitda = _num(fd.get("ebitda"))
    ev_ebitda = (ev / ebitda) if (ev and ebitda and ebitda > 0) else None

    revenue = _num(fd.get("totalRevenue"))
    fcf = _num(fd.get("freeCashflow"))
    fcf_margin = (fcf / revenue * 100.0) if (fcf and revenue) else None

    de = _num(fd.get("debtToEquity"))
    if de is not None:
        de = de / 100.0  # yahoo reports as percent

    earnings_date, confirmed = None, False
    try:
        ed = (cal.get("earnings") or {}).get("earningsDate") or []
        if ed:
            ts = _num(ed[0])
            if ts:
                earnings_date = datetime.utcfromtimestamp(ts).date().isoformat()
                confirmed = len(ed) == 1
    except Exception:
        pass

    return {
        "pe_ltm": _num(ks.get("trailingPE")) or _num(price.get("trailingPE")),
        "pe_fwd": _num(ks.get("forwardPE")),
        "ev_ebitda": ev_ebitda,
        "roic": roic,
        "roic_detail": roic_detail,
        "debt_equity": de,
        "fcf_margin": fcf_margin,
        "market_cap": _num(price.get("marketCap")),
        "sector": prof.get("sector"),
        "earnings_date": earnings_date,
        "earnings_confirmed": confirmed,
        "source": "yahoo",
    }


def earnings_from_finnhub(sym: str) -> tuple[str | None, bool]:
    key = os.environ.get("FINNHUB_API_KEY")
    if not key:
        return None, False
    today = date.today()
    to = date(today.year + 1, today.month, 1)
    d = get_json(
        FINNHUB_CAL.format(frm=today.isoformat(), to=to.isoformat(), sym=sym, key=key),
        cache_s=12 * 3600,
    )
    rows = (d or {}).get("earningsCalendar") or []
    if not rows:
        return None, False
    rows.sort(key=lambda r: r.get("date", ""))
    return rows[0].get("date"), True


def fetch_fundamentals(sym: str, price: float | None = None) -> tuple[dict, list[str]]:
    """Nasdaq first (keyless, reliable), Yahoo second (rate-limits hard)."""
    from . import nasdaq_fund

    errors: list[str] = []
    out: dict = {}
    try:
        out = nasdaq_fund.fetch(sym, price=price)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"fundamentals/nasdaq: {str(exc)[:120]}")
    try:
        y = from_yahoo(sym)
        for k, v in y.items():
            if out.get(k) in (None, "") and v is not None:
                out[k] = v
    except Exception as exc:  # noqa: BLE001
        errors.append(f"fundamentals/yahoo: {str(exc)[:120]}")
    if not out.get("earnings_date"):
        try:
            ed, conf = earnings_from_finnhub(sym)
            if ed:
                out["earnings_date"] = ed
                out["earnings_confirmed"] = conf
        except Exception as exc:  # noqa: BLE001
            errors.append(f"earnings/finnhub: {str(exc)[:120]}")
    return out, errors


def earnings_bucket(earnings_date: str | None, today: date | None = None):
    """Returns (days_until, bucket). Bucket drives UI + alerts (Amendment C)."""
    if not earnings_date:
        return None, "na"
    today = today or date.today()
    try:
        d = datetime.fromisoformat(earnings_date).date()
    except Exception:
        return None, "na"
    days = (d - today).days
    if 0 <= days <= 3:
        return days, "imminent"
    if 4 <= days <= 10:
        return days, "approaching"
    if -3 <= days < 0:
        return days, "drift"  # expectations being repriced right now
    return days, "distant"
