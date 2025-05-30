import asyncio
import json
from urllib.parse import quote

import aiohttp
import discord
from discord.ext import commands, tasks

# Load config
with open("config.json") as f:
    config = json.load(f)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user.name}")
    poll_war.start()


@bot.command()
async def linkcoc(ctx, tag):
    """Link your Clash of Clans tag to your Discord account."""
    tag = tag.upper().replace("O", "0")
    if not tag.startswith("#"):
        await ctx.send("❌ Invalid tag format. It should start with `#`.")
        return
    try:
        with open("user_map.json") as f:
            user_map = json.load(f)
    except FileNotFoundError:
        user_map = {}

    user_map[tag] = ctx.author.id
    with open("user_map.json", "w") as f:
        json.dump(user_map, f, indent=2)

    await ctx.send(f"🔗 Linked {tag} to {ctx.author.mention}")


@bot.command()
async def unlinkcoc(ctx):
    """Unlink your Clash of Clans tag from your Discord account."""
    try:
        with open("user_map.json") as f:
            user_map = json.load(f)
    except FileNotFoundError:
        user_map = {}

    removed = [tag for tag, uid in user_map.items() if uid == ctx.author.id]
    for tag in removed:
        del user_map[tag]

    with open("user_map.json", "w") as f:
        json.dump(user_map, f, indent=2)

    await ctx.send(f"❎ Unlinked {len(removed)} tag(s) from {ctx.author.mention}")


@tasks.loop(seconds=300)
async def poll_war():
    await bot.wait_until_ready()
    guild = bot.get_guild(int(config["guild_id"]))
    role = discord.utils.get(guild.roles, name=config["war_role"])

    try:
        headers = {"Authorization": f"Bearer {config['coc_api_key']}"}
        encoded_tag = quote(config["clan_tag"])
        url = f"https://api.clashofclans.com/v1/clans/{encoded_tag}/currentwar"
        print(f"📡 Fetching: {url}")
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 404:
                    print("🔍 No active or prep war found.")
                    return
                war_data = await resp.json()

        state = war_data.get("state")
        print(f"🏹 War State: {state}")

        if state != "inWar":
            print("⚠️ Clan is not currently in war. Skipping role assignment.")
            return

        current_war_tags = [m["tag"] for m in war_data["clan"]["members"]]
        print(f"🔗 War Participants: {current_war_tags}")

        try:
            with open("user_map.json") as f:
                user_map = json.load(f)
        except FileNotFoundError:
            user_map = {}

        # Assign @active-war role
        for tag in current_war_tags:
            discord_id = user_map.get(tag)
            if discord_id:
                member = guild.get_member(discord_id)
                if member and role not in member.roles:
                    await member.add_roles(role)
                    print(f"✅ Assigned role to {member.display_name} ({tag})")

        # Remove role from members not in war
        for member in guild.members:
            if role in member.roles:
                mapped_tags = [t for t, uid in user_map.items() if uid == member.id]
                if not any(tag in current_war_tags for tag in mapped_tags):
                    await member.remove_roles(role)
                    print(f"🗑️ Removed role from {member.display_name}")

    except Exception as e:
        print(f"[ERROR] {e}")


bot.run(config["discord_token"])
