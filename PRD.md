# PRD — "Expectations Dashboard"
**A free, self-hosted equity monitoring dashboard for expectations-investing**

| Field | Value |
|---|---|
| Owner | You (single user) |
| Date | 2026-07-30 |
| Status | **APPROVED v4 — amendments A–F merged, ticker management added; blocked on 2 inputs (see §10)** |
| Cost target | $0/month, hard constraint |
| Repo | `github.com/mikefromcornell/expectations-dashboard` — **public** |
| Hosting | GitHub Pages (static site) + GitHub Actions (scheduled data refresh) |
| Notifications | Discord webhook |
| Watchlist | **74 tickers** (55 equities · 8 ADRs · 11 ETFs) — loaded, see `watchlist-validation.md` |

---

## 1. Problem & Goal

You invest using the **expectations investing** framework (Mauboussin/Rappaport): the job is not to forecast, but to read the expectations already embedded in the price, then watch for evidence that those expectations are wrong.

Today that means opening 6–8 tabs (Yahoo, Dataroma, OpenInsider, Capitol Trades, an earnings calendar, a spreadsheet). The goal is **one page** that answers, every morning: *what changed in the expectations embedded in my names, and who smart is buying or selling?*

### Success criteria
1. One URL, loads in <2s, works on phone.
2. Every ticker in the watchlist shows % from 52-wk high and % from 52-wk low (the non-negotiable baseline metric).
3. Next earnings date visible for every ticker; no surprises.
4. Daily summary published at **10:00 AM ET every trading day**, pushed to Discord.
5. Total recurring cost: $0.
6. Zero manual data entry beyond editing one `watchlist.yaml`.

### Non-goals (v1)
- Order execution / brokerage integration.
- Backtesting engine.
- Multi-user accounts, auth, or sharing.
- Options data, crypto, non-US listings.
- Tick-by-tick streaming (see §3 on what "live" realistically means).

---

## 2. The honest trade-off you need to approve first

**"Live real-time" and "completely free" are in direct tension.** Real-time consolidated US equity quotes are a licensed product; every genuinely free source is either delayed 15 minutes, unofficial (Yahoo scraping), or rate-limited to a trickle.

Proposed resolution — a **two-speed** model:

| Layer | Freshness | Mechanism | Cost |
|---|---|---|---|
| **Quotes** (price, day %, 52-wk position) | ~1 min, on-demand | Browser fetches Yahoo/Stooq quote endpoint directly on page load + every 60s while tab is open | $0 |
| **Snapshot** (all metrics, pre-computed) | Every 15 min, market hours | GitHub Actions cron → commits JSON to repo | $0 |
| **Fundamentals** (P/E, EV/EBITDA, ROIC) | Nightly | GitHub Actions cron, 01:00 ET | $0 |
| **Ownership** (Dataroma, insiders, politicians) | Daily | GitHub Actions cron, 06:00 ET | $0 |

So the dashboard *feels* live — prices tick while you watch it — but heavy data is pre-baked.

> **DECIDED (2026-07-30):** Delayed data accepted in exchange for $0 cost and the highest/unlimited symbol cap. No Finnhub websocket (50-symbol cap, exposes key client-side). Quotes come from **keyless, uncapped sources** (Yahoo `/v7/finance/quote` batched, Stooq CSV fallback) polled from the browser every 60s — no per-symbol ceiling, no API key.
>
> **Mandatory UI requirement:** every data panel must display its freshness explicitly — a persistent header badge (`Quotes: delayed ~15 min · updated 10:42:03 ET`) plus a per-panel "as of" timestamp, and a red **STALE** banner if data exceeds its expected refresh age. The dashboard must never imply data is more current than it is.

---

## 3. Architecture

```
┌──────────────────────────────────────────────────────────┐
│  GitHub Actions (cron)                                    │
│                                                           │
│  quotes.yml      */15 * 13-21 * * 1-5   → data/quotes.json│
│  fundamentals.yml 0 5 * * *             → data/fund.json  │
│  ownership.yml   0 10 * * *             → data/own.json   │
│    ├ EDGAR Form 4 + politicians : daily                   │
│    └ Dataroma                   : every 72h (ETag-gated)  │
│  daily.yml       0 14 * * 1-5 (10am ET) → daily summary   │
│                                          + Discord push   │
└───────────────────────┬──────────────────────────────────┘
                        │ commits JSON to /data
                        ▼
┌──────────────────────────────────────────────────────────┐
│  GitHub Pages — static site (vanilla JS + Tailwind CDN)  │
│  reads /data/*.json  +  polls live quotes client-side     │
└──────────────────────────────────────────────────────────┘
```

