"""Wall Street consensus price targets (Nasdaq, keyless)."""
from __future__ import annotations

from .http import FetchError, get_json

TARGET = "https://api.nasdaq.com/api/analyst/{sym}/targetprice"
RATINGS = "https://api.nasdaq.com/api/analyst/{sym}/ratings"


def fetch(sym: str) -> dict:
    d = get_json(TARGET.format(sym=sym.upper()), cache_s=24 * 3600, tries=2)
    data = (d or {}).get("data") or {}
    c = data.get("consensusOverview") or {}
    target = c.get("priceTarget")
    if not target:
        raise FetchError("no consensus target")
    buy, hold, sell = c.get("buy") or 0, c.get("hold") or 0, c.get("sell") or 0
    n = buy + hold + sell
    return {
        "target": float(target),
        "low": c.get("lowPriceTarget"),
        "high": c.get("highPriceTarget"),
        "buy": buy,
        "hold": hold,
        "sell": sell,
        "analysts": n,
        "detail": (
            f"Consensus ${float(target):,.2f} "
            f"(range ${c.get('lowPriceTarget')}–${c.get('highPriceTarget')}) · "
            f"{buy} buy / {hold} hold / {sell} sell"
        ),
    }
