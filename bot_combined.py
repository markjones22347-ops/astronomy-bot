import discord
from discord import app_commands
from discord.ext import commands
import secrets
import string
import os
import threading
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import requests

# Role IDs
ADMIN_ROLE_ID = 1498479431906230393
TICKET_MANAGER_ROLE_ID = 1498479846286692578
SUPPORT_ROLE_ID = 1498478824273219616

# Load .env file if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# GitHub Gist for persistent storage
GIST_ID = os.environ.get("GIST_ID")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

# In-memory cache
licenses_cache = {}

def load_licenses():
    """Load licenses from GitHub Gist"""
    global licenses_cache
    if not GIST_ID or not GITHUB_TOKEN:
        print("WARNING: GIST_ID or GITHUB_TOKEN not set. Using in-memory storage (will lose data on restart)")
        return licenses_cache
    
    try:
        url = f"https://api.github.com/gists/{GIST_ID}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            gist_data = response.json()
            for filename, file_data in gist_data['files'].items():
                if filename == "licenses.json":
                    licenses_cache = json.loads(file_data['content'])
                    print(f"Loaded {len(licenses_cache)} licenses from Gist")
                    return licenses_cache
    except Exception as e:
        print(f"Failed to load from Gist: {e}")
    
    return licenses_cache

def save_licenses():
    """Save licenses to GitHub Gist"""
    if not GIST_ID or not GITHUB_TOKEN:
        print("WARNING: GIST_ID or GITHUB_TOKEN not set. Skipping save to Gist")
        return
    
    try:
        url = f"https://api.github.com/gists/{GIST_ID}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        data = {
            "files": {
                "licenses.json": {
                    "content": json.dumps(licenses_cache, indent=2)
                }
            }
        }
        response = requests.patch(url, headers=headers, json=data)
        
        if response.status_code == 200:
            print(f"Saved {len(licenses_cache)} licenses to Gist")
        else:
            print(f"Failed to save to Gist: {response.status_code}")
    except Exception as e:
        print(f"Failed to save to Gist: {e}")

def init_db():
    """Initialize licenses from Gist"""
    global licenses_cache
    licenses_cache = load_licenses()
    if not licenses_cache:
        licenses_cache = {}

def generate_key():
    return '-'.join([''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4)) for _ in range(4)])

class LicenseBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=discord.Intents.default())
        self.admin_role_id = ADMIN_ROLE_ID
        self.ticket_reminders = {}  # Track reminder cooldowns
        
    async def setup_hook(self):
        init_db()
        await self.tree.sync()
        
    async def on_ready(self):
        print(f'Bot logged in as {self.user}')
    
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return  # Ignore unknown commands
        if isinstance(error, commands.MissingRole):
            await ctx.send("❌ Invalid whitelist: You are not authorized to use this command.")
        else:
            raise error

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
        
        # Load licenses
        licenses_cache = load_licenses()
        
        # Check if key exists
        if key not in licenses_cache:
            await interaction.response.send_message(
                "❌ Invalid license key! Please check your key and try again.", 
                ephemeral=True
            )
            return
        
        # Check if username is already taken by another key
        for existing_key, data in licenses_cache.items():
            if data.get('username') == username and existing_key != key:
                await interaction.response.send_message(
                    f"❌ Username `{username}` is already registered to another key! Please choose a different username.",
                    ephemeral=True
                )
                return
        
        license_data = licenses_cache[key]
        
        # Check if key is already used
        if license_data.get('used', False):
            if license_data.get('username') == username:
                embed = discord.Embed(
                    title="✅ Already Registered",
                    description="This key is already registered to you!",
                    color=discord.Color.green()
                )
                embed.add_field(name="Key", value=f"`{key}`", inline=False)
                embed.add_field(name="Username", value=f"`{username}`", inline=False)
                embed.add_field(name="Status", value="Ready to use in client", inline=False)
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                embed = discord.Embed(
                    title="❌ Key Already Used",
                    description=f"This key is registered to another user.",
                    color=discord.Color.red()
                )
                embed.add_field(name="Registered to", value=f"`{license_data.get('username')}`", inline=False)
                embed.add_field(name="Action", value="Contact an admin if this is an error", inline=False)
                await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Register the key
        licenses_cache[key]['used'] = True
        licenses_cache[key]['username'] = username
        licenses_cache[key]['registered_by'] = str(interaction.user.id)
        save_licenses()
        
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

