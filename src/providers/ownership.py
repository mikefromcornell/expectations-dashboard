"""Ownership signals: SEC EDGAR Form 4 insiders, politician trades, Dataroma.

Dataroma is fetched at most once per DATAROMA_HOURS (default 72) and cached
aggressively — it is scraped politely for personal, non-commercial use.
"""
from __future__ import annotations

import json
import os
import re
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from ..config import DATA, EDGAR_UA, ROOT
from .http import FetchError, get_json, get_text, read_cache, write_cache

DATAROMA_HOURS = float(os.environ.get("DATAROMA_HOURS", "72"))
STATE_DIR = ROOT / ".state"
STATE_DIR.mkdir(exist_ok=True)

EDGAR_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
EDGAR_TICKERS = "https://www.sec.gov/files/company_tickers.json"
DATAROMA_ACTIVITY = "https://www.dataroma.com/m/allact.php?typ=a"

# House/Senate Stock Watcher: keyless JSON mirrors of STOCK Act filings.
HOUSE_TRADES = (
    "https://house-stock-watcher-data.s3-us-west-2.amazonaws.com/data/"
    "all_transactions.json"
)
SENATE_TRADES = (
    "https://senate-stock-watcher-data.s3-us-west-2.amazonaws.com/aggregate/"
    "all_transactions.json"
)
# Official House Clerk index (works; filing-level metadata only)
HOUSE_FD_ZIP = "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}FD.ZIP"


def _edgar_headers() -> dict:
    return {"User-Agent": EDGAR_UA, "Accept-Encoding": "gzip, deflate"}


def load_cik_map() -> dict[str, int]:
    try:
        d = get_json(EDGAR_TICKERS, headers=_edgar_headers(), cache_s=7 * 86400)
    except Exception:
        return {}
    return {v["ticker"].upper(): int(v["cik_str"]) for v in (d or {}).values()}


def insider_activity(sym: str, cik_map: dict[str, int], days: int = 90) -> tuple[str | None, str]:
    """Net Form 4 open-market activity in the trailing window."""
    cik = cik_map.get(sym.upper()) or cik_map.get(sym.replace("-", ".").upper())
    if not cik:
        return None, "Not an EDGAR filer (ETF/ADR) — insider data n/a"
    try:
        d = get_json(
            EDGAR_SUBMISSIONS.format(cik=cik), headers=_edgar_headers(), cache_s=12 * 3600
        )
    except Exception as exc:  # noqa: BLE001
        raise FetchError(f"edgar submissions: {str(exc)[:100]}") from exc

    recent = (d or {}).get("filings", {}).get("recent", {})
    forms = recent.get("form", []) or []
    dates = recent.get("filingDate", []) or []
    cutoff = date.today() - timedelta(days=days)
    n = 0
    latest = None
    for f, ds in zip(forms, dates):
        if f != "4":
            continue
        try:
            fd = datetime.fromisoformat(ds).date()
        except Exception:
            continue
        if fd >= cutoff:
            n += 1
            latest = latest or ds
    if n == 0:
        return None, f"No Form 4 filings in {days}d"
    if n >= 3:
        return "buy", f"{n} Form 4 filings in {days}d (cluster) — latest {latest}"
    return "buy", f"{n} Form 4 filing(s) in {days}d — latest {latest}"


