# -*- coding: utf-8 -*-
"""
Script thu thập giá chuyển nhượng từ footballtransfers.com
cho các cầu thủ Premier League 2024-2025 (>90 phút)
"""
import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

import sqlite3
import time
import random
import re
from bs4 import BeautifulSoup
import undetected_chromedriver as uc
from selenium.common.exceptions import TimeoutException, WebDriverException

# ==========================
# ⚙️ CẤU HÌNH
# ==========================
# Không cần chrome_driver_path nữa vì undetected_chromedriver tự quản lý
DB_PATH = "fbref_pl_2024_2025.sqlite"
SOURCE_TABLE = "player_stats_over_90min"
TARGET_DB_PATH = "player_transfer_values.sqlite"  # Ghi sang DB riêng
TARGET_TABLE = "player_transfer_values"

# Rate limiting - Cân bằng giữa tốc độ và tránh Cloudflare
MIN_DELAY = 0.5  # giây
MAX_DELAY = 0.5  # giây
MAX_RETRIES = 2  # Tăng số lần retry
PAGE_TIMEOUT = 120  # Timeout vừa phải

# Giới hạn tổng thời gian chạy ~< 20 phút (đệm 1 phút)
RUN_MAX_SECONDS = 50 * 60

def build_driver(headless=False):
    """
    Khởi tạo undetected-chromedriver để bypass Cloudflare protection
    KHÔNG dùng headless mode vì gây timeout với Cloudflare
    """
    print("🔧 Đang khởi tạo Chrome driver...")
    
    try:
        # Tạo driver tối ưu tốc độ tải (không headless để tránh Cloudflare)
        options = uc.ChromeOptions()
        options.page_load_strategy = "eager"  # không đợi tài nguyên phụ
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-extensions")
        options.add_argument("--blink-settings=imagesEnabled=false")  # tắt tải ảnh

        driver = uc.Chrome(
            headless=False,  # Bắt buộc phải False
            use_subprocess=False,
            version_main=141,
            options=options
        )
        
        print("✅ Driver đã khởi tạo thành công!")
        
        # Timeout và implicit wait
        driver.set_page_load_timeout(PAGE_TIMEOUT)
        driver.set_script_timeout(PAGE_TIMEOUT)
        driver.implicitly_wait(0)  # không cần implicit wait vì chỉ đọc page_source
        
        # Minimize window thay vì headless
        driver.minimize_window()
        
        return driver
        
    except Exception as e:
        print(f"⚠️ Thử với cấu hình tự động detect...")
        
        try:
            options = uc.ChromeOptions()
            options.page_load_strategy = "eager"
            options.add_argument("--disable-gpu")
            options.add_argument("--disable-extensions")
            options.add_argument("--blink-settings=imagesEnabled=false")

            driver = uc.Chrome(
                headless=False,
                use_subprocess=False,
                options=options
            )
            
            print("✅ Driver đã khởi tạo thành công!")
            driver.set_page_load_timeout(PAGE_TIMEOUT)
            driver.set_script_timeout(PAGE_TIMEOUT)
            driver.implicitly_wait(0)
            driver.minimize_window()
            
            return driver
            
        except Exception as e2:
            print(f"❌ Lỗi: {e2}")
            raise

def name_to_slug(name):
    """Convert player name to URL slug"""
    slug = name.lower()
    
    # Xử lý các ký tự đặc biệt phổ biến
    replacements = {
        'á': 'a', 'à': 'a', 'ã': 'a', 'â': 'a', 'ä': 'a',
        'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
        'í': 'i', 'ì': 'i', 'î': 'i', 'ï': 'i',
        'ó': 'o', 'ò': 'o', 'õ': 'o', 'ô': 'o', 'ö': 'o',
        'ú': 'u', 'ù': 'u', 'û': 'u', 'ü': 'u',
        'ñ': 'n', 'ç': 'c', 'ø': 'o', 'å': 'a',
        'ş': 's', 'ğ': 'g', 'ı': 'i',
    }
    
    for old, new in replacements.items():
        slug = slug.replace(old, new)
    
    # Replace spaces with hyphens
    slug = slug.replace(' ', '-')
    
    # Remove remaining special characters
    slug = re.sub(r'[^\w-]', '', slug)
    
    # Remove multiple consecutive hyphens
    slug = re.sub(r'-+', '-', slug)
    
    return slug.strip('-')

