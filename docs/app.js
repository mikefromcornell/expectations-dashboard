/* Expectations Dashboard — reads /data/*.json produced by GitHub Actions. */
const $ = (id) => document.getElementById(id);
const PAL = ['#60a5fa','#a78bfa','#f472b6','#fb923c','#facc15','#4ade80','#2dd4bf','#38bdf8',
             '#818cf8','#c084fc','#f87171','#a3e635','#fbbf24','#34d399','#22d3ee','#94a3b8'];

let D = [], META = {}, PORT = {}, BUFF = {}, DISC = {};
let S = { key: 'score', dir: -1 };
const F = { near: 0, earn: 0, sig: 0, gap: 0 };

const f = (v, d = 2) => (v === null || v === undefined) ? '<span class="dash">—</span>' : (+v).toFixed(d);
const pc = (v) => v === null || v === undefined ? '<span class="dash">—</span>'
  : `<span class="${v >= 0 ? 'up' : 'dn'}">${v >= 0 ? '+' : ''}${(+v).toFixed(2)}%</span>`;
const scol = (s) => s === null || s === undefined ? '#3a4763' : s >= .62 ? '#22c55e' : s >= .42 ? '#f59e0b' : '#ef4444';
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

/* On GitHub Pages `docs/` is the site root and data is copied to docs/data.
   Opening the file locally from the repo, data lives at ../data. Try both. */
async function grab(name, fallback) {
  const bust = '?v=' + Date.now();
  for (const base of ['data/', '../data/']) {
    try {
      const r = await fetch(base + name + bust);
      if (r.ok) return await r.json();
    } catch (e) { /* try next */ }
  }
  return fallback;
}

async function boot() {
  const [t, m, p, b, dc, hs] = await Promise.all([
    grab('tickers.json', []),
    grab('meta.json', {}),
    grab('portfolio.json', {}),
    grab('buffett.json', {}),
    grab('discovery.json', {}),
    grab('history_index.json', {}),
  ]);
  D = t; META = m; PORT = p; BUFF = b; DISC = dc;
  HIDX = new Set((hs && hs.tickers) || []);
  HQ = (hs && hs.quarters) || {};
  if (!D.length) {
    $('freshness').innerHTML = '<span class="badge warn">No data yet — run the Refresh workflow</span>';
  }
  renderFreshness();
  const secs = [...new Set(D.filter(r => r.type !== 'etf').map(r => r.sector).filter(Boolean))].sort();
  $('sector').innerHTML = '<option value="">All sectors</option>' + secs.map(s => `<option>${esc(s)}</option>`).join('');
  render(); renderETF(); renderBuff(); renderPort(); renderDisc();
}

function renderFreshness() {
  const gen = META.generated ? new Date(META.generated) : null;
  const ageH = gen ? (Date.now() - gen.getTime()) / 3.6e6 : null;
  const stale = ageH !== null && ageH > 6;
  $('freshness').innerHTML = `
    <span class="badge ${stale ? 'warn' : 'live'}">Quotes <b>delayed ~15 min</b>${gen ? ' · ' + gen.toLocaleString() : ''}</span>
    <span class="badge">${META.tickers ?? 0} tickers</span>
    ${META.errors ? `<span class="badge warn">${META.errors} fetch warnings</span>` : ''}
    ${stale ? '<span class="badge warn">⚠ DATA STALE — last build over 6h ago</span>' : ''}`;
}

/* ---------------- main table ---------------- */
function earnCell(r) {
  // Funds genuinely have no earnings — leave them as n/a.
  if (r.type === 'etf') return '<span class="p-na">n/a</span>';
  // For companies where no free source published a date, offer a way out
  // instead of a dead "n/a": link straight to Yahoo's earnings calendar.
  // stopPropagation so clicking the link doesn't also open the row drawer.
  if (r.earnings_days === null || r.earnings_days === undefined) {
    return `<a class="earnlink" target="_blank" rel="noopener"
      onclick="event.stopPropagation()"
      title="No date published by our free sources — check Yahoo Finance"
      href="https://finance.yahoo.com/calendar/earnings?symbol=${encodeURIComponent(r.symbol)}">check ↗</a>`;
  }
  const d = r.earnings_days, e = r.earnings_confirmed ? '' : ' <span class="est">est.</span>';
  if (d >= 0 && d <= 3) return `<span class="pill p-imm">in ${d}d</span>${e}`;
  if (d >= 4 && d <= 10) return `<span class="pill p-app">in ${d}d</span>${e}`;
  if (d < 0 && d >= -3) return `<span class="pill p-drift">reported ${Math.abs(d)}d ago</span>`;
  return `<span class="pill p-far">${d > 0 ? 'in ' + d + 'd' : Math.abs(d) + 'd ago'}</span>${e}`;
}
function rangeCell(r) {
  if (r.new_listing || r.pos52 === null || r.pos52 === undefined)
    return `<div class="rng"><div style="font-size:10px;color:#8fa0bf">&lt; 52wk history</div></div>`;
  return `<div class="rng"><div class="rngbar"><div class="rngdot" style="left:calc(${Math.max(0, Math.min(100, r.pos52))}% - 1.5px)"></div></div>
    <div class="rnglbl"><span>${(r.low52 ?? 0).toFixed(0)}</span><span>${r.pos52.toFixed(0)}%</span><span>${(r.high52 ?? 0).toFixed(0)}</span></div></div>`;
}
function sigCell(r) {
  let o = '';
  if (r.insider === 'buy') o += '🟢'; if (r.insider === 'sell') o += '🔻';
  if (r.politician === 'buy') o += '🏛';
  if (r.superinv === 'add' || r.superinv === 'new') o += '💼';
  if (r.superinv === 'trim') o += '📉';
  return o ? `<span class="sig">${o}</span>` : '<span class="dash">—</span>';
}
function flags(r) {
  let o = '';
  if (r.suppressed) o += '<span class="flag gray">metrics n/a</span>';
  if (r.thin) o += '<span class="flag gray">thin OTC</span>';
  if (r.alias) o += `<span class="flag gray">was ${esc(r.alias)}</span>`;
  if (r.new_listing) o += '<span class="flag gray">new listing</span>';
  if (!r.price) o += '<span class="flag" style="background:#450a0a;color:#fca5a5">no price</span>';
  else if (r.errors && r.errors.length) o += '<span class="flag" style="background:#2a1508;color:#fdba74">partial</span>';
  return o;
}


/* current multiple vs its own 2-year mean — the "is this rich or cheap
   versus its own history" read, shown inline rather than as extra columns */
