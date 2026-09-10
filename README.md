# NEXUS Wealth Dashboard

A futuristic, self-contained wealth dashboard generated from `Datasource/Savings_And_Expense_Tracker.xlsx`
(Savings, Wealth Projection, Fixed Expenses, Husband_Expenses, Wife_Expenses sheets), enriched with
**live stock, ETF, and crypto prices** pulled from free public APIs.

## Files

| File | Purpose |
|---|---|
| `refresh_data.py` | Reads the Excel workbook + pulls live market data → writes `data.js` / `data.json` |
| `Refresh_Data.bat` | Double-click shortcut to run `refresh_data.py` on Windows |
| `index.html` | The dashboard UI (open directly in any browser, no server needed) |
| `Open_Dashboard.bat` | Double-click shortcut to open `index.html` |
| `style.css` / `dashboard.js` | Dashboard styling & rendering logic |
| `data.js` / `data.json` | Generated data snapshot (created/overwritten by refresh) |
| `live_server.py` | Optional local server for a truly *live* ticker tape + market intel (see below) |
| `Start_Live_Server.bat` | Double-click shortcut to run `live_server.py` |
| `Datasource/Savings_And_Expense_Tracker.xlsx` | Source workbook (Savings, Wealth Projection, Fixed Expenses, Husband_Expenses, Wife_Expenses) |

## How to use

1. **Refresh data**: double-click `Refresh_Data.bat` (or run `python refresh_data.py`).
   This pulls:
   - Live prices for all 24 stock/ETF tickers (MSFT, GOOGL, AAPL, AMZN, META, VOO, QQQ, etc.)
     from Yahoo Finance's public chart API (no key/auth required).
   - Live BTC & ETH prices from CoinGecko's public API.
   - Live USD/INR exchange rate.
   - The latest holdings, expenses, savings, and formulas from
     `Datasource/Savings_And_Expense_Tracker.xlsx`.
2. **View dashboard**: double-click `Open_Dashboard.bat` (or open `index.html` in a browser).
3. **Optional — go fully live**: double-click `Start_Live_Server.bat` and leave the console
   window open. This starts a tiny local server on `http://localhost:8787` that the dashboard
   automatically detects and polls for the scrolling ticker tape (prices every 60s) and the
   Watchlist/Market-News panels (analyst ratings, dividends, earnings, macro news every 20 min).
   Without it running, those sections still work off a static one-time snapshot from your last
   `Refresh_Data.bat` run and clearly label themselves "offline"/"static snapshot".

Re-run step 1 any time you want fresh Excel numbers, then reload the browser tab.

## What's on the dashboard

- **KPI strip**: combined net worth, monthly savings rate, portfolio risk score, blended
  growth assumption. (Click the 👁 icon top-right to blur all numeric values for privacy.)
- **Smart Alerts**: auto-detected rebalancing, concentration (e.g. MSFT/crypto), and
  emergency-fund-thinness alerts, severity-tagged.
