"""
  python lookup.py --name "Bukayo Saka"
  python lookup.py --club "Arsenal"
"""
import argparse
import csv
import json
import sys
import requests
from typing import List, Dict
from urllib.parse import quote

# Thiết lập UTF-8 encoding cho Windows console
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

DEFAULT_BASE_URL = "http://127.0.0.1:8000"

import re
import unicodedata

def slugify(s: str) -> str:
    s = (s or "").strip()
    # xử lý riêng đ/Đ
    s = s.replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "output"


def print_json(rows: List[Dict]) -> None:
    """In kết quả dạng pretty JSON"""
    if not rows:
        print("Không có dữ liệu.")
        return
    
    # Pretty print JSON với indent
    print(json.dumps(rows, indent=2, ensure_ascii=False))

def write_csv(rows: List[Dict], filename: str) -> str:
    if not rows:
        return filename
    all_cols = []
    for r in rows:
        for k in r.keys():
            if k not in all_cols:
                all_cols.append(k)
    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=all_cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return filename

# gọi API
def query_by_name(base_url: str, name: str, limit: int) -> List[Dict]:
    url = f"{base_url.rstrip('/')}/players"
    params = {"name": name, "limit": limit, "offset": 0}
    r = requests.get(url, params=params, timeout=30)
    if r.status_code != 200:
        try:
            detail = r.json().get("detail")
        except Exception:
            detail = r.text
        raise SystemExit(f"API lỗi {r.status_code}: {detail}")
    return r.json()

def query_by_club(base_url: str, club: str) -> List[Dict]:
    # endpoint path param -> cần encode
    url = f"{base_url.rstrip('/')}/players/by-club/{quote(club, safe='')}"
    params = {"exact": "true"}  # mặc định khớp chính xác
    r = requests.get(url, params=params, timeout=30)
    if r.status_code != 200:
        try:
            detail = r.json().get("detail")
        except Exception:
            detail = r.text
        raise SystemExit(f"API lỗi {r.status_code}: {detail}")
    return r.json()

# ---------- main ----------
def main():
    parser = argparse.ArgumentParser(description="Tra cứu dữ liệu cầu thủ qua FastAPI.")
    parser.add_argument("--name", type=str, help="Tên cầu thủ (LIKE).")
    parser.add_argument("--club", type=str, help="Tên câu lạc bộ.")
    parser.add_argument("--base-url", type=str, default=DEFAULT_BASE_URL, help="URL FastAPI (mặc định http://127.0.0.1:8000)")
    parser.add_argument("--limit", type=int, default=1000, help="Giới hạn khi tìm theo tên (mặc định 1000).")
    args = parser.parse_args()

    if bool(args.name) == bool(args.club):
        parser.error("Chọn đúng 1 trong 2 tham số: --name hoặc --club")

    try:
        if args.name:
            rows = query_by_name(args.base_url, args.name, args.limit)
            print_json(rows)
            fname = f"{slugify(args.name)}.csv"
            write_csv(rows, fname)
            print(f"\nCSV đã lưu: {fname}")
        else:
            rows = query_by_club(args.base_url, args.club)
            print_json(rows)
            fname = f"{slugify(args.club)}.csv"
            write_csv(rows, fname)
            print(f"\nCSV đã lưu: {fname}")
    except requests.ConnectionError:
        print("Không kết nối được API. Hãy chắc server đang chạy: uvicorn app.main:app --reload")
        sys.exit(1)

if __name__ == "__main__":
    main()
