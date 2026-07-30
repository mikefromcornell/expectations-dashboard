"""Earnings calendar.

Nasdaq's calendar is queried per-date, not per-symbol, so one sweep of the next
N weekdays yields dates for the whole watchlist in ~45 requests instead of 74.
Finnhub is the per-symbol fallback when a key is configured.
"""
from __future__ import annotations

import os
import time
from datetime import date, timedelta

from .http import get_json

NASDAQ_CAL = "https://api.nasdaq.com/api/calendar/earnings?date={d}"
FINNHUB_CAL = (
    "https://finnhub.io/api/v1/calendar/earnings?from={frm}&to={to}&symbol={sym}&token={key}"
)


def sweep(symbols: set[str], weeks: int = 9, throttle: float = 0.2) -> dict[str, dict]:
    """Walk forward over weekdays, collecting earnings dates for our symbols."""
    found: dict[str, dict] = {}
    d = date.today()
    end = d + timedelta(weeks=weeks)
    remaining = set(symbols)
    while d <= end and remaining:
        if d.weekday() < 5:  # weekdays only
            try:
                payload = get_json(NASDAQ_CAL.format(d=d.isoformat()), cache_s=12 * 3600, tries=2)
                rows = ((payload or {}).get("data") or {}).get("rows") or []
                for r in rows:
                    sym = (r.get("symbol") or "").strip().upper()
                    if sym in remaining:
                        found[sym] = {
                            "date": d.isoformat(),
                            "confirmed": True,
                            "time": r.get("time"),
                            "eps_forecast": r.get("epsForecast"),
                        }
                        remaining.discard(sym)
            except Exception:
                pass
            time.sleep(throttle)
        d += timedelta(days=1)
    return found


def from_finnhub(sym: str) -> dict | None:
    key = os.environ.get("FINNHUB_API_KEY")
    if not key:
        return None
    today = date.today()
    to = today + timedelta(days=400)
    try:
        d = get_json(
            FINNHUB_CAL.format(frm=today.isoformat(), to=to.isoformat(), sym=sym, key=key),
            cache_s=12 * 3600,
        )
    except Exception:
        return None
    rows = (d or {}).get("earningsCalendar") or []
    if not rows:
        return None
    rows.sort(key=lambda r: r.get("date", ""))
    return {"date": rows[0].get("date"), "confirmed": True, "time": rows[0].get("hour")}
