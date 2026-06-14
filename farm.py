import discord
from discord.ext import commands
from discord import app_commands
from database import is_authorized, log_farm, get_authorized_with_tokens, get_token_count
from config import ROLE_LIMITS, ROLE_ORDER, ROLE_EMOJIS, DISCORD_BOT_TOKEN
import aiohttp
import asyncio
import logging

logger = logging.getLogger(__name__)


def get_farm_limit(member: discord.Member) -> tuple[int, str]:
    role_names = [r.name for r in member.roles]
    for tier in ROLE_ORDER:
        if tier in role_names:
            return ROLE_LIMITS[tier], tier
    return 0, "none"


async def add_member_to_guild(session: aiohttp.ClientSession,
                               guild_id: int, user_id: int,
                               access_token: str) -> str:
    """
    Use Discord REST API to add a user to a guild.
    Returns: 'added' | 'already' | 'error'
    """
    url = f"https://discord.com/api/v10/guilds/{guild_id}/members/{user_id}"
    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {"access_token": access_token}

    try:
        async with session.put(url, json=payload, headers=headers) as resp:
            if resp.status == 201:
                return "added"
            elif resp.status == 204:
                return "already"
            elif resp.status == 429:
                # Rate limited — wait and retry once
                retry_after = float((await resp.json()).get("retry_after", 1))
                await asyncio.sleep(retry_after)
                async with session.put(url, json=payload, headers=headers) as r2:
                    return "added" if r2.status == 201 else ("already" if r2.status == 204 else "error")
            else:
                body = await resp.text()
                logger.warning("Add member %s failed: %s — %s", user_id, resp.status, body)
                return "error"
    except Exception as e:
        logger.error("Exception adding member %s: %s", user_id, e)
        return "error"


