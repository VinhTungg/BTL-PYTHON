# -*- coding: utf-8 -*-
import sys
import time
import random
import sqlite3
from collections import defaultdict

import pandas as pd
from bs4 import BeautifulSoup, Comment
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException
# Cấu hình
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

BASE_SEASON_URL = "https://fbref.com/en/comps/9/2024-2025"
SEASON_NAME = "2024-2025-Premier-League-Stats"
DB_FILE = "fbref_pl_2024_2025_full.sqlite"
OUT_TABLE = "player_stats_cleaned"
MIN_MINUTES_THRESHOLD = 90
WAIT_SEC = 1.5
STAT_PAGES = {
    "standard": ("stats", "stats_standard", "all_stats_standard"),
    "shooting": ("shooting", "stats_shooting", "all_stats_shooting"),
    "passing": ("passing", "stats_passing", "all_stats_passing"),
    "passing_types": ("passing_types", "stats_passing_types", "all_stats_passing_types"),
    "gca": ("gca", "stats_gca", "all_stats_gca"),
    "defense": ("defense", "stats_defense", "all_stats_defense"),
    "possession": ("possession", "stats_possession", "all_stats_possession"),
    "playing_time": ("playingtime", "stats_playing_time", "all_stats_playing_time"),
    "misc": ("misc", "stats_misc", "all_stats_misc"),
    "goalkeeping": ("keepers", "stats_keeper", "all_stats_keeper"),
    "goalkeeping_adv": ("keepersadv", "stats_keeper_adv", "all_stats_keeper_adv"),
}

def build_driver():
    """Khởi tạo Chrome driver"""
    try:
        driver = uc.Chrome(headless=False, use_subprocess=False, version_main=141)
    except Exception:
        driver = uc.Chrome(headless=False, use_subprocess=False)
    
    driver.set_page_load_timeout(90)
    driver.set_script_timeout(90)
    driver.maximize_window()
    return driver

def human_pause(min_delay=0.7, max_delay=1.6):
    """Tạm dừng ngẫu nhiên để tránh bị chặn"""
    time.sleep(random.uniform(min_delay, max_delay))

def extract_table_html(driver, container_id, table_id):
    """Trích xuất HTML của bảng từ container"""
    try:
        container = driver.find_element(By.ID, container_id)
        html = container.get_attribute("innerHTML")
        soup = BeautifulSoup(html, "lxml")
        
        # Tìm bảng trực tiếp
        table = soup.find("table", id=table_id)
        if table:
            return str(table)
        
        # Tìm trong comments
        for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
            if table_id in comment:
                inner_soup = BeautifulSoup(comment, "lxml")
                table = inner_soup.find("table", id=table_id)
                if table:
                    return str(table)
        return None
    except Exception:
        return None

def parse_table_html(table_html, page_type):
    """Phân tích HTML bảng thành dữ liệu"""
    if not table_html:
        return []
    
    soup = BeautifulSoup(table_html, "lxml")
    table = soup.find("table")
    if not table:
        return []
    
    # Lấy headers
    headers = []
    thead = table.find("thead")
    if thead:
        last_row = thead.find_all("tr")[-1]
        for th in last_row.find_all("th"):
            headers.append(th.get("data-stat") or th.get_text(strip=True))
    
    # Xử lý dữ liệu
    rows_data = []
    tbody = table.find("tbody")
    if not tbody:
        return rows_data

    for row in tbody.find_all("tr"):
        if "thead" in row.get("class", []):
            continue
            
        cells = row.find_all(["th", "td"])
        if not cells:
            continue

        row_data = {}
        for idx, cell in enumerate(cells):
            key = headers[idx] if idx < len(headers) else f"col_{idx}"
            text = cell.get_text(strip=True)
            link = cell.find("a")
            
            # Xử lý các trường hợp đặc biệt
            if key.lower() == "player":
                row_data["player"] = text
                if link and link.get("href", "").startswith("/"):
                    row_data["player_link"] = "https://fbref.com" + link.get("href")
            elif key.lower() in ("team", "squad"):
                row_data["squad"] = text
            else:
                row_data = _process_stat_cell(row_data, key, text, page_type)
                
        rows_data.append(row_data)
    
    return rows_data

