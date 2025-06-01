import asyncio
import json
from datetime import datetime, timedelta, timezone

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

CLAN_TAG = config["clan_tag"].replace("#", "%23")
API_BASE = "https://api.clashofclans.com/v1"
HEADERS = {"Authorization": f"Bearer {config['coc_api_key']}"}

last_state = None
last_participants = set()
war_end_time = None

TH_EMOJIS = {
    1: "<:th1:1377885021095989278>",
    2: "<:th2:1377885017707118664>",
    3: "<:th3:1377885014129381477>",
    4: "<:th4:1377885009230430208>",
    5: "<:th5:1377885004671221801>",
    6: "<:th6:1377884999902036008>",
    7: "<:th7:1377884995888091146>",
    8: "<:th8:1377884992218206228>",
    9: "<:th9:1377884987495419924>",
    10: "<:th10:1377884982739075122>",
    11: "<:th11:1377884980990054411>",
    12: "<:th12:1377884975298252851>",
    13: "<:th13:1377884973494960178>",
    14: "<:th14:1377884971284434964>",
    15: "<:th15:1377884968314736701>",
    16: "<:th16:1377884966180098118>",
    17: "<:th17:1377884963692744856>",
}


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    poll_war.start()


async def fetch_json(session, url):
    async with session.get(url, headers=HEADERS) as resp:
        if resp.status != 200:
            print(f"[ERROR] Failed to fetch: {url} => {resp.status}")
            return None
        return await resp.json()


@tasks.loop(seconds=300)
async def poll_war():
    global last_state, last_participants, war_end_time
    try:
        async with aiohttp.ClientSession() as session:
            war_data = await fetch_json(
                session, f"{API_BASE}/clans/{CLAN_TAG}/currentwar"
            )
            if not war_data:
                return

            state = war_data.get("state")
            if state == "notInWar":
                league_data = await fetch_json(
                    session, f"{API_BASE}/clans/{CLAN_TAG}/currentwar/leaguegroup"
                )
                if league_data and "rounds" in league_data:
                    current_round = league_data.get("rounds", [])[-1]
                    war_tags = current_round.get("warTags", [])
                    current_war_tag = next(
                        (tag for tag in war_tags if tag != "#0"), None
                    )
                    if current_war_tag:
                        current_war_tag = current_war_tag.replace("#", "%23")
                        war_data = await fetch_json(
                            session, f"{API_BASE}/clanwarleagues/wars/{current_war_tag}"
                        )
                        state = war_data.get("state")
                        war_type = "CWL War"
                    else:
                        return
                else:
                    return
            else:
                war_type = "Regular War"

            if state not in ["inWar", "warEnded"]:
                return

            guild = bot.get_guild(int(config["guild_id"]))
            channel = guild.get_channel(int(config["announcement_channel_id"]))
            role = discord.utils.get(
                guild.roles, name=config.get("war_role", "active-war")
            )

            participants = set()
            player_lines, enemy_lines, two_attack_users = [], [], []

            for member in war_data.get("clan", {}).get("members", []):
                tag = member.get("tag")
                th = member.get("townhallLevel", 0)
                name = member.get("name")
                participants.add(tag)
                discord_id = user_map.get(tag)
                attacks_used = len(member.get("attacks", []))
                attacks_left = max(0, 2 - attacks_used)

                if attacks_left == 2 and discord_id:
                    two_attack_users.append(discord_id)

                emoji = TH_EMOJIS.get(th, "🏰")
                player_lines.append(
                    (th, f"{emoji} {name} (TH{th}) — {attacks_left} attack(s) left")
                )

                if discord_id and state == "inWar":
                    member_obj = guild.get_member(int(discord_id))
                    if member_obj and role:
                        await member_obj.add_roles(role)

            for enemy in war_data.get("opponent", {}).get("members", []):
                th = enemy.get("townhallLevel", 0)
                name = enemy.get("name")
                attacks_used = len(enemy.get("attacks", []))
                attacks_left = max(0, 2 - attacks_used)
                emoji = TH_EMOJIS.get(th, "🏰")
                enemy_lines.append(
                    (th, f"{emoji} {name} (TH{th}) — {attacks_left} attack(s) left")
                )

            player_lines.sort(reverse=True)
            enemy_lines.sort(reverse=True)
            sorted_player_lines = [line for _, line in player_lines]
            sorted_enemy_lines = [line for _, line in enemy_lines]

            if state == "warEnded" and war_end_time is not None:
                for tag, discord_id in user_map.items():
                    member_obj = guild.get_member(int(discord_id))
                    if member_obj and role:
                        await member_obj.remove_roles(role)

                our_clan = war_data.get("clan", {}).get("name", "Our Clan")
                enemy_clan = war_data.get("opponent", {}).get("name", "Enemy Clan")
                our_stars = war_data.get("clan", {}).get("stars", 0)
                enemy_stars = war_data.get("opponent", {}).get("stars", 0)
                our_destruction = war_data.get("clan", {}).get(
                    "destructionPercentage", 0
                )
                enemy_destruction = war_data.get("opponent", {}).get(
                    "destructionPercentage", 0
                )

                if our_stars > enemy_stars or (
                    our_stars == enemy_stars and our_destruction > enemy_destruction
                ):
                    result_title = "🏆 **Victory!**"
                elif our_stars < enemy_stars or (
                    our_stars == enemy_stars and our_destruction < enemy_destruction
                ):
                    result_title = "💀 **Defeat!**"
                else:
                    result_title = "⚖️ **Tie!**"

                result_message = (
                    f"{result_title} ({war_type})\n\n"
                    f"**{our_clan}**\n⭐ {our_stars}  —  🏚 {our_destruction:.1f}%\n"
                    f"**{enemy_clan}**\n⭐ {enemy_stars}  —  🏚 {enemy_destruction:.1f}%"
                )

                await channel.send(result_message)
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