async def do_farm(ctx_or_interaction, server_id: str):
    is_slash = isinstance(ctx_or_interaction, discord.Interaction)

    if is_slash:
        user  = ctx_or_interaction.user
        guild = ctx_or_interaction.guild
        bot   = ctx_or_interaction.client
    else:
        user  = ctx_or_interaction.author
        guild = ctx_or_interaction.guild
        bot   = ctx_or_interaction.bot

    async def send(embed, ephemeral=False):
        if is_slash:
            if ctx_or_interaction.response.is_done():
                await ctx_or_interaction.followup.send(embed=embed, ephemeral=ephemeral)
            else:
                await ctx_or_interaction.response.send_message(embed=embed, ephemeral=ephemeral)
        else:
            await ctx_or_interaction.reply(embed=embed)

    # --- Guard: caller must be authorized ---
    if not await is_authorized(str(user.id)):
        await send(discord.Embed(
            title="❌ Not Authorized",
            description=(
                "You need to authorize your account first.\n\n"
                "Use `!auth` or click **Auth Bot** in `!lauth`."
            ),
            color=0xFF4444,
        ), ephemeral=True)
        return

    # --- Guard: must be in a guild ---
    if guild is None:
        await send(discord.Embed(title="❌ Server Only", description="Use this inside a server.", color=0xFF4444))
        return

    member = guild.get_member(user.id)
    if member is None:
        await send(discord.Embed(title="❌ Error", description="Could not fetch your member info.", color=0xFF4444))
        return

    # --- Guard: check tier ---
    limit, tier = get_farm_limit(member)
    if limit == 0:
        await send(discord.Embed(
            title="❌ No Role Tier",
            description="You don't have a tier role. Ask the owner to assign one with `!giverole`.",
            color=0xFF4444,
        ))
        return

    # --- Guard: valid server ID ---
    try:
        target_id = int(server_id)
    except ValueError:
        await send(discord.Embed(title="❌ Invalid ID", description="Server ID must be a number.", color=0xFF4444))
        return

    # --- Guard: bot must be in target server ---
    target_guild = bot.get_guild(target_id)
    if target_guild is None:
        await send(discord.Embed(
            title="❌ Bot Not in Server",
            description=(
                f"Bot is not in server `{server_id}`.\n\n"
                "Add the bot to that server first using `!lauth` → **Add Bot**."
            ),
            color=0xFF4444,
        ))
        return

    # --- Check available tokens in pool ---
    pool_size = await get_token_count()
    if pool_size == 0:
        await send(discord.Embed(
            title="⚠️ Empty Token Pool",
            description=(
                "No authorized members with OAuth tokens yet.\n\n"
                "Members need to click **Auth Bot** (not just be force-authed) "
                "so their account token is stored."
            ),
            color=0xFEE75C,
        ))
        return

    tier_emoji = ROLE_EMOJIS.get(tier, "🏅")
    actual_limit = min(limit, pool_size)

    # Send progress embed
    progress = discord.Embed(
        title="⏳ Farming in progress…",
        description=(
            f"Adding up to **{actual_limit}** members to **{target_guild.name}**\n"
            f"Tier: {tier_emoji} **{tier}** • Pool: **{pool_size}** with tokens"
        ),
        color=0xFEE75C,
    )
    progress.set_thumbnail(url=target_guild.icon.url if target_guild.icon else None)
    progress.timestamp = discord.utils.utcnow()

    if is_slash:
        await ctx_or_interaction.response.send_message(embed=progress)
        edit_msg = await ctx_or_interaction.original_response()
    else:
        edit_msg = await ctx_or_interaction.reply(embed=progress)

    # --- Actually farm ---
    pool = await get_authorized_with_tokens(actual_limit)
    added = 0
    already = 0
    errors = 0

    async with aiohttp.ClientSession() as session:
        for entry in pool:
            result = await add_member_to_guild(
                session, target_id,
                int(entry["user_id"]),
                entry["access_token"],
            )
            if result == "added":
                added += 1
            elif result == "already":
                already += 1
            else:
                errors += 1
            # Small delay to avoid rate limits
            await asyncio.sleep(0.5)

    await log_farm(str(user.id), server_id, added)

    # --- Result embed ---
    color = 0x57F287 if added > 0 else (0xFEE75C if already > 0 else 0xFF4444)
    result_embed = discord.Embed(
        title="🌾 Farm Complete",
        color=color,
    )
    result_embed.add_field(
        name="🎯 Target Server",
        value=f"**{target_guild.name}**\n`{server_id}`",
        inline=True,
    )
    result_embed.add_field(
        name=f"{tier_emoji} Tier",
        value=f"**{tier}**",
        inline=True,
    )
    result_embed.add_field(name="\u200b", value="\u200b", inline=True)
    result_embed.add_field(name="✅ Added", value=f"**{added}**", inline=True)
    result_embed.add_field(name="👥 Already In", value=f"**{already}**", inline=True)
    result_embed.add_field(name="❌ Failed", value=f"**{errors}**", inline=True)
    result_embed.set_thumbnail(url=target_guild.icon.url if target_guild.icon else None)
    result_embed.set_footer(
        text=f"Requested by {user.display_name}",
        icon_url=user.display_avatar.url,
    )
    result_embed.timestamp = discord.utils.utcnow()
    await edit_msg.edit(embed=result_embed)


class FarmCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="farm")
    async def farm_prefix(self, ctx: commands.Context, server_id: str = None):
        if server_id is None:
            await ctx.reply(embed=discord.Embed(
                title="❌ Missing Argument",
                description="**Usage:** `!farm <server_id>`",
                color=0xFF4444,
            ))
            return
        await do_farm(ctx, server_id)

    @app_commands.command(name="farm", description="Farm authorized members into a server")
    @app_commands.describe(server_id="The Discord server ID to farm members into")
    async def farm_slash(self, interaction: discord.Interaction, server_id: str):
        await do_farm(interaction, server_id)


async def setup(bot: commands.Bot):
    await bot.add_cog(FarmCog(bot))
