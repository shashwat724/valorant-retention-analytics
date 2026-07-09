"""
Phase 4 - Churn prediction model.

CRITICAL DESIGN DECISION - avoiding data leakage:
The churn label is "no session in the final 14 days of the observation window"
(WINDOW_END - CHURN_GAP_DAYS). If features were computed using the player's
FULL session history (including those last 14 days), a feature like "days
since last session" would essentially encode the label directly - the model
would look artificially perfect while having learned nothing real.

Fix: every feature is computed using ONLY data on or before CUTOFF_DATE
(= WINDOW_END - 14 days). The label describes what happens strictly AFTER
that cutoff. This mirrors how a real churn model would be deployed - predict
forward from what you know today, not from data you won't have until later.

Run: python churn_model.py
Outputs:
  - ../data/processed/player_features.csv   (feature table, for Power BI too)
  - ../data/processed/churn_predictions.csv (predictions + probabilities)
  - prints model evaluation metrics
"""

import sqlite3
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    roc_auc_score, accuracy_score, precision_score, recall_score,
    f1_score, confusion_matrix, classification_report
)
from xgboost import XGBClassifier

DB_PATH = "../data/processed/valorant_analytics.db"
WINDOW_END = datetime(2026, 6, 30)
CHURN_GAP_DAYS = 14
CUTOFF = WINDOW_END - timedelta(days=CHURN_GAP_DAYS)

RANDOM_STATE = 42


def build_features():
    conn = sqlite3.connect(DB_PATH)
    sessions = pd.read_sql("SELECT * FROM player_sessions", conn, parse_dates=["session_date"])
    matches = pd.read_sql("SELECT * FROM matches", conn, parse_dates=["match_date"])
    players = pd.read_sql("SELECT * FROM players", conn, parse_dates=["account_created"])
    retention = pd.read_sql("SELECT player_id, churned FROM v_player_retention_features", conn)
    ranks = pd.read_sql("SELECT rank_id, rank_tier_order FROM ranks", conn)
    conn.close()

    sess_pre = sessions[sessions.session_date <= CUTOFF].copy()
    match_pre = matches[matches.match_date <= CUTOFF].copy()
    match_pre = match_pre.merge(ranks, on="rank_id", how="left")

    rows = []
    for _, p in players.iterrows():
        pid = p["player_id"]
        s = sess_pre[sess_pre.player_id == pid].sort_values("session_date")
        m = match_pre[match_pre.player_id == pid].sort_values("match_date")

        total_sessions = len(s)
        total_matches = len(m)

        if total_sessions > 0:
            last_session = s.session_date.max()
            days_since_last_session = (CUTOFF - last_session).days
            gaps = s.session_date.diff().dt.days.dropna()
            avg_gap_days = gaps.mean() if len(gaps) > 0 else days_since_last_session
            party_ratio = (s.party_size > 1).mean()
            avg_session_min = s.session_duration_min.mean()
            span_days = max((s.session_date.max() - s.session_date.min()).days, 1)
            sessions_per_week = total_sessions / (span_days / 7.0)
        else:
            days_since_last_session = (CUTOFF - p["account_created"]).days
            avg_gap_days = days_since_last_session
            party_ratio = 0.0
            avg_session_min = 0.0
            sessions_per_week = 0.0

        if total_matches > 0:
            win_rate = (m.match_result == "Win").mean()
            avg_acs = m.acs.mean()
            avg_kast = m.kast_pct.mean()
            avg_hs_pct = m.headshot_pct.mean()
            avg_rr_change = m.rr_change.mean()
            current_rank_tier = m.sort_values("match_date").rank_tier_order.iloc[-1]
            # recent form: RR trend over last 10 matches vs. all-time avg
            recent = m.sort_values("match_date").tail(10)
            recent_rr_trend = recent.rr_change.mean() - avg_rr_change
        else:
            win_rate = 0.0
            avg_acs = 0.0
            avg_kast = 0.0
            avg_hs_pct = 0.0
            avg_rr_change = 0.0
            current_rank_tier = p["starting_rank_id"]
            recent_rr_trend = 0.0

        account_tenure_days = (CUTOFF - p["account_created"]).days

        rows.append({
            "player_id": pid,
            "total_sessions": total_sessions,
            "total_matches": total_matches,
            "days_since_last_session": days_since_last_session,
            "avg_gap_days": round(avg_gap_days, 2),
            "sessions_per_week": round(sessions_per_week, 2),
            "party_ratio": round(party_ratio, 3),
            "avg_session_min": round(avg_session_min, 1),
            "win_rate": round(win_rate, 3),
            "avg_acs": round(avg_acs, 1),
            "avg_kast": round(avg_kast, 1),
            "avg_hs_pct": round(avg_hs_pct, 1),
            "avg_rr_change": round(avg_rr_change, 2),
            "recent_rr_trend": round(recent_rr_trend, 2),
            "current_rank_tier": current_rank_tier,
            "account_tenure_days": account_tenure_days,
        })

    features = pd.DataFrame(rows)
    features = features.merge(retention, on="player_id", how="left")
    return features


