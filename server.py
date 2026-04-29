#!/usr/bin/env python3
import os, json, subprocess
from flask import Flask, send_from_directory, jsonify

app = Flask(__name__, static_folder='.')
CACHE_FILE = os.path.join(os.path.dirname(__file__), 'dashboard_cache.json')

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/api/data')
def get_data():
    """Return cached data instantly."""
    try:
        with open(CACHE_FILE) as f:
            return jsonify(json.load(f))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/refresh', methods=['POST'])
def refresh():
    """Run the pipeline and update the cache, then return fresh data."""
    try:
        script = os.path.join(os.path.dirname(__file__), 'process_dashboard.py')
        result = subprocess.run(
            ['python3', script],
            capture_output=True, text=True, timeout=90
        )
        if result.returncode != 0:
            return jsonify({'error': result.stderr}), 500
        raw = result.stdout.strip()
        js = raw.index('{')
        data = json.loads(raw[js:])
        with open(CACHE_FILE, 'w') as f:
            json.dump(data, f)
        return jsonify(data)
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Pipeline timed out after 90s'}), 504
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
