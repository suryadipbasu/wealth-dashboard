#!/usr/bin/env python3
"""
Live Server - Wealth Dashboard
-------------------------------
A tiny local HTTP server that keeps the dashboard's stock-market ticker
tape "live" without needing a paid data feed or a browser CORS proxy.

Why this exists: Yahoo Finance's/NASDAQ's free public APIs don't send
Access-Control-Allow-Origin headers, so a static index.html opened
directly (file://) or from a simple static server cannot poll them from
in-page JavaScript. This script fetches server-side (no CORS problem)
and re-serves the results with permissive CORS headers so dashboard.js
can poll them every ~60 seconds.

Two refresh cadences run in background threads:
  - "tape" (prices + market session status): every 60s
  - "deep" (analyst ratings, dividend/earnings dates, macro news,
    watchlist): every 20 minutes (these don't change minute to minute)

Endpoints:
  GET /api/tape.json    -> live prices + market status
  GET /api/deep.json    -> analyst/dividend/earnings/news/watchlist
  GET /api/status       -> health check + last-updated timestamps

Run:  python live_server.py   (then open index.html as usual)
Stop: Ctrl+C
"""
import json
import os
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import refresh_data as rd

PORT = 8787
TAPE_INTERVAL_SEC = 60
DEEP_INTERVAL_SEC = 20 * 60

STATE_LOCK = threading.Lock()
STATE = {
    "tape": {"generatedAt": None, "marketStatus": None, "items": []},
    "deep": {"generatedAt": None, "watchlist": [], "macroNews": {}, "macro": [], "indiaMacro": None},
}


_HELD_CACHE = {"tickers": None, "mtime": None}


def held_tickers():
    """Tickers actually held (qty > 0 in the Savings sheet), not just tracked.
    Cached and only re-read when the workbook's mtime changes, since this is
    called every ~60s by the tape refresh loop."""
    try:
        mtime = os.path.getmtime(rd.XLSX_PATH)
        if _HELD_CACHE["tickers"] is not None and _HELD_CACHE["mtime"] == mtime:
            return _HELD_CACHE["tickers"]
        _, savings, _, _, _, _ = rd.load_workbook_data()
        tickers = sorted({
            ticker for _, (ticker, qty_cell, _) in rd.HOLDING_ROWS.items()
            if rd.safe_num(rd.get_cell(savings, qty_cell)) > 0
        })
        _HELD_CACHE["tickers"] = tickers
        _HELD_CACHE["mtime"] = mtime
        return tickers
    except Exception:
        return sorted({t for t in rd.TICKER_MAP.values()})



def all_tape_symbols():
    """Unique symbols to tick every 60s: held stocks + watchlist + crypto."""
    syms = set(held_tickers()) | set(rd.WATCHLIST_META.keys())
    return sorted(syms)


def refresh_tape():
    market_status = rd.compute_market_status()
    items = []

    def _fetch_symbol(t):
        q = rd.fetch_yahoo_quote(rd.api_ticker(t))
        if q and q.get("price") is not None:
            return {"ticker": t, "price": q["price"], "changePct": q.get("changePct", 0)}
        return None

    symbols = all_tape_symbols()
    for r in rd.parallel_map(symbols, _fetch_symbol, max_workers=8):
        if r:
            items.append(r)
    # crypto (24/7, no market-status gating)
    crypto_live = rd.fetch_crypto()
    for coin_id, sym in (("bitcoin", "BTC"), ("ethereum", "ETH")):
        c = crypto_live.get(coin_id)
        if c and c.get("usd"):
            items.append({"ticker": sym, "price": c["usd"], "changePct": c.get("usd_24h_change", 0) / 100.0})
    # global macro indicators (indices, DXY, sector ETFs) — commodities
    # (gold/silver/crude oil) are snapshot-only via data.json, not tape-ticked
    def _fetch_macro(item):
        sym, (yticker, name) = item
        q = rd.fetch_yahoo_quote(yticker)
        if q and q.get("price") is not None:
            return {"ticker": sym, "price": q["price"], "changePct": q.get("changePct", 0), "isMacro": True}
        return None

    for r in rd.parallel_map(list(rd.MACRO_TICKERS.items()), _fetch_macro, max_workers=8):
        if r:
            items.append(r)
    with STATE_LOCK:
        STATE["tape"] = {
            "generatedAt": datetime.now().isoformat(timespec="seconds"),
            "marketStatus": market_status,
            "items": items,
        }
    print(f"[tape] refreshed {len(items)} symbols @ {market_status['label']}")


