import aiohttp
import discord
import urllib.parse
from discord.ext import commands, tasks
from discord import app_commands

TOKEN = "MTQ5MzMxNjkxMjY5OTE1MDUwOA.GCmuSF.zr8iNVcAdhUamVOgDIdxPkIWeWsJE0zHDcqmV0"

# =========================
# ALERT SETTINGS
# =========================
NATIONWIDE_ALERTS = True
ALERT_AREA = "FL"  # used only if NATIONWIDE_ALERTS = False
ALERT_CHECK_SECONDS = 30

IMPORTANT_ALERTS = {
    "Tornado Warning",
    "Severe Thunderstorm Warning",
    "Flash Flood Warning",
    "Hurricane Warning",
    "Tropical Storm Warning",
    "Tornado Watch",
    "Severe Thunderstorm Watch",
}

# =========================
# DISCORD INTENTS
# =========================
intents = discord.Intents.default()
intents.message_content = True


class SkywatchersBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.http_session = None
        self.posted_alert_ids = set()

    async def setup_hook(self):
        self.http_session = aiohttp.ClientSession(
            headers={
                "User-Agent": "SkywatchersDiscordBot/1.0",
                "Accept": "application/geo+json",
            }
        )
        await self.tree.sync()

    async def close(self):
        if self.http_session and not self.http_session.closed:
            await self.http_session.close()
        await super().close()


bot = SkywatchersBot()

# =========================
# SERVER CONFIG
# =========================
ROLE_NAMES = [
    "Admin",
    "Moderator",
    "Lead Forecaster",
    "Storm Chaser",
    "Radar Analyst",
    "Forecaster",
    "Spotter",
    "Beginner",
    "Severe Alerts",
    "Tornado Alerts",
    "Hurricane Alerts",
    "Outbreak Access",
]

SERVER_LAYOUT = {
    "📌 INFO": [
        "welcome",
        "announcements",
        "server-info",
        "verification",
        "rules",
        "interview-questionnaire",
    ],
    "🚨 LIVE WEATHER": [
        "live-alerts",
        "radar-feed",
        "velocity-radar",
        "storm-tracking",
        "tornado-reports",
        "damage-reports",
    ],
    "📊 FORECASTING": [
        "spc-outlooks",
        "model-discussion",
        "soundings-skewt",
        "mesoanalysis",
    ],
    "🌪️ STORM CHASING": [
        "chase-planning",
        "live-chase-chat",
        "chase-reports",
        "vehicle-setup",
    ],
    "📸 MEDIA": [
        "storm-photos",
        "storm-videos",
        "radar-gifs",
        "best-captures",
    ],
    "💬 COMMUNITY": [
        "general",
        "weather-chat",
        "off-topic",
        "bot-commands",
    ],
    "🎙️ VOICE": [
        "Live Chase VC",
        "Forecast Discussion",
        "General VC",
    ],
    "🛠️ STAFF": [
        "mod-chat",
        "report-queue",
        "server-logs",
        "staff-applications",
    ],
}

SELF_ROLES = {
    "stormchaser": "Storm Chaser",
    "radaranalyst": "Radar Analyst",
    "forecaster": "Forecaster",
    "spotter": "Spotter",
    "beginner": "Beginner",
    "severealerts": "Severe Alerts",
    "tornadoalerts": "Tornado Alerts",
    "hurricanealerts": "Hurricane Alerts",
}

OUTBREAK_OPEN_CHANNELS = {
    "live-alerts",
    "storm-tracking",
    "tornado-reports",
    "damage-reports",
    "radar-feed",
    "velocity-radar",
}

# =========================
# HELPERS
# =========================
def get_role(guild: discord.Guild, name: str):
    return discord.utils.get(guild.roles, name=name)


def get_text_channel(guild: discord.Guild, name: str):
    return discord.utils.get(guild.text_channels, name=name)


def get_category(guild: discord.Guild, name: str):
    return discord.utils.get(guild.categories, name=name)


def classify_alert(event_name: str) -> str:
    name = event_name.lower()
    if "tornado" in name:
        return "Tornado Alerts"
    if "hurricane" in name or "tropical storm" in name:
        return "Hurricane Alerts"
    return "Severe Alerts"


def get_alert_url() -> str:
    if NATIONWIDE_ALERTS:
        return "https://api.weather.gov/alerts/active"
    return f"https://api.weather.gov/alerts/active?area={ALERT_AREA}"


