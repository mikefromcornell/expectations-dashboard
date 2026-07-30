"""Discord alerts + 10:00 ET daily summary.

One webhook, one channel. Alert type is conveyed by embed colour and title so
the daily summary is never buried. A dedupe state file prevents repeat pings
for the same event.
"""
from __future__ import annotations

import json
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests

from ..config import DATA, ROOT, load_watchlist

STATE = ROOT / ".state" / "alerts.json"
STATE.parent.mkdir(exist_ok=True)
WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "")

RED, GREEN, AMBER, BLUE, PURPLE = 0xEF4444, 0x22C55E, 0xF59E0B, 0x5865F2, 0xA78BFA


def _state() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text())
        except Exception:
            pass
    return {}


def _save(st: dict) -> None:
    STATE.write_text(json.dumps(st, indent=1))


def _post(embeds: list[dict], dry: bool = False) -> bool:
    if not embeds:
        return True
    if dry or not WEBHOOK:
        for e in embeds:
            print(f"    [dry] {e.get('title')}")
        return not WEBHOOK
    ok = True
    for i in range(0, len(embeds), 10):  # Discord caps at 10 embeds per message
        r = requests.post(WEBHOOK, json={"embeds": embeds[i:i + 10]}, timeout=20)
        if r.status_code >= 300:
            print(f"    ! discord {r.status_code}: {r.text[:120]}")
            ok = False
        time.sleep(0.6)
    return ok


def _load(name: str, default):
    p = DATA / name
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


def check_alerts(dry: bool = False) -> int:
    rows = _load("tickers.json", [])
    wl = {t.symbol: t for t in load_watchlist()}
    st = _state()
    today = date.today().isoformat()
    embeds: list[dict] = []

    def fire(key: str, embed: dict) -> None:
        if st.get(key) == today:
            return
        st[key] = today
        embeds.append(embed)

    for r in rows:
        sym, price = r["symbol"], r.get("price")
        if not price:
            continue
        t = wl.get(sym)

        # 52-week extremes
        if r.get("pct_from_low") is not None and r["pct_from_low"] < 1.0:
            fire(f"{sym}:low52", {
                "title": f"🔴 {sym} — at/near 52-week low",
                "color": RED,
                "description": (f"**${price:,.2f}** · {r.get('change_pct', 0):+.2f}% today\n"
                                f"{r['pct_from_low']:+.1f}% from 52-wk low"),
            })
        if r.get("pct_from_high") is not None and r["pct_from_high"] > -1.0:
            fire(f"{sym}:high52", {
                "title": f"🟢 {sym} — at/near 52-week high",
                "color": GREEN,
                "description": f"**${price:,.2f}** · {r['pct_from_high']:+.1f}% from 52-wk high",
            })
        # user thresholds
        if t and t.alert_low and price <= t.alert_low:
            fire(f"{sym}:alertlow", {
                "title": f"🔴 {sym} crossed your alert_low",
                "color": RED,
                "description": f"**${price:,.2f}** ≤ ${t.alert_low:,.2f}",
            })
        if t and t.alert_high and price >= t.alert_high:
            fire(f"{sym}:alerthigh", {
                "title": f"🟢 {sym} crossed your alert_high",
                "color": GREEN,
                "description": f"**${price:,.2f}** ≥ ${t.alert_high:,.2f}",
            })
        # earnings
        d = r.get("earnings_days")
        if d is not None:
            if d in (7, 1):
                fire(f"{sym}:earn{d}", {
                    "title": f"🟠 {sym} — earnings in {d} day{'s' if d > 1 else ''}",
                    "color": AMBER,
                    "description": f"{r.get('earnings_date')} · "
                                   f"{'confirmed' if r.get('earnings_confirmed') else 'estimated'}",
                })
            if -3 <= d < 0:
                fire(f"{sym}:drift", {
                    "title": f"🔵 {sym} — post-earnings drift window",
                    "color": BLUE,
                    "description": (f"Reported {abs(d)}d ago. Expectations are being repriced now — "
                                    "worth revisiting your assumptions."),
                })
        # ownership
        if r.get("insider") == "buy" and "cluster" in (r.get("insider_detail") or ""):
            fire(f"{sym}:cluster", {
                "title": f"🟢 {sym} — insider cluster buy",
                "color": GREEN, "description": r["insider_detail"],
            })
        if r.get("superinv") in ("new", "add"):
            fire(f"{sym}:superinv", {
                "title": f"💼 {sym} — superinvestor {r['superinv']}",
                "color": PURPLE, "description": r.get("superinv_detail", ""),
            })
        # expectations
        if r.get("gap_pct") is not None and r["gap_pct"] > 25:
            fire(f"{sym}:gap", {
                "title": f"🎯 {sym} — expectations gap {r['gap_pct']:+.1f}%",
                "color": PURPLE,
                "description": f"Price ${price:,.2f} vs your fair value ${r.get('fair_value'):,.2f}",
            })

    ok = _post(embeds, dry)
    if ok and not dry:
        _save(st)
    print(f"  {len(embeds)} alert(s)")
    return 0


