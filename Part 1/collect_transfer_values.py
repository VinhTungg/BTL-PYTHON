# -*- coding: utf-8 -*-
import sqlite3
import requests
from bs4 import BeautifulSoup
from unidecode import unidecode
import re
import os
import time
from urllib.parse import quote

# === Cấu hình cơ bản ===
DB_FILE = "fbref_pl_2024_2025_full.sqlite"
TARGET_TABLE = "player_transfer_values_2024_2025"
BASE_URL = "https://www.footballtransfers.com/en/players/"
SEARCH_URL = "https://www.footballtransfers.com/en/players?q="
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}

# === Tạo kết nối DB và bảng đích ===
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        cur = conn.cursor()
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {TARGET_TABLE} (
                player TEXT,
                market_value TEXT,
                club TEXT,
                last_update TEXT
            )
        """)
        conn.commit()

# === Xoá toàn bộ dữ liệu trong bảng (nếu tồn tại) ===
def clear_table():
    with sqlite3.connect(DB_FILE) as conn:
        cur = conn.cursor()
        cur.execute(f"DELETE FROM {TARGET_TABLE}")
        conn.commit()
        print(f"🧹 Đã xoá toàn bộ dữ liệu cũ trong bảng {TARGET_TABLE}.\n")

# === Ghi alias (nếu tên khác với URL thật) ===
def log_alias(original, alias_url):
    with open("alias_detected.txt", "a", encoding="utf-8") as f:
        f.write(f"{original} -> {alias_url}\n")

# === Chuẩn hóa tên cầu thủ để tạo slug ===
def make_slug(name):
    name = unidecode(name.lower())
    name = re.sub(r"[^a-z0-9\s-]", "", name)
    return re.sub(r"\s+", "-", name.strip())

# === Crawl dữ liệu từ 1 trang cầu thủ ===
def crawl_page(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        if res.status_code != 200:
            print(f"  ⚠️ HTTP {res.status_code} tại {url}")
            return None
        if res.url != url:
            log_alias(url, res.url)
        soup = BeautifulSoup(res.text, "html.parser")

        value_tag = soup.select_one(".player-value .player-tag") or soup.select_one(".playerInfo-value")
        club_tag = soup.select_one(".playerInfoTop-bar__club, .playerInfoTop-bar__team")
        market_value = value_tag.text.strip() if value_tag else "N/a"
        club = club_tag.text.strip() if club_tag else "N/a"

        # Ngày cập nhật có thể ở nhiều chỗ khác nhau
        date_candidates = soup.find_all(text=re.compile("Last update", re.IGNORECASE))
        last_update = "N/a"
        for d in date_candidates:
            try:
                last_update = d.parent.text.strip()
                break
            except:
                pass

        # Loại bỏ noise như “Last update:” để lấy phần ngày
        if "Last update" in last_update:
            last_update = last_update.split(":", 1)[-1].strip()

        if not market_value.startswith("€"):
            return None

        return market_value, club, last_update
    except requests.exceptions.Timeout:
        print(f"  ⏳ Timeout, thử lại {url}")
        try:
            time.sleep(2)
            res = requests.get(url, headers=HEADERS, timeout=20)
            if res.status_code == 200:
                return crawl_page(url)
        except:
            return None
        return None
    except Exception as e:
        print(f"  ⚠️ Lỗi crawl_page({url}): {e}")
        return None

# === Lấy giá trị từ trang kết quả tìm kiếm nếu không có profile riêng ===
def crawl_from_search_results(soup):
    try:
        item = soup.select_one(".ft-listing .ft-listing__item, .search-results__item")
        if not item:
            return None
        name = item.select_one(".ft-listing__name")
        value = item.select_one(".ft-listing__value")
        club = item.select_one(".ft-listing__team")
        if value and value.text.strip().startswith("€"):
            return value.text.strip(), (club.text.strip() if club else "N/a"), "Approx (search result)"
    except Exception:
        pass
    return None

# === Hàm crawl tổng hợp, xử lý alias ===
def fetch_player_value(player):
    slug = make_slug(player)
    urls = [f"{BASE_URL}{slug}", f"{BASE_URL}{slug}-1", f"{BASE_URL}{slug}-2", f"{BASE_URL}{slug}-3"]

    for url in urls:
        data = crawl_page(url)
        if data:
            return data

    search_url = f"{SEARCH_URL}{quote(player)}"
    try:
        res = requests.get(search_url, headers=HEADERS, timeout=15)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            link_tag = soup.select_one("a[href*='/en/players/']")
            if link_tag:
                alias_url = "https://www.footballtransfers.com" + link_tag["href"]
                log_alias(player, alias_url)
                data = crawl_page(alias_url)
                if data:
                    return data
            data = crawl_from_search_results(soup)
            if data:
                return data
    except Exception as e:
        print(f"  ⚠️ Lỗi tìm kiếm {player}: {e}")

    return "N/a", "N/a", "N/a"

# === Ghi dữ liệu vào DB ===
def insert_record(player, value, club, date):
    with sqlite3.connect(DB_FILE) as conn:
        cur = conn.cursor()
        cur.execute(f"INSERT INTO {TARGET_TABLE} VALUES (?, ?, ?, ?)", (player, value, club, date))
        conn.commit()

# === Hàm chính ===
def main():
    print("🔧 Khởi tạo cơ sở dữ liệu...")
    init_db()
    clear_table()  # XÓA DỮ LIỆU TRƯỚC KHI CHẠY

    with sqlite3.connect(DB_FILE) as conn:
        players = [row[0] for row in conn.execute("SELECT DISTINCT player FROM player_stats_cleaned").fetchall()]

    print(f"📋 Tổng cầu thủ cần kiểm tra: {len(players)}\n")

    seen = set()
    for i, player in enumerate(players, start=1):
        if player in seen:
            continue
        print(f"[{i}/{len(players)}] {player}")
        try:
            value, club, date = fetch_player_value(player)
            print(f"  💶 {value} | 🏟 {club} | 🕓 {date}")
            insert_record(player, value, club, date)
            seen.add(player)
        except Exception as e:
            print(f"⚠️ Lỗi khi xử lý {player}: {e}")
            insert_record(player, "N/a", "N/a", "N/a")

    print(f"\n✅ Hoàn tất! Dữ liệu mới đã được lưu vào bảng {TARGET_TABLE}.")

# === Chạy ===
if __name__ == "__main__":
    main()
