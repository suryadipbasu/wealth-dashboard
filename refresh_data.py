#!/usr/bin/env python3
"""
Refresh Data - Wealth Dashboard
--------------------------------
Pulls the latest data from Savings_And_Expense_Tracker.xlsx (Savings,
Wealth Projection, Fixed Expenses, Husband_Expenses, Wife_Expenses) AND live
market data (stocks, ETFs, crypto, USD/INR fx) from free/unauthenticated
public APIs (Yahoo Finance chart API + CoinGecko), then computes the
full wealth-dashboard model and writes it to data.js (consumed by
index.html).

Run:  python refresh_data.py
"""
import concurrent.futures as cf
import hashlib
import json
import os
import sys
import threading
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime

import calendar
import openpyxl
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
XLSX_PATH = os.path.join(BASE_DIR, "Datasource", "Savings_And_Expense_Tracker.xlsx")
OUT_JS = os.path.join(BASE_DIR, "data.js")
OUT_JSON = os.path.join(BASE_DIR, "data.json")

UA = {"User-Agent": "Mozilla/5.0 (WealthDashboard/1.0)"}

# ---------------------------------------------------------------------------
# Local disk cache: every successful public-API response is persisted here
# keyed by a hash of a human-readable cache key. When a live call fails
# (rate-limited / API down / offline), callers fall back to the last
# successful cached value instead of showing nothing. This also lets
# live_server.py and refresh_data.py share one cache on disk.
# ---------------------------------------------------------------------------
CACHE_DIR = os.path.join(BASE_DIR, ".api_cache")
_cache_lock = threading.Lock()


def _cache_path(key):
    h = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, h + ".json")


def cache_get(key):
    try:
        with open(_cache_path(key), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return None


def cache_set(key, value):
    try:
        with _cache_lock:
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(_cache_path(key), "w", encoding="utf-8") as f:
                json.dump({"cachedAt": datetime.now().isoformat(timespec="seconds"), "value": value}, f)
    except Exception:  # noqa: BLE001
        pass


def cache_get_value(key):
    """Read a cache entry written by cache_set and return just its value
    (or None if missing/corrupt)."""
    entry = cache_get(key)
    if isinstance(entry, dict) and "value" in entry:
        return entry["value"]
    return None


def parallel_map(items, fn, max_workers=8):
    """Run fn(item) for every item concurrently on a small thread pool
    (network-bound I/O, so threads are sufficient - no need for
    multiprocessing) and return results in the same order as `items`.
    A failure in one item's worker doesn't abort the others; it just
    yields None for that slot (the caller's own fetch function is
    responsible for its own cache-fallback logic on failure)."""
    results = [None] * len(items)
    if not items:
        return results
    with cf.ThreadPoolExecutor(max_workers=min(max_workers, len(items))) as ex:
        future_to_idx = {ex.submit(fn, item): i for i, item in enumerate(items)}
        for fut in cf.as_completed(future_to_idx):
            i = future_to_idx[fut]
            try:
                results[i] = fut.result()
            except Exception as e:  # noqa: BLE001
                print(f"  [warn] parallel task failed: {e}", file=sys.stderr)
                results[i] = None
    return results


# ---------------------------------------------------------------------------
# Ticker map: Savings sheet rows B67:B93 hold linked Excel "Stock" data-type
# cells (rendered as #VALUE! by openpyxl). Their true tickers were derived by
# cross-referencing the F-column holding-value formulas in rows 29-54, which
# multiply each holding qty (col E) by the matching Bxx live-price cell.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Holding rows in the Savings sheet: ticker, quantity (col E), and the native
# Excel "Stock" linked-data-type cell (col B, rows 64-87) that holds the
# ticker's live price when Excel refreshes it online. This script fetches
# its own independent live price per ticker via Yahoo Finance; the B-cell is
# only consulted as a last-resort fallback and is NEVER written back to,
# since overwriting it with a plain number would strip Excel's live data-type
# binding and break the "Refresh Data Types" feature for the user.
# ---------------------------------------------------------------------------
HOLDING_ROWS = {
    29: ("MSFT", "E29", "B64"), 30: ("QQQ", "E30", "B67"), 31: ("QQQM", "E31", "B68"),
    32: ("META", "E32", "B77"), 33: ("DUOL", "E33", "B74"), 34: ("TMDX", "E34", "B79"),
    35: ("SOUN", "E35", "B85"), 36: ("AMD", "E36", "B86"), 37: ("PLTR", "E37", "B84"),
    38: ("VOO", "E38", "B66"), 39: ("NFLX", "E39", "B78"), 40: ("SOXX", "E40", "B70"),
    41: ("EWS", "E41", "B69"), 42: ("GOOGL", "E42", "B65"), 43: ("UNH", "E43", "B81"),
    44: ("RKLB", "E44", "B87"), 45: ("CRSP", "E45", "B71"), 46: ("ASML", "E46", "B72"),
    47: ("AMZN", "E47", "B73"), 48: ("ASTS", "E48", "B75"), 49: ("BEAM", "E49", "B76"),
    50: ("AAPL", "E50", "B80"), 51: ("IREN", "E51", "B82"), 52: ("CRWD", "E52", "B83"),
}
FX_CELL = "B90"  # USD/INR (native Stock/Currency linked-data-type cell)

INFLATION_RATE = 0.06          # long-run average India CPI inflation assumption
SAVINGS_GROWTH_YOY = 0.10      # rule 4, scenario 3: save 10% more each year than prior year
PROJECTION_YEARS = [1, 3, 5, 10, 15, 20, 25, 30]
BENCHMARK_TICKER = "%5EGSPC"   # S&P 500
BENCHMARK_LABEL = "S&P 500"

# Optimistic long-run nominal return assumptions per asset class (used for
# scenario 2 & 3 blended portfolio growth rate)
ASSET_RETURNS = {
    "emergency": 0.035,
    "pension": 0.085,
    "debt": 0.071,
    "indian_equity": 0.13,
    "foreign_equity": 0.11,
    "crypto": 0.20,
}

# Approximate annualized volatility assumptions per asset class (for the
# risk-vs-return bubble chart). These are illustrative long-run estimates,
# not a statistical calculation from your actual holdings.
ASSET_VOLATILITY = {
    "emergency": 0.01,
    "pension": 0.06,
    "debt": 0.05,
    "indian_equity": 0.18,
    "foreign_equity": 0.22,
    "crypto": 0.55,
}

# Recommended target allocation used for the portfolio-drift chart. Tune to taste.
TARGET_ALLOCATION = {
    "emergency": 0.10,
    "pension": 0.15,
    "debt": 0.20,
    "indianEquity": 0.15,
    "foreignEquity": 0.35,
    "crypto": 0.05,
}

# Approximate sector/geography classification per ticker (illustrative, for the
# exposure treemap). Not sourced from the workbook.
TICKER_META = {
    "MSFT": {"sector": "Technology", "geo": "United States"},
    "GOOGL": {"sector": "Technology", "geo": "United States"},
    "VOO": {"sector": "Diversified ETF", "geo": "United States"},
    "QQQ": {"sector": "Diversified ETF (Tech-heavy)", "geo": "United States"},
    "QQQM": {"sector": "Diversified ETF (Tech-heavy)", "geo": "United States"},
    "EWS": {"sector": "Diversified ETF", "geo": "Singapore"},
    "SOXX": {"sector": "Semiconductors ETF", "geo": "United States"},
    "CRSP": {"sector": "Healthcare/Biotech", "geo": "United States"},
    "ASML": {"sector": "Semiconductors", "geo": "Europe"},
    "AMZN": {"sector": "Consumer/Tech", "geo": "United States"},
    "DUOL": {"sector": "Technology", "geo": "United States"},
    "ASTS": {"sector": "Communications/Tech", "geo": "United States"},
    "BEAM": {"sector": "Healthcare/Biotech", "geo": "United States"},
    "META": {"sector": "Technology", "geo": "United States"},
    "NFLX": {"sector": "Communication Services", "geo": "United States"},
    "TMDX": {"sector": "Healthcare", "geo": "United States"},
    "AAPL": {"sector": "Technology", "geo": "United States"},
    "UNH": {"sector": "Healthcare", "geo": "United States"},
    "IREN": {"sector": "Technology/Crypto Infra", "geo": "Australia"},
    "CRWD": {"sector": "Technology (Cybersecurity)", "geo": "United States"},
    "PLTR": {"sector": "Technology", "geo": "United States"},
    "SOUN": {"sector": "Technology (AI)", "geo": "United States"},
    "AMD": {"sector": "Technology (Semiconductors)", "geo": "United States"},
    "RKLB": {"sector": "Industrials (Aerospace)", "geo": "United States"},
}

HISTORY_RANGES = {"1M": "1mo", "3M": "3mo", "6M": "6mo", "1Y": "1y"}

# ---------------------------------------------------------------------------
# Watchlist: stocks/ETFs the user tracks (both currently-held names and ones
# they're only watching). Held tickers are cross-referenced against
# HOLDING_ROWS at build time and flagged accordingly in the payload.
# ---------------------------------------------------------------------------
WATCHLIST_META = {
    "AMD": "Advanced Micro Devices", "TSM": "TSMC", "MU": "Micron",
    "SNDK": "SanDisk Corp", "WDC": "Western Digital", "SPCX": "SpaceX",
    "GOOGL": "Alphabet Class A", "USO": "United States Oil Fund",
    "CRWD": "CrowdStrike Holdings", "MARA": "MARA Holdings",
    "PANW": "Palo Alto Networks", "NBIS": "Nebius Group", "IREN": "IREN",
    "CNC": "Centene", "SOUN": "SoundHound AI", "UNH": "UnitedHealth",
    "NVO": "Novo Nordisk", "OKLO": "Oklo Inc", "PLTR": "Palantir Technologies",
    "ACHR": "Archer Aviation", "RKLB": "Rocket Lab USA", "JOBY": "Joby Aviation",
    "CRSP": "Crispr Therapeutics", "ASTS": "AST SpaceMobile", "BEAM": "Beam Therapeutics",
    "BRK.B": "Berkshire Hathaway B", "BRK.A": "Berkshire Hathaway A",
    "TMDX": "TransMedics Group", "CRM": "Salesforce", "AAPL": "Apple",
    "AMZN": "Amazon", "META": "Meta Platforms", "MSFT": "Microsoft",
    "ASML": "ASML Holding", "DUOL": "Duolingo", "NFLX": "Netflix",
    "GOOG": "Alphabet Class C", "NVDA": "Nvidia",
    "TQQQ": "ProShares UltraPro QQQ", "VTI": "Vanguard Total Stock Market ETF",
    "VOO": "Vanguard S&P 500 ETF", "SOXX": "iShares Semiconductor ETF",
    "IVV": "iShares Core S&P 500 ETF", "IWM": "iShares Russell 2000 ETF",
    "QQQM": "Invesco NASDAQ 100 ETF", "QQQ": "Invesco QQQ Trust",
}
WATCHLIST_ETFS = {"TQQQ", "VTI", "VOO", "SOXX", "IVV", "IWM", "QQQM", "QQQ"}

# ---------------------------------------------------------------------------
# Macro / global-market indicators: index & benchmark tickers not held as
# portfolio positions, shown on the ticker tape + a dedicated "Global Markets"
# panel for market-context (rule: "unauthenticated public API" — all served
# by the same free Yahoo Finance chart API already used for holdings).
# ---------------------------------------------------------------------------
MACRO_TICKERS = {
    "SPX": ("%5EGSPC", "S&P 500"),
    "NDX": ("%5ENDX", "Nasdaq 100"),
    "US30": ("%5EDJI", "Dow Jones Industrial Avg"),
    "NI225": ("%5EN225", "Nikkei 225"),
    "NIFTY": ("%5ENSEI", "Nifty 50"),
    "BANKNIFTY": ("%5ENSEBANK", "Bank Nifty"),
    "DXY": ("DX-Y.NYB", "US Dollar Index"),
    "HACK": ("HACK", "ETFMG Cyber Security ETF"),
    "IGV": ("IGV", "iShares Expanded Tech-Software ETF"),
}
# Commodities are grouped separately (rendered alongside crypto in the
# "Crypto & Commodities" panel) rather than in the macro-indicators grid.
COMMODITIES = {
    "GOLD": ("GC%3DF", "Gold (Futures)"),
    "SILVER": ("SI%3DF", "Silver (Futures)"),
    "USOIL": ("CL%3DF", "Crude Oil (WTI)"),
}
MACRO_FALLBACK_SKIP = {"CL%3DF", "DX-Y.NYB", "GC%3DF", "SI%3DF"}  # not on NASDAQ's quote API, skip that fallback attempt


def api_ticker(ticker):
    """Yahoo/NASDAQ use a hyphen for share classes (BRK.B -> BRK-B)."""
    return ticker.replace(".", "-")


# ---------------------------------------------------------------------------
# Macro news, analyst ratings, dividend + earnings dates (all free,
# unauthenticated public endpoints).
# ---------------------------------------------------------------------------
NEWS_REGIONS = {
    "US": ("markets OR economy OR Federal Reserve", "en-US", "US"),
    "India": ("markets OR economy OR RBI OR Sensex OR Nifty", "en-IN", "IN"),
    "EU": ("Eurozone economy OR ECB OR European Union markets", "en-GB", "GB"),
    "China": ("China economy OR China markets OR PBOC", "en-US", "US"),
    "Middle East": ("Middle East economy OR oil prices OR OPEC", "en-US", "US"),
    "Japan": ("Japan economy OR Bank of Japan OR Nikkei", "en-US", "US"),
}


NEWS_CACHE_MAX = 30
_news_cache = {}  # region -> list of {title, link, pubDate, source}, newest-first, capped at NEWS_CACHE_MAX


def _merge_news_cache(region, fresh_items, cap=NEWS_CACHE_MAX):
    """Accumulate headlines across repeated refreshes instead of discarding
    everything each time a feed returns fewer/different items. New items are
    placed first (freshest), then any previously-cached items not present in
    this fetch are appended, deduped by link (falls back to title), and the
    combined list is capped at `cap` entries. This is what lets live_server's
    periodic news refresh build up a rolling history of up to 30 headlines
    per region instead of only ever showing the latest ~6."""
    seen = set()
    merged = []
    for item in fresh_items + _news_cache.get(region, []):
        key = item.get("link") or item.get("title")
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(item)
        if len(merged) >= cap:
            break
    _news_cache[region] = merged
    return merged


def fetch_rss(url, retries=2, delay=1.0, limit=20):
    import xml.etree.ElementTree as ET
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=15) as resp:
                root = ET.fromstring(resp.read())
            items = []
            for item in root.findall(".//item")[:limit]:
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                pub = (item.findtext("pubDate") or "").strip()
                source_el = item.find("source")
                source = source_el.text.strip() if source_el is not None and source_el.text else None
                if not source and " - " in title:
                    title, source = title.rsplit(" - ", 1)
                items.append({"title": title, "link": link, "pubDate": pub, "source": source})
            return items
        except Exception as e:  # noqa: BLE001
            time.sleep(delay)
    print(f"  [warn] failed to fetch RSS {url}", file=sys.stderr)
    return []