function mean2y(cur, mean) {
  if (mean === null || mean === undefined) return '';
  if (cur === null || cur === undefined) return `<span class="m2y">${mean.toFixed(1)} avg</span>`;
  const d = (cur / mean - 1) * 100;
  const cls = d > 10 ? 'rich' : d < -10 ? 'cheap' : '';
  return `<span class="m2y ${cls}" title="2-year mean ${mean.toFixed(2)} · current is ${d >= 0 ? '+' : ''}${d.toFixed(0)}% vs it">${mean.toFixed(1)} avg</span>`;
}
function targetCell(r) {
  if (!r.analyst_target) return '<span class="dash">—</span>';
  const up = r.analyst_upside;
  const c = up === null || up === undefined ? '' : up >= 0 ? 'up' : 'dn';
  return `<span title="${esc(r.analyst_detail || '')}">$${r.analyst_target.toFixed(2)}` +
    (up === null || up === undefined ? '' : `<span class="m2y ${c}" style="color:${up >= 0 ? '#4ade80' : '#f87171'}">${up >= 0 ? '+' : ''}${up.toFixed(0)}%</span>`) + `</span>`;
}

function render() {
  const q = $('q').value.toLowerCase(), sec = $('sector').value;
  let rows = D.filter(r => r.type !== 'etf').filter(r => {
    if (q && !(r.symbol.toLowerCase().includes(q) || (r.name || '').toLowerCase().includes(q))) return 0;
    if (sec && r.sector !== sec) return 0;
    if (F.near && !(r.pct_from_low !== null && r.pct_from_low < 12)) return 0;
    if (F.earn && !(r.earnings_days !== null && r.earnings_days >= 0 && r.earnings_days <= 7)) return 0;
    if (F.sig && !(r.insider || r.politician || r.superinv)) return 0;
    if (F.gap && r.gap_pct === null) return 0;
    return 1;
  });
  rows.sort((a, b) => {
    let x = a[S.key], y = b[S.key];
    if (x === null || x === undefined) return 1;
    if (y === null || y === undefined) return -1;
    return typeof x === 'string' ? S.dir * x.localeCompare(y) : S.dir * (x - y);
  });
  $('tb').innerHTML = rows.map(r => `<tr onclick="openD('${r.symbol}')">
    <td><div class="sym">${r.symbol}${flags(r)}</div><div class="nm">${esc(r.name)}</div></td>
    <td class="num mono">${f(r.price)}</td>
    <td>${earnCell(r)}</td>
    <td class="num mono dn">${r.pct_from_high === null || r.pct_from_high === undefined ? '<span class="dash">—</span>' : f(r.pct_from_high, 1) + '%'}</td>
    <td class="num mono up">${r.pct_from_low === null || r.pct_from_low === undefined ? '<span class="dash">—</span>' : '+' + f(r.pct_from_low, 1) + '%'}</td>
    <td>${rangeCell(r)}</td>
    <td class="num mono">${f(r.pe_ltm, 1)}${mean2y(r.pe_ltm, r.pe_mean_2y)}</td>
    <td class="num mono">${f(r.ps_ratio, 1)}${mean2y(r.ps_ratio, r.ps_mean_2y)}</td>
    <td class="num mono">${r.roic === null || r.roic === undefined ? '<span class="dash">—</span>' : f(r.roic, 1) + '%'}</td>
    <td class="num mono">${targetCell(r)}</td>
    <td>${sigCell(r)}</td>
    <td class="num mono"><b style="color:${scol(r.score)};font-size:13.5px">${r.score === null || r.score === undefined ? '<span class="dash">—</span>' : (r.score * 100).toFixed(0) + '%'}</b>${r.score_partial ? '<span class="star" title="scored on partial inputs">*</span>' : ''}</td></tr>`).join('');
  $('count').textContent = `${rows.length} of ${D.filter(r => r.type !== 'etf').length} equities · ${D.filter(r => r.type === 'etf').length} funds in separate tab`;
}
function renderETF() {
  $('tbe').innerHTML = D.filter(r => r.type === 'etf').map(r => `<tr>
    <td><div class="sym">${r.symbol}${flags(r)}</div><div class="nm">${esc(r.name)}</div></td>
    <td class="num mono">${f(r.price)}</td><td class="num mono">${pc(r.change_pct)}</td>
    <td class="num mono dn">${r.pct_from_high === null ? '<span class="dash">—</span>' : f(r.pct_from_high, 1) + '%'}</td>
    <td class="num mono up">${r.pct_from_low === null ? '<span class="dash">—</span>' : '+' + f(r.pct_from_low, 1) + '%'}</td>
    <td>${rangeCell(r)}</td></tr>`).join('');
}
function sort(k, el) {
  S.dir = S.key === k ? -S.dir : (k === 'symbol' ? 1 : -1); S.key = k;
  document.querySelectorAll('#dash thead th').forEach(t => t.classList.remove('sorted'));
  if (el) el.classList.add('sorted');
  render();
}
function tgl(k) { F[k] = !F[k]; $('c-' + k).classList.toggle('on'); render(); }
function tab(id, el) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('on'));
  $(id).classList.add('on');
  document.querySelectorAll('nav a').forEach(a => a.classList.remove('on'));
  el.classList.add('on');
  if (id === 'maub') maubInit();
}


/* ─────────────────────────────────────────────────────────────────────
   Charts: is the price being driven by the multiple, or by the business?
   Hand-written SVG — no chart library, keeps the page self-contained.
   ───────────────────────────────────────────────────────────────────── */
let HIST = {};      // per-ticker chart data, fetched on demand
let HIDX = new Set(); // which tickers have history
let HQ = {};        // quarters available per ticker

function niceTicks(lo, hi, n) {
  if (!(hi > lo)) return [lo];
  const raw = (hi - lo) / n, mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(v => v >= raw) || mag * 10;
  const out = []; for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(v);
  return out;
}

/* Dual-axis: fundamental (area, left) vs multiple (line, right).
   The whole point is the divergence — business up while multiple down = de-rating. */
