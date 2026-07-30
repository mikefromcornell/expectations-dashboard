"""Buffett Lens — deterministic checklist, no LLM.

Seven tests drawn from Buffett's written criteria. Thresholds live in
config/buffett.yaml so the user can disagree with a rule rather than a
black box. Not affiliated with Berkshire; not advice.
"""
from __future__ import annotations

from ..models import TickerResult

TEST_LABELS = {
    "moat": "Durable moat",
    "returns": "Returns on capital",
    "leverage": "Conservative leverage",
    "cashgen": "Cash generation",
    "stability": "Earnings stability",
    "circle": "Circle of competence",
    "price": "Margin of safety",
}

COMPLEX_TAGS = {"biotech", "crypto", "conservatorship", "spac", "pre-revenue"}


def moat_label(roic: float | None, cfg: dict) -> str:
    if roic is None:
        return "Unknown"
    if roic >= cfg.get("moat_roic_wide", 18.0):
        return "Wide"
    if roic >= cfg.get("moat_roic_narrow", 10.0):
        return "Narrow"
    return "None"


def apply_buffett(r: TickerResult, cfg: dict, tags: list[str] | None = None) -> None:
    if r.type == "etf" or r.suppressed:
        r.buffett = None
        return

    tags = [t.lower() for t in (tags or [])]
    moat = moat_label(r.roic, cfg)
    tests: dict[str, dict] = {}

    tests["moat"] = {
        "pass": moat in ("Wide", "Narrow"),
        "why": (f"ROIC {r.roic:.1f}% → {moat.lower()} moat" if r.roic is not None
                else "ROIC unavailable — cannot assess"),
    }
    tests["returns"] = {
        "pass": r.roic is not None and r.roic >= cfg.get("returns_min_roic", 15.0),
        "why": (f"ROIC {r.roic:.1f}% vs ~10% cost of capital" if r.roic is not None
                else "ROIC unavailable"),
    }
    de = r.debt_equity
    tests["leverage"] = {
        "pass": de is not None and de < cfg.get("max_debt_equity", 1.0),
        "why": f"Debt/equity {de:.2f}" if de is not None else "Debt/equity unavailable",
    }
    fm = r.fcf_margin
    tests["cashgen"] = {
        "pass": fm is not None and fm >= cfg.get("min_fcf_margin", 10.0),
        "why": f"FCF margin {fm:.1f}%" if fm is not None else "FCF margin unavailable",
    }
    stable = not r.new_listing
    tests["stability"] = {
        "pass": stable,
        "why": ("Listed under 12 months — no multi-year record to judge" if r.new_listing
                else "Has multi-year trading history"),
    }
    is_complex = any(t in COMPLEX_TAGS for t in tags) or r.suppressed
    tests["circle"] = {
        "pass": not is_complex,
        "why": ("Tagged complex — outside a simple earnings model" if is_complex
                else "Business model readable from public filings"),
    }
    mos = cfg.get("min_margin_of_safety_pct", 15.0)
    tests["price"] = {
        "pass": r.gap_pct is not None and r.gap_pct > mos,
        "why": (f"Your fair value implies {r.gap_pct:+.1f}% (need >{mos:.0f}%)"
                if r.gap_pct is not None else "No fair value set — price test cannot run"),
    }

    r.buffett = {
        "moat": moat,
        "de": de,
        "fcf_margin": fm,
        "tests": tests,
        "passed": sum(1 for t in tests.values() if t["pass"]),
        "total": len(tests),
        "labels": TEST_LABELS,
    }


def portfolio_observations(results: list[TickerResult]) -> list[dict]:
    """Rules-based portfolio-level notes."""
    eq = [r for r in results if r.type != "etf"]
    out: list[dict] = []
    if not eq:
        return out

    sectors: dict[str, int] = {}
    for r in eq:
        sectors[r.sector or "Unknown"] = sectors.get(r.sector or "Unknown", 0) + 1
    top_sec = max(sectors.items(), key=lambda kv: kv[1])
    pct = top_sec[1] / len(eq) * 100
    out.append({
        "tone": "warn" if pct > 30 else "ok",
        "label": "Concentration",
        "text": (f"{top_sec[0]} is {pct:.0f}% of equity names ({top_sec[1]} of {len(eq)}). "
                 "Buffett favours concentration in understood businesses — but sector "
                 "concentration is not the same as conviction concentration."),
    })

    wide = [r for r in eq if r.buffett and r.buffett["moat"] == "Wide"]
    out.append({
        "tone": "ok",
        "label": "Moat quality",
        "text": f"{len(wide)} names show wide-moat ROIC. This is the part of the book he'd like most.",
    })

    lev = [r for r in eq if r.debt_equity is not None and r.debt_equity > 1.5]
    if lev:
        out.append({
            "tone": "warn",
            "label": "Leverage",
            "text": (f"{len(lev)} names carry debt/equity >1.5 ({', '.join(r.symbol for r in lev[:6])}). "
                     "Balance-sheet risk is avoided regardless of business quality."),
        })

    nofv = [r for r in eq if r.gap_pct is None]
    if nofv:
        out.append({
            "tone": "warn",
            "label": "Margin of safety",
            "text": (f"{len(nofv)} of {len(eq)} equities have no fair value set, so the price test "
                     "cannot run. Closing this gap in expectations.yaml is the highest-value action."),
        })

    newl = [r for r in eq if r.new_listing]
    if newl:
        out.append({
            "tone": "warn",
            "label": "Track record",
            "text": (f"{', '.join(r.symbol for r in newl)} listed under 12 months — no multi-year "
                     "record exists, so the consistency test fails by construction."),
        })

    funds = [r for r in results if r.type == "etf"]
    if funds:
        out.append({
            "tone": "ok",
            "label": "Index exposure",
            "text": (f"{len(funds)} funds held — consistent with his standing advice for most "
                     "investors, and excluded from every test above."),
        })
    return out
