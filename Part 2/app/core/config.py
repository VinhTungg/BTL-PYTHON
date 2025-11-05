import os
from pathlib import Path

#Thu muc goc
ROOT_DIR = Path(__file__).resolve().parents[2]

DB_FILE = Path(os.getenv("DB_FILE", str(ROOT_DIR / "fbref_pl_2024_2025_full.sqlite"))).resolve()
SOURCE_TABLE = os.getenv("SOURCE_TABLE", "player_stats_cleaned")

# Giới hạn cho phân trang
DEFAULT_LIMIT = int(os.getenv("DEFAULT_LIMIT", "100"))
MAX_LIMIT = int(os.getenv("MAX_LIMIT", "1000"))