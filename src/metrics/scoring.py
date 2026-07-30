"""Expectations Score (PRD §5.6 / Amendment A).

Design rules:
  * every component carries a plain-English detail string
  * missing inputs are DROPPED and weights RE-NORMALISED, never defaulted to 0.5
  * funds and suppressed tickers are not scored at all
"""
from __future__ import annotations

from ..models import Signal, TickerResult


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def build_signals(r: TickerResult, weights: dict) -> list[Signal]:
    S: list[Signal] = []

    # 1. expectations gap
    w = weights.get("expectations_gap", 0.35)
    if r.gap_pct is None:
        S.append(
            Signal(
                "expectations_gap",
                "Expectations gap",
                None,
                "No fair value set — add one in config/expectations.yaml to activate this component",
                w,
            )
        )
    else:
        S.append(
            Signal(
                "expectations_gap",
                "Expectations gap",
                _clamp(0.5 + r.gap_pct / 120.0),
                f"Your fair value ${r.fair_value:,.2f} vs price ${r.price:,.2f} → {r.gap_pct:+.1f}%",
                w,
            )
        )

    # 2. 52-week position (lower in range scores higher)
    w = weights.get("position_52wk", 0.20)
    if r.pos52 is None or r.new_listing:
        S.append(
            Signal(
                "position_52wk",
                "52-week position",
                None,
                "No 52-week range — listed under 12 months",
                w,
            )
        )
    else:
        S.append(
            Signal(
                "position_52wk",
                "52-week position",
                _clamp(1.0 - r.pos52 / 100.0),
                (
                    f"{r.pct_from_low:+.1f}% above 52-wk low, {r.pct_from_high:+.1f}% from high "
                    f"— {r.pos52:.0f}th percentile of range"
                ),
                w,
            )
        )

    # 3. valuation vs own history (proxy: absolute P/E bands until history accumulates)
    w = weights.get("valuation_vs_history", 0.15)
    if r.pe_ltm is None or r.pe_ltm <= 0:
        S.append(Signal("valuation_vs_history", "Valuation vs own history", None,
                        "No positive LTM P/E available", w))
    else:
        score = _clamp(1.0 - (r.pe_ltm - 8.0) / 42.0)
        S.append(Signal("valuation_vs_history", "Valuation vs own history", score,
                        f"LTM P/E {r.pe_ltm:.1f} (band 8–50; own-history percentile arrives once "
                        f"the data archive has 5 quarters)", w))

    # 4. ROIC trend
    w = weights.get("roic_trend", 0.10)
    if r.roic is None:
        S.append(Signal("roic_trend", "ROIC trend", None, "ROIC not computable from available data", w))
    else:
        score = _clamp((r.roic - 2.0) / 28.0)
        S.append(Signal("roic_trend", "ROIC trend", score,
                        f"ROIC {r.roic:.1f}% (computed in-repo: NOPAT ÷ invested capital)", w))

    # 5. insider activity
    w = weights.get("insider_activity", 0.10)
    m = {"buy": 0.85, "sell": 0.20, None: 0.50}
    S.append(Signal("insider_activity", "Insider activity", m.get(r.insider, 0.5),
                    r.insider_detail, w))

    # 6. superinvestor flow
    w = weights.get("superinvestor_flow", 0.10)
    m2 = {"new": 0.90, "add": 0.80, "trim": 0.25, None: 0.50}
    S.append(Signal("superinvestor_flow", "Superinvestor flow", m2.get(r.superinv, 0.5),
                    r.superinv_detail, w))
    return S


def apply_score(r: TickerResult, scoring: dict) -> None:
    if r.type == "etf" or r.suppressed:
        r.score = None
        r.score_parts = []
        r.score_n = "not scored (fund or suppressed)"
        return
    weights = scoring.get("weights", {})
    sigs = build_signals(r, weights)
    avail = [s for s in sigs if s.score is not None]
    tw = sum(s.weight for s in avail)
    r.score = round(sum(s.score * s.weight for s in avail) / tw, 4) if tw else None
    r.score_partial = len(avail) < len(sigs)
    r.score_n = f"{len(avail)} of {len(sigs)}"
    r.score_parts = [s.to_dict() for s in sigs]


def rating(score: float | None, scoring: dict) -> str:
    if score is None:
        return "n/a"
    th = scoring.get("thresholds", {})
    if score >= th.get("attractive", 0.62):
        return "attractive"
    if score >= th.get("watch", 0.42):
        return "watch"
    return "expensive"