def build_radar_link() -> str:
    return "https://radar.weather.gov/"


def build_weathergov_link() -> str:
    return "https://www.weather.gov/"


def build_spc_link(event_name: str) -> str:
    name = event_name.lower()
    if "flash flood" in name:
        return "https://www.wpc.ncep.noaa.gov/"
    return "https://www.spc.noaa.gov/"


def build_nhc_link(event_name: str):
    name = event_name.lower()
    if "hurricane" in name or "tropical storm" in name:
        return "https://www.nhc.noaa.gov/"
    return None


def build_map_search_link(area_desc: str, event_name: str) -> str:
    query = urllib.parse.quote(f"{area_desc} {event_name} radar map")
    return f"https://www.google.com/search?q={query}"


def trim_text(text: str, max_len: int = 1000) -> str:
    if not text:
        return "None"
    return text[:max_len] + ("..." if len(text) > max_len else "")


async def ensure_role(guild: discord.Guild, role_name: str):
    role = get_role(guild, role_name)
    if role is None:
        role = await guild.create_role(name=role_name)
    return role


async def ensure_category(guild: discord.Guild, category_name: str):
    category = get_category(guild, category_name)
    if category is None:
        category = await guild.create_category(category_name)
    return category


async def ensure_text_channel(guild: discord.Guild, category: discord.CategoryChannel, channel_name: str):
    channel = get_text_channel(guild, channel_name)
    if channel is None:
        channel = await guild.create_text_channel(channel_name, category=category)
    return channel


async def ensure_voice_channel(guild: discord.Guild, category: discord.CategoryChannel, channel_name: str):
    channel = discord.utils.get(guild.voice_channels, name=channel_name)
    if channel is None:
        channel = await guild.create_voice_channel(channel_name, category=category)
    return channel


# =========================
# EVENTS
# =========================
@bot.event
async def on_ready():
    if not nws_alert_loop.is_running():
        nws_alert_loop.start()
    print(f"✅ Logged in as {bot.user}")