- **Wealth Projection Horizon** (1/3/5/10/15/20/25/30 years, inflation-adjusted to today's ₹):
  1. Savings only, no investment growth, minus inflation.
  2. Savings + optimistic blended market growth, minus inflation.
  3. Same as #2, plus a 10% year-over-year increase in monthly savings.
  - **What-if sliders** below the chart let you interactively adjust savings rate, expected
    return, inflation, and horizon — recomputed live, client-side.
- **Asset allocation** (pie + bar), with **click-to-drill-down** on the donut (asset class →
  underlying holdings).
- **Goal tracking**: Financial Independence (25x annual expenses) progress ring.
- **Net worth trend vs S&P 500 benchmark**: 1M/3M/6M/1Y range toggle + $ value/% change toggle,
  plus a peak-to-trough **drawdown** chart underneath.
- **Alpha vs benchmark** (bar, by period) and **risk-vs-return bubble chart** (bubble size =
  position weight).
- **Sector/geography exposure treemap** and **portfolio drift vs target allocation** bar chart.
- **Household cash flow Sankey diagram** (income → fixed expenses / spending / savings) plus a
  **12-month contributions forecast** (stacked bar, Husband vs Wife).
- **Live market feed**: every stock/ETF/crypto holding with current price, % change (with
  explicit ▲/▼ icon + signed %, not color alone — colorblind-safe), and INR value.
- **Household cash flow cards**: Husband's & Wife's income, expenses, leftover, and expense
  breakdowns (fixed expenses, savings %, travel, misc — excluding the excluded columns per your
  instructions: Perks+ Expenses, Salary Hike Type, Stock Grant Per Year, Rent Hike %, % of
  salary/Bank).
- **AI insights & risk panel**: auto-generated observations (e.g., MSFT concentration risk,
  savings rate quality, currency exposure) based on your real numbers.
- **Natural-language query box**: ask things like "drawdown", "alpha", "goal", "alerts", "crypto"
  — it jumps to and summarizes the relevant chart (keyword-matched, fully client-side).
- **Light/dark mode** toggle (🌙/☀ icon) and **CSV export** (📤 icon) of all stock/crypto holdings.
- **Data-source labeling**: footer notes which figures are live vs Excel-cached.
- **Live scrolling ticker tape** (top of page): held stocks/ETFs/crypto + your full watchlist,
  price + %change, market-session badge (Pre-Market / Open / After-Hours / Closed / Holiday,
  computed from US Eastern time incl. DST), refreshes every 60s when `live_server.py` is running.
- **Interactive KPI tiles**: click any of the 4 headline KPI cards to expand an inline
  breakdown (allocation mix, savings split by person, top risk factors, or blended return by
  asset class) without leaving the page.
- **Watchlist & Market Intelligence panel**: your 44 stocks + 8 ETF watchlist (filterable by
  Held/Watching/ETF), each card showing live price/%change/52-week range plus analyst
  consensus rating, next earnings date, and next ex-dividend date pulled from NASDAQ's public
  API.
- **World & Macro-Economic News panel**: tabbed headlines for US / India / EU / China / Middle
  East / Japan markets & economy, sourced from Google News RSS, refreshed every 20 minutes.
- **Interactive ticker cards** (Live Holdings section): click a stock/crypto card to expand a
  mini sparkline + 52-week range + analyst/dividend/earnings chips (for held names that are also
  on the watchlist data set).

## Live data sources & redundancy

`refresh_data.py` now tries multiple free, unauthenticated public APIs with automatic fallback,
so a single provider outage/rate-limit doesn't break a refresh:

- **Stocks/ETFs**: Yahoo Finance chart API (`query1` then `query2` mirror) → falls back to
  NASDAQ's public quote API (`api.nasdaq.com`) for US-listed names if both Yahoo mirrors fail →
  falls back to the last cached Excel value as a last resort.
- **Crypto**: CoinGecko public API → falls back to Binance's public 24hr ticker API.
- **FX**: Yahoo Finance (`INR=X`) → falls back to the cached Excel FX cell.
- Also researched but **not wired in**: Stooq's CSV endpoint (`stooq.com/q/l/...`) is genuinely
  unauthenticated for quotes, but returned a bot-check/Cloudflare challenge page in testing
  rather than data, so it wasn't reliable enough to include as a fallback.

## Out of scope (and why)

A few of the requested "premium wealth-dashboard" features aren't implemented because this is a
static, local, single-user HTML file with no backend/server/database — they'd require
infrastructure genuinely beyond that scope:

- **Read-only encrypted account linking with MFA / true multi-account auto-sync** (banks,
  brokerages, retirement accounts): requires a bank-aggregation provider (e.g. Plaid/Yodlee),
  OAuth, and a secure backend to hold credentials/tokens — not something a static local file can
  do safely.
- **Per-holding tax-lot / cost-basis tracking, tax-loss harvesting**: the workbook has no
  purchase-price/cost-basis or lot data, only current quantities.
- **Dividend/income calendar**: no dividend schedule/ex-date data exists anywhere in the source
  workbook or the free APIs used.
- **Fee-impact chart**: no expense-ratio/fee data exists for the funds/ETFs held.
- **Change history/audit trail for manual Excel edits**: would require diffing snapshots of the
  workbook over time, which isn't tracked today (the dashboard only ever sees the latest state).
- **True mobile-native parity / draggable-resizable widget layout**: the dashboard is fully
  responsive (usable on mobile), but drag/resize widget rearrangement wasn't built — the
  additional complexity/testing surface wasn't judged worth it for a single-user local tool.

## Live server & market intelligence details

`Start_Live_Server.bat` runs `live_server.py`, a stdlib-only local HTTP server (no extra installs)
that re-uses `refresh_data.py`'s fetch functions server-side (to sidestep the fact that Yahoo
Finance and NASDAQ's public APIs don't send CORS headers, so a browser page can't poll them
directly). It exposes:

- `GET /api/tape.json` — live prices for held + watchlist tickers and BTC/ETH, refreshed every
  60 seconds, plus the current US market session status.
- `GET /api/deep.json` — analyst ratings, dividend dates, earnings dates (per watchlist ticker)
  and macro news headlines, refreshed every 20 minutes (these don't change minute-to-minute).
- `GET /api/status` — health check + last-updated timestamps for both.

**Known limitations**:
- NASDAQ's public API (used for analyst ratings/dividends/earnings) doesn't recognize
  `BRK.A`/`BRK.B` under its symbol scheme — those two show price data fine but no
  analyst/dividend/earnings chips (card shows "coverage unavailable").
- The market-holiday calendar in `compute_market_status()` is a hardcoded approximate NYSE
  holiday list for 2026 — update it yearly if you keep using this past 2026.
- The first `refresh_deep()` pass after starting the live server takes a few minutes (46
  watchlist tickers × 3 API calls each with rate-limit-friendly delays) before the Watchlist and
  News panels switch from "static snapshot" to live data — this is expected, not a bug.
- `Refresh_Data.bat` itself (the Excel + core-holdings refresh) now takes roughly 8–9 minutes to
  run end-to-end, up from before, because it also enriches your held stocks with the same
  analyst/dividend/earnings lookups. This is a one-time manual step, not something you need to
  run often.

## Notes on data sources

- **Excel "Live" stock cells** (`_FV` linked data-type cells) can't be read directly by Python
  libraries — they're Excel's native Stocks data type. The underlying tickers were reverse
  engineered from the holding-value formulas in the Savings sheet and are now fetched live
  and independently via Yahoo Finance in `refresh_data.py`.
- **Wife's corpus total** (`Wealth Projection!E12`) comes from an external linked workbook
  that isn't present locally, so it's used as the last-cached snapshot value from
  `Datasource/Savings_And_Expense_Tracker.xlsx`. Her income/expense figures (`Wife_Expenses`) are the cached
  values synced from her own tracker the last time the Excel file itself was refreshed.
- Inflation assumption: 6% (long-run India CPI). Growth assumptions per asset class, volatility
  assumptions, and target allocation are all defined at the top of `refresh_data.py`
  (`ASSET_RETURNS`, `ASSET_VOLATILITY`, `TARGET_ALLOCATION`) — tweak them any time before
  re-running.
- The **net worth trend / drawdown / alpha** charts only cover currently-held tickers (historical
  weights aren't tracked) and approximate historical FX using today's USD/INR rate — treat them
  as directionally useful, not exact.
