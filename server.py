#!/usr/bin/env python3
import os, json, subprocess, threading, time
from flask import Flask, send_from_directory, jsonify

app = Flask(__name__, static_folder='.')
CACHE_FILE = os.path.join(os.path.dirname(__file__), 'dashboard_cache.json')
REFRESH_INTERVAL = 15 * 60  # 15 minutes in seconds
_pipeline_lock = threading.Lock()

def run_pipeline():
    """Run process_dashboard.py and write cache. Returns (data, error)."""
    with _pipeline_lock:
        try:
            script = os.path.join(os.path.dirname(__file__), 'process_dashboard.py')
            result = subprocess.run(
                ['python3', script],
                capture_output=True, text=True, timeout=90
            )
            if result.returncode != 0:
                return None, result.stderr or 'Pipeline exited with non-zero status'
            raw = result.stdout.strip()
            js = raw.index('{')
            data = json.loads(raw[js:])
            with open(CACHE_FILE, 'w') as f:
                json.dump(data, f)
            return data, None
        except subprocess.TimeoutExpired:
            return None, 'Pipeline timed out after 90s'
        except Exception as e:
            return None, str(e)

def scheduler():
    """Background thread: run pipeline every 15 minutes."""
    print(f"[scheduler] Starting — will refresh every {REFRESH_INTERVAL // 60} minutes")
    while True:
        time.sleep(REFRESH_INTERVAL)
        print(f"[scheduler] Running scheduled refresh at {time.strftime('%H:%M:%S')}")
        data, err = run_pipeline()
        if err:
            print(f"[scheduler] Error: {err}")
        else:
            print(f"[scheduler] Done — updated: {data.get('last_updated','?')}")

# Start background scheduler as a daemon thread
_scheduler_thread = threading.Thread(target=scheduler, daemon=True)
_scheduler_thread.start()

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/api/data')
def get_data():
    """Return cached data instantly — no pipeline run."""
    try:
        with open(CACHE_FILE) as f:
            return jsonify(json.load(f))
    except FileNotFoundError:
        return jsonify({'error': 'No cache yet — click Refresh to fetch data'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/refresh', methods=['POST'])
def refresh():
    """Manually trigger pipeline and return fresh data."""
    data, err = run_pipeline()
    if err:
        return jsonify({'error': err}), 500
    return jsonify(data)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