# =========================
# SETUP / CLEANUP
# =========================
@bot.command()
@commands.has_permissions(administrator=True)
async def setup(ctx):
    guild = ctx.guild
    if guild is None:
        return

    await ctx.send("⚙️ Building Skywatchers server...")

    for role_name in ROLE_NAMES:
        await ensure_role(guild, role_name)

    for category_name, channels in SERVER_LAYOUT.items():
        category = await ensure_category(guild, category_name)
        for channel_name in channels:
            if category_name == "🎙️ VOICE":
                await ensure_voice_channel(guild, category, channel_name)
            else:
                await ensure_text_channel(guild, category, channel_name)

    welcome = get_text_channel(guild, "welcome")
    if welcome:
        embed = discord.Embed(
            title="🌪️ Welcome to Skywatchers",
            description=(
                "Welcome to **Skywatchers** — a severe weather community for forecasts, live tracking, storm reports, radar discussion, and chasing.\n\n"
                "Use `/role` to assign yourself weather roles and alert pings."
            ),
        )
        await welcome.send(embed=embed)

    server_info = get_text_channel(guild, "server-info")
    if server_info:
        embed = discord.Embed(
            title="📘 Server Info",
            description=(
                "**What you'll find here:**\n"
                "• Live severe weather alerts\n"
                "• Radar and velocity discussion\n"
                "• Forecast/model analysis\n"
                "• Storm chasing chat\n"
                "• Photo and video sharing\n\n"
                "**Useful commands:**\n"
                "`!setup`\n"
                "`!cleanupskywatchers`\n"
                "`!setnationwide`\n"
                "`!setarea FL`\n"
                "`!alert tornado Your message here`\n"
                "`!outbreak_on`\n"
                "`!outbreak_off`\n"
                "`!apply your answers here`"
            ),
        )
        await server_info.send(embed=embed)

    verification = get_text_channel(guild, "verification")
    if verification:
        embed = discord.Embed(
            title="✅ Self-Assign Roles",
            description=(
                "Use these slash commands:\n\n"
                "`/role stormchaser`\n"
                "`/role radaranalyst`\n"
                "`/role forecaster`\n"
                "`/role spotter`\n"
                "`/role beginner`\n"
                "`/role severealerts`\n"
                "`/role tornadoalerts`\n"
                "`/role hurricanealerts`\n\n"
                "Remove one with:\n"
                "`/removerole stormchaser`"
            ),
        )
        await verification.send(embed=embed)

    rules_channel = get_text_channel(guild, "rules")
    if rules_channel:
        embed = discord.Embed(
            title="📜 Skywatchers Rules",
            description=(
                "**1. Be respectful**\n"
                "No harassment, hate speech, or personal attacks.\n\n"
                "**2. No fake reports**\n"
                "Do not post false warnings, fake tornado sightings, or misleading weather information.\n\n"
                "**3. Keep severe weather channels serious**\n"
                "During active events, keep live channels focused on real weather discussion.\n\n"
                "**4. No spam**\n"
                "Avoid message flooding, repeated pings, or off-topic clutter.\n\n"
                "**5. Use the correct channels**\n"
                "Radar goes in radar channels, reports in report channels, forecasts in forecast channels, and media in media channels.\n\n"
                "**6. Safety first**\n"
                "Do not encourage reckless storm chasing or dangerous behavior.\n\n"
                "**7. Staff decisions stand**\n"
                "Listen to moderators and admins when they redirect or stop a discussion.\n\n"
                "**8. Follow Discord's rules**\n"
                "Anything against Discord rules is also against Skywatchers rules."
            ),
        )
        embed.set_footer(text="Breaking rules may result in warnings, mutes, or bans.")
        await rules_channel.send(embed=embed)

    questionnaire_channel = get_text_channel(guild, "interview-questionnaire")
    if questionnaire_channel:
        embed = discord.Embed(
            title="📝 Interview Questionnaire",
            description=(
                "If you want to apply for staff or a trusted role, answer these questions:\n\n"
                "**1. What should we call you?**\n\n"
                "**2. What role are you applying for?**\n\n"
                "**3. How long have you been interested in weather or storm chasing?**\n\n"
                "**4. Do you have forecasting, radar, spotting, or moderation experience?**\n\n"
                "**5. Have you been staff in another Discord server before?**\n\n"
                "**6. How active can you be each week?**\n\n"
                "**7. How would you handle misinformation during a severe weather event?**\n\n"
                "**8. Why do you want this role in Skywatchers?**\n\n"
                "**9. What makes you a good fit?**\n\n"
                "**10. Anything else you want staff to know?**"
            ),
        )
        embed.set_footer(text="Use !apply to submit your answers.")
        await questionnaire_channel.send(embed=embed)

    await ctx.send("🌪️ Setup complete.")


@bot.command()
@commands.has_permissions(administrator=True)
async def cleanupskywatchers(ctx):
    guild = ctx.guild
    if guild is None:
        return

    await ctx.send("🧹 Cleaning Skywatchers setup...")

    categories_to_delete = list(SERVER_LAYOUT.keys())
    roles_to_delete = set(ROLE_NAMES)

    for category in list(guild.categories):
        if category.name in categories_to_delete:
            for channel in list(category.channels):
                await channel.delete()
            await category.delete()

    for role in list(guild.roles):
        if role.name in roles_to_delete:
            try:
                await role.delete()
            except discord.Forbidden:
                pass
            except discord.HTTPException:
                pass

    await ctx.send("✅ Cleanup complete. Run `!setup` again.")


# =========================
# MANUAL ALERTS / SETTINGS
# =========================
@bot.command()
@commands.has_permissions(administrator=True)
async def alert(ctx, alert_type: str, *, message: str):
    guild = ctx.guild
    if guild is None:
        return

    channel = get_text_channel(guild, "live-alerts")
    if channel is None:
        await ctx.send("❌ Could not find #live-alerts")
        return

    role_map = {
        "severe": "Severe Alerts",
        "tornado": "Tornado Alerts",
        "hurricane": "Hurricane Alerts",
    }

    role_name = role_map.get(alert_type.lower())
    role = get_role(guild, role_name) if role_name else None
    mention = role.mention if role else "@here"

    embed = discord.Embed(
        title=f"🚨 {alert_type.upper()} ALERT",
        description=message,
    )
    embed.set_footer(text=f"Sent by {ctx.author.display_name}")

    await channel.send(content=mention, embed=embed)
    await ctx.send("✅ Alert sent.")


