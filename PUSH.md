# Deploy — copy-paste, ~4 minutes

Everything is built, tested and committed locally. I could not create the repo for you: this sandbox
has **no GitHub credentials** (`gh` CLI absent, `api.github.com/user` → 401), and a write token can't
be delivered here safely. The commands below run on **your** machine, so no credential leaves it.

---

## 1. Create the repo and push

```bash
cd expectations-dashboard        # the folder from this workspace

# Option A — GitHub CLI (creates the repo and pushes in one step)
gh repo create mikefromcornell/expectations-dashboard --public --source=. --remote=origin --push

# Option B — no CLI: create an empty PUBLIC repo named `expectations-dashboard`
# at https://github.com/new  (no README, no .gitignore, no licence), then:
git remote add origin https://github.com/mikefromcornell/expectations-dashboard.git
git branch -M main
git push -u origin main
```

Git history is already initialised with 4 clean commits. Nothing else to prepare.

---

## 2. Enable Pages

**Settings → Pages → Source: `GitHub Actions`**

Site: `https://mikefromcornell.github.io/expectations-dashboard/`

It ships with a full dataset already committed, so it renders the moment Pages finishes — no waiting
for a build.

---

## 3. Add secrets

**Settings → Secrets and variables → Actions → New repository secret**

| Secret | Required? | Value |
|---|---|---|
| `EDGAR_USER_AGENT` | recommended | `MikeCornell your@realemail.com` — see warning |
| `DISCORD_WEBHOOK_URL` | for alerts | Discord → Server Settings → Integrations → Webhooks → New → Copy URL |
| `FINNHUB_API_KEY` | optional | free at finnhub.io — extra quote/earnings fallback |
| `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` | optional | reddit.com/prefs/apps → create a **script** app |

> ⚠️ **The SEC User-Agent format is strict.** Verified against the live API:
> `MikeCornell you@example.com` → **200**; anything with parentheses or slashes → **403**;
> any `@users.noreply.github.com` address → **403**. Without a valid one, insider data silently stops.

**Do not add your Gemini key here** — see §5.

---

## 4. First run

**Actions → Refresh data → Run workflow → stage `all`**

~13 minutes for 74 tickers (deliberately throttled to stay polite to free providers). It commits
`data/*.json` back to the repo, which triggers the Pages deploy.

---

## 5. Your Gemini key — paste it into the app, not the repo

**The key you sent works.** I tested it live: `gemini-flash-latest` returned a valid completion.
Two things you should know:

- `gemini-2.5-flash` returns **404 – no longer available to new users**, and `gemini-2.0-flash` is
  **quota-exhausted** on your account. I changed the app to try `gemini-flash-latest` first and fall
  back through the other Flash models, so it works today and survives Google renaming things.
- **I did not put the key in the repo, and you shouldn't either.** The repo is public — a committed
  key is scraped within minutes. The Mauboussin tab is designed for exactly this: open it, paste the
  key once, and it lives in your browser's `localStorage` on that device only.

> Since the key was shared in this chat, **rotate it** at
> [aistudio.google.com/apikey](https://aistudio.google.com/apikey) once you've pasted the new one in.
> Deleting the old key takes one click.

---

## 6. Verify

- [ ] Dashboard: 63 equities; Funds tab: 11
- [ ] Header shows "Quotes delayed ~15 min" plus a timestamp
- [ ] Clicking a row opens the drawer with the full score breakdown
- [ ] Portfolio tab: **Total 100.00%**, 74 positions, beta 1.13, Sharpe 0.18, Sortino 0.27
- [ ] Discovery: 18 Dataroma conviction clusters
- [ ] Mauboussin: paste key → pick a ticker → Analyse returns text

---

## Current configuration

**Equal weight** — all 74 tickers at 1.3514% (last one 1.3478% to make it sum to exactly 100.00%).

**Fair values: empty**, as you asked. This means the Expectations Gap column is blank and the
35%-weighted gap component of the Expectations Score is inactive, so every score shows `*` (scored on
5 of 6 inputs). The scores are still valid — weights re-normalise across available inputs rather than
defaulting to a neutral value.

A `20 × LTM EPS` rule is scaffolded and ready in `config/expectations.yaml` behind
`auto_fair_value.enabled: false`. Flip it to `true` and rebuild to switch it on for all 55 tickers
with a positive P/E. Worth knowing before you do: a flat 20× applies the same multiple to a 90%-ROIC
compounder and a cyclical, so it's a screen that says "look here", not a target price.

---

## Local development

```bash
pip install -r requirements.txt

python -m src.build --stage all           # full rebuild (~13 min)
python -m src.build --stage quotes        # prices only (~2 min)
python -m src.alerts.engine alerts --dry  # preview alerts, no Discord post
python -m src.alerts.engine daily --dry   # preview the 10am summary
python -m pytest tests/ -q                # 7 smoke tests, no network

python -m http.server 8000 --directory docs   # open localhost:8000
```

```bash
python -m src.watchlist add NVDA          # validates before committing
python -m src.watchlist import file.csv   # bulk; strips cost basis
python -m src.watchlist remove SOFI       # archives, never deletes
python -m src.watchlist weights           # show current sizing
```
