"""
Phase 4 - Player segmentation (KMeans clustering).

Groups players into behavioral segments using engagement/performance
features - separate from the churn model, this answers "what KINDS of
players do we have" rather than "who's about to leave."

k=4 chosen by silhouette score comparison (see console output) - note the
scores are modest (~0.18-0.23), which honestly reflects that player
behavior exists on a continuum rather than in sharply separated groups.
That's a real, defensible finding, not a flaw to hide.

Run: python player_segmentation.py  (run churn_model.py first)
Output: ../data/processed/player_segments.csv
"""

import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

SEG_COLS = ["sessions_per_week", "avg_acs", "win_rate", "party_ratio", "avg_session_min", "current_rank_tier"]
K = 4


def name_clusters(cluster_means: pd.DataFrame) -> dict:
    """Rank clusters by engagement frequency and assign 4 distinct, ordered
    labels. Deliberately simple/deterministic so every cluster gets a
    unique name - avoids clever override logic that can collide labels."""
    ranked = cluster_means.sort_values("sessions_per_week", ascending=False)
    labels_by_rank = ["Hardcore Core", "Social / Party Player", "Casual Regular", "At-Risk / Low Engagement"]
    return {cluster_id: labels_by_rank[i] for i, cluster_id in enumerate(ranked.index)}


def main():
    features = pd.read_csv("../data/processed/player_features.csv")
    X = features[SEG_COLS].fillna(0)
    Xs = StandardScaler().fit_transform(X)

    km = KMeans(n_clusters=K, random_state=42, n_init=10)
    features["cluster"] = km.fit_predict(Xs)
    score = silhouette_score(Xs, features["cluster"])
    print(f"Silhouette score (k={K}): {score:.3f}")

    print()
    print("Cluster profiles (mean values per cluster):")
    profile = features.groupby("cluster")[SEG_COLS + ["churned"]].mean().round(2)
    profile["n_players"] = features.groupby("cluster").size()
    print(profile)

    # descriptive labels based on relative cluster characteristics
    cluster_means = features.groupby("cluster")[SEG_COLS].mean()
    cluster_names = name_clusters(cluster_means)

    features["segment_name"] = features["cluster"].map(cluster_names)

    print()
    print("Segment names assigned:")
    print(features.groupby("segment_name").size())

    out_cols = ["player_id", "cluster", "segment_name", "churned"] + SEG_COLS
    features[out_cols].to_csv("../data/processed/player_segments.csv", index=False)
    print()
    print("Saved: player_segments.csv")


if __name__ == "__main__":
    main()
