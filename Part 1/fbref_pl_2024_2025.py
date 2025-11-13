import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

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

BASE_SEASON_URL = "https://fbref.com/en/comps/9/2024-2025"
SEASON_NAME = "2024-2025-Premier-League-Stats"
DB_FILE = "fbref_pl_2024_2025_full.sqlite"
OUT_TABLE = "player_stats_cleaned"
MIN_MINUTES_THRESHOLD = 90
WAIT_SEC = 1.5

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


def build_driver():
    """Khởi tạo Chrome driver với undetected_chromedriver"""
    print("Đang khởi tạo Chrome driver...")
    try:
        driver = uc.Chrome(headless=False, use_subprocess=False, version_main=141)
        print("Driver đã khởi tạo thành công (Chrome v141)!")
    except Exception:
        print("Không thể khởi tạo với version 141, thử auto detect...")
        driver = uc.Chrome(headless=False, use_subprocess=False)
        print("Driver auto detect thành công!")
    driver.set_page_load_timeout(90)
    driver.set_script_timeout(90)
    driver.maximize_window()
    return driver


def human_pause(a=0.7, b=1.6):
    """Tạo khoảng dừng ngẫu nhiên giống hành vi người dùng"""
    time.sleep(random.uniform(a, b))


def extract_table_html_from_container(driver, container_id, expected_table_id):
    """Trích xuất HTML của bảng từ container"""
    try:
        container = driver.find_element(By.ID, container_id)
        html = container.get_attribute("innerHTML")
        soup = BeautifulSoup(html, "lxml")
        
        direct_tbl = soup.find("table", id=expected_table_id)
        if direct_tbl:
            return str(direct_tbl)
        
        for c in soup.find_all(string=lambda t: isinstance(t, Comment)):
            if expected_table_id in c:
                inner = BeautifulSoup(c, "lxml")
                tbl = inner.find("table", id=expected_table_id)
                if tbl:
                    return str(tbl)
        return None
    except Exception as e:
        print(f"Lỗi khi tách bảng {expected_table_id}: {e}")
        return None


def parse_table_html(table_html, page_tag):
    """Parse HTML của bảng thành danh sách dictionary"""
    rows_data = []
    soup = BeautifulSoup(table_html, "lxml")
    table = soup.find("table")
    if not table:
        return rows_data
    
    headers = []
    thead = table.find("thead")
    if thead:
        last_tr = thead.find_all("tr")[-1]
        for th in last_tr.find_all("th"):
            headers.append(th.get("data-stat") or th.get_text(strip=True))
    
    tbody = table.find("tbody")
    if not tbody:
        return rows_data

    for tr in tbody.find_all("tr"):
        if "thead" in tr.get("class", []):
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
            
            if key.lower() == "player":
                row["player"] = text
                if href and href.startswith("/"):
                    row["player_link"] = "https://fbref.com" + href
            elif key.lower() in ("team", "squad"):
                row["squad"] = text
            else:
                if page_tag == "standard" and key.lower() in ("age", "birth_year", "born", "nationality", "nation", "position", "pos"):
                    norm = {
                        "age": "standard__age",
                        "birth_year": "standard__birth_year",
                        "born": "standard__birth_year",
                        "nationality": "standard__nationality",
                        "nation": "standard__nationality",
                        "position": "standard__position",
                        "pos": "standard__position"
                    }.get(key.lower(), key)
                    row[norm] = text
                else:
                    row[key] = text
        rows_data.append(row)
    return rows_data


def merge_stats(master, rows, page_tag):
    """Gộp dữ liệu từ các trang khác nhau vào master dictionary"""
    for r in rows:
        player = r.get("player")
        squad = r.get("squad") or r.get("team")
        if not player:
            continue

        key = (player, squad or "")
        entry = master[key]
        entry["player"] = player
        entry["squad"] = squad or entry.get("squad") or ""
        if "player_link" in r:
            entry["player_link"] = r["player_link"]
        
        for k, v in r.items():
            if k in ("player", "squad", "team", "player_link"):
                continue
            
            val = v if (v is not None and str(v).strip() != "") else "N/a"
            
            if k.startswith("standard__"):
                if k not in entry or entry[k] in ("", "N/a"):
                    entry[k] = val
                continue
            
            prefixed = f"{page_tag}__{k}"
            entry[prefixed] = val


