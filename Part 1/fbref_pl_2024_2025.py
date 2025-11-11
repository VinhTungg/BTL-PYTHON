# -*- coding: utf-8 -*-
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import time
import random
import sqlite3
import re
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
    print("🔧 Đang khởi tạo Chrome driver...")
    try:
        driver = uc.Chrome(headless=False, use_subprocess=False, version_main=141)
        print("✅ Driver đã khởi tạo thành công (Chrome v141)!")
    except Exception:
        print("⚠️ Không thể khởi tạo với version 141, thử auto detect...")
        driver = uc.Chrome(headless=False, use_subprocess=False)
        print("✅ Driver auto detect thành công!")
    driver.set_page_load_timeout(90)
    driver.set_script_timeout(90)
    driver.maximize_window()
    return driver


def human_pause(a=0.7, b=1.6):
    time.sleep(random.uniform(a, b))


def extract_table_html_from_container(driver, container_id, expected_table_id):
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
        print(f"⚠️ Lỗi khi tách bảng {expected_table_id}: {e}")
        return None


def parse_table_html(table_html, page_tag):
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
    try:
        return int(str(x).replace(",", ""))
    except Exception:
        return None


def filter_min_over_90(master):
    print("\n🔍 Dò cột 'minutes' để lọc > 90...")
    
    all_keys = set()
    for data in master.values():
        all_keys.update(data.keys())
    
    minute_like = [k for k in all_keys if ("minute" in k.lower() or k.lower() in ("min", "mins", "minutes"))]
    minute_like_sorted = sorted(minute_like, key=lambda s: (("90" in s) or ("per_90" in s) or ("90s" in s)))
    print(f"📋 Phát hiện cột phút: {minute_like_sorted if minute_like_sorted else '(không thấy)'}")
    
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
    
    print(f"✅ {len(filtered)} cầu thủ có > {MIN_MINUTES_THRESHOLD} phút.")
    return filtered


def write_sqlite(db_path, table_name, records):
    if not records:
        print("[SQLITE] Không có bản ghi để ghi.")
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
    print(f"[SQLITE] ✅ Đã ghi {len(records)} bản ghi vào {db_file_short(db_path)} (bảng {table_name})")


def db_file_short(p):
    return p.split("/")[-1].split("\\")[-1]


def curate_keep_columns(df_cols):
    base = [
        "player","squad","age","birth_year","nation","position",
        "standard__games","standard__games_starts","standard__minutes","standard__npxg",
        "standard__xg","standard__xg_assist","standard__progressive_passes",
        "standard__progressive_carries","standard__progressive_passes_received",
        "standard__goals","standard__assists","standard__goals_assists",
        "standard__cards_yellow","standard__cards_red",
    ]

    shooting = [
        "shooting__shots","shooting__shots_on_target","shooting__shots_per90",
        "shooting__npxg_net","shooting__xg_net",
    ]

    passing = [
        "passing__passes_completed_short","passing__passes_completed_medium","passing__passes_completed_long",
        "passing__passes_pct_short","passing__passes_pct_medium","passing__passes_pct",
        "passing__passes_long","passing__passes_into_final_third","passing__passes_into_penalty_area",
        "passing__pass_xa","passing__xg_assist_net","passing__passes_progressive_distance",
        "passing__passes_total_distance","passing__assisted_shots",
    ]

    passtypes = [
        "passing_types__through_balls","passing_types__passes_switches",
        "passing_types__corner_kicks","passing_types__corner_kicks_in",
        "passing_types__corner_kicks_out","passing_types__passes_blocked",
        "passing_types__passes_live","passing_types__passes_dead",
    ]

    gca = [
        "gca__gca","gca__gca_passes_live","gca__sca","gca__sca_per90",
        "gca__sca_shots","gca__sca_take_ons","gca__sca_fouled",
    ]

    possession = [
        "possession__touches","possession__touches_live_ball",
        "possession__touches_att_3rd","possession__touches_att_pen_area",
        "possession__touches_def_3rd","possession__touches_mid_3rd",
        "possession__carries","possession__carries_progressive_distance",
        "possession__carries_into_final_third","possession__carries_into_penalty_area",
        "possession__passes_received","possession__take_ons","possession__take_ons_won",
        "possession__take_ons_tackled","possession__miscontrols","possession__dispossessed",
    ]

    defense = [
        "defense__tackles","defense__tackles_def_3rd","defense__tackles_mid_3rd",
        "defense__tackles_att_3rd","defense__tackles_interceptions",
        "defense__blocks","defense__blocked_shots","defense__blocked_passes",
        "defense__clearances","defense__errors","defense__challenges","defense__challenges_lost",
        "defense__challenge_tackles","defense__interceptions",
    ]

    misc = [
        "misc__fouls","misc__fouled","misc__offsides","misc__aerials_won",
        "misc__aerials_lost","misc__ball_recoveries",
    ]

    gk = [
        "goalkeeping__minutes_90s","goalkeeping_adv__minutes_90s",
        "goalkeeping__gk_saves","goalkeeping__gk_save_pct",
        "goalkeeping__gk_goals_against","goalkeeping__gk_pens_allowed",
    ]

    wish = base + shooting + passing + passtypes + gca + possession + defense + misc + gk
    return [c for c in wish if c in df_cols or c.replace("standard__", "") in df_cols]


def main():
    print("=== Thu thập & lọc dữ liệu cầu thủ Premier League 2024–2025 ===")
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
                print(f"  ⚠ Không tách được bảng {table_id}")
                continue
            
            rows = parse_table_html(table_html, page_tag)
            print(f"  ✓ {len(rows)} dòng")
            merge_stats(master, rows, page_tag)
            human_pause(0.8, 1.4)
        
        filtered = filter_min_over_90(master)
        if not filtered:
            print("[!] Không có cầu thủ nào qua ngưỡng phút – kiểm tra lại cột minutes.")
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
        
        base_heads = ["player","squad","age","birth_year","nation","position"]
        ordered = [c for c in base_heads if c in df.columns] + [c for c in sorted(df.columns) if c not in base_heads]
        df = df.loc[:, ordered]
        
        print(f"\n[+] Tổng cột (giữ tất cả): {len(df.columns)}")
        
        write_sqlite(DB_FILE, OUT_TABLE, df.to_dict(orient="records"))
        print(f"\n📊 Dữ liệu đã được lưu: {DB_FILE}")

    finally:
        try:
            driver.quit()
        except:
            pass


if __name__ == "__main__":
    main()