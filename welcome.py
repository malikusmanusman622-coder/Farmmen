import discord
from discord.ext import commands
from discord import app_commands
from config import WELCOME_CHANNEL_NAME, DEFAULT_MEMBER_ROLE, ROLE_COLORS, DISCORD_OWNER_ID
import random


WELCOME_COLORS = [0x5865F2, 0x57F287, 0xFEE75C, 0xEB459E, 0xED4245]


def welcome_embed(member: discord.Member) -> discord.Embed:
    guild = member.guild
    color = random.choice(WELCOME_COLORS)

    embed = discord.Embed(
        title=f"👋 Welcome to {guild.name}!",
        description=(
            f"Hey {member.mention}, we're glad you're here!\n\n"
            f"You are member **#{guild.member_count:,}** to join.\n"
            f"Make sure to read the server rules and get authorized!"
        ),
        color=color,
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    if guild.icon:
        embed.set_author(name=guild.name, icon_url=guild.icon.url)
    embed.add_field(
        name="🔑 Get Access",
        value="Use `!lauth` or `/lauth` to authorize your account\nand unlock farming commands.",
        inline=False,
    )
    embed.set_footer(
        text=f"Joined • {discord.utils.utcnow().strftime('%B %d, %Y')}",
        icon_url=member.display_avatar.url,
    )
    embed.timestamp = discord.utils.utcnow()
    return embed


async def send_welcome(member: discord.Member):
    channel = discord.utils.get(member.guild.text_channels, name=WELCOME_CHANNEL_NAME)
    if channel is None:
        channel = discord.utils.get(member.guild.text_channels, name="general")
    if channel is None and member.guild.system_channel:
        channel = member.guild.system_channel
    if channel is None:
        return
    try:
        await channel.send(embed=welcome_embed(member))
    except discord.Forbidden:
        pass


class WelcomeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _is_owner(self, user):
        return user.id == DISCORD_OWNER_ID

    @commands.command(name="welcome")
    async def welcome_prefix(self, ctx: commands.Context, member: discord.Member = None):
        if not self._is_owner(ctx.author):
            await ctx.reply(embed=discord.Embed(title="❌ Access Denied", description="Only the bot owner can use this command.", color=0xFF4444))
            return
        target = member or ctx.author
        await ctx.send(embed=welcome_embed(target))

    @app_commands.command(name="welcome", description="[Owner only] Send a welcome message for a member")
    @app_commands.describe(member="The member to welcome")
    async def welcome_slash(self, interaction: discord.Interaction, member: discord.Member = None):
        if not self._is_owner(interaction.user):
            await interaction.response.send_message(embed=discord.Embed(title="❌ Access Denied", description="Only the bot owner can use this command.", color=0xFF4444), ephemeral=True)
            return
        target = member or interaction.user
        await interaction.response.send_message(embed=welcome_embed(target))

    @commands.command(name="setwelcome")
    async def setwelcome_prefix(self, ctx: commands.Context):
        if not self._is_owner(ctx.author):
            await ctx.reply(embed=discord.Embed(title="❌ Access Denied", description="Only the bot owner can configure welcome settings.", color=0xFF4444))
            return
        await ctx.reply(embed=self._setwelcome_embed())

    @app_commands.command(name="setwelcome", description="[Owner only] View welcome system configuration")
    async def setwelcome_slash(self, interaction: discord.Interaction):
        if not self._is_owner(interaction.user):
            await interaction.response.send_message(embed=discord.Embed(title="❌ Access Denied", description="Only the bot owner can configure welcome settings.", color=0xFF4444), ephemeral=True)
            return
        await interaction.response.send_message(embed=self._setwelcome_embed(), ephemeral=True)

    def _setwelcome_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="⚙️ Welcome System Configuration",
            description=(
                f"Welcome messages are sent to **#{WELCOME_CHANNEL_NAME}**.\n\n"
                f"Create a channel named `{WELCOME_CHANNEL_NAME}` in your server "
                f"and the bot will automatically send welcome messages there when members join.\n\n"
                f"Fallback order: `#{WELCOME_CHANNEL_NAME}` → `#general` → system channel"
            ),
            color=0x57F287,
        )
        embed.set_footer(text="Owner-only configuration")
        return embed


async def setup(bot: commands.Bot):
    await bot.add_cog(WelcomeCog(bot))
