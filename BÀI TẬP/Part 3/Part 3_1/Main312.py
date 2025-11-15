#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import numpy as np
import pandas as pd
from pathlib import Path

SUMMARY_CSV = Path("./team_metric_summary.csv")
LEADERS_CSV = Path("./metric_leaders.csv")
FORMIDX_CSV = Path("./team_form_index.csv")
ROUND_DIGITS = 3

NEGATIVE_METRICS = [
    "cards_yellow",
    "cards_red",
    "misc__fouls",
    "misc__cards_yellow",
    "misc__cards_red",
]

def main():
    df = pd.read_csv(SUMMARY_CSV, sep=';', decimal=',')

    if "Club" not in df.columns:
        raise ValueError("File summary phải có cột 'Club'.")
    df = df.set_index("Club")

    for c in df.columns:
        if c.endswith("_mean"):
            df[c] = pd.to_numeric(df[c], errors="coerce")

    mean_cols = [c for c in df.columns if c.endswith("_mean")]
    rows = []
    for col in sorted(mean_cols):
        s = df[col]
        if s.notna().any():
            top_team = s.idxmax()
            top_val = float(s.loc[top_team])
            rows.append({
                "metric": col[:-5],
                "top_team": top_team,
                "value": round(top_val, ROUND_DIGITS),
            })

    leaders = pd.DataFrame(rows)
    leaders.to_csv(LEADERS_CSV, index=False, sep=';', decimal=',')

    Z = (df[mean_cols] - df[mean_cols].mean()) / df[mean_cols].std(ddof=0).replace(0, np.nan)

    for m in NEGATIVE_METRICS:
        col = f"{m}_mean"
        if col in Z.columns:
            Z[col] = -Z[col]

    fi = Z.mean(axis=1, skipna=True).to_frame("form_index")
    fi = fi.sort_values("form_index", ascending=False).round(ROUND_DIGITS)
    fi.to_csv(FORMIDX_CSV, sep=';', decimal=',')

if __name__ == "__main__":
    main()
