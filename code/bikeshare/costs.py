"""
DATA-260 Homework 7 - Part 4: the reference cost model, used ONLY to check the agent (it is never shown to the model).

Rates are the Bay Wheels prices on the pricing page (https://www.lyft.com/bikes/bay-wheels/pricing). The page is a five-column table
(Single ride, Day pass, Month pass, Lyft Bike, Lyft Pink) whose text flattens to five values per row, so the Month-pass values are the 3rd:
    pay per use :  classic  $1.00 unlock + $0.19/min          ebike  $1.00 unlock + $0.49/min
    Month pass  :  $29/month; classic 45 min free, then $0.17/min;   ebike free unlock + $0.17/min
Assumptions (the page does not say): minutes are billed fractionally (no rounding up); the membership is bought for every calendar
month from the first to the last trip inclusive.
"""

import csv
import math
from datetime import datetime

RATES = {"unlock": 1.00, "classic_ppu": 0.19, "ebike_ppu": 0.49, "month_fee": 29.0, "member_free_classic_min": 45.0, "member_per_min": 0.17}

# Phrases that must appear in the saved snapshot for the rates above to be considered confirmed by the evidence.
RATE_EVIDENCE = {
    "month_fee": "$29/month",
    "classic_ppu": "$1.00 to unlock, then $0.19/min",
    "ebike_ppu": "$1.00 unlock + $0.49/min",
    "member_classic": "45 min free, then $0.17/min",
    "member_ebike": "Free unlocks + $0.17/min",
}


def confirm_rates(snapshot_text: str) -> dict:
    found = {k: phrase in snapshot_text for k, phrase in RATE_EVIDENCE.items()}
    return {"all_confirmed": all(found.values()), "found": found}


def _ride_costs(rideable_type: str, minutes: float) -> tuple[float, float]:
    if rideable_type == "electric_bike":
        return RATES["unlock"] + RATES["ebike_ppu"] * minutes, RATES["member_per_min"] * minutes
    return (RATES["unlock"] + RATES["classic_ppu"] * minutes,
            max(0.0, minutes - RATES["member_free_classic_min"]) * RATES["member_per_min"])


def reference_costs(csv_path) -> dict:
    rides = []
    with open(csv_path, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            try:
                a, b = datetime.fromisoformat(r["started_at"]), datetime.fromisoformat(r["ended_at"])
            except (ValueError, KeyError):
                continue
            minutes = (b - a).total_seconds() / 60
            ppu, residual = _ride_costs(r.get("rideable_type", ""), minutes)
            rides.append({"start": a, "minutes": minutes, "ppu": ppu, "residual": residual})
    first, last = min(x["start"] for x in rides), max(x["start"] for x in rides)
    months = (last.year - first.year) * 12 + last.month - first.month + 1
    ppu_total = sum(x["ppu"] for x in rides)
    residual = sum(x["residual"] for x in rides)
    fee = RATES["month_fee"] * months
    weeks: dict[str, dict] = {}
    for x in rides:
        w = weeks.setdefault(x["start"].strftime("%Y-%W"), {"rides": 0, "minutes": 0.0, "spend": 0.0})
        w["rides"] += 1
        w["minutes"] += x["minutes"]
        w["spend"] += x["ppu"]
    n = len(rides)
    return {
        "rides": n, "months": months, "first_trip": first.isoformat(sep=" "), "last_trip": last.isoformat(sep=" "),
        "total_minutes": round(sum(x["minutes"] for x in rides), 2),
        "pay_per_use_total": round(ppu_total, 2),
        "membership_fee_total": round(fee, 2), "membership_residual": round(residual, 2),
        "membership_total": round(fee + residual, 2),
        "decision": "Buy Monthly Membership" if fee + residual < ppu_total else "Pay Per Ride/Minute",
        "actual_rides_per_month": round(n / months, 2),
        # rides per month at which pay-per-use spending equals the monthly fee: fee / (average pay-per-use cost per ride)
        "break_even_rides_per_month": round(RATES["month_fee"] / (ppu_total / n), 2) if ppu_total > 0 else math.inf,
        "weeks": [{"week": k, "rides": v["rides"], "avg_duration_min": round(v["minutes"] / v["rides"], 2), "spend": round(v["spend"], 2)}
                  for k, v in sorted(weeks.items())],
    }


def check_result(parsed: dict | None, truth: dict, tolerance: float = 0.03) -> dict:
    """Compare what the agent reported with the reference numbers. Money must be within `tolerance` (relative) or 25 cents."""
    def close(a, b):
        return isinstance(a, (int, float)) and abs(a - b) <= max(0.25, tolerance * abs(b))

    def close_rel(a, b):
        return isinstance(a, (int, float)) and abs(a - b) <= max(0.05, 0.05 * abs(b))

    if not parsed:
        return {"checked": False, "reason": "no parsable result", "all_ok": False}
    costs = parsed.get("costs") or {}
    checks = {
        "decision": parsed.get("decision") == truth["decision"],
        "pay_per_use_total": close(costs.get("pay_per_use_total"), truth["pay_per_use_total"]),
        "membership_total": close(costs.get("membership_total"), truth["membership_total"]),
        "months": costs.get("months") == truth["months"],
        "break_even_rides_per_month": close_rel((parsed.get("break_even") or {}).get("rides_per_month"), truth["break_even_rides_per_month"]),
    }
    return {"checked": True, "checks": checks, "all_ok": all(checks.values()),
            "reference": {k: truth[k] for k in ("decision", "pay_per_use_total", "membership_total", "membership_fee_total", "membership_residual", "months",
                                                  "break_even_rides_per_month")}}
