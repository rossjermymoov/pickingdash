#!/usr/bin/env python3
import json, statistics, requests
from datetime import datetime
from collections import defaultdict

BASE = "https://c9f.myhelm.app/public-api"
PICKERS = {"185": "Edna Lima", "275": "Mark Lewis", "89": "Aderoju Kosoko"}
SESSION = requests.Session()

def fetch(url, token):
    r = SESSION.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=15)
    r.raise_for_status()
    return r.json()

def login():
    r = SESSION.post(
        f"{BASE}/auth/login",
        json={"email": "ross@saas-ecommerce.com", "password": "Nadine32!"},
        timeout=15
    )
    r.raise_for_status()
    return r.json().get("token")

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

    # Fulfilment clients (for scan stats and anomaly context)
    try:
        fc_data = fetch(f"{BASE}/fulfilment_clients", token)
        client_map = {str(c["id"]): c["name"] for c in fc_data.get("data", [])}
    except Exception:
        client_map = {}

    # Build pick_id -> fulfilment client name from pick_details
    # (fulfilment_client_id lives in order_data inside pick_inventories, not the pick header)
    pick_client_map = {}
    for pid, detail in pick_details.items():
        for inv in detail.get("pick_inventories", []):
            fc_id = str(inv.get("order_data", {}).get("fulfilment_client_id") or "")
            if fc_id and fc_id in client_map:
                pick_client_map[pid] = client_map[fc_id]
                break  # one client per pick is enough

    # Scan overview from time tracking (exclude >120s outliers from averages)
    nav_durs  = [int(t["duration"]) for t in all_tt if t["type"] == "LOCATION_SCAN" and int(t["duration"]) <= 120]
    item_durs = [int(t["duration"]) for t in all_tt if t["type"] == "ITEM_SCAN"     and int(t["duration"]) <= 120]
    scan_pickers = sorted({PICKERS[str(t["user_id"])] for t in all_tt if str(t["user_id"]) in PICKERS})
    scan_overview = {
        "nav_avg":    round(statistics.mean(nav_durs),  1) if nav_durs  else 0,
        "nav_med":    round(statistics.median(nav_durs),1) if nav_durs  else 0,
        "pick_avg":   round(statistics.mean(item_durs), 1) if item_durs else 0,
        "pick_med":   round(statistics.median(item_durs),1) if item_durs else 0,
        "total_scans": len(nav_durs) + len(item_durs),
        "scan_pickers": scan_pickers,
    }

    # Client scan stats — join time_tracking events to picks via pick_header_id
    tt_by_pick = defaultdict(list)
    for t in all_tt:
        if t.get("pick_header_id"):
            tt_by_pick[str(t["pick_header_id"])].append(t)

    client_nav  = defaultdict(list)
    client_item = defaultdict(list)
    for pick_id, events in tt_by_pick.items():
        client = pick_client_map.get(pick_id)
        if not client:
            continue
        for t in events:
            dur = int(t["duration"])
            if dur > 120:
                continue
            if t["type"] == "LOCATION_SCAN":
                client_nav[client].append(dur)
            elif t["type"] == "ITEM_SCAN":
                client_item[client].append(dur)

    client_scan_stats = sorted([
        {
            "client":   c,
            "nav_avg":  round(statistics.mean(client_nav[c]),  1) if client_nav[c]  else 0,
            "pick_avg": round(statistics.mean(client_item[c]), 1) if client_item[c] else 0,
            "nav_n":    len(client_nav[c]),
            "pick_n":   len(client_item[c]),
        }
        for c in set(client_nav) | set(client_item)
    ], key=lambda x: x["nav_avg"] + x["pick_avg"], reverse=True)

    # Scan duration distribution
    def bucket(d):
        if d <=  5: return "0-5s"
        if d <= 15: return "5-15s"
        if d <= 30: return "15-30s"
        if d <= 60: return "30-60s"
        return ">60s"

    labels = ["0-5s","5-15s","15-30s","30-60s",">60s"]
    nb, pb = defaultdict(int), defaultdict(int)
    for t in all_tt:
        dur = int(t["duration"])
        if t["type"] == "LOCATION_SCAN": nb[bucket(dur)] += 1
        elif t["type"] == "ITEM_SCAN":   pb[bucket(dur)] += 1
    scan_distribution = {
        "labels": labels,
        "nav":  {l: nb[l] for l in labels},
        "pick": {l: pb[l] for l in labels},
    }

    # Anomalies >30s with client context
    anomalies = sorted([
        {
            "picker":   PICKERS.get(str(t["user_id"]), str(t["user_id"])),
            "client":   pick_client_map.get(str(t.get("pick_header_id","")), "—"),
            "duration": int(t["duration"]),
            "type":     t["type"].replace("_", " "),
            "date":     t["action_date"],
        }
        for t in all_tt if int(t["duration"]) > 30
    ], key=lambda x: x["duration"], reverse=True)[:15]

    print(json.dumps({
        "overall_avg_wave_mins": round(overall_avg / 60, 1),
        "user_stats":        user_stats,
        "picks_per_day":     picks_per_day,
        "scan_overview":     scan_overview,
        "client_scan_stats": client_scan_stats,
        "scan_distribution": scan_distribution,
        "anomalies":         anomalies,
        "total_waves":       len(all_picks),
        "last_updated":      datetime.now().strftime("%d %b %Y %H:%M"),
    }))

main()
