import os
import sqlite3
from flask import Flask, request, jsonify
from datetime import datetime
import requests

# --- Configuration ---
script_dir = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(script_dir, 'keys.db')
DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')

app = Flask(__name__)

# --- Database Connection ---
def db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# --- API Endpoints ---
@app.route('/redeem', methods=['POST'])
def redeem_key():
    """
    Handles the INITIAL key activation for an application.
    This now validates the key and records user info without deactivating the key.
    """
    key_from_app = request.form.get('key')
    if not key_from_app:
        return jsonify({"status": "error", "message": "No key provided."}), 400

    conn = db_connection()
    try:
        key_data = conn.execute('SELECT * FROM keys WHERE key_string = ?', (key_from_app,)).fetchone()

        # Check if key exists and is active
        if key_data and key_data['is_active']:
            # --- NEW LOGIC: ONLY RECORD INFO, DON'T DEACTIVATE ---
            # Check if this is the first time the key is being used by an app
            # The 'redeemed_by' field will be empty or won't start with "IP:"
            if not key_data['redeemed_by'] or not key_data['redeemed_by'].startswith("IP:"):
                user_ip = request.remote_addr
                user_agent = request.headers.get('User-Agent', 'Unknown')
                redeemed_by_info = f"IP: {user_ip} | Client: {user_agent}"
                
                # We only UPDATE the info, we DO NOT set is_active to False.
                conn.execute(
                    'UPDATE keys SET redeemed_at = ?, redeemed_by = ? WHERE key_string = ?',
                    (datetime.utcnow(), redeemed_by_info, key_from_app)
                )
                conn.commit()

                # Send a Discord notification for the first activation
                if DISCORD_WEBHOOK_URL:
                    discord_payload = { "content": f"🎉 **First Activation!**\n- **Key:** `{key_from_app}`\n- **From:** `{redeemed_by_info}`" }
                    try:
                        requests.post(DISCORD_WEBHOOK_URL, json=discord_payload, timeout=5)
                    except requests.exceptions.RequestException as e:
                        print(f"Warning: Could not send Discord notification. Error: {e}")
            
            # Key is valid, grant access.
            return jsonify({"status": "success", "message": "Key successfully validated."}), 200
        
        else:
            # This case now covers keys that are invalid OR have been banned.
            return jsonify({"status": "error", "message": "This key is invalid or has been banned."}), 403 # 403 Forbidden

    except sqlite3.Error as e:
        print(f"Database error during API redeem: {e}")
        return jsonify({"status": "error", "message": "A database error occurred on the server."}), 500
    
    finally:
        if conn: conn.close()


@app.route('/check_status', methods=['POST'])
def check_key_status():
    """Checks if a key is still active for the heartbeat check."""
    key_to_check = request.form.get('key')
    if not key_to_check:
        return jsonify({"status": "invalid"}), 400

    conn = db_connection()
    try:
        key_data = conn.execute('SELECT is_active FROM keys WHERE key_string = ?', (key_to_check,)).fetchone()
        if key_data and key_data['is_active']:
            return jsonify({"status": "valid"}), 200
        else:
            # This will fail if the key has been banned.
            return jsonify({"status": "invalid"}), 403
    finally:
        if conn: conn.close()

# --- Main Run ---
if __name__ == '__main__':
    if DISCORD_WEBHOOK_URL is None:
        print("WARNING: DISCORD_WEBHOOK_URL is not set.")
    app.run(host='127.0.0.1', port=5000)