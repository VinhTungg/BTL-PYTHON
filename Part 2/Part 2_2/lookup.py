# -*- coding: utf-8 -*-
"""
Tra cứu dữ liệu cầu thủ qua FastAPI bằng requests.

Cú pháp:
  python lookup.py --name "Bukayo Saka"
  python lookup.py --club "Arsenal"

Tuỳ chọn:
  --base-url  URL server FastAPI (mặc định http://127.0.0.1:8000)
  --limit     Giới hạn số dòng cho truy vấn theo tên (mặc định 1000)
  --max-cols  Số cột tối đa in ra màn hình (CSV luôn ghi full cột)
"""

import argparse
import csv
import sys
import requests
from typing import List, Dict
from urllib.parse import quote

DEFAULT_BASE_URL = "http://127.0.0.1:8000"

# ---------- tiện ích ----------
import re
import unicodedata

def slugify(s: str) -> str:
    s = (s or "").strip()
    # xử lý riêng đ/Đ
    s = s.replace("đ", "d").replace("Đ", "D")
    # bóc dấu Unicode về ASCII
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii")
    # thành dạng file-safe
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "output"


def choose_columns(rows: List[Dict], max_cols: int) -> List[str]:
    """Chọn cột để in ra terminal (ưu tiên cột quan trọng; CSV vẫn full)."""
    if not rows:
        return []
    keys = list(rows[0].keys())
    priority = ["player", "squad", "age", "birth_year", "nation", "position",
                "standard__minutes", "minutes", "standard__games", "standard__goals",
                "standard__assists", "shooting__shots_on_target", "defense__tackles"]
    cols = [c for c in priority if c in keys]
    for k in keys:
        if k not in cols:
            cols.append(k)
    return cols[:max_cols]

def print_table(rows: List[Dict], max_cols: int = 12) -> None:
    if not rows:
        print("Không có dữ liệu.")
        return
    cols = choose_columns(rows, max_cols)
    # độ rộng cột
    widths = {c: max(len(str(c)), *(len(str(r.get(c, ""))) for r in rows)) for c in cols}
    widths = {c: min(w, 30) for c, w in widths.items()}  # cắt bớt cho gọn terminal

    # header
    line = " | ".join(f"{c[:widths[c]].ljust(widths[c])}" for c in cols)
    print(line)
    print("-" * len(line))

    # rows
    for r in rows:
        cells = []
        for c in cols:
            val = "" if r.get(c) is None else str(r.get(c))
            if len(val) > widths[c]:
                val = val[: widths[c] - 1] + "…"
            cells.append(val.ljust(widths[c]))
        print(" | ".join(cells))

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

# ---------- gọi API ----------
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
    parser.add_argument("--club", type=str, help="Tên câu lạc bộ (khớp chính xác mặc định).")
    parser.add_argument("--base-url", type=str, default=DEFAULT_BASE_URL, help="URL FastAPI (mặc định http://127.0.0.1:8000)")
    parser.add_argument("--limit", type=int, default=1000, help="Giới hạn khi tìm theo tên (mặc định 1000).")
    parser.add_argument("--max-cols", type=int, default=12, help="Số cột tối đa in ra màn hình (CSV luôn ghi full).")
    args = parser.parse_args()

    if bool(args.name) == bool(args.club):
        parser.error("Chọn đúng 1 trong 2 tham số: --name hoặc --club")

    try:
        if args.name:
            rows = query_by_name(args.base_url, args.name, args.limit)
            print_table(rows, max_cols=args.max_cols)
            fname = f"{slugify(args.name)}.csv"
            write_csv(rows, fname)
            print(f"\nCSV đã lưu: {fname}")
        else:
            rows = query_by_club(args.base_url, args.club)
            print_table(rows, max_cols=args.max_cols)
            fname = f"{slugify(args.club)}.csv"
            write_csv(rows, fname)
            print(f"\nCSV đã lưu: {fname}")
    except requests.ConnectionError:
        print("Không kết nối được API. Hãy chắc server đang chạy: uvicorn app.main:app --reload")
        sys.exit(1)

if __name__ == "__main__":
    main()