function dualChart(series, multKey, fundKey, opts) {
  const W = 520, H = 210, L = 44, R = 46, T = 12, B = 26;
  const pts = series.filter(p => p[multKey] != null && p[fundKey] != null && p[multKey] > 0);
  if (pts.length < 8) return '<div class="hint">Not enough history for this chart.</div>';
  const iw = W - L - R, ih = H - T - B;
  const mv = pts.map(p => p[multKey]), fv = pts.map(p => p[fundKey]);
  const mlo = Math.min(...mv), mhi = Math.max(...mv);
  const flo = Math.min(...fv), fhi = Math.max(...fv);
  const mPad = (mhi - mlo) * 0.12 || 1, fPad = (fhi - flo) * 0.12 || 1;
  const m0 = Math.max(0, mlo - mPad), m1 = mhi + mPad;
  const f0 = Math.max(0, flo - fPad), f1 = fhi + fPad;
  const x = i => L + (i / (pts.length - 1)) * iw;
  const ym = v => T + ih - ((v - m0) / (m1 - m0)) * ih;
  const yf = v => T + ih - ((v - f0) / (f1 - f0)) * ih;

  const fundPath = pts.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${yf(p[fundKey]).toFixed(1)}`).join('');
  const area = `${fundPath}L${x(pts.length - 1).toFixed(1)},${(T + ih)}L${L},${(T + ih)}Z`;
  const multPath = pts.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${ym(p[multKey]).toFixed(1)}`).join('');
  const mean = mv.reduce((a, b) => a + b, 0) / mv.length;

  let g = '';
  niceTicks(m0, m1, 4).forEach(v => {
    g += `<line x1="${L}" y1="${ym(v).toFixed(1)}" x2="${W - R}" y2="${ym(v).toFixed(1)}" stroke="#1a2440" stroke-width="1"/>`;
    g += `<text x="${W - R + 5}" y="${(ym(v) + 3).toFixed(1)}" fill="#5f708f" font-size="9">${v.toFixed(1)}x</text>`;
  });
  niceTicks(f0, f1, 4).forEach(v => {
    g += `<text x="${L - 5}" y="${(yf(v) + 3).toFixed(1)}" fill="#5f708f" font-size="9" text-anchor="end">${opts.fmtFund(v)}</text>`;
  });
  const step = Math.max(1, Math.floor(pts.length / 5));
  for (let i = 0; i < pts.length; i += step) {
    g += `<text x="${x(i).toFixed(1)}" y="${H - 8}" fill="#5f708f" font-size="9" text-anchor="middle">${pts[i].t.slice(0, 7)}</text>`;
  }
  const last = pts[pts.length - 1];
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" preserveAspectRatio="xMidYMid meet">
    ${g}
    <path d="${area}" fill="${opts.fundColor}" opacity=".16"/>
    <path d="${fundPath}" fill="none" stroke="${opts.fundColor}" stroke-width="1.8"/>
    <line x1="${L}" y1="${ym(mean).toFixed(1)}" x2="${W - R}" y2="${ym(mean).toFixed(1)}" stroke="${opts.multColor}" stroke-width="1" stroke-dasharray="4 3" opacity=".65"/>
    <text x="${W - R - 3}" y="${(ym(mean) - 4).toFixed(1)}" fill="${opts.multColor}" font-size="9" text-anchor="end" opacity=".9">mean ${mean.toFixed(1)}x</text>
    <path d="${multPath}" fill="none" stroke="${opts.multColor}" stroke-width="1.5"/>
    <circle cx="${x(pts.length - 1).toFixed(1)}" cy="${ym(last[multKey]).toFixed(1)}" r="3" fill="${opts.multColor}"/>
  </svg>
  <div class="chartlegend">
    <span><i style="background:${opts.fundColor}"></i>${opts.fundLabel} (left)</span>
    <span><i style="background:${opts.multColor}"></i>${opts.multLabel} (right) — now <b style="color:${opts.multColor}">${last[multKey].toFixed(1)}x</b></span>
  </div>`;
}

/* Price return factors exactly into multiple change x fundamental growth.
   Stacked bars make it obvious which one did the work. */
function decompChart(rows, mode) {
  if (!rows || !rows.length) return '<div class="hint">Not enough history to decompose returns.</div>';
  const mk = mode === 'pe' ? 'pe_change' : 'ps_change';
  const gk = mode === 'pe' ? 'eps_growth' : 'sales_growth';
  const gLabel = mode === 'pe' ? 'EPS growth' : 'Sales growth';
  const mLabel = mode === 'pe' ? 'P/E change' : 'P/S change';
  let out = '<div class="decomp">';
  rows.forEach(r => {
    if (r[mk] == null || r[gk] == null) return;
    const mult = r[mk], fund = r[gk];
    const am = Math.abs(mult), af = Math.abs(fund), tot = am + af || 1;
    const pm = am / tot * 100, pf = af / tot * 100;
    const cm = mult >= 0 ? '#60a5fa' : '#f87171';
    const cf = fund >= 0 ? '#4ade80' : '#fb923c';
    const driver = af > am ? gLabel.toLowerCase() : 'multiple change';
    const dcol = af > am ? '#4ade80' : '#60a5fa';
    out += `<div class="decomprow">
      <div class="decomphead">
        <b>${r.period}</b>
        <span>price <b style="color:${r.price_return >= 0 ? '#22c55e' : '#ef4444'}">${r.price_return >= 0 ? '+' : ''}${r.price_return}%</b></span>
      </div>
      <div class="decompbar">
        <i style="width:${pm.toFixed(1)}%;background:${cm}" title="${mLabel} ${mult >= 0 ? '+' : ''}${mult}%"></i>
        <i style="width:${pf.toFixed(1)}%;background:${cf}" title="${gLabel} ${fund >= 0 ? '+' : ''}${fund}%"></i>
      </div>
      <div class="decompkey">
        <span style="color:${cm}">${mLabel} ${mult >= 0 ? '+' : ''}${mult}%</span>
        <span style="color:${cf}">${gLabel} ${fund >= 0 ? '+' : ''}${fund}%</span>
        ${r.share_effect != null && Math.abs(r.share_effect) >= 1 ? `<span style="color:#a78bfa">share count ${r.share_effect >= 0 ? '+' : ''}${r.share_effect}%</span>` : ''}
      </div>
      <div class="verdict">Driven mainly by <b style="color:${dcol}">${driver}</b>.</div>
    </div>`;
  });
  return out + '</div>';
}

async function loadHistory(sym) {
  if (HIST[sym]) return HIST[sym];
  for (const base of ['data/history/', '../data/history/']) {
    try {
      const r = await fetch(base + sym + '.json');
      if (r.ok) { HIST[sym] = await r.json(); return HIST[sym]; }
    } catch (e) { /* try next */ }
  }
  return null;
}

function multipleMode(sym, mode) {
  const h = HIST[sym]; if (!h) return;
  const box = document.getElementById('mchart');
  const isPE = mode === 'pe';
  box.innerHTML = dualChart(h.series, isPE ? 'pe' : 'ps', isPE ? 'eps' : 'rev', {
    multKey: isPE ? 'pe' : 'ps',
    multLabel: isPE ? 'P/E (TTM)' : 'P/S (TTM)',
    fundLabel: isPE ? 'EPS (TTM)' : 'Revenue (TTM)',
    multColor: isPE ? '#60a5fa' : '#a78bfa',
    fundColor: isPE ? '#f59e0b' : '#fb923c',
    fmtFund: v => isPE ? '$' + v.toFixed(1) : '$' + (v / 1e9).toFixed(0) + 'B',
  });
  document.getElementById('dchart').innerHTML = decompChart(h.summary.decomposition, mode);
  ['btn-ps', 'btn-pe'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.toggle('on', id === 'btn-' + mode);
  });
}

/* ---------------- drawer ---------------- */
function tick(v) { return v ? '<span style="color:#22c55e">✓</span>' : '<span style="color:#ef4444">✗</span>'; }
function openD(sym) {
  const r = D.find(x => x.symbol === sym); if (!r) return;
  $('dsym').textContent = r.symbol;
  $('dname').textContent = (r.name || '') + (r.sector ? ' · ' + r.sector : '');
  let h = `<div class="sec"><h3>Price &amp; 52-week range</h3>
    <div class="kv"><span>Price</span><b>${r.price ? '$' + f(r.price) : 'unavailable'}</b></div>
    <div class="kv"><span>Day change</span><b>${pc(r.change_pct)}</b></div>`;
  if (r.new_listing || r.pos52 === null) {
    h += `<div class="kv"><span>52-week range</span><b style="color:#8fa0bf">not available — under 12 months of history</b></div>`;
  } else {
    h += `<div class="kv"><span>52-week high</span><b>$${f(r.high52)} <span class="dn">(${f(r.pct_from_high, 1)}%)</span></b></div>
      <div class="kv"><span>52-week low</span><b>$${f(r.low52)} <span class="up">(+${f(r.pct_from_low, 1)}%)</span></b></div>
      <div class="kv"><span>Position in range</span><b>${f(r.pos52, 0)}th percentile</b></div>`;
  }
  if (r.alias) h += `<div class="kv"><span>Historical alias</span><b>${esc(r.alias)}</b></div>`;
  h += '</div>';

  if (r.score !== null && r.score !== undefined) {
    h += `<div class="sec"><h3>Expectations Score — ${(r.score * 100).toFixed(0)}% ${r.score_partial ? `<span style="color:#f59e0b">(scored on ${r.score_n})</span>` : ''}</h3>`;
    (r.score_parts || []).forEach(p => {
      h += `<div class="comp"><div class="comptop">
        <span class="compname" style="color:${p.score === null ? '#5f708f' : '#e8edf7'}">${esc(p.label)}</span>
        <span class="compw">weight ${(p.weight * 100).toFixed(0)}%</span>
        <b style="color:${p.score === null ? '#3a4763' : scol(p.score)}">${p.score === null ? 'n/a' : p.score.toFixed(2)}</b></div>
        <div class="compdetail">${esc(p.detail)}</div></div>`;
    });
    h += `<div class="hint" style="margin-top:9px">Missing inputs are dropped and remaining weights re-normalised — never silently substituted with a neutral 0.5.</div></div>`;
  }

  if (HIDX.has(r.symbol)) {
    h += `<div class="sec"><h3>What is driving the price?</h3>
      <div style="display:flex;gap:6px;margin-bottom:10px">
        <span class="chip on" id="btn-ps" onclick="multipleMode('${r.symbol}','ps')">P/S vs Revenue</span>
        <span class="chip" id="btn-pe" onclick="multipleMode('${r.symbol}','pe')">P/E vs EPS</span>
      </div>
      <div class="chartbox">
        <div class="charttitle">Multiple vs. fundamental (TTM)</div>
        <div class="chartsub">When the business line rises while the multiple falls, the market is de-rating a growing company — and vice versa.</div>
        <div id="mchart"></div>
      </div>
      <div class="chartbox">
        <div class="charttitle">Return decomposition</div>
        <div class="chartsub">Price return = multiple change × fundamental growth. Bar width shows which contributed more.</div>
        <div id="dchart"></div>
      </div>
      <div class="hint">Built from SEC XBRL quarterly filings (${HQ[r.symbol] || '—'} quarters) joined to daily closes, point-in-time: each date only uses data filed by then, so there is no look-ahead bias.</div>
    </div>`;
  }

  h += `<div class="sec"><h3>Valuation</h3>`;
  if (r.suppressed) h += `<div class="hint">Metrics suppressed — standard multiples are not meaningful for this security.</div>`;
  else h += `<div class="kv"><span>P/E (LTM)</span><b>${f(r.pe_ltm, 1)}</b></div>
      <div class="kv"><span>P/E — 2-year mean</span><b>${f(r.pe_mean_2y, 1)}</b></div>
      <div class="kv"><span>Price / Sales</span><b>${f(r.ps_ratio, 1)}</b></div>
      <div class="kv"><span>P/S — 2-year mean</span><b>${f(r.ps_mean_2y, 1)}</b></div>
      <div class="kv"><span>EV/EBITDA</span><b>${f(r.ev_ebitda, 1)}</b></div>
      <div class="kv"><span>Revenue (LTM)</span><b>${r.revenue ? '$' + (r.revenue / 1e9).toFixed(1) + 'B' : '—'}</b></div>
      <div class="kv"><span>Debt / equity</span><b>${f(r.debt_equity, 2)}</b></div>
      <div class="kv"><span>FCF margin</span><b>${r.fcf_margin === null ? '—' : f(r.fcf_margin, 1) + '%'}</b></div>
      <div class="kv"><span>ROIC <span style="color:#5f708f;font-size:11px">(computed in-repo)</span></span><b>${r.roic === null ? '—' : f(r.roic, 1) + '%'}</b></div>`;
  if (r.roic_detail) h += `<div class="hint" style="margin-top:6px">${esc(r.roic_detail)}</div>`;
  if (r.analyst_target) h += `<div class="kv" style="margin-top:8px"><span>Analyst consensus</span><b>$${r.analyst_target.toFixed(2)}${r.analyst_upside != null ? ` <span class="${r.analyst_upside >= 0 ? 'up' : 'dn'}">(${r.analyst_upside >= 0 ? '+' : ''}${r.analyst_upside.toFixed(1)}%)</span>` : ''}</b></div>
    <div class="hint">${esc(r.analyst_detail || '')}</div>`;
  h += '</div>';

  h += `<div class="sec"><h3>Risk</h3>
    <div class="kv"><span>Beta (3y weekly vs SPY)</span><b>${f(r.beta, 2)}</b></div>
    <div class="kv"><span>30-day volatility</span><b>${r.vol30 === null ? '—' : f(r.vol30, 1) + '%'}</b></div>
    <div class="kv"><span>Downside deviation</span><b>${r.downdev === null ? '—' : f(r.downdev, 1) + '%'}</b></div>
    <div class="kv"><span>1-year return</span><b>${r.ret1y === null ? '—' : f(r.ret1y, 1) + '%'}</b></div></div>`;

  h += `<div class="sec"><h3>Expectations (your inputs)</h3>`;
  if (r.fair_value) h += `<div class="kv"><span>Your fair value</span><b>$${f(r.fair_value)}</b></div>
      <div class="kv"><span>Gap vs price</span><b class="${r.gap_pct >= 0 ? 'up' : 'dn'}">${r.gap_pct >= 0 ? '+' : ''}${f(r.gap_pct, 1)}%</b></div>`;
  else h += `<div class="hint">No fair value set. Add one in <code>config/expectations.yaml</code> to activate the gap column and score component.</div>`;
  h += `</div>`;

  h += `<div class="sec"><h3>Earnings &amp; catalysts</h3>
    <div class="kv"><span>Next earnings</span><b>${r.earnings_date
      ? `${r.earnings_date} ${r.earnings_confirmed ? '<span style="color:#22c55e;font-size:11px">confirmed</span>' : '<span style="color:#8fa0bf;font-size:11px">estimated</span>'}`
      : (r.type === 'etf' ? 'n/a'
        : `<a class="earnlink" target="_blank" rel="noopener" href="https://finance.yahoo.com/calendar/earnings?symbol=${encodeURIComponent(r.symbol)}">check on Yahoo ↗</a>`)}</b></div>
    ${r.catalyst_date ? `<div class="kv"><span>Catalyst</span><b>${esc(r.catalyst_date)} — ${esc(r.catalyst_note || '')}</b></div>` : ''}</div>`;

  h += `<div class="sec"><h3>Ownership signals</h3>
    <div class="kv"><span>🟢 Insider (Form 4)</span><b style="max-width:60%;text-align:right">${esc(r.insider_detail)}</b></div>
    <div class="kv"><span>🏛 Politician</span><b style="max-width:60%;text-align:right">${esc(r.politician_detail)}</b></div>
    <div class="kv"><span>💼 Superinvestor</span><b style="max-width:60%;text-align:right">${esc(r.superinv_detail)}</b></div></div>`;

  if (r.buffett) {
    const b = r.buffett, L = b.labels || {};
    h += `<div class="sec"><h3>Buffett checklist — ${b.passed} of ${b.total} tests passed</h3>`;
    Object.keys(L).forEach(k => {
      const t = b.tests[k]; if (!t) return;
      h += `<div class="comp"><div class="comptop"><span class="compname">${tick(t.pass)} ${esc(L[k])}</span></div>
        <div class="compdetail">${esc(t.why)}</div></div>`;
    });
    h += `<div class="hint" style="margin-top:9px">Deterministic rules from Buffett's written criteria — not a prediction of his actions, not advice. Thresholds editable in <code>config/buffett.yaml</code>.</div></div>`;
  }

  h += `<div class="sec"><h3>Data provenance</h3><div class="hint">`;
  Object.entries(r.sources || {}).forEach(([k, v]) => { h += `${esc(k)} · <b>${esc(v)}</b><br>`; });
  if (r.errors && r.errors.length) {
    h += `<div style="margin-top:8px;color:#fdba74"><b>Fetch warnings (${r.errors.length}):</b><br>`;
    r.errors.slice(0, 6).forEach(e => { h += `<span style="font-size:10.5px">• ${esc(e)}</span><br>`; });
    h += `</div>`;
  }
  h += `</div></div>`;
  $('dbody').innerHTML = h;
  if (HIDX.has(r.symbol)) {
    const mc = $('mchart');
    if (mc) mc.innerHTML = '<div class="hint">Loading history…</div>';
    loadHistory(r.symbol).then(hh => {
      if (!hh) { if ($('mchart')) $('mchart').innerHTML = '<div class="hint">History unavailable.</div>'; return; }
      if ($('dsym').textContent === r.symbol) multipleMode(r.symbol, 'ps');
    });
  }
  $('drawer').classList.add('on'); $('scrim').classList.add('on');
}
function closeD() { $('drawer').classList.remove('on'); $('scrim').classList.remove('on'); $('addm').classList.remove('on'); }