def _process_stat_cell(row_data, key, value, page_type):
    # Các cột cơ bản lấy từ bảng standard
    basic_columns = {
        "age": "age",
        "birth_year": "birth_year",
        "born": "birth_year",
        "nationality": "nation",
        "nation": "nation",
        "position": "position",
        "pos": "position",
        "minutes": "minutes",
        "games": "games",
        "ranker": "ranker",
    }

    key_lower = key.lower()

    if page_type == "standard" and key_lower in basic_columns:
        normalized_key = basic_columns[key_lower]
        row_data[normalized_key] = value
    else:
        row_data[key] = value

    return row_data

def merge_player_stats(master_data, new_rows, page_type):
    """Hợp nhất dữ liệu cầu thủ"""
    for row in new_rows:
        player = row.get("player")
        squad = row.get("squad")
        if not player:
            continue

        key = (player, squad or "")
        player_data = master_data[key]

        # Cập nhật thông tin cơ bản
        player_data.update({
            "player": player,
            "squad": squad or player_data.get("squad", "")
        })

        if "player_link" in row:
            player_data["player_link"] = row["player_link"]

        # Hợp nhất thống kê
        for stat_key, value in row.items():
            if stat_key in ("player", "squad", "player_link"):
                continue

            clean_value = value if (value and str(value).strip()) else "N/a"

            # các cột cơ bản từ bảng standard
            if page_type == "standard" and stat_key in (
                "age", "birth_year", "nation", "position", "minutes", "games", "ranker"
            ):
                if stat_key not in player_data or player_data[stat_key] in ("", "N/a"):
                    player_data[stat_key] = clean_value
            else:
                if page_type == "standard":
                    final_key = stat_key
                else:
                    base_key = stat_key
                    prefix = page_type + "_"
                    if base_key.startswith(prefix):
                        base_key = base_key[len(prefix):]
                    final_key = f"{page_type}__{base_key}"

                player_data[final_key] = clean_value


def filter_by_minutes(player_data, threshold=90):
    """Lọc cầu thủ theo số phút thi đấu"""
    print(f"\n🔍 Lọc cầu thủ có > {threshold} phút...")
    
    # Tìm cột minutes chính
    minute_columns = ['minutes', 'playing_time__minutes', 'goalkeeping__gk_minutes']
    
    filtered_players = {}
    found_players = 0
    
    for key, data in player_data.items():
        minutes = None
        
        for col in minute_columns:
            if col in data:
                try:
                    minutes = int(str(data[col]).replace(",", ""))
                    break
                except (ValueError, TypeError):
                    continue
        
        if minutes and minutes > threshold:
            filtered_players[key] = data
    return filtered_players


def clean_duplicate_columns(dataframe):
    """Làm sạch các cột trùng lặp"""
    columns_to_remove = []
    
    # Định nghĩa các nhóm cột trùng lặp
    duplicate_groups = {
        'games': ['matches', 'games'],
        'age': ['age'],
        'birth_year': ['birth_year', 'born'],
        'position': ['position'], 
        'squad': ['squad', 'team'],
        'nation': ['nation', 'nationality'],
        'ranker': ['ranker']
    }
    
    for primary_key, alternatives in duplicate_groups.items():
        found_columns = []
        for col in dataframe.columns:
            col_lower = col.lower()
            if any(alt in col_lower for alt in alternatives) and not any(x in col_lower for x in ['90', 'per_90', 'starts', 'subs']):
                found_columns.append(col)
        
        if found_columns:
            # Giữ lại cột ưu tiên
            keep_column = primary_key if primary_key in found_columns else found_columns[0]
            columns_to_remove.extend([col for col in found_columns if col != keep_column])
    
    # Loại bỏ cột trùng lặp
    columns_to_remove = list(set(columns_to_remove))
    if columns_to_remove:
        dataframe = dataframe.drop(columns=columns_to_remove)
    
    return dataframe


