import os
import psycopg2
import uuid
import discord
from discord import app_commands
from datetime import datetime, timedelta, timezone
import sys

# --- Configuration ---
SERVER_ID = 1436253746861445178 

# Paste your External Database URL and Bot Token directly between the quotes.
DATABASE_URL = "PASTE_YOUR_EXTERNAL_DATABASE_URL_HERE"
BOT_TOKEN = "PASTE_YOUR_SECRET_DISCORD_BOT_TOKEN_HERE"

# --- Database Functions ---
def db_connection():
    return psycopg2.connect(DATABASE_URL)

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
                 # Check if the expires_at column exists
                cur.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name='keys' AND column_name='expires_at'
                """)
                if cur.fetchone() is None:
                    print("Adding 'expires_at' column to existing table...")
                    cur.execute("ALTER TABLE keys ADD COLUMN expires_at TIMESTAMP WITH TIME ZONE;")
                    print("Column added.")
                else:
                    print("Table 'keys' already has expiration column.")


# --- Bot Setup ---
class KeyBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        guild = discord.Object(id=SERVER_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

    async def on_ready(self):
        print(f'Logged in as {self.user} (ID: {self.user.id})')

client = KeyBot()

# --- Bot Commands ---
@client.tree.command(name="generate", description="Generate a new access key.")
@app_commands.describe(duration="The validity period of the key.")
@app_commands.choices(duration=[
    app_commands.Choice(name="Day (24 hours)", value="day"),
    app_commands.Choice(name="Week (7 days)", value="week"),
    app_commands.Choice(name="Lifetime", value="lifetime"),
])
async def generate(interaction: discord.Interaction, duration: app_commands.Choice[str]):
    new_key = f"KEY-{str(uuid.uuid4()).upper()}"
    now = datetime.now(timezone.utc)
    expires_at = None
    duration_text = "Lifetime"

    if duration.value == "day":
        expires_at = now + timedelta(days=1)
        duration_text = "1 Day"
    elif duration.value == "week":
        expires_at = now + timedelta(days=7)
        duration_text = "7 Days"

    conn = db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                'INSERT INTO keys (key_string, expires_at) VALUES (%s, %s)',
                (new_key, expires_at)
            )
            conn.commit()
        await interaction.response.send_message(f"✅ **Key Generated ({duration_text}):** `{new_key}`", ephemeral=True)
    finally:
        if conn: conn.close()

@client.tree.command(name="info", description="Get detailed information about a specific key.")
@app_commands.describe(key="The key you want to get info about")
async def info(interaction: discord.Interaction, key: str):
    conn = db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT key_string, is_active, redeemed_by, redeemed_at, created_at, expires_at FROM keys WHERE key_string = %s',
                (key,)
            )
            key_data = cur.fetchone()

            if not key_data:
                await interaction.response.send_message("❌ **Key Not Found**", ephemeral=True)
                return

            key_string, is_active, redeemed_by, redeemed_at, created_at, expires_at = key_data
            now = datetime.now(timezone.utc)

            is_expired = expires_at and now > expires_at
            
            embed = discord.Embed(title="Key Information", color=discord.Color.blue())
            embed.add_field(name="Key String", value=f"`{key_string}`", inline=False)
            
            status = ""
            if is_active and not is_expired:
                status = "✅ Active"
                embed.color = discord.Color.green()
            elif not is_active:
                status = "❌ Redeemed / Banned"
                embed.color = discord.Color.red()
            elif is_expired:
                status = "⏰ Expired"
                embed.color = discord.Color.orange()

            embed.add_field(name="Status", value=status, inline=True)

            if expires_at:
                embed.add_field(name="Expires At (UTC)", value=expires_at.strftime("%Y-%m-%d %H:%M:%S"), inline=True)
            else:
                embed.add_field(name="Expires", value="Never (Lifetime)", inline=True)

            if redeemed_by:
                if redeemed_by.startswith("IP:"):
                    embed.add_field(name="Redeemed By", value=f"`{redeemed_by}`", inline=False)
                else: # Banned by user
                    embed.add_field(name="Deactivated By", value=redeemed_by, inline=False)
            
            if redeemed_at:
                embed.add_field(name="Redeemed At (UTC)", value=redeemed_at.strftime("%Y-%m-%d %H:%M:%S"), inline=False)
            
            embed.set_footer(text=f"Key created at {created_at.strftime('%Y-%m-%d %H:%M:%S')} UTC")
            await interaction.response.send_message(embed=embed, ephemeral=True)
    finally:
        if conn: conn.close()
        
# Keep the other commands like list, ban, and nuke the same as before...
# (The previous `bot.py` code has them if you need to copy them back)

# --- Run the Bot ---
if __name__ == '__main__':
    if not BOT_TOKEN or "PASTE" in BOT_TOKEN:
        print("FATAL: BOT_TOKEN is not set.")
    elif not DATABASE_URL or "PASTE" in DATABASE_URL:
        print("FATAL: DATABASE_URL is not set.")
    else:
        init_db()
        client.run(BOT_TOKEN)