/* ---------------- add ticker ---------------- */
const REPO = 'mikefromcornell/expectations-dashboard';
function openAdd() { $('addm').classList.add('on'); $('scrim').classList.add('on'); }
function closeAdd() { $('addm').classList.remove('on'); $('scrim').classList.remove('on'); }
function lookup() {
  const v = $('asym').value.toUpperCase().trim(), e = $('alk');
  if (!v) { e.innerHTML = 'Validated against the quote provider before commit.'; return; }
  if (D.find(x => x.symbol === v)) { e.innerHTML = `<span style="color:#f59e0b">⚠ ${v} is already in your watchlist — submitting will update its fields, not duplicate it.</span>`; return; }
  e.innerHTML = `<span class="ok">✓ ${v} will be validated by the build before it is committed.</span>`;
}
function submitAdd() {
  const sym = $('asym').value.toUpperCase().trim(); if (!sym) return;
  const fv = $('afv').value.trim(), lo = $('alo').value.trim(), hi = $('ahi').value.trim();
  const tags = $('atags').value.trim(), notes = $('anotes').value.trim();
  let body = `Add \`${sym}\` to the watchlist.\n\n\`\`\`yaml\n  - symbol: ${sym}\n`;
  if (fv) body += `    fair_value: ${fv}\n`;
  if (lo) body += `    alert_low: ${lo}\n`;
  if (hi) body += `    alert_high: ${hi}\n`;
  if (tags) body += `    tags: [${tags}]\n`;
  if (notes) body += `    notes: "${notes.replace(/"/g, "'")}"\n`;
  body += '```\n\nAppend this block to `config/watchlist.yaml`, or run `python -m src.watchlist add ' + sym + '`.';
  const url = `https://github.com/${REPO}/issues/new?title=${encodeURIComponent('Add ticker: ' + sym)}&body=${encodeURIComponent(body)}`;
  window.open(url, '_blank');
}

