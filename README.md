# 🏰 Clash of Clans WarSync Bot

A fully automated Discord bot that tracks Clash of Clans wars and assigns/removes the `@active-war` role based on current war participation. Built using Python, the Clash of Clans API, and Discord.py.

## 🔧 Features

- 🛡 Automatically assigns `@active-war` to members participating in a war
- 🧹 Clears roles when war ends
- 📣 Sends alerts at:
  - War start
  - Halfway point (with current score + attacks remaining)
  - 2 hours remaining (pinging users with 2 attacks left)
  - War end (with result summary)
- 🎯 Sorts participants by Town Hall level with visual TH icons ( Emojis Must Be In Your Server To Work Properly ) 
- 🔗 `!linkcoc <tag>` command to link a user's Clash tag to their Discord ID


## 📁 File Structure

.
├── bot.py # Main bot logic
├── config.json # Configuration (API keys, guild ID, channel ID, etc.)
├── user_map.json # Mapping of Clash tags to Discord IDs


## 🧪 Requirements

- Python 3.9+
- Dependencies:
  - `discord.py`
  - `aiohttp`


```bash

⚙️ Configuration

Update config.json with:

{
  "discord_token": "YOUR_DISCORD_BOT_TOKEN",
  "guild_id": "YOUR_GUILD_ID",
  "announcement_channel_id": "CHANNEL_ID",
  "clan_tag": "#YOURCLANTAG",
  "coc_api_key": "YOUR_COC_API_TOKEN",
  "war_role": "active-war",
}

🚀 Run as a Service (Linux)

Create a systemd unit to keep the bot running:

# /etc/systemd/system/clashbot.service
[Unit]
Description=Clash of Clans WarSync Bot
After=network.target

[Service]
User=yourusername
WorkingDirectory=/path/to/repo
ExecStart=/usr/bin/python3 /path/to/repo/bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target

Enable and start:

sudo systemctl daemon-reload
sudo systemctl enable clashbot
sudo systemctl start clashbot
