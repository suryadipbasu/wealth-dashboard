# 🌌 NEXUS Wealth Dashboard

> A futuristic, self-contained household wealth dashboard — built from a single Excel workbook,
> enriched with **live stock, ETF, crypto, and macro-economic data** pulled from free public APIs.
> No database. No paid backend. Just an Excel sheet, a Python script, and a static webpage.

🔗 **Live demo**: https://suryadipbasu.github.io/wealth-dashboard/

![Made with Python](https://img.shields.io/badge/data%20pipeline-Python-3776AB?logo=python&logoColor=white)
![Chart.js](https://img.shields.io/badge/charts-Chart.js-FF6384?logo=chartdotjs&logoColor=white)
![GitHub Pages](https://img.shields.io/badge/hosted%20on-GitHub%20Pages-222?logo=github)
![No backend](https://img.shields.io/badge/backend-none%20needed-brightgreen)

---

## ✨ What is this?

You fill in your money details in one Excel file. A Python script reads it, mixes in live market
prices, and spits out a JSON file. A static webpage reads that JSON and renders a full financial
command-center: net worth, savings rate, 30-year wealth projections, portfolio risk, asset
allocation, cash flow, and more — all with a glowing, sci-fi-dashboard aesthetic. 🚀

## 🧭 How it all works (the 30-second version)

```
📊 Datasource/Savings_And_Expense_Tracker.xlsx   (you fill this in)
          │
          ▼
🐍 refresh_data.py   → reads the Excel + calls free stock/crypto/macro APIs
          │
          ▼
🗂️ data.json / data.js   (generated snapshot, no manual editing needed)
          │
          ▼
🖥️ index.html + dashboard.js + style.css   → the dashboard you actually look at
```

There are **three ways to keep prices fresh**, all already wired up:

| Mode | How | Best for |
|---|---|---|
| 🔁 **Manual refresh** | Run `Refresh_Data.bat` whenever you want new numbers | Running locally on your own PC |
| ⏱️ **Auto-refresh (GitHub Actions)** | `.github/workflows/refresh-data.yml` re-runs `refresh_data.py` every 15 min and commits the new `data.json` | Once deployed to GitHub Pages — fully hands-off, this is what keeps the live demo above from going stale |
| 📡 **Live ticker tape (local only)** | `Start_Live_Server.bat` runs a tiny local server so the scrolling ticker updates every 60s while the dashboard is open on *that same machine* | Local use, live price-watching |

> ⚠️ **Important**: the "Live Server" (`live_server.py`, port `8787`) only exists on a machine
> that is actually running it — it is **not** something a deployed GitHub Pages site can offer,
> because Pages only serves static files with no backend at all. On the deployed site, the
> dashboard instead shows an **"Auto-Refreshed"** pill and pulls straight from `data.json`, which
> the GitHub Actions workflow above keeps updated every 15 minutes automatically — you don't need
> to do anything for that to keep working.

## 📁 File map

| File | Purpose |
|---|---|
| `Datasource/Savings_And_Expense_Tracker.xlsx` | 📊 **The only file you need to edit.** Your savings, expenses, and projections. |
| `refresh_data.py` | 🐍 Reads the Excel + pulls live market data → writes `data.js` / `data.json`. |
| `Refresh_Data.bat` | 🖱️ Double-click shortcut (Windows) to run `refresh_data.py`. |
| `index.html` | 🖥️ The dashboard itself — open directly in any browser, no server required. |
| `Open_Dashboard.bat` | 🖱️ Double-click shortcut to open `index.html`. |
| `style.css` / `dashboard.js` | 🎨 Dashboard styling & chart-rendering logic. |
| `data.js` / `data.json` | 📦 Generated snapshot — **don't edit by hand**, it gets overwritten every refresh. |
| `live_server.py` / `Start_Live_Server.bat` | 📡 Optional local server for a truly live ticker tape (local use only, see table above). |
| `.github/workflows/refresh-data.yml` | 🤖 GitHub Actions workflow that auto-refreshes data every 15 min once deployed. |

---

## 🚀 Quick start (just want to see it running locally?)

1. Open the workbook — `Datasource/Savings_And_Expense_Tracker.xlsx` — already has sample data in it.
2. Double-click `Refresh_Data.bat` and wait for it to finish (a few minutes the first time).
3. Double-click `Open_Dashboard.bat`. That's it. 🎉

---

## 🛠️ Setting this up with **your own** financial data (from scratch)

The dashboard is only as good as the numbers in the Excel workbook. Here's exactly what to fill
in, sheet by sheet. **Rule of thumb**: type over the *values*, don't touch cells that already
contain a formula (anything starting with `=`) — those calculate themselves.

### 1️⃣ `Savings` sheet — everything you own

This is your net-worth ledger. Each row is one holding.

| Section | What to put | Example |
|---|---|---|
| **Savings Bank MIN BAL A/C** | Your bank names + minimum balance you keep in each | `HDFC` → `F` column = ₹5,000 |
| **Fixed Deposits** | One row per FD: ROI %, inception/maturity date, maturity amount, current value | `HDFC (Emergency Fund)` → 7.25% |
| **Pension Funds** | EPF / NPS balances | `Employee Provident Fund` → current balance |
| **Debt Funds** | PPF and similar | `Public Provident Fund` → current balance |
| **Equity - MF/ELSS** | Mutual funds — name + current value (column `F`) | `Nifty50 Index Fund` |
| **Equity - Indian Stocks & US ETFs** | 🟢 **This is the important one** — one row per stock/ETF you hold, prefixed `NASDAQ:` | see below 👇 |
| **Crypto Assets** | Bitcoin, Ethereum, or any exchange wallet balance | `Bitcoin (BTC)` → quantity in column `E` |

**Adding/removing a stock or ETF holding:**
- Each stock row only needs column `E` (quantity you hold) filled in — the price is fetched live.
- If a row's quantity (`E`) is `0`, the dashboard just treats it as "not currently held" (handy for
  tickers you're watching but haven't bought yet).
- To track a **new** ticker that isn't already a row: add a new row under "Equity - Indian Stocks
  & US ETFs" with the ticker name in column `A` (e.g. `NASDAQ: TSLA`), then open
  `refresh_data.py` and add one line to the `HOLDING_ROWS` dictionary (near the top of the file)
  mapping your new row number → `(ticker, "E<row>", None)`. Search for `HOLDING_ROWS = {` to find it.
- To remove a holding you no longer own, just set its quantity (`E`) to `0` — no need to delete
  the row.

> 💡 The workbook uses Excel's built-in **Stocks data type** (`A64:A90`) purely as a visual
> "live card" inside Excel itself — the dashboard does **not** depend on it and fetches its own
> live prices independently via `refresh_data.py`. You can leave that block alone.

### 2️⃣ `Wealth Projection` sheet — your monthly savings breakdown

Two blocks, one for each partner (`HUSBAND` / `WIFE`):

| Cell | Meaning |
|---|---|
| `B2:B8` (or `B12:B16`) | Monthly amount going into each instrument (Mutual Fund, PPF, Crypto, US Equity, RD, Gold, NPS) |
| `C9` (or `C17`) `Monthly Total Savings` | Auto-sums the column above — leave as formula |

Just update the ₹ amount you invest monthly per instrument. This total automatically feeds the
"Household Cash Flow" and "Wealth Projection Horizon" charts on the dashboard.

### 3️⃣ `Fixed Expenses` sheet — recurring deductions (insurance, RDs, taxes)

One row per fixed/recurring outgoing (car insurance, term insurance, annual health check-up, ITR
filing fees, etc.). Fill in `Amount`, `RD Amount Deducted per month`, and due dates. Column `I2`
(`Total Deductions per month`) sums it up automatically — this feeds both partners' expense
sheets.

### 4️⃣ `Husband_Expenses` / `Wife_Expenses` sheets — monthly budget per person

Both sheets follow the same pattern:

| Row type | What it means |
|---|---|
| Rows under **"Necessary Expenses"** | Rent, groceries, utilities, food, clothes — your actual monthly spend |
| Rows under **"Fixed Expenses"** | Insurance/maintenance pulled in from the `Fixed Expenses` sheet |
| Row under **"Savings"** (e.g. `Savings per month`) | Auto-pulled from the `Wealth Projection` sheet — leave as formula |
| Rows under **"Travel Expenses"** | Flights, cabs — recurring or occasional travel spend |
| Rows under **"Miscellaneous Expenses"** | Personal spending, unexpected buffer, family contributions |
| **`Net Average Salary`** row (near the bottom) | 🟢 **Type your actual monthly take-home salary here** |
| **`Total Utilization`** / **`Leftover Salary`** rows | Auto-calculated — leave as formulas |

> ⚠️ If you add or remove rows in these two sheets, the row numbers for `Net Average Salary`,
> `Total Utilization`, and `Leftover Salary` will shift. Open `refresh_data.py`, search for
> `sb_salary = safe_num(get_cell(sb, "B29"))` (and the 5 lines around it), and update the cell
> references to match your new row numbers.

### 5️⃣ Tweak the assumptions (optional)

Near the top of `refresh_data.py`:
- `ASSET_RETURNS` — expected long-term annual return assumption per asset class.
- `ASSET_VOLATILITY` — used for the risk score.
- `TARGET_ALLOCATION` — your ideal portfolio mix, used for the drift chart.
- Inflation assumption (6% by default, long-run India CPI) — search for `INFLATION`.

### 6️⃣ Refresh and view

Run `Refresh_Data.bat`, then open `index.html` (or `Open_Dashboard.bat`). Repeat step 6 any time
your numbers change.

---

## 🌐 Deploying your own copy to GitHub Pages

1. Push this folder to a new GitHub repo of your own (public repos get free GitHub Pages hosting).
2. In the repo settings → **Pages**, set source to the `main` branch, root folder (`/`).
3. The included `.github/workflows/refresh-data.yml` workflow will automatically re-run
   `refresh_data.py` every 15 minutes and commit the refreshed `data.json`/`data.js` — no server
   needed, GitHub's free Actions minutes handle it.
4. Your dashboard is now live at `https://<your-username>.github.io/<repo-name>/`. 🎉

> Note: the optional `live_server.py` / 60-second ticker tape only works when running locally —
> GitHub Pages can't run a Python backend. On Pages, the dashboard automatically detects it isn't
> on `localhost` and skips trying to reach a live server at all, instead showing an
> **"Auto-Refreshed"** pill sourced from `data.json`'s own timestamp. This is expected, not a bug.

---

## 🪄 What's on the dashboard

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

## 🔌 Live data sources & redundancy

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

## 🧱 Out of scope (and why)

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

## 📡 Live server & market intelligence details

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

## 📝 Notes on data sources

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