/* ---------------- portfolio ---------------- */
function wsum() { return D.reduce((a, r) => a + (+r.weight_pct || 0), 0); }
// Position weights are set in config/watchlist.yaml, not edited in the table.
function normalize() {
  const t = wsum(); if (!t) return;
  D.forEach(r => { if (r.weight_pct) r.weight_pct = Math.round(r.weight_pct / t * 10000) / 100; });
  render(); renderETF(); renderPort();
}
function saveWeights() {
  const held = D.filter(r => r.weight_pct).sort((a, b) => b.weight_pct - a.weight_pct);
  let body = 'Update position weights in `config/watchlist.yaml`:\n\n```yaml\n';
  held.forEach(r => { body += `  - symbol: ${r.symbol}\n    weight: ${r.weight_pct}\n`; });
  body += '```\n';
  window.open(`https://github.com/${REPO}/issues/new?title=${encodeURIComponent('Update portfolio weights')}&body=${encodeURIComponent(body)}`, '_blank');
}
function arc(cx, cy, rad, a0, a1) {
  const p = a => [cx + rad * Math.cos(a), cy + rad * Math.sin(a)];
  const [x0, y0] = p(a0), [x1, y1] = p(a1);
  return `M${cx},${cy} L${x0},${y0} A${rad},${rad} 0 ${(a1 - a0) > Math.PI ? 1 : 0} 1 ${x1},${y1} Z`;
}
function drawPie(svgId, legId, items) {
  const tot = items.reduce((a, b) => a + b.v, 0) || 1;
  let a = -Math.PI / 2, s = '';
  items.forEach((it, i) => {
    const sweep = it.v / tot * Math.PI * 2;
    s += `<path d="${arc(126, 126, 118, a, a + sweep - 0.004)}" fill="${PAL[i % PAL.length]}" opacity=".92"><title>${esc(it.k)}: ${it.v.toFixed(2)}%</title></path>`;
    a += sweep;
  });
  s += `<circle cx="126" cy="126" r="62" fill="#111830"/>
    <text x="126" y="120" text-anchor="middle" fill="#e8edf7" font-size="21" font-weight="800">${tot.toFixed(0)}%</text>
    <text x="126" y="138" text-anchor="middle" fill="#5f708f" font-size="10">allocated</text>`;
  $(svgId).innerHTML = s;
  $(legId).innerHTML = items.map((it, i) =>
    `<div class="lg"><span class="sw" style="background:${PAL[i % PAL.length]}"></span><span style="flex:1">${esc(it.k)}</span><b class="mono">${it.v.toFixed(1)}%</b></div>`).join('');
}
function renderPort() {
  const held = D.filter(r => r.weight_pct > 0).sort((a, b) => b.weight_pct - a.weight_pct);
  const t = wsum(), off = Math.abs(t - 100) > 0.5;
  const el = $('wsum');
  el.textContent = `Total ${t.toFixed(2)}%`;
  el.style.background = off ? '#450a0a' : '#052e16';
  el.style.color = off ? '#fca5a5' : '#86efac';

  if (!held.length) {
    $('stats').innerHTML = `<div class="stat" style="grid-column:1/-1"><div class="s">No position weights set. Type a % into the <b>Weight</b> column on the Dashboard or Funds tab — the pie charts and risk statistics populate immediately, then click “Save to watchlist.yaml”.</div></div>`;
    ['pie', 'pie2'].forEach(i => $(i).innerHTML = '');
    ['pieleg', 'pieleg2', 'typebar', 'typeleg', 'flags'].forEach(i => $(i).innerHTML = '');
    return;
  }
  const wavg = (k) => {
    const v = held.filter(r => r[k] !== null && r[k] !== undefined);
    const w = v.reduce((a, r) => a + r.weight_pct, 0);
    return w ? v.reduce((a, r) => a + r.weight_pct * r[k], 0) / w : null;
  };
  const beta = wavg('beta'), wvol = wavg('vol30'), pret = wavg('ret1y'), pdd = wavg('downdev');
  const RF = PORT.risk_free ?? 4.3;
  const sharpe = (pret !== null && wvol) ? (pret - RF) / wvol : null;
  const sortino = (pret !== null && pdd) ? (pret - RF) / pdd : null;
  const sq = v => v === null ? '#8fa0bf' : v >= 2 ? '#22c55e' : v >= 1 ? '#4ade80' : v >= .5 ? '#f59e0b' : '#ef4444';

  const top = held.slice(0, 15).map(r => ({ k: r.symbol, v: r.weight_pct }));
  const rest = held.slice(15).reduce((a, b) => a + b.weight_pct, 0);
  if (rest > 0) top.push({ k: `Other (${held.length - 15})`, v: rest });
  drawPie('pie', 'pieleg', top);
  const bys = {};
  held.forEach(r => { const k = r.type === 'etf' ? 'Funds & ETFs' : (r.sector || 'Unknown'); bys[k] = (bys[k] || 0) + r.weight_pct; });
  drawPie('pie2', 'pieleg2', Object.entries(bys).map(([k, v]) => ({ k, v })).sort((a, b) => b.v - a.v));

  const top5 = held.slice(0, 5).reduce((a, b) => a + b.weight_pct, 0);
  const top10 = held.slice(0, 10).reduce((a, b) => a + b.weight_pct, 0);
  const hhi = held.reduce((a, r) => a + r.weight_pct ** 2, 0);
  const eff = hhi ? 10000 / hhi : 0;
  const unset = D.filter(r => !r.weight_pct).length;
  const St = [
    ['Portfolio return (1y)', pret === null ? '—' : pret.toFixed(1) + '%', 'Weighted annualised'],
    ['Sharpe ratio', sharpe === null ? '—' : `<span style="color:${sq(sharpe)}">${sharpe.toFixed(2)}</span>`, `(${pret === null ? '—' : pret.toFixed(1)}% − ${RF}% rf) ÷ ${wvol === null ? '—' : wvol.toFixed(1)}% vol<br><span style="color:#5f708f">rf: ${esc(PORT.risk_free_source || 'n/a')}</span>`],
    ['Sortino ratio', sortino === null ? '—' : `<span style="color:${sq(sortino)}">${sortino.toFixed(2)}</span>`, `Excess return ÷ ${pdd === null ? '—' : pdd.toFixed(1)}% downside dev`],
    ['Portfolio beta', beta === null ? '—' : beta.toFixed(2), beta === null ? '' : beta > 1.1 ? 'More volatile than SPY' : beta < .9 ? 'Less volatile than SPY' : 'Roughly market-like'],
    ['Weighted 30d vol', wvol === null ? '—' : wvol.toFixed(1) + '%', 'Σ(wᵢ·σᵢ) — ignores correlation'],
    ['Positions held', held.length, `${unset} watchlist names unweighted`],
    ['Top 5 weight', top5.toFixed(1) + '%', top5 > 50 ? 'Highly concentrated' : 'Moderate'],
    ['Effective positions', eff.toFixed(1), '1/HHI — true diversification'],
  ];
  $('stats').innerHTML = St.map(([l, v, s]) => `<div class="stat"><div class="v">${v}</div><div class="l">${esc(l)}</div><div class="s">${s}</div></div>`).join('');

  const byt = {}; held.forEach(r => { const k = r.type === 'etf' ? 'ETF' : r.type === 'adr' ? 'ADR' : 'Equity'; byt[k] = (byt[k] || 0) + r.weight_pct; });
  const TC = { Equity: '#60a5fa', ETF: '#a78bfa', ADR: '#4ade80' };
  $('typebar').innerHTML = Object.entries(byt).map(([k, v]) => `<i style="width:${v / t * 100}%;background:${TC[k]}" title="${k} ${v.toFixed(1)}%"></i>`).join('');
  $('typeleg').innerHTML = Object.entries(byt).map(([k, v]) => `<div class="lg"><span class="sw" style="background:${TC[k]}"></span><span style="flex:1">${k}</span><b class="mono">${v.toFixed(1)}%</b></div>`).join('');

  const FL = [];
  if (top5 > 50) FL.push(['#fca5a5', `Top 5 positions are ${top5.toFixed(1)}% of the book — concentrated.`]);
  if (eff && eff < 12) FL.push(['#fcd34d', `Effective positions ${eff.toFixed(1)} despite ${held.length} holdings — the tail is doing little.`]);
  if (beta && beta > 1.15) FL.push(['#fcd34d', `Beta ${beta.toFixed(2)} — the book amplifies market moves both ways.`]);
  const semis = held.filter(r => ['ASML', 'TSM', 'AMD', 'INTC', 'AVGO', 'SMEGF', 'MRAAY'].includes(r.symbol)).reduce((a, b) => a + b.weight_pct, 0);
  if (semis > 8) FL.push(['#fca5a5', `Semiconductor exposure ${semis.toFixed(1)}% — Situational Awareness discloses large puts against exactly these names. Not a reason to sell; a reason to know the correlation.`]);
  if (off) FL.push(['#fcd34d', `Weights total ${t.toFixed(2)}%, not 100%.`]);
  if (unset) FL.push(['#8fa0bf', `${unset} watchlist names have no weight — excluded from every statistic here.`]);
  if (!FL.length) FL.push(['#86efac', 'No concentration flags triggered.']);
  $('flags').innerHTML = FL.map(([c, x]) => `<div class="li"><span style="color:${c};font-size:15px">●</span><span class="d" style="font-size:12.5px">${x}</span></div>`).join('');
}

