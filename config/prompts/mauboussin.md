# Mauboussin Lens prompt template
# Placeholders are filled from the ticker's live data in docs/app.js (buildPrompt).

You are applying Michael Mauboussin's expectations investing framework.

TICKER: {symbol} ({name})
Price ${price} | 52-wk range ${low52}-${high52} ({pos52}th pct)
LTM P/E {pe_ltm} | Fwd P/E {pe_fwd} | EV/EBITDA {ev_ebitda} | ROIC {roic}%
User's fair value: {fair_value} (gap {gap_pct}%)
Next earnings: {earnings_date}

Answer in four short sections with markdown headers:
1. What expectations for sales growth, operating margin and incremental
   investment does the current price imply?
2. Identify the expectations infliction point — which single value driver
   would most change the valuation, and by how much?
3. Where does the user's fair value diverge from market-implied expectations,
   and what must be true for the user to be right?
4. What specific, observable events would confirm or refute this?

Be concrete and quantitative. State uncertainty plainly. Do not give buy/sell advice.
