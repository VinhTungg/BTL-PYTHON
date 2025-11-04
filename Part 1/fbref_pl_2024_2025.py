# -*- coding: utf-8 -*-
import os
import sys
import random
import time
import sqlite3
from collections import defaultdict
from bs4 import BeautifulSoup, Comment

# Fix encoding cho Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, StaleElementReferenceException, WebDriverException
)

# ==========================
# ⚙️ CẤU HÌNH
# ==========================
# Không cần chrome_driver_path nữa vì undetected_chromedriver tự quản lý
BASE_SEASON_URL = "https://fbref.com/en/comps/9/2024-2025"
SEASON_NAME = "2024-2025-Premier-League-Stats"

STAT_PAGES = {
    "standard":      ("stats",          "stats_standard",       "all_stats_standard"),
    "shooting":      ("shooting",       "stats_shooting",       "all_stats_shooting"),
    "passing":       ("passing",        "stats_passing",        "all_stats_passing"),
    "passing_types": ("passing_types",  "stats_passing_types",  "all_stats_passing_types"),
    "gca":           ("gca",            "stats_gca",            "all_stats_gca"),
    "defense":       ("defense",        "stats_defense",        "all_stats_defense"),
    "possession":    ("possession",     "stats_possession",     "all_stats_possession"),
    "misc":          ("misc",           "stats_misc",           "all_stats_misc"),
    "goalkeeping":   ("keepers",        "stats_keeper",         "all_stats_keeper"),
    "goalkeeping_adv": ("keepersadv",   "stats_keeper_adv",     "all_stats_keeper_adv"),
}

SKIP_MISSING_PAGE = True
MIN_MINUTES_THRESHOLD = 90

def build_driver():
    """
    Sử dụng undetected_chromedriver để bypass Cloudflare protection
    """
    print("🔧 Đang khởi tạo Chrome driver...")
    
    try:
        # Chỉ định version_main=141 để khớp với Chrome browser hiện tại
        driver = uc.Chrome(
            headless=False,
            use_subprocess=False,
            version_main=141  # Chỉ định version Chrome hiện tại
        )
        
        print("✅ Driver đã khởi tạo thành công!")
        
        # Tăng timeout cho page load
        driver.set_page_load_timeout(90)
        driver.set_script_timeout(90)
        
        # Maximize window để tránh bị phát hiện là bot
        driver.maximize_window()
        
        return driver
        
    except Exception as e:
        print(f"⚠️ Không thể dùng version 141, thử tự động detect...")
        
        try:
            # Thử để None để tự động detect
            driver = uc.Chrome(
                headless=False,
                use_subprocess=False
            )
            
            print("✅ Driver đã khởi tạo thành công!")
            driver.set_page_load_timeout(90)
            driver.set_script_timeout(90)
            driver.maximize_window()
            
            return driver
            
        except Exception as e2:
            print(f"❌ Lỗi: {e2}")
            print("\n💡 GIẢI PHÁP: Vui lòng cập nhật Chrome browser lên version mới nhất:")
            print("   1. Mở Chrome → Menu (3 chấm) → Help → About Google Chrome")
            print("   2. Chrome sẽ tự động cập nhật")
            raise

def human_pause(a=0.7, b=1.8):
    time.sleep(random.uniform(a, b))

def random_scroll(driver, steps=3):
    try:
        for _ in range(steps):
            y = random.randint(200, 1200)
            driver.execute_script(f"window.scrollBy(0, {y});")
            time.sleep(random.uniform(0.2, 0.6))
        driver.execute_script("window.scrollBy(0, -150);")
        time.sleep(random.uniform(0.2, 0.5))
    except WebDriverException:
        pass

def wait_for_container(driver, container_id, timeout=20):
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.ID, container_id))
        )
        return True
    except TimeoutException:
        return False

def extract_table_html_from_container(driver, container_id, expected_table_id):
    try:
        container = driver.find_element(By.ID, container_id)
        html = container.get_attribute("innerHTML")
        soup = BeautifulSoup(html, "lxml")
        comments = soup.find_all(string=lambda text: isinstance(text, Comment))
        for c in comments:
            try:
                inner = BeautifulSoup(c, "lxml")
                tbl = inner.find("table", id=expected_table_id)
                if tbl:
                    return str(tbl)
            except Exception:
                continue
        direct_tbl = soup.find("table", id=expected_table_id)
        if direct_tbl:
            return str(direct_tbl)
    except NoSuchElementException:
        return None
    return None