@bot.command()
@commands.has_permissions(administrator=True)
async def setarea(ctx, area_code: str):
    global ALERT_AREA, NATIONWIDE_ALERTS
    ALERT_AREA = area_code.upper()
    NATIONWIDE_ALERTS = False
    bot.posted_alert_ids.clear()
    await ctx.send(f"✅ Alerts now set to **{ALERT_AREA}** only.")


@bot.command()
@commands.has_permissions(administrator=True)
async def setnationwide(ctx):
    global NATIONWIDE_ALERTS
    NATIONWIDE_ALERTS = True
    bot.posted_alert_ids.clear()
    await ctx.send("✅ Alerts now set to **nationwide U.S.**")


# =========================
# OUTBREAK MODE
# =========================
@bot.command()
@commands.has_permissions(administrator=True)
async def outbreak_on(ctx):
    guild = ctx.guild
    if guild is None:
        return

    everyone = guild.default_role

    for channel in guild.text_channels:
        if channel.name not in OUTBREAK_OPEN_CHANNELS and channel.category and channel.category.name != "🛠️ STAFF":
            await channel.set_permissions(everyone, send_messages=False)

    await ctx.send("🚨 Outbreak mode ON")


@bot.command()
@commands.has_permissions(administrator=True)
async def outbreak_off(ctx):
    guild = ctx.guild
    if guild is None:
        return

    everyone = guild.default_role

    for channel in guild.text_channels:
        if channel.category and channel.category.name != "🛠️ STAFF":
            await channel.set_permissions(everyone, overwrite=None)

    await ctx.send("✅ Outbreak mode OFF")


# =========================
# APPLICATION COMMAND
# =========================
@bot.command()
async def apply(ctx, *, answers: str):
    guild = ctx.guild
    if guild is None:
        return

    app_channel = get_text_channel(guild, "staff-applications")
    if app_channel is None:
        await ctx.send("❌ Could not find #staff-applications")
        return

    embed = discord.Embed(
        title="📨 New Application",
        description=trim_text(answers, 3500),
    )
    embed.set_footer(text=f"Submitted by {ctx.author.display_name}")
    await app_channel.send(embed=embed)
    await ctx.send("✅ Your application was submitted.")


# =========================
# SLASH COMMANDS
# =========================
@bot.tree.command(name="role", description="Give yourself a role")
@app_commands.describe(role_key="Example: stormchaser, tornadoalerts, forecaster")
async def role_command(interaction: discord.Interaction, role_key: str):
    if interaction.guild is None:
        await interaction.response.send_message("This only works inside a server.", ephemeral=True)
        return

    role_name = SELF_ROLES.get(role_key.lower())
    if not role_name:
        await interaction.response.send_message("❌ Role not found.", ephemeral=True)
        return

    role = get_role(interaction.guild, role_name)
    if role is None:
        await interaction.response.send_message("❌ Role not found.", ephemeral=True)
        return

    member = interaction.user
    if isinstance(member, discord.Member):
        if role in member.roles:
            await interaction.response.send_message(f"You already have **{role_name}**.", ephemeral=True)
            return
        await member.add_roles(role, reason="Self-assigned role")
        await interaction.response.send_message(f"✅ Added **{role_name}**.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Could not assign role.", ephemeral=True)


@bot.tree.command(name="removerole", description="Remove one of your roles")
@app_commands.describe(role_key="Example: stormchaser, tornadoalerts, forecaster")
async def remove_role_command(interaction: discord.Interaction, role_key: str):
    if interaction.guild is None:
        await interaction.response.send_message("This only works inside a server.", ephemeral=True)
        return

    role_name = SELF_ROLES.get(role_key.lower())
    if not role_name:
        await interaction.response.send_message("❌ Role not found.", ephemeral=True)
        return

    role = get_role(interaction.guild, role_name)
    if role is None:
        await interaction.response.send_message("❌ Role not found.", ephemeral=True)
        return

    member = interaction.user
    if isinstance(member, discord.Member):
        if role not in member.roles:
            await interaction.response.send_message(f"You do not have **{role_name}**.", ephemeral=True)
            return
        await member.remove_roles(role, reason="Self-removed role")
        await interaction.response.send_message(f"✅ Removed **{role_name}**.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Could not remove role.", ephemeral=True)