**Why this shape:** no server, no database, no secrets in the browser (except optionally a read-only quote key), free forever, and the JSON commit history gives you a free time-series archive of every metric as a side effect.

### Repo layout
```
expectations-dashboard/
├── config/
│   ├── watchlist.yaml        # SOURCE OF TRUTH — tickers + per-ticker settings
│   ├── expectations.yaml     # your fair values / implied growth per ticker
│   ├── scoring.yaml          # Expectations Score weights & thresholds
│   ├── archive.yaml          # removed tickers, timestamped (never deleted)
│   └── import/               # drop CSVs here → auto-merged by Action
├── src/
│   ├── providers/            # one module per data source, all cached
│   ├── metrics/              # 52wk position, ROIC, valuation
│   ├── scoring.py            # Signal model + Expectations Score
│   ├── watchlist.py          # add / remove / import / validate CLI
│   ├── alerts/               # rules engine
│   └── build.py              # orchestrator → writes /data/*.json
├── data/                     # generated JSON (committed by Actions)
├── docs/                     # GitHub Pages root (index.html, daily.html, app.js)
└── .github/workflows/
```

### 3.1 Hosting — resolved

Public repo → **GitHub Pages**, served at `https://mikefromcornell.github.io/expectations-dashboard/`. Unlimited Actions minutes, unlimited Pages bandwidth, no third-party host, no login wall. Simplest and cheapest path. Privacy consequences handled in §8.1.

### Cost / limits check
- > **DECIDED (revised): public repo + GitHub Pages.** Public repos get **unlimited Actions minutes**, so the 2,000 min/month concern disappears entirely and we can keep the 15-min quote cadence without rationing. Pages serves free from public repos. This is the simplest possible $0 setup.
  - ⚠️ **Trade-off accepted:** the repo is world-readable. See §8.1 for the privacy mitigations this makes mandatory.
- ⚠️ GitHub silently disables cron workflows after **60 days of repo inactivity**. Mitigation: the daily job commits to the repo, which itself counts as activity — self-sustaining.
- Actions cron is UTC and can be delayed by several minutes under load; the 10:00 ET job will be scheduled with a DST-aware guard so it never fires at 9am or 11am.

---

## 4. Data sources (all free tiers)

| Data | Primary | Fallback | Notes / risk |
|---|---|---|---|
| Quotes, 52-wk hi/lo, day % | Yahoo batch quote (keyless, **no symbol cap**) | Stooq CSV (keyless), Finnhub `/quote` | Delayed ~15 min; labeled as such in UI. Yahoo is unofficial and periodically breaks → fallback chain is mandatory |
| Next earnings date | Finnhub `/calendar/earnings` (free) | Yahoo, Nasdaq | Confirmed vs. estimated flag surfaced in UI |
| LTM P/E, Fwd P/E, EV/EBITDA | Yahoo `info` + statements | FMP free tier | Fwd P/E depends on analyst consensus availability |
| **ROIC** | **Computed by us**: NOPAT ÷ (total debt + equity − cash − goodwill adj.) | — | Vendors disagree wildly on ROIC; computing it ourselves makes it consistent and auditable. Formula documented in-repo. |
| Insider buying | **SEC EDGAR Form 4** (official, free, no key) | OpenInsider scrape | EDGAR requires a declared User-Agent; 10 req/s limit. Cluster-buy detection included. |
| Politician trades | House/Senate Stock Watcher JSON | Capitol Trades / EODHD free tier | 45-day disclosure lag is inherent — UI will label it |
| Superinvestors | **Dataroma** — scraped **once per 72h** (configurable 24–72h), heavily cached | 13F via EDGAR | ⚠️ See §8. 72h is ample: 13F data changes quarterly, not daily |
| Catalysts | Manual entries in `watchlist.yaml` + auto (earnings, investor days, lockups) | — | v1: mostly manual; you own the catalyst calendar |

**API keys needed (all free signups):** Finnhub. Everything else is keyless. Keys live in GitHub Actions Secrets, never in the browser.

---

## 5. Features

### 5.1 Main dashboard (`/`)
Sortable, filterable table — one row per ticker:

| Column | Detail |
|---|---|
| Ticker / Name | + sector badge |
| Price | live, colored on tick |
| Day % | |
| **% from 52-wk high** | e.g. `−23.4%` — **core metric, always visible** |
| **% from 52-wk low** | e.g. `+11.2%` |
| **52-wk position bar** | visual sparkline showing where price sits in the range |
| Next earnings | date + days-until, red if ≤7 days |
| Next catalyst | from config, with countdown |
| LTM P/E · Fwd P/E · EV/EBITDA · ROIC | color-scaled vs. own 5-yr history |
| Signals | 🟢 insider buy · 🏛 politician buy · 💼 superinvestor add — icons, hover for detail |
| Expectations gap | market-implied growth vs. your assumption (see 5.4) |
| **Expectations Score** | single 0–1 composite, sortable — the "where do I look today" column (see 5.6) |

**Amendment C — earnings day-bucketing.** The earnings column shows a bucketed state, not just a raw date, because the bucket is what drives action:

| Bucket | Window | Display |
|---|---|---|
| Imminent | 0–3 days | 🔴 `Earnings in 2d` — high-volatility catalyst |
| Approaching | 4–10 days | 🟠 `Earnings in 7d` |
| **Post-earnings drift** | −3–0 days | 🔵 `Reported 2d ago` — **expectations are being revised right now; this is the window that matters most for your framework** |
| Distant | >10 days | ⚪ `Nov 14 (est.)` |

Estimated vs. confirmed dates are visually distinguished (`est.` suffix + lighter weight).

Click a row → **detail drawer**: price chart, full valuation history, all insider transactions (12mo), all politician trades, all superinvestor positions from Dataroma, your reverse-DCF inputs.

### 5.2 Dataroma discovery section (separate page, `/discovery`)
Independent of your watchlist — this is idea generation:
- **Recent superinvestor buys** across all Dataroma-tracked managers, last 90 days.
- Filters: manager, sector, new position vs. add, position size % of portfolio.
- **Conviction cluster flag:** ≥3 managers buying the same name in the same quarter.
- One-click **"add to watchlist"** → opens a pre-filled GitHub issue/PR editing `watchlist.yaml` (keeps everything git-tracked, no backend needed).

### 5.3 Daily summary page (`/daily`) — refreshed 10:00 AM ET
Auto-generated, and pushed to Discord as an embed:
1. **Overnight/pre-market movers** in your watchlist (>2%).
2. **Earnings this week** — table with dates.
3. **New 52-wk highs/lows** and anyone who crossed a threshold you set.
4. **New insider buys** (Form 4s filed since yesterday).
5. **New politician disclosures** touching your names.
6. **Dataroma changes** (when 13F season delivers them).
7. **Expectations watch** — names where market-implied growth moved >X% vs. yesterday.
8. Archived: `/daily/2026-07-30.html`, so you build a searchable journal.

***Amendment D — self-contained archive pages.*** Each archived daily page is written as a **standalone HTML file with fully inline styles** — no external CSS, no framework, no JS dependency. A page from three years ago renders identically forever, even if the dashboard's styling is rewritten. Each is ~30 KB, opens offline, and can be emailed or saved as PDF as-is.

### 5.4 Expectations-investing layer (the differentiator)
For each ticker, `expectations.yaml` holds your assumptions (sales growth, operating margin, incremental investment rate, WACC, forecast period). The engine runs a **reverse DCF**:
- Solves for the **market-implied sales growth rate** at today's price.
- Shows **your estimate vs. market-implied** → the expectations gap.
- Computes the **expectations infliction point**: how far a driver must move to justify the price.
- Tracks how implied expectations drift over time (chart), because *the change* is the signal.

> **DECIDED: simplified version in v1.** No solver in the first release. You enter your own numbers per ticker in `expectations.yaml`:
> ```yaml
> AAPL:
>   my_implied_growth: 0.06      # what you think is justifiable
>   market_implied_growth: 0.11  # what you read the price as embedding
>   fair_value: 165.00           # optional
>   notes: "Services mix shift already priced in"
> ```
> The dashboard computes and displays the **expectations gap** (market − yours), a fair-value vs. price gauge, upside/downside %, and colors the row by gap size. It tracks how your entries change over time via git history, so you get the drift chart for free.
>
> **The automated reverse-DCF solver moves to v1.1** — it will back-solve `market_implied_growth` from price so you no longer hand-enter it, and add expectations infliction points. The v1 config schema is deliberately designed so the solver later just *populates* the same field, meaning no migration and no rework.

