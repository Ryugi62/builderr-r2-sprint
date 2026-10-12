"""Download the daily bars the live board uses (Yahoo, split/dividend adjusted like
yfinance auto_adjust=True) for the 42-ticker Round 2 fetch universe. Research only —
the agent never touches the network. Output is not committed (data licence)."""
import datetime
import json
import sys
import time
import urllib.request

TICKERS = ["SPY", "QQQ", "NVDA", "MSFT", "AAPL", "META", "AMZN", "GOOGL", "AVGO", "AMD", "MU", "MRVL",
           "NFLX", "TSLA", "PLTR", "ORCL", "CRM", "JPM", "V", "MA", "COST", "LLY", "SMH", "XLK", "XLC",
           "XLY", "XLF", "XLI", "XLE", "XLV", "XLP", "XLU", "XLRE", "DIA", "IWM", "SOXX", "QLD", "SSO",
           "TQQQ", "SOXL", "UPRO", "SPXL"]


def fetch(t, rng="5y"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{t}?range={rng}&interval=1d&events=div%2Csplit"
    d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20))
    d = d["chart"]["result"][0]
    q, adj, off = d["indicators"]["quote"][0], d["indicators"]["adjclose"][0]["adjclose"], d["meta"]["gmtoffset"]
    rows = []
    for i, s in enumerate(d["timestamp"]):
        o, h, l, c, v, a = (q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i], adj[i])
        if None in (o, h, l, c, a) or c <= 0:
            continue
        f = a / c
        day = datetime.datetime.utcfromtimestamp(s + off).strftime("%Y-%m-%d")
        rows.append({"ts": day, "open": o * f, "high": h * f, "low": l * f, "close": a, "volume": v or 0})
    return rows


if __name__ == "__main__":
    out = {}
    for t in TICKERS:
        out[t] = fetch(t)
        time.sleep(0.3)
    json.dump(out, open(sys.argv[1] if len(sys.argv) > 1 else "data/bars5y.json", "w"))