def daily_summary(dry: bool = False) -> int:
    rows = _load("tickers.json", [])
    meta = _load("meta.json", {})
    eq = [r for r in rows if r.get("price")]
    today = date.today()

    movers = sorted([r for r in eq if abs(r.get("change_pct") or 0) >= 2],
                    key=lambda r: -abs(r.get("change_pct") or 0))[:6]
    earnings = sorted([r for r in eq if r.get("earnings_days") is not None
                       and 0 <= r["earnings_days"] <= 7], key=lambda r: r["earnings_days"])
    drift = [r for r in eq if r.get("earnings_days") is not None and -3 <= r["earnings_days"] < 0]
    lows = [r for r in eq if r.get("pct_from_low") is not None and r["pct_from_low"] < 5]
    highs = [r for r in eq if r.get("pct_from_high") is not None and r["pct_from_high"] > -2]
    insiders = [r for r in eq if r.get("insider") == "buy"]
    supers = [r for r in eq if r.get("superinv") in ("new", "add")]
    ranked = sorted([r for r in eq if r.get("score") is not None],
                    key=lambda r: -r["score"])[:5]

    def lst(items, fn, empty="none"):
        return "\n".join(fn(r) for r in items[:6]) or empty

    fields = [
        {"name": f"📈 Movers (≥2%) — {len(movers)}", "inline": False,
         "value": lst(movers, lambda r: f"`{r['symbol']}` {r['change_pct']:+.2f}% → ${r['price']:,.2f}")},
        {"name": f"📅 Earnings within 7 days — {len(earnings)}", "inline": False,
         "value": lst(earnings, lambda r: f"`{r['symbol']}` in {r['earnings_days']}d ({r.get('earnings_date')})")},
        {"name": f"🔵 Post-earnings drift — {len(drift)}", "inline": False,
         "value": lst(drift, lambda r: f"`{r['symbol']}` reported {abs(r['earnings_days'])}d ago")},
        {"name": f"⚠️ Within 5% of 52-wk low — {len(lows)}", "inline": False,
         "value": lst(lows, lambda r: f"`{r['symbol']}` {r['pct_from_low']:+.1f}% above low")},
        {"name": f"🟢 Insider buying (90d) — {len(insiders)}", "inline": False,
         "value": lst(insiders, lambda r: f"`{r['symbol']}` {r['insider_detail'][:70]}")},
        {"name": f"💼 Superinvestor adds — {len(supers)}", "inline": False,
         "value": lst(supers, lambda r: f"`{r['symbol']}` {r['superinv_detail'][:70]}")},
        {"name": "🎯 Top Expectations Scores", "inline": False,
         "value": lst(ranked, lambda r: f"`{r['symbol']}` {r['score']*100:.0f}%")},
    ]
    embed = {
        "title": f"📊 Daily Summary — {today.strftime('%d %b %Y')}",
        "color": BLUE,
        "fields": [f for f in fields if f["value"] != "none"],
        "footer": {"text": f"{meta.get('tickers', 0)} tickers · quotes delayed ~15 min · "
                           f"built {meta.get('generated', '')[:16]}"},
    }
    _post([embed], dry)
    write_daily_page(rows, movers, earnings, drift, lows, highs, insiders, supers, ranked, meta)
    return 0


