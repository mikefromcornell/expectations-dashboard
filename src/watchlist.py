"""Watchlist management CLI.

    python -m src.watchlist add NVDA TSM
    python -m src.watchlist import my_holdings.csv
    python -m src.watchlist remove SOFI
    python -m src.watchlist validate
    python -m src.watchlist weights            # show current sizing

config/watchlist.yaml is the single source of truth. Removals are archived,
never deleted. Cost basis / share counts are stripped on import (repo is public).
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

import yaml

from .config import ARCHIVE_PATH, IMPORT_DIR, WATCHLIST_PATH, load_watchlist
from .providers.quotes import fetch_quote

# Never committed to a public repo (PRD §8.1)
BANNED_COLUMNS = {
    "cost", "cost_basis", "costbasis", "avg_cost", "average_cost", "basis",
    "shares", "share_count", "quantity", "qty", "units", "position_value",
    "market_value", "pnl", "gain", "unrealized",
}

HEADER = """\
# ════════════════════════════════════════════════════════════════
#  WATCHLIST — single source of truth for the Expectations Dashboard
# ════════════════════════════════════════════════════════════════
#  Add a ticker:  python -m src.watchlist add NVDA
#  Bulk import:   python -m src.watchlist import file.csv
#  Remove:        python -m src.watchlist remove SOFI   (archives, never deletes)
#  Validate:      python -m src.watchlist validate
#  Or use the '+ Add Ticker' button in the dashboard header.
#
#  Only `symbol` is required. All other fields are optional.
#  `weight` is % of portfolio and drives the Portfolio tab.
#
#  NEVER add cost basis or share counts - this repo is PUBLIC (PRD §8.1).
# ════════════════════════════════════════════════════════════════
"""


def _read_raw() -> dict:
    if not WATCHLIST_PATH.exists():
        return {"tickers": []}
    return yaml.safe_load(WATCHLIST_PATH.read_text()) or {"tickers": []}


def _write_raw(doc: dict) -> None:
    body = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100)
    WATCHLIST_PATH.write_text(HEADER + "\n" + body)


def _normalise(sym: str) -> str:
    s = sym.strip().upper()
    if ":" in s:          # NYSE:TSM -> TSM
        s = s.split(":")[-1]
    return s.replace(".", "-")   # BRK.B -> BRK-B


def cmd_add(symbols: list[str], validate: bool = True) -> int:
    doc = _read_raw()
    existing = {str(t.get("symbol", "")).upper(): t for t in doc.get("tickers", [])}
    added, updated, failed = [], [], []
    for raw in symbols:
        sym = _normalise(raw)
        if validate:
            q, errs = fetch_quote(sym)
            if not q or not q.price:
                failed.append((sym, errs[-1] if errs else "no quote"))
                continue
        if sym in existing:
            updated.append(sym)
            continue
        entry = {"symbol": sym}
        if validate and q:
            entry["type"] = "equity"
        doc.setdefault("tickers", []).append(entry)
        added.append(sym)
    _write_raw(doc)
    for s in added:
        print(f"  added    {s}")
    for s in updated:
        print(f"  exists   {s} (unchanged — edit fields in YAML)")
    for s, e in failed:
        print(f"  REJECTED {s}: {e}")
    return 1 if failed else 0


def cmd_remove(symbols: list[str]) -> int:
    doc = _read_raw()
    keep, gone = [], []
    targets = {_normalise(s) for s in symbols}
    for t in doc.get("tickers", []):
        if str(t.get("symbol", "")).upper() in targets:
            gone.append(t)
        else:
            keep.append(t)
    doc["tickers"] = keep
    _write_raw(doc)

    arch = {}
    if ARCHIVE_PATH.exists():
        arch = yaml.safe_load(ARCHIVE_PATH.read_text()) or {}
    arch.setdefault("archived", [])
    stamp = datetime.utcnow().isoformat(timespec="seconds")
    for t in gone:
        arch["archived"].append({**t, "archived_at": stamp})
    ARCHIVE_PATH.write_text(yaml.safe_dump(arch, sort_keys=False, allow_unicode=True))
    for t in gone:
        print(f"  archived {t.get('symbol')} -> config/archive.yaml")
    if not gone:
        print("  nothing matched")
    return 0


def cmd_import(paths: list[str]) -> int:
    files: list[Path] = []
    for p in paths:
        pp = Path(p)
        files.extend(sorted(pp.glob("*.csv")) if pp.is_dir() else [pp])
    if not files:
        print("  no CSV files found")
        return 1

    doc = _read_raw()
    by_sym = {str(t.get("symbol", "")).upper(): t for t in doc.get("tickers", [])}
    n_new = n_upd = 0
    stripped: set[str] = set()

    for f in files:
        text = f.read_bytes().decode("utf-8-sig")
        sample = text[:400]
        has_header = any(h in sample.lower() for h in ("ticker", "symbol"))
        rdr = csv.DictReader(text.splitlines()) if has_header else None
        rows = list(rdr) if rdr else [{"ticker": l.strip()} for l in text.splitlines() if l.strip()]
        for row in rows:
            row = {(k or "").strip().lower(): v for k, v in row.items() if k}
            for bad in list(row):
                if bad in BANNED_COLUMNS:
                    stripped.add(bad)
                    row.pop(bad)
            raw = row.get("ticker") or row.get("symbol") or ""
            sym = _normalise(str(raw))
            if not sym:
                continue
            entry = by_sym.get(sym, {"symbol": sym})
            for src, dst, cast in (
                ("name", "name", str), ("fair_value", "fair_value", float),
                ("alert_low", "alert_low", float), ("alert_high", "alert_high", float),
                ("weight", "weight", float), ("catalyst_date", None, None),
                ("notes", "notes", str), ("tags", "tags", None),
            ):
                v = row.get(src)
                if v in (None, "", "-"):
                    continue
                try:
                    if src == "catalyst_date":
                        entry.setdefault("catalyst", {})["date"] = str(v)
                    elif src == "tags":
                        entry["tags"] = [t.strip() for t in str(v).split(",") if t.strip()]
                    else:
                        entry[dst] = cast(v) if cast else v
                except Exception:
                    pass
            if sym in by_sym:
                n_upd += 1
            else:
                n_new += 1
                doc.setdefault("tickers", []).append(entry)
                by_sym[sym] = entry
    _write_raw(doc)
    print(f"  imported {n_new} new, updated {n_upd}")
    if stripped:
        print(f"  STRIPPED sensitive columns (public repo): {', '.join(sorted(stripped))}")
    return 0


def cmd_validate() -> int:
    wl = load_watchlist()
    bad = []
    print(f"  validating {len(wl)} tickers against the quote chain…")
    for t in wl:
        q, errs = fetch_quote(t.quote_symbol)
        if not q or not q.price:
            bad.append((t.symbol, errs[-1] if errs else "no quote"))
            print(f"    FAIL {t.symbol}: {errs[-1] if errs else 'no quote'}")
    print(f"  {len(wl) - len(bad)}/{len(wl)} resolve")
    return 1 if bad else 0


def cmd_weights() -> int:
    wl = load_watchlist()
    held = [t for t in wl if t.weight]
    total = sum(t.weight for t in held)
    for t in sorted(held, key=lambda x: -(x.weight or 0)):
        print(f"  {t.symbol:<8} {t.weight:>6.2f}%")
    print(f"  {'TOTAL':<8} {total:>6.2f}%  ({len(held)} held, {len(wl) - len(held)} unweighted)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="watchlist")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add"); a.add_argument("symbols", nargs="+")
    a.add_argument("--no-validate", action="store_true")
    r = sub.add_parser("remove"); r.add_argument("symbols", nargs="+")
    i = sub.add_parser("import"); i.add_argument("paths", nargs="*", default=[str(IMPORT_DIR)])
    sub.add_parser("validate")
    sub.add_parser("weights")
    ns = ap.parse_args(argv)

    if ns.cmd == "add":
        return cmd_add(ns.symbols, validate=not ns.no_validate)
    if ns.cmd == "remove":
        return cmd_remove(ns.symbols)
    if ns.cmd == "import":
        return cmd_import(ns.paths or [str(IMPORT_DIR)])
    if ns.cmd == "validate":
        return cmd_validate()
    if ns.cmd == "weights":
        return cmd_weights()
    return 0


if __name__ == "__main__":
    sys.exit(main())
