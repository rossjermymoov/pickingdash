#!/usr/bin/env python3
import json, subprocess, statistics
from datetime import datetime
from collections import defaultdict

BASE = "https://c9f.myhelm.app/public-api"
PICKERS = {"185": "Edna Lima", "275": "Mark Lewis", "89": "Aderoju Kosoko"}

def fetch(url, token):
    r = subprocess.run(
        ["curl", "-s", url, "-H", f"Authorization: Bearer {token}"],
        capture_output=True, text=True, timeout=15
    )
    return json.loads(r.stdout)

def login():
    r = subprocess.run(
        ["curl", "-s", "-X", "POST", f"{BASE}/auth/login",
         "-H", "Content-Type: application/json",
         "-d", '{"email":"ross@saas-ecommerce.com","password":"Nadine32!"}'],
        capture_output=True, text=True, timeout=15
    )
    return json.loads(r.stdout).get("token")

def main():
    token = login()
    if not token:
        print(json.dumps({"error": "Login failed"})); return

    # Fetch all picks (3 pages)
    all_picks = []
    for page in [1, 2, 3]:
        d = fetch(f"{BASE}/picks?page={page}", token)
        all_picks.extend(d.get("data", []))

    # Fetch time tracking (4 pages)
    all_tt = []
    for page in [1, 2, 3, 4]:
        d = fetch(f"{BASE}/logs/time_tracking?page={page}", token)
        all_tt.extend(d.get("data", []))

    # Fetch recent 40 pick details for customer data
    sorted_picks = sorted(all_picks, key=lambda p: p["created_at"], reverse=True)
    pick_details = {}
    for p in sorted_picks[:40]:
        try:
            d = fetch(f"{BASE}/picks/{p['id']}", token)
            if "id" in d:
                pick_details[str(d["id"])] = d
        except: pass

    # Per-pick durations (filter >4hr outliers = forgotten picks)
    pick_dur = {}
    for p in all_picks:
        if p.get("completed_at") and p.get("created_at") and p.get("assigned_to"):
            secs = (datetime.fromisoformat(p["completed_at"]) - datetime.fromisoformat(p["created_at"])).total_seconds()
            if secs <= 14400:
                pick_dur[str(p["id"])] = {
                    "duration_secs": secs,
                    "user_id": str(p["assigned_to"]),
                    "date": p["created_at"][:10],
                }

    # Order counts per wave from pick details
    order_counts = {}
    for pid, detail in pick_details.items():
        invs = detail.get("pick_inventories", [])
        if invs:
            order_counts[pid] = len(invs)

    # User stats
    user_durs = defaultdict(list)
    user_order_mins = defaultdict(list)  # mins per order, where we have detail data
    for pid, pd in pick_dur.items():
        if pd["user_id"] in PICKERS:
            user_durs[pd["user_id"]].append(pd["duration_secs"])
            if pid in order_counts and order_counts[pid] > 0:
                mpo = (pd["duration_secs"] / 60) / order_counts[pid]
                user_order_mins[pd["user_id"]].append(mpo)

    all_durs = [d for dlist in user_durs.values() for d in dlist]
    overall_avg = statistics.mean(all_durs) if all_durs else 0

    user_stats = []
    for uid, durs in user_durs.items():
        avg = statistics.mean(durs)
        mpo_list = user_order_mins.get(uid, [])
        user_stats.append({
            "id": uid,
            "name": PICKERS[uid],
            "total_waves": len(durs),
            "avg_wave_mins": round(avg / 60, 1),
            "avg_secs": round(avg),
            "median_wave_mins": round(statistics.median(durs) / 60, 1),
            "vs_avg_mins": round((avg - overall_avg) / 60, 1),
            "faster": avg < overall_avg,
            "mins_per_order": round(statistics.mean(mpo_list), 2) if mpo_list else None,
            "mpo_sample": len(mpo_list),
        })
    user_stats.sort(key=lambda x: x["mins_per_order"] if x["mins_per_order"] is not None else x["avg_secs"] / 60)

    # Picks per day per user (last 14 days)
    ppd = defaultdict(lambda: defaultdict(int))
    for p in all_picks:
        uid = str(p["assigned_to"]) if p.get("assigned_to") else None
        if uid in PICKERS:
            ppd[p["created_at"][:10]][uid] += 1
    all_dates = sorted(ppd.keys())[-14:]
    picks_per_day = {
        "dates": [d[5:] for d in all_dates],  # MM-DD format
        "series": {name: [ppd[d].get(uid, 0) for d in all_dates]
                   for uid, name in PICKERS.items()}
    }

    # Customer analysis from pick details
    cust_durs = defaultdict(list)
    for pid, detail in pick_details.items():
        if pid not in pick_dur:
            continue
        dur = pick_dur[pid]["duration_secs"]
        companies = set()
        for inv in detail.get("pick_inventories", []):
            od = inv.get("order_data", {})
            co = (od.get("shipping_name_company") or od.get("invoice_name_company") or "").strip()
            if co:
                companies.add(co)
        for co in companies:
            cust_durs[co].append(dur)

    top_customers = sorted(
        [{"company": co, "avg_mins": round(statistics.mean(durs) / 60, 1), "picks": len(durs)}
         for co, durs in cust_durs.items()],
        key=lambda x: x["avg_mins"], reverse=True
    )[:12]

    # Scan anomalies (>30s)
    anomalies = sorted(
        [{"user": PICKERS.get(str(t["user_id"]), str(t["user_id"])),
          "duration": int(t["duration"]),
          "type": t["type"],
          "date": t["action_date"]}
         for t in all_tt if int(t["duration"]) > 30],
        key=lambda x: x["duration"], reverse=True
    )[:10]

    print(json.dumps({
        "overall_avg_wave_mins": round(overall_avg / 60, 1),
        "user_stats": user_stats,
        "picks_per_day": picks_per_day,
        "top_customers": top_customers,
        "anomalies": anomalies,
        "total_waves": len(all_picks),
        "last_updated": datetime.now().strftime("%d %b %Y %H:%M"),
        "tt_limited": len(all_tt) < 200,
    }))

main()