def write_daily_page(rows, movers, earnings, drift, lows, highs, insiders, supers, ranked, meta):
    """Self-contained, inline-styled archive page (PRD Amendment D)."""
    d = date.today().isoformat()
    out = ROOT / "docs" / "daily"
    out.mkdir(parents=True, exist_ok=True)

    def sec(title, items, fn):
        if not items:
            return ""
        li = "".join(
            f'<div style="padding:7px 0;border-bottom:1px solid #16203a;font-size:13px">{fn(r)}</div>'
            for r in items[:12])
        return (f'<div style="background:#111830;border:1px solid #1e2942;border-radius:11px;'
                f'padding:16px 18px;margin-bottom:14px">'
                f'<h2 style="font-size:13px;margin:0 0 11px">{title}</h2>{li}</div>')

    body = "".join([
        sec(f"📈 Movers (≥2%)", movers,
            lambda r: f"<b>{r['symbol']}</b> <span style=\"color:{'#22c55e' if r['change_pct']>=0 else '#ef4444'}\">"
                      f"{r['change_pct']:+.2f}%</span> → ${r['price']:,.2f}"),
        sec("📅 Earnings within 7 days", earnings,
            lambda r: f"<b>{r['symbol']}</b> in {r['earnings_days']}d — {r.get('earnings_date')}"),
        sec("🔵 Post-earnings drift window", drift,
            lambda r: f"<b>{r['symbol']}</b> reported {abs(r['earnings_days'])}d ago — expectations being repriced"),
        sec("⚠️ Within 5% of 52-week low", lows,
            lambda r: f"<b>{r['symbol']}</b> {r['pct_from_low']:+.1f}% above low · ${r['price']:,.2f}"),
        sec("🟢 Insider buying (90d)", insiders, lambda r: f"<b>{r['symbol']}</b> {r['insider_detail']}"),
        sec("💼 Superinvestor activity", supers, lambda r: f"<b>{r['symbol']}</b> {r['superinv_detail']}"),
        sec("🎯 Top Expectations Scores", ranked,
            lambda r: f"<b>{r['symbol']}</b> {r['score']*100:.0f}%"),
    ])
    html = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Daily Summary — {d}</title></head>
<body style="background:#0b1020;color:#e8edf7;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
padding:28px;max-width:900px;margin:0 auto">
<h1 style="font-size:20px;margin:0 0 4px">Daily Summary — {d}</h1>
<div style="color:#5f708f;font-size:12px;margin-bottom:20px">
Generated {meta.get('generated','')} · {meta.get('tickers',0)} tickers · quotes delayed ~15 min ·
<a href="../index.html" style="color:#60a5fa">back to dashboard</a></div>
{body}
<div style="color:#5f708f;font-size:11px;margin-top:22px;line-height:1.6">
Self-contained archive page — inline styles only, renders identically forever.<br>
Sources: Yahoo / StockAnalysis / Nasdaq, SEC EDGAR, Dataroma, FRED. Not investment advice.</div>
</body></html>"""
    (out / f"{d}.html").write_text(html)
    (out / "index.html").write_text(html)
    print(f"  wrote docs/daily/{d}.html")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["alerts", "daily"])
    ap.add_argument("--dry", action="store_true")
    ns = ap.parse_args()
    raise SystemExit(check_alerts(ns.dry) if ns.mode == "alerts" else daily_summary(ns.dry))