/* ---------------- buffett ---------------- */
function renderBuff() {
  const B = D.filter(r => r.buffett).sort((a, b) => b.buffett.passed - a.buffett.passed);
  $('bobs').innerHTML = (BUFF.observations || []).map(o =>
    `<div class="li"><span class="s" style="min-width:auto;color:${o.tone === 'warn' ? '#fcd34d' : o.tone === 'bad' ? '#fca5a5' : '#86efac'}">${esc(o.label)}</span><span class="d">${esc(o.text)}</span></div>`).join('')
    || '<div class="hint">No observations yet — run the build.</div>';
  $('tbb').innerHTML = B.map(r => {
    const b = r.buffett, t = b.tests;
    const col = b.passed >= 6 ? '#22c55e' : b.passed >= 4 ? '#f59e0b' : '#ef4444';
    return `<tr onclick="openD('${r.symbol}')">
      <td><div class="sym">${r.symbol}</div><div class="nm">${esc(r.name)}</div></td>
      <td><span class="pill ${b.moat === 'Wide' ? 'p-drift' : b.moat === 'Narrow' ? 'p-far' : 'p-imm'}">${b.moat}</span></td>
      <td class="num mono">${r.roic === null ? '—' : r.roic.toFixed(1) + '%'}</td>
      <td class="num mono">${b.de === null ? '—' : b.de.toFixed(2)}</td>
      <td class="num mono">${b.fcf_margin === null ? '—' : b.fcf_margin.toFixed(1) + '%'}</td>
      <td>${tick(t.stability.pass)}</td><td>${tick(t.circle.pass)}</td>
      <td>${tick(t.price.pass)} <span class="d" style="font-size:11px">${r.gap_pct === null ? 'no FV' : (r.gap_pct > 0 ? '+' : '') + r.gap_pct.toFixed(0) + '%'}</span></td>
      <td class="num"><b style="color:${col};font-size:14px">${b.passed}/${b.total}</b></td></tr>`;
  }).join('');
}

