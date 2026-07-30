"""Portfolio statistics: allocation, beta, vol, Sharpe, Sortino, concentration.

Honesty note carried into the UI: weighted volatility is Sigma(w_i * sigma_i),
which ignores correlation and therefore OVERSTATES portfolio risk. Sharpe and
Sortino computed from it are consequently CONSERVATIVE. The covariance-matrix
fix is a v1.1 item.
"""
from __future__ import annotations

from ..models import TickerResult
from ..providers.http import get_text

FRED_DGS3MO = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS3MO"
DEFAULT_RF = 4.3


def risk_free_rate() -> tuple[float, str]:
    """3-month T-bill from FRED. Free, keyless CSV."""
    try:
        txt = get_text(FRED_DGS3MO)
        rows = [l.split(",") for l in txt.strip().splitlines()[1:]]
        for r in reversed(rows):
            if len(r) >= 2 and r[1] not in (".", "", None):
                return float(r[1]), f"FRED DGS3MO as of {r[0]}"
    except Exception:
        pass
    return DEFAULT_RF, "fallback default (FRED unavailable)"


def compute(results: list[TickerResult]) -> dict:
    held = [r for r in results if r.weight_pct]
    total_w = sum(r.weight_pct for r in held)
    if not held or total_w <= 0:
        return {
            "total_weight": 0.0, "positions": 0, "unset": len(results),
            "note": "No position weights set — add a Weight to any ticker to populate this tab.",
            "flags": [], "by_position": [], "by_sector": [], "by_type": [],
        }

    def wavg(attr: str) -> float | None:
        vals = [(r.weight_pct, getattr(r, attr)) for r in held if getattr(r, attr) is not None]
        if not vals:
            return None
        w = sum(v[0] for v in vals)
        return sum(a * b for a, b in vals) / w if w else None

    beta = wavg("beta")
    wvol = wavg("vol30")
    pret = wavg("ret1y")
    pdd = wavg("downdev")
    rf, rf_src = risk_free_rate()

    sharpe = ((pret - rf) / wvol) if (pret is not None and wvol) else None
    sortino = ((pret - rf) / pdd) if (pret is not None and pdd) else None

    srt = sorted(held, key=lambda r: r.weight_pct, reverse=True)
    top5 = sum(r.weight_pct for r in srt[:5])
    top10 = sum(r.weight_pct for r in srt[:10])
    hhi = sum(r.weight_pct ** 2 for r in held)
    eff = (10000.0 / hhi) if hhi else 0.0

    by_pos = [{"k": r.symbol, "v": round(r.weight_pct, 3)} for r in srt[:15]]
    rest = sum(r.weight_pct for r in srt[15:])
    if rest > 0:
        by_pos.append({"k": f"Other ({len(srt) - 15})", "v": round(rest, 3)})

    sect: dict[str, float] = {}
    for r in held:
        k = "Funds & ETFs" if r.type == "etf" else (r.sector or "Unknown")
        sect[k] = sect.get(k, 0.0) + r.weight_pct
    by_sector = sorted(
        [{"k": k, "v": round(v, 3)} for k, v in sect.items()], key=lambda d: -d["v"]
    )

    types: dict[str, float] = {}
    for r in held:
        k = {"etf": "ETF", "adr": "ADR"}.get(r.type, "Equity")
        types[k] = types.get(k, 0.0) + r.weight_pct
    by_type = [{"k": k, "v": round(v, 3)} for k, v in types.items()]

    flags: list[dict] = []
    if top5 > 50:
        flags.append({"tone": "bad", "text":
            f"Top 5 positions are {top5:.1f}% of the book — concentrated. "
            "Fine if deliberate, dangerous if drifted."})
    if eff and eff < 12:
        flags.append({"tone": "warn", "text":
            f"Effective positions {eff:.1f} despite {len(held)} holdings — the tail is doing "
            "almost nothing."})
    if beta and beta > 1.15:
        flags.append({"tone": "warn", "text":
            f"Beta {beta:.2f} — the book amplifies market moves in both directions."})
    semis = sum(r.weight_pct for r in held
                if r.symbol in {"ASML", "TSM", "AMD", "INTC", "AVGO", "SMEGF", "MRAAY"})
    if semis > 8:
        flags.append({"tone": "bad", "text":
            f"Semiconductor exposure {semis:.1f}% across ASML/TSM/AMD/INTC/AVGO — and Situational "
            "Awareness discloses large put positions against exactly these names. Not a reason to "
            "sell; a reason to know the correlation."})
    unset = [r for r in results if not r.weight_pct]
    if unset:
        flags.append({"tone": "info", "text":
            f"{len(unset)} watchlist names have no weight set — excluded from every statistic here."})
    if abs(total_w - 100.0) > 0.5:
        flags.append({"tone": "warn", "text":
            f"Weights total {total_w:.2f}%, not 100%. Use 'Normalise' or edit watchlist.yaml."})
    if not flags:
        flags.append({"tone": "ok", "text": "No concentration flags triggered."})

    return {
        "total_weight": round(total_w, 2),
        "positions": len(held),
        "unset": len(unset),
        "beta": round(beta, 3) if beta is not None else None,
        "wvol": round(wvol, 2) if wvol is not None else None,
        "ret1y": round(pret, 2) if pret is not None else None,
        "downdev": round(pdd, 2) if pdd is not None else None,
        "risk_free": rf,
        "risk_free_source": rf_src,
        "sharpe": round(sharpe, 3) if sharpe is not None else None,
        "sortino": round(sortino, 3) if sortino is not None else None,
        "top5": round(top5, 2),
        "top10": round(top10, 2),
        "hhi": round(hhi, 1),
        "effective_positions": round(eff, 1),
        "largest": {"symbol": srt[0].symbol, "weight": round(srt[0].weight_pct, 2)},
        "by_position": by_pos,
        "by_sector": by_sector,
        "by_type": by_type,
        "flags": flags,
        "methodology": (
            "Weighted volatility is Sigma(w_i*sigma_i) and ignores correlation, so it overstates "
            "portfolio risk. Sharpe and Sortino derived from it are therefore conservative — your "
            "true ratios are likely better. Covariance-matrix version is a v1.1 item."
        ),
    }
