import discord
from discord.ext import commands
from discord import app_commands
from config import (
    DISCORD_CLIENT_ID, OAUTH_REDIRECT_URI, OAUTH_SCOPES,
    DEFAULT_MEMBER_ROLE
)
from database import is_authorized, get_authorized_count


def build_oauth_url() -> str:
    return (
        f"https://discord.com/api/oauth2/authorize"
        f"?client_id={DISCORD_CLIENT_ID}"
        f"&redirect_uri={OAUTH_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope={OAUTH_SCOPES}"
    )


def build_invite_url() -> str:
    return (
        f"https://discord.com/api/oauth2/authorize"
        f"?client_id={DISCORD_CLIENT_ID}"
        f"&permissions=8"
        f"&scope=bot+applications.commands"
    )


class AuthView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

        self.add_item(discord.ui.Button(
            label="Add Bot to Server",
            style=discord.ButtonStyle.blurple,
            emoji="🤖",
            url=build_invite_url(),
            row=0,
        ))

        self.add_item(discord.ui.Button(
            label="Authorize Account",
            style=discord.ButtonStyle.green,
            emoji="🔑",
            url=build_oauth_url(),
            row=0,
        ))


def lauth_embed(authorized_count: int) -> discord.Embed:
    embed = discord.Embed(
        title="🔐 Farm Bot — Authorization Panel",
        description=(
            "Welcome! Use the buttons below to get started.\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=0x5865F2,
    )
    embed.add_field(
        name="🤖 Add Bot to Server",
        value="Invite the bot to your server so it can farm members into it.",
        inline=False,
    )
    embed.add_field(
        name="🔑 Authorize Account",
        value=(
            "Link your Discord account so the bot can add you to servers.\n"
            "You'll automatically receive the **Member** role after authorizing."
        ),
        inline=False,
    )
    embed.add_field(
        name="📊 Authorized Members",
        value=f"**{authorized_count:,}** members have authorized so far.",
        inline=False,
    )
    embed.set_footer(text="Both ! prefix and / slash commands are supported.")
    embed.timestamp = discord.utils.utcnow()
    return embed


class AuthCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="lauth")
    async def lauth_prefix(self, ctx: commands.Context):
        count = await get_authorized_count()
        await ctx.reply(embed=lauth_embed(count), view=AuthView())

    @app_commands.command(name="lauth", description="Get buttons to add the bot or authorize your account")
    async def lauth_slash(self, interaction: discord.Interaction):
        count = await get_authorized_count()
        await interaction.response.send_message(embed=lauth_embed(count), view=AuthView())

    @commands.command(name="auth")
    async def auth_prefix(self, ctx: commands.Context):
        already = await is_authorized(str(ctx.author.id))
        if already:
            embed = discord.Embed(
                title="✅ Already Authorized",
                description=(
                    "Your account is already authorized!\n"
                    "You can use `!farm <server_id>` to start farming."
                ),
                color=0x57F287,
            )
            embed.set_footer(text=f"Authorized as {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
            await ctx.reply(embed=embed)
            return

        embed = discord.Embed(
            title="🔑 Authorize Your Account",
            description=(
                "Click the button below to authorize your Discord account.\n\n"
                "After authorization you will **automatically receive the Member role**\n"
                "and gain access to farming commands."
            ),
            color=0x5865F2,
        )
        embed.set_footer(text="Your account info is stored securely.")
        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(label="Authorize Now", emoji="🔑", style=discord.ButtonStyle.green, url=build_oauth_url()))
        await ctx.reply(embed=embed, view=view)

    @app_commands.command(name="auth", description="Authorize your account to use farming commands")
    async def auth_slash(self, interaction: discord.Interaction):
        already = await is_authorized(str(interaction.user.id))
        if already:
            embed = discord.Embed(
                title="✅ Already Authorized",
                description="Your account is already authorized! Use `/farm` to start farming.",
                color=0x57F287,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title="🔑 Authorize Your Account",
            description=(
                "Click the button below to link your Discord account.\n\n"
                "After authorization you will **automatically receive the Member role**\n"
                "and gain access to farming commands."
            ),
            color=0x5865F2,
        )
        embed.set_footer(text="Your account info is stored securely.")
        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(label="Authorize Now", emoji="🔑", style=discord.ButtonStyle.green, url=build_oauth_url()))
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AuthCog(bot))