**Amendment E — v1.1 solver specification (four-model weighted valuation).** Rather than a single DCF, the solver will triangulate across four independent models and report a probability-weighted intrinsic value:

| Model | Weight | Method |
|---|---|---|
| Enhanced DCF with WACC | 35% | Multi-stage FCF growth, bear/base/bull scenarios probability-weighted 20/60/20. WACC from CAPM + after-tax cost of debt. |
| Owner Earnings (Buffett) | 35% | Net income + D&A − capex − ΔWorking capital, discounted at required return with terminal value. |
| EV/EBITDA multiple | 20% | Implied equity value from the company's own median historical multiple applied to current EBITDA. |
| Residual Income (EBO) | 10% | Book value + PV of excess returns above cost of equity. |

Aggregate gap = (weighted intrinsic value − market cap) / market cap. Attractive >+15%, expensive <−15%, neutral in between. Each model reports its own value, implied gap, and a sensitivity note; models lacking data are dropped and weights re-normalised.

Two reasons this is the right target: it cross-checks the `fair_value` you hand-enter in v1 (a large divergence is itself a signal worth flagging), and multi-model triangulation is far more robust than one DCF whose output is hostage to a single terminal-growth assumption. *Methodology derived from an independent reading of standard valuation literature — see §11.*

### 5.5 Adding & managing tickers — persistent, three ways

**Requirement:** adding a ticker must be easy, must persist across refreshes and rebuilds, and must survive a laptop change. The single source of truth is **`config/watchlist.yaml` in the repo** — git-tracked, versioned, diffable, restorable. Everything below is just a different front door onto that one file.

There is deliberately **no browser-local storage** as a source of truth: `localStorage` is per-device, silently wiped by a cache clear, and invisible to the GitHub Actions jobs that build the data. It's used only as a UI convenience cache.

#### Method 1 — Edit the YAML (canonical)
```yaml
tickers:
  - symbol: AAPL
    name: Apple Inc.
    fair_value: 165.00          # optional — drives expectations gap
    market_implied_growth: 0.11 # optional
    alert_low: 170              # optional — per-ticker overrides
    alert_high: 260
    catalyst:
      date: 2026-09-09
      note: iPhone event
    tags: [core, mega-cap]
    notes: "Services mix shift already priced in"
  - symbol: MSFT               # minimal form — symbol alone is valid
```
Only `symbol` is required. Everything else is optional and can be filled in later.

#### Method 2 — ⭐ "Add Ticker" button in the dashboard (the easy path)
A persistent **`+ Add Ticker`** control in the dashboard header opens a small modal: symbol (with live validation + company-name lookup), optional fair value, alert thresholds, tags, notes.

On submit, since a static site has no backend, it uses **GitHub's prefilled-form URL scheme** to open a pre-populated `watchlist.yaml` edit or a new Issue in a new tab — you press one button to commit. That commit triggers the rebuild, and the ticker appears on the next refresh.

- **Signed in to GitHub on that device:** ~2 clicks, works on desktop and phone.
- **Optional upgrade (v1.1):** a GitHub *Issue Form* + a `watchlist-bot` Action that parses the issue and commits the YAML edit automatically — zero manual editing, works from the GitHub mobile app. Recommended once v1 is stable.

Same mechanism powers **`+ Add to watchlist`** on every row of the `/discovery` page (PRD §5.2), so a superinvestor buy becomes a tracked position in two clicks.

#### Method 3 — Bulk CSV import
Drop a CSV at `config/import/*.csv` and push; an Action merges it into `watchlist.yaml`, de-duplicating by symbol and preserving existing per-ticker settings. Also runnable locally:
```bash
python -m src.watchlist add NVDA TSMC ASML      # append symbols
python -m src.watchlist import my_holdings.csv  # bulk merge
python -m src.watchlist remove SOFI             # remove
python -m src.watchlist validate                # check symbols resolve
```
Recognised CSV headers (all optional except `ticker`/`symbol`): `ticker`, `name`, `fair_value`, `alert_low`, `alert_high`, `catalyst_date`, `catalyst_note`, `tags`, `notes`.

