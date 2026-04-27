import discord
from discord import app_commands
from discord.ext import commands
import sqlite3
import secrets
import string
import os
from datetime import datetime

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
                  generated_at TEXT, used BOOLEAN DEFAULT 0, hwid TEXT)''')
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
    
    key, username, generated_by, generated_at, used, hwid = result
    status = "Used" if used else "Available"
    
    embed = discord.Embed(title="License Key Info", color=discord.Color.blue())
    embed.add_field(name="Key", value=f"`{key}`", inline=False)
    embed.add_field(name="Status", value=status, inline=True)
    embed.add_field(name="Username", value=username or "N/A", inline=True)
    embed.add_field(name="Generated", value=generated_at[:19], inline=True)
    embed.add_field(name="HWID", value=f"`{hwid or 'N/A'}`", inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="users", description="Show all registered users (Admin only)")
@app_commands.check(is_admin)
async def users(interaction: discord.Interaction):
    conn = sqlite3.connect('licenses.db')
    c = conn.cursor()
    c.execute("SELECT username, key, generated_at, hwid FROM licenses WHERE used = 1 ORDER BY generated_at DESC")
    results = c.fetchall()
    conn.close()
    
    if not results:
        await interaction.response.send_message("No registered users found.", ephemeral=True)
        return
    
    embed = discord.Embed(title="Registered Users", color=discord.Color.green())
    embed.description = f"Total registered users: **{len(results)}**"
    
    for i, (username, key, date, hwid) in enumerate(results[:25]):  # Show max 25
        value = f"Key: `{key}`\nDate: {date[:10]}\nHWID: `{hwid[:8]}...`" if hwid else "No HWID"
        embed.add_field(name=f"{i+1}. {username}", value=value, inline=False)
    
    if len(results) > 25:
        embed.set_footer(text=f"Showing 25 of {len(results)} users")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="revoke", description="Revoke a user's access (Admin only)")
@app_commands.check(is_admin)
@app_commands.describe(username="Username to revoke")
async def revoke(interaction: discord.Interaction, username: str):
    conn = sqlite3.connect('licenses.db')
    c = conn.cursor()
    
    # Find user's key
    c.execute("SELECT key FROM licenses WHERE username = ? AND used = 1", (username,))
    result = c.fetchone()
    
    if not result:
        conn.close()
        await interaction.response.send_message(f"User `{username}` not found or not active.", ephemeral=True)
        return
    
    key = result[0]
    
    # Reset the license (mark as unused, clear username and hwid)
    c.execute("UPDATE licenses SET used = 0, username = NULL, hwid = NULL WHERE key = ?", (key,))
    conn.commit()
    conn.close()
    
    await interaction.response.send_message(f"✅ Revoked access for `{username}`. Key `{key}` is now available again.", ephemeral=True)

@bot.tree.command(name="banhwid", description="Ban a HWID to prevent re-registration (Admin only)")
@app_commands.check(is_admin)
@app_commands.describe(hwid="HWID to ban", reason="Reason for ban")
async def banhwid(interaction: discord.Interaction, hwid: str, reason: str = "No reason provided"):
    conn = sqlite3.connect('licenses.db')
    c = conn.cursor()
    
    # Check if banned_hwids table exists, create if not
    c.execute('''CREATE TABLE IF NOT EXISTS banned_hwids
                 (hwid TEXT PRIMARY KEY, banned_by TEXT, banned_at TEXT, reason TEXT)''')
    
    c.execute("INSERT OR REPLACE INTO banned_hwids (hwid, banned_by, banned_at, reason) VALUES (?, ?, ?, ?)",
              (hwid, str(interaction.user.id), datetime.now().isoformat(), reason))
    conn.commit()
    conn.close()
    
    await interaction.response.send_message(f"🔨 Banned HWID: `{hwid}`\nReason: {reason}", ephemeral=True)

@bot.tree.command(name="unbanhwid", description="Unban a HWID (Admin only)")
@app_commands.check(is_admin)
@app_commands.describe(hwid="HWID to unban")
async def unbanhwid(interaction: discord.Interaction, hwid: str):
    conn = sqlite3.connect('licenses.db')
    c = conn.cursor()
    c.execute("DELETE FROM banned_hwids WHERE hwid = ?", (hwid,))
    conn.commit()
    conn.close()
    
    await interaction.response.send_message(f"✅ Unbanned HWID: `{hwid}`", ephemeral=True)

@bot.tree.command(name="stats", description="Show license system statistics (Admin only)")
@app_commands.check(is_admin)
async def stats(interaction: discord.Interaction):
    conn = sqlite3.connect('licenses.db')
    c = conn.cursor()
    
    # Get stats
    c.execute("SELECT COUNT(*) FROM licenses")
    total_keys = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM licenses WHERE used = 1")
    used_keys = c.fetchone()[0]
    
    c.execute("SELECT COUNT(DISTINCT hwid) FROM licenses WHERE used = 1")
    unique_users = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM banned_hwids")
    banned_count = c.fetchone()[0] if c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='banned_hwids'").fetchone() else 0
    
    conn.close()
    
    embed = discord.Embed(title="License System Statistics", color=discord.Color.purple())
    embed.add_field(name="Total Keys", value=str(total_keys), inline=True)
    embed.add_field(name="Used Keys", value=str(used_keys), inline=True)
    embed.add_field(name="Available Keys", value=str(total_keys - used_keys), inline=True)
    embed.add_field(name="Unique Users", value=str(unique_users), inline=True)
    embed.add_field(name="Banned HWIDs", value=str(banned_count), inline=True)
    embed.add_field(name="Active Rate", value=f"{(used_keys/total_keys*100):.1f}%" if total_keys > 0 else "0%", inline=True)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="finduser", description="Find user by HWID (Admin only)")
@app_commands.check(is_admin)
@app_commands.describe(hwid="HWID to search for")
async def finduser(interaction: discord.Interaction, hwid: str):
    conn = sqlite3.connect('licenses.db')
    c = conn.cursor()
    c.execute("SELECT username, key, generated_at FROM licenses WHERE hwid = ?", (hwid,))
    results = c.fetchall()
    conn.close()
    
    if not results:
        await interaction.response.send_message("No users found with that HWID.", ephemeral=True)
        return
    
    embed = discord.Embed(title="Users with this HWID", color=discord.Color.orange())
    for username, key, date in results:
        embed.add_field(name=username, value=f"Key: `{key}`\nDate: {date[:10]}", inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="resetkey", description="Reset a key to unused status (Admin only)")
@app_commands.check(is_admin)
@app_commands.describe(key="License key to reset")
async def resetkey(interaction: discord.Interaction, key: str):
    conn = sqlite3.connect('licenses.db')
    c = conn.cursor()
    c.execute("UPDATE licenses SET used = 0, username = NULL, hwid = NULL WHERE key = ?", (key,))
    conn.commit()
    conn.close()
    
    await interaction.response.send_message(f"🔄 Reset key `{key}` to available status.", ephemeral=True)

# Run the bot
if __name__ == "__main__":
    TOKEN = os.environ.get("DISCORD_TOKEN", "YOUR_DISCORD_BOT_TOKEN_HERE")
    if TOKEN == "YOUR_DISCORD_BOT_TOKEN_HERE":
        print("ERROR: Please set the DISCORD_TOKEN environment variable!")
        print("Create a .env file with: DISCORD_TOKEN=your_token_here")
        exit(1)
    bot.run(TOKEN)