def house_filing_index(year: int | None = None) -> dict:
    """Official House Clerk periodic-transaction filing index.

    Verified 2026-07-30. This is filing-level metadata (member, date, DocID),
    NOT ticker-level trades — the actual transactions live in per-filing PDFs
    that would need OCR. It is used to surface "new disclosures exist" rather
    than to claim a specific member bought a specific ticker.
    """
    import io
    import zipfile

    from .http import _CURL, FetchError  # noqa: F401

    year = year or date.today().year
    url = HOUSE_FD_ZIP.format(year=year)
    cache = STATE_DIR / f"house_fd_{year}.json"
    if cache.exists() and (time.time() - cache.stat().st_mtime) < 24 * 3600:
        try:
            return json.loads(cache.read_text())
        except Exception:
            pass
    try:
        import requests

        from ..config import BROWSER_UA

        r = requests.get(url, headers={"User-Agent": BROWSER_UA}, timeout=60)
        r.raise_for_status()
        z = zipfile.ZipFile(io.BytesIO(r.content))
        name = next(n for n in z.namelist() if n.lower().endswith(".txt"))
        lines = z.read(name).decode("utf-8", errors="replace").splitlines()
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:120], "filings": []}

    if not lines:
        return {"error": "empty index", "filings": []}
    hdr = [h.strip() for h in lines[0].split("\t")]
    rows = []
    cutoff = date.today() - timedelta(days=120)
    for ln in lines[1:]:
        parts = ln.split("\t")
        if len(parts) != len(hdr):
            continue
        rec = dict(zip(hdr, [p.strip() for p in parts]))
        if rec.get("FilingType") != "P":  # P = periodic transaction report
            continue
        try:
            fd = datetime.strptime(rec.get("FilingDate", ""), "%m/%d/%Y").date()
        except Exception:
            continue
        if fd < cutoff:
            continue
        rows.append({
            "member": f"{rec.get('First','')} {rec.get('Last','')}".strip(),
            "state": rec.get("StateDst"),
            "filed": fd.isoformat(),
            "doc_id": rec.get("DocID"),
            "url": (
                f"https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/"
                f"{rec.get('Year')}/{rec.get('DocID')}.pdf"
            ),
        })
    rows.sort(key=lambda r: r["filed"], reverse=True)
    payload = {"fetched": datetime.utcnow().isoformat(), "filings": rows[:200]}
    cache.write_text(json.dumps(payload))
    return payload


def politician_trades(symbols: set[str], days: int = 120) -> dict[str, dict]:
    """Ticker-level STOCK Act trades, if any free mirror is reachable.

    As of 2026-07-30 the House/Senate Stock Watcher S3 mirrors return 403 and
    Capitol Trades rate-limits datacenter IPs, so this usually returns {} and
    the dashboard falls back to house_filing_index() above. Kept in place so
    coverage resumes automatically if a mirror comes back.
    """
    out: dict[str, dict] = {}
    cutoff = date.today() - timedelta(days=days)
    for url, chamber in ((HOUSE_TRADES, "House"), (SENATE_TRADES, "Senate")):
        try:
            rows = get_json(url, cache_s=24 * 3600, tries=2)
        except Exception:
            continue
        for r in rows or []:
            tk = (r.get("ticker") or "").strip().upper()
            if not tk or tk in ("--", "N/A") or tk not in symbols:
                continue
            ds = r.get("disclosure_date") or r.get("transaction_date") or ""
            try:
                dd = datetime.strptime(ds, "%m/%d/%Y").date()
            except Exception:
                try:
                    dd = datetime.fromisoformat(ds).date()
                except Exception:
                    continue
            if dd < cutoff:
                continue
            ttype = (r.get("type") or "").lower()
            action = "buy" if "purchase" in ttype else "sell" if "sale" in ttype else None
            if not action:
                continue
            prev = out.get(tk)
            if prev and prev["date"] >= dd:
                continue
            out[tk] = {
                "action": action,
                "date": dd,
                "detail": (
                    f"{chamber} {action} {r.get('amount','')} · disclosed {dd.isoformat()} "
                    f"(45-day statutory lag applies)"
                ).strip(),
            }
    return {k: {"action": v["action"], "detail": v["detail"]} for k, v in out.items()}


# ---------------- Dataroma (72h cadence) ----------------