def as_int_safe(x):
    """Chuyển đổi giá trị sang integer một cách an toàn"""
    try:
        return int(str(x).replace(",", ""))
    except Exception:
        return None


def filter_min_over_90(master):
    """Lọc các cầu thủ có số phút thi đấu > ngưỡng tối thiểu"""
    print("\nDò cột 'minutes' để lọc > 90...")
    
    all_keys = set()
    for data in master.values():
        all_keys.update(data.keys())
    
    minute_like = [k for k in all_keys if ("minute" in k.lower() or k.lower() in ("min", "mins", "minutes"))]
    minute_like_sorted = sorted(minute_like, key=lambda s: (("90" in s) or ("per_90" in s) or ("90s" in s)))
    print(f"Phát hiện cột phút: {minute_like_sorted if minute_like_sorted else '(không thấy)'}")
    
    filtered = {}
    for key, data in master.items():
        minutes = None
        for c in minute_like_sorted:
            if c in data and not any(x in c.lower() for x in ["90", "per_90", "90s"]):
                minutes = as_int_safe(data.get(c, ""))
                if minutes is not None:
                    break
        
        if minutes is not None and minutes > MIN_MINUTES_THRESHOLD:
            filtered[key] = data
    
    print(f"{len(filtered)} cầu thủ có > {MIN_MINUTES_THRESHOLD} phút.")
    return filtered


def write_sqlite(db_path, table_name, records):
    """Ghi dữ liệu vào SQLite database"""
    if not records:
        print("Không có bản ghi để ghi.")
        return
    
    all_cols = set()
    for r in records:
        all_cols.update(r.keys())
    
    all_cols.discard("player_link")
    
    rename_meta = {
        "standard__age": "age",
        "standard__birth_year": "birth_year",
        "standard__nationality": "nation",
        "standard__position": "position"
    }
    
    head_cols = [c for c in ["player", "squad", "age", "birth_year", "nation", "position"] if c in (set(rename_meta.values()) | all_cols)]
    other_cols = []
    for c in sorted(all_cols):
        if c in rename_meta:
            short = rename_meta[c]
            if short not in head_cols and short not in other_cols and short not in ["player", "squad"]:
                other_cols.append(short)
        elif c not in head_cols and c not in rename_meta.values():
            other_cols.append(c)
    
    cols = head_cols + other_cols
    
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(f"DROP TABLE IF EXISTS [{table_name}];")
    cur.execute(f"CREATE TABLE [{table_name}] ({', '.join(f'[{c}] TEXT' for c in cols)});")
    
    batch = []
    for r in records:
        row = []
        mapped = dict(r)
        for old, new in rename_meta.items():
            if old in mapped and (new not in mapped or mapped.get(new) in ("", None, "N/a")):
                mapped[new] = mapped.get(old)
        
        for c in cols:
            val = mapped.get(c, "N/a")
            if val is None or str(val).strip() == "" or str(val).lower() in ["nan", "none"]:
                val = "N/a"
            row.append(str(val))
        batch.append(tuple(row))
    
    placeholders = ", ".join(["?"] * len(cols))
    cur.executemany(f"INSERT INTO [{table_name}] VALUES ({placeholders});", batch)
    conn.commit()
    conn.close()
    print(f"Đã ghi {len(records)} bản ghi vào {db_file_short(db_path)} (bảng {table_name})")


def db_file_short(p):
    """Lấy tên file từ đường dẫn đầy đủ"""
    return p.split("/")[-1].split("\\")[-1]


def find_duplicate_columns(df):
    """Tìm các cột có dữ liệu trùng lặp"""
    print("\nĐang tìm các cột có dữ liệu trùng lặp...")
    
    duplicate_pairs = {}
    columns = list(df.columns)
    protected_cols = ["player", "squad", "age", "birth_year", "nation", "position"]
    
    for i in range(len(columns)):
        for j in range(i + 1, len(columns)):
            col1, col2 = columns[i], columns[j]
            
            if col1 in duplicate_pairs or col2 in duplicate_pairs:
                continue
            
            try:
                series1 = df[col1].astype(str).str.strip()
                series2 = df[col2].astype(str).str.strip()
                
                match_count = (series1 == series2).sum()
                total_count = len(df)
                match_ratio = match_count / total_count if total_count > 0 else 0
                
                if match_ratio >= 0.95:
                    if col1 in protected_cols:
                        keep, remove = col1, col2
                    elif col2 in protected_cols:
                        keep, remove = col2, col1
                    elif "__" not in col1 and "__" in col2:
                        keep, remove = col1, col2
                    elif "__" not in col2 and "__" in col1:
                        keep, remove = col2, col1
                    elif col1.startswith("standard__") and not col2.startswith("standard__"):
                        keep, remove = col1, col2
                    elif col2.startswith("standard__") and not col1.startswith("standard__"):
                        keep, remove = col2, col1
                    else:
                        keep, remove = (col1, col2) if len(col1) <= len(col2) else (col2, col1)
                    
                    duplicate_pairs[remove] = keep
                    print(f"  Phát hiện trùng lặp ({match_ratio*100:.1f}%): '{remove}' => '{keep}'")
            
            except Exception:
                continue
    
    if not duplicate_pairs:
        print("  Không tìm thấy cột trùng lặp nào!")
    else:
        print(f"\n  Tổng cộng: {len(duplicate_pairs)} cột sẽ bị loại bỏ")
    
    return duplicate_pairs