def get_transfer_value(driver, player_name, retry_count=0):
    """
    Lấy giá chuyển nhượng từ footballtransfers.com
    
    Returns:
        str: Giá trị (ví dụ: "€100M") hoặc "N/a" nếu không tìm thấy
    """
    try:
        slug = name_to_slug(player_name)
        url = f"https://www.footballtransfers.com/en/players/{slug}"
        
        try:
            driver.get(url)
        except TimeoutException:
            # Nếu timeout, vẫn tiếp tục thử lấy dữ liệu
            pass
        
        # Đợi ngắn để Cloudflare verify (tối ưu tốc độ)
        time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
        
        html = driver.page_source
        soup = BeautifulSoup(html, 'html.parser')
        
        # Check if page exists
        title = soup.find('title')
        if title and ('404' in title.text or 'Not Found' in title.text):
            return "N/a"
        
        # Tìm giá trị chuyển nhượng
        # Method 1: Tìm trong div có class player-value
        value_elem = soup.find('div', class_=re.compile(r'player-value'))
        if value_elem:
            value_text = value_elem.text.strip()
            match = re.search(r'€[\d.]+[KMB]?', value_text)
            if match:
                return match.group(0)
        
        # Method 2: Tìm trong toàn bộ text
        all_text = soup.get_text()
        # Tìm pattern: €XX.XM hoặc €XXM
        matches = re.findall(r'€[\d.]+[KMB]', all_text)
        if matches:
            # Lấy giá trị đầu tiên (thường là market value)
            return matches[0]
        
        return "N/a"
        
    except TimeoutException:
        # Timeout thường xảy ra nhưng không sao, vẫn có thể lấy được data
        return "N/a"
        
    except WebDriverException as e:
        # Lỗi driver nghiêm trọng hơn, chỉ retry 1 lần
        if retry_count < 1:
            print(f"    ⟳ Lỗi driver, thử lại...")
            time.sleep(random.uniform(1.0, 2.0))
            return get_transfer_value(driver, player_name, retry_count + 1)
        return "N/a"
        
    except Exception as e:
        print(f"    ⚠ Lỗi: {str(e)[:50]}")
        return "N/a"


def get_players_from_db(db_path, table_name):
    """Lấy danh sách cầu thủ từ database"""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    cur.execute(f"SELECT player, squad, player_link FROM [{table_name}];")
    players = cur.fetchall()
    
    conn.close()
    return players

def save_transfer_value(conn, player, squad, player_link, value):
    """Lưu giá trị chuyển nhượng vào database (schema tối giản)"""
    cur = conn.cursor()
    cur.execute(f"""
        INSERT OR REPLACE INTO [{TARGET_TABLE}] 
        (player, squad, player_link, transfer_value)
        VALUES (?, ?, ?, ?);
    """, (player, squad, player_link, value))
    conn.commit()

def get_already_crawled_players(conn):
    """Lấy danh sách cầu thủ đã cào rồi"""
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT player, squad FROM [{TARGET_TABLE}];")
        crawled = set((player, squad) for player, squad in cur.fetchall())
        return crawled
    except:
        return set()

