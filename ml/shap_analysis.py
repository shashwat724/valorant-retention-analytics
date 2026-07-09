"""
Phase 4 - SHAP explainability.

Loads the trained XGBoost churn model and explains WHY it predicts churn -
not just a bare probability. This is what separates a real analytics
project from a black-box model: a stakeholder can be told "player X is
flagged because their session frequency dropped and their win rate fell",
not just "the model said 78%."

Run: python shap_analysis.py  (run churn_model.py first)
Outputs:
  - ../data/processed/shap_feature_importance.csv
  - outputs/shap_summary_bar.png
  - outputs/shap_summary_beeswarm.png
"""

import joblib
import numpy as np
import pandas as pd
import shap
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

FEATURE_COLS = [
    "total_sessions", "total_matches", "days_since_last_session", "avg_gap_days",
    "sessions_per_week", "party_ratio", "avg_session_min", "win_rate", "avg_acs",
    "avg_kast", "avg_hs_pct", "avg_rr_change", "recent_rr_trend",
    "current_rank_tier", "account_tenure_days",
]


def main():
    model = joblib.load("../data/processed/churn_model.joblib")
    features = pd.read_csv("../data/processed/player_features.csv")
    X = features[FEATURE_COLS]

    explainer = shap.TreeExplainer(model)
    shap_values = explainer(X)

    # global feature importance (mean absolute SHAP value)
    mean_abs_shap = np.abs(shap_values.values).mean(axis=0)
    importance = pd.DataFrame({
        "feature": FEATURE_COLS,
        "mean_abs_shap": mean_abs_shap,
    }).sort_values("mean_abs_shap", ascending=False)
    importance.to_csv("../data/processed/shap_feature_importance.csv", index=False)

    print("=" * 60)
    print("TOP CHURN DRIVERS (by mean |SHAP value|)")
    print("=" * 60)
    for _, row in importance.head(8).iterrows():
        print(f"  {row['feature']:<25s} {row['mean_abs_shap']:.4f}")

    # summary bar plot
    import os
    os.makedirs("outputs", exist_ok=True)
    plt.figure(figsize=(8, 6))
    shap.summary_plot(shap_values, X, plot_type="bar", show=False)
    plt.tight_layout()
    plt.savefig("outputs/shap_summary_bar.png", dpi=150)
    plt.close()

    # beeswarm (shows direction of effect, not just magnitude)
    plt.figure(figsize=(8, 6))
    shap.summary_plot(shap_values, X, show=False)
    plt.tight_layout()
    plt.savefig("outputs/shap_summary_beeswarm.png", dpi=150)
    plt.close()

    print()
    print("Saved: shap_feature_importance.csv, shap_summary_bar.png, shap_summary_beeswarm.png")


if __name__ == "__main__":
    main()
