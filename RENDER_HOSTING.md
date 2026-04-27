# Hosting on Render.com

## Overview

Render.com offers free hosting for Discord bots and web APIs. This guide will help you deploy your license system.

## Important Note

**SQLite on Render:** Since Render uses ephemeral filesystems, your SQLite database will reset on every deploy/restart. For production use, consider:
- Using Render's **PostgreSQL** (paid) or **MySQL** (paid)
- Using an external database service
- Accepting that data resets (for testing only)

For a free alternative with persistent storage, consider **Railway.app** or **Fly.io**.

## Step-by-Step Setup

### 1. Prepare Your Code

Make sure these files are in your `license_bot/` folder:
- `bot.py`
- `api.py`
- `requirements.txt`
- `render.yaml` (already created)
- `Procfile` (already created)

### 2. Update Configuration

Edit `bot.py` and set your Discord bot token as an environment variable:
```python
# Change this line:
TOKEN = os.environ.get("DISCORD_TOKEN", "YOUR_DISCORD_BOT_TOKEN_HERE")
```

Edit `api.py` and set your API key as an environment variable:
```python
# Change this line:
API_KEY = os.environ.get("API_KEY", "your_secret_api_key_here")
```

### 3. Push to GitHub

```bash
cd license_bot
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/astronomy-license.git
git push -u origin main
```

### 4. Create Render Account

1. Go to https://render.com
2. Sign up with GitHub
3. Click "New +" and select "Blueprint"
4. Connect your GitHub repo
5. Render will detect `render.yaml` and create both services

### 5. Set Environment Variables

For **astronomy-license-api** (Web Service):
- `API_KEY` - Your secret API key
- `FLASK_ENV` - Set to `production`

For **astronomy-license-bot** (Worker):
- `DISCORD_TOKEN` - Your Discord bot token

### 6. Update Mod Configuration

In your Minecraft mod (`LicenseManager.java`), update the API URL:
```java
// Use your Render web service URL
private static final String API_URL = "https://astronomy-license-api.onrender.com";
private static final String API_KEY = "your_secret_api_key_here"; // Must match env var
```

## Alternative: Manual Setup (Without render.yaml)

### Create Web Service (API)

1. Click "New +" → "Web Service"
2. Select your GitHub repo
3. Configure:
   - **Name:** astronomy-license-api
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python api.py`
4. Add environment variables:
   - `API_KEY` = your_secret_key
5. Click "Create Web Service"

### Create Worker (Bot)

1. Click "New +" → "Background Worker"
2. Select your GitHub repo
3. Configure:
   - **Name:** astronomy-license-bot
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python bot.py`
4. Add environment variables:
   - `DISCORD_TOKEN` = your_bot_token
5. Click "Create Background Worker"

## After Deployment

### Get Your API URL

1. Go to your **astronomy-license-api** service
2. Copy the URL (e.g., `https://astronomy-license-api.onrender.com`)
3. Update it in your Minecraft mod's `LicenseManager.java`

### Test the API

```bash
curl -X POST https://your-service.onrender.com/verify \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{"key":"ABCD-EFGH-IJKL-MNOP", "username":"testuser", "hwid":"test123"}'
```

## Free Tier Limits

- **Web Services:** 512 MB RAM, sleeps after 15 min inactivity
- **Workers:** Always on (good for bot)
- **Bandwidth:** 100 GB/month
- **Builds:** 500 minutes/month

**Note:** Web services spin down after 15 minutes of inactivity. First request after spin-down takes ~30 seconds. Workers stay running.

## Troubleshooting

### Bot not responding:
- Check DISCORD_TOKEN is correct
- Ensure bot has proper permissions in Discord
- Check Render logs (Dashboard → Service → Logs)

### API not working:
- Verify API_KEY matches between mod and server
- Check CORS if testing from browser
- Test with curl first

### Database resets:
- This is expected on free tier
- For persistent storage, upgrade to PostgreSQL or use Railway.app

## Upgrading to PostgreSQL (Paid)

1. In Render Dashboard, click "New +" → "PostgreSQL"
2. Create a database
3. Get the "Internal Database URL"
4. Update `api.py` to use PostgreSQL instead of SQLite
5. Add `DATABASE_URL` environment variable

## Security Tips

1. **Never commit tokens/keys to GitHub**
2. **Use environment variables** for all secrets
3. **Enable HTTPS only** in production
4. **Rotate API keys** periodically
5. **Monitor logs** for suspicious activity

## Commands Reference

| Command | Description |
|---------|-------------|
| `/generate [count]` | Create new license keys |
| `/delete <key>` | Delete a key |
| `/show` | Show all keys with owners |
| `/lookup <key>` | Detailed key info |
| `/users` | List all registered users |
| `/revoke <username>` | Remove user access |
| `/banhwid <hwid> [reason]` | Ban a device |
| `/unbanhwid <hwid>` | Unban a device |
| `/stats` | System statistics |
| `/finduser <hwid>` | Find users by HWID |
| `/resetkey <key>` | Reset key to unused |

## Support

If you have issues:
1. Check Render logs (Dashboard → Service → Logs)
2. Test API locally first: `python api.py`
3. Verify Discord bot token at https://discord.com/developers/applications
4. Check that admin IDs are correct in `bot.py`
