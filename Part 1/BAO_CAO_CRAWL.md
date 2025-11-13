# Báo cáo thu thập dữ liệu Premier League 2024-2025

## 📋 Tổng quan

Dự án thu thập toàn bộ dữ liệu thống kê cầu thủ Premier League mùa giải 2024-2025 từ hai nguồn:
- **FBref**: Thống kê chi tiết về hiệu suất cầu thủ
- **FootballTransfers**: Giá trị chuyển nhượng ước tính

### Mục tiêu
1. ✅ Thu thập **TẤT CẢ** các cột thống kê từ FBref (không bỏ sót)
2. ✅ Lọc cầu thủ có số phút thi đấu > 90 phút
3. ✅ Thu thập giá trị chuyển nhượng từ FootballTransfers
4. ✅ Lưu trữ tập trung trong một database duy nhất
5. ✅ Code sạch, dễ bảo trì, hỗ trợ UTF-8 đầy đủ

---

## 🗄️ Cấu trúc Database

### Database: `fbref_pl_2024_2025_full.sqlite`

**Vị trí**: `Part 1/fbref_pl_2024_2025_full.sqlite`  
**Kích thước**: ~644 KB  

#### Bảng 1: `player_stats_cleaned`
- **Số records**: 502 cầu thủ
- **Số cột**: 268 cột
- **Điều kiện**: Cầu thủ có `minutes > 90`

**Cấu trúc cột**:
```
Core columns (6):
  - player, squad, age, birth_year, nation, position

Stats columns (262):
  - defense__*: ~20 cột (tackles, blocks, interceptions, clearances, etc.)
  - standard__*: ~20 cột (games, goals, assists, xG, cards, etc.)
  - passing__*: ~20 cột (passes completed, distance, xA, progressive, etc.)
  - passing_types__*: ~20 cột (through balls, corners, crosses, etc.)
  - possession__*: ~20 cột (touches, carries, take-ons, dribbles, etc.)
  - shooting__*: ~20 cột (shots, shots on target, xG, npxG, etc.)
  - gca__*: ~20 cột (goal creation actions, shot creation actions, etc.)
  - misc__*: ~20 cột (fouls, aerials, offsides, ball recoveries, etc.)
  - goalkeeping__*: ~20 cột (saves, save %, goals against, etc.)
  - goalkeeping_adv__*: ~20 cột (advanced GK metrics, distribution, etc.)
  - Plus nhiều cột phái sinh (per_90s, percentages, matches, minutes_90s, etc.)
```

#### Bảng 2: `player_transfer_values_2024_2025`
- **Số records**: 495 records (98.6% coverage)
- **Số cột**: 4 cột
- **Thành công**: 361 records có giá trị hợp lệ (72.9%)

**Schema**:
```
- player: TEXT (Tên cầu thủ)
- market_value: TEXT (Giá trị chuyển nhượng, format: €X.XM/K)
- club: TEXT (Câu lạc bộ hiện tại)
- last_update: TEXT (Ngày cập nhật giá trị)
```

---

## 🔧 Kiến trúc kỹ thuật

### 1. Script: `fbref_pl_2024_2025.py`

**Chức năng**: Thu thập toàn bộ stats từ FBref

**Công nghệ**:
- `undetected_chromedriver` v141: Bypass Cloudflare
- `BeautifulSoup` + `lxml`: Parse HTML
- `pandas`: Xử lý DataFrame
- `sqlite3`: Lưu trữ dữ liệu

**Luồng xử lý**:
```
1. Khởi tạo Chrome driver (headless=False, timeouts=90s)
2. Duyệt 10 trang stats:
   - standard, shooting, passing, passing_types
   - gca, defense, possession, misc
   - goalkeeping, goalkeeping_adv
3. Mỗi trang:
   - Wait for container (WebDriverWait 25s)
   - Extract table từ HTML (kể cả trong HTML comments)
   - Parse thành dict với prefix page_tag__
4. Merge tất cả stats theo key (player, squad)
5. Filter players với minutes > 90
6. Sắp xếp cột: core columns trước, stats columns sau (sorted)
7. Ghi SQLite với column ordering cố định
```

