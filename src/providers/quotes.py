"""Quote provider with fallback chain.

Chain order (all keyless except the last):
    1. Yahoo chart      - full OHLC history, best coverage, but rate-limits hard
    2. StockAnalysis    - full daily history JSON, reliable, keyless
    3. Nasdaq API       - quote + 52wk range only, no history
    4. Finnhub          - quote only, needs free key

Tested 2026-07-30: Stooq was dropped from the chain after it deployed a
JavaScript proof-of-work interstitial, which makes it unusable from a script.
Yahoo returned 429 to this sandbox's IP for sustained periods, which is exactly
why more than one keyless provider is required rather than optional.
"""
from __future__ import annotations



import math
import os
import statistics
from dataclasses import dataclass

from .http import FetchError, get_json, get_text

YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={rng}&interval=1d"
STOCKANALYSIS = "https://stockanalysis.com/api/symbol/s/{sym}/history"
STOCKANALYSIS_ETF = "https://stockanalysis.com/api/symbol/e/{sym}/history"
NASDAQ_INFO = "https://api.nasdaq.com/api/quote/{sym}/info?assetclass={cls}"
FINNHUB_QUOTE = "https://finnhub.io/api/v1/quote?symbol={sym}&token={key}"


@dataclass
class Quote:
    symbol: str
    price: float | None = None
    prev_close: float | None = None
    change_pct: float | None = None
    high52: float | None = None
    low52: float | None = None
    currency: str = "USD"
    exchange: str | None = None
    source: str = "unknown"
    closes: list[float] | None = None  # daily closes for risk metrics
    history_days: int = 0


def _pct(a: float, b: float) -> float:
    return (a - b) / b * 100.0 if b else 0.0


def from_yahoo(sym: str, rng: str = "3y") -> Quote:
    data = get_json(YAHOO_CHART.format(sym=sym, rng=rng), cache_s=600)
    res = (data or {}).get("chart", {}).get("result")
    if not res:
        err = (data or {}).get("chart", {}).get("error") or "no result"
        raise FetchError(f"yahoo: {err}")
    r = res[0]
    m = r.get("meta", {})
    closes: list[float] = []
    try:
        raw = r["indicators"]["quote"][0]["close"]
        closes = [c for c in raw if c is not None]
    except Exception:
        closes = []
    price = m.get("regularMarketPrice")
    prev = m.get("chartPreviousClose") or m.get("previousClose")
    return Quote(
        symbol=sym,
        price=price,
        prev_close=prev,
        change_pct=_pct(price, prev) if price and prev else None,
        high52=m.get("fiftyTwoWeekHigh"),
        low52=m.get("fiftyTwoWeekLow"),
        currency=m.get("currency", "USD"),
        exchange=m.get("fullExchangeName"),
        source="yahoo",
        closes=closes,
        history_days=len(closes),
    )


def from_stockanalysis(sym: str, is_etf: bool = False, rng: str = "5Y") -> Quote:
    """Keyless daily history.

    Quirks handled here:
      * share classes use a dot, not a hyphen  (BRK.B, not BRK-B)
      * ?range=5Y returns data as a bare list; the default returns {"data": [...]}
      * rows arrive newest-first, so they are sorted chronologically
    """
    s = sym.replace("-", ".").lower()
    base = (STOCKANALYSIS_ETF if is_etf else STOCKANALYSIS).format(sym=s)
    d = get_json(f"{base}?range={rng}", cache_s=900)
    payload = (d or {}).get("data")
    rows = payload if isinstance(payload, list) else (payload or {}).get("data") or []
    if not rows:
        raise FetchError("stockanalysis: no rows")
    rows = sorted(rows, key=lambda r: r.get("t", ""))
    closes = [float(r["c"]) for r in rows if r.get("c") is not None]
    if not closes:
        raise FetchError("stockanalysis: no closes")
    price = closes[-1]
    prev = closes[-2] if len(closes) > 1 else price
    window = closes[-252:]
    return Quote(
        symbol=sym,
        price=price,
        prev_close=prev,
        change_pct=_pct(price, prev),
        high52=max(window),
        low52=min(window),
        source="stockanalysis",
        closes=closes,
        history_days=len(closes),
    )


def _money(s) -> float | None:
    if not s:
        return None
    try:
        return float(str(s).replace("$", "").replace(",", "").replace("%", "").strip())
    except ValueError:
        return None


