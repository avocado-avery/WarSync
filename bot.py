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

last_messages = {}
war_end_times = {}


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    poll_cwl_wars.start()


@tasks.loop(seconds=300)
async def poll_cwl_wars():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(CWL_GROUP_URL, headers=HEADERS) as cwl_resp:
                if cwl_resp.status != 200:
                    print(f"[ERROR] Failed to fetch CWL group info: {cwl_resp.status}")
                    return
                league_data = await cwl_resp.json()

            war_tags = [
                tag
                for round in league_data.get("rounds", [])
                for tag in round.get("warTags", [])
                if tag != "#0"
            ]
            if not war_tags:
                print("[INFO] No active war tags found.")
                return

            guild = bot.get_guild(int(config["guild_id"]))
            channel = guild.get_channel(int(config["announcement_channel_id"]))
            role = discord.utils.get(
                guild.roles, name=config.get("war_role", "active-war")
            )

            for war_tag in war_tags:
                war_url = f"https://api.clashofclans.com/v1/clanwarleagues/wars/{war_tag.replace('#', '%23')}"
                async with session.get(war_url, headers=HEADERS) as war_resp:
                    if war_resp.status != 200:
                        print(
                            f"[WARN] Failed to fetch war {war_tag}: {war_resp.status}"
                        )
                        continue
                    war_data = await war_resp.json()

                state = war_data.get("state")
                if state not in ["preparation", "inWar", "warEnded"]:
                    continue

                try:
                    end_time_raw = war_data.get("endTime") or war_data.get("startTime")
                    war_end = datetime.fromisoformat(
                        end_time_raw.replace("UTC", "+00:00")
                    )
                except Exception:
                    war_end = datetime.now(timezone.utc) + timedelta(hours=23)

                now = datetime.now(timezone.utc)
                time_left = war_end - now
                halfway = abs((time_left.total_seconds() - 43200)) < 300
                final_2hr = abs((time_left.total_seconds() - 7200)) < 300
                has_ended = state == "warEnded"

                our_clan = war_data.get("clan", {}).get("name", "Our Clan")
                enemy_clan = war_data.get("opponent", {}).get("name", "Enemy Clan")
                our_members = war_data.get("clan", {}).get("members", [])
                enemy_members = war_data.get("opponent", {}).get("members", [])

                def summarize_ths(members):
                    th_counts = {}
                    for m in members:
                        th = m.get("townhallLevel")
                        th_counts[th] = th_counts.get(th, 0) + 1
                    return " ".join(
                        f"{TH_EMOJIS.get(th, str(th))}x{count}"
                        for th, count in sorted(th_counts.items(), reverse=True)
                    )

                our_th_summary = summarize_ths(our_members)
                enemy_th_summary = summarize_ths(enemy_members)

                msg_key = (
                    f"{our_clan}: {our_th_summary}\n{enemy_clan}: {enemy_th_summary}"
                )

                for member in our_members:
                    tag = member.get("tag")
                    discord_id = user_map.get(tag)
                    if discord_id:
                        member_obj = guild.get_member(int(discord_id))
                        if member_obj and role:
                            await member_obj.add_roles(role)

                if last_messages.get(war_tag) != msg_key:
                    msg = (
                        f"📣 **CWL War Status** ({state})\n"
                        f"**{our_clan} vs {enemy_clan}** — {len(our_members)}v{len(enemy_members)}\n"
                        f"⏳ Starts or ends in: **{int(time_left.total_seconds() // 3600)}h {(time_left.total_seconds() % 3600) // 60:.0f}m**\n"
                        f"🔗 Tag: `{war_tag}`\n"
                        f"**{our_clan}**: {our_th_summary}\n"
                        f"**{enemy_clan}**: {enemy_th_summary}"
                    )
                    await channel.send(msg)
                    last_messages[war_tag] = msg_key
                    war_end_times[war_tag] = war_end

                # Halfway ping
                if state == "inWar" and halfway:
                    stars_us = war_data.get("clan", {}).get("stars", 0)
                    stars_them = war_data.get("opponent", {}).get("stars", 0)
                    destruction_us = war_data.get("clan", {}).get(
                        "destructionPercentage", 0
                    )
                    destruction_them = war_data.get("opponent", {}).get(
                        "destructionPercentage", 0
                    )
                    await channel.send(
                        f"⏳ **Halfway through the CWL war!**\n"
                        f"**{our_clan}**: ⭐ {stars_us} — 🏚 {destruction_us:.1f}%\n"
                        f"**{enemy_clan}**: ⭐ {stars_them} — 🏚 {destruction_them:.1f}%"
                    )

                # Final 2 hour ping
                if state == "inWar" and final_2hr:
                    two_attack_users = []
                    for member in our_members:
                        tag = member.get("tag")
                        discord_id = user_map.get(tag)
                        if discord_id and len(member.get("attacks", [])) == 0:
                            two_attack_users.append(f"<@{discord_id}>")
                    if two_attack_users:
                        await channel.send(
                            "⚠️ **2 hours left! The following still have 2 attacks:**\n"
                            + "\n".join(two_attack_users)
                        )

                # War ended cleanup
                if has_ended:
                    for tag, discord_id in user_map.items():
                        member_obj = guild.get_member(int(discord_id))
                        if member_obj and role:
                            await member_obj.remove_roles(role)
                    stars_us = war_data.get("clan", {}).get("stars", 0)
                    stars_them = war_data.get("opponent", {}).get("stars", 0)
                    destruction_us = war_data.get("clan", {}).get(
                        "destructionPercentage", 0
                    )
                    destruction_them = war_data.get("opponent", {}).get(
                        "destructionPercentage", 0
                    )

                    if stars_us > stars_them or (
                        stars_us == stars_them and destruction_us > destruction_them
                    ):
                        result_title = "🏆 **Victory!**"
                    elif stars_us < stars_them or (
                        stars_us == stars_them and destruction_us < destruction_them
                    ):
                        result_title = "💀 **Defeat!**"
                    else:
                        result_title = "⚖️ **Tie!**"

                    await channel.send(
                        f"⚔️ **CWL War has ended! Roles cleared.**\n"
                        f"**{our_clan}**: ⭐ {stars_us} — 🏚 {destruction_us:.1f}%\n"
                        f"**{enemy_clan}**: ⭐ {stars_them} — 🏚 {destruction_them:.1f}%\n"
                        f"{result_title}"
                    )

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
