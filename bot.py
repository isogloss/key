import os
import sqlite3
import uuid
import discord
from discord import app_commands
from datetime import datetime
import sys

# --- Configuration ---
script_dir = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(script_dir, 'keys.db')
SCHEMA = os.path.join(script_dir, 'schema.sql')

BOT_TOKEN = os.environ.get('DISCORD_BOT_TOKEN') 
SERVER_ID = 1436253746861445178 

# --- Database Functions ---
def db_connection():
    try:
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        print(f"Database connection error: {e}")
        sys.exit(1)

def init_db():
    if not os.path.exists(DATABASE):
        print("Database not found. Initializing...")
        try:
            conn = db_connection()
            with open(SCHEMA, 'r') as f:
                conn.cursor().executescript(f.read())
            conn.commit()
            conn.close()
            print("Database initialized successfully.")
        except Exception as e:
            print(f"FATAL ERROR during DB init: {e}")
            sys.exit(1)

# --- Nuke Confirmation View ---
class NukeConfirmationView(discord.ui.View):
    def __init__(self, author_id):
        super().__init__(timeout=30.0) # View times out after 30 seconds
        self.author_id = author_id
        self.nuked = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("You are not authorized to confirm this action.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="CONFIRM NUKE", style=discord.ButtonStyle.danger, custom_id="confirm_nuke_all")
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        conn = db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM keys')
            deleted_count = cursor.rowcount
            conn.commit()
            self.nuked = True

            for item in self.children:
                item.disabled = True
            
            embed = discord.Embed(title="☢️ NUKE COMPLETE ☢️", color=discord.Color.dark_red())
            embed.description = f"**Success! All {deleted_count} keys have been permanently deleted.**"
            await interaction.response.edit_message(embed=embed, view=self)
        except Exception as e:
            print(f"Error during /nuke confirmation: {e}")
            embed = discord.Embed(title="Nuke Failed", description="An error occurred. Check the bot's console.", color=discord.Color.orange())
            await interaction.response.edit_message(embed=embed, view=self)
        finally:
            if conn: conn.close()
    
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="cancel_nuke_all")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        embed = discord.Embed(title="Nuke Cancelled", description="The operation was cancelled. No keys were deleted.", color=discord.Color.green())
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        if not self.nuked:
            for item in self.children:
                item.disabled = True
            
            # Need to get the original message to edit it on timeout
            message = await self.message
            if message:
                embed = discord.Embed(title="Nuke Timed Out", description="You did not respond in time. The nuke was cancelled.", color=discord.Color.light_grey())
                await message.edit(embed=embed, view=self)

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
        print('Bot is ready and commands are synced.')
        print('------')

client = KeyBot()

# --- Bot Commands ---
# (generate, list, info, and ban commands remain unchanged)
@client.tree.command(name="generate", description="Generate a new access key.")
async def generate(interaction: discord.Interaction):
    new_key = f"KEY-{str(uuid.uuid4()).upper()}"
    conn = db_connection()
    try:
        conn.execute('INSERT INTO keys (key_string) VALUES (?)', (new_key,))
        conn.commit()
        await interaction.response.send_message(f"✅ **Key Generated:** `{new_key}`", ephemeral=True)
    finally:
        if conn: conn.close()

@client.tree.command(name="list", description="List all keys and their status.")
async def list_keys(interaction: discord.Interaction):
    conn = db_connection()
    try:
        keys = conn.execute('SELECT key_string, is_active, redeemed_by FROM keys ORDER BY id').fetchall()
        if not keys:
            await interaction.response.send_message("No keys found in the database.", ephemeral=True)
            return

        embed = discord.Embed(title="Key Status List", color=discord.Color.blue())
        message = ""
        for k in keys:
            status_icon = "✅" if k['is_active'] else "❌"
            redeemed_info = f"by {k['redeemed_by']}" if k['redeemed_by'] else ""
            message += f"{status_icon} `{k['key_string']}` {redeemed_info}\n"
        
        embed.description = message
        await interaction.response.send_message(embed=embed, ephemeral=True)
    finally:
        if conn: conn.close()