FEATURE_COLS = [
    "total_sessions", "total_matches", "days_since_last_session", "avg_gap_days",
    "sessions_per_week", "party_ratio", "avg_session_min", "win_rate", "avg_acs",
    "avg_kast", "avg_hs_pct", "avg_rr_change", "recent_rr_trend",
    "current_rank_tier", "account_tenure_days",
]


def train_and_evaluate(features: pd.DataFrame):
    X = features[FEATURE_COLS]
    y = features["churned"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=RANDOM_STATE
    )

    # --- Baseline: Logistic Regression (scaled features) ---
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    logreg = LogisticRegression(max_iter=1000, class_weight="balanced", random_state=RANDOM_STATE)
    logreg.fit(X_train_scaled, y_train)
    logreg_pred = logreg.predict(X_test_scaled)
    logreg_proba = logreg.predict_proba(X_test_scaled)[:, 1]

    # --- Main model: XGBoost ---
    n_pos = y_train.sum()
    n_neg = len(y_train) - n_pos
    scale_pos_weight = n_neg / n_pos

    xgb = XGBClassifier(
        n_estimators=150, max_depth=3, learning_rate=0.08,
        scale_pos_weight=scale_pos_weight, eval_metric="logloss",
        random_state=RANDOM_STATE,
    )
    xgb.fit(X_train, y_train)
    xgb_pred = xgb.predict(X_test)
    xgb_proba = xgb.predict_proba(X_test)[:, 1]

    # --- 5-fold cross-validated AUC (more reliable given small N=300) ---
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    cv_auc_scores = cross_val_score(
        XGBClassifier(n_estimators=150, max_depth=3, learning_rate=0.08,
                       scale_pos_weight=scale_pos_weight, eval_metric="logloss",
                       random_state=RANDOM_STATE),
        X, y, cv=skf, scoring="roc_auc"
    )

    print("=" * 60)
    print("BASELINE: Logistic Regression")
    print("=" * 60)
    print(classification_report(y_test, logreg_pred, target_names=["Active", "Churned"]))
    print(f"ROC-AUC (test set): {roc_auc_score(y_test, logreg_proba):.3f}")

    print()
    print("=" * 60)
    print("MAIN MODEL: XGBoost")
    print("=" * 60)
    print(classification_report(y_test, xgb_pred, target_names=["Active", "Churned"]))
    print(f"ROC-AUC (test set):        {roc_auc_score(y_test, xgb_proba):.3f}")
    print(f"ROC-AUC (5-fold CV mean):  {cv_auc_scores.mean():.3f}  (+/- {cv_auc_scores.std():.3f})")
    print(f"Confusion matrix (test set, rows=actual, cols=predicted):")
    print(confusion_matrix(y_test, xgb_pred))

    return xgb, X, y, X_train, X_test, y_train, y_test


if __name__ == "__main__":
    features = build_features()
    features.to_csv("../data/processed/player_features.csv", index=False)
    print(f"Feature table built: {features.shape[0]} players, {len(FEATURE_COLS)} features")
    print(f"Churn rate: {features.churned.mean()*100:.1f}%")
    print()

    model, X, y, X_train, X_test, y_train, y_test = train_and_evaluate(features)

    # save predictions for the full dataset (for Power BI / SHAP script)
    all_proba = model.predict_proba(X)[:, 1]
    all_pred = model.predict(X)
    out = features[["player_id", "churned"]].copy()
    out["churn_probability"] = np.round(all_proba, 4)
    out["predicted_churn"] = all_pred
    out.to_csv("../data/processed/churn_predictions.csv", index=False)
    print()
    print("Saved: player_features.csv, churn_predictions.csv")

    import joblib
    joblib.dump(model, "../data/processed/churn_model.joblib")
    print("Saved: churn_model.joblib (for shap_analysis.py)")
