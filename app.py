import os
import psycopg2
from flask import Flask, request, jsonify
from datetime import datetime, timezone

# --- Configuration ---
DATABASE_URL = os.environ.get('DATABASE_URL')
app = Flask(__name__)

# --- Database Connection ---
def db_connection():
    return psycopg2.connect(DATABASE_URL)

# --- API Endpoint ---
@app.route('/redeem', methods=['POST'])
def redeem_key():
    key_from_app = request.form.get('key')
    if not key_from_app:
        return jsonify({"status": "error", "message": "No key provided."}), 400

    conn = db_connection()
    try:
        with conn.cursor() as cur:
            # Get the key's status, expiration, and if it's been redeemed before
            cur.execute('SELECT is_active, expires_at, redeemed_at, redeemed_by FROM keys WHERE key_string = %s', (key_from_app,))
            key_data = cur.fetchone()

            if not key_data:
                return jsonify({"status": "error", "message": "This key is invalid."}), 403

            is_active, expires_at, first_redeemed_at, first_redeemed_by = key_data
            
            # 1. Check if the key has been manually banned by an admin
            if not is_active:
                 return jsonify({"status": "error", "message": "This key has been banned."}), 403

            # 2. Check if the key's time has run out
            if expires_at and datetime.now(timezone.utc) > expires_at:
                return jsonify({"status": "error", "message": "This key has expired."}), 403

            # SUCCESS! The key is valid.
            
            # We can log the very first time it was used, but we will NOT deactivate it.
            if not first_redeemed_at:
                user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
                user_agent = request.headers.get('User-Agent', 'Unknown')
                redeemed_by_info = f"IP: {user_ip} | Client: {user_agent}"
                
                cur.execute(
                    'UPDATE keys SET redeemed_at = %s, redeemed_by = %s WHERE key_string = %s',
                    (datetime.now(timezone.utc), redeemed_by_info, key_from_app)
                )
                conn.commit()

            return jsonify({"status": "success", "message": "Access Granted."}), 200

    except Exception as e:
        print(f"Database error during API redeem: {e}")
        return jsonify({"status": "error", "message": "A server error occurred."}), 500
    finally:
        if conn: conn.close()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