def fetch_macro_news():
    """Top headlines per region via Google News' free public RSS search
    (no API key required). Results are merged into a rolling per-region
    cache (max 30 records) so headlines persist across refresh cycles
    rather than being replaced wholesale every time."""
    news = {}
    for region, (query, hl, gl) in NEWS_REGIONS.items():
        url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl={hl}&gl={gl}&ceid={gl}:{hl.split('-')[0]}"
        fresh = fetch_rss(url)
        news[region] = _merge_news_cache(region, fresh)
        time.sleep(0.2)
    return news


def fetch_stock_news(ticker, limit=4):
    """Recent headlines for a specific ticker via Google News RSS."""
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(ticker + ' stock')}&hl=en-US&gl=US&ceid=US:en"
    return fetch_rss(url)[:limit]


def fetch_nasdaq_analyst_rating(ticker):
    """Analyst consensus rating (Buy/Hold/Sell) via NASDAQ's public API.
    Falls back to the last successfully cached rating if the live call
    fails outright (vs. a valid response that simply has no rating)."""
    cache_key = f"analyst:{ticker}"
    data = http_json(f"https://api.nasdaq.com/api/analyst/{api_ticker(ticker)}/ratings", retries=2)
    if data is None:
        cached = cache_get_value(cache_key)
        if cached is not None:
            print(f"  [cache] {ticker} analyst rating: live fetch failed, using cached value", file=sys.stderr)
        return cached
    if not data.get("data"):
        cache_set(cache_key, None)
        return None
    d = data["data"]
    result = {
        "consensus": d.get("meanRatingType"),
        "summary": d.get("ratingsSummary"),
        "numAnalysts": len(d.get("brokerNames") or []),
    }
    cache_set(cache_key, result)
    return result


def fetch_nasdaq_dividends(ticker):
    """Next ex-dividend / payment date + yield via NASDAQ's public API.
    Falls back to the last successfully cached value if the live call
    fails outright (vs. a valid response that simply has no dividend)."""
    cache_key = f"dividend:{ticker}"
    data = http_json(f"https://api.nasdaq.com/api/quote/{api_ticker(ticker)}/dividends?assetclass=stocks", retries=2)
    if data is None:
        cached = cache_get_value(cache_key)
        if cached is not None:
            print(f"  [cache] {ticker} dividends: live fetch failed, using cached value", file=sys.stderr)
        return cached
    if not data.get("data"):
        cache_set(cache_key, None)
        return None
    d = data["data"]
    ex_date = d.get("exDividendDate")
    if not ex_date or ex_date in ("N/A", "0"):
        cache_set(cache_key, None)
        return None
    result = {
        "exDividendDate": ex_date,
        "paymentDate": d.get("dividendPaymentDate"),
        "yield": d.get("yield"),
        "annualizedDividend": d.get("annualizedDividend"),
    }
    cache_set(cache_key, result)
    return result


