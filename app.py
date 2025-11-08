import os
import psycopg2
from flask import Flask, request, jsonify
from datetime import datetime

# --- Configuration ---
DATABASE_URL = os.environ.get('DATABASE_URL')
app = Flask(__name__)

# --- Database Connection ---
def db_connection():
    return psycopg2.connect(DATABASE_URL)

# --- Initialize the database schema ---
def init_db():
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.keys');")
            if cur.fetchone()[0] is None:
                print("Creating 'keys' table with expiration column...")
                cur.execute('''
                    CREATE TABLE keys (
                        id SERIAL PRIMARY KEY,
                        key_string TEXT NOT NULL UNIQUE,
                        is_active BOOLEAN NOT NULL DEFAULT TRUE,
                        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        redeemed_at TIMESTAMP WITH TIME ZONE,
                        redeemed_by TEXT,
                        expires_at TIMESTAMP WITH TIME ZONE
                    );
                ''')
                print("Table 'keys' created.")
            else:
                print("Table 'keys' already exists.")

# --- API Endpoint ---
@app.route('/redeem', methods=['POST'])
def redeem_key():
    key_from_app = request.form.get('key')
    if not key_from_app:
        return jsonify({"status": "error", "message": "No key provided."}), 400

    conn = db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT is_active, expires_at FROM keys WHERE key_string = %s', (key_from_app,))
            key_data = cur.fetchone()

            if not key_data:
                return jsonify({"status": "error", "message": "This key is invalid."}), 403

            is_active, expires_at = key_data
            
            # 1. Check if banned/already redeemed
            if not is_active:
                 return jsonify({"status": "error", "message": "This key has already been redeemed or banned."}), 403

            # 2. Check if expired
            if expires_at and datetime.now(expires_at.tzinfo) > expires_at:
                return jsonify({"status": "error", "message": "This key has expired."}), 403

            # If we get here, the key is valid. Redeem it.
            user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
            user_agent = request.headers.get('User-Agent', 'Unknown')
            redeemed_by_info = f"IP: {user_ip} | Client: {user_agent}"
            
            cur.execute(
                'UPDATE keys SET is_active = FALSE, redeemed_at = %s, redeemed_by = %s WHERE key_string = %s',
                (datetime.now(expires_at.tzinfo if expires_at else None), redeemed_by_info, key_from_app)
            )
            conn.commit()
            return jsonify({"status": "success", "message": "Key successfully redeemed."}), 200

    except Exception as e:
        print(f"Database error during API redeem: {e}")
        return jsonify({"status": "error", "message": "A server error occurred."}), 500
    finally:
        if conn: conn.close()

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
