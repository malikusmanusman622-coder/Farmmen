import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "bot.db")


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS authorized_users (
                user_id       TEXT PRIMARY KEY,
                username      TEXT,
                access_token  TEXT,
                refresh_token TEXT,
                authorized_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Migration: add token columns if they don't exist yet
        for col in ("access_token", "refresh_token"):
            try:
                await db.execute(f"ALTER TABLE authorized_users ADD COLUMN {col} TEXT")
            except Exception:
                pass
        await db.execute("""
            CREATE TABLE IF NOT EXISTS farm_logs (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    TEXT,
                server_id  TEXT,
                count      INTEGER,
                used_at    TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()


async def add_authorized_user(user_id: str, username: str,
                               access_token: str = None, refresh_token: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO authorized_users (user_id, username, access_token, refresh_token, authorized_at)
               VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(user_id) DO UPDATE SET
                   username      = excluded.username,
                   access_token  = COALESCE(excluded.access_token, access_token),
                   refresh_token = COALESCE(excluded.refresh_token, refresh_token),
                   authorized_at = excluded.authorized_at""",
            (str(user_id), username, access_token, refresh_token),
        )
        await db.commit()


async def is_authorized(user_id: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM authorized_users WHERE user_id = ?", (str(user_id),)
        ) as cursor:
            return await cursor.fetchone() is not None


async def get_all_authorized() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT user_id, username, access_token, authorized_at FROM authorized_users ORDER BY authorized_at DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_authorized_with_tokens(limit: int) -> list[dict]:
    """Return up to `limit` authorized users that have a stored OAuth token."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT user_id, username, access_token
               FROM authorized_users
               WHERE access_token IS NOT NULL AND access_token != ''
               ORDER BY RANDOM()
               LIMIT ?""",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_authorized_count() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM authorized_users") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def get_token_count() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM authorized_users WHERE access_token IS NOT NULL AND access_token != ''"
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def remove_authorized_user(user_id: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM authorized_users WHERE user_id = ?", (str(user_id),)
        )
        await db.commit()
        return cursor.rowcount > 0


async def log_farm(user_id: str, server_id: str, count: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO farm_logs (user_id, server_id, count) VALUES (?, ?, ?)",
            (str(user_id), str(server_id), count),
        )
        await db.commit()


async def get_farm_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*), SUM(count) FROM farm_logs") as cursor:
            row = await cursor.fetchone()
            return {"total_commands": row[0] or 0, "total_members": row[1] or 0}