**Xử lý đặc biệt**:
- FBref giấu bảng trong HTML comments → Extract cả comments
- Metadata columns từ `standard` được rename: `standard__age` → `age`
- Giữ **TẤT CẢ** các cột, không filter/dedup
- UTF-8 encoding: `sys.stdout.reconfigure(encoding="utf-8")`

### 2. Script: `collect_transfer_values.py`

**Chức năng**: Thu thập giá trị chuyển nhượng từ FootballTransfers

**Công nghệ**:
- `requests` + `BeautifulSoup`: HTTP requests và parse HTML
- `unidecode`: Chuẩn hóa tên cầu thủ thành slug
- `sqlite3`: Lưu trữ

**Luồng xử lý**:
```
1. Load danh sách 502 cầu thủ từ player_stats_cleaned
2. Với mỗi cầu thủ:
   a) Tạo slug từ tên: "Mohamed Salah" → "mohamed-salah"
   b) Thử các URL variants:
      - /en/players/mohamed-salah
      - /en/players/mohamed-salah-1
      - /en/players/mohamed-salah-2
      - /en/players/mohamed-salah-3
   c) Parse giá trị từ HTML:
      - Selector: .player-value .player-tag hoặc .playerInfo-value
      - Club: .playerInfoTop-bar__club hoặc __team
      - Last update: text chứa "Last update"
   d) Fallback: Search nếu không tìm thấy
3. Ghi vào DB (INSERT)
4. Log aliases vào alias_detected.txt
```

**Xử lý lỗi**:
- Timeout: Retry 1 lần với timeout 20s
- HTTP error: Log và return N/a
- Missing value: Return "N/a"
- UTF-8 encoding cho Vietnamese/special characters

---

## 📊 Kết quả thu thập

### FBref Stats
```
✅ Tổng cầu thủ: 502 records
✅ Tổng cột: 268 columns (TẤT CẢ các cột từ 10 trang stats)
✅ Dữ liệu: 100% hoàn chỉnh
✅ Điều kiện: minutes > 90
```

**Breakdown theo trang**:
- Standard: 574 dòng → 502 sau filter
- Shooting: 574 dòng
- Passing: 574 dòng
- Passing types: 574 dòng
- GCA: 574 dòng
- Defense: 574 dòng
- Possession: 574 dòng
- Misc: 574 dòng
- Goalkeeping: 44 dòng (only GKs)
- Goalkeeping adv: 44 dòng (only GKs)

### FootballTransfers Market Values
```
✅ Đã scrape: 495/502 records (98.6%)
✅ Thành công: 361 records (72.9%)
❌ Không tìm thấy: 134 records (27.1% return "N/a")
⚠️ Chưa scrape: 7 records (1.4%)
```

**Phân tích "N/a"**:
- Cầu thủ mới/trẻ không có profile
- Tên khác biệt giữa FBref và FootballTransfers
- Slug không khớp (ký tự đặc biệt, thứ tự tên)
- Profile 404 hoặc không có market value

**Ví dụ thành công**:
- Youri Tielemans: €40.9M
- Yves Bissouma: €18.5M
- Yukinari Sugawara: €4.1M
- Álex Moreno: €2.1M
- Łukasz Fabiański: €0.8M

---

## 🛠️ Cải tiến kỹ thuật

### UTF-8 Encoding
**Vấn đề**: Windows console mặc định dùng `cp1252`, không hỗ trợ emoji và Unicode đặc biệt

**Giải pháp**:
```python
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")
```

### Clean Code
- ✅ Loại bỏ comments dài dòng
- ✅ Loại bỏ docstrings không cần thiết
- ✅ Loại bỏ section headers (`# ===...===`)
- ✅ Consistent formatting và spacing
- ✅ Code tự giải thích, dễ đọc

### Column Management
**Trước**: Filter 100 cột hữu ích qua `curate_keep_columns()`  
**Sau**: Giữ **TẤT CẢ 268 cột**, không filter

