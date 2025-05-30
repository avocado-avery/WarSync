import asyncio
import json
from datetime import datetime, timedelta

import aiohttp
import discord
from discord.ext import commands, tasks

with open("config.json") as f:
    config = json.load(f)

with open("user_map.json") as f:
    user_map = json.load(f)

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

API_URL = f"https://api.clashofclans.com/v1/clans/{config['clan_tag'].replace('#', '%23')}/currentwar"
HEADERS = {"Authorization": f"Bearer {config['coc_api_key']}"}

last_state = None
last_participants = set()
war_end_time = None


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    poll_war.start()


@tasks.loop(seconds=300)
async def poll_war():
    global last_state, last_participants, war_end_time
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(API_URL, headers=HEADERS) as resp:
                if resp.status != 200:
                    print(f"[ERROR] Failed to fetch war info: {resp.status}")
                    return
                data = await resp.json()

        state = data.get("state")
        if state not in ["inWar", "warEnded"]:
            return

        guild = bot.get_guild(int(config["guild_id"]))
        channel = guild.get_channel(int(config["announcement_channel_id"]))
        role = discord.utils.get(guild.roles, name=config.get("war_role", "active-war"))

        participants = set()
        player_lines = []
        enemy_lines = []
        two_attack_users = []
        th_tally_clan = {}
        th_tally_enemy = {}

        # Parse clan side
        for member in data.get("clan", {}).get("members", []):
            tag = member.get("tag")
            th = member.get("townhallLevel", 0)
            name = member.get("name")
            participants.add(tag)
            discord_id = user_map.get(tag)
            attacks_used = len(member.get("attacks", []))
            attacks_left = max(0, 2 - attacks_used)

            th_tally_clan[th] = th_tally_clan.get(th, 0) + 1
            if attacks_left == 2 and discord_id:
                two_attack_users.append(discord_id)

            player_lines.append(
                (th, f"🏰 {name} (TH{th}) — {attacks_left} attack(s) left")
            )

            if discord_id and state == "inWar":
                member_obj = guild.get_member(int(discord_id))
                if member_obj and role:
                    await member_obj.add_roles(role)

        # Parse enemy side
        for enemy in data.get("opponent", {}).get("members", []):
            th = enemy.get("townhallLevel", 0)
            name = enemy.get("name")
            th_tally_enemy[th] = th_tally_enemy.get(th, 0) + 1
            enemy_lines.append((th, f"🏰 {name} (TH{th})"))

        player_lines.sort(reverse=True)
        enemy_lines.sort(reverse=True)
        sorted_player_lines = [line for _, line in player_lines]
        sorted_enemy_lines = [line for _, line in enemy_lines]

        # On war start
        if state == "inWar" and participants != last_participants:
            header = "📣 **New war started!**"
            our_clan = data.get("clan", {}).get("name", "Our Clan")
            enemy_clan = data.get("opponent", {}).get("name", "Enemy Clan")
            vs_line = f"**{our_clan} vs {enemy_clan}**"
            clan_ths = ", ".join(
                [f"{v} TH{k}" for k, v in sorted(th_tally_clan.items(), reverse=True)]
            )
            enemy_ths = ", ".join(
                [f"{v} TH{k}" for k, v in sorted(th_tally_enemy.items(), reverse=True)]
            )
            war_end_time = datetime.utcnow() + timedelta(hours=24)

            await channel.send(
                f"{role.mention}\n{header}\n{vs_line}\n\n**Our THs:** {clan_ths}\n**Enemy THs:** {enemy_ths}\n\n"
                + "\n".join(sorted_player_lines)
                + "\n\n**Enemy Roster:**\n"
                + "\n".join(sorted_enemy_lines)
            )
            last_participants = participants

        # On war halfway
        if state == "inWar" and war_end_time:
            now = datetime.utcnow()
            remaining = war_end_time - now
            if abs(remaining.total_seconds() - 43200) < 300:
                await channel.send(
                    "⏳ **Halfway through the war!**\n" + "\n".join(sorted_player_lines)
                )

            if abs(remaining.total_seconds() - 7200) < 300:
                mentions = [f"<@{uid}>" for uid in two_attack_users]
                if mentions:
                    await channel.send(
                        "⚠️ **2 hours left! The following still have 2 attacks:**\n"
                        + "\n".join(mentions)
                    )

        if state == "warEnded" and last_state != "warEnded":
            for tag, discord_id in user_map.items():
                member_obj = guild.get_member(int(discord_id))
                if member_obj and role:
                    await member_obj.remove_roles(role)
            await channel.send("⚔️ **War has ended! Roles have been cleared.**")
            last_participants = set()
            war_end_time = None

        last_state = state

    except Exception as e:
        print(f"[ERROR] {e}")


@bot.command()
async def linkcoc(ctx, tag: str):
    if not tag.startswith("#"):
        await ctx.send("❌ Invalid tag. It should start with '#' (e.g. #ABC123)")
        return
    user_map[tag.upper()] = str(ctx.author.id)
    with open("user_map.json", "w") as f:
        json.dump(user_map, f, indent=2)
    await ctx.send(f"✅ Linked Clash of Clans tag `{tag}` to {ctx.author.mention}")


bot.run(config["discord_token"])
