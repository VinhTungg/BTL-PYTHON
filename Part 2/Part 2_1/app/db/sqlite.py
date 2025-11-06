import sqlite3
from typing import List

from ..core.config import SOURCE_TABLE, DB_FILE


def get_conn() -> sqlite3.Connection:
    # Ensure sqlite receives a filesystem path string
    conn = sqlite3.connect(str(DB_FILE))
    conn.row_factory = sqlite3.Row
    return conn

def list_tables(conn: sqlite3.Connection) -> List[str]:
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    return [r[0] for r in cur.fetchall()]

def ensure_source_table(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?;", (SOURCE_TABLE,))
    if not cur.fetchone():
        raise RuntimeError(
            f"Không tìm thấy bảng nguồn '{SOURCE_TABLE}' trong DB '{DB_FILE.name}'. "
            f"Các bảng hiện có: {list_tables(conn)}"
        )

def create_indexes(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{SOURCE_TABLE}_player ON [{SOURCE_TABLE}](player)")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{SOURCE_TABLE}_squad  ON [{SOURCE_TABLE}](squad)")
    conn.commit()