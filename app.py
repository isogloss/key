import os
import psycopg2
from flask import Flask, request, jsonify
from datetime import datetime, timezone

DATABASE_URL = os.environ.get('DATABASE_URL')
app = Flask(__name__)

def db_connection(): return psycopg2.connect(DATABASE_URL)

@app.route('/redeem', methods=['POST'])
def redeem_key():
    key_from_app = request.form.get('key')
    hwid_from_app = request.form.get('hwid')
    
    if not key_from_app:
        return jsonify({"status": "error", "message": "No key provided."}), 400

    conn = db_connection()
    try:
        with conn.cursor() as cur:
            # THIS IS THE FIX: This query uses the new 'redeemed_hwid' column
            cur.execute('SELECT is_active, expires_at, redeemed_hwid FROM keys WHERE key_string = %s', (key_from_app,))
            key_data = cur.fetchone()

            if not key_data:
                return jsonify({"status": "error", "message": "This key is invalid."}), 403

            is_active, expires_at, stored_hwid = key_data
            
            if not is_active:
                 return jsonify({"status": "error", "message": "This key has been banned."}), 403

            if expires_at and datetime.now(timezone.utc) > expires_at:
                return jsonify({"status": "error", "message": "This key has expired."}), 403
            
            # Record IP and HWID on first use only
            if not stored_hwid and hwid_from_app:
                user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
                # THIS IS THE FIX: This query updates the new columns
                cur.execute(
                    'UPDATE keys SET redeemed_ip = %s, redeemed_hwid = %s WHERE key_string = %s',
                    (user_ip, hwid_from_app, key_from_app)
                )
                conn.commit()

            return jsonify({"status": "success", "message": "Access Granted."}), 200

    except Exception as e:
        print(f"Server error during redemption: {e}")
        return jsonify({"status": "error", "message": "A server error occurred."}), 500
    finally:
        if conn: conn.close()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
