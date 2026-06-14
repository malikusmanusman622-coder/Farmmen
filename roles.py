import discord
from discord.ext import commands
from discord import app_commands
from config import DISCORD_OWNER_ID, ROLE_LIMITS, ROLE_ORDER, ROLE_COLORS, ROLE_EMOJIS
from database import get_all_authorized, get_authorized_count, get_farm_stats, add_authorized_user, remove_authorized_user, is_authorized
import math


TIER_NAMES = list(ROLE_LIMITS.keys())


class RolesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _is_owner(self, user: discord.User | discord.Member) -> bool:
        return user.id == DISCORD_OWNER_ID

    async def _ensure_role(self, guild: discord.Guild, role_name: str) -> discord.Role | None:
        role = discord.utils.get(guild.roles, name=role_name)
        if role is None:
            color = discord.Colour(ROLE_COLORS.get(role_name, 0x99AAB5))
            try:
                role = await guild.create_role(
                    name=role_name,
                    color=color,
                    reason="Auto-created by Farm Bot",
                )
            except discord.Forbidden:
                return None
        elif role.color.value != ROLE_COLORS.get(role_name, role.color.value):
            try:
                await role.edit(color=discord.Colour(ROLE_COLORS[role_name]))
            except discord.Forbidden:
                pass
        return role

    async def _give_role(self, guild: discord.Guild, target: discord.Member, role_name: str) -> tuple[bool, str]:
        role = await self._ensure_role(guild, role_name)
        if role is None:
            return False, f"❌ I don't have permission to create or manage the `{role_name}` role."

        tier_roles = [discord.utils.get(guild.roles, name=t) for t in TIER_NAMES]
        existing = [r for r in tier_roles if r and r in target.roles]
        if existing:
            try:
                await target.remove_roles(*existing, reason="Replacing tier role")
            except discord.Forbidden:
                pass

        try:
            await target.add_roles(role, reason=f"Tier role assigned by owner")
            emoji = ROLE_EMOJIS.get(role_name, "🏅")
            return True, f"{emoji} **{target.display_name}** has been given the **{role_name}** role."
        except discord.Forbidden:
            return False, "❌ I don't have permission to assign roles."

    @commands.command(name="giverole")
    async def giverole_prefix(self, ctx: commands.Context, member: discord.Member = None, role_name: str = None):
        if not self._is_owner(ctx.author):
            embed = discord.Embed(title="❌ Access Denied", description="Only the bot owner can assign tier roles.", color=0xFF4444)
            await ctx.reply(embed=embed)
            return
        if member is None or role_name is None:
            tiers = " • ".join(f"{ROLE_EMOJIS.get(t,'')} `{t}`" for t in TIER_NAMES)
            embed = discord.Embed(
                title="❌ Usage Error",
                description=f"**Usage:** `!giverole @user <tier>`\n\n**Available tiers:**\n{tiers}",
                color=0xFF4444,
            )
            await ctx.reply(embed=embed)
            return

        role_name_proper = role_name.capitalize()
        if role_name_proper not in TIER_NAMES:
            tiers = " • ".join(f"{ROLE_EMOJIS.get(t,'')} `{t}`" for t in TIER_NAMES)
            embed = discord.Embed(
                title="❌ Unknown Tier",
                description=f"**`{role_name}`** is not a valid tier.\n\n**Available tiers:**\n{tiers}",
                color=0xFF4444,
            )
            await ctx.reply(embed=embed)
            return

        ok, msg = await self._give_role(ctx.guild, member, role_name_proper)
        color = 0x57F287 if ok else 0xFF4444
        embed = discord.Embed(description=msg, color=color)
        await ctx.reply(embed=embed)

    @app_commands.command(name="giverole", description="[Owner only] Give a tier role to a member")
    @app_commands.describe(member="The member to give the role to", role_name="The tier role to assign")
    @app_commands.choices(role_name=[
        app_commands.Choice(name=f"{ROLE_EMOJIS[t]} {t} — {ROLE_LIMITS[t]} members/cmd", value=t)
        for t in TIER_NAMES
    ])
    async def giverole_slash(self, interaction: discord.Interaction, member: discord.Member, role_name: str):
        if not self._is_owner(interaction.user):
            embed = discord.Embed(title="❌ Access Denied", description="Only the bot owner can assign tier roles.", color=0xFF4444)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        ok, msg = await self._give_role(interaction.guild, member, role_name)
        color = 0x57F287 if ok else 0xFF4444
        await interaction.response.send_message(embed=discord.Embed(description=msg, color=color), ephemeral=not ok)

    @commands.command(name="tiers")
    async def tiers_prefix(self, ctx: commands.Context):
        if not self._is_owner(ctx.author):
            await ctx.reply(embed=discord.Embed(title="❌ Access Denied", description="Only the bot owner can view tiers.", color=0xFF4444))
            return
        await ctx.reply(embed=self._tiers_embed())

    @app_commands.command(name="tiers", description="[Owner only] Show all role tiers and their farming limits")
    async def tiers_slash(self, interaction: discord.Interaction):
        if not self._is_owner(interaction.user):
            await interaction.response.send_message(embed=discord.Embed(title="❌ Access Denied", description="Only the bot owner can view tiers.", color=0xFF4444), ephemeral=True)
            return
        await interaction.response.send_message(embed=self._tiers_embed())

    def _tiers_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🏅 Role Tiers & Farm Limits",
            description="Upgrade your tier to farm more members per command.\nAsk the owner to assign you a role with `!giverole`.",
            color=0xFFD700,
        )
        for tier in ROLE_ORDER:
            limit = ROLE_LIMITS[tier]
            emoji = ROLE_EMOJIS[tier]
            color_hex = f"#{ROLE_COLORS[tier]:06X}"
            bar = "█" * min(limit // 5, 7) + "░" * (7 - min(limit // 5, 7))
            embed.add_field(
                name=f"{emoji} {tier}",
                value=f"`{bar}` **{limit}** members/cmd\nColor: `{color_hex}`",
                inline=True,
            )
        embed.set_footer(text="Both ! and / commands are supported.")
        return embed

    @commands.command(name="pool")
    async def pool_prefix(self, ctx: commands.Context, page: int = 1):
        if not self._is_owner(ctx.author):
            await ctx.reply(embed=discord.Embed(title="❌ Access Denied", description="Only the bot owner can view the pool.", color=0xFF4444))
            return
        await self._send_pool(ctx.reply, page)

    @app_commands.command(name="pool", description="[Owner only] View all authorized members in the pool")
    @app_commands.describe(page="Page number to view")
    async def pool_slash(self, interaction: discord.Interaction, page: int = 1):
        if not self._is_owner(interaction.user):
            await interaction.response.send_message(embed=discord.Embed(title="❌ Access Denied", description="Only the bot owner can view the pool.", color=0xFF4444), ephemeral=True)
            return
        await self._send_pool(interaction.response.send_message, page)

    async def _send_pool(self, send_fn, page: int = 1):
        users = await get_all_authorized()
        total = len(users)
        per_page = 15
        total_pages = max(1, math.ceil(total / per_page))
        page = max(1, min(page, total_pages))

        embed = discord.Embed(
            title="🌊 Authorized Member Pool",
            color=0x00E5FF,
        )

        if total == 0:
            embed.description = "No members have authorized yet.\nShare `!lauth` to get members to authorize."
        else:
            start = (page - 1) * per_page
            chunk = users[start : start + per_page]
            lines = []
            for i, u in enumerate(chunk, start=start + 1):
                date = u["authorized_at"][:10] if u["authorized_at"] else "?"
                lines.append(f"`{i:>3}.` **{u['username']}** — `{u['user_id']}` *(auth: {date})*")

            embed.description = "\n".join(lines)
            embed.add_field(name="📊 Stats", value=f"**{total:,}** total authorized", inline=True)
            embed.add_field(name="📄 Page", value=f"**{page}** / **{total_pages}**", inline=True)

        embed.set_footer(text=f"Use !pool <page> to navigate • Total: {total}")
        embed.timestamp = discord.utils.utcnow()
        await send_fn(embed=embed)

    @commands.command(name="forceauth")
    async def forceauth_prefix(self, ctx: commands.Context, user_id: str = None, *, username: str = None):
        if not self._is_owner(ctx.author):
            await ctx.reply(embed=discord.Embed(title="❌ Access Denied", description="Only the bot owner can force-authorize members.", color=0xFF4444))
            return
        if user_id is None:
            await ctx.reply(embed=discord.Embed(
                title="❌ Usage Error",
                description="**Usage:** `!forceauth <user_id> [username]`\n\nExample: `!forceauth 123456789012345678 JohnDoe`",
                color=0xFF4444,
            ))
            return
        try:
            user_id = str(int(user_id))
        except ValueError:
            await ctx.reply(embed=discord.Embed(title="❌ Invalid ID", description="User ID must be a number.", color=0xFF4444))
            return
        await self._do_forceauth(ctx.reply, user_id, username or f"User#{user_id[-4:]}")

    @app_commands.command(name="forceauth", description="[Owner only] Force-authorize a member by their Discord user ID")
    @app_commands.describe(
        user_id="The Discord user ID to force-authorize",
        username="Display name to store (optional)",
    )
    async def forceauth_slash(self, interaction: discord.Interaction, user_id: str, username: str = None):
        if not self._is_owner(interaction.user):
            await interaction.response.send_message(embed=discord.Embed(title="❌ Access Denied", description="Only the bot owner can force-authorize members.", color=0xFF4444), ephemeral=True)
            return
        try:
            uid = str(int(user_id))
        except ValueError:
            await interaction.response.send_message(embed=discord.Embed(title="❌ Invalid ID", description="User ID must be a number.", color=0xFF4444), ephemeral=True)
            return
        await self._do_forceauth(interaction.response.send_message, uid, username or f"User#{uid[-4:]}")

    async def _do_forceauth(self, send_fn, user_id: str, username: str):
        already = await is_authorized(user_id)
        await add_authorized_user(user_id, username)

        await self._try_assign_member_role_by_id(int(user_id), username)

        total = await get_authorized_count()
        embed = discord.Embed(
            title="✅ Force-Authorized" if not already else "🔄 Re-Authorized",
            color=0x57F287,
        )
        embed.add_field(name="👤 User", value=f"**{username}**\n`{user_id}`", inline=True)
        embed.add_field(name="📊 Pool Size", value=f"**{total:,}** authorized", inline=True)
        embed.add_field(
            name="ℹ️ What happens next",
            value=(
                "This member is now in the authorized pool.\n"
                "They will be included in the next `!farm` command\n"
                "and have received the **Member** role if they share a server."
            ),
            inline=False,
        )
        embed.set_footer(text="Owner action • Force authorization")
        embed.timestamp = discord.utils.utcnow()
        await send_fn(embed=embed)

    async def _try_assign_member_role_by_id(self, user_id: int, username: str):
        from config import DEFAULT_MEMBER_ROLE
        for guild in self.bot.guilds:
            member = guild.get_member(user_id)
            if member:
                role = discord.utils.get(guild.roles, name=DEFAULT_MEMBER_ROLE)
                if role is None:
                    color = discord.Colour(ROLE_COLORS.get(DEFAULT_MEMBER_ROLE, 0x5865F2))
                    try:
                        role = await guild.create_role(name=DEFAULT_MEMBER_ROLE, color=color, reason="Auto-created by Farm Bot")
                    except discord.Forbidden:
                        continue
                if role not in member.roles:
                    try:
                        await member.add_roles(role, reason="Force-authorized by owner")
                    except discord.Forbidden:
                        pass

    @commands.command(name="forceauthname")
    async def forceauthname_prefix(self, ctx: commands.Context, *, username: str = None):
        if not self._is_owner(ctx.author):
            await ctx.reply(embed=discord.Embed(title="❌ Access Denied", description="Only the bot owner can force-authorize members.", color=0xFF4444))
            return
        if not username:
            await ctx.reply(embed=discord.Embed(
                title="❌ Usage Error",
                description="**Usage:** `!forceauthname <username>`\n\nSearches the current server for a matching member name.",
                color=0xFF4444,
            ))
            return
        await self._do_forceauthname(ctx.reply, ctx.guild, username)

    @app_commands.command(name="forceauthname", description="[Owner only] Force-authorize a member by username — no ID needed")
    @app_commands.describe(username="The member's username or display name to search for")
    async def forceauthname_slash(self, interaction: discord.Interaction, username: str):
        if not self._is_owner(interaction.user):
            await interaction.response.send_message(embed=discord.Embed(title="❌ Access Denied", description="Only the bot owner can force-authorize members.", color=0xFF4444), ephemeral=True)
            return
        await self._do_forceauthname(interaction.response.send_message, interaction.guild, username)

    async def _do_forceauthname(self, send_fn, guild: discord.Guild, username: str):
        if guild is None:
            await send_fn(embed=discord.Embed(title="❌ Server Only", description="This command must be used inside a server.", color=0xFF4444))
            return

        query = username.lower().lstrip("@")
        matches = [
            m for m in guild.members
            if query in m.name.lower() or query in m.display_name.lower()
        ]

        if not matches:
            embed = discord.Embed(
                title="⚠️ No Match Found",
                description=f"No member matching **`{username}`** was found in this server.\n\nTip: Use `!forceauth <user_id>` if the member is not in this server.",
                color=0xFEE75C,
            )
            await send_fn(embed=embed)
            return

        if len(matches) > 1:
            lines = "\n".join(f"• **{m.display_name}** — `{m.id}` (@{m.name})" for m in matches[:10])
            if len(matches) > 10:
                lines += f"\n*...and {len(matches) - 10} more*"
            embed = discord.Embed(
                title=f"⚠️ {len(matches)} Matches Found",
                description=f"Be more specific, or use `!forceauth <user_id>` to target exactly:\n\n{lines}",
                color=0xFEE75C,
            )
            await send_fn(embed=embed)
            return

        member = matches[0]
        already = await is_authorized(str(member.id))
        await add_authorized_user(str(member.id), member.name)
        await self._try_assign_member_role_by_id(member.id, member.name)

        total = await get_authorized_count()
        embed = discord.Embed(
            title="✅ Force-Authorized" if not already else "🔄 Re-Authorized",
            color=0x57F287,
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="👤 Member", value=f"{member.mention}\n**{member.display_name}** (@{member.name})", inline=True)
        embed.add_field(name="🆔 User ID", value=f"`{member.id}`", inline=True)
        embed.add_field(name="📊 Pool Size", value=f"**{total:,}** authorized", inline=True)
        embed.set_footer(text="Owner action • Force authorization by name")
        embed.timestamp = discord.utils.utcnow()
        await send_fn(embed=embed)

    @commands.command(name="forceauthall")
    async def forceauthall_prefix(self, ctx: commands.Context):
        if not self._is_owner(ctx.author):
            await ctx.reply(embed=discord.Embed(title="❌ Access Denied", description="Only the bot owner can force-authorize all members.", color=0xFF4444))
            return
        await self._do_forceauthall(ctx, ctx.guild)

    @app_commands.command(name="forceauthall", description="[Owner only] Force-authorize every member in this server at once")
    async def forceauthall_slash(self, interaction: discord.Interaction):
        if not self._is_owner(interaction.user):
            await interaction.response.send_message(embed=discord.Embed(title="❌ Access Denied", description="Only the bot owner can force-authorize all members.", color=0xFF4444), ephemeral=True)
            return
        await interaction.response.defer()
        await self._do_forceauthall(interaction, interaction.guild)

    async def _do_forceauthall(self, ctx_or_interaction, guild: discord.Guild):
        is_slash = isinstance(ctx_or_interaction, discord.Interaction)

        if guild is None:
            msg = discord.Embed(title="❌ Server Only", description="Use this inside a server.", color=0xFF4444)
            if is_slash:
                await ctx_or_interaction.followup.send(embed=msg)
            else:
                await ctx_or_interaction.reply(embed=msg)
            return

        progress_embed = discord.Embed(
            title="⏳ Force-Authorizing All Members…",
            description=f"Processing **{guild.member_count:,}** members. This may take a moment.",
            color=0xFEE75C,
        )
        if is_slash:
            progress_msg = await ctx_or_interaction.followup.send(embed=progress_embed)
        else:
            progress_msg = await ctx_or_interaction.reply(embed=progress_embed)

        added = 0
        skipped = 0
        bots = 0
        from config import DEFAULT_MEMBER_ROLE

        member_role = discord.utils.get(guild.roles, name=DEFAULT_MEMBER_ROLE)
        if member_role is None:
            color = discord.Colour(ROLE_COLORS.get(DEFAULT_MEMBER_ROLE, 0x5865F2))
            try:
                member_role = await guild.create_role(name=DEFAULT_MEMBER_ROLE, color=color, reason="Auto-created by Farm Bot")
            except discord.Forbidden:
                member_role = None

        for member in guild.members:
            if member.bot:
                bots += 1
                continue
            already = await is_authorized(str(member.id))
            await add_authorized_user(str(member.id), member.name)
            if member_role and member_role not in member.roles:
                try:
                    await member.add_roles(member_role, reason="Force-auth all by owner")
                except discord.Forbidden:
                    pass
            if already:
                skipped += 1
            else:
                added += 1

        total = await get_authorized_count()
        result_embed = discord.Embed(
            title="✅ Force-Auth All Complete",
            description=f"All human members of **{guild.name}** have been authorized.",
            color=0x57F287,
        )
        result_embed.add_field(name="🆕 Newly Authorized", value=f"**{added:,}**", inline=True)
        result_embed.add_field(name="🔄 Already Had Auth", value=f"**{skipped:,}**", inline=True)
        result_embed.add_field(name="🤖 Bots Skipped", value=f"**{bots:,}**", inline=True)
        result_embed.add_field(name="📊 Total Pool Size", value=f"**{total:,}** authorized members", inline=False)
        result_embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        result_embed.set_footer(text=f"Owner action • {guild.name}")
        result_embed.timestamp = discord.utils.utcnow()

        await progress_msg.edit(embed=result_embed)

    @commands.command(name="forceunauth")
    async def forceunauth_prefix(self, ctx: commands.Context, user_id: str = None):
        if not self._is_owner(ctx.author):
            await ctx.reply(embed=discord.Embed(title="❌ Access Denied", description="Only the bot owner can revoke authorization.", color=0xFF4444))
            return
        if user_id is None:
            await ctx.reply(embed=discord.Embed(
                title="❌ Usage Error",
                description="**Usage:** `!forceunauth <user_id>`",
                color=0xFF4444,
            ))
            return
        try:
            user_id = str(int(user_id))
        except ValueError:
            await ctx.reply(embed=discord.Embed(title="❌ Invalid ID", description="User ID must be a number.", color=0xFF4444))
            return
        await self._do_forceunauth(ctx.reply, user_id)

    @app_commands.command(name="forceunauth", description="[Owner only] Revoke a member's authorization by their Discord user ID")
    @app_commands.describe(user_id="The Discord user ID to de-authorize")
    async def forceunauth_slash(self, interaction: discord.Interaction, user_id: str):
        if not self._is_owner(interaction.user):
            await interaction.response.send_message(embed=discord.Embed(title="❌ Access Denied", description="Only the bot owner can revoke authorization.", color=0xFF4444), ephemeral=True)
            return
        try:
            uid = str(int(user_id))
        except ValueError:
            await interaction.response.send_message(embed=discord.Embed(title="❌ Invalid ID", description="User ID must be a number.", color=0xFF4444), ephemeral=True)
            return
        await self._do_forceunauth(interaction.response.send_message, uid)

    async def _do_forceunauth(self, send_fn, user_id: str):
        removed = await remove_authorized_user(user_id)
        if not removed:
            embed = discord.Embed(
                title="⚠️ Not Found",
                description=f"`{user_id}` was not in the authorized pool.",
                color=0xFEE75C,
            )
            await send_fn(embed=embed)
            return

        total = await get_authorized_count()
        embed = discord.Embed(
            title="🚫 Authorization Revoked",
            color=0xFF4444,
        )
        embed.add_field(name="👤 User ID", value=f"`{user_id}`", inline=True)
        embed.add_field(name="📊 Pool Size", value=f"**{total:,}** remaining", inline=True)
        embed.set_footer(text="Owner action • Authorization revoked")
        embed.timestamp = discord.utils.utcnow()
        await send_fn(embed=embed)

    @commands.command(name="stats")
    async def stats_prefix(self, ctx: commands.Context):
        if not self._is_owner(ctx.author):
            embed = discord.Embed(title="❌ Access Denied", description="Only the bot owner can view stats.", color=0xFF4444)
            await ctx.reply(embed=embed)
            return
        embed = await self._stats_embed()
        await ctx.reply(embed=embed)

    @app_commands.command(name="stats", description="[Owner only] View bot statistics")
    async def stats_slash(self, interaction: discord.Interaction):
        if not self._is_owner(interaction.user):
            embed = discord.Embed(title="❌ Access Denied", description="Only the bot owner can view stats.", color=0xFF4444)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        embed = await self._stats_embed()
        await interaction.response.send_message(embed=embed)

    async def _stats_embed(self) -> discord.Embed:
        auth_count = await get_authorized_count()
        farm_stats = await get_farm_stats()
        embed = discord.Embed(title="📊 Farm Bot Statistics", color=0x5865F2)
        embed.add_field(name="✅ Authorized Members", value=f"**{auth_count:,}**", inline=True)
        embed.add_field(name="🌾 Total Farms Run", value=f"**{farm_stats['total_commands']:,}**", inline=True)
        embed.add_field(name="👥 Total Members Farmed", value=f"**{farm_stats['total_members']:,}**", inline=True)
        embed.timestamp = discord.utils.utcnow()
        embed.set_footer(text="Owner-only view")
        return embed


    @commands.command(name="broadcast")
    async def broadcast_prefix(self, ctx: commands.Context):
        if not self._is_owner(ctx.author):
            await ctx.reply(embed=discord.Embed(title="❌ Access Denied", description="Only the bot owner can broadcast.", color=0xFF4444))
            return
        await self._do_broadcast(ctx.reply, ctx.bot)

    @app_commands.command(name="broadcast", description="[Owner only] Send the Auth panel to every server the bot is in")
    async def broadcast_slash(self, interaction: discord.Interaction):
        if not self._is_owner(interaction.user):
            await interaction.response.send_message(embed=discord.Embed(title="❌ Access Denied", description="Only the bot owner can broadcast.", color=0xFF4444), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await self._do_broadcast(interaction.followup.send, interaction.client)

    async def _do_broadcast(self, reply_fn, bot):
        from cogs.auth import AuthView, lauth_embed
        from database import get_authorized_count

        guilds = bot.guilds
        sent = 0
        failed = 0

        progress = discord.Embed(
            title="📡 Broadcasting…",
            description=f"Sending Auth panel to **{len(guilds)}** servers…",
            color=0xFEE75C,
        )
        progress_msg = await reply_fn(embed=progress)

        for guild in guilds:
            channel = (
                discord.utils.get(guild.text_channels, name="general")
                or discord.utils.get(guild.text_channels, name="welcome")
                or discord.utils.get(guild.text_channels, name="bot-commands")
                or discord.utils.get(guild.text_channels, name="bots")
                or guild.system_channel
                or next(
                    (c for c in guild.text_channels
                     if c.permissions_for(guild.me).send_messages),
                    None,
                )
            )
            if channel is None:
                failed += 1
                continue
            try:
                count = await get_authorized_count()
                await channel.send(embed=lauth_embed(count), view=AuthView())
                sent += 1
            except discord.Forbidden:
                failed += 1
            except Exception:
                failed += 1

        result = discord.Embed(
            title="📡 Broadcast Complete",
            color=0x57F287 if sent > 0 else 0xFF4444,
        )
        result.add_field(name="✅ Sent", value=f"**{sent}** servers", inline=True)
        result.add_field(name="❌ Failed", value=f"**{failed}** servers", inline=True)
        result.add_field(name="📊 Total", value=f"**{len(guilds)}** servers", inline=True)
        result.add_field(
            name="ℹ️ What happens next",
            value=(
                "Members in each server will see the **Auth Bot** button.\n"
                "Once they click it and authorize, they'll be added to your farm pool\n"
                "and can be farmed into any server with `!farm`."
            ),
            inline=False,
        )
        result.set_footer(text="Owner action • Broadcast")
        result.timestamp = discord.utils.utcnow()

        if progress_msg:
            await progress_msg.edit(embed=result)
        else:
            await reply_fn(embed=result)


async def setup(bot: commands.Bot):
    await bot.add_cog(RolesCog(bot))