def refresh_deep():
    held_set = held_tickers()

    def _fetch_watchlist_item(item):
        t, name = item
        q = rd.fetch_yahoo_quote(rd.api_ticker(t))
        analyst = rd.fetch_nasdaq_analyst_rating(t)
        dividend = rd.fetch_nasdaq_dividends(t)
        earnings = rd.fetch_nasdaq_earnings(t)
        return {
            "ticker": t, "name": name, "isHeld": t in held_set, "isEtf": t in rd.WATCHLIST_ETFS,
            "priceUsd": q.get("price") if q else None, "changePct": q.get("changePct") if q else None,
            "low52": q.get("low52") if q else None, "high52": q.get("high52") if q else None,
            "analyst": analyst, "dividend": dividend, "earnings": earnings,
            "unavailable": q is None,
        }

    watchlist = list(rd.parallel_map(list(rd.WATCHLIST_META.items()), _fetch_watchlist_item, max_workers=8))
    macro_news = rd.fetch_macro_news()
    india_macro = rd.fetch_india_macro()

    def _fetch_macro_snapshot(item):
        sym, (yticker, name) = item
        q = rd.fetch_yahoo_quote(yticker)
        return {"ticker": sym, "name": name, "price": q.get("price") if q else None,
                "changePct": q.get("changePct") if q else None,
                "low52": q.get("low52") if q else None, "high52": q.get("high52") if q else None}

    macro_snapshot = list(rd.parallel_map(list(rd.MACRO_TICKERS.items()), _fetch_macro_snapshot, max_workers=8))
    with STATE_LOCK:
        STATE["deep"] = {
            "generatedAt": datetime.now().isoformat(timespec="seconds"),
            "watchlist": watchlist,
            "macroNews": macro_news,
            "macro": macro_snapshot,
            "indiaMacro": india_macro,
        }
    print(f"[deep] refreshed {len(watchlist)} watchlist tickers + macro news + {len(macro_snapshot)} global indicators")


def loop(fn, interval, name):
    while True:
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            print(f"[{name}] error: {e}")
        time.sleep(interval)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # keep console clean; background threads already print status

    def _send_json(self, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.end_headers()

    def do_GET(self):
        with STATE_LOCK:
            tape, deep = STATE["tape"], STATE["deep"]
        if self.path.startswith("/api/tape.json"):
            self._send_json(tape)
        elif self.path.startswith("/api/deep.json"):
            self._send_json(deep)
        elif self.path.startswith("/api/status"):
            self._send_json({
                "ok": True,
                "tapeLastUpdated": tape["generatedAt"],
                "deepLastUpdated": deep["generatedAt"],
            })
        else:
            self._send_json({"error": "not found", "endpoints": ["/api/tape.json", "/api/deep.json", "/api/status"]})


def main():
    print(f"Wealth Dashboard live server starting on http://localhost:{PORT}")
    print("Endpoints: /api/tape.json  /api/deep.json  /api/status")
    print("Leave this window open while using the dashboard. Ctrl+C to stop.\n")

    threading.Thread(target=loop, args=(refresh_tape, TAPE_INTERVAL_SEC, "tape"), daemon=True).start()
    threading.Thread(target=loop, args=(refresh_deep, DEEP_INTERVAL_SEC, "deep"), daemon=True).start()

    server = ThreadingHTTPServer(("localhost", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping live server.")


if __name__ == "__main__":
    main()
