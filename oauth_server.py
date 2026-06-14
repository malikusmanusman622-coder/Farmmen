from aiohttp import web
from config import DEFAULT_MEMBER_ROLE, ROLE_COLORS
from database import add_authorized_user
import logging
import discord

logger = logging.getLogger(__name__)

bot_ref = None


async def handle_internal_authorized(request: web.Request) -> web.Response:
    """Called by the Express API server after successful OAuth exchange."""
    try:
        data = await request.json()
    except Exception:
        return web.Response(text="Bad JSON", status=400)

    user_id      = data.get("userId")
    username     = data.get("username", "Unknown")
    access_token = data.get("accessToken")
    refresh_token = data.get("refreshToken")

    if not user_id:
        return web.Response(text="Missing userId", status=400)

    # Store user WITH their OAuth token so farm can actually add them
    await add_authorized_user(str(user_id), username, access_token, refresh_token)
    logger.info("User authorized via OAuth: %s (%s) — token stored: %s",
                username, user_id, "yes" if access_token else "no")

    await _try_assign_member_role(int(user_id), username)

    return web.json_response({"ok": True})


async def _try_assign_member_role(user_id: int, username: str):
    if bot_ref is None:
        return
    try:
        for guild in bot_ref.guilds:
            member = guild.get_member(user_id)
            if member:
                role = discord.utils.get(guild.roles, name=DEFAULT_MEMBER_ROLE)
                if role is None:
                    color = discord.Colour(ROLE_COLORS.get(DEFAULT_MEMBER_ROLE, 0x5865F2))
                    role = await guild.create_role(
                        name=DEFAULT_MEMBER_ROLE,
                        color=color,
                        reason="Auto-created for authorized users",
                    )
                if role not in member.roles:
                    await member.add_roles(role, reason="Authorized via OAuth2")
                    logger.info("Assigned Member role to %s in %s", username, guild.name)
    except Exception as e:
        logger.warning("Could not assign role: %s", e)


async def start_oauth_server(app_bot=None):
    global bot_ref
    bot_ref = app_bot

    app = web.Application()
    app.router.add_post("/internal/authorized", handle_internal_authorized)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 5001)
    await site.start()
    logger.info("Internal OAuth notification server running on port 5001")
