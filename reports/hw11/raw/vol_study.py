"""Daily-move statistics for the HW11 watchlist (real Yahoo data, 1 year). Output: raw/vol_study.json"""
import json, statistics as st, urllib.request, datetime as dt
out = {"fetched": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "range": "1y", "tickers": {}}
for t in ["NVDA", "TSLA", "KO", "JPM"]:
    req = urllib.request.Request(f"https://query1.finance.yahoo.com/v8/finance/chart/{t}?range=1y&interval=1d",
                                 headers={"User-Agent": "Mozilla/5.0"})
    r = json.load(urllib.request.urlopen(req, timeout=30))["chart"]["result"][0]
    c = [x for x in r["indicators"]["quote"][0]["close"] if x is not None]
    mv = [(b - a) / a * 100 for a, b in zip(c, c[1:])]
    a = [abs(m) for m in mv]
    out["tickers"][t] = {"days": len(mv), "stdev_pct": round(st.pstdev(mv), 2),
        "median_abs_pct": round(st.median(a), 2),
        "days_ge_2pct": sum(x >= 2 for x in a), "days_ge_3pct": sum(x >= 3 for x in a),
        "days_ge_4pct": sum(x >= 4 for x in a), "days_ge_5pct": sum(x >= 5 for x in a),
        "days_ge_8pct": sum(x >= 8 for x in a), "max_abs_pct": round(max(a), 2)}
json.dump(out, open("raw/vol_study.json", "w"), indent=2)
print(json.dumps(out, indent=1))