def remove_duplicate_columns(df):
    """Loại bỏ các cột trùng lặp khỏi DataFrame"""
    duplicate_pairs = find_duplicate_columns(df)
    
    if duplicate_pairs:
        cols_to_remove = list(duplicate_pairs.keys())
        print(f"\nĐang xóa {len(cols_to_remove)} cột trùng lặp...")
        df_cleaned = df.drop(columns=cols_to_remove)
        print(f"  Đã xóa: {', '.join(cols_to_remove[:10])}{'...' if len(cols_to_remove) > 10 else ''}")
        return df_cleaned, duplicate_pairs
    
    return df, {}


def main():
    """Hàm chính: Crawl dữ liệu từ FBref và lưu vào SQLite"""
    print("=== Thu thập & lọc dữ liệu cầu thủ Premier League 2024-2025 ===")
    driver = build_driver()
    master = defaultdict(dict)

    try:
        for page_tag, (suffix, table_id, container_id) in STAT_PAGES.items():
            url = f"{BASE_SEASON_URL}/{suffix}/{SEASON_NAME}"
            print(f"[{page_tag}] -> {url}")
            driver.get(url)
            
            try:
                WebDriverWait(driver, 25).until(EC.presence_of_element_located((By.ID, container_id)))
            except TimeoutException:
                pass
            
            human_pause(WAIT_SEC, WAIT_SEC + 0.8)
            
            table_html = extract_table_html_from_container(driver, container_id, table_id)
            if not table_html:
                print(f"  Không tách được bảng {table_id}")
                continue
            
            rows = parse_table_html(table_html, page_tag)
            print(f"  {len(rows)} dòng")
            merge_stats(master, rows, page_tag)
            human_pause(0.8, 1.4)
        
        filtered = filter_min_over_90(master)
        if not filtered:
            print("Không có cầu thủ nào qua ngưỡng phút - kiểm tra lại cột minutes.")
            return
        
        df = pd.DataFrame(list(filtered.values()))
        
        rename_meta = {
            "standard__age": "age",
            "standard__birth_year": "birth_year",
            "standard__nationality": "nation",
            "standard__position": "position"
        }
        for old, new in rename_meta.items():
            if old in df.columns and new not in df.columns:
                df[new] = df[old]
        
        if "player_link" in df.columns:
            df = df.drop(columns=["player_link"])
        
        print(f"\nTổng cột trước khi lọc trùng lặp: {len(df.columns)}")
        df, duplicate_info = remove_duplicate_columns(df)
        print(f"Tổng cột sau khi lọc trùng lặp: {len(df.columns)}")
        
        base_heads = ["player","squad","age","birth_year","nation","position"]
        ordered = [c for c in base_heads if c in df.columns] + [c for c in sorted(df.columns) if c not in base_heads]
        df = df.loc[:, ordered]
        
        if duplicate_info:
            print("\nBáo cáo các cột đã xóa do trùng lặp:")
            for removed, kept in list(duplicate_info.items())[:20]:
                print(f"  '{removed}' -> giữ lại '{kept}'")
            if len(duplicate_info) > 20:
                print(f"  ... và {len(duplicate_info) - 20} cột khác")
        
        write_sqlite(DB_FILE, OUT_TABLE, df.to_dict(orient="records"))
        print(f"\nDữ liệu đã được lưu: {DB_FILE}")

    finally:
        try:
            driver.quit()
        except:
            pass


if __name__ == "__main__":
    main()