def is_admin(interaction) -> bool:
    if not interaction.guild:
        return False
    role = interaction.guild.get_role(bot.admin_role_id)
    user = interaction.user if hasattr(interaction, 'user') else interaction.author
    return role in user.roles

def is_ticket_manager(interaction) -> bool:
    if not interaction.guild:
        return False
    role = interaction.guild.get_role(TICKET_MANAGER_ROLE_ID)
    user = interaction.user if hasattr(interaction, 'user') else interaction.author
    return role in user.roles

# Ticket Configuration Modal
class TicketPanelModal(discord.ui.Modal, title="Create Ticket Panel"):
    button_count = discord.ui.TextInput(
        label="Number of buttons",
        placeholder="1-5",
        required=True,
        max_length=1
    )
    
    button_labels = discord.ui.TextInput(
        label="Button labels (comma-separated)",
        placeholder="Support, General, Billing",
        required=True,
        max_length=100
    )
    
    welcome_message = discord.ui.TextInput(
        label="Welcome message for tickets",
        placeholder="Welcome! Please describe your issue.",
        required=True,
        max_length=500,
        style=discord.TextStyle.paragraph
    )
    
    ping_user_id = discord.ui.TextInput(
        label="User ID to ping (leave empty for none)",
        placeholder="123456789012345678",
        required=False,
        max_length=20
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            button_count = int(self.button_count.value)
            if button_count < 1 or button_count > 5:
                await interaction.response.send_message("Button count must be between 1 and 5", ephemeral=True)
                return
            
            button_labels = [label.strip() for label in self.button_labels.value.split(',')]
            if len(button_labels) != button_count:
                await interaction.response.send_message(f"Button count ({button_count}) doesn't match number of labels ({len(button_labels)})", ephemeral=True)
                return
            
            ping_user_id = self.ping_user_id.value.strip() if self.ping_user_id.value.strip() else None
            
            # Create embed
            embed = discord.Embed(
                title="🎫 Create a Ticket",
                description="Click a button below to create a ticket.",
                color=discord.Color.blue()
            )
            embed.set_footer(text="Select a category")
            
            # Create view with buttons
            view = discord.ui.View()
            
            for label in button_labels:
                button = discord.ui.Button(label=label, style=discord.ButtonStyle.primary)
                button.callback = lambda i, l=label: self.create_ticket(i, l, self.welcome_message.value, ping_user_id)
                view.add_item(button)
            
            await interaction.response.send_message(embed=embed, view=view)
            
        except ValueError:
            await interaction.response.send_message("Invalid button count. Please enter a number.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Error creating panel: {str(e)}", ephemeral=True)
    
    async def create_ticket(self, interaction: discord.Interaction, category: str, welcome_message: str, ping_user_id: str):
        guild = interaction.guild
        user = interaction.user
        
        # Create ticket channel
        ticket_channel = await guild.create_text_channel(
            f"ticket-{user.name}-{category.lower()}",
            category=guild.categories[0] if guild.categories else None,
            overwrites={
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True),
                guild.get_role(bot.admin_role_id): discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
                guild.get_role(SUPPORT_ROLE_ID): discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
        )
        
        # Create welcome embed
        embed = discord.Embed(
            title=f"🎫 Ticket - {category}",
            description=welcome_message,
            color=discord.Color.green()
        )
        embed.add_field(name="Created by", value=user.mention, inline=True)
        embed.add_field(name="Category", value=category, inline=True)
        embed.set_footer(text=f"Ticket ID: {ticket_channel.id}")
        
        # Create view with close and remind buttons
        view = discord.ui.View()
        
        # Close button
        close_button = discord.ui.Button(label="Close Ticket", style=discord.ButtonStyle.danger)
        close_button.callback = lambda i: self.close_ticket(i, ticket_channel)
        view.add_item(close_button)
        
        # Remind button
        remind_button = discord.ui.Button(label="Remind Support", style=discord.ButtonStyle.secondary)
        remind_button.callback = lambda i: self.remind_support(i, ticket_channel)
        view.add_item(remind_button)
        
        # Send welcome message
        await ticket_channel.send(embed=embed, view=view)
        
        # Ping user if specified
        if ping_user_id:
            try:
                ping_user = await bot.fetch_user(ping_user_id)
                await ticket_channel.send(f"{ping_user.mention}")
            except:
                pass
        
        # Ping support role
        support_role = guild.get_role(SUPPORT_ROLE_ID)
        if support_role:
            await ticket_channel.send(f"{support_role.mention} New ticket created!")
        
        await interaction.response.send_message(f"Ticket created: {ticket_channel.mention}", ephemeral=True)
    
    async def close_ticket(self, interaction: discord.Interaction, channel: discord.TextChannel):
        embed = discord.Embed(
            title="🔒 Ticket Closed",
            description="This ticket has been closed.",
            color=discord.Color.red()
        )
        embed.add_field(name="Closed by", value=interaction.user.mention, inline=True)
        
        await interaction.response.send_message(embed=embed)
        await channel.set_permissions(interaction.guild.default_role, read_messages=False)
        await channel.set_permissions(interaction.user, read_messages=False, send_messages=False)
    
    async def remind_support(self, interaction: discord.Interaction, channel: discord.TextChannel):
        # Check cooldown
        cooldown_key = f"{channel.id}_remind"
        if cooldown_key in bot.ticket_reminders:
            last_remind = bot.ticket_reminders[cooldown_key]
            if datetime.now() - last_remind < timedelta(hours=1):
                remaining = timedelta(hours=1) - (datetime.now() - last_remind)
                await interaction.response.send_message(f"⏰ Remind on cooldown. Try again in {int(remaining.total_seconds() / 60)} minutes.", ephemeral=True)
                return
        
        # Update cooldown
        bot.ticket_reminders[cooldown_key] = datetime.now()
        
        # Ping support role
        support_role = interaction.guild.get_role(SUPPORT_ROLE_ID)
        if support_role:
            await channel.send(f"🔔 {support_role.mention} Reminder: Please check this ticket!")
        
        await interaction.response.send_message("✅ Support team has been reminded!", ephemeral=True)

@bot.tree.command(name="generate", description="Generate license keys (Admin only)")
@app_commands.check(is_admin)
@app_commands.describe(count="Number of keys to generate")
async def generate(interaction: discord.Interaction, count: int = 1):
    keys = []
    for _ in range(count):
        key = generate_key()
        licenses_cache[key] = {
            'username': None,
            'generated_by': str(interaction.user.id),
            'generated_at': datetime.now().isoformat(),
            'used': False
        }
        keys.append(key)
    
    save_licenses()
    
    embed = discord.Embed(
        title=f"✅ Generated {count} License Key(s)",
        color=discord.Color.green()
    )
    for i, key in enumerate(keys):
        embed.add_field(name=f"Key {i+1}", value=f"`{key}`", inline=False)
    embed.set_footer(text=f"Generated by {interaction.user.display_name}")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="delete", description="Delete a license key (Admin only)")
