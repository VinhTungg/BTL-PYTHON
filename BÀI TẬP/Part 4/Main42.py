#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pandas as pd
import matplotlib.pyplot as plt

K_DIAG_CSV = "kmeans_k_summary.csv"

def main():
    diag = pd.read_csv(K_DIAG_CSV)

    # Elbow
    plt.figure()
    plt.plot(diag["k"], diag["inertia"], marker="o")
    plt.xlabel("Số cụm K")
    plt.ylabel("Inertia")
    plt.title("Elbow Method (K-means)")
    plt.grid(True)

    # Silhouette
    plt.figure()
    plt.plot(diag["k"], diag["silhouette"], marker="o")
    plt.xlabel("Số cụm K")
    plt.ylabel("Silhouette score")
    plt.title("Silhouette vs K")
    plt.grid(True)

    plt.show()

if __name__ == "__main__":
    main()
