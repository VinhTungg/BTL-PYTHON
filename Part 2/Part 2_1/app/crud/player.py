import aiosqlite
from typing import List, Dict

from ..core.config import SOURCE_TABLE


async def fetch_by_name(conn: aiosqlite.Connection, name: str) -> List[Dict]:
    sql = f"SELECT * FROM [{SOURCE_TABLE}] WHERE LOWER(player) LIKE LOWER(?)"
    async with conn.execute(sql, (f"%{name}%",)) as cursor:
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def fetch_by_club(conn: aiosqlite.Connection, club: str, exact: bool = True) -> List[Dict]:
    if exact:
        sql = f"SELECT * FROM [{SOURCE_TABLE}] WHERE LOWER(squad) = LOWER(?)"
        params = (club,)
    else:
        sql = f"SELECT * FROM [{SOURCE_TABLE}] WHERE LOWER(squad) LIKE LOWER(?)"
        params = (f"%{club}%",)
    
    async with conn.execute(sql, params) as cursor:
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
