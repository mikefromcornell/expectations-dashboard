# Review: `mikefromcornell/economindTEST` — what's reusable

**Reviewed:** 2026-07-30 · 27 MB, 19 commits, 166 Rust files + 1 Python file + SvelteKit dashboard

## ⚠️ Read this first: the repo is a fork, and it is not licensed to you

`economindTEST` is a **fork of [`huhlig/economind`](https://github.com/huhlig/economind)**. Every commit, including the single "Checkpoint" commit that contains all the content, is authored by **Hans W. Uhlig (huhlig@gmail.com)**. You did not write this code.

Two hard blockers:

1. **There is no LICENSE file.** Under default copyright, "no license" means **all rights reserved** — no permission to copy, modify, or redistribute.
2. **134 of the 166 Rust files carry an explicit restrictive header:**
   > *"This source code is protected under international copyright law. All rights reserved… This file is confidential and only available to authorized individuals with the permission of the copyright holders. If you encounter this file and do not have permission, please contact the copyright holders and delete this file."*

**This collides directly with your decision to make `expectations-dashboard` public.** Copying this code into a public repo would republish someone else's confidential, all-rights-reserved work under your name. That's a real legal exposure, not a theoretical one — and a public repo makes it trivially discoverable, including by the author.

**My recommendation: take ideas and patterns, copy zero lines of code.** Everything genuinely useful here is a *design decision* — which is not copyrightable — and all of it is re-implementable from scratch in a few hours. That's what I've scoped below.

> Note: `trading_bot.py` and `universe.csv` carry **no** copyright header, unlike the Rust files. But they're still authored by Uhlig in an unlicensed repo, so the same default-copyright rule applies. Don't copy them either.
> If you want actual reuse rights, the clean path is to ask Uhlig to add a permissive license (MIT/Apache-2.0) to the upstream repo. Until then, patterns only.

---

## What's in there

| Area | Contents | Relevance to us |
|---|---|---|
| `trading_bot.py` (39 KB) | Standalone Python swing scanner: yfinance, RSI/MACD/Bollinger, earnings detection, Claude news sentiment, composite scoring, HTML report | **Highest** — same stack, same problem shape |
| `personas/` (23 JSON) | LLM analyst personas: Buffett, Munger, Burry, Damodaran, Lynch, Pabrai, Ackman, Druckenmiller + `valuation.json`, `fundamentals.json` | **High** — as a *methodology* reference |
| `datafeed/` (Rust) | Provider trait abstraction + 10 implementations (Tiingo, Finnhub, Polygon, AlphaVantage, FMP, Marketstack, StockData, Kibot) | **Medium** — the abstraction shape |
| `universe.csv` | 493 S&P 500 symbols | Low — trivially regenerable |
| `NOTES.md` | Small table ranking free data providers by use case | Medium — sanity-checks our source picks |
| `dashboard/` (SvelteKit) | 10 Svelte routes, WebSocket client, auth store | Low — wrong architecture for us (needs a server) |
| `strategies/`, `crates/`, `src-tauri/` | Momentum, mean-reversion, Kelly sizing, ATR sizing; DuckDB/Postgres; Tauri desktop shell | **None** — trading-execution platform, not expectations investing |

---

## The 6 ideas worth adopting

### 1. ⭐ Composite scoring with explicit weights → **"Expectations Score"**
Their scanner reduces many signals to one 0–1 number using a declared weight table, then buckets it BUY / WATCH / AVOID at fixed thresholds. Each signal carries a `score` **and a human-readable `detail` string** explaining itself.

That last part is the good bit: the dashboard never shows an unexplained number. Adapted to your framework — replacing their momentum/RSI inputs with expectations inputs:

```yaml
expectations_score:
  weights:
    expectations_gap:    0.35   # your fair value vs. price
    position_52wk:       0.20   # where in the 52-wk range
    valuation_vs_history: 0.15  # P/E, EV/EBITDA vs. own 5-yr
    roic_trend:          0.10
    insider_activity:    0.10
    superinvestor_flow:  0.10
  thresholds: { attractive: 0.62, watch: 0.42 }
```
Gives you one sortable "where should I look today" column, with every component hoverable and explained. **Re-implemented from scratch, our weights, our signals.**

### 2. ⭐ `Signal` / `StockResult` dataclass pattern
A `Signal` is `{name, score, detail, raw}`; a `StockResult` aggregates signals plus price/company/earnings and — importantly — an **`error` field per ticker**. One ticker failing never kills the run; it renders as a visible error row.

For a 50-ticker job on flaky free APIs, that per-ticker error isolation is exactly right. **Adopt the pattern** (a 4-field dataclass is not meaningfully copyrightable, and I'll write it fresh).

### 3. ⭐⭐ The `valuation.json` persona = a ready-made spec for your v1.1 reverse-DCF
This is the most valuable single artifact in the repo. It specifies a **four-model weighted valuation**:

| Model | Weight |
|---|---|
| Enhanced DCF w/ WACC + bear/base/bull scenarios (20/60/20 probability) | 35% |
| Owner Earnings (Buffett): NI + D&A − capex − ΔWC | 35% |
| EV/EBITDA vs. median historical multiple | 20% |
| Residual Income / EBO: book value + PV of excess returns | 10% |

Aggregate gap = (intrinsic − market cap) / market cap; bullish >+15%, bearish <−15%.

That's a coherent, defensible valuation methodology that maps almost perfectly onto expectations investing — and it directly informs the v1.1 solver. **Methodology is not copyrightable**; I'd implement it independently. It also usefully cross-checks your v1 hand-entered `fair_value`.

### 4. Provider trait abstraction (validates our §4 design)
Their Rust `datafeed` splits providers into narrow traits — `DailyDataProvider`, `FundamentalsProvider`, `NewsProvider`, `StreamingMarketDataProvider` — with 10 swappable implementations behind them. Notably, half sit in an `archive/` folder: **providers they tried and abandoned.**

This is independent confirmation of the fallback-chain design in PRD §4, and evidence that free providers *do* break and get swapped. Reinforces keeping Yahoo/Stooq/Finnhub behind one interface. No code needed — we already planned this.

### 5. Earnings-catalyst day-bucketing
Their `analyze_earnings()` buckets days-to-earnings into windows (0–3d high-volatility, 4–10d in-window, −3–0d post-earnings drift) rather than showing a raw date. Small, but a genuinely better UI primitive than "2026-08-14" — and it feeds alerting cleanly. Our PRD already has 7/1-day alerts; I'll add a post-earnings-drift window since that's when expectations actually get revised.

### 6. Self-contained dark-mode HTML report
`save_html_report()` emits a single standalone dark-themed HTML file with inline styles, score bars, and color-coded signals — no build step, no framework. That's precisely the right shape for our **`/daily` summary archive pages** (PRD §5.3). **Concept only; I'll write our own markup.** Their inline-style-everything approach is genuinely worth copying as an *approach* because it makes each archived daily page permanently self-contained.

---

## What to explicitly skip

- **Rust workspace, DuckDB/Postgres, Tauri desktop shell** — needs a server and a build toolchain; violates the free-static-hosting constraint.
- **SvelteKit dashboard** — assumes a live backend with WebSocket + auth. Our data is pre-baked JSON.
- **Trading strategies** (momentum, mean-reversion, Kelly/ATR sizing) — that's systematic short-horizon trading. Actively *opposed* to expectations investing, which is about long-horizon divergence between price-implied and fundamental expectations.
- **`universe.csv`** — we already scrape S&P 500 from Wikipedia if needed; you're supplying 50 names anyway.
- **Claude news-sentiment integration** — needs a paid Anthropic key. Breaks the $0 constraint. (Optional post-v1 if you ever want it.)
- **`ANTHROPIC_API_KEY` / `SIMFIN_API_KEY` / Postgres env pattern** — irrelevant to a static site; our only secrets are the Discord webhook and Finnhub key.

---

## Proposed PRD amendments

| # | Change | Section | Version |
|---|---|---|---|
| A | Add **Expectations Score** — weighted composite, config-declared weights, per-component `detail` strings, sortable column | §5.1, §5.4 | v1 |
| B | Adopt `Signal`/`StockResult` shape with **per-ticker error isolation**; failed tickers render as error rows, never kill the run | §3 | v1 |
| C | Earnings **day-bucketing** incl. post-earnings-drift window (−3→0d) | §5.1, §5.5 | v1 |
| D | `/daily` archive pages as **self-contained inline-styled HTML** | §5.3 | v1 |
| E | Adopt the **4-model weighted valuation** (DCF+WACC / Owner Earnings / EV-EBITDA / Residual Income) as the v1.1 solver spec | §5.4 | v1.1 |
| F | Add **§11 Provenance** documenting that no code was copied from `economindTEST` | §11 | v1 |

None of these change the architecture, hosting, or cost model. A–D add maybe half a day to P1–P3.

---

## Bottom line

The genuinely valuable content is **one Python file and one JSON persona** — `trading_bot.py`'s scoring architecture and `valuation.json`'s four-model methodology. Both are *ideas*, and ideas are free to reuse. The other 26 MB is a Rust algorithmic-trading platform solving a different problem with an architecture incompatible with your $0 static-hosting constraint.

**Recommendation: adopt amendments A–F, copy no code, and add a provenance note to the README.** If you want real code reuse, ask Uhlig to slap MIT or Apache-2.0 on the upstream repo first.
