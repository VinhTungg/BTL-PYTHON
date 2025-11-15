#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sqlite3
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score

DB_PATH = "fbref_pl_2024_2025_full.sqlite"
TABLE   = "player_stats_cleaned"

OUT_CLUSTERS_CSV = Path("kmeans.csv")
K_DIAG_CSV       = Path("kmeans_k_summary.csv")
PCA_FEATURES_CSV = Path("kmeans_features.csv")  

K_MIN = 2
K_MAX = 8
def load_players() -> pd.DataFrame:
    with sqlite3.connect(DB_PATH) as con:
        df = pd.read_sql_query(f"SELECT * FROM {TABLE}", con)
    return df

def to_numeric_safe(s: pd.Series) -> pd.Series:
    s = s.astype(str).str.replace("€", "").str.replace(" ", "")
    s = s.str.replace(".", "").str.replace(",", ".")
    return pd.to_numeric(s, errors="coerce")

def build_feature_matrix(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    meta_cols = [c for c in ["player", "club", "position", "minutes"] if c in df.columns]
    meta = df[meta_cols].copy()

    base_feats = [
        "age",
        "minutes",
        "goals",
        "assists",
        "xg",
        "xg_assist",
        "npxg",
        "shots_on_target",
        "defense__tackles",
        "defense__interceptions",
        "passing__passes",
        "passing__passes_completed",
        "passing__progressive_passes",
        "possession__carries",
        "possession__progressive_carries",
    ]
    feat_cols = [c for c in base_feats if c in df.columns]

    X = pd.DataFrame(index=df.index)
    for c in feat_cols:
        X[c] = to_numeric_safe(df[c])

    # per90 cho mấy chỉ số tấn công
    if "minutes" in X.columns:
        m = X["minutes"].replace(0, np.nan)
        for col in ["goals", "assists", "xg", "xg_assist", "npxg"]:
            if col in X.columns:
                X[f"{col}_p90"] = (X[col] / m) * 90

    X = X.dropna(axis=1, how="all")
    X = X.apply(lambda col: col.fillna(col.median()))

    return meta, X

def choose_best_k(X_scaled: np.ndarray, k_min: int, k_max: int) -> int:
    rows = []
    for k in range(k_min, k_max + 1):
        km = KMeans(n_clusters=k, random_state=42, n_init="auto")
        labels = km.fit_predict(X_scaled)

        if 1 < len(set(labels)) < len(labels):
            sil = silhouette_score(X_scaled, labels)
        else:
            sil = np.nan

        inertia = float(km.inertia_)
        rows.append({"k": k, "silhouette": sil, "inertia": inertia})

    diag = pd.DataFrame(rows)
    diag[["silhouette", "inertia"]] = diag[["silhouette", "inertia"]].round(3)
    
    print(diag.round(3))

    diag.to_csv(K_DIAG_CSV, index=False)
    print(f"✔ Saved to {K_DIAG_CSV}")

    valid = diag.dropna(subset=["silhouette"])
    valid = diag.dropna(subset=["silhouette"])
    if valid.empty:
        best_k = int(diag.loc[diag["inertia"].idxmin(), "k"])
    else:
        max_sil = valid["silhouette"].max()

        candidates = valid[valid["silhouette"] >= max_sil - 0.03]
        best_row = candidates.loc[candidates["inertia"].idxmin()]
        best_k = int(best_row["k"])
        print(f"Chọn K tốt nhất theo silhouette: K = {best_k} (sil = {best_row['silhouette']:.3f})")

    return best_k
def main():
    df = load_players()
    print(f"Loaded {len(df)} players")

    meta, X = build_feature_matrix(df)
    print(f"Using {X.shape[1]} features for K-means")

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X.values)

    best_k = choose_best_k(X_scaled, K_MIN, K_MAX)

    kmeans = KMeans(n_clusters=best_k, random_state=42, n_init="auto")
    labels = kmeans.fit_predict(X_scaled)
 
    out = meta.copy()
    out["cluster"] = labels
    if "club" in out.columns:
        out = out.sort_values(["cluster", "club", "player"])
    else:
        out = out.sort_values(["cluster", "player"])
        
    out.to_csv(OUT_CLUSTERS_CSV, index=False, encoding="utf-8-sig", sep=";", decimal=",")
    print(f"✔ Saved clusters to {OUT_CLUSTERS_CSV} | (K = {best_k})")
    
    X_for_pca = X.drop(columns=["minutes"]) if "minutes" in X.columns else X
    
    pca_df = meta.join(X_for_pca)
    pca_df["cluster"] = labels
    
    num_cols = pca_df.select_dtypes(include=["number"]).columns
    pca_df[num_cols] = pca_df[num_cols].round(3)
    
    pca_df.to_csv("kmeans_features.csv", index=False, encoding="utf-8-sig", sep=";", decimal=",")
    print(f"✔ Saved PCA features to {PCA_FEATURES_CSV}")

if __name__ == "__main__":
    main()