#### Validation & safety
- Every added symbol is **validated against the quote provider before commit** — typos and delisted tickers are rejected with a clear message rather than silently producing empty rows.
- Adds are **idempotent**: re-adding an existing symbol updates fields instead of duplicating.
- **Removing a ticker archives it** to `config/archive.yaml` with a timestamp rather than deleting, so you keep the history of what you used to watch and why.
- ⚠️ Per §8.1, the ingest step **strips any cost-basis or share-count columns** — they are never committed to the public repo.
- Watchlist size is soft-capped at 100 with a warning; the free-tier data budget is comfortable to ~100 symbols.

### 5.6 Expectations Score — weighted composite *(Amendment A)*

One sortable 0–1 number per ticker answering "where should I spend attention today." Weights are declared in `config/scoring.yaml`, fully editable, must sum to 1.0:

```yaml
weights:
  expectations_gap:     0.35   # your fair_value vs. price — the core of the framework
  position_52wk:        0.20   # where price sits in the 52-wk range
  valuation_vs_history: 0.15   # LTM P/E & EV/EBITDA vs. own 5-yr percentile
  roic_trend:           0.10   # improving / stable / deteriorating
  insider_activity:     0.10   # net open-market buys, 90d
  superinvestor_flow:   0.10   # Dataroma adds vs. trims, last 2 quarters
thresholds:
  attractive: 0.62   # 🟢
  watch:      0.42   # 🟡  (below → 🔴 expensive/avoid)
```

**Non-negotiable design rule (from the economind review): every component carries a human-readable `detail` string.** Hovering the score expands to show each input, its sub-score, its weight, and a plain-English explanation — e.g. *"52-wk position 0.81 — trading 4.2% above 52-wk low, in the bottom decile of its range."* No unexplained numbers ever appear on the dashboard.

Missing inputs are handled by **re-normalising over available weights**, never by silently substituting 0.5 — and the UI marks partial scores with a `*` plus a "scored on 4 of 6 inputs" note.

### 5.7 Signal / result model *(Amendment B)*

Every metric is produced as a `Signal { name, score, detail, raw, as_of, source }` and aggregated per ticker into a `TickerResult` that includes a **per-ticker `errors[]` list**.

**Failure isolation is a hard requirement:** one ticker failing — or one provider 429-ing — must never abort the run of the other 49. A failed ticker renders as a visible error row with its last-good cached values greyed out and an "as of" timestamp, so you can always tell stale data from fresh data. This matters because we're deliberately built on free, unofficial, rate-limited endpoints.

### 5.8 Alerts (Discord)
Config-driven rules in `watchlist.yaml`, per-ticker overrides supported:

| Category | Default triggers |
|---|---|
| Price / range | within 5% of 52-wk low; new 52-wk high/low; day move >5% |
| Valuation | Fwd P/E crosses your band; EV/EBITDA below 5-yr trough |
| Events | earnings in 7 / 1 days; earnings released; catalyst date reached |
| Insiders | any officer/director open-market buy >$100k; cluster buy |
| Politicians | any disclosed purchase in a watchlist name |
| Superinvestors | new position or >25% add by a tracked manager |
| Expectations | price crosses your `fair_value`; expectations gap widens past your threshold; **Expectations Score crosses the attractive/watch threshold** |
| Post-earnings | **new: ticker enters the post-earnings-drift window (−3→0d)** — prompt to revisit your assumptions while expectations are being repriced |

> **DECIDED: one Discord channel, one webhook secret** (`DISCORD_WEBHOOK_URL`). To stop the 10am summary being buried among alerts, messages are visually differentiated: alerts post as compact color-coded embeds (red = downside/52-wk low, green = insider/superinvestor buy, amber = earnings imminent), the daily summary posts as a single large embed with a title banner. A dedupe state file (`data/.alert_state.json`) prevents repeat pings for the same event.

---

## 6. Delivery plan

| Phase | Scope | Est. |
|---|---|---|
| **P0 — Skeleton** | Repo, config schema, Actions scaffolding, Pages deploy, 50-ticker quote pipeline, 52-wk high/low table, `Signal`/`TickerResult` model + error isolation *(B)* | Day 1 |
| **P0.5 — Ticker management** | `watchlist.py` CLI (add/remove/import/validate), CSV bulk import Action, `+ Add Ticker` modal + prefilled-GitHub flow, archive-on-remove | Day 1–2 |
| **P1 — Core data** | Earnings dates + day-bucketing *(C)*, valuation metrics, ROIC, detail drawer | Day 2 |
| **P2.5 — Scoring** | `scoring.yaml`, Expectations Score with per-component detail strings, sortable column *(A)* | Day 3 |
| **P2 — Ownership** | EDGAR Form 4, politicians, Dataroma scraper + `/discovery` page | Day 3 |
| **P3 — Notify** | Discord alerts, rules engine, 10am daily summary + archive | Day 4 |
| **P3.5 — Expectations (simplified)** | `expectations.yaml` schema, gap columns, fair-value gauge, gap alerts | Day 4 |
| **P4 — Polish** | Mobile layout, dark mode, failure/staleness banners, self-contained daily archive pages *(D)*, README + provenance note *(F)* | Day 5 |
| **v1.1** | Four-model reverse-DCF solver *(E)*, expectations infliction points, watchlist-bot Issue Form automation | +1–2 weeks |

