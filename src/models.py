"""Signal / TickerResult model.

PRD Amendment B: every metric carries a human-readable `detail`, and every
ticker isolates its own errors so one failure never aborts the run.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Signal:
    key: str
    label: str
    score: float | None  # 0..1, None = not computable
    detail: str  # plain-English explanation, ALWAYS populated
    weight: float = 0.0
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TickerResult:
    symbol: str
    name: str = ""
    type: str = "equity"
    sector: str | None = None

    # quote
    price: float | None = None
    change_pct: float | None = None
    high52: float | None = None
    low52: float | None = None
    pct_from_high: float | None = None
    pct_from_low: float | None = None
    pos52: float | None = None
    currency: str = "USD"

    # fundamentals
    pe_ltm: float | None = None
    pe_fwd: float | None = None
    ev_ebitda: float | None = None
    roic: float | None = None
    roic_trend: str | None = None
    debt_equity: float | None = None
    fcf_margin: float | None = None
    market_cap: float | None = None

    # risk
    beta: float | None = None
    vol30: float | None = None
    downdev: float | None = None
    ret1y: float | None = None

    # events
    earnings_date: str | None = None
    earnings_days: int | None = None
    earnings_confirmed: bool = False
    catalyst_date: str | None = None
    catalyst_note: str | None = None

    # ownership
    insider: str | None = None  # buy | sell | None
    insider_detail: str = "No Form 4 activity in 90d"
    politician: str | None = None
    politician_detail: str = "No disclosures"
    superinv: str | None = None  # add | new | trim
    superinv_detail: str = "No Dataroma change"

    # expectations
    weight_pct: float | None = None
    fair_value: float | None = None
    fair_value_source: str | None = None
    gap_pct: float | None = None

    # scoring
    score: float | None = None
    score_partial: bool = False
    score_n: str = ""
    score_parts: list[dict] = field(default_factory=list)

    # buffett
    buffett: dict | None = None

    # flags / provenance
    new_listing: bool = False
    suppressed: bool = False
    thin: bool = False
    alias: str | None = None
    stale: bool = False
    errors: list[str] = field(default_factory=list)
    sources: dict = field(default_factory=dict)

    def add_error(self, where: str, exc: Exception | str) -> None:
        msg = str(exc)
        self.errors.append(f"{where}: {msg[:180]}")

    def to_dict(self) -> dict:
        return asdict(self)