# Real Dataroma markup (verified 2026-07-30):
#   <td class="firm"><a href="/m/m_activity.php?m=ABI&typ=a">Abrams Bison</a></td>
#   <td class="period">Q1 2026</td>
#   <td class="sym"><span class="tit_ctl">
#     <a class="buy" href="/m/activity.php?sym=SUNB&typ=a">SUNB</a>
#     <div>Sunbelt Rentals Holdings Inc<br/>Buy<br/>Change to portfolio: 35.38%</div>
#   </span></td>
_MANAGER_RE = re.compile(
    r'<td class="firm"><a[^>]*>(.*?)</a></td>\s*<td class="period">(.*?)</td>', re.S
)
_ACT_RE = re.compile(
    r'<a class="(buy|sell)" href="/m/activity\.php\?sym=([A-Z0-9\.\-]{1,8})[^"]*">'
    r"[^<]*</a>\s*<div>(.*?)</div>",
    re.S,
)
_ROW_SPLIT_RE = re.compile(r"<tr>", re.I)


def _dataroma_state() -> Path:
    return STATE_DIR / "dataroma.json"


def fetch_dataroma(force: bool = False) -> tuple[dict, str]:
    """Scrape the activity summary at most once per DATAROMA_HOURS.

    Cache age comes from the `fetched` field inside the file, NOT from the
    file's mtime: the state file is committed to the repo, and every CI
    checkout rewrites mtime to "now". Using mtime meant the 72h timer never
    expired on Actions, so the data silently froze on 2026-07-30 and kept
    serving Q1 2026 holdings well after Dataroma had moved to Q2 2026.
    """
    st = _dataroma_state()
    if st.exists() and not force:
        try:
            cached = json.loads(st.read_text())
            fetched = cached.get("fetched")
            age_h = (
                (datetime.utcnow() - datetime.fromisoformat(fetched)).total_seconds() / 3600.0
                if fetched else 1e9
            )
            if age_h < DATAROMA_HOURS:
                return cached, f"cached {age_h:.0f}h ago"
        except Exception:
            pass
    try:
        html = get_text(DATAROMA_ACTIVITY, headers={"Accept": "text/html"})
    except Exception as exc:  # noqa: BLE001
        if st.exists():
            return json.loads(st.read_text()), f"stale (fetch failed: {str(exc)[:60]})"
        return {}, f"unavailable: {str(exc)[:80]}"

    acts: dict[str, dict] = {}
    recent: list[dict] = []
    buyers: dict[str, set[str]] = defaultdict(set)

    for chunk in _ROW_SPLIT_RE.split(html):
        m = _MANAGER_RE.search(chunk)
        if not m:
            continue
        manager = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        period = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        for kind, sym, detail in _ACT_RE.findall(chunk):
            sym = sym.upper().replace(".", "-")
            text = " ".join(re.sub(r"<br\s*/?>", " · ", detail).split())
            text = re.sub(r"<[^>]+>", "", text)
            low = text.lower()
            if kind == "buy":
                action = "add" if "add" in low else "new"
            else:
                action = "trim"
            entry = {
                "symbol": sym,
                "manager": manager,
                "period": period,
                "action": action,
                "detail": text[:160],
            }
            recent.append(entry)
            if action in ("add", "new"):
                buyers[sym].add(manager)
            # first writer wins; buys take precedence over trims for the badge
            if sym not in acts or (acts[sym]["action"] == "trim" and action != "trim"):
                acts[sym] = {
                    "action": action,
                    "detail": f"{manager} ({period}): {text[:110]}",
                }

    clusters = sorted(
        ({"symbol": s, "n": len(m), "managers": sorted(m)} for s, m in buyers.items() if len(m) >= 3),
        key=lambda d: -d["n"],
    )
    # Which quarter does this scrape actually represent? Managers file at
    # different times, so take the most common period rather than the first.
    period_counts: dict[str, int] = defaultdict(int)
    for e in recent:
        if e.get("period"):
            period_counts[e["period"]] += 1
    latest_period = max(period_counts, key=period_counts.get) if period_counts else None

    payload = {
        "fetched": datetime.utcnow().isoformat(),
        "latest_period": latest_period,
        "period_mix": dict(sorted(period_counts.items(), key=lambda kv: -kv[1])[:4]),
        "activity": acts,
        "recent": recent[:400],
        "clusters": clusters[:25],
    }
    st.write_text(json.dumps(payload))
    return payload, "fresh"