## 7. Risks

| Risk | Mitigation |
|---|---|
| Yahoo endpoint breaks | Multi-provider fallback chain; dashboard shows a "stale data" banner rather than silently lying |
| Free-tier rate limits (Finnhub ~60/min) | Aggressive caching, batching, staggered refresh; 50 tickers is well within limits |
| Dataroma blocks scraping | **72h fetch cadence**, polite UA, ETag/If-Modified-Since, exponential backoff, serve last-good cache on failure; fallback to raw 13F parsing from EDGAR |
| Cron drift / silent workflow disable | Timestamp on every panel; heartbeat alert to Discord if data >6h stale |
| Data quality (ROIC, Fwd P/E) | Show source + as-of date on hover; you can override any figure in config |

## 8. Legal / ToS note
Dataroma has no public API; this design scrapes it **once per 72 hours** for **personal, non-commercial** use and caches aggressively. That's low-risk but technically at their discretion. The repo will keep the Dataroma provider isolated behind an interface so it can be swapped for direct EDGAR 13F parsing if needed. Yahoo Finance access via `yfinance` is likewise unofficial. Since the repo is now **public**, the "personal, non-commercial" framing is weaker than it would be in a private repo — scraped Dataroma data will sit in a world-readable `/data` folder. Mitigations: fetch only every 72h, store only the fields the dashboard renders (not full page dumps), add a `README` disclaimer crediting Dataroma and stating non-commercial personal use, and keep the provider swappable to EDGAR 13F parsing. Same unofficial-access caveat applies to Yahoo.

### 8.1 Privacy consequences of a public repo — please read

You reversed the earlier "private" decision to get free GitHub Pages and unlimited Actions minutes. That's a legitimate trade, but it means **everything below is publicly visible to anyone who finds the repo**, including via GitHub search:

- Your **full 50-ticker watchlist**
- Your **cost basis and position sizes**, if the uploaded file contains them
- Your **`expectations.yaml`** — fair values, implied-growth views, and your written thesis notes
- Your **alert thresholds** (i.e. the prices at which you intend to act)
- The **full git history**, forever — a private-then-public flip does not erase it, and deleted files remain in history

**Mandatory mitigations in v1:**
1. **Never commit cost basis or share counts.** The ingest step strips them; the dashboard shows % from 52-wk high/low, not P&L. If you want P&L, it stays in a local-only gitignored file.
2. `DISCORD_WEBHOOK_URL` and `FINNHUB_API_KEY` live in **GitHub Actions Secrets**, never in the repo. A public repo makes leaked secrets exploitable within minutes.
3. Push protection + secret scanning enabled (free on public repos).
4. `.gitignore` covers `*.local.yaml`, `notes/`, `positions*`.
5. Thesis notes in `expectations.yaml` should be terse and non-sensitive. Write them as if they'll be read — because they can be.

**If any of that is uncomfortable, the better configuration is:** private repo + Cloudflare Pages + Cloudflare Access (still $0, still phone-accessible, gated behind your login). The only thing you'd lose is unlimited Actions minutes, and at ~1,000 min/month estimated usage you'd fit inside the free 2,000 anyway. **Say the word and I'll switch it — otherwise I proceed public with the mitigations above.**

---

## 9. Decisions log

