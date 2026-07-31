"""Quarterly fundamentals from SEC XBRL company facts.

Free, keyless, official, and deep — most filers have quarterly revenue / net
income / EPS / share counts back to 2010. Nasdaq only exposes 4 annual periods,
which produces a 4-step staircase; this gives a real TTM series so the multiple
history and the return decomposition are meaningful.

Everything here is point-in-time: a quarter is only used from FILING_LAG_DAYS
after its period end, so historical multiples never benefit from data that
wasn't public yet (no look-ahead bias).
"""
from __future__ import annotations

from datetime import date, timedelta

from ..config import EDGAR_UA
from .http import FetchError, get_json

COMPANY_FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

# Filers tag the same concept differently; try in order of preference.
REVENUE_TAGS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
    "SalesRevenueGoodsNet",
    "RevenuesNetOfInterestExpense",
)
NET_INCOME_TAGS = ("NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic")
SHARES_TAGS = (
    "WeightedAverageNumberOfDilutedSharesOutstanding",
    "WeightedAverageNumberOfSharesOutstandingBasic",
    "WeightedAverageNumberOfBasicSharesOutstanding",
)
EQUITY_TAGS = ("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest")

FILING_LAG_DAYS = 45  # ~10-Q deadline; when a quarter becomes public knowledge
MIN_Q_DAYS, MAX_Q_DAYS = 80, 100


def _edgar_headers() -> dict:
    return {"User-Agent": EDGAR_UA, "Accept-Encoding": "gzip, deflate"}


def fetch_facts(cik: int) -> dict:
    return get_json(COMPANY_FACTS.format(cik=cik), headers=_edgar_headers(), cache_s=24 * 3600)


def _quarterly(gaap: dict, tags: tuple[str, ...]) -> dict[str, float]:
    """Non-overlapping quarterly values keyed by period end.

    Filers switch tags over time — NVDA reported `Revenues` until 2020 and
    `RevenueFromContractWithCustomer...` afterwards — so all tags are merged
    rather than stopping at the first that matches. Earlier tags in the tuple
    win where two cover the same quarter; within one tag, the latest filing
    wins (restatements).
    """
    merged: dict[str, tuple[float, str, int]] = {}
    for rank, tag in enumerate(tags):
        node = gaap.get(tag)
        if not node:
            continue
        for facts in node.get("units", {}).values():
            for f in facts:
                s, e = f.get("start"), f.get("end")
                if not s or not e:
                    continue
                try:
                    days = (date.fromisoformat(e) - date.fromisoformat(s)).days
                except ValueError:
                    continue
                if not (MIN_Q_DAYS <= days <= MAX_Q_DAYS):
                    continue
                filed = f.get("filed", "")
                prev = merged.get(e)
                if prev is None or rank < prev[2] or (rank == prev[2] and filed >= prev[1]):
                    merged[e] = (f["val"], filed, rank)
    return {k: v[0] for k, v in merged.items()}


def _instant(gaap: dict, tags: tuple[str, ...]) -> dict[str, float]:
    """Balance-sheet style facts (point in time, no start date)."""
    for tag in tags:
        node = gaap.get(tag)
        if not node:
            continue
        best: dict[str, tuple[float, str]] = {}
        for facts in node.get("units", {}).values():
            for f in facts:
                if f.get("start") or not f.get("end"):
                    continue
                prev = best.get(f["end"])
                filed = f.get("filed", "")
                if prev is None or filed >= prev[1]:
                    best[f["end"]] = (f["val"], filed)
        if best:
            return {k: v[0] for k, v in best.items()}
    return {}


def _split_adjust(shares: dict[str, float]) -> dict[str, float]:
    """Restate historical share counts onto the current post-split basis.

    SEC facts are as-filed, so a 20:1 split shows up as a 20x jump in share
    count on one quarter. Price history from the quote providers is already
    split-adjusted, so leaving this raw produces absurd historical EPS/SPS
    (AMZN's 2021 20:1 split made 5-year P/S read +1663%).

    Walking backwards from the newest quarter and dividing by each detected
    ratio puts every earlier quarter on today's share basis.
    """
    ends = sorted(shares)
    if len(ends) < 2:
        return dict(shares)
    out = dict(shares)
    factor = 1.0
    for i in range(len(ends) - 1, 0, -1):
        cur, prev = shares[ends[i]], shares[ends[i - 1]]
        if prev > 0:
            ratio = cur / prev
            # a genuine split is a clean, large jump; ignore ordinary drift
            if ratio >= 1.5 or ratio <= 0.67:
                nearest = min((2, 3, 4, 5, 10, 20), key=lambda k: abs(ratio - k))
                if abs(ratio - nearest) / nearest < 0.1:
                    factor *= nearest
                elif ratio <= 0.67:
                    inv = min((2, 3, 4, 5, 10, 20), key=lambda k: abs(1 / ratio - k))
                    if abs(1 / ratio - inv) / inv < 0.1:
                        factor /= inv
        if factor != 1.0:
            out[ends[i - 1]] = shares[ends[i - 1]] * factor
    return out