@app_commands.check(is_admin)
@app_commands.describe(key="License key to delete")
async def delete(interaction: discord.Interaction, key: str):
    if key in licenses_cache:
        del licenses_cache[key]
        save_licenses()
        
        embed = discord.Embed(
            title="✅ Key Deleted",
            color=discord.Color.green()
        )
        embed.add_field(name="Deleted Key", value=f"`{key}`", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        embed = discord.Embed(
            title="❌ Key Not Found",
            description=f"The key `{key}` does not exist.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="show", description="Show all license keys (Admin only)")
@app_commands.check(is_admin)
async def show(interaction: discord.Interaction):
    if not licenses_cache:
        await interaction.response.send_message("No keys found.", ephemeral=True)
        return
    
    embed = discord.Embed(
        title=f"📋 License Keys ({len(licenses_cache)} total)",
        color=discord.Color.blue()
    )
    
    for key, data in list(licenses_cache.items())[:10]:
        username = data.get('username') or "N/A"
        generated_by = data.get('generated_by', 'Unknown')
        registered_by = data.get('registered_by', 'N/A')
        used_str = "✅ Used" if data.get('used') else "⬜ Available"
        registered_info = f"{username}" if registered_by == 'N/A' else f"{username} (<@{registered_by}>)"
        embed.add_field(
            name=f"`{key}`",
            value=f"**Generated by:** <@{generated_by}>\n**Registered to:** {registered_info}\n**Status:** {used_str}\n**Date:** {data['generated_at'][:10]}",
            inline=False
        )
    
    if len(licenses_cache) > 10:
        embed.set_footer(text=f"Showing 10 of {len(licenses_cache)} keys")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="purge", description="Delete license keys in bulk (Admin only)")
@app_commands.check(is_admin)
@app_commands.describe(mode="Purge mode: all, keys, or username")
@app_commands.describe(keys="Comma-separated keys to delete (for keys mode)")
@app_commands.describe(username="Username to delete keys for (for username mode)")
async def purge(interaction: discord.Interaction, mode: str, keys: str = None, username: str = None):
    mode = mode.lower()
    deleted_count = 0
    
    if mode == "all":
        deleted_count = len(licenses_cache)
        licenses_cache.clear()
        save_licenses()
        
        embed = discord.Embed(
            title=f"🗑️ Purged All Keys",
            description=f"Deleted **{deleted_count}** license keys.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    elif mode == "keys":
        if not keys:
            await interaction.response.send_message("Please provide keys to delete (comma-separated).", ephemeral=True)
            return
        
        key_list = [k.strip().upper() for k in keys.split(',')]
        deleted = []
        not_found = []
        
        for key in key_list:
            if key in licenses_cache:
                del licenses_cache[key]
                deleted.append(key)
            else:
                not_found.append(key)
        
        save_licenses()
        
        embed = discord.Embed(
            title=f"🗑️ Purge Keys",
            color=discord.Color.orange()
        )
        embed.add_field(name="Deleted", value=f"{len(deleted)} keys", inline=True)
        embed.add_field(name="Not Found", value=f"{len(not_found)} keys", inline=True)
        
        if deleted:
            embed.add_field(name="Deleted Keys", value="\n".join([f"`{k}`" for k in deleted[:10]]), inline=False)
        if not_found:
            embed.add_field(name="Not Found", value="\n".join([f"`{k}`" for k in not_found[:10]]), inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    elif mode == "username":
        if not username:
            await interaction.response.send_message("Please provide a username.", ephemeral=True)
            return
        
        keys_to_delete = [k for k, v in licenses_cache.items() if v.get('username') == username]
        
        if not keys_to_delete:
            await interaction.response.send_message(f"No keys found for username `{username}`.", ephemeral=True)
            return
        
        for key in keys_to_delete:
            del licenses_cache[key]
        
        save_licenses()
        
        embed = discord.Embed(
            title=f"🗑️ Purged by Username",
            description=f"Deleted **{len(keys_to_delete)}** keys for username `{username}`.",
            color=discord.Color.orange()
        )
        embed.add_field(name="Deleted Keys", value="\n".join([f"`{k}`" for k in keys_to_delete[:10]]), inline=False)
        
        if len(keys_to_delete) > 10:
            embed.set_footer(text=f"Showing 10 of {len(keys_to_delete)} deleted keys")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    else:
        await interaction.response.send_message("Invalid mode. Use: all, keys, or username", ephemeral=True)

@bot.tree.command(name="lookup", description="Look up a specific key (Admin only)")
@app_commands.check(is_admin)
@app_commands.describe(key="License key to look up")
async def lookup(interaction: discord.Interaction, key: str):
    if key not in licenses_cache:
        embed = discord.Embed(
            title="❌ Key Not Found",
            description=f"The key `{key}` does not exist.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    data = licenses_cache[key]
    status = "✅ Used" if data.get('used') else "⬜ Available"
    
    embed = discord.Embed(
        title="🔍 License Key Details",
        color=discord.Color.blue()
    )
    embed.add_field(name="Key", value=f"`{key}`", inline=True)
    embed.add_field(name="Status", value=status, inline=True)
    embed.add_field(name="Username", value=data.get('username') or "N/A", inline=True)
    embed.add_field(name="Generated", value=data['generated_at'][:19], inline=True)
    embed.add_field(name="Generated By", value=f"<@{data['generated_by']}>", inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="users", description="Show all registered users (Admin only)")
@app_commands.check(is_admin)
async def users(interaction: discord.Interaction):
    registered = {k: v for k, v in licenses_cache.items() if v.get('used')}
    
    if not registered:
        await interaction.response.send_message("No registered users found.", ephemeral=True)
        return
    
    embed = discord.Embed(title="Registered Users", color=discord.Color.green())
    embed.description = f"Total registered users: **{len(registered)}**"
    
    for i, (key, data) in enumerate(list(registered.items())[:25]):
        embed.add_field(name=f"{i+1}. {data.get('username')}", value=f"Key: `{key}`\nDate: {data['generated_at'][:10]}", inline=False)
    
    if len(registered) > 25:
        embed.set_footer(text=f"Showing 25 of {len(registered)} users")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="revoke", description="Revoke a user's access (Admin only)")
@app_commands.check(is_admin)
@app_commands.describe(username="Username to revoke")
async def revoke(interaction: discord.Interaction, username: str):
    # Find user's key
    key_to_revoke = None
    for key, data in licenses_cache.items():
        if data.get('username') == username and data.get('used'):
            key_to_revoke = key
            break
    
    if not key_to_revoke:
        embed = discord.Embed(
            title="❌ User Not Found",
            description=f"User `{username}` not found or not active.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    # Reset the license
    licenses_cache[key_to_revoke]['used'] = False
    licenses_cache[key_to_revoke]['username'] = None
    save_licenses()
    
    embed = discord.Embed(
        title="✅ Access Revoked",
        color=discord.Color.orange()
    )
    embed.add_field(name="Username", value=f"`{username}`", inline=True)
    embed.add_field(name="Key", value=f"`{key_to_revoke}`", inline=True)
    embed.add_field(name="Status", value="Now available for re-use", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="stats", description="Show license system statistics (Admin only)")
@app_commands.check(is_admin)
async def stats(interaction: discord.Interaction):
    total_keys = len(licenses_cache)
    used_keys = sum(1 for data in licenses_cache.values() if data.get('used'))
    
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
    if key in licenses_cache:
        licenses_cache[key]['used'] = False
        licenses_cache[key]['username'] = None
        save_licenses()
        
        embed = discord.Embed(
            title="🔄 Key Reset",
            color=discord.Color.orange()
        )
        embed.add_field(name="Key", value=f"`{key}`", inline=True)
        embed.add_field(name="Status", value="Now available for re-use", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        embed = discord.Embed(
            title="❌ Key Not Found",
            description=f"The key `{key}` does not exist.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="register", description="Register your license key (Opens registration form)")
async def register(interaction: discord.Interaction):
    # Show the registration modal
    modal = RegistrationModal()
    await interaction.response.send_modal(modal)

@bot.tree.command(name="ticket", description="Create a ticket panel (Ticket Manager only)")
@app_commands.check(is_ticket_manager)
async def ticket_command(interaction: discord.Interaction):
    """Create a ticket panel (Ticket Manager only)"""
    modal = TicketPanelModal()
    await interaction.response.send_modal(modal)

# Simple HTTP server for mod verification
class VerificationHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress logs
        pass
        
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps({"status": "License server running"}).encode())
    
    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
    
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
            
            response = {"valid": False}
            
            if key not in licenses_cache:
                response["error"] = "Invalid key"
            elif licenses_cache[key].get('used') and licenses_cache[key].get('username') != username:
                response["error"] = "Key already used"
            else:
                licenses_cache[key]['used'] = True
                licenses_cache[key]['username'] = username
                save_licenses()
                
                response = {"valid": True, "message": "License verified"}
            
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

def run_server(port):
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
    
    # Get port from environment or use default
    PORT = int(os.environ.get("PORT", 80))
    
    server_thread = threading.Thread(target=run_server, args=(PORT,), daemon=True)
    server_thread.start()
    print(f"HTTP server started on port {PORT}")
    
    print("Starting Discord bot...")
    try:
        bot.run(TOKEN)
    except Exception as e:
        print(f"Bot failed to start: {e}")
        exit(1)
