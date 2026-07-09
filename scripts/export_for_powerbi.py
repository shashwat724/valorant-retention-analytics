"""
Phase 5 - Exports a clean star schema for Power BI.

Power BI has no native SQLite connector, so the reliable path for a
beginner is: export clean CSVs -> import into Power BI -> build
relationships there. This script builds a proper star schema (fact +
dimension tables) rather than dumping raw tables 1:1, and folds in the
Phase 4 ML outputs (churn probability, segment) directly onto the
player dimension so they're immediately usable on any visual.

Run: python export_for_powerbi.py
Output: ../powerbi/data/*.csv (10 files)
"""

import sqlite3
import pandas as pd
from datetime import datetime, timedelta

DB_PATH = "../data/processed/valorant_analytics.db"
OUT_DIR = "../powerbi/data"


def main():
    conn = sqlite3.connect(DB_PATH)

    # ---------------- Dimension: Players (merged with Phase 4 ML outputs) ----------------
    players = pd.read_sql("SELECT * FROM players", conn)
    current_rank = pd.read_sql("SELECT player_id, rank_name AS current_rank_name, rank_tier_order AS current_rank_tier_order FROM v_player_current_rank", conn)
    churn_pred = pd.read_csv("../data/processed/churn_predictions.csv")
    segments = pd.read_csv("../data/processed/player_segments.csv")[["player_id", "segment_name"]]

    dim_players = (
        players
        .merge(current_rank, on="player_id", how="left")
        .merge(churn_pred[["player_id", "churned", "churn_probability", "predicted_churn"]], on="player_id", how="left")
        .merge(segments, on="player_id", how="left")
    )
    # "NA" (North America) is read as a null/blank value by many CSV import
    # tools (pandas, and often Power BI's default Power Query settings) -
    # map region codes to full names to avoid silent data loss on import.
    region_names = {
        "NA": "North America", "EU": "Europe", "APAC": "Asia-Pacific",
        "KR": "Korea", "LATAM": "Latin America", "BR": "Brazil",
    }
    dim_players["region"] = dim_players["region"].map(region_names)
    dim_players.to_csv(f"{OUT_DIR}/Dim_Players.csv", index=False)

    # ---------------- Dimension: Agents / Maps / Ranks ----------------
    agents = pd.read_sql("SELECT * FROM agents", conn)
    agents.to_csv(f"{OUT_DIR}/Dim_Agents.csv", index=False)

    maps = pd.read_sql("SELECT * FROM maps", conn)
    maps.to_csv(f"{OUT_DIR}/Dim_Maps.csv", index=False)

    ranks = pd.read_sql("SELECT * FROM ranks", conn)
    ranks.to_csv(f"{OUT_DIR}/Dim_Ranks.csv", index=False)

    # ---------------- Dimension: Patches (with readable agent names) ----------------
    patches = pd.read_sql("SELECT * FROM patches", conn)
    agent_lookup = agents.set_index("agent_id")["agent_name"]
    patches["buffed_agent_name"] = patches["buffed_agent_id"].map(agent_lookup)
    patches["nerfed_agent_name"] = patches["nerfed_agent_id"].map(agent_lookup)
    patches.to_csv(f"{OUT_DIR}/Dim_Patches.csv", index=False)

    # ---------------- Dimension: Date (for Power BI time intelligence) ----------------
    all_dates = pd.date_range("2026-03-01", "2026-06-30", freq="D")
    dim_date = pd.DataFrame({"Date": all_dates})
    dim_date["Year"] = dim_date.Date.dt.year
    dim_date["MonthNum"] = dim_date.Date.dt.month
    dim_date["MonthName"] = dim_date.Date.dt.strftime("%b")
    dim_date["Week"] = dim_date.Date.dt.isocalendar().week
    dim_date["DayOfWeek"] = dim_date.Date.dt.strftime("%A")
    dim_date["IsWeekend"] = dim_date.Date.dt.dayofweek >= 5
    dim_date["Date"] = dim_date["Date"].dt.date.astype(str)
    dim_date.to_csv(f"{OUT_DIR}/Dim_Date.csv", index=False)

    # ---------------- Fact: Matches ----------------
    matches = pd.read_sql("SELECT * FROM matches", conn)
    matches.to_csv(f"{OUT_DIR}/Fact_Matches.csv", index=False)

    # ---------------- Fact: Rounds ----------------
    rounds = pd.read_sql("SELECT * FROM rounds", conn)
    rounds.to_csv(f"{OUT_DIR}/Fact_Rounds.csv", index=False)

    # ---------------- Fact: Sessions ----------------
    sessions = pd.read_sql("SELECT * FROM player_sessions", conn)
    sessions.to_csv(f"{OUT_DIR}/Fact_Sessions.csv", index=False)

    # ---------------- Precomputed: Patch Impact (from the SQL view) ----------------
    patch_impact = pd.read_sql("SELECT * FROM v_patch_impact", conn)
    patch_impact.to_csv(f"{OUT_DIR}/Precomputed_PatchImpact.csv", index=False)

    # ---------------- Precomputed: Party size -> return rate (business Q8) ----------------
    party_retention = pd.read_sql("SELECT * FROM v_party_retention", conn)
    party_retention.to_csv(f"{OUT_DIR}/Precomputed_PartyRetention.csv", index=False)

    # ---------------- Precomputed: Queue frequency by rank (business Q6) ----------------
    queue_freq = pd.read_sql("SELECT * FROM v_queue_frequency_by_rank", conn)
    queue_freq.to_csv(f"{OUT_DIR}/Precomputed_QueueFrequencyByRank.csv", index=False)

    # ---------------- Precomputed: SHAP feature importance ----------------
    shap_imp = pd.read_csv("../data/processed/shap_feature_importance.csv")
    shap_imp.to_csv(f"{OUT_DIR}/Precomputed_SHAP_Importance.csv", index=False)

    conn.close()

    print("Exported to powerbi/data/:")
    for f in ["Dim_Players", "Dim_Agents", "Dim_Maps", "Dim_Ranks", "Dim_Patches", "Dim_Date",
              "Fact_Matches", "Fact_Rounds", "Fact_Sessions",
              "Precomputed_PatchImpact", "Precomputed_PartyRetention",
              "Precomputed_QueueFrequencyByRank", "Precomputed_SHAP_Importance"]:
        df = pd.read_csv(f"{OUT_DIR}/{f}.csv")
        print(f"  {f}.csv  -> {len(df)} rows, {len(df.columns)} cols")


if __name__ == "__main__":
    main()