def _ttm(series: dict[str, float]) -> dict[str, float]:
    """Rolling 4-quarter sums, keyed by the latest quarter end."""
    ends = sorted(series)
    out: dict[str, float] = {}
    for i in range(3, len(ends)):
        window = ends[i - 3:i + 1]
        try:
            span = (date.fromisoformat(window[-1]) - date.fromisoformat(window[0])).days
        except ValueError:
            continue
        if span > 400:  # gap in filings — not a clean TTM
            continue
        out[window[-1]] = sum(series[w] for w in window)
    return out


def build_history(cik: int, closes: list[tuple[str, float]]) -> dict:
    """Join a daily close series to point-in-time TTM fundamentals.

    closes: [(iso_date, close_price), ...] ascending.
    Returns a dict with a daily series of P/E, P/S, P/B plus the raw TTM values.
    """
    facts = fetch_facts(cik)
    gaap = (facts or {}).get("facts", {}).get("us-gaap", {})
    if not gaap:
        raise FetchError("no us-gaap facts")

    rev_q = _quarterly(gaap, REVENUE_TAGS)
    ni_q = _quarterly(gaap, NET_INCOME_TAGS)
    sh_q = _split_adjust(_quarterly(gaap, SHARES_TAGS))
    equity = _instant(gaap, EQUITY_TAGS)
    if not rev_q or not ni_q:
        raise FetchError("missing quarterly revenue or net income")

    rev_ttm, ni_ttm = _ttm(rev_q), _ttm(ni_q)
    if not rev_ttm:
        raise FetchError("could not build TTM series")

    ends = sorted(rev_ttm)
    avail_cache: dict[str, str | None] = {}

    def latest_available(d: date) -> str | None:
        key = d.isoformat()
        if key in avail_cache:
            return avail_cache[key]
        found = None
        for e in ends:
            if date.fromisoformat(e) + timedelta(days=FILING_LAG_DAYS) <= d:
                found = e
            else:
                break
        avail_cache[key] = found
        return found

    series = []
    for iso, px in closes:
        try:
            d = date.fromisoformat(iso)
        except ValueError:
            continue
        e = latest_available(d)
        if not e or e not in ni_ttm or e not in sh_q:
            continue
        shares = sh_q[e]
        rev, ni = rev_ttm[e], ni_ttm[e]
        if not shares or shares <= 0 or rev <= 0:
            continue
        sps = rev / shares
        eps = ni / shares
        bvps = (equity.get(e, 0) / shares) if equity.get(e) else None
        series.append({
            "t": iso,
            "px": round(px, 2),
            "ps": round(px / sps, 3) if sps > 0 else None,
            "pe": round(px / eps, 2) if eps > 0 else None,
            "pb": round(px / bvps, 2) if bvps and bvps > 0 else None,
            "rev": rev,
            "eps": round(eps, 4),
            "period": e,
        })
    if not series:
        raise FetchError("no overlapping price/fundamental data")
    return {
        "series": series,
        "quarters": len(rev_q),
        "first": series[0]["t"],
        "last": series[-1]["t"],
    }


def summarise(hist: dict, years: float = 2.0) -> dict:
    """Trailing-mean multiples and the return decomposition."""
    s = hist["series"]
    end = s[-1]
    cutoff = (date.fromisoformat(end["t"]) - timedelta(days=int(365 * years))).isoformat()
    window = [p for p in s if p["t"] >= cutoff]

    def mean(key):
        vals = [p[key] for p in window if p.get(key) is not None and p[key] > 0]
        return round(sum(vals) / len(vals), 2) if vals else None

    out = {
        "pe_mean_2y": mean("pe"),
        "ps_mean_2y": mean("ps"),
        "pb_mean_2y": mean("pb"),
        "window_points": len(window),
        "decomposition": [],
    }

    for label, yrs in (("1y", 1), ("3y", 3), ("5y", 5)):
        target = (date.fromisoformat(end["t"]) - timedelta(days=365 * yrs)).isoformat()
        earlier = [p for p in s if p["t"] <= target]
        if not earlier:
            continue
        st = earlier[-1]
        row = {"period": label, "from": st["t"], "to": end["t"],
               "price_return": round((end["px"] / st["px"] - 1) * 100, 1)}
        if st.get("ps") and end.get("ps"):
            row["ps_change"] = round((end["ps"] / st["ps"] - 1) * 100, 1)
            row["sales_growth"] = round((end["rev"] / st["rev"] - 1) * 100, 1)
        if st.get("pe") and end.get("pe") and st["eps"] > 0 and end["eps"] > 0:
            row["pe_change"] = round((end["pe"] / st["pe"] - 1) * 100, 1)
            row["eps_growth"] = round((end["eps"] / st["eps"] - 1) * 100, 1)
        # share count moves sit outside a two-factor split; surface rather than hide
        if st["rev"] and end["rev"] and st.get("ps") and end.get("ps"):
            implied = (1 + row["ps_change"] / 100) * (1 + row["sales_growth"] / 100) - 1
            row["share_effect"] = round(
                ((1 + row["price_return"] / 100) / (1 + implied) - 1) * 100, 1
            )
        out["decomposition"].append(row)
    return out


def downsample(series: list[dict], max_points: int = 320) -> list[dict]:
    """Thin the daily series for the browser without losing shape."""
    if len(series) <= max_points:
        return series
    step = len(series) / max_points
    out = [series[int(i * step)] for i in range(max_points)]
    if out[-1]["t"] != series[-1]["t"]:
        out.append(series[-1])
    return out