def parse_table_html(table_html):
    rows_data = []
    soup = BeautifulSoup(table_html, "lxml")
    table = soup.find("table")
    if not table:
        return rows_data

    headers = []
    thead = table.find("thead")
    if thead:
        last_tr = thead.find_all("tr")[-1]
        ths = last_tr.find_all("th")
        for th in ths:
            col = th.get("data-stat") or th.get_text(strip=True)
            headers.append(col)

    tbody = table.find("tbody")
    if not tbody:
        return rows_data

    for tr in tbody.find_all("tr"):
        cl = tr.get("class", [])
        if "thead" in cl:
            continue
        cells = tr.find_all(["th", "td"])
        if not cells:
            continue
        row = {}
        for idx, cell in enumerate(cells):
            key = headers[idx] if idx < len(headers) else f"col_{idx}"
            text = cell.get_text(strip=True)
            link = cell.find("a")
            href = link.get("href") if link else ""
            if key in ("player", "Player"):
                row["player"] = text
                if href and href.startswith("/"):
                    row["player_link"] = "https://fbref.com" + href
                elif href:
                    row["player_link"] = href
            elif key in ("team", "squad", "Squad"):
                row["squad"] = text
            else:
                row[key] = text
        rows_data.append(row)
    return rows_data

def to_int_safe(x):
    try:
        return int(str(x).replace(",", ""))
    except Exception:
        return None

def merge_stats(master, rows, page_tag):
    # Quy tắc lọc cột trùng lặp theo prefix trang
    # - Với mọi trang KHÔNG phải 'standard': bỏ qua các cột chung đã có ở standard
    # - Riêng 'goalkeeping_adv': bỏ thêm 2 cột trùng với 'goalkeeping'
    # Dùng lowercase để so sánh
    COMMON_DUPLICATE_COLS_LOWER = {
        # Thông tin cá nhân (trùng giữa các trang, chỉ giữ ở standard)
        "age",
        "nationality", "nation",
        "birth_year", "born",
        "position", "pos",

        # Thông tin trận đấu (chỉ giữ ở standard)
        "matches", "match", "mp", "games",
        "starts", "start", "gs",
        "minutes", "min", "minutes_90s", "90s", "minutes_per_90",

        # Cột ranking (chỉ giữ ở standard)
        "ranker", "rk", "rank",

        # Một số thống kê tổng hợp cơ bản (đã có trong standard)
        "goals", "assists",
        "xg", "npxg", "xg_assist",
        "pens_made", "pens_att",
        "cards_yellow", "cards_red",
        "progressive_passes", "progressive_carries", "progressive_passes_received",
        "passes", "passes_completed",
        "crosses", "interceptions", "tackles_won",

        # Các cột khác
        "games_starts", "minutes_per_match",
    }

    GK_DUPES_LOWER = {"gk_goals_against", "gk_pens_allowed"}
    
    for r in rows:
        player = r.get("player") or r.get("Player")
        squad = r.get("squad") or r.get("Squad") or r.get("team")
        if not player:
            continue
        key = (player, squad or "")
        entry = master[key]
        entry["player"] = player
        entry["squad"] = squad or entry.get("squad") or ""
        if "player_link" in r:
            entry["player_link"] = r["player_link"]
        
        for k, v in r.items():
            if k in ("player", "Player", "squad", "Squad", "team", "player_link"):
                continue
            
            k_lower = k.lower()
            
            # Quy tắc lọc cột trùng lặp:
            # 1) standard: giữ TẤT CẢ
            # 2) các trang khác: bỏ các cột chung đã có ở standard
            # 3) riêng goalkeeping_adv: bỏ thêm 2 cột trùng với goalkeeping
            
            skip = False
            
            # Bỏ các cột chung ở mọi trang không phải standard
            if page_tag != "standard" and k_lower in COMMON_DUPLICATE_COLS_LOWER:
                skip = True

            # Riêng goalkeeping_adv: bỏ 2 cột trùng với goalkeeping
            if not skip and page_tag == "goalkeeping_adv" and k_lower in GK_DUPES_LOWER:
                skip = True
            
            if skip:
                continue
            
            col_name = f"{page_tag}__{k}"
            entry[col_name] = v if v != "" else "N/a"

def filter_min_over_90(master):
    CANDIDATE_KEYS = [
        "standard__minutes", "standard__Min", "standard__mins", "standard__min",
        "minutes", "Min"
    ]
    filtered = {}
    for key, data in master.items():
        minutes = None
        for c in CANDIDATE_KEYS:
            if c in data:
                minutes = to_int_safe(data.get(c, ""))
                if minutes is not None:
                    break
        if minutes is None:
            minutes = 0
        if minutes > MIN_MINUTES_THRESHOLD:
            filtered[key] = data
    return filtered

