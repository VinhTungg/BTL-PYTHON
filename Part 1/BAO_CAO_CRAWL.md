## Báo cáo cào dữ liệu FBref và FootballTransfers (2024-2025)

### Mục tiêu
- Thu thập đầy đủ thống kê cầu thủ Premier League 2024-2025 từ FBref (players > 90 phút).
- Thu thập giá chuyển nhượng (market value) của từng cầu thủ từ FootballTransfers.
- Lưu dữ liệu bền vững vào SQLite, cấu trúc rõ ràng, không trùng cột, có khả năng kiểm tra/khôi phục.

## Kiến trúc và luồng xử lý

### 1) Cào FBref: `fbref_pl_2024_2025.py`
- Khởi tạo trình duyệt: undetected_chromedriver (tránh Cloudflare), timeouts mở rộng.
- Duyệt lần lượt các trang thống kê: standard, shooting, passing, passing_types, gca, defense, possession, misc, goalkeeping, goalkeeping_adv.
- Tách bảng từ HTML comment (FBref thường nhúng bảng trong comment), sau đó parse HTML → map về dict.
- Gộp dữ liệu nhiều trang theo khóa (`player`, `squad`, `player_link`) thông qua `merge_stats` với quy tắc chống trùng cột:
  - Giữ mọi cột từ `standard`.
  - Giữ mọi cột từ `goalkeeping`.
  - Với `goalkeeping_adv`: bỏ `gk_goals_against`, `gk_pens_allowed` (đã có trong `goalkeeping`).
  - Với các trang khác: bỏ các cột “chung” đã tồn tại ở `standard` (vd tuổi, phút, rank...).
- Lọc cầu thủ có `minutes > 90`.
- Ghi SQLite: `fbref_pl_2024_2025.sqlite` bảng `player_stats_over_90min`.

### 2) Cào FootballTransfers: `collect_transfer_values.py`
- Khởi tạo trình duyệt tối ưu tốc độ: pageLoadStrategy=`eager`, tắt ảnh, bỏ implicit wait.
- Sinh URL từ tên cầu thủ (slug hóa) → mở trang profile.
- Delay ngắn 0.5s giữa các request để giảm bị chặn.
- Trích giá trị:
  - Ưu tiên tìm trong khối có class chứa `player-value`.
  - Fallback regex toàn trang `€[\d.]+[KMB]`.
  - Nếu không tìm thấy → `N/a`.
- Ghi SQLite riêng: `player_transfer_values.sqlite` bảng `player_transfer_values` (schema tối giản: `player, squad, player_link, transfer_value`).

## Khó khăn thường gặp và nguyên nhân

### FBref
- Cloudflare/Chống bot: tải trang chậm, thỉnh thoảng treo.
- Bảng trong HTML comment: cần tách ra rồi mới parse.
- Trùng cột giữa các trang thống kê (vd `age`, `minutes_90s`, `ranker` xuất hiện ở nhiều bảng; GK vs GK_Adv trùng chỉ số).
- Tiêu đề cột không đồng nhất giữa trang (cùng ý nghĩa, tên khác nhau).

### FootballTransfers
- Không phải mọi cầu thủ đều có profile → 404 hoặc trang chung không chứa value.
- Slug tên không khớp profile thực tế (ký tự đặc biệt, thứ tự tên, biệt danh).
- Giá trị render bởi JS, đôi khi xuất hiện trễ.
- Có rate limit/Cloudflare → cần delay và tối ưu tải trang.

## Giải pháp đã áp dụng

### Kỹ thuật trình duyệt/hiệu năng
- undetected_chromedriver để vượt chống bot cơ bản.
- `page_load_strategy = eager`, tắt ảnh (`--blink-settings=imagesEnabled=false`) để giảm thời gian tải.
- Bỏ implicit wait (dùng delay chủ động) nhằm rút ngắn thời gian.
- Delay 0.5s giữa các request để giảm nguy cơ bị chặn.

### Parse & hợp nhất dữ liệu FBref
- Hàm tách bảng từ comment + parse header/body linh hoạt.
- Quy tắc chống trùng cột ngay trong `merge_stats`:
  - `standard`: giữ tất cả các cột nền tảng.
  - `goalkeeping_adv`: bỏ 2 cột trùng với `goalkeeping`.
  - Trang khác: bỏ các cột “chung” đã có ở `standard` (age, minutes, rank,...).
- Kiểm chứng bằng script `full_duplicate_check.py` (xác nhận 0 cột trùng sau khi ghi DB).

### Lưu trữ dữ liệu
- FBref: `fbref_pl_2024_2025.sqlite`/`player_stats_over_90min`.
- FootballTransfers: tách DB riêng `player_transfer_values.sqlite`/`player_transfer_values` để cô lập schema và đơn giản hóa vận hành.
- Khóa chính cho bảng giá trị: `(player, squad)` (idempotent cập nhật bằng INSERT OR REPLACE).

## Kết quả thực tế lần chạy gần nhất
- FBref: 502 cầu thủ (> 90 phút) ghi vào `player_stats_over_90min` (DB: `fbref_pl_2024_2025.sqlite`), không trùng cột.
- FootballTransfers: 502 bản ghi; 264 có giá; 238 `N/a` (khả năng cao do 404/slug lệch/JS render trễ).

## Phương án cải tiến/định hướng tới

### FootballTransfers – tăng tỷ lệ có giá trị
- Fallback qua trang search của site để tìm đúng profile trước khi parse.
- Danh sách “slug đặc biệt” đã được xác thực, cache lại để lần sau dùng thẳng đúng URL.
- Chiến lược retry thông minh cho những bản ghi `N/a`:
  - Wave 1: chờ 0.5s (nhanh),
  - Wave 2: tăng chờ lên 1.0–1.5s cho phần còn `N/a`,
  - Wave 3: fallback search.

### Hiệu năng & ổn định
- Chạy song song 2–3 driver (chia danh sách cầu thủ), sau đó gộp kết quả để tăng tốc 2–3x.
- Thêm proxy xoay vòng và User-Agent rotation nếu cần.
- Ghi log lỗi riêng (bản ghi nào 404/JS trễ) để tái xử lý mục tiêu.
- Thêm chế độ resume: bỏ qua cầu thủ đã có trong DB, tiếp tục phần còn lại.

### Chất lượng dữ liệu
- Chuẩn hóa đơn vị tiền tệ (mọi giá trị quy về €), parse cả định dạng có/không hậu tố K/M/B.
- Bổ sung kiểm tra sanity (giá trị âm/zero/chuỗi bất thường → gắn `N/a` hoặc re-try).

## Hướng dẫn vận hành nhanh

### Chạy cào FBref
```bash
python fbref_pl_2024_2025.py
```

### Kiểm tra cột trùng trong DB FBref
```bash
python full_duplicate_check.py
```

### Chạy cào FootballTransfers (ghi vào DB riêng)
```bash
python collect_transfer_values.py
```

### Truy vấn tiến độ (SQL mẫu)
```sql
-- Tổng cầu thủ nguồn
SELECT COUNT(*) FROM player_stats_over_90min;

-- Tổng đã ghi giá trị
SELECT COUNT(*) FROM player_transfer_values;

-- Số bản ghi có giá trị thực
SELECT COUNT(*) FROM player_transfer_values 
WHERE transfer_value IS NOT NULL AND transfer_value <> 'N/a';
```

---


