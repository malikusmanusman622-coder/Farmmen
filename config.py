import os

DISCORD_BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
DISCORD_CLIENT_ID = os.environ["DISCORD_CLIENT_ID"]
DISCORD_CLIENT_SECRET = os.environ["DISCORD_CLIENT_SECRET"]
DISCORD_OWNER_ID = int(os.environ["DISCORD_OWNER_ID"])

REPLIT_DEV_DOMAIN = os.environ.get("REPLIT_DEV_DOMAIN", "")
REPLIT_DOMAINS = os.environ.get("REPLIT_DOMAINS", "")


def get_base_url() -> str:
    if REPLIT_DOMAINS:
        domain = REPLIT_DOMAINS.split(",")[0].strip()
        return f"https://{domain}"
    if REPLIT_DEV_DOMAIN:
        return f"https://{REPLIT_DEV_DOMAIN}"
    return "http://localhost:5000"


OAUTH_REDIRECT_URI = f"{get_base_url()}/api/discord/callback"
OAUTH_SCOPES = "identify+guilds.join"

PREFIX = "!"
DEFAULT_MEMBER_ROLE = "Member"
WELCOME_CHANNEL_NAME = "welcome"

ROLE_LIMITS = {
    "Premium":  35,
    "Diamond":  25,
    "Gold":     15,
    "Silver":   10,
    "Member":    2,
}

ROLE_ORDER = ["Premium", "Diamond", "Gold", "Silver", "Member"]

ROLE_COLORS = {
    "Premium":  0xFFD700,
    "Diamond":  0x00E5FF,
    "Gold":     0xFFA500,
    "Silver":   0xC0C0C0,
    "Member":   0x5865F2,
}

ROLE_EMOJIS = {
    "Premium":  "👑",
    "Diamond":  "💎",
    "Gold":     "🥇",
    "Silver":   "🥈",
    "Member":   "👤",
}