/* ---------------- discovery ---------------- */
function renderDisc() {
  const wl = new Set(DISC.watchlist || D.map(r => r.symbol));
  $('dclusters').innerHTML = (DISC.clusters || []).map(c =>
    `<tr><td><div class="sym">${c.symbol}${wl.has(c.symbol) ? '<span class="flag gray">watching</span>' : ''}</div></td>
     <td><span class="flag">${c.n} managers</span></td>
     <td class="d" style="font-size:11.5px">${esc(c.managers.slice(0, 4).join(' · '))}${c.managers.length > 4 ? ' …' : ''}</td>
     <td>${wl.has(c.symbol) ? '<span class="dash">—</span>' : `<button class="btn ghost" style="font-size:11px;padding:5px 10px" onclick="quickAdd('${c.symbol}')">+ Watchlist</button>`}</td></tr>`).join('')
    || '<tr><td colspan="4" class="hint">No conviction clusters in the latest Dataroma fetch.</td></tr>';

  $('drecent').innerHTML = (DISC.recent || []).slice(0, 60).map(r =>
    `<tr><td><div class="sym">${r.symbol}${wl.has(r.symbol) ? '<span class="flag gray">watching</span>' : ''}</div></td>
     <td class="d" style="font-size:11.5px">${esc(r.manager)}</td>
     <td><span class="${r.action === 'trim' ? 'dn' : 'up'}">${r.action.toUpperCase()}</span></td>
     <td class="d" style="font-size:11px">${esc(r.period)}</td>
     <td class="d" style="font-size:11px">${esc(r.detail.slice(0, 90))}</td></tr>`).join('')
    || '<tr><td colspan="5" class="hint">Dataroma data not yet fetched.</td></tr>';

  if (DISC.fetched) $('dfetch').textContent = 'Dataroma fetched ' + new Date(DISC.fetched).toLocaleString() + ' · ' + (DISC.how || '');
}
function quickAdd(sym) { $('asym').value = sym; lookup(); openAdd(); }

