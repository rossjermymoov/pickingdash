# Picker Performance Dashboard

Live warehouse picking performance dashboard for Cloud9 Fulfilment, powered by the DC36/Helm API.

## What it shows
- Average pick time per picker vs team average (green = faster, red = slower)
- Daily pick volumes per picker (last 14 days)
- Top customers by average pick time
- Scan anomalies — individual scan events over 30 seconds

## Files
- `index.html` — self-contained dashboard (embed in any web page or open directly)
- `process_dashboard.py` — data pipeline: logs in to Helm, fetches all picks + time tracking, outputs JSON
- `dashboard_cache.json` — latest pre-processed data cache

## Refreshing data
Run `python3 process_dashboard.py > dashboard_cache.json` to pull fresh data from the API.