def fetch_nasdaq_earnings(ticker):
    """Next quarter's consensus EPS forecast + most recent reported-earnings
    date via NASDAQ's public API (no key needed). Falls back to the last
    successfully cached value if both underlying live calls fail outright."""
    cache_key = f"earnings:{ticker}"
    t = api_ticker(ticker)
    out = {"nextFiscalQuarterEnd": None, "consensusEps": None, "numEstimates": None, "lastReportedDate": None}
    fdata = http_json(f"https://api.nasdaq.com/api/analyst/{t}/earnings-forecast", retries=2)
    got_any = fdata is not None
    try:
        rows = fdata["data"]["quarterlyForecast"]["rows"]
        if rows:
            out["nextFiscalQuarterEnd"] = rows[0].get("fiscalEnd")
            out["consensusEps"] = rows[0].get("consensusEPSForecast")
            out["numEstimates"] = rows[0].get("noOfEstimates")
    except Exception:  # noqa: BLE001
        pass
    time.sleep(0.15)
    sdata = http_json(f"https://api.nasdaq.com/api/company/{t}/earnings-surprise", retries=2)
    got_any = got_any or (sdata is not None)
    try:
        table = sdata["data"]["earningsSurpriseTable"]["rows"]
        if table:
            out["lastReportedDate"] = table[0].get("dateReported")
    except Exception:  # noqa: BLE001
        pass
    if got_any:
        cache_set(cache_key, out)
        return out
    cached = cache_get_value(cache_key)
    if cached is not None:
        print(f"  [cache] {ticker} earnings: live fetch failed, using cached value", file=sys.stderr)
        return cached
    return out


def compute_india_market_status(now_utc=None):
    """Approximate NSE/BSE equity-market session (open 9:15-15:30 IST,
    Mon-Fri, minus major holidays) — no external tz packages needed."""
    from datetime import timedelta, timezone

    now_utc = now_utc or datetime.now(timezone.utc)
    ist_now = now_utc + timedelta(hours=5, minutes=30)

    INDIA_HOLIDAYS_2026 = {  # NSE full-day closures (approximate; update yearly)
        "01-26", "03-04", "03-21", "04-03", "04-14", "05-01", "08-15", "08-27", "10-02", "10-20", "11-08", "12-25",
    }
    md = ist_now.strftime("%m-%d")
    weekday = ist_now.weekday()  # Mon=0..Sun=6
    minutes = ist_now.hour * 60 + ist_now.minute

    if weekday >= 5 or md in INDIA_HOLIDAYS_2026:
        status, label = "closed", "Offline" + (" (Holiday)" if md in INDIA_HOLIDAYS_2026 else " (Weekend)")
    elif 9 * 60 + 15 <= minutes < 15 * 60 + 30:
        status, label = "open", "Online"
    else:
        status, label = "closed", "Offline"
    return {"status": status, "label": label, "istTime": ist_now.strftime("%Y-%m-%d %H:%M IST")}


def compute_market_status(now_utc=None):
    """Approximate US equity-market session (pre-market / open / after-hours
    / closed / holiday) from Eastern Time, without external tz packages.
    DST rule: 2nd Sunday of March 02:00 ET -> 1st Sunday of November 02:00 ET.
    Also includes an "india" sub-object with the NSE/BSE session status."""
    from datetime import timedelta, timezone

    now_utc = now_utc or datetime.now(timezone.utc)

    def nth_sunday(year, month, n):
        d = datetime(year, month, 1)
        offset = (6 - d.weekday()) % 7  # weekday(): Mon=0..Sun=6
        first_sunday = d + timedelta(days=offset)
        return first_sunday + timedelta(days=7 * (n - 1))

    year = now_utc.year
    dst_start = nth_sunday(year, 3, 2) + timedelta(hours=7)   # 2am ET = 7am UTC (EST)
    dst_end = nth_sunday(year, 11, 1) + timedelta(hours=6)    # 2am ET = 6am UTC (EDT)
    is_dst = dst_start <= now_utc.replace(tzinfo=None) < dst_end
    offset_hours = -4 if is_dst else -5
    et_now = now_utc + timedelta(hours=offset_hours)

    US_HOLIDAYS_2026 = {  # NYSE full-day closures (approximate; update yearly)
        "01-01", "01-19", "02-16", "04-03", "05-25", "06-19", "07-03", "09-07", "11-26", "12-25",
    }
    md = et_now.strftime("%m-%d")
    weekday = et_now.weekday()  # Mon=0..Sun=6
    minutes = et_now.hour * 60 + et_now.minute

    if weekday >= 5 or md in US_HOLIDAYS_2026:
        status, label = "closed", "Market Closed" + (" (Holiday)" if md in US_HOLIDAYS_2026 else " (Weekend)")
    elif 4 * 60 <= minutes < 9 * 60 + 30:
        status, label = "pre-market", "Pre-Market"
    elif 9 * 60 + 30 <= minutes < 16 * 60:
        status, label = "open", "Market Open"
    elif 16 * 60 <= minutes < 20 * 60:
        status, label = "after-hours", "After-Hours"
    else:
        status, label = "closed", "Market Closed"

    ist_now = now_utc + timedelta(hours=5, minutes=30)
    return {"status": status, "label": label, "etTime": et_now.strftime("%Y-%m-%d %H:%M ET"),
            "istTime": ist_now.strftime("%Y-%m-%d %H:%M IST"),
            "india": compute_india_market_status(now_utc)}


def http_json(url, retries=3, delay=1.5):
    last_err = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read())
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(delay)
    print(f"  [warn] failed to fetch {url}: {last_err}", file=sys.stderr)
    return None


YAHOO_MIRRORS = ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]


def _fetch_yahoo_chart(ticker, params=""):
    """Try both Yahoo chart-API mirrors (query1 then query2) before giving up."""
    for host in YAHOO_MIRRORS:
        data = http_json(f"https://{host}/v8/finance/chart/{ticker}{params}", retries=2)
        if data and data.get("chart", {}).get("result"):
            return data
    return None


def fetch_nasdaq_quote(ticker):
    """Fallback source: NASDAQ's public (unauthenticated) quote API. Only
    covers US-listed tickers/ADRs, used when both Yahoo mirrors fail."""
    url = f"https://api.nasdaq.com/api/quote/{ticker}/info?assetclass=stocks"
    data = http_json(url, retries=2)
    if not data:
        return None
    try:
        p = data["data"]["primaryData"]
        price = float(str(p["lastSalePrice"]).replace("$", "").replace(",", ""))
        pct = float(str(p["percentageChange"]).replace("%", "").replace(",", ""))
        return {
            "price": price,
            "changePct": pct / 100.0,
            "low52": None,
            "high52": None,
            "currency": "USD",
            "source": "nasdaq",
        }
    except Exception as e:  # noqa: BLE001
        print(f"  [warn] nasdaq parse error for {ticker}: {e}", file=sys.stderr)
        return None


def fetch_yahoo_quote(ticker):
    """Fetch live price + 52w range + % change. Tries Yahoo Finance chart API
    (query1, then query2 mirror) first; falls back to NASDAQ's public quote
    API for US-listed names if both Yahoo mirrors are unreachable; falls
    back further to the last successful disk-cached quote if all live
    sources fail (e.g. offline / rate-limited)."""
    cache_key = f"quote:{ticker}"
    data = _fetch_yahoo_chart(ticker)
    if data:
        try:
            meta = data["chart"]["result"][0]["meta"]
            price = meta.get("regularMarketPrice")
            prev = meta.get("previousClose") or meta.get("chartPreviousClose")
            change_pct = ((price - prev) / prev) if (price and prev) else 0.0
            result = {
                "price": price,
                "changePct": change_pct,
                "low52": meta.get("fiftyTwoWeekLow"),
                "high52": meta.get("fiftyTwoWeekHigh"),
                "currency": meta.get("currency"),
                "source": "yahoo",
            }
            cache_set(cache_key, result)
            return result
        except Exception as e:  # noqa: BLE001
            print(f"  [warn] parse error for {ticker}: {e}", file=sys.stderr)
    # Both Yahoo mirrors failed (rate-limit / outage) - try NASDAQ fallback.
    # Skip for non-US-listed / index / fx pseudo-tickers where it can't work.
    if not ticker.startswith("%") and "=" not in ticker and ticker not in ("EWS",) and ticker not in MACRO_FALLBACK_SKIP:
        fallback = fetch_nasdaq_quote(ticker)
        if fallback:
            print(f"  [info] {ticker}: used NASDAQ fallback (Yahoo unreachable)", file=sys.stderr)
            cache_set(cache_key, fallback)
            return fallback
    cached = cache_get_value(cache_key)
    if cached is not None:
        print(f"  [cache] {ticker}: live sources failed, using last cached quote", file=sys.stderr)
        return {**cached, "stale": True}
    return None


def fetch_history(ticker, range_key="1y", interval="1d"):
    """Fetch historical daily closes for a ticker over the given range.
    Falls back to the last successful disk-cached series if the live
    fetch fails."""
    cache_key = f"hist:{ticker}:{range_key}:{interval}"
    data = _fetch_yahoo_chart(ticker, f"?range={range_key}&interval={interval}")
    if not data:
        cached = cache_get_value(cache_key)
        if cached is not None:
            print(f"  [cache] {ticker} history: live fetch failed, using cached series", file=sys.stderr)
            return [tuple(x) for x in cached]
        return None
    try:
        result = data["chart"]["result"][0]
        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
        series = [(ts, c) for ts, c in zip(timestamps, closes) if c is not None]
        cache_set(cache_key, series)
        return series
    except Exception as e:  # noqa: BLE001
        print(f"  [warn] history parse error for {ticker}: {e}", file=sys.stderr)
        cached = cache_get_value(cache_key)
        if cached is not None:
            return [tuple(x) for x in cached]
        return None