@client.tree.command(name="info", description="Get information about a specific key.")
@app_commands.describe(key="The key you want to get info about")
async def info(interaction: discord.Interaction, key: str):
    conn = db_connection()
    try:
        key_data = conn.execute('SELECT * FROM keys WHERE key_string = ?', (key,)).fetchone()

        if not key_data:
            await interaction.response.send_message("❌ **Key Not Found:** No key exists with that value.", ephemeral=True)
            return

        if key_data['is_active']:
            embed = discord.Embed(title="Key Information", color=discord.Color.green())
            embed.add_field(name="Status", value="✅ Active / Not Redeemed", inline=False)
        else:
            embed = discord.Embed(title="Key Information", color=discord.Color.red())
            embed.add_field(name="Status", value="❌ Inactive (Redeemed or Banned)", inline=False)
            
            redeemed_by_str = key_data['redeemed_by']
            if redeemed_by_str.startswith("IP:"):
                parts = redeemed_by_str.split(' | Client: ')
                ip_part = parts[0].replace('IP: ', '')
                client_part = parts[1] if len(parts) > 1 else "Unknown"
                embed.add_field(name="Redeemed From IP", value=f"`{ip_part}`", inline=False)
                embed.add_field(name="System / Client Info", value=f"`{client_part}`", inline=False)
            else: 
                embed.add_field(name="Deactivated By", value=f"`{redeemed_by_str}`", inline=False)

            redeemed_time = datetime.strptime(key_data['redeemed_at'].split('.')[0], "%Y-%m-%d %H:%M:%S")
            embed.add_field(name="Deactivated At (UTC)", value=redeemed_time.strftime("%Y-%m-%d %H:%M:%S"), inline=True)

        embed.add_field(name="Key String", value=f"`{key_data['key_string']}`", inline=False)
        created_time = datetime.strptime(key_data['created_at'].split('.')[0], "%Y-%m-%d %H:%M:%S")
        embed.set_footer(text=f"Key created at {created_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")

        await interaction.response.send_message(embed=embed, ephemeral=True)
    finally:
        if conn: conn.close()

@client.tree.command(name="ban", description="Permanently ban a key to revoke all access.")
@app_commands.describe(key="The key you want to ban")
async def ban(interaction: discord.Interaction, key: str):
    conn = db_connection()
    try:
        key_data = conn.execute('SELECT * FROM keys WHERE key_string = ?', (key,)).fetchone()

        if not key_data:
            await interaction.response.send_message(f"❌ **Key Not Found:** No key exists with the value `{key}`.", ephemeral=True)
            return

        if not key_data['is_active']:
            await interaction.response.send_message(f"🟡 **Already Inactive:** This key was already redeemed or banned.", ephemeral=True)
            return
            
        banned_by_info = f"Banned by {interaction.user}"
        conn.execute(
            'UPDATE keys SET is_active = ?, redeemed_at = ?, redeemed_by = ? WHERE key_string = ?',
            (False, datetime.utcnow(), banned_by_info, key)
        )
        conn.commit()
        await interaction.response.send_message(f"✅ **Key Banned:** Access has been permanently revoked for `{key}`.", ephemeral=True)
    finally:
        if conn: conn.close()

# --- NEW COMMAND ADDED HERE ---
@client.tree.command(name="nuke", description="[DANGEROUS] Deletes all keys from the database.")
async def nuke(interaction: discord.Interaction):
    """Asks for confirmation before deleting all keys."""
    embed = discord.Embed(title="☢️ NUKE CONFIRMATION ☢️", color=discord.Color.dark_red())
    embed.description = (
        "**WARNING: This is an irreversible action.**\n\n"
        "This will permanently delete **ALL** keys from the database. "
        "Everyone, including current users, will lose access immediately. "
        "This cannot be undone."
    )
    embed.add_field(name="Are you sure you want to proceed?", value="You have 30 seconds to confirm.")
    
    view = NukeConfirmationView(author_id=interaction.user.id)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    # Store the message object on the view so we can edit it on timeout
    view.message = await interaction.original_response()

# --- Run the Bot ---
if __name__ == '__main__':
    if BOT_TOKEN is None:
        print("FATAL: The DISCORD_BOT_TOKEN environment variable is not set.")
    else:
        init_db()
        client.run(BOT_TOKEN)