"""
Phase 2 - Loads generated CSVs (data/raw/) into the normalized SQLite database
defined in sql/01_schema.sql. Also computes account_created-based churn label
used later in Phase 4 (ML).

Run: python load_to_sqlite.py
Output: data/processed/valorant_analytics.db
"""

import sqlite3
import pandas as pd
import os

RAW_DIR = "../data/raw"
DB_PATH = "../data/processed/valorant_analytics.db"
SCHEMA_PATH = "../sql/01_schema.sql"


def main():
    os.makedirs("../data/processed", exist_ok=True)
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())

    tables = {
        "agents": "agents.csv",
        "maps": "maps.csv",
        "ranks": "ranks.csv",
        "patches": "patches.csv",
        "players": "players.csv",
        "player_sessions": "player_sessions.csv",
        "matches": "matches.csv",
        "rounds": "rounds.csv",
    }

    # NOTE: "NA" is a real Valorant region code (North America) but pandas'
    # default NA-detection reads the literal string "NA" as a missing value.
    # players.csv (region column) needs keep_default_na disabled to avoid that.
    for table, csv_file in tables.items():
        if table == "players":
            df = pd.read_csv(f"{RAW_DIR}/{csv_file}", keep_default_na=False, na_values=[])
        else:
            df = pd.read_csv(f"{RAW_DIR}/{csv_file}")
        df.to_sql(table, conn, if_exists="append", index=False)
        print(f"loaded {table}: {len(df)} rows")

    conn.commit()

    # sanity check: foreign keys valid
    conn.execute("PRAGMA foreign_key_check")
    issues = conn.execute("PRAGMA foreign_key_check").fetchall()
    print(f"foreign key violations: {len(issues)}")

    conn.close()


if __name__ == "__main__":
    main()
