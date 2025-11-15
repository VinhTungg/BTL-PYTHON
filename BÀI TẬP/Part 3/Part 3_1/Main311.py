#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
import numpy as np
import pandas as pd
from typing import List, Optional

# Cấu hình database và export
DB_PATH = "../fbref_pl_2024_2025_full.sqlite"
TABLE = "player_stats_cleaned"
OUT_CSV = "team_metric_summary.csv"

TEAM_COL = "club"
PLAYER_COL = "player"
MINUTES_COL = "minutes"

CSV_SEP = ';'
CSV_DECIMAL = ','
ROUND_DIGITS = 2

# Các giá trị được coi là missing data
NA_STRINGS = {"", "-", "—", "_", "N/A", "N/a", "NA", "na", "n/a", "None", "null", "NULL"}

def to_numeric_safe(s: pd.Series) -> pd.Series:
    """Chuyển đổi cột sang số, xử lý các giá trị missing và dấu phẩy thập phân"""
    if s.dtype == object:
        s = s.replace(list(NA_STRINGS), np.nan)
        s = s.apply(lambda x: str(x).replace(',', '.') if isinstance(x, str) else x)
    return pd.to_numeric(s, errors="coerce")

def detect_cols(df: pd.DataFrame,
                team_col: Optional[str], player_col: Optional[str], minutes_col: Optional[str]):
    """Tự động detect tên cột nếu chưa được chỉ định"""
    if team_col is None:
        if "team" in df.columns:
            team_col = "team"
        elif "club" in df.columns:
            team_col = "club"
        elif "squad" in df.columns:
            team_col = "squad"
    if player_col is None:
        player_col = "player" if "player" in df.columns else None
    if minutes_col is None:
        cands = [c for c in df.columns if "minutes" in c.lower() and "90" not in c.lower()]
        minutes_col = cands[0] if cands else None
    return team_col, player_col, minutes_col

def coerce_numeric(df: pd.DataFrame, exclude: List[str]) -> List[str]:
    numeric_cols = []
    for c in df.columns:
        if c in exclude:
            continue
        df[c] = to_numeric_safe(df[c])
        if df[c].notna().any():
            numeric_cols.append(c)
    return numeric_cols

def minutes_weighted_stats(g: pd.DataFrame, cols: List[str], minutes_col: Optional[str]) -> pd.Series:
    out = {}
    w = None
    if minutes_col and minutes_col in g.columns:
        w = to_numeric_safe(g[minutes_col]).clip(lower=0).replace([np.inf, -np.inf], np.nan).fillna(0.0)
        total = w.sum()
        w = None if (total == 0 or np.isnan(total)) else (w / total)

    for c in cols:
        s = to_numeric_safe(g[c]).astype(float)

        if w is not None:
            mean_val = float(np.nansum(s.values * w.values))
        else:
            mean_val = float(np.nanmean(s.values))

        median_val = float(np.nanmedian(s.values))
        std_val    = float(np.nanstd(s.values, ddof=0))
        
        out[f"{c}_median"] = median_val
        out[f"{c}_mean"]   = mean_val
        out[f"{c}_std"]    = std_val

    return pd.Series(out)

def main():

    # Kết nối database và đọc dữ liệu
    with sqlite3.connect(DB_PATH) as con:
        df = pd.read_sql_query(f"SELECT * FROM {TABLE}", con)

    # Detect và chuẩn hóa tên cột
    team_col, player_col, minutes_col = detect_cols(df, TEAM_COL, PLAYER_COL, MINUTES_COL)
    if team_col is None or player_col is None:
        raise SystemExit(f"Không tìm thấy cột team/player. Columns: {list(df.columns)}")

    rename = {}
    if team_col != "club":
        rename[team_col] = "club"
    if player_col != "player":
        rename[player_col] = "player"
    if minutes_col and minutes_col != "minutes":
        rename[minutes_col] = "minutes"
    if rename:
        df = df.rename(columns=rename)
        if minutes_col:
            minutes_col = "minutes"

    # Chuyển đổi cột số
    exclude = {"club","player","position","nation","squad","id"}
    numeric_cols = coerce_numeric(df, list(exclude))
    if "minutes" in numeric_cols:
        numeric_cols.remove("minutes")

    # Tính toán thống kê theo đội
    cols_for_apply = numeric_cols + (["minutes"] if "minutes" in df.columns else [])

    summary = (
        df.groupby("club", dropna=True)[cols_for_apply]
          .apply(lambda g: minutes_weighted_stats(g, numeric_cols, "minutes" if "minutes" in g.columns else None))
          .reset_index()
          .rename(columns={"club": "Club"})
          .set_index("Club")
          .sort_index()
          .round(ROUND_DIGITS)
    )

    # Xuất file CSV
    summary.to_csv(OUT_CSV, index=True, sep=CSV_SEP, decimal=CSV_DECIMAL)
    print(f"✔ Xuất file {OUT_CSV} | {summary.shape[0]} đội × {summary.shape[1]} cột")

if __name__ == "__main__":
    main()