def main():
    print("=" * 70)
    print("🔄 Thu thập giá chuyển nhượng từ footballtransfers.com")
    print("=" * 70)
    
    # Lấy toàn bộ cầu thủ trong DB (không giới hạn)
    LIMIT_PLAYERS = None
    
    # Kết nối database nguồn (đọc danh sách cầu thủ)
    conn_src = sqlite3.connect(DB_PATH)
    
    # Tạo bảng nếu chưa có (không xóa dữ liệu cũ)
    # Kết nối database đích (ghi giá trị)
    conn_target = sqlite3.connect(TARGET_DB_PATH)
    cur = conn_target.cursor()
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS [{TARGET_TABLE}] (
            [player] TEXT,
            [squad] TEXT,
            [player_link] TEXT,
            [transfer_value] TEXT,
            PRIMARY KEY ([player], [squad])
        );
    """)
    conn_target.commit()
    print(f"✓ Đã chuẩn bị bảng: {TARGET_TABLE} (DB: {TARGET_DB_PATH})")
    
    # Lấy danh sách cầu thủ chưa cào
    all_players = get_players_from_db(DB_PATH, SOURCE_TABLE)
    already_crawled = get_already_crawled_players(conn_target)
    
    # Lọc ra những cầu thủ chưa cào
    players = [(p, s, l) for p, s, l in all_players if (p, s) not in already_crawled]
    
    # Giới hạn số lượng (nếu có), mặc định None = full
    players = players[:LIMIT_PLAYERS]
    
    total = len(players)
    total_all = len(all_players)
    already_done = len(already_crawled)
    
    print(f"📊 Tổng số cầu thủ trong DB: {total_all}")
    print(f"✓ Đã cào rồi: {already_done}")
    print(f"🎯 Sẽ cào trong lần này: {total} cầu thủ (full)")
    print()
    
    # Khởi tạo driver
    print("🌐 Khởi động browser...")
    # Browser sẽ minimize, không headless để tránh timeout
    driver = build_driver()
    
    try:
        start_time = time.time()
        success_count = 0
        failed_count = 0
        na_count = 0
        
        for idx, (player, squad, player_link) in enumerate(players, 1):
            # Giới hạn theo thời gian thực thi
            elapsed = time.time() - start_time
            if elapsed > RUN_MAX_SECONDS:
                print("\n⏰ Đã đạt giới hạn thời gian, dừng sớm để không vượt quá 20 phút.")
                break
            print(f"[{idx}/{total}] {player} ({squad})")
            
            # Lấy giá chuyển nhượng
            value = get_transfer_value(driver, player)
            
            # Lưu vào database đích
            save_transfer_value(conn_target, player, squad, player_link, value)
            
            # Thống kê
            if value == "N/a":
                na_count += 1
                print(f"  → N/a")
            else:
                success_count += 1
                print(f"  → {value} ✓")
            
            # Rate limiting - đợi giữa các request
            if idx < total:  # Không cần đợi ở cầu thủ cuối
                delay = random.uniform(MIN_DELAY, MAX_DELAY)
                time.sleep(delay)
            
            # Hiển thị progress mỗi 20 cầu thủ
            if idx % 20 == 0:
                print(f"\n📈 Tiến độ: {idx}/{total} ({idx*100//total}%)")
                print(f"   Có giá: {success_count} | N/a: {na_count}")
                remaining = max(total - idx, 0)
                est_left_min = int((remaining * 3.5) / 60)
                time_used_min = int((time.time() - start_time) / 60)
                print(f"   Đã chạy: ~{time_used_min} phút | Ước tính còn: ~{est_left_min} phút\n")
        
        print("\n" + "=" * 70)
        print("✅ HOÀN THÀNH!")
        print("=" * 70)
        print(f"📊 Tổng kết:")
        print(f"   - Tổng cầu thủ: {total}")
        print(f"   - Có giá: {success_count} ({success_count*100//total}%)")
        print(f"   - Không có giá (N/a): {na_count} ({na_count*100//total}%)")
        print(f"\n📁 Dữ liệu đã lưu vào:")
        print(f"   File: {TARGET_DB_PATH}")
        print(f"   Bảng: {TARGET_TABLE}")
        
    except KeyboardInterrupt:
        print("\n\n⚠ Đã dừng bởi người dùng")
        print(f"Đã xử lý: {idx}/{total} cầu thủ")
        
    finally:
        driver.quit()
        conn_src.close()
        conn_target.close()

if __name__ == "__main__":
    main()