def from_nasdaq(sym: str, is_etf: bool = False) -> Quote:
    """Quote + 52-week range. No history, so risk metrics stay null."""
    cls = "etf" if is_etf else "stocks"
    d = get_json(NASDAQ_INFO.format(sym=sym.upper(), cls=cls), cache_s=600)
    data = (d or {}).get("data")
    if not data:
        raise FetchError("nasdaq: no data")
    pd = data.get("primaryData") or {}
    price = _money(pd.get("lastSalePrice"))
    if not price:
        raise FetchError("nasdaq: no price")
    chg = _money(pd.get("percentageChange"))
    hi = lo = None
    rng = ((data.get("keyStats") or {}).get("fiftyTwoWeekHighLow") or {}).get("value")
    if rng and "-" in str(rng):
        parts = [p.strip() for p in str(rng).split("-")]
        lo, hi = _money(parts[0]), _money(parts[-1])
    return Quote(
        symbol=sym,
        price=price,
        change_pct=chg,
        high52=hi,
        low52=lo,
        exchange=data.get("exchange"),
        source="nasdaq",
        closes=[],
        history_days=0,
    )


def from_finnhub(sym: str) -> Quote:
    key = os.environ.get("FINNHUB_API_KEY")
    if not key:
        raise FetchError("finnhub: no API key configured")
    d = get_json(FINNHUB_QUOTE.format(sym=sym, key=key), cache_s=300)
    if not d or d.get("c") in (None, 0):
        raise FetchError("finnhub: empty quote")
    return Quote(
        symbol=sym,
        price=d.get("c"),
        prev_close=d.get("pc"),
        change_pct=_pct(d.get("c"), d.get("pc")) if d.get("pc") else None,
        source="finnhub",
    )


def fetch_quote(sym: str, is_etf: bool = False) -> tuple[Quote | None, list[str]]:
    """Try each provider in order. Returns (quote, errors).

    Providers that carry price history are tried first, because beta, volatility,
    Sortino and the new-listing check all depend on the close series.
    """
    errors: list[str] = []
    chain = (
        ("yahoo", lambda: from_yahoo(sym)),
        ("stockanalysis", lambda: from_stockanalysis(sym, is_etf)),
        ("stockanalysis_alt", lambda: from_stockanalysis(sym, not is_etf)),
        ("nasdaq", lambda: from_nasdaq(sym, is_etf)),
        ("finnhub", lambda: from_finnhub(sym)),
    )
    for name, fn in chain:
        try:
            q = fn()
            if q.price:
                return q, errors
            errors.append(f"{name}: no price")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {str(exc)[:110]}")
    return None, errors


# ---------- risk metrics derived from the close series ----------

TRADING_DAYS = 252


def daily_returns(closes: list[float]) -> list[float]:
    out = []
    for a, b in zip(closes, closes[1:]):
        if a:
            out.append(b / a - 1.0)
    return out


def annualised_vol(closes: list[float], window: int = 30) -> float | None:
    rets = daily_returns(closes)[-window:]
    if len(rets) < 5:
        return None
    return statistics.pstdev(rets) * math.sqrt(TRADING_DAYS) * 100.0


def downside_deviation(closes: list[float], window: int = TRADING_DAYS) -> float | None:
    rets = [r for r in daily_returns(closes)[-window:]]
    if len(rets) < 20:
        return None
    neg = [r for r in rets if r < 0]
    if not neg:
        return 0.0
    return statistics.pstdev(neg) * math.sqrt(TRADING_DAYS) * 100.0


def annualised_return(closes: list[float], window: int = TRADING_DAYS) -> float | None:
    w = closes[-(window + 1):]
    if len(w) < 30 or not w[0]:
        return None
    years = (len(w) - 1) / TRADING_DAYS
    if years <= 0:
        return None
    return ((w[-1] / w[0]) ** (1 / years) - 1) * 100.0


def beta_vs(closes: list[float], bench: list[float]) -> float | None:
    a, b = daily_returns(closes), daily_returns(bench)
    n = min(len(a), len(b))
    if n < 60:
        return None
    a, b = a[-n:], b[-n:]
    var = statistics.pvariance(b)
    if not var:
        return None
    mean_a, mean_b = statistics.fmean(a), statistics.fmean(b)
    cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b)) / n
    return cov / var