def save_to_sqlite(dataframe, db_path, table_name):
    """Lưu dữ liệu vào SQLite"""
    if dataframe.empty:
        print(" Không có dữ liệu để lưu")
        return
    
    # Làm sạch cột
    dataframe = clean_duplicate_columns(dataframe)
    
    # Đổi tên cột squad thành club
    if 'squad' in dataframe.columns:
        dataframe = dataframe.rename(columns={'squad': 'club'})
    
    # Sắp xếp cột - sử dụng club thay vì squad
    base_columns = ['player', 'club', 'age', 'birth_year', 'nation', 'position']
    available_base = [col for col in base_columns if col in dataframe.columns]
    
    # Sắp xếp cột thống kê theo nhóm
    stat_categories = ['standard', 'shooting', 'passing', 'passing_types', 'gca', 
                      'defense', 'possession', 'playing_time', 'misc', 'goalkeeping', 'goalkeeping_adv']
    
    stat_columns = []
    for category in stat_categories:
        category_cols = [col for col in dataframe.columns 
                        if col.startswith(f"{category}__") and col not in available_base]
        stat_columns.extend(sorted(category_cols))
    
    # Các cột còn lại
    other_columns = [col for col in dataframe.columns 
                    if col not in available_base and col not in stat_columns]
    
    final_columns = available_base + stat_columns + sorted(other_columns)
    dataframe = dataframe[final_columns]
    
    # Lưu vào database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
    
    # Tạo bảng
    column_defs = ", ".join([f"[{col}] TEXT" for col in final_columns])
    cursor.execute(f"CREATE TABLE {table_name} ({column_defs})")
    
    # Chèn dữ liệu
    records = []
    for _, row in dataframe.iterrows():
        record = []
        for col in final_columns:
            value = row[col]
            if pd.isna(value) or not str(value).strip() or str(value).lower() in ['nan', 'none']:
                record.append("N/a")
            else:
                record.append(str(value))
        records.append(tuple(record))
    
    placeholders = ", ".join(["?"] * len(final_columns))
    cursor.executemany(f"INSERT INTO {table_name} VALUES ({placeholders})", records)
    conn.commit()
    conn.close()

def main():
    
    driver = build_driver()
    all_players = defaultdict(dict)

    try:
        # Thu thập dữ liệu từ các trang thống kê
        for stat_type, (url_suffix, table_id, container_id) in STAT_PAGES.items():
            url = f"{BASE_SEASON_URL}/{url_suffix}/{SEASON_NAME}"
            print(f"Đang xử lý {stat_type}...")
            
            driver.get(url)
            
            # Chờ trang load
            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.ID, container_id))
                )
            except TimeoutException:
                print(f"  Timeout khi chờ {container_id}")
                continue
            
            human_pause(WAIT_SEC, WAIT_SEC + 0.5)
            
            # Trích xuất và phân tích dữ liệu
            table_html = extract_table_html(driver, container_id, table_id)
            if not table_html:
                print(f"   ❌ Không tìm thấy bảng {table_id}")
                continue
            
            rows = parse_table_html(table_html, stat_type)
            print(f"   ✅ {len(rows)} cầu thủ")
            
            merge_player_stats(all_players, rows, stat_type)
            human_pause(0.5, 1.0)
        
        # Lọc cầu thủ
        filtered_players = filter_by_minutes(all_players, MIN_MINUTES_THRESHOLD)
        
        if not filtered_players:
            print("❌ Không có cầu thủ nào đủ điều kiện")
            return
        
        # Chuẩn bị và lưu dữ liệu
        df = pd.DataFrame(list(filtered_players.values()))
        
        if "player_link" in df.columns:
            df = df.drop(columns=["player_link"])
        
        save_to_sqlite(df, DB_FILE, OUT_TABLE)
        
        print(f"\n Dữ liệu đã được lưu vào {DB_FILE}")

    finally:
        driver.quit()

if __name__ == "__main__":
    main()