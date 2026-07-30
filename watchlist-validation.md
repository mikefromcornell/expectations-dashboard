# Watchlist ingest & validation report
**Source:** `uploads/tickers.csv` · **Validated:** 2026-07-30 · **Result: 74 tickers, all resolve**

## Summary

| | Count |
|---|---|
| Lines in file | 75 |
| Duplicate removed | 1 (`AMZN`) |
| **Unique tickers** | **74** |
| Verified against SEC EDGAR company registry | 64 |
| Verified as ETF / ADR (not EDGAR-listed by design) | 10 |
| **Unresolvable / invalid** | **0** ✅ |

Composition: **55 operating companies · 11 ETFs · 8 ADRs**

Written to `config/watchlist.yaml`.

> Note: this is 74 names, not the ~50 in the PRD. Still comfortably inside free-tier limits (soft cap 100), no design change needed.

---

## Normalisations applied

| Input | Stored as | Why |
|---|---|---|
| `avgo` | `AVGO` | Lowercase → uppercased |
| `BRK.B` | `BRK-B` | Yahoo uses `-` for share classes; `.` breaks the endpoint |
| `NYSE:AVEX` | `AVEX` | Exchange prefix stripped (Google-Finance style, not used by our providers) |
| `NYSE:TSM` | `TSM` | Same |
| `AMZN` ×2 | `AMZN` ×1 | De-duplicated (appeared at lines 1 and 69) |

The importer applies these rules automatically, so future CSVs in any of these formats will just work.

---

## Names worth a second look

Not errors — all four resolve — but each has a wrinkle worth knowing before it shows up as a strange dashboard row:

**`FISV` — correct, but recently changed.** Fiserv moved NYSE→Nasdaq on 11 Nov 2025 and reverted its ticker from `FI` back to `FISV`. Your file has the current symbol. Flagging it because historical data before Nov 2025 sits under `FI`, so the 52-week high/low may be truncated depending on provider. I'll add a `historical_alias: FI` field so the range is computed over the full 52 weeks.

**`SMEGF` — thin OTC ADR.** Siemens Energy's unsponsored OTC line. Prices are sparse and the bid/ask is wide, so the 52-week range and any valuation multiple will be noisy. The primary listing (`ENR.DE`, Xetra) is far more liquid. Worth switching if you actually track this one.

**`AVEX` (AEVEX Corp), `GEMI` (Gemini Space Station), `BLSH` (Bullish), `FIGR` (Figure Technology)** — all recent listings. Any ticker with under 12 months of trading has **no true 52-week range**, and P/E may be absent or meaningless. The dashboard will show these with an explicit `< 52wk history` badge rather than a misleading range computed from a short window.

**`FNMA` / `FMCC`** — OTC, in conservatorship. Standard valuation multiples (P/E, EV/EBITDA, ROIC) are not meaningful for these. They'll render with metrics suppressed and a note, rather than printing nonsense numbers.

---

## ETFs and the expectations framework — a design question

11 of your 74 are ETFs (`XBI`, `AVDV`, `AVUV`, `VXUS`, `BCI`, `JETS`, `VUG`, `VTI`, `QQQ`, `SLV`, `FBTC`).

These have **no earnings date, no insider activity, no P/E in any meaningful sense, no ROIC, and no reverse-DCF**. Roughly half the dashboard's columns are structurally empty for them, and the Expectations Score can't be computed at all.

Rather than show a table full of dashes, the plan is:

- Tag them `type: etf` in config (**already done**).
- Give them their own **"Funds & ETFs" section** below the equities table, with only the columns that apply: price, day %, **% from 52-wk high / low** (your core metric — fully valid here), and 52-week position bar.
- Exclude them from Expectations Score ranking so they don't distort the sort.
- Keep them in price/range alerting, since that works fine.

Same treatment for `SLV` (commodity trust) and `FBTC` (spot Bitcoin ETF) — neither has earnings or fundamentals.

**Tell me if you'd rather see them inline in one combined table instead.**

---

## The 74

**Equities (55):** AMZN · CPRI · GEMI · SRRK · ADBE · AVGO · GOOGL · VIRT · CPRT · GPC · STNG · BRK-B · FICO · LHX · CROX · EFX · ODFL · BRO · ZETA · CRM · FISV · CLH · UBER · ALLE · PFE · COST · AAPL · LAMR · HEI · COP · XOM · MIR · DASH · ZM · CVX · CARR · ELV · TECH · FNMA · FMCC · UNH · MA · PGY · AVEX · INTC · AMD · MSFT · ETN · BLSH · IDYA · FIGR · MELI · IBM · V · SPGI

**ADRs (8):** NVO (Novo Nordisk) · ASML · BABA · JD · TSM (Taiwan Semi) · SMEGF (Siemens Energy) · MRAAY (Murata) · EVVTY (Evolution AB)

**ETFs / funds (11):** QQQ · VTI · VUG · VXUS · AVUV · AVDV · XBI · JETS · BCI · SLV · FBTC

---

## Note on live validation

I verified every symbol against the **SEC EDGAR company registry** (authoritative, keyless) plus manual classification of the 10 ETF/ADR entries EDGAR doesn't cover.

I could not price-check them live: **Yahoo Finance returned HTTP 429 to this sandbox's IP** on every request. That's not a problem with your tickers — and it's a useful real-world confirmation of two PRD decisions: the mandatory **multi-provider fallback chain** (§4) and **per-ticker error isolation** (§5.7). GitHub Actions runners use different IPs and won't hit this, but the retry/backoff logic is clearly not optional. First thing the build does is a live price check across all 74 and report any that don't return a quote.