| # | Question | Decision | Date |
|---|---|---|---|
| 1 | Quote latency | **Delayed data accepted.** Use keyless/uncapped sources; freshness must be displayed prominently in the UI | 2026-07-30 |
| 2 | Repo visibility | **Private** | 2026-07-30 |
| 3 | Dataroma cadence | **Every 72h** (configurable down to 24h) | 2026-07-30 |
| 4 | Site host & visibility | **Public repo + GitHub Pages.** Reverses decision #2 — unlimited Actions minutes, free Pages. Privacy mitigations mandatory, see §8.1 | 2026-07-30 |
| 5 | Expectations engine | **Simplified in v1** (you enter the numbers); automated reverse-DCF solver in v1.1 | 2026-07-30 |
| 6 | Watchlist | **CSV/spreadsheet upload** from you | 2026-07-30 |
| 7 | Discord | **One channel / one webhook**, differentiated embed styling | 2026-07-30 |
| 8 | GitHub | `github.com/mikefromcornell/expectations-dashboard` | 2026-07-30 |
| 9 | economind reuse | **Amendments A–F adopted; zero code copied.** Repo is unlicensed & marked confidential — patterns/methodology only. See §11 | 2026-07-30 |
| 10 | Ticker management | **`config/watchlist.yaml` is the single source of truth**, git-persisted. Three front doors: YAML edit, `+ Add Ticker` modal via prefilled GitHub URL, bulk CSV import. No browser-local state | 2026-07-30 |
| 11 | Watchlist loaded | **74 tickers ingested & validated** (1 dupe removed, 5 normalised, 0 invalid). ETFs get a separate section — no earnings/P/E/ROIC/score applies to them | 2026-07-30 |
| 12 | Push method | **Build-in-workspace, then hand over a push command.** Scoped GitHub PATs are free, but a token can't be delivered securely through this chat — see §10 | 2026-07-30 |

> Note: #2 (private) is superseded by #4 (public). §8.1 documents what that exposes and how to reverse it if you change your mind.

---

## 10. Blockers before I can execute

I have everything I need on design. Two things are outstanding, both on your side:

1. ✅ **Ticker list — RECEIVED AND LOADED.** 74 unique tickers validated and written to `config/watchlist.yaml`. Full report: `watchlist-validation.md`.
2. ⚠️ **GitHub push method — resolved as "build then hand over".**

   You said *"go with scoped token if it is free, otherwise the free option."* To answer directly: **fine-grained PATs are completely free** — cost isn't the issue. The problem is delivery. Pasting a token into this chat puts a live write-credential into conversation history, and **this repo is public**, so a leaked token is exploitable within minutes by bots that scan for exactly this. There's no secure channel here to hand it over, so cost isn't the deciding factor — security is.

   **Therefore: I build the complete, working project in this workspace. You review it. Then you run one copy-paste block to create the repo and push.** Same end state, ~60 seconds of your time, and no credential ever leaves your machine.

   If you'd still rather I push directly, you can create a fine-grained PAT (Contents / Actions / Workflows / Pages: read-write, scoped to this one repo, 7-day expiry) — but **revoke it immediately after**, and know that it will persist in this conversation's history.

**Secrets you'll add in GitHub → Settings → Secrets → Actions (never paste them to me):**
- `DISCORD_WEBHOOK_URL`
- `FINNHUB_API_KEY` (free signup at finnhub.io)

---

## 11. Provenance & IP hygiene *(Amendment F)*

`mikefromcornell/economindTEST` was reviewed on 2026-07-30 for reusable components (full analysis: `economind-review.md`).

**Finding:** that repo is a fork of `huhlig/economind`, authored by Hans W. Uhlig, with **no LICENSE file** (default = all rights reserved) and an explicit confidentiality header on 134 of 166 source files.

**Decision: no code, text, configuration, or data files are copied from it into this project.** Amendments A–E are re-implementations of *design patterns and valuation methodology* — ideas, which are not subject to copyright — written from scratch for this codebase. Specifically:

- **A/B (composite scoring, signal model):** common software patterns, independently implemented with our own signals, weights and thresholds.
- **C (earnings bucketing):** a UI convention, re-derived with our own windows.
- **D (self-contained HTML):** a standard static-report technique; our own markup.
- **E (four-model valuation):** standard finance methodology — DCF/WACC, Buffett owner earnings, EV/EBITDA comps, residual income (Edwards-Bell-Ohlson) — all published, textbook methods predating that repo.

This note will be reproduced in the public `README.md`. Because this repo is public (§8.1), the provenance trail matters and is documented deliberately.

**If you later want genuine code reuse from economind, the clean route is to ask Hans Uhlig to add MIT or Apache-2.0 to the upstream repo.** Until then: patterns only.

---

*PRD approved on all design points. Execution begins once the CSV lands and you pick a push method.*
