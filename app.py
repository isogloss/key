import os
import psycopg2
from flask import Flask, request, jsonify
from datetime import datetime
import requests

# --- Configuration ---
DATABASE_URL = os.environ.get('DATABASE_URL')

app = Flask(__name__)

# --- Database Connection ---
def db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

# --- Initialize the database schema if it doesn't exist ---
def init_db():
    conn = db_connection()
    cur = conn.cursor()
    # Check if the table exists
    cur.execute("SELECT to_regclass('public.keys');")
    table_exists = cur.fetchone()[0]
    
    if not table_exists:
        print("Creating 'keys' table...")
        cur.execute('''
            CREATE TABLE keys (
                id SERIAL PRIMARY KEY,
                key_string TEXT NOT NULL UNIQUE,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                redeemed_at TIMESTAMP,
                redeemed_by TEXT
            );
        ''')
        conn.commit()
        print("Table 'keys' created.")
    else:
        print("Table 'keys' already exists.")
        
    cur.close()
    conn.close()

# --- API Endpoints ---
@app.route('/redeem', methods=['POST'])
def redeem_key():
    key_from_app = request.form.get('key')
    if not key_from_app:
        return jsonify({"status": "error", "message": "No key provided."}), 400

    conn = db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT is_active FROM keys WHERE key_string = %s', (key_from_app,))
            key_data = cur.fetchone()

            if key_data and key_data[0]: # is_active is at index 0
                # The key is valid and active, now update it
                user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
                user_agent = request.headers.get('User-Agent', 'Unknown')
                redeemed_by_info = f"IP: {user_ip} | Client: {user_agent}"
                
                cur.execute(
                    'UPDATE keys SET is_active = FALSE, redeemed_at = %s, redeemed_by = %s WHERE key_string = %s',
                    (datetime.utcnow(), redeemed_by_info, key_from_app)
                )
                conn.commit()
                return jsonify({"status": "success", "message": "Key successfully redeemed."}), 200
            else:
                return jsonify({"status": "error", "message": "This key is invalid or has already been redeemed."}), 403
    except Exception as e:
        print(f"Database error during API redeem: {e}")
        return jsonify({"status": "error", "message": "A server error occurred."}), 500
    finally:
        if conn: conn.close()


@app.route('/check_status', methods=['POST'])
def check_key_status():
    key_to_check = request.form.get('key')
    if not key_to_check:
        return jsonify({"status": "invalid"}), 400

    conn = db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT is_active FROM keys WHERE key_string = %s', (key_to_check,))
            key_data = cur.fetchone()
            if key_data and key_data[0]:
                return jsonify({"status": "valid"}), 200
            else:
                return jsonify({"status": "invalid"}), 403
    finally:
        if conn: conn.close()

# --- Main Run ---
if __name__ == '__main__':
    print("Initializing database...")
    init_db()
    print("Starting Flask application...")
    # The 'app.run' part is not used by gunicorn, but good for local testing
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
