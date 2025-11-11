import aiosqlite
from typing import AsyncGenerator, List

from ..core.config import SOURCE_TABLE, DB_FILE


async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    async with aiosqlite.connect(str(DB_FILE)) as conn:
        conn.row_factory = aiosqlite.Row
        yield conn


async def list_tables(conn: aiosqlite.Connection) -> List[str]:
    async with conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;") as cursor:
        rows = await cursor.fetchall()
        return [row[0] for row in rows]


async def ensure_source_table(conn: aiosqlite.Connection):
    async with conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?;", (SOURCE_TABLE,)) as cursor:
        row = await cursor.fetchone()
        if not row:
            tables = await list_tables(conn)
            raise RuntimeError(
                f"Không tìm thấy bảng nguồn '{SOURCE_TABLE}' trong DB '{DB_FILE.name}'. "
                f"Các bảng hiện có: {tables}"
            )


async def create_indexes(conn: aiosqlite.Connection):
    await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{SOURCE_TABLE}_player ON [{SOURCE_TABLE}](player)")
    await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{SOURCE_TABLE}_squad ON [{SOURCE_TABLE}](squad)")
    await conn.commit()


async def close_db():
    pass