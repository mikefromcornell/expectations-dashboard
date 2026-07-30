"""Smoke tests — no network required."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.config import load_watchlist, load_scoring, load_buffett
from src.models import TickerResult
from src.metrics.scoring import apply_score
from src.metrics.buffett import apply_buffett
from src.metrics.portfolio import compute
from src.providers.fundamentals import earnings_bucket
from datetime import date, timedelta


def test_watchlist_loads():
    wl = load_watchlist()
    assert len(wl) == 74
    assert len({t.symbol for t in wl}) == 74, "duplicates in watchlist"
    assert all(t.symbol == t.symbol.upper() for t in wl)


def test_scoring_renormalises_on_missing_inputs():
    r = TickerResult(symbol="X", price=100, pos52=50, pct_from_low=10, pct_from_high=-10)
    apply_score(r, load_scoring())
    assert r.score is not None and 0 <= r.score <= 1
    assert r.score_partial, "should be flagged partial when inputs are missing"
    # every component must carry a detail string
    assert all(p["detail"] for p in r.score_parts)


def test_funds_are_not_scored():
    r = TickerResult(symbol="QQQ", type="etf", price=500)
    apply_score(r, load_scoring())
    assert r.score is None


def test_earnings_buckets():
    t = date.today()
    assert earnings_bucket((t + timedelta(days=2)).isoformat(), t)[1] == "imminent"
    assert earnings_bucket((t + timedelta(days=6)).isoformat(), t)[1] == "approaching"
    assert earnings_bucket((t - timedelta(days=2)).isoformat(), t)[1] == "drift"
    assert earnings_bucket((t + timedelta(days=40)).isoformat(), t)[1] == "distant"
    assert earnings_bucket(None, t)[1] == "na"


def test_buffett_runs_with_missing_data():
    r = TickerResult(symbol="X", price=10)
    apply_buffett(r, load_buffett(), [])
    assert r.buffett["total"] == 7
    assert all(t["why"] for t in r.buffett["tests"].values())


def test_portfolio_handles_no_weights():
    out = compute([TickerResult(symbol="A", price=1)])
    assert out["positions"] == 0


def test_portfolio_math():
    a = TickerResult(symbol="A", price=10, beta=1.0, vol30=20, ret1y=10, downdev=10)
    b = TickerResult(symbol="B", price=10, beta=2.0, vol30=40, ret1y=30, downdev=20)
    a.weight_pct, b.weight_pct = 50.0, 50.0
    out = compute([a, b])
    assert out["positions"] == 2
    assert abs(out["beta"] - 1.5) < 1e-6
    assert abs(out["top5"] - 100.0) < 1e-6
    assert out["sharpe"] is not None and out["sortino"] is not None
    # sortino uses downside deviation only, so it must exceed sharpe here
    assert out["sortino"] > out["sharpe"]