```python
# Code cũ (filtered):
keep_cols = curate_keep_columns(df.columns)
ordered = [c for c in base_heads if c in df.columns] + [c for c in keep_cols if c not in base_heads]

# Code mới (keep all):
ordered = [c for c in base_heads if c in df.columns] + [c for c in sorted(df.columns) if c not in base_heads]
```

---

## 🚧 Khó khăn và giải pháp

### Khó khăn 1: FBref Cloudflare/Anti-bot
**Vấn đề**: 
- Trang load chậm, thỉnh thoảng bị block
- Bảng stats giấu trong HTML comments

**Giải pháp**:
- Dùng `undetected_chromedriver` v141
- Set timeouts cao: `page_load_timeout=90s`, `script_timeout=90s`
- Parse cả HTML comments để extract tables
- Wait for elements với `WebDriverWait(25s)`

### Khó khăn 2: FootballTransfers Slug mismatch
**Vấn đề**: 
- "Manuel Akanji" → slug "manuel-akanji" nhưng thực tế là "manuel-obafemi-akanji"
- Special characters không map chuẩn

**Giải pháp**:
- Thử 4 URL variants: base, -1, -2, -3
- Fallback search page
- Log aliases vào file để track mapping
- Accept 27% N/a rate (reasonable cho web scraping)

### Khó khăn 3: Windows Console Encoding
**Vấn đề**: 
- Unicode characters crash script: `UnicodeEncodeError`
- Emoji không hiển thị được

**Giải pháp**:
- Force UTF-8 với `sys.stdout.reconfigure()`
- Apply cho cả `stdout` và `stderr`

---

## 📝 Hướng dẫn sử dụng

### Chạy scraper FBref
```bash
cd "Part 1"
python fbref_pl_2024_2025.py
```

**Thời gian**: ~5-10 phút  
**Output**: `fbref_pl_2024_2025_full.sqlite` với bảng `player_stats_cleaned`

### Chạy scraper FootballTransfers
```bash
cd "Part 1"
python collect_transfer_values.py
```

**Thời gian**: ~15-20 phút (502 players × ~2s/request)  
**Output**: Thêm bảng `player_transfer_values_2024_2025` vào cùng DB

### Kiểm tra dữ liệu
```python
import sqlite3

conn = sqlite3.connect('fbref_pl_2024_2025_full.sqlite')

# Kiểm tra stats
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM player_stats_cleaned')
print(f"Stats: {cur.fetchone()[0]} players")

cur.execute('PRAGMA table_info(player_stats_cleaned)')
print(f"Columns: {len(cur.fetchall())} columns")

# Kiểm tra transfer values
cur.execute('SELECT COUNT(*) FROM player_transfer_values_2024_2025')
print(f"Transfer values: {cur.fetchone()[0]} records")

cur.execute('SELECT COUNT(*) FROM player_transfer_values_2024_2025 WHERE market_value != "N/a"')
print(f"Valid values: {cur.fetchone()[0]} records")

conn.close()
```

### Query mẫu
```sql
-- Top 10 cầu thủ có giá trị cao nhất
SELECT 
    p.player,
    p.squad,
    p.age,
    p.position,
    t.market_value,
    p.standard__goals,
    p.standard__assists,
    p.standard__xg
FROM player_stats_cleaned p
LEFT JOIN player_transfer_values_2024_2025 t 
    ON p.player = t.player
WHERE t.market_value != 'N/a'
ORDER BY CAST(REPLACE(REPLACE(t.market_value, '€', ''), 'M', '') AS FLOAT) DESC
LIMIT 10;

-- Stats trung bình theo vị trí
SELECT 
    position,
    COUNT(*) as total_players,
    ROUND(AVG(CAST(standard__goals AS FLOAT)), 2) as avg_goals,
    ROUND(AVG(CAST(standard__assists AS FLOAT)), 2) as avg_assists,
    ROUND(AVG(CAST(standard__minutes AS FLOAT)), 0) as avg_minutes
FROM player_stats_cleaned
WHERE position != 'N/a'
GROUP BY position
ORDER BY total_players DESC;
```