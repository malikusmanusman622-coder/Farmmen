import asyncio
import logging
import discord
from discord.ext import commands
from config import DISCORD_BOT_TOKEN, PREFIX, DISCORD_OWNER_ID, DEFAULT_MEMBER_ROLE, ROLE_COLORS
from database import init_db, is_authorized
from oauth_server import start_oauth_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True


class FarmBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=PREFIX,
            intents=intents,
            help_command=None,
            owner_id=DISCORD_OWNER_ID,
        )

    async def setup_hook(self):
        await self.load_extension("cogs.farm")
        await self.load_extension("cogs.auth")
        await self.load_extension("cogs.roles")
        await self.load_extension("cogs.welcome")
        await self.tree.sync()
        logger.info("All cogs loaded & slash commands synced globally.")

    async def on_ready(self):
        logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        logger.info(" Farm Bot online: %s (ID: %s)", self.user, self.user.id)
        logger.info(" Servers: %d", len(self.guilds))
        logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        await self.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"!lauth | {len(self.guilds)} servers",
            ),
        )

    async def on_guild_join(self, guild: discord.Guild):
        logger.info("Joined new server: %s (ID: %s, Members: %d)", guild.name, guild.id, guild.member_count)
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"!lauth | {len(self.guilds)} servers",
            )
        )
        channel = (
            discord.utils.get(guild.text_channels, name="general")
            or guild.system_channel
            or next((c for c in guild.text_channels if c.permissions_for(guild.me).send_messages), None)
        )
        if channel:
            embed = discord.Embed(
                title="👋 Thanks for adding Farm Bot!",
                description=(
                    "I'm ready to start farming members into your server.\n\n"
                    "**Quick Start:**\n"
                    "1️⃣ Use `!lauth` to get authorization buttons\n"
                    "2️⃣ Have members click **Authorize Account**\n"
                    "3️⃣ Use `!farm <server_id>` to farm them here\n\n"
                    "Use `!help` to see all available commands."
                ),
                color=0x5865F2,
            )
            embed.set_thumbnail(url=self.user.display_avatar.url)
            embed.set_footer(text="Farm Bot • Both ! and / commands supported")
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                pass

    async def on_member_join(self, member: discord.Member):
        from cogs.welcome import send_welcome
        await send_welcome(member)

        if await is_authorized(str(member.id)):
            await _assign_role(member, DEFAULT_MEMBER_ROLE, "Authorized user rejoined")
            logger.info("Auto-assigned Member role to returning authorized user: %s", member.display_name)

    async def on_command_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingRequiredArgument):
            embed = discord.Embed(
                title="❌ Missing Argument",
                description=f"Missing: **{error.param.name}**\nUse `!help` for command usage.",
                color=0xFF4444,
            )
            await ctx.reply(embed=embed)
        elif isinstance(error, commands.CommandNotFound):
            pass
        elif isinstance(error, commands.BadArgument):
            embed = discord.Embed(title="❌ Bad Argument", description=str(error), color=0xFF4444)
            await ctx.reply(embed=embed)
        elif isinstance(error, commands.MemberNotFound):
            embed = discord.Embed(title="❌ Member Not Found", description="Could not find that member.", color=0xFF4444)
            await ctx.reply(embed=embed)
        else:
            logger.error("Unhandled command error: %s", error, exc_info=True)


async def _assign_role(member: discord.Member, role_name: str, reason: str):
    guild = member.guild
    role = discord.utils.get(guild.roles, name=role_name)
    if role is None:
        color = discord.Colour(ROLE_COLORS.get(role_name, 0x5865F2))
        try:
            role = await guild.create_role(name=role_name, color=color, reason="Auto-created by Farm Bot")
        except discord.Forbidden:
            logger.warning("No permission to create role '%s' in %s", role_name, guild.name)
            return
    if role not in member.roles:
        try:
            await member.add_roles(role, reason=reason)
        except discord.Forbidden:
            logger.warning("No permission to assign role '%s' in %s", role_name, guild.name)


bot = FarmBot()


def _build_help_embed(user: discord.User | discord.Member) -> discord.Embed:
    embed = discord.Embed(
        title="📖 Farm Bot — Command Reference",
        description=(
            "All commands work as both `!prefix` and `/slash`.\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=0x5865F2,
    )
    embed.add_field(
        name="✅ Member Commands — everyone can use these",
        value=(
            "`!lauth` / `/lauth` — Authorization panel (Add Bot + Auth buttons)\n"
            "`!auth` / `/auth` — Get your personal authorization link\n"
            "`!farm <server_id>` / `/farm` — Farm members into a server"
        ),
        inline=False,
    )
    embed.add_field(
        name="👑 Owner-Only Commands",
        value=(
            "`!giverole @user <tier>` / `/giverole` — Assign a tier role\n"
            "`!tiers` / `/tiers` — View all role tiers & limits\n"
            "`!pool [page]` / `/pool` — View the authorized member pool\n"
            "`!stats` / `/stats` — Bot statistics\n"
            "`!welcome [@member]` / `/welcome` — Send a welcome message\n"
            "`!setwelcome` / `/setwelcome` — Welcome system config"
        ),
        inline=False,
    )
    embed.add_field(
        name="👑 Owner-Only — Force Authorization",
        value=(
            "`!forceauthall` / `/forceauthall` — Authorize every member in the server\n"
            "`!forceauthname <name>` / `/forceauthname` — Authorize by username\n"
            "`!forceauth <id> [name]` / `/forceauth` — Authorize by user ID\n"
            "`!forceunauth <id>` / `/forceunauth` — Revoke authorization"
        ),
        inline=False,
    )
    embed.add_field(
        name="🏅 Tier Limits",
        value=(
            "👑 Premium `35`  •  💎 Diamond `25`  •  🥇 Gold `15`\n"
            "🥈 Silver `10`  •  👤 Member `2`  — members per farm command"
        ),
        inline=False,
    )
    embed.set_footer(
        text=f"Farm Bot • Requested by {user.display_name}",
        icon_url=user.display_avatar.url,
    )
    embed.timestamp = discord.utils.utcnow()
    return embed


@bot.command(name="help")
async def help_cmd(ctx: commands.Context):
    await ctx.reply(embed=_build_help_embed(ctx.author))


@bot.tree.command(name="help", description="Show all available commands")
async def help_slash(interaction: discord.Interaction):
    await interaction.response.send_message(embed=_build_help_embed(interaction.user), ephemeral=True)


async def main():
    await init_db()
    async with bot:
        await start_oauth_server(app_bot=bot)
        await bot.start(DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
