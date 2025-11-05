import sqlite3
import sys
import requests
from bs4 import BeautifulSoup
import time
from unidecode import unidecode
import re

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ===================== CONFIG =====================
DB_FILE = "fbref_pl_2024_2025_full.sqlite"
TARGET_TABLE = "player_transfer_values_2024_2025"
BASE_URL = "https://www.footballtransfers.com/en/players/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}
# ==================================================

# --- Xoá bảng cũ & tạo lại ---
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        cur = conn.cursor()
        cur.execute(f"DROP TABLE IF EXISTS {TARGET_TABLE};")
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {TARGET_TABLE}(
                player TEXT,
                etv_value TEXT,
                club TEXT,
                last_update TEXT
            );
        """)
    print(f"✅ Bảng {TARGET_TABLE} đã được reset trong {DB_FILE}")

# --- Lưu 1 bản ghi ---
def insert_record(player, etv_value, club, last_update):
    with sqlite3.connect(DB_FILE) as conn:
        cur = conn.cursor()
        cur.execute(f"""
            INSERT INTO {TARGET_TABLE} (player, etv_value, club, last_update)
            VALUES (?, ?, ?, ?);
        """, (player, etv_value, club, last_update))
        conn.commit()

# --- Lấy danh sách cầu thủ từ DB chính ---
def get_players():
    with sqlite3.connect(DB_FILE) as conn:
        df = conn.execute("SELECT player FROM player_stats_cleaned").fetchall()
        players = [x[0] for x in df]
    print(f"📋 Tổng cầu thủ cần kiểm tra: {len(players)}")
    return players

# --- Chuẩn hoá tên cầu thủ thành slug URL ---
def make_slug(name):
    name = unidecode(name.lower())
    name = re.sub(r"[^a-z0-9\s-]", "", name)
    name = re.sub(r"\s+", "-", name.strip())
    return name

# --- Crawl dữ liệu cầu thủ ---
def fetch_player_value(player):
    slug = make_slug(player)
    urls = [
        f"{BASE_URL}{slug}",
        f"{BASE_URL}{slug}-1",
        f"{BASE_URL}{slug}-2"
    ]

    for url in urls:
        try:
            res = requests.get(url, headers=HEADERS, timeout=15)
            if res.status_code != 200:
                continue
            soup = BeautifulSoup(res.text, "html.parser")

            # Tìm thẻ chứa giá trị
            value_tag = soup.select_one(".player-value .player-tag")
            club_tag = soup.select_one(".playerInfoTop-bar__club")
            date_tag = soup.find(string=re.compile(r"Last update", re.I))

            if not value_tag or not club_tag:
                continue

            etv_value = value_tag.text.strip()
            club = club_tag.text.strip()
            last_update = date_tag.strip() if date_tag else "N/a"

            print(f"  💶 {etv_value} | 🏟 {club} | 🕓 {last_update}")
            return etv_value, club, last_update

        except Exception:
            continue

    print("  ❌ Không tìm thấy profile.")
    return "N/a", "N/a", "N/a"

# --- MAIN ---
def main():
    init_db()
    players = get_players()

    for i, player in enumerate(players, start=1):
        print(f"[{i}/{len(players)}] {player}")
        try:
            etv_value, club, last_update = fetch_player_value(player)
            insert_record(player, etv_value, club, last_update)
        except Exception as e:
            print(f"⚠️ Lỗi khi xử lý {player}: {e}")
            insert_record(player, "N/a", "N/a", "N/a")
        time.sleep(0.3)  # tránh bị chặn IP

    print(f"\n✅ Hoàn tất! Dữ liệu đã được lưu vào bảng {TARGET_TABLE}.\n")

if __name__ == "__main__":
    main()