/* ---------------- mauboussin (browser-key, on tab open) ---------------- */
const LSK = 'ed_gemini_key';
function maubInit() {
  const k = localStorage.getItem(LSK);
  $('gkey').value = k || '';
  $('gstate').innerHTML = k ? '<span class="badge" style="background:#052e16;border-color:#14532d;color:#86efac">✓ key saved locally</span>'
    : '<span class="badge warn">no key — analysis disabled</span>';
  const sel = $('msym');
  if (!sel.options.length) {
    sel.innerHTML = D.filter(r => r.type !== 'etf' && r.price)
      .map(r => `<option value="${r.symbol}">${r.symbol} — ${esc(r.name)}</option>`).join('');
  }
  const cached = maubCache($('msym').value);
  if (cached) showMaub(cached); else $('mout').innerHTML = '<div class="hint">Select a ticker and press Analyse. Results cache for 24h per ticker.</div>';
}
function saveKey() {
  const v = $('gkey').value.trim();
  if (v) localStorage.setItem(LSK, v); else localStorage.removeItem(LSK);
  maubInit();
}
function clearKey() { localStorage.removeItem(LSK); $('gkey').value = ''; maubInit(); }
function maubCache(sym, val, model) {
  const k = 'ed_maub_' + sym;
  if (val === undefined) {
    try {
      const o = JSON.parse(localStorage.getItem(k) || 'null');
      if (o && Date.now() - o.t < 864e5) return o;
    } catch (e) { }
    return null;
  }
  localStorage.setItem(k, JSON.stringify({ t: Date.now(), text: val, sym, model }));
}
function buildPrompt(r) {
  return `You are applying Michael Mauboussin's expectations investing framework.

TICKER: ${r.symbol} (${r.name})
Price $${r.price} | 52-wk range $${r.low52 ?? 'n/a'}-${r.high52 ?? 'n/a'} (${r.pos52 === null ? 'n/a' : r.pos52.toFixed(0) + 'th pct'})
LTM P/E ${r.pe_ltm ?? 'n/a'} | Fwd P/E ${r.pe_fwd ?? 'n/a'} | EV/EBITDA ${r.ev_ebitda ?? 'n/a'} | ROIC ${r.roic === null ? 'n/a' : r.roic.toFixed(1) + '%'}
User's fair value: ${r.fair_value ? '$' + r.fair_value + ' (gap ' + r.gap_pct.toFixed(1) + '%)' : 'not set'}
Next earnings: ${r.earnings_date || 'unknown'}

Answer in four short sections with markdown headers:
1. What expectations for sales growth, operating margin and incremental investment does the current price imply?
2. Identify the expectations infliction point — which single value driver would most change the valuation, and by how much?
3. Where does the user's fair value diverge from market-implied expectations, and what must be true for the user to be right?
4. What specific, observable events would confirm or refute this?

Be concrete and quantitative. State uncertainty plainly. Do not give buy/sell advice.`;
}
async function analyse(force) {
  const sym = $('msym').value, r = D.find(x => x.symbol === sym);
  if (!r) return;
  if (!force) { const c = maubCache(sym); if (c) return showMaub(c); }
  const key = localStorage.getItem(LSK);
  if (!key) { $('mout').innerHTML = '<div class="hint" style="color:#fca5a5">No API key saved. Paste a free Google AI Studio key above, or use “Copy prompt” to run it manually.</div>'; return; }
  $('mout').innerHTML = '<div class="hint">Calling Gemini…</div>';
  // Model names churn and individual models hit quota independently, so try a
  // chain rather than pinning one. gemini-flash-latest always maps to the
  // current Flash release and was the one verified working on this key.
  const MODELS = ['gemini-flash-latest', 'gemini-2.5-flash', 'gemini-3-flash-preview', 'gemini-2.0-flash'];
  let lastErr = '';
  for (const model of MODELS) {
    try {
      const res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${encodeURIComponent(key)}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ contents: [{ parts: [{ text: buildPrompt(r) }] }] }),
      });
      const j = await res.json();
      if (j.error) { lastErr = `${model}: ${j.error.status} — ${j.error.message}`; continue; }
      const text = (((j.candidates || [])[0] || {}).content || {}).parts?.[0]?.text;
      if (!text) { lastErr = `${model}: empty response`; continue; }
      maubCache(sym, text, model);
      return showMaub({ sym, text, t: Date.now(), model });
    } catch (e) { lastErr = `${model}: ${e.message}`; }
  }
  $('mout').innerHTML = `<div class="hint" style="color:#fca5a5">All models failed.<br>Last error: ${esc(lastErr)}<br><br>
    Free tier is ~15 requests/minute and quota is per-model. Wait a moment, or use “Copy prompt” to run it manually.</div>`;
}
function showMaub(o) {
  const html = esc(o.text)
    .replace(/^#{1,6}\s*(.+)$/gm, '<b style="color:#7dd3fc">$1</b>')
    .replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
    .replace(/\n/g, '<br>');
  $('mout').innerHTML = `<div style="font-size:10.5px;color:#5f708f;text-transform:uppercase;letter-spacing:.6px;margin-bottom:11px">
      ${esc(o.model || 'gemini')} · ${new Date(o.t).toLocaleString()} · cached 24h</div>
    <div style="line-height:1.72;font-size:13px">${html}</div>
    <div style="border-top:1px solid #1e2942;margin-top:12px;padding-top:11px;font-size:11.5px;color:#5f708f">
      ⚠️ LLM-generated from public market data. Not verified, not advice. It can be confidently wrong — treat it as a prompt for your own thinking.</div>`;
}
function copyPrompt() {
  const r = D.find(x => x.symbol === $('msym').value); if (!r) return;
  navigator.clipboard.writeText(buildPrompt(r)).then(() => {
    window.open('https://aistudio.google.com/prompts/new_chat', '_blank');
  });
}

document.addEventListener('keydown', e => { if (e.key === 'Escape') closeD(); });
boot();
