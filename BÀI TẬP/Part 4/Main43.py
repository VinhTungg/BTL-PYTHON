#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D 

PCA_FEATURES_CSV = "kmeans_features.csv"

def main():
    df = pd.read_csv(PCA_FEATURES_CSV, sep=';', decimal=',')

    # tách label cụm + meta
    meta_cols = [c for c in ["player", "club", "position", "minutes"] if c in df.columns]
    if "cluster" not in df.columns:
        raise SystemExit("File PCA không có cột 'cluster'. Hãy chạy lại file K-means trước.")

    labels = df["cluster"].astype(int).values

    # chọn feature columns = tất cả trừ meta + cluster
    drop_cols = meta_cols + ["cluster"]
    feat_cols = [c for c in df.columns if c not in drop_cols]

    X = df[feat_cols].copy()
    
    X = X.apply(lambda s: pd.to_numeric(s, errors="coerce")).fillna(0.0)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X.values)

    # PCA 2D
    from sklearn.decomposition import PCA
    pca2 = PCA(n_components=2, random_state=42)
    X_pca2 = pca2.fit_transform(X_scaled)

    plt.figure()
    plt.scatter(X_pca2[:, 0], X_pca2[:, 1], c=labels, s=10)
    plt.xlabel("PC1")
    plt.ylabel("PC2")
    plt.title("PCA 2D – player clusters")
    plt.grid(True)

    # PCA 3D
    pca3 = PCA(n_components=3, random_state=42)
    X_pca3 = pca3.fit_transform(X_scaled)

    fig = plt.figure()
    ax = fig.add_subplot(111, projection="3d")
    ax.scatter(X_pca3[:, 0], X_pca3[:, 1], X_pca3[:, 2], c=labels, s=10)
    ax.set_xlabel("PC1")
    ax.set_ylabel("PC2")
    ax.set_zlabel("PC3")
    ax.set_title("PCA 3D – player clusters")

    plt.show()
if __name__ == "__main__":
    main()
