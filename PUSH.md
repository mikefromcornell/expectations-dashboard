# Push to GitHub — copy-paste

Nothing has been pushed. Everything below runs on **your** machine, so no token ever leaves it.

---

## 1. Create the repo and push

Download/copy the `expectations-dashboard` folder from this workspace, then:

```bash
cd expectations-dashboard

git init -b main
git add -A
git commit -m "Expectations Dashboard v1"

# Option A — GitHub CLI (creates the repo for you)
gh repo create mikefromcornell/expectations-dashboard --public --source=. --remote=origin --push

# Option B — no CLI: create an empty PUBLIC repo named
#   expectations-dashboard
# at https://github.com/new (no README, no .gitignore, no licence), then:
git remote add origin https://github.com/mikefromcornell/expectations-dashboard.git
git push -u origin main
```

> A `.git` folder already exists in the workspace copy with one commit. If you'd rather start clean:
> `rm -rf .git` before the `git init` above.

---

## 2. Turn on Pages

**Settings → Pages → Source: `GitHub Actions`**

Site lands at `https://mikefromcornell.github.io/expectations-dashboard/`

---

## 3. Add secrets

**Settings → Secrets and variables → Actions → New repository secret**

| Secret | Required? | Value |
|---|---|---|
| `EDGAR_USER_AGENT` | recommended | `MikeCornell your@realemail.com` — see warning below |
| `DISCORD_WEBHOOK_URL` | for alerts | Discord → Server Settings → Integrations → Webhooks → New → Copy URL |
| `FINNHUB_API_KEY` | optional | free key at finnhub.io |
| `REDDIT_CLIENT_ID` | optional | reddit.com/prefs/apps → create a **script** app |
| `REDDIT_CLIENT_SECRET` | optional | same page |

> ⚠️ **The SEC User-Agent format is strict.** Tested against the live API:
> - `MikeCornell you@example.com` → **200 OK**
> - `expectations-dashboard/1.0 (research; github.com/...)` → **403** (parentheses/slashes)
> - anything `@users.noreply.github.com` → **403** (subdomain rejected)
>
> Use a plain `Name realemail@domain.com`. Without it, insider data silently stops working.

**Never paste any of these into a chat, including to me.**

---

## 4. First run

**Actions → Refresh data → Run workflow → stage: `all`**

Takes ~13 minutes for 74 tickers (deliberately throttled to stay polite to free providers).
It commits `data/*.json` back to the repo, which triggers the Pages deploy.

Then open the site. It ships with a working dataset already committed, so it renders immediately
even before the first Actions run finishes.

---

## 5. Verify

- [ ] Dashboard lists 63 equities, Funds tab lists 11
- [ ] Header shows "Quotes delayed ~15 min" plus a timestamp
- [ ] Clicking a row opens the drawer with the score breakdown
- [ ] Portfolio tab: type a weight on the Dashboard, pies and Sharpe/Sortino populate
- [ ] Discovery tab shows 18 Dataroma conviction clusters
- [ ] Discord receives a message after the first run *(alerts fire on the schedule)*

---

## Local development

```bash
pip install -r requirements.txt

python -m src.build --stage all          # full rebuild (~13 min)
python -m src.build --stage quotes       # prices only (~2 min)
python -m src.alerts.engine alerts --dry # preview alerts, no Discord post
python -m src.alerts.engine daily --dry  # preview the 10am summary
python -m pytest tests/ -q               # 7 smoke tests, no network

python -m http.server 8000 --directory docs   # then open localhost:8000
```

Ticker management:

```bash
python -m src.watchlist add NVDA
python -m src.watchlist import myfile.csv
python -m src.watchlist remove SOFI
python -m src.watchlist validate
python -m src.watchlist weights
```

---

## First things worth doing

1. **Set fair values** in `config/expectations.yaml`. Right now 0 of 63 equities have one, so the
   35%-weighted gap component is inactive and every score shows `*` (partial). This is the single
   highest-impact thing you can do — it switches on the core of the framework.
2. **Set position weights** — either in the Weight column or `config/watchlist.yaml`. Until then the
   Portfolio tab has nothing to compute.
3. **Add your Gemini key** in the Mauboussin tab (free, aistudio.google.com/apikey).