def write_sqlite(db_path, table_name, records):
    if not records:
        print("[SQLITE] Không có bản ghi để ghi.")
        return
    all_cols = set()
    for r in records:
        all_cols.update(r.keys())
    id_cols = ["player", "squad", "player_link"]
    other_cols = [c for c in sorted(all_cols) if c not in id_cols]
    cols = id_cols + other_cols

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # Xóa bảng cũ nếu có (để tránh lỗi cấu trúc khác nhau)
    cur.execute(f"DROP TABLE IF EXISTS [{table_name}];")
    
    # Tạo bảng mới với cấu trúc đầy đủ
    columns_sql = ", ".join([f'[{c}] TEXT' for c in cols])
    cur.execute(f"CREATE TABLE [{table_name}] ({columns_sql});")

    placeholders = ", ".join(["?"] * len(cols))
    insert_sql = f"INSERT INTO [{table_name}] ({', '.join('['+c+']' for c in cols)}) VALUES ({placeholders});"

    batch = []
    for r in records:
        row = []
        for c in cols:
            val = r.get(c, None)
            if val is None or val == "":
                val = "N/a"
            row.append(str(val))
        batch.append(tuple(row))
    cur.executemany(insert_sql, batch)
    conn.commit()
    conn.close()
    print(f"[SQLITE] Đã ghi {len(records)} bản ghi vào {db_path} bảng {table_name}")

def main():
    print("=== FBref Premier League 2024-2025: Thu thập thống kê cầu thủ (Min > 90) ===")
    print(f"Base season URL: {BASE_SEASON_URL}/{SEASON_NAME}")
    print("Các bảng sẽ thu thập:", ", ".join(STAT_PAGES.keys()))
    driver = build_driver()

    failed_pages = []
    master = defaultdict(dict)

    try:
        for page_tag, (suffix, table_id, container_id) in STAT_PAGES.items():
            # Build URL đúng format: /comps/9/2024-2025/[suffix]/2024-2025-Premier-League-Stats
            url = f"{BASE_SEASON_URL}/{suffix}/{SEASON_NAME}"
            print(f"[{page_tag}] -> {url}")
            
            # Retry logic cho việc load trang
            max_retries = 3
            page_loaded = False
            
            for attempt in range(max_retries):
                try:
                    if attempt > 0:
                        print(f"  ⟳ Thử lại lần {attempt + 1}/{max_retries}...")
                        human_pause(3.0, 5.0)  # Đợi lâu hơn khi retry
                    
                    driver.get(url)
                    
                    # Đợi thêm để Cloudflare có thời gian verify
                    human_pause(3.0, 5.0)
                    
                    page_loaded = True
                    break
                    
                except TimeoutException as e:
                    print(f"  ⚠ Timeout khi load trang (lần thử {attempt + 1})")
                    if attempt == max_retries - 1:
                        failed_pages.append((page_tag, url, f"Timeout sau {max_retries} lần thử"))
                        
                except WebDriverException as e:
                    print(f"  ⚠ Lỗi WebDriver: {str(e)[:100]}")
                    if attempt == max_retries - 1:
                        failed_pages.append((page_tag, url, str(e)[:200]))
            
            if not page_loaded:
                if SKIP_MISSING_PAGE:
                    continue
                else:
                    break

            human_pause(1.5, 2.5)
            random_scroll(driver, steps=random.randint(2, 5))
            ok = wait_for_container(driver, container_id, timeout=25)
            if not ok:
                failed_pages.append((page_tag, url, "Không tìm thấy container"))
                continue

            table_html = extract_table_html_from_container(driver, container_id, table_id)
            if not table_html:
                failed_pages.append((page_tag, url, "Không tách được bảng từ comment"))
                continue

            rows = parse_table_html(table_html)
            print(f"  ✓ {len(rows)} dòng")
            merge_stats(master, rows, page_tag)
            human_pause(1.0, 2.0)

        filtered = filter_min_over_90(master)
        print(f"==> {len(filtered)} cầu thủ chơi > {MIN_MINUTES_THRESHOLD} phút")

        out_db = "fbref_pl_2024_2025.sqlite"
        out_table = "player_stats_over_90min"
        write_sqlite(out_db, out_table, list(filtered.values()))

        if failed_pages:
            print("\n⚠ CÁC TRANG BỊ LỖI:")
            for tag, url, err in failed_pages:
                print(f"  ❌ [{tag}] {err}")
            print(f"\nĐã cào thành công: {len(STAT_PAGES) - len(failed_pages)}/{len(STAT_PAGES)} trang")
        else:
            print("\n✅ Hoàn thành! Không có trang nào bị lỗi.")
        
        print(f"\n📊 Kết quả: {len(filtered)} cầu thủ đã được lưu vào database")
        print(f"📁 File: {out_db} | Bảng: {out_table}")
        
    except KeyboardInterrupt:
        print("\n⚠ Đã dừng bởi người dùng")
    finally:
        try:
            driver.quit()
        except:
            pass

if __name__ == "__main__":
    main()
