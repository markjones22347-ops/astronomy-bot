from flask import Flask, request, jsonify
import sqlite3
import hashlib
import os
from functools import wraps

app = Flask(__name__)
API_KEY = "your_secret_api_key_here"  # Change this!

def init_db():
    conn = sqlite3.connect('licenses.db')
    c = conn.cursor()
    # Create banned_hwids table if not exists
    c.execute('''CREATE TABLE IF NOT EXISTS banned_hwids
                 (hwid TEXT PRIMARY KEY, banned_by TEXT, banned_at TEXT, reason TEXT)''')
    conn.commit()
    conn.close()

init_db()

def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        key = request.headers.get('X-API-Key')
        if key and key == API_KEY:
            return f(*args, **kwargs)
        return jsonify({"error": "Invalid or missing API key"}), 401
    return decorated_function

def get_db_connection():
    conn = sqlite3.connect('licenses.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/verify', methods=['POST'])
@require_api_key
def verify_license():
    data = request.json
    key = data.get('key')
    username = data.get('username')
    hwid = data.get('hwid')
    
    if not key or not username:
        return jsonify({"valid": False, "error": "Missing key or username"}), 400
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM licenses WHERE key = ?", (key,))
    result = c.fetchone()
    
    if not result:
        conn.close()
        return jsonify({"valid": False, "error": "Invalid key"})
    
    # Check if HWID is banned
    if hwid:
        c.execute("SELECT reason FROM banned_hwids WHERE hwid = ?", (hwid,))
        ban_result = c.fetchone()
        if ban_result:
            conn.close()
            return jsonify({"valid": False, "error": f"This device is banned. Reason: {ban_result['reason']}"})
    
    # Check if key is already used by someone else
    if result['used'] and result['username'] != username:
        conn.close()
        return jsonify({"valid": False, "error": "Key already used"})
    
    # Check if HWID matches (if already registered)
    if result['used'] and result['hwid'] and result['hwid'] != hwid:
        conn.close()
        return jsonify({"valid": False, "error": "HWID mismatch"})
    
    # Mark key as used
    c.execute("UPDATE licenses SET username = ?, used = 1, hwid = ? WHERE key = ?",
              (username, hwid, key))
    conn.commit()
    conn.close()
    
    return jsonify({"valid": True, "message": "License verified"})

@app.route('/check', methods=['POST'])
@require_api_key
def check_license():
    data = request.json
    key = data.get('key')
    username = data.get('username')
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM licenses WHERE key = ? AND username = ? AND used = 1",
              (key, username))
    result = c.fetchone()
    conn.close()
    
    if result:
        return jsonify({"valid": True})
    return jsonify({"valid": False})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