@bot.tree.command(name="serverstatus", description="Show server status")
async def server_status(interaction: discord.Interaction):
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("This only works inside a server.", ephemeral=True)
        return

    embed = discord.Embed(
        title="Skywatchers Server Status",
        description=(
            f"Members: **{guild.member_count}**\n"
            f"Roles: **{len(guild.roles)}**\n"
            f"Text Channels: **{len(guild.text_channels)}**\n"
            f"Voice Channels: **{len(guild.voice_channels)}**"
        ),
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="stormreport", description="Post a storm report")
@app_commands.describe(report="Your storm report")
async def storm_report(interaction: discord.Interaction, report: str):
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("This only works inside a server.", ephemeral=True)
        return

    reports_channel = get_text_channel(guild, "tornado-reports")
    if reports_channel is None:
        await interaction.response.send_message("❌ Could not find #tornado-reports", ephemeral=True)
        return

    embed = discord.Embed(
        title="🌪️ New Storm Report",
        description=report,
    )
    embed.set_footer(text=f"Reported by {interaction.user.display_name}")

    await reports_channel.send(embed=embed)
    await interaction.response.send_message("✅ Report posted.", ephemeral=True)


# =========================
# LIVE NWS ALERT LOOP
# =========================
@tasks.loop(seconds=ALERT_CHECK_SECONDS)
async def nws_alert_loop():
    if bot.http_session is None:
        return

    url = get_alert_url()

    try:
        async with bot.http_session.get(url) as resp:
            if resp.status != 200:
                print(f"NWS request failed: {resp.status}")
                return

            data = await resp.json()
            features = data.get("features", [])

            for feature in features:
                props = feature.get("properties", {})
                alert_id = props.get("id") or feature.get("id")

                if not alert_id or alert_id in bot.posted_alert_ids:
                    continue

                event = props.get("event", "Weather Alert")
                if event not in IMPORTANT_ALERTS:
                    continue

                headline = props.get("headline", event)
                description = props.get("description", "No description provided.")
                instruction = props.get("instruction", "")
                severity = props.get("severity", "Unknown")
                urgency = props.get("urgency", "Unknown")
                certainty = props.get("certainty", "Unknown")
                area_desc = props.get("areaDesc", "Unknown area")
                sent = props.get("sent", "Unknown")
                expires = props.get("expires", "Unknown")
                sender = props.get("senderName", "NWS")
                nws_link = props.get("url", "")

                role_name = classify_alert(event)
                radar_link = build_radar_link()
                weathergov_link = build_weathergov_link()
                spc_link = build_spc_link(event)
                nhc_link = build_nhc_link(event)
                map_search_link = build_map_search_link(area_desc, event)

                embed = discord.Embed(
                    title=f"🚨 {event}",
                    description=headline,
                )
                embed.add_field(name="Area", value=trim_text(area_desc, 1024), inline=False)
                embed.add_field(name="Severity", value=severity, inline=True)
                embed.add_field(name="Urgency", value=urgency, inline=True)
                embed.add_field(name="Certainty", value=certainty, inline=True)
                embed.add_field(name="Sent", value=sent, inline=False)
                embed.add_field(name="Expires", value=expires, inline=False)
                embed.add_field(name="Details", value=trim_text(description), inline=False)

                if instruction:
                    embed.add_field(name="Instructions", value=trim_text(instruction), inline=False)

                links = [
                    f"[National Radar]({radar_link})",
                    f"[Weather.gov]({weathergov_link})",
                    f"[Radar/Map Search]({map_search_link})",
                    f"[SPC / WPC]({spc_link})",
                ]

                if nhc_link:
                    links.append(f"[NHC]({nhc_link})")

                if nws_link:
                    links.append(f"[Official NWS Alert]({nws_link})")

                embed.add_field(name="Links", value="\n".join(links), inline=False)
                embed.set_footer(text=sender)

                for guild in bot.guilds:
                    channel = get_text_channel(guild, "live-alerts")
                    if channel is None:
                        continue

                    role = get_role(guild, role_name)
                    mention = role.mention if role else "@here"
                    await channel.send(content=mention, embed=embed)

                bot.posted_alert_ids.add(alert_id)

    except Exception as e:
        print(f"Alert loop error: {e}")


@nws_alert_loop.before_loop
async def before_nws_alert_loop():
    await bot.wait_until_ready()


# =========================
# RUN
# =========================
bot.run(TOKEN)