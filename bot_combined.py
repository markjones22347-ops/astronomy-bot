import discord
from discord import app_commands
from discord.ext import commands
import sqlite3
import secrets
import string
import os
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

# Load .env file if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Database setup
def init_db():
    conn = sqlite3.connect('licenses.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS licenses
                 (key TEXT PRIMARY KEY, username TEXT, generated_by TEXT, 
                  generated_at TEXT, used BOOLEAN DEFAULT 0)''')
    conn.commit()
    conn.close()

def generate_key():
    return '-'.join([''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4)) for _ in range(4)])

class LicenseBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=discord.Intents.default())
        self.admin_ids = [1484746407700074598, 1482917635417964797]  # Admin Discord IDs
        
    async def setup_hook(self):
        init_db()
        await self.tree.sync()
        
    async def on_ready(self):
        print(f'Bot logged in as {self.user}')

bot = LicenseBot()

# Registration Modal
class RegistrationModal(discord.ui.Modal, title="Register Your License"):
    key_input = discord.ui.TextInput(
        label="License Key",
        placeholder="XXXX-XXXX-XXXX-XXXX",
        required=True,
        max_length=19,
        min_length=19
    )
    
    username_input = discord.ui.TextInput(
        label="Username (for in-game login)",
        placeholder="Enter your username",
        required=True,
        max_length=32
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        key = self.key_input.value.strip().upper()
        username = self.username_input.value.strip()
        
        # Validate key format
        if not key.replace("-", "").isalnum() or len(key.replace("-", "")) != 16:
            await interaction.response.send_message(
                "❌ Invalid key format! Use format: XXXX-XXXX-XXXX-XXXX", 
                ephemeral=True
            )
            return
        
        # Normalize key format
        key = key.replace("-", "")
        key = '-'.join([key[i:i+4] for i in range(0, 16, 4)])
        
        conn = sqlite3.connect('licenses.db')
        c = conn.cursor()
        
        # Check if key exists
        c.execute("SELECT * FROM licenses WHERE key = ?", (key,))
        result = c.fetchone()
        
        if not result:
            conn.close()
            await interaction.response.send_message(
                "❌ Invalid license key! Please check your key and try again.", 
                ephemeral=True
            )
            return
        
        key_id, existing_user, generated_by, generated_at, used = result
        
        # Check if key is already used
        if used:
            if existing_user == username:
                await interaction.response.send_message(
                    f"✅ This key is already registered to you (`{username}`)!\n\n"
                    f"You can now use the client with:\n"
                    f"• Key: `{key}`\n"
                    f"• Username: `{username}`", 
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"❌ This key is already registered to someone else (`{existing_user}`).\n"
                    f"Contact an admin if you believe this is an error.", 
                    ephemeral=True
                )
            conn.close()
            return
        
        # Register the key
        c.execute("UPDATE licenses SET used = 1, username = ? WHERE key = ?", (username, key))
        conn.commit()
        conn.close()
        
        # Success message
        embed = discord.Embed(
            title="✅ License Registered Successfully!",
            color=discord.Color.green()
        )
        embed.add_field(name="License Key", value=f"`{key}`", inline=False)
        embed.add_field(name="Username", value=f"`{username}`", inline=False)
        embed.add_field(
            name="Next Steps", 
            value="You can now launch the Astronomy client and enter these credentials when prompted.",
            inline=False
        )
        embed.set_footer(text="Keep your key safe! Don't share it with others.")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def on_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message(
            f"❌ An error occurred: {str(error)}. Please try again or contact an admin.",
            ephemeral=True
        )

def is_admin(interaction: discord.Interaction) -> bool:
    return interaction.user.id in bot.admin_ids

@bot.tree.command(name="generate", description="Generate license keys (Admin only)")
@app_commands.check(is_admin)
@app_commands.describe(count="Number of keys to generate")
async def generate(interaction: discord.Interaction, count: int = 1):
    conn = sqlite3.connect('licenses.db')
    c = conn.cursor()
    
    keys = []
    for _ in range(count):
        key = generate_key()
        c.execute("INSERT INTO licenses (key, generated_by, generated_at) VALUES (?, ?, ?)",
                  (key, str(interaction.user.id), datetime.now().isoformat()))
        keys.append(key)
    
    conn.commit()
    conn.close()
    
    key_list = '\n'.join(keys)
    await interaction.response.send_message(f"Generated {count} key(s):\n```\n{key_list}\n```", ephemeral=True)

@bot.tree.command(name="delete", description="Delete a license key (Admin only)")
@app_commands.check(is_admin)
@app_commands.describe(key="License key to delete")
async def delete(interaction: discord.Interaction, key: str):
    conn = sqlite3.connect('licenses.db')
    c = conn.cursor()
    c.execute("DELETE FROM licenses WHERE key = ?", (key,))
    conn.commit()
    conn.close()
    await interaction.response.send_message(f"Deleted key: `{key}`", ephemeral=True)

@bot.tree.command(name="show", description="Show all license keys (Admin only)")
@app_commands.check(is_admin)
async def show(interaction: discord.Interaction):
    conn = sqlite3.connect('licenses.db')
    c = conn.cursor()
    c.execute("SELECT key, username, used, generated_at FROM licenses")
    keys = c.fetchall()
    conn.close()
    
    if not keys:
        await interaction.response.send_message("No keys found.", ephemeral=True)
        return
    
    message = "License Keys:\n```\n"
    message += f"{'Key':<20} {'Username':<15} {'Used':<5} {'Generated'}\n"
    message += "-" * 60 + "\n"
    
    for key, username, used, generated_at in keys:
        username = username or "N/A"
        used_str = "Yes" if used else "No"
        message += f"{key:<20} {username:<15} {used_str:<5} {generated_at[:10]}\n"
    
    message += "```"
    
    if len(message) > 2000:
        message = message[:1990] + "...```"
    
    await interaction.response.send_message(message, ephemeral=True)

@bot.tree.command(name="lookup", description="Look up a specific key (Admin only)")
@app_commands.check(is_admin)
@app_commands.describe(key="License key to look up")
async def lookup(interaction: discord.Interaction, key: str):
    conn = sqlite3.connect('licenses.db')
    c = conn.cursor()
    c.execute("SELECT * FROM licenses WHERE key = ?", (key,))
    result = c.fetchone()
    conn.close()
    
    if not result:
        await interaction.response.send_message("Key not found.", ephemeral=True)
        return
    
    key, username, generated_by, generated_at, used = result
    status = "Used" if used else "Available"
    
    embed = discord.Embed(title="License Key Info", color=discord.Color.blue())
    embed.add_field(name="Key", value=f"`{key}`", inline=False)
    embed.add_field(name="Status", value=status, inline=True)
    embed.add_field(name="Username", value=username or "N/A", inline=True)
    embed.add_field(name="Generated", value=generated_at[:19], inline=True)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="users", description="Show all registered users (Admin only)")
@app_commands.check(is_admin)
async def users(interaction: discord.Interaction):
    conn = sqlite3.connect('licenses.db')
    c = conn.cursor()
    c.execute("SELECT username, key, generated_at FROM licenses WHERE used = 1 ORDER BY generated_at DESC")
    results = c.fetchall()
    conn.close()
    
    if not results:
        await interaction.response.send_message("No registered users found.", ephemeral=True)
        return
    
    embed = discord.Embed(title="Registered Users", color=discord.Color.green())
    embed.description = f"Total registered users: **{len(results)}**"
    
    for i, (username, key, date) in enumerate(results[:25]):
        embed.add_field(name=f"{i+1}. {username}", value=f"Key: `{key}`\nDate: {date[:10]}", inline=False)
    
    if len(results) > 25:
        embed.set_footer(text=f"Showing 25 of {len(results)} users")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="revoke", description="Revoke a user's access (Admin only)")
@app_commands.check(is_admin)
@app_commands.describe(username="Username to revoke")
async def revoke(interaction: discord.Interaction, username: str):
    conn = sqlite3.connect('licenses.db')
    c = conn.cursor()
    
    c.execute("SELECT key FROM licenses WHERE username = ? AND used = 1", (username,))
    result = c.fetchone()
    
    if not result:
        conn.close()
        await interaction.response.send_message(f"User `{username}` not found or not active.", ephemeral=True)
        return
    
    key = result[0]
    c.execute("UPDATE licenses SET used = 0, username = NULL WHERE key = ?", (key,))
    conn.commit()
    conn.close()
    
    await interaction.response.send_message(f"✅ Revoked access for `{username}`. Key `{key}` is now available again.", ephemeral=True)

@bot.tree.command(name="stats", description="Show license system statistics (Admin only)")
@app_commands.check(is_admin)
async def stats(interaction: discord.Interaction):
    conn = sqlite3.connect('licenses.db')
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM licenses")
    total_keys = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM licenses WHERE used = 1")
    used_keys = c.fetchone()[0]
    
    conn.close()
    
    embed = discord.Embed(title="License System Statistics", color=discord.Color.purple())
    embed.add_field(name="Total Keys", value=str(total_keys), inline=True)
    embed.add_field(name="Used Keys", value=str(used_keys), inline=True)
    embed.add_field(name="Available Keys", value=str(total_keys - used_keys), inline=True)
    embed.add_field(name="Active Rate", value=f"{(used_keys/total_keys*100):.1f}%" if total_keys > 0 else "0%", inline=True)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="resetkey", description="Reset a key to unused status (Admin only)")
@app_commands.check(is_admin)
@app_commands.describe(key="License key to reset")
async def resetkey(interaction: discord.Interaction, key: str):
    conn = sqlite3.connect('licenses.db')
    c = conn.cursor()
    c.execute("UPDATE licenses SET used = 0, username = NULL WHERE key = ?", (key,))
    conn.commit()
    conn.close()
    
    await interaction.response.send_message(f"🔄 Reset key `{key}` to available status.", ephemeral=True)

@bot.tree.command(name="register", description="Register your license key (Opens registration form)")
async def register(interaction: discord.Interaction):
    # Show the registration modal
    modal = RegistrationModal()
    await interaction.response.send_modal(modal)

# Simple HTTP server for mod verification
class VerificationHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress logs
        pass
        
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({"status": "License server running"}).encode())
    
    def do_POST(self):
        if self.path != '/verify':
            self.send_response(404)
            self.end_headers()
            return
        
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode())
            key = data.get('key', '').upper()
            username = data.get('username', '')
            
            conn = sqlite3.connect('licenses.db')
            c = conn.cursor()
            c.execute("SELECT * FROM licenses WHERE key = ?", (key,))
            result = c.fetchone()
            
            response = {"valid": False}
            
            if not result:
                response["error"] = "Invalid key"
            elif result[4] and result[1] != username:  # used and different username
                response["error"] = "Key already used"
            else:
                # Mark as used
                c.execute("UPDATE licenses SET used = 1, username = ? WHERE key = ?", (username, key))
                conn.commit()
                response = {"valid": True, "message": "License verified"}
            
            conn.close()
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
            
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"valid": False, "error": str(e)}).encode())
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

def run_server(port=10000):
    server = HTTPServer(('0.0.0.0', port), VerificationHandler)
    print(f"Verification server running on port {port}")
    server.serve_forever()

# Run the bot
if __name__ == "__main__":
    TOKEN = os.environ.get("DISCORD_TOKEN")
    if not TOKEN:
        print("ERROR: DISCORD_TOKEN environment variable not set!")
        print("Please set it in Render dashboard under Environment tab")
        print("Exiting...")
        exit(1)
    
    print(f"Token found: {TOKEN[:10]}...{TOKEN[-4:]}")
    
    # Start HTTP server in background thread
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    print("HTTP server started on port 10000")
    
    # Run Discord bot (main thread)
    print("Starting Discord bot...")
    try:
        bot.run(TOKEN)
    except Exception as e:
        print(f"Bot failed to start: {e}")
        exit(1)
