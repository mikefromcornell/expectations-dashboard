# Expectations Dashboard

A free, self-hosted equity dashboard built around the **expectations investing** framework
(Mauboussin/Rappaport): read the expectations embedded in a price, then watch for evidence they're wrong.

**Live site:** https://mikefromcornell.github.io/expectations-dashboard/

**Current config:** 74 tickers at **equal weight** (1.3514% each, summing to exactly 100%).
Fair values are **not set** — the Expectations Gap column and the 35%-weighted gap component of the
Expectations Score are inactive until you add them to `config/expectations.yaml`. An automatic
`20 × LTM EPS` rule is scaffolded there behind `auto_fair_value.enabled` (currently `false`).

Static site on GitHub Pages, data refreshed by GitHub Actions. **No server, no database, $0/month.**

---

## What it does

| Tab | Contents |
|---|---|
| **Dashboard** | 63 equities — price, day %, **% from 52-wk high/low**, range bar, earnings bucket, Expectations Score, P/E LTM & fwd, EV/EBITDA, ROIC, expectations gap, ownership signals |
| **Funds & ETFs** | 11 funds, only the columns that apply (no earnings/P/E/ROIC exists for them) |
| **Portfolio** | Editable position weights, allocation pies, beta, volatility, **Sharpe & Sortino**, HHI concentration, rules-based flags |
| **Buffett Lens** | Deterministic 7-test checklist from his published criteria — no LLM |
| **Mauboussin Lens** | LLM expectations analysis, on-demand, using *your* browser-stored Gemini key |
| **Discovery** | Dataroma conviction clusters, recent superinvestor activity, WSB links, manual-follow links |

Click any row for a detail drawer with the full score breakdown, valuation, risk, ownership and data provenance.

---

## Setup

### 1. Enable GitHub Pages
Settings → Pages → Source: **GitHub Actions**.

### 2. Add repository secrets
Settings → Secrets and variables → Actions:

| Secret | Required | Purpose |
|---|---|---|
| `DISCORD_WEBHOOK_URL` | for alerts | Single webhook; alert type is conveyed by embed colour |
| `EDGAR_USER_AGENT` | recommended | SEC requires `Name your@email.com`. See note below |
| `FINNHUB_API_KEY` | optional | Free fallback quote/earnings provider |
| `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` | optional | Enables the WSB mention summary |

> **EDGAR User-Agent is fussy.** Tested: `ExpectationsDashboard you@example.com` → 200;
> parentheses, slashes or a `users.noreply.github.com` address → **403**.

### 3. Run it
Actions → **Refresh data** → Run workflow. First full build takes ~13 minutes for 74 tickers.

---

## Managing tickers

`config/watchlist.yaml` is the **single source of truth** — git-tracked, so it persists across
refreshes, rebuilds and devices. Three ways in:

```bash
python -m src.watchlist add NVDA TSM      # validates before committing
python -m src.watchlist import file.csv   # bulk; strips cost basis automatically
python -m src.watchlist remove SOFI       # archives to config/archive.yaml, never deletes
python -m src.watchlist validate          # check every symbol still resolves
python -m src.watchlist weights           # show current sizing
```

Or use **+ Add Ticker** in the dashboard header — a static site has no backend, so it opens a
pre-filled GitHub issue containing the exact YAML block.

---

## Schedules

| Workflow | When | Does |
|---|---|---|
| `refresh.yml` | every 15 min, 13–20 UTC weekdays | quotes only |
| `refresh.yml` | 05:00 UTC daily | full rebuild + ownership |
| `daily.yml` | **10:00 America/New_York**, weekdays | rebuild + Discord summary + archive page |
| `pages.yml` | on push to `docs/` or `data/` | deploy |

`daily.yml` registers both 14:00 and 15:00 UTC and exits on whichever isn't 10am New York, so it
lands at 10am year-round without a DST edit.

---

## Honest limitations

**Quotes are delayed ~15 minutes.** Real-time consolidated quotes are a licensed product. The header
always shows data age and turns red past 6 hours.

**Sharpe and Sortino are conservative.** Weighted volatility is Σ(wᵢ·σᵢ), which ignores correlation
and overstates portfolio risk — so your true ratios are likely *better*. The covariance-matrix fix is
free (we already pull 5 years of history) and is the top v1.1 item.

**5 of 74 tickers have no free price source:** `FNMA`, `FMCC`, `SMEGF`, `MRAAY`, `EVVTY` — thin OTC
and unsponsored ADR lines. They render with a `no price` flag rather than silently showing zero.

**Politician trades are filing-level, not ticker-level.** The House/Senate Stock Watcher S3 mirrors
returned 403 as of 2026-07-30, so `data/politicians.json` uses the official House Clerk index: it
proves new disclosures exist and links the source PDFs, but doesn't claim which tickers were traded.
Coverage resumes automatically if a mirror returns.

**Reddit blocks unauthenticated `.json`** from datacenter IPs since May 2026 — the WSB summary needs
OAuth credentials. Without them the tab still shows working links.

**Provider fragility is designed for, not assumed away.** Yahoo rate-limits hard and Stooq deployed a
JavaScript proof-of-work wall, so the quote chain is Yahoo → StockAnalysis → Nasdaq → Finnhub, and a
failed ticker shows its last-good value marked stale rather than aborting the run.

---

## Privacy — this repo is public

Your watchlist, alert thresholds, fair values and thesis notes are **world-readable and permanent in
git history**. Mitigations in place: cost basis and share counts are stripped on import and never
committed; all credentials live in Actions Secrets; `.gitignore` covers `*.local.yaml`, `notes/`,
`config/positions*`.

If that's not acceptable, a private repo + Cloudflare Pages is also $0 — see PRD §8.1.

---

## Layout

```
config/     watchlist, expectations, scoring weights, buffett thresholds
src/        providers/ (quotes, fundamentals, ownership, earnings)
            metrics/   (scoring, buffett, portfolio)
            alerts/    (discord + daily summary)
            build.py, watchlist.py
data/       generated JSON, committed by Actions (free time-series archive)
docs/       the static site + daily/ archive pages
```

## Provenance

`mikefromcornell/economindTEST` was reviewed for reusable components. It is a fork of
`huhlig/economind` with **no LICENSE** and an explicit confidentiality header on 134 files, so
**no code, text, config or data was copied from it**. The scoring architecture, signal model and
valuation methodology here are independent re-implementations of design patterns and standard
finance techniques. See `PRD.md` §11.

---

*Not investment advice. All data is provided as-is from free sources that can and do break.*
