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

API_CURRENT_WAR = f"https://api.clashofclans.com/v1/clans/{config['clan_tag'].replace('#', '%23')}/currentwar"
CWL_GROUP_URL = f"https://api.clashofclans.com/v1/clans/{config['clan_tag'].replace('#', '%23')}/currentwar/leaguegroup"
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


@tasks.loop(seconds=300)
async def poll_war():
    global last_state, last_participants, war_end_time
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(API_CURRENT_WAR, headers=HEADERS) as resp:
                if resp.status != 200:
                    print("[INFO] Trying CWL war endpoint instead...")
                    async with session.get(CWL_GROUP_URL, headers=HEADERS) as cwl_resp:
                        if cwl_resp.status != 200:
                            print(
                                f"[ERROR] Failed to fetch CWL group info: {cwl_resp.status}"
                            )
                            return
                        league_data = await cwl_resp.json()

                    war_tags = [
                        tag
                        for round in league_data.get("rounds", [])
                        for tag in round.get("warTags", [])
                        if tag != "#0"
                    ]
                    current_war_data = None
                    for war_tag in war_tags:
                        war_url = f"https://api.clashofclans.com/v1/clanwarleagues/wars/{war_tag.replace('#', '%23')}"
                        async with session.get(war_url, headers=HEADERS) as war_resp:
                            if war_resp.status == 200:
                                potential_data = await war_resp.json()
                                if (
                                    potential_data.get("state")
                                    in ["preparation", "inWar"]
                                    and potential_data.get("clan", {}).get("tag")
                                    == config["clan_tag"]
                                ):
                                    current_war_data = potential_data
                                    break

                    if not current_war_data:
                        print("[ERROR] No active CWL war found.")
                        return

                    data = current_war_data
                else:
                    data = await resp.json()

        state = data.get("state")
        if state not in ["preparation", "inWar", "warEnded"]:
            return

        guild = bot.get_guild(int(config["guild_id"]))
        channel = guild.get_channel(int(config["announcement_channel_id"]))
        role = discord.utils.get(guild.roles, name=config.get("war_role", "active-war"))

        # PREP STAGE NOTICE
        if state == "preparation" and last_state != "preparation":
            prep_end_time = datetime.fromisoformat(
                data["endTime"].replace("UTC", "+00:00")
            )
            time_left = prep_end_time - datetime.now(timezone.utc)

            war_type = "CWL" if data.get("warType", "") == "cwl" else "regular war"
            our_clan = data.get("clan", {}).get("name", "Our Clan")
            enemy_clan = data.get("opponent", {}).get("name", "Enemy Clan")

            clan_size = len(data.get("clan", {}).get("members", []))
            enemy_size = len(data.get("opponent", {}).get("members", []))

            prep_message = (
                f"🛡️ **{war_type.title()} prep has begun!**\n"
                f"**{our_clan} vs {enemy_clan}** — {clan_size}v{enemy_size}\n"
                f"⏳ War starts in **{int(time_left.total_seconds() // 3600)} hours and {(time_left.total_seconds() % 3600) // 60:.0f} minutes**."
            )

            await channel.send(prep_message)

        # CLEANUP + TRACK CURRENT STATE
        if state == "warEnded" and war_end_time is not None:
            for tag, discord_id in user_map.items():
                member_obj = guild.get_member(int(discord_id))
                if member_obj and role:
                    await member_obj.remove_roles(role)

            our_clan = data.get("clan", {}).get("name", "Our Clan")
            enemy_clan = data.get("opponent", {}).get("name", "Enemy Clan")
            our_stars = data.get("clan", {}).get("stars", 0)
            enemy_stars = data.get("opponent", {}).get("stars", 0)
            our_destruction = data.get("clan", {}).get("destructionPercentage", 0)
            enemy_destruction = data.get("opponent", {}).get("destructionPercentage", 0)

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
                f"{result_title}\n\n"
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