BINANCE_SYMBOLS = {"bitcoin": "BTCUSDT", "ethereum": "ETHUSDT"}


def fetch_crypto_binance(fx_usdinr):
    """Fallback crypto source: Binance public 24hr ticker (no API key needed).
    Used only if CoinGecko is unreachable. Converts USD->INR using the fx
    rate already fetched for stocks so the payload shape matches CoinGecko's."""
    out = {}
    for coin_id, symbol in BINANCE_SYMBOLS.items():
        data = http_json(f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}", retries=2)
        if not data:
            continue
        try:
            usd = float(data["lastPrice"])
            chg = float(data["priceChangePercent"])
            out[coin_id] = {
                "usd": usd,
                "inr": usd * fx_usdinr if fx_usdinr else None,
                "usd_24h_change": chg,
                "inr_24h_change": chg,
            }
        except Exception as e:  # noqa: BLE001
            print(f"  [warn] binance parse error for {symbol}: {e}", file=sys.stderr)
    return out


def fetch_crypto(fx_usdinr=None):
    """Fetch BTC/ETH live price in USD + INR + 24h change from CoinGecko (no
    API key needed). Falls back to Binance's public ticker API if CoinGecko
    is unreachable (e.g. regional rate-limiting/outage), then to the last
    successfully cached quotes if both live sources fail."""
    cache_key = "crypto_quotes"
    url = ("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum"
           "&vs_currencies=usd,inr&include_24hr_change=true")
    data = http_json(url, retries=2)
    if data and data.get("bitcoin") and data.get("ethereum"):
        cache_set(cache_key, data)
        return data
    print("  [info] CoinGecko unreachable - falling back to Binance public API", file=sys.stderr)
    fallback = fetch_crypto_binance(fx_usdinr)
    if fallback and fallback.get("bitcoin") and fallback.get("ethereum"):
        cache_set(cache_key, fallback)
        return fallback
    cached = cache_get_value(cache_key)
    if cached is not None:
        print("  [cache] crypto quotes: live sources failed, using last cached values", file=sys.stderr)
        return cached
    return fallback


