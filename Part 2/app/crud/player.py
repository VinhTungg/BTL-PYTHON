import sqlite3
from typing import List, Dict

from ..core.config import SOURCE_TABLE


def fetch_by_name(conn: sqlite3.Connection, name: str, limit: int, offset: int) -> List[Dict]:
    cur = conn.cursor()
    sql = f"""
        SELECT * FROM [{SOURCE_TABLE}]
        WHERE LOWER(player) LIKE LOWER(?)
        LIMIT ? OFFSET ?;
    """
    cur.execute(sql, (f"%{name}%", limit, offset))
    return [dict(r) for r in cur.fetchall()]

def fetch_by_club(conn: sqlite3.Connection, club: str, exact: bool = True) -> List[Dict]:
    """
    Trả về TOÀN BỘ cột (tức toàn bộ chỉ số) của TẤT CẢ cầu thủ thuộc CLB.
    Mặc định exact=True để khớp chính xác tên CLB.
    """
    cur = conn.cursor()
    if exact:
        sql = f"SELECT * FROM [{SOURCE_TABLE}] WHERE LOWER(squad) = LOWER(?);"
        params = (club,)
    else:
        sql = f"SELECT * FROM [{SOURCE_TABLE}] WHERE LOWER(squad) LIKE LOWER(?);"
        params = (f"%{club}%",)
    cur.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]
