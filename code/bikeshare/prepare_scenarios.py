"""
DATA-260 Homework 7 - Part 4: build the two acceptance datasets from REAL Bay Wheels trip files.

Source: https://s3.amazonaws.com/baywheels-data/  (public monthly trip CSVs, columns unchanged, rows are real trips).
Nothing is invented; rows are only SELECTED, with a fixed seed (9871). The trip files are anonymous, so each scenario
treats its sample as one hypothetical rider's trip history.

  scenario_membership_wins.csv  600 real trips from 2024-06, casual riders, 20 minutes or longer (many/long rides, one month)
  scenario_payperuse_wins.csv   528 real trips: 11 short (2-8 min) classic-bike trips from each of the 48 months 2021-01..2024-12
                                (few, short rides spread over four years)

A provenance file records the source zips (with their SHA-256), the filters and the row counts.

Run from the repo root, inside the venv:   python code/bikeshare/prepare_scenarios.py
"""

import hashlib
import io
import json
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

SEED = 9871
BASE = "https://s3.amazonaws.com/baywheels-data/{ym}-baywheels-tripdata.csv.zip"
# the published 2022-11 file name has a typo ("baywheeels"); everything else follows BASE
URL_OVERRIDES = {"202211": "https://s3.amazonaws.com/baywheels-data/202211-baywheeels-tripdata.csv.zip"}
OUT = Path(__file__).resolve().parent / "data"
COLUMNS = ["ride_id", "rideable_type", "started_at", "ended_at", "start_station_name", "start_station_id",
           "end_station_name", "end_station_id", "start_lat", "start_lng", "end_lat", "end_lng", "member_casual"]


def load_month(ym: str, cache: Path) -> tuple[pd.DataFrame, dict]:
    path = cache / f"{ym}.zip"
    if not path.exists():
        urllib.request.urlretrieve(URL_OVERRIDES.get(ym, BASE.format(ym=ym)), path)
    raw = path.read_bytes()
    z = zipfile.ZipFile(io.BytesIO(raw))
    name = next(n for n in z.namelist() if n.endswith(".csv") and not n.startswith("__MACOSX"))
    df = pd.read_csv(z.open(name), dtype=str)
    df = df[COLUMNS].copy()
    df["_dur"] = (pd.to_datetime(df["ended_at"], format="mixed") - pd.to_datetime(df["started_at"], format="mixed")).dt.total_seconds() / 60
    meta = {"month": ym, "url": URL_OVERRIDES.get(ym, BASE.format(ym=ym)), "zip_sha256": hashlib.sha256(raw).hexdigest(), "zip_bytes": len(raw), "csv_rows": len(df)}
    return df, meta


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    prov = {"built_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "seed": SEED, "sources": [], "scenarios": {}}
    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp)
        df, meta = load_month("202406", cache)
        prov["sources"].append(meta)
        pool = df[(df["member_casual"] == "casual") & (df["_dur"] >= 20) & (df["_dur"] <= 180)]
        pick = pool.sample(n=600, random_state=SEED).sort_values("started_at")
        pick[COLUMNS].to_csv(OUT / "scenario_membership_wins.csv", index=False)
        prov["scenarios"]["membership_wins"] = {
            "file": "scenario_membership_wins.csv", "rows": len(pick), "pool_rows": len(pool),
            "filter": "2024-06, member_casual=casual, 20 <= duration <= 180 min, random sample of 600 (seed 9871)",
            "bike_mix": pick["rideable_type"].value_counts().to_dict()}
        parts = []
        for year in range(2021, 2025):
            for month in range(1, 13):
                ym = f"{year}{month:02d}"
                df, meta = load_month(ym, cache)
                prov["sources"].append(meta)
                pool = df[(df["member_casual"] == "casual") & (df["rideable_type"] == "classic_bike") & (df["_dur"] >= 2) & (df["_dur"] <= 8)]
                parts.append(pool.sample(n=11, random_state=SEED))
                print(ym, "csv rows", meta["csv_rows"], "pool", len(pool), flush=True)
                (cache / f"{ym}.zip").unlink()
        pick = pd.concat(parts).sort_values("started_at")
        pick[COLUMNS].to_csv(OUT / "scenario_payperuse_wins.csv", index=False)
        prov["scenarios"]["payperuse_wins"] = {
            "file": "scenario_payperuse_wins.csv", "rows": len(pick), "months": 48,
            "filter": "each month 2021-01..2024-12: member_casual=casual, rideable_type=classic_bike, 2 <= duration <= 8 min, 11 random trips (seed 9871)",
            "bike_mix": pick["rideable_type"].value_counts().to_dict()}
    for name, sc in prov["scenarios"].items():
        d = pd.read_csv(OUT / sc["file"])
        mins = (pd.to_datetime(d["ended_at"], format="mixed") - pd.to_datetime(d["started_at"], format="mixed")).dt.total_seconds() / 60
        sc["mean_duration_min"] = round(float(mins.mean()), 2)
        sc["first_trip"], sc["last_trip"] = d["started_at"].min(), d["started_at"].max()
        sc["csv_sha256"] = hashlib.sha256((OUT / sc["file"]).read_bytes()).hexdigest()
        print(name, sc["rows"], "rows, mean", sc["mean_duration_min"], "min,", sc["first_trip"], "->", sc["last_trip"])
    (OUT / "scenarios_provenance.json").write_text(json.dumps(prov, indent=2), encoding="utf-8", newline="\n")
    print("wrote", OUT / "scenarios_provenance.json")


if __name__ == "__main__":
    main()
