"""Config loading + paths. Single source of truth = config/watchlist.yaml."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
DATA = ROOT / "data"
DOCS = ROOT / "docs"

WATCHLIST_PATH = CONFIG / "watchlist.yaml"
EXPECTATIONS_PATH = CONFIG / "expectations.yaml"
SCORING_PATH = CONFIG / "scoring.yaml"
BUFFETT_PATH = CONFIG / "buffett.yaml"
ARCHIVE_PATH = CONFIG / "archive.yaml"
MANUAL_IDEAS_PATH = CONFIG / "manual_ideas.yaml"
IMPORT_DIR = CONFIG / "import"

# Symbols with <12 months of trading history have no true 52-week range.
# Recomputed at build time from actual history length; this is the seed list.
NEW_LISTING_MONTHS = 12

# EDGAR requires a declared User-Agent with contact info.
# SEC requires a plain "Name contact@domain" declared User-Agent.
# Parentheses, slashes and version strings get a 403 — keep this format exactly.
# Override with the EDGAR_USER_AGENT secret to use your own contact address.
# SEC requires a plain "Name contact@domain" User-Agent. Tested behaviour:
#   "ExpectationsDashboard contact@example.com"            -> 200
#   "expectations-dashboard/1.0 (research; github.com/..)"  -> 403 (parens/slashes)
#   "...@users.noreply.github.com"                          -> 403 (subdomain rejected)
# Set the EDGAR_USER_AGENT secret to your own real address.
EDGAR_UA = os.environ.get("EDGAR_USER_AGENT", "ExpectationsDashboard contact@example.com")
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _load_yaml(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default if default is not None else {}
    with path.open() as fh:
        return yaml.safe_load(fh) or (default if default is not None else {})


@dataclass
class Ticker:
    symbol: str
    name: str = ""
    type: str = "equity"  # equity | etf | adr
    sector: str | None = None
    weight: float | None = None  # % of portfolio
    fair_value: float | None = None
    market_implied_growth: float | None = None
    alert_low: float | None = None
    alert_high: float | None = None
    catalyst: dict | None = None
    tags: list[str] = field(default_factory=list)
    notes: str = ""
    historical_alias: str | None = None
    suppress_fundamentals: bool = False
    thin_liquidity: bool = False

    @property
    def is_fund(self) -> bool:
        return self.type == "etf"

    @property
    def quote_symbol(self) -> str:
        """Provider-facing symbol. Yahoo uses '-' for share classes."""
        return self.symbol.replace(".", "-")


def load_watchlist() -> list[Ticker]:
    raw = _load_yaml(WATCHLIST_PATH, {})
    out: list[Ticker] = []
    seen: set[str] = set()
    for item in raw.get("tickers", []) or []:
        if isinstance(item, str):
            item = {"symbol": item}
        sym = str(item.get("symbol", "")).strip().upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        out.append(
            Ticker(
                symbol=sym,
                name=item.get("name", "") or "",
                type=item.get("type", "equity"),
                sector=item.get("sector"),
                weight=item.get("weight"),
                fair_value=item.get("fair_value"),
                market_implied_growth=item.get("market_implied_growth"),
                alert_low=item.get("alert_low"),
                alert_high=item.get("alert_high"),
                catalyst=item.get("catalyst"),
                tags=item.get("tags") or [],
                notes=item.get("notes", "") or "",
                historical_alias=item.get("historical_alias"),
                suppress_fundamentals=bool(item.get("suppress_fundamentals", False)),
                thin_liquidity=bool(item.get("thin_liquidity", False)),
            )
        )
    return out


def load_auto_fv() -> dict:
    """Automatic fair-value rule. Manual entries in expectations.yaml always win."""
    raw = _load_yaml(EXPECTATIONS_PATH, {}) or {}
    d = raw.get("auto_fair_value") or {}
    return {"enabled": bool(d.get("enabled", False)), "target_pe": d.get("target_pe", 20)}


def load_expectations() -> dict:
    raw = _load_yaml(EXPECTATIONS_PATH, {}) or {}
    return {k: v for k, v in raw.items() if k != "auto_fair_value"}


def load_scoring() -> dict:
    default = {
        "weights": {
            "expectations_gap": 0.35,
            "position_52wk": 0.20,
            "valuation_vs_history": 0.15,
            "roic_trend": 0.10,
            "insider_activity": 0.10,
            "superinvestor_flow": 0.10,
        },
        "thresholds": {"attractive": 0.62, "watch": 0.42},
    }
    return _load_yaml(SCORING_PATH, default) or default


def load_buffett() -> dict:
    default = {
        "moat_roic_wide": 18.0,
        "moat_roic_narrow": 10.0,
        "returns_min_roic": 15.0,
        "max_debt_equity": 1.0,
        "min_fcf_margin": 10.0,
        "min_margin_of_safety_pct": 15.0,
    }
    return _load_yaml(BUFFETT_PATH, default) or default


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def today() -> date:
    return utcnow().date()