def fetch_crypto_history(coin_id, days=365):
    """Fetch ~1y of daily USD closes for a coin from CoinGecko's free
    market_chart endpoint (no API key). Used for sparklines + 52w high/low
    on the crypto ticker cards. Falls back to the last successfully cached
    series if unreachable (e.g. rate-limited)."""
    cache_key = f"cryptohist:{coin_id}:{days}"
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart?vs_currency=usd&days={days}&interval=daily"
    data = http_json(url, retries=2)
    if not data or not data.get("prices"):
        cached = cache_get_value(cache_key)
        if cached is not None:
            print(f"  [cache] {coin_id} history: live fetch failed, using cached series", file=sys.stderr)
            return cached
        return None
    try:
        prices = data["prices"]  # [[ms_timestamp, price], ...]
        dates = [datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d") for ts, _ in prices]
        closes = [round(p, 2) for _, p in prices]
        result = {"dates": dates, "closes": closes, "low52": round(min(closes), 2), "high52": round(max(closes), 2)}
        cache_set(cache_key, result)
        return result
    except Exception as e:  # noqa: BLE001
        print(f"  [warn] crypto history parse error for {coin_id}: {e}", file=sys.stderr)
        cached = cache_get_value(cache_key)
        return cached


def fetch_worldbank_indicator(country, indicator, per_page=20):
    """Fetch a time series for a World Bank Open Data indicator (no API key
    needed). Returns a sorted list of (year:str, value:float) tuples,
    skipping years with no reported value. Falls back to the last
    successfully cached series if the live call fails."""
    cache_key = f"wb:{country}:{indicator}"
    url = f"https://api.worldbank.org/v2/country/{country}/indicator/{indicator}?format=json&per_page={per_page}"
    data = http_json(url, retries=2)
    if not data or len(data) < 2 or not data[1]:
        cached = cache_get_value(cache_key)
        if cached is not None:
            print(f"  [cache] World Bank {indicator}: live fetch failed, using cached series", file=sys.stderr)
            return [tuple(x) for x in cached]
        return []
    rows = [(r["date"], r["value"]) for r in data[1] if r.get("value") is not None]
    rows.sort(key=lambda x: x[0])
    cache_set(cache_key, rows)
    return rows


def fetch_india_macro():
    """India macro-economic backdrop: CPI inflation (YoY %) and nominal vs
    real GDP growth, from the World Bank Open Data public API (no key
    required). World Bank annual data typically lags 1-2 years behind
    present, unlike the live market tickers above."""
    try:
        cpi = fetch_worldbank_indicator("IN", "FP.CPI.TOTL.ZG")
        real_gdp = fetch_worldbank_indicator("IN", "NY.GDP.MKTP.KD.ZG")
        nominal_gdp_lcu = fetch_worldbank_indicator("IN", "NY.GDP.MKTP.CN")
        nominal_growth = []
        for i in range(1, len(nominal_gdp_lcu)):
            y0, v0 = nominal_gdp_lcu[i - 1]
            y1, v1 = nominal_gdp_lcu[i]
            if v0:
                nominal_growth.append((y1, (v1 - v0) / v0 * 100))
        if not (cpi and real_gdp and nominal_growth):
            return None
        real_map, nominal_map = dict(real_gdp), dict(nominal_growth)
        years = sorted(set(real_map) & set(nominal_map))[-10:]
        latest_cpi_year, latest_cpi_val = cpi[-1]
        latest_real_year, latest_real_val = real_gdp[-1]
        return {
            "inflation": {"latestYear": latest_cpi_year, "latestPct": round(latest_cpi_val, 2),
                          "years": [y for y, _ in cpi[-10:]], "values": [round(v, 2) for _, v in cpi[-10:]]},
            "gdp": {"years": years, "real": [round(real_map[y], 2) for y in years],
                    "nominal": [round(nominal_map[y], 2) for y in years],
                    "latestYear": latest_real_year, "latestRealPct": round(latest_real_val, 2),
                    "latestNominalPct": round(nominal_map.get(latest_real_year, nominal_growth[-1][1]), 2)},
            "source": "World Bank Open Data (FP.CPI.TOTL.ZG, NY.GDP.MKTP.KD.ZG, NY.GDP.MKTP.CN) — annual data, lags 1-2 years",
        }
    except Exception as e:  # noqa: BLE001
        print(f"  [warn] India macro (World Bank) fetch failed: {e}", file=sys.stderr)
        return None


def get_cell(ws, coord):
    return ws[coord].value


def safe_num(v, default=0.0):
    try:
        if v is None or v == "N/A" or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def load_workbook_data():
    print("Reading workbook (cached formula values as fallback)...")
    wb = openpyxl.load_workbook(XLSX_PATH, data_only=True)
    savings = wb["Savings"]
    wealth = wb["Wealth Projection"]
    fixed = wb["Fixed Expenses"]
    sb = wb["Husband_Expenses"]
    jb = wb["Wife_Expenses"]
    return wb, savings, wealth, fixed, sb, jb


def main():
    if not os.path.exists(XLSX_PATH):
        print(f"ERROR: {XLSX_PATH} not found.")
        sys.exit(1)

    wb, savings, wealth, fixed, sb, jb = load_workbook_data()

    # ---------------- Live market data ----------------
    print("Fetching live FX (USD/INR)...")
    fx_quote = fetch_yahoo_quote("INR=X")
    usdinr = fx_quote["price"] if fx_quote and fx_quote.get("price") else safe_num(get_cell(savings, FX_CELL), 94.5)
    print(f"  USD/INR = {usdinr}")

    print("Fetching live stock/ETF prices from Yahoo Finance (parallelized)...")
    live_prices = {}
    tick_items = [(row, ticker) for row, (ticker, _, _) in HOLDING_ROWS.items()]

    def _fetch_ticker_quote(item):
        row, ticker = item
        return ticker, fetch_yahoo_quote(ticker)

    for (row, ticker), (_, q) in zip(tick_items, parallel_map(tick_items, _fetch_ticker_quote, max_workers=8)):
        price_cell = HOLDING_ROWS[row][2]
        if q and q.get("price"):
            live_prices[row] = q
            print(f"  {ticker:8s} -> {q['price']}")
        else:
            fallback = safe_num(get_cell(savings, price_cell))
            live_prices[row] = {"price": fallback, "changePct": 0, "low52": None, "high52": None}
            print(f"  {ticker:8s} -> fallback cached value {fallback}")

    print("Fetching live crypto prices from CoinGecko (Binance fallback)...")
    crypto_live = fetch_crypto(fx_usdinr=usdinr)
    btc = crypto_live.get("bitcoin", {})
    eth = crypto_live.get("ethereum", {})
    btc_usd = btc.get("usd") or safe_num(get_cell(savings, "B88"), 0)
    eth_usd = eth.get("usd") or safe_num(get_cell(savings, "B89"), 0)
    btc_chg = btc.get("usd_24h_change", 0) / 100.0
    eth_chg = eth.get("usd_24h_change", 0) / 100.0

    print("Fetching 1y crypto history for sparklines + 52w range (parallelized)...")
    btc_history, eth_history = parallel_map(["bitcoin", "ethereum"], fetch_crypto_history, max_workers=2)

    # ---------------- Stock holdings ----------------
    stocks = []
    total_foreign_equity_value = 0.0
    for row, (ticker, qty_cell, price_cell) in HOLDING_ROWS.items():
        qty = safe_num(get_cell(savings, qty_cell))
        quote = live_prices.get(row, {"price": 0, "changePct": 0})
        price_usd = quote["price"] or 0
        value_inr = qty * price_usd * usdinr
        total_foreign_equity_value += value_inr
        stocks.append({
            "ticker": ticker,
            "qty": qty,
            "priceUsd": price_usd,
            "changePct": quote.get("changePct", 0),
            "low52": quote.get("low52"),
            "high52": quote.get("high52"),
            "valueInr": value_inr,
        })
    # non-priced wallets that are already USD-denominated cash/dividends
    ind_money_usd = safe_num(get_cell(savings, "E53"))
    vested_usd = safe_num(get_cell(savings, "E54"))
    ind_money_inr = ind_money_usd * usdinr
    vested_inr = vested_usd * usdinr
    total_foreign_equity_value += ind_money_inr + vested_inr
    stocks = sorted(stocks, key=lambda s: s["valueInr"], reverse=True)

    # NOTE: deliberately no write-back to the Savings sheet's B64:B90 range.
    # Those are Excel's native "Stock"/"Currency" linked-data-type cells
    # (refreshed live by Excel itself via Data > Refresh All when online);
    # overwriting them with plain numbers via openpyxl would strip the
    # data-type binding and break that feature for the user permanently.


    # ---------------- Market status + analyst/dividend/earnings intel ----------------
    print("Computing market session status...")
    market_status = compute_market_status()

    print("Fetching global market indicators (indices, DXY, sector ETFs, parallelized)...")
    macro = []
    macro_history_payload = {}

    def _fetch_macro_item(item):
        sym, (yticker, name) = item
        q = fetch_yahoo_quote(yticker)
        h = fetch_history(yticker, "1y", "1d")
        return sym, name, q, h

    for sym, name, q, h in parallel_map(list(MACRO_TICKERS.items()), _fetch_macro_item, max_workers=8):
        if q and q.get("price") is not None:
            macro.append({"ticker": sym, "name": name, "price": q["price"], "changePct": q.get("changePct", 0),
                          "low52": q.get("low52"), "high52": q.get("high52")})
            print(f"  {sym:10s} -> {q['price']}")
        else:
            print(f"  {sym:10s} -> unavailable")
        if h:
            h_dates = [datetime.fromtimestamp(ts).strftime("%Y-%m-%d") for ts, _ in h]
            h_closes = [round(c, 2) for _, c in h]
            macro_history_payload[sym] = {
                "dates": h_dates, "closes": h_closes,
                "low52": round(min(h_closes), 2) if h_closes else None,
                "high52": round(max(h_closes), 2) if h_closes else None,
            }

    print("Fetching India macro-economic indicators (World Bank Open Data)...")
    india_macro = fetch_india_macro()
    if india_macro:
        print(f"  CPI inflation (latest {india_macro['inflation']['latestYear']}): {india_macro['inflation']['latestPct']}%")
        print(f"  Real GDP growth (latest {india_macro['gdp']['latestYear']}): {india_macro['gdp']['latestRealPct']}%")
    else:
        print("  [warn] India macro data unavailable this run")

    print("Fetching 1y USD/INR history (for INR depreciation chart)...")
    fx_history_raw = fetch_history("INR=X", "1y", "1d")
    fx_history_payload = {"dates": [], "rates": [], "yoyChangePct": None}
    if fx_history_raw:
        fx_dates = [datetime.fromtimestamp(ts).strftime("%Y-%m-%d") for ts, _ in fx_history_raw]
        fx_rates = [round(v, 3) for _, v in fx_history_raw]
        fx_history_payload = {
            "dates": fx_dates, "rates": fx_rates,
            "yoyChangePct": round((fx_rates[-1] / fx_rates[0] - 1) * 100, 2) if fx_rates and fx_rates[0] else None,
        }

    print("Fetching long-range USD/INR history (for 1-30y depreciation comparison)...")
    fx_depreciation_payload = {"dates": [], "rates": [], "horizons": []}
    fx_long_raw = fetch_history("INR=X", "max", "1mo")
    if fx_long_raw:
        fxl_dates = [datetime.fromtimestamp(ts).strftime("%Y-%m-%d") for ts, _ in fx_long_raw]
        fxl_rates = [round(v, 3) for _, v in fx_long_raw]
        current_rate = fxl_rates[-1]
        current_date = datetime.strptime(fxl_dates[-1], "%Y-%m-%d")
        horizons = []
        for yrs in (1, 2, 3, 4, 5, 10, 15, 20, 25, 30):
            try:
                target = current_date.replace(year=current_date.year - yrs)
            except ValueError:  # Feb 29 in a non-leap target year
                target = current_date.replace(year=current_date.year - yrs, day=28)
            best_idx = None
            for i, d in enumerate(fxl_dates):
                if datetime.strptime(d, "%Y-%m-%d") <= target:
                    best_idx = i
                else:
                    break
            if best_idx is not None and fxl_rates[best_idx]:
                past_rate = fxl_rates[best_idx]
                horizons.append({
                    "years": yrs, "pastDate": fxl_dates[best_idx], "pastRate": past_rate,
                    "currentRate": current_rate, "changePct": round((current_rate / past_rate - 1) * 100, 2),
                })
        fx_depreciation_payload = {"dates": fxl_dates, "rates": fxl_rates, "horizons": horizons}
        print(f"  Long-range history: {fxl_dates[0]} -> {fxl_dates[-1]} ({len(horizons)} horizons available)")

    print("Fetching analyst ratings + dividend + earnings dates for held stocks (parallelized)...")

    def _fetch_stock_intel(s):
        t = s["ticker"]
        return (fetch_nasdaq_analyst_rating(t), fetch_nasdaq_dividends(t), fetch_nasdaq_earnings(t))

    for s, (analyst, dividend, earnings) in zip(stocks, parallel_map(stocks, _fetch_stock_intel, max_workers=8)):
        s["analyst"], s["dividend"], s["earnings"] = analyst, dividend, earnings

    print("Fetching quotes/analyst/dividend/earnings for watchlist (interested + held names, parallelized)...")
    held_ticker_set = {s["ticker"] for s in stocks if s["qty"] > 0}
    watchlist = []
    watchlist_pending = []
    for t, name in WATCHLIST_META.items():
        if t in held_ticker_set:
            held_entry = next(s for s in stocks if s["ticker"] == t)
            watchlist.append({
                "ticker": t, "name": name, "isHeld": True, "isEtf": t in WATCHLIST_ETFS,
                "priceUsd": held_entry["priceUsd"], "changePct": held_entry["changePct"],
                "low52": held_entry["low52"], "high52": held_entry["high52"],
                "analyst": held_entry["analyst"], "dividend": held_entry["dividend"], "earnings": held_entry["earnings"],
            })
        else:
            watchlist_pending.append((t, name))

    def _fetch_watchlist_item(item):
        t, name = item
        q = fetch_yahoo_quote(api_ticker(t))
        analyst = fetch_nasdaq_analyst_rating(t)
        dividend = fetch_nasdaq_dividends(t)
        earnings = fetch_nasdaq_earnings(t)
        return t, name, q, analyst, dividend, earnings

    for t, name, q, analyst, dividend, earnings in parallel_map(watchlist_pending, _fetch_watchlist_item, max_workers=8):
        watchlist.append({
            "ticker": t, "name": name, "isHeld": False, "isEtf": t in WATCHLIST_ETFS,
            "priceUsd": q.get("price") if q else None, "changePct": q.get("changePct") if q else None,
            "low52": q.get("low52") if q else None, "high52": q.get("high52") if q else None,
            "analyst": analyst, "dividend": dividend, "earnings": earnings,
            "unavailable": q is None,
        })

    print("Fetching macro/world economic news headlines...")
    macro_news = fetch_macro_news()

    # ---------------- Crypto holdings ----------------
    btc_qty = safe_num(get_cell(savings, "E56"))
    eth_qty = safe_num(get_cell(savings, "E57"))
    coindcx_inr = safe_num(get_cell(savings, "F58"))
    btc_value_inr = btc_qty * btc_usd * usdinr
    eth_value_inr = eth_qty * eth_usd * usdinr
    crypto = [
        {"symbol": "BTC", "qty": btc_qty, "priceUsd": btc_usd, "changePct": btc_chg, "valueInr": btc_value_inr,
         "low52": btc_history.get("low52") if btc_history else None, "high52": btc_history.get("high52") if btc_history else None},
        {"symbol": "ETH", "qty": eth_qty, "priceUsd": eth_usd, "changePct": eth_chg, "valueInr": eth_value_inr,
         "low52": eth_history.get("low52") if eth_history else None, "high52": eth_history.get("high52") if eth_history else None},
    ]
    crypto_history_payload = {}
    if btc_history:
        crypto_history_payload["BTC"] = {"dates": btc_history["dates"], "closes": btc_history["closes"]}
    if eth_history:
        crypto_history_payload["ETH"] = {"dates": eth_history["dates"], "closes": eth_history["closes"]}
    total_crypto_value = btc_value_inr + eth_value_inr + coindcx_inr

    # ---------------- Commodities (Gold, Silver, Crude Oil) — informational, not held ----------------
    print("Fetching commodities (Gold, Silver, Crude Oil) quotes + 1y history (parallelized)...")
    commodities = []
    commodity_history_payload = {}

    def _fetch_commodity_item(item):
        sym, (yticker, name) = item
        q = fetch_yahoo_quote(yticker)
        h = fetch_history(yticker, "1y", "1d")
        return sym, name, q, h

    for sym, name, q, h in parallel_map(list(COMMODITIES.items()), _fetch_commodity_item, max_workers=4):
        if q and q.get("price") is not None:
            commodities.append({
                "symbol": sym, "name": name, "priceUsd": q["price"], "changePct": q.get("changePct", 0),
                "low52": q.get("low52"), "high52": q.get("high52"),
            })
            print(f"  {sym:8s} -> {q['price']}")
        else:
            print(f"  {sym:8s} -> unavailable")
        if h:
            h_dates = [datetime.fromtimestamp(ts).strftime("%Y-%m-%d") for ts, _ in h]
            h_closes = [round(c, 2) for _, c in h]
            commodity_history_payload[sym] = {"dates": h_dates, "closes": h_closes}

    # ---------------- Other Savings sheet totals ----------------
    emergency_fund = safe_num(get_cell(savings, "F8")) + safe_num(get_cell(savings, "F9"))
    pension_fund = safe_num(get_cell(savings, "F18")) + safe_num(get_cell(savings, "F19"))
    debt_funds = (sum(safe_num(get_cell(savings, f"F{r}")) for r in [3, 4, 5, 6]) +
                  sum(safe_num(get_cell(savings, f"F{r}")) for r in [10, 11, 12, 13, 14, 15]) +
                  safe_num(get_cell(savings, "F21")))
    indian_equity = sum(safe_num(get_cell(savings, f"F{r}")) for r in [23, 24, 25, 26])

    total_networth_husband = (emergency_fund + pension_fund + debt_funds + indian_equity +
                                total_foreign_equity_value + total_crypto_value)
    total_networth_no_pension_emergency = total_networth_husband - emergency_fund - pension_fund

    allocation = {
        "emergency": emergency_fund,
        "pension": pension_fund,
        "debt": debt_funds,
        "indianEquity": indian_equity,
        "foreignEquity": total_foreign_equity_value,
        "crypto": total_crypto_value,
    }

    # ---------------- Wealth Projection sheet (monthly savings + Wife cached corpus) ----------------
    sb_monthly_savings = safe_num(get_cell(wealth, "C9"))       # Husband monthly total savings
    jb_monthly_savings = safe_num(get_cell(wealth, "C17"))      # Wife monthly total savings
    wife_corpus_cached = safe_num(get_cell(wealth, "E12"))    # Wife total saved till today (cached, external link)

    combined_networth_today = total_networth_husband + wife_corpus_cached
    combined_monthly_savings = sb_monthly_savings + jb_monthly_savings

    # ---------------- Income / Expenses ----------------
    # NOTE: Husband_Expenses!D25 and Wife_Expenses!D25 ("Total Utilization") sum BOTH
    # true living expenses AND savings/investment contributions (the "Savings per
    # month" row pulled in from the Wealth Projection sheet) in the same column.
    # Treating that combined total as "expenses" made the household look like it
    # was barely saving when in fact a large chunk of salary was going straight
    # into investments. We split living-expense rows from the savings row below
    # so every downstream number (cash-flow widgets, FI goal, expense-ratio risk
    # check) is measuring the right thing.
    sb_salary = safe_num(get_cell(sb, "B29"))
    sb_expenses_total = safe_num(get_cell(sb, "D25"))  # living expenses + savings/investment rows combined
    sb_leftover = safe_num(get_cell(sb, "B30"))
    jb_salary = safe_num(get_cell(jb, "B30"))
    jb_expenses_total = safe_num(get_cell(jb, "D25"))  # living expenses + savings/investment rows combined
    jb_leftover = safe_num(get_cell(jb, "B31"))

    fixed_expenses_monthly = safe_num(get_cell(fixed, "I2"))

    def cat(ws, label_col, val_col, rows):
        out = []
        for r in rows:
            name = get_cell(ws, f"{label_col}{r}")
            val = safe_num(get_cell(ws, f"{val_col}{r}"))
            if name and val:
                out.append({"name": str(name), "amount": val})
        return out

    # Rows under each sheet's "Savings" section header (Mutual Funds, PPF, NPS,
    # US Equity Investment, MSFT ESOP/ESPP, Crypto) — these are investment
    # contributions, not spending. JB row 16 "Medical Insurance" sits inside
    # her sheet's Savings section but is a genuine expense, so it stays out.
    # Both sheets now roll up their investment contributions into a single
    # "Savings per month" row that pulls the total straight from the Wealth
    # Projection sheet, instead of itemizing each instrument separately.
    SB_SAVINGS_ROWS = [15]
    SB_LIVING_ROWS = [3, 4, 5, 7, 8, 10, 20, 22, 23, 24]
    JB_SAVINGS_ROWS = [13]
    JB_LIVING_ROWS = [3, 4, 5, 6, 7, 8, 10, 11, 17, 18, 19, 20, 22, 23, 24]

    sb_expense_breakdown = cat(sb, "A", "D", SB_LIVING_ROWS)
    sb_savings_breakdown = cat(sb, "A", "D", SB_SAVINGS_ROWS)
    jb_expense_breakdown = cat(jb, "A", "D", JB_LIVING_ROWS)
    jb_savings_breakdown = cat(jb, "A", "D", JB_SAVINGS_ROWS)

    sb_savings_from_sheet = sum(x["amount"] for x in sb_savings_breakdown)
    jb_savings_from_sheet = sum(x["amount"] for x in jb_savings_breakdown)
    sb_living_expenses = sb_expenses_total - sb_savings_from_sheet
    jb_living_expenses = jb_expenses_total - jb_savings_from_sheet

    income = {
        "sb": {"salary": sb_salary, "expenses": sb_living_expenses, "expensesTotal": sb_expenses_total,
               "savingsInvestments": sb_savings_from_sheet, "leftover": sb_leftover,
               "leftoverPct": (sb_leftover / sb_salary) if sb_salary else 0},
        "jb": {"salary": jb_salary, "expenses": jb_living_expenses, "expensesTotal": jb_expenses_total,
               "savingsInvestments": jb_savings_from_sheet, "leftover": jb_leftover,
               "leftoverPct": (jb_leftover / jb_salary) if jb_salary else 0},
        "combined": {
            "salary": sb_salary + jb_salary,
            "expenses": sb_living_expenses + jb_living_expenses,
            "expensesTotal": sb_expenses_total + jb_expenses_total,
            "savingsInvestments": sb_savings_from_sheet + jb_savings_from_sheet,
            "leftover": sb_leftover + jb_leftover,
        },
    }

    # ---------------- Wealth Projections (3 scenarios) ----------------
    weighted_return = (
        (allocation["emergency"] / total_networth_husband) * ASSET_RETURNS["emergency"] +
        (allocation["pension"] / total_networth_husband) * ASSET_RETURNS["pension"] +
        (allocation["debt"] / total_networth_husband) * ASSET_RETURNS["debt"] +
        (allocation["indianEquity"] / total_networth_husband) * ASSET_RETURNS["indian_equity"] +
        (allocation["foreignEquity"] / total_networth_husband) * ASSET_RETURNS["foreign_equity"] +
        (allocation["crypto"] / total_networth_husband) * ASSET_RETURNS["crypto"]
    ) if total_networth_husband else 0.09

    def scenario_1_flat_savings_no_growth(years):
        """Just saving monthly (no investment growth), inflation-adjusted to today's purchasing power."""
        months = years * 12
        nominal = combined_networth_today + combined_monthly_savings * months
        real = nominal / ((1 + INFLATION_RATE) ** years)
        return nominal, real

    def scenario_2_growth_minus_inflation(years):
        """Monthly savings compounding at blended optimistic portfolio return, inflation-adjusted."""
        r_month = weighted_return / 12
        months = years * 12
        fv_lump = combined_networth_today * ((1 + r_month) ** months)
        if r_month > 0:
            fv_annuity = combined_monthly_savings * (((1 + r_month) ** months - 1) / r_month)
        else:
            fv_annuity = combined_monthly_savings * months
        nominal = fv_lump + fv_annuity
        real = nominal / ((1 + INFLATION_RATE) ** years)
        return nominal, real

    def scenario_3_growth_plus_escalating_savings(years):
        """Same growth assumptions as scenario 2, but contribution grows 10% every year vs prior year."""
        r_month = weighted_return / 12
        balance = combined_networth_today
        monthly = combined_monthly_savings
        for y in range(years):
            for _m in range(12):
                balance = balance * (1 + r_month) + monthly
            monthly *= (1 + SAVINGS_GROWTH_YOY)
        nominal = balance
        real = nominal / ((1 + INFLATION_RATE) ** years)
        return nominal, real

    projections = {"years": PROJECTION_YEARS, "scenario1": [], "scenario2": [], "scenario3": []}
    for y in PROJECTION_YEARS:
        n1, r1 = scenario_1_flat_savings_no_growth(y)
        n2, r2 = scenario_2_growth_minus_inflation(y)
        n3, r3 = scenario_3_growth_plus_escalating_savings(y)
        projections["scenario1"].append({"nominal": n1, "real": r1})
        projections["scenario2"].append({"nominal": n2, "real": r2})
        projections["scenario3"].append({"nominal": n3, "real": r3})

    # ---------------- Risk assessment ----------------
    equity_like_pct = (allocation["indianEquity"] + allocation["foreignEquity"] + allocation["crypto"]) / total_networth_husband if total_networth_husband else 0
    crypto_pct = allocation["crypto"] / total_networth_husband if total_networth_husband else 0
    single_stock_msft = next((s for s in stocks if s["ticker"] == "MSFT"), None)
    msft_pct = (single_stock_msft["valueInr"] / total_networth_husband) if (single_stock_msft and total_networth_husband) else 0

    risk_factors = []
    risk_score = 0
    if equity_like_pct > 0.6:
        risk_score += 30
        risk_factors.append(f"High equity/crypto exposure ({equity_like_pct*100:.1f}%) — strong growth potential but higher volatility.")
    if msft_pct > 0.25:
        risk_score += 30
        risk_factors.append(f"Concentration risk: MSFT alone is {msft_pct*100:.1f}% of Husband's tracked portfolio — consider diversifying single-stock exposure.")
    if crypto_pct > 0.05:
        risk_score += 10
        risk_factors.append(f"Crypto allocation is {crypto_pct*100:.1f}% — highly volatile asset class.")
    fx_exposure_pct = allocation["foreignEquity"] / total_networth_husband if total_networth_husband else 0
    if fx_exposure_pct > 0.35:
        risk_score += 15
        risk_factors.append(f"Foreign currency exposure is {fx_exposure_pct*100:.1f}% of Husband's tracked portfolio — sensitive to USD/INR fluctuations.")
    if income["combined"]["expenses"] / income["combined"]["salary"] > 0.85 if income["combined"]["salary"] else False:
        risk_score += 10
        risk_factors.append("Household living-expense ratio is above 85% of income — limited buffer for shocks.")
    if not risk_factors:
        risk_factors.append("Portfolio looks reasonably balanced across asset classes.")
    risk_level = "Low" if risk_score < 25 else ("Moderate" if risk_score < 55 else "High")

    # ---------------- Historical performance (priced holdings) + benchmark + drawdown ----------------
    print("Fetching historical prices for held equities + benchmark (for trend/drawdown/alpha, parallelized)...")
    qty_map = {t: safe_num(get_cell(savings, qty_cell)) for _, (t, qty_cell, _) in HOLDING_ROWS.items()}
    held_tickers = sorted({t for t, q in qty_map.items() if q > 0})
    history_raw = {}
    hist_targets = held_tickers + [BENCHMARK_TICKER]
    hist_results = parallel_map(hist_targets, lambda t: fetch_history(t, "1y", "1d"), max_workers=8)
    for t, h in zip(hist_targets, hist_results[:-1]):
        if h:
            history_raw[t] = h
    benchmark_raw = hist_results[-1]

    # Per-ticker 1y daily history for interactive ticker-card sparklines/52w range
    ticker_history_payload = {}
    for t, raw in history_raw.items():
        dates = [datetime.fromtimestamp(ts).strftime("%Y-%m-%d") for ts, _ in raw]
        closes = [round(c, 2) for _, c in raw]
        ticker_history_payload[t] = {
            "dates": dates,
            "closes": closes,
            "low52": round(min(closes), 2) if closes else None,
            "high52": round(max(closes), 2) if closes else None,
        }

    print("Fetching 1y history for watchlist-only tickers (chart expansion in Watchlist panel, parallelized)...")
    watchlist_history_payload = dict(ticker_history_payload)  # held tickers already have 1y history fetched above
    wl_only_tickers = [t for t in WATCHLIST_META if t not in watchlist_history_payload]
    wl_only_results = parallel_map(wl_only_tickers, lambda t: fetch_history(api_ticker(t), "1y", "1d"), max_workers=8)
    for t, h in zip(wl_only_tickers, wl_only_results):
        if h:
            wh_dates = [datetime.fromtimestamp(ts).strftime("%Y-%m-%d") for ts, _ in h]
            wh_closes = [round(c, 2) for _, c in h]
            watchlist_history_payload[t] = {
                "dates": wh_dates, "closes": wh_closes,
                "low52": round(min(wh_closes), 2) if wh_closes else None,
                "high52": round(max(wh_closes), 2) if wh_closes else None,
            }

    def series_from_raw(raw):
        if not raw:
            return None
        idx = pd.to_datetime([datetime.fromtimestamp(ts) for ts, _ in raw]).normalize()
        vals = [c for _, c in raw]
        return pd.Series(vals, index=idx)

    weighted_series = []
    for t, raw in history_raw.items():
        s = series_from_raw(raw)
        if s is not None:
            weighted_series.append(s * qty_map[t])
    if weighted_series:
        port_df = pd.concat(weighted_series, axis=1).sort_index()
        port_df = port_df.groupby(port_df.index).last().ffill().bfill()
        portfolio_usd_series = port_df.sum(axis=1)
        portfolio_inr_series = portfolio_usd_series * usdinr
    else:
        portfolio_inr_series = pd.Series(dtype=float)

    bench_series = series_from_raw(benchmark_raw)

    if len(portfolio_inr_series) > 1:
        running_max = portfolio_inr_series.cummax()
        drawdown_series = (portfolio_inr_series - running_max) / running_max
    else:
        drawdown_series = pd.Series(dtype=float)

    def pct_return(series, days):
        if series is None or len(series) < 2:
            return None
        d = min(days, len(series) - 1)
        start_v, end_v = series.iloc[-d - 1], series.iloc[-1]
        if not start_v:
            return None
        return (end_v / start_v) - 1

    alpha_by_period = []
    for label, days in [("1M", 21), ("3M", 63), ("6M", 126), ("1Y", 252)]:
        p_ret = pct_return(portfolio_inr_series, days)
        b_ret = pct_return(bench_series, days) if bench_series is not None else None
        if p_ret is not None and b_ret is not None:
            alpha_by_period.append({"period": label, "portfolioReturn": p_ret, "benchmarkReturn": b_ret, "alpha": p_ret - b_ret})

    history_payload = {
        "available": not portfolio_inr_series.empty,
        "dates": [d.strftime("%Y-%m-%d") for d in portfolio_inr_series.index] if not portfolio_inr_series.empty else [],
        "portfolioInr": [round(v, 2) for v in portfolio_inr_series.tolist()] if not portfolio_inr_series.empty else [],
        "benchmarkNormalized": [],
        "drawdownPct": [round(v, 4) for v in drawdown_series.tolist()] if not drawdown_series.empty else [],
        "benchmarkLabel": BENCHMARK_LABEL,
        "note": ("Covers only priced foreign-equity holdings (stocks/ETFs you actually hold), not FDs/PPF/pension "
                 "which have no market price history. Historical USD/INR is approximated using today's live rate "
                 "applied across the whole window."),
    }
    if bench_series is not None and not portfolio_inr_series.empty:
        aligned_bench = bench_series.reindex(portfolio_inr_series.index).ffill().bfill()
        first_bench = aligned_bench.iloc[0] if len(aligned_bench) else None
        norm_factor = (portfolio_inr_series.iloc[0] / first_bench) if first_bench else 1
        history_payload["benchmarkNormalized"] = [round(v * norm_factor, 2) for v in aligned_bench.tolist()]

    # ---------------- Sector / geography exposure (treemap) ----------------
    treemap = []
    for s in stocks:
        if s["valueInr"] > 0:
            meta = TICKER_META.get(s["ticker"], {"sector": "Other", "geo": "Other"})
            treemap.append({"ticker": s["ticker"], "value": s["valueInr"], "sector": meta["sector"], "geo": meta["geo"]})

    # ---------------- Risk vs return (bubble) ----------------
    ASSET_LABELS = [
        ("emergency", "Emergency Fund", "emergency"),
        ("pension", "Pension Fund", "pension"),
        ("debt", "Debt Funds", "debt"),
        ("indianEquity", "Indian Equity", "indian_equity"),
        ("foreignEquity", "Foreign Equity", "foreign_equity"),
        ("crypto", "Crypto", "crypto"),
    ]
    risk_return_bubble = [
        {"label": label, "riskPct": ASSET_VOLATILITY[rkey] * 100, "returnPct": ASSET_RETURNS[rkey] * 100, "weight": allocation[akey]}
        for akey, label, rkey in ASSET_LABELS
    ]

    # ---------------- Portfolio drift vs target ----------------
    drift = []
    for akey, label, _ in ASSET_LABELS:
        current_pct = (allocation[akey] / total_networth_husband) if total_networth_husband else 0
        target_pct = TARGET_ALLOCATION[akey]
        drift.append({"label": label, "current": current_pct, "target": target_pct, "driftPts": (current_pct - target_pct) * 100})

    # ---------------- Goals (Financial Independence / 25x rule) ----------------
    annual_expenses_combined = income["combined"]["expenses"] * 12
    fi_target = annual_expenses_combined * 25
    fi_progress = (combined_networth_today / fi_target) if fi_target else 0
    goals = [{
        "name": "Financial Independence (25x annual expenses)",
        "target": fi_target,
        "current": combined_networth_today,
        "progressPct": min(fi_progress, 1.5),
    }]

    # ---------------- Contributions forecast (next 12 months) ----------------
    today = datetime.now()
    y0, m0 = today.year, today.month
    months_labels = []
    for i in range(12):
        mm = (m0 - 1 + i) % 12 + 1
        yy = y0 + (m0 - 1 + i) // 12
        months_labels.append(f"{calendar.month_abbr[mm]} {yy}")
    contributions_forecast = {
        "months": months_labels,
        "sb": [round(sb_monthly_savings, 2)] * 12,
        "jb": [round(jb_monthly_savings, 2)] * 12,
    }

    # ---------------- Smart alerts ----------------
    alerts = []
    for d in drift:
        if abs(d["driftPts"]) >= 5:
            sev = "high" if abs(d["driftPts"]) >= 10 else "medium"
            alerts.append({"severity": sev, "message": f"{d['label']} is {d['driftPts']:+.1f} pts vs target ({d['current']*100:.1f}% vs {d['target']*100:.1f}%) — rebalancing suggested."})
    if msft_pct > 0.25:
        alerts.append({"severity": "high", "message": f"Concentration risk: MSFT is {msft_pct*100:.1f}% of Husband's tracked portfolio."})
    if crypto_pct > 0.10:
        alerts.append({"severity": "medium", "message": f"Crypto allocation elevated at {crypto_pct*100:.1f}% of Husband's tracked portfolio."})
    if income["combined"]["expenses"] and (emergency_fund / income["combined"]["expenses"]) < 3:
        alerts.append({"severity": "high", "message": f"Emergency fund covers only ~{emergency_fund / income['combined']['expenses']:.1f} months of living expenses (below the 3-month minimum)."})
    if not alerts:
        alerts.append({"severity": "low", "message": "No urgent rebalancing or concentration alerts — portfolio is within target ranges."})

    # ---------------- Data source labeling (transparency) ----------------
    data_sources = {
        "stocks": "Live — Yahoo Finance public chart API (query1/query2 mirrors, NASDAQ public quote API fallback)",
        "crypto": "Live — CoinGecko public API (Binance public ticker API fallback)",
        "commodities": "Live — Yahoo Finance public chart API (Gold/Silver/Crude Oil futures)",
        "fx": "Live — Yahoo Finance (USD/INR)",
        "emergencyFund": "Excel — Savings sheet (manual entry)",
        "pensionFund": "Excel — Savings sheet (manual entry)",
        "debtFunds": "Excel — Savings sheet (manual entry)",
        "indianEquity": "Excel — Savings sheet (manual entry)",
        "wifeCorpus": "Excel — Wealth Projection sheet (manual entry)",
        "wifeExpenses": "Excel — Wife_Expenses sheet (manual entry)",
        "analystRatings": "Live — NASDAQ public analyst-ratings API",
        "dividendDates": "Live — NASDAQ public dividends API",
        "earningsDates": "Live — NASDAQ public earnings-forecast/earnings-surprise API",
        "macroNews": "Live — Google News public RSS search (per-region economic headlines)",
        "marketStatus": "Computed — US Eastern Time session rules (pre-market/open/after-hours/closed), approximate holiday calendar",
        "globalIndicators": "Live — Yahoo Finance public chart API (indices, DXY, sector ETFs)",
        "indiaMacro": "Live — World Bank Open Data public API (CPI inflation, GDP growth) — annual data, lags 1-2 years",
    }

    # ---------------- Insights ----------------
    months_emergency_coverage = (emergency_fund / income["combined"]["expenses"]) if income["combined"]["expenses"] else 0

    insights = []
    insights.append(f"Combined household net worth is ~₹{combined_networth_today:,.0f}, growing by ~₹{combined_monthly_savings:,.0f}/month.")
    if msft_pct > 0.25:
        insights.append(f"MSFT alone is {msft_pct*100:.1f}% of Husband's tracked portfolio (foreign equity overall is {allocation['foreignEquity']/total_networth_husband*100:.1f}%) — mostly ESPP/ESOP grants. Consider redirecting new contributions into diversified index funds (VOO/QQQ) until MSFT drifts closer to its {TARGET_ALLOCATION['foreignEquity']*100:.0f}% target.")
    else:
        insights.append(f"Foreign equity is {allocation['foreignEquity']/total_networth_husband*100:.1f}% of Husband's tracked portfolio, mostly MSFT stock/ESPP/ESOP.")
    savings_rate = combined_monthly_savings / income["combined"]["salary"] if income["combined"]["salary"] else 0
    insights.append(f"Household savings rate is {savings_rate*100:.1f}% of combined income — {'excellent' if savings_rate > 0.4 else 'good' if savings_rate > 0.25 else 'room to improve'}.")
    insights.append(f"At a blended optimistic portfolio return of {weighted_return*100:.1f}% (vs {INFLATION_RATE*100:.0f}% inflation), disciplined investing plus a 10% YoY savings step-up could grow real net worth to ~₹{projections['scenario3'][-1]['real']:,.0f} in {PROJECTION_YEARS[-1]} years (today's money).")
    if crypto_pct < 0.02:
        insights.append("Crypto allocation is minimal — acceptable for a conservative risk profile, optional to increase for higher growth potential.")
    insights.append(f"Emergency fund covers ~{months_emergency_coverage:.1f} months of household living expenses — {'consider topping up toward the standard 6-month cushion.' if months_emergency_coverage < 6 else 'a healthy buffer at or above the standard 6-month guideline.'}")


    payload = {
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "fx": {"usdinr": usdinr},
        "stocks": stocks,
        "crypto": crypto,
        "commodities": commodities,
        "wallets": {"indMoneyInr": ind_money_inr, "vestedInr": vested_inr, "coinDcxInr": coindcx_inr},
        "allocation": allocation,
        "netWorth": {
            "husband": total_networth_husband,
            "husbandExPensionEmergency": total_networth_no_pension_emergency,
            "wifeCached": wife_corpus_cached,
            "combined": combined_networth_today,
        },
        "monthlySavings": {"sb": sb_monthly_savings, "jb": jb_monthly_savings, "combined": combined_monthly_savings},
        "income": income,
        "expenseBreakdown": {"sb": sb_expense_breakdown, "sbSavings": sb_savings_breakdown,
                             "jb": jb_expense_breakdown, "jbSavings": jb_savings_breakdown,
                             "fixedMonthly": fixed_expenses_monthly},
        "assumptions": {"inflation": INFLATION_RATE, "savingsGrowthYoY": SAVINGS_GROWTH_YOY,
                         "blendedPortfolioReturn": weighted_return, "assetReturns": ASSET_RETURNS},
        "projections": projections,
        "risk": {"score": min(risk_score, 100), "level": risk_level, "factors": risk_factors},
        "insights": insights,
        "history": history_payload,
        "tickerHistory": ticker_history_payload,
        "cryptoHistory": crypto_history_payload,
        "commodityHistory": commodity_history_payload,
        "marketStatus": market_status,
        "watchlist": watchlist,
        "watchlistHistory": watchlist_history_payload,
        "macro": macro,
        "macroHistory": macro_history_payload,
        "indiaMacro": india_macro,
        "fxHistory": fx_history_payload,
        "fxDepreciation": fx_depreciation_payload,
        "macroNews": macro_news,
        "alphaByPeriod": alpha_by_period,
        "treemap": treemap,
        "riskReturnBubble": risk_return_bubble,
        "drift": drift,
        "targetAllocation": TARGET_ALLOCATION,
        "goals": goals,
        "contributionsForecast": contributions_forecast,
        "alerts": alerts,
        "dataSources": data_sources,
    }

    with open(OUT_JSON, "w") as f:
        json.dump(payload, f, indent=2)
    with open(OUT_JS, "w") as f:
        f.write("window.DASHBOARD_DATA = ")
        json.dump(payload, f)
        f.write(";\n")

    print(f"\nDone. Wrote {OUT_JS} and {OUT_JSON}")
    print(f"Combined net worth: Rs. {combined_networth_today:,.0f}")
    print(f"Combined monthly savings: Rs. {combined_monthly_savings:,.0f}")
    print(f"Blended portfolio return assumption: {weighted_return*100:.2f}%  |  Risk: {risk_level} ({risk_score}/100)")


if __name__ == "__main__":
    main()
