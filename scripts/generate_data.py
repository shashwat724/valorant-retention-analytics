"""
Phase 2 - Synthetic data generator for VALORANT Player Retention & Meta Analytics Platform.

Generates statistically realistic ranked-play data on top of REAL reference data
(actual agent roster, roles, maps, rank ladder). See docs/01_ARCHITECTURE.md section 5
for why this project uses generated data instead of a live API pull.

Underlying simulation logic (documented so every number is explainable):
- Each player has a latent skill (drives win probability + performance stats)
- Each player has a latent engagement level + decay rate (drives session frequency,
  which naturally produces churn - not hardcoded, it falls out of the simulation)
- Rank is tracked as a continuous rating (Elo-style) and mapped to the real tier ladder
- Round-level economy follows a simple state machine (loss -> next round more likely eco/force)

Run: python generate_data.py
Output: CSVs written to ../data/raw/
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta

RNG = np.random.default_rng(42)

N_PLAYERS = 300
WINDOW_DAYS = 120
WINDOW_END = datetime(2026, 6, 30)
WINDOW_START = WINDOW_END - timedelta(days=WINDOW_DAYS)
CHURN_GAP_DAYS = 14  # no session in final N days of window = churned

OUT_DIR = "../data/raw"

# ---------------------------------------------------------------------------
# Reference data (real game data)
# ---------------------------------------------------------------------------

AGENTS = [
    ("Jett", "Duelist"), ("Reyna", "Duelist"), ("Raze", "Duelist"),
    ("Phoenix", "Duelist"), ("Yoru", "Duelist"), ("Neon", "Duelist"), ("Iso", "Duelist"),
    ("Brimstone", "Controller"), ("Viper", "Controller"), ("Omen", "Controller"),
    ("Astra", "Controller"), ("Harbor", "Controller"), ("Clove", "Controller"),
    ("Sova", "Initiator"), ("Breach", "Initiator"), ("Skye", "Initiator"),
    ("KAY/O", "Initiator"), ("Fade", "Initiator"), ("Gekko", "Initiator"),
    ("Killjoy", "Sentinel"), ("Cypher", "Sentinel"), ("Sage", "Sentinel"),
    ("Chamber", "Sentinel"), ("Deadlock", "Sentinel"),
]

MAPS = [
    ("Ascent", 2), ("Bind", 2), ("Haven", 3), ("Split", 2), ("Icebox", 2),
    ("Breeze", 2), ("Fracture", 2), ("Pearl", 2), ("Lotus", 3), ("Sunset", 2),
]

RANK_NAMES = [f"{tier} {n}" for tier in
              ["Iron", "Bronze", "Silver", "Gold", "Platinum", "Diamond", "Ascendant", "Immortal"]
              for n in (1, 2, 3)] + ["Radiant"]
# 25 ranks total, elo breakpoints every 100 points
ELO_PER_RANK = 100

REGIONS = ["NA", "EU", "APAC", "KR", "LATAM", "BR"]
REGION_WEIGHTS = [0.30, 0.25, 0.20, 0.10, 0.10, 0.05]

BUY_TYPES = ["Full Buy", "Half Buy", "Eco", "Force Buy"]


def elo_to_rank_id(elo: float) -> int:
    idx = int(np.clip(elo // ELO_PER_RANK, 0, len(RANK_NAMES) - 1))
    return idx + 1  # rank_id is 1-indexed


def build_reference_tables():
    agents_df = pd.DataFrame(
        [(i + 1, name, role) for i, (name, role) in enumerate(AGENTS)],
        columns=["agent_id", "agent_name", "role"],
    )
    maps_df = pd.DataFrame(
        [(i + 1, name, sites) for i, (name, sites) in enumerate(MAPS)],
        columns=["map_id", "map_name", "site_count"],
    )
    ranks_df = pd.DataFrame(
        [(i + 1, name, i + 1) for i, name in enumerate(RANK_NAMES)],
        columns=["rank_id", "rank_name", "rank_tier_order"],
    )
    return agents_df, maps_df, ranks_df


# ---------------------------------------------------------------------------
# Patches (simulated balance timeline - drives the "agent change -> engagement"
# product analytics question). Spaced ~24 days apart across the window.
# ---------------------------------------------------------------------------

PATCH_EFFECT_STRENGTH = 1.7   # pick-rate multiplier for buffed agent
PATCH_NERF_STRENGTH = 0.5     # pick-rate multiplier for nerfed agent
PATCH_PERF_DELTA = 0.09       # perf/win_prob shift applied to buffed/nerfed agent


def build_patches(agents_df: pd.DataFrame):
    n_patches = 5
    spacing = WINDOW_DAYS // (n_patches + 1)
    rows = []
    agent_ids = agents_df["agent_id"].tolist()
    for i in range(n_patches):
        patch_date = WINDOW_START + timedelta(days=spacing * (i + 1))
        buffed, nerfed = RNG.choice(agent_ids, size=2, replace=False)
        buffed_name = agents_df.loc[agents_df.agent_id == buffed, "agent_name"].iloc[0]
        nerfed_name = agents_df.loc[agents_df.agent_id == nerfed, "agent_name"].iloc[0]
        rows.append({
            "patch_id": i + 1,
            "patch_version": f"9.{i+1:02d}",
            "patch_date": patch_date.date().isoformat(),
            "buffed_agent_id": int(buffed),
            "nerfed_agent_id": int(nerfed),
            "patch_notes": f"{buffed_name} buffed (ability cooldown/damage improved); "
                            f"{nerfed_name} nerfed (ability cost/damage reduced). [simulated]",
        })
    return pd.DataFrame(rows)


def active_patch_for_date(patches_df: pd.DataFrame, d):
    eligible = patches_df[patches_df["patch_date"] <= d.date().isoformat()]
    if eligible.empty:
        return None
    return eligible.sort_values("patch_date").iloc[-1]


# ---------------------------------------------------------------------------
# Players (latent skill + engagement archetype)
# ---------------------------------------------------------------------------

def build_players():
    rows = []
    skills = RNG.beta(2, 2, size=N_PLAYERS)  # 0..1, centered
    engagement_base = RNG.gamma(shape=2.2, scale=1.6, size=N_PLAYERS)  # sessions/week baseline
    decay_rate = RNG.exponential(scale=0.55, size=N_PLAYERS)  # higher = churns faster
    tenure_days = RNG.integers(30, 900, size=N_PLAYERS)  # account age before window start

    for i in range(N_PLAYERS):
        starting_elo = 300 + skills[i] * 1900 + RNG.normal(0, 120)
        starting_elo = float(np.clip(starting_elo, 0, 2499))
        account_created = WINDOW_START - timedelta(days=int(tenure_days[i]))
        rows.append({
            "player_id": i + 1,
            "player_name": f"Player_{i+1:04d}",
            "account_created": account_created.date().isoformat(),
            "starting_rank_id": elo_to_rank_id(starting_elo),
            "region": RNG.choice(REGIONS, p=REGION_WEIGHTS),
            "_skill": skills[i],
            "_elo": starting_elo,
            "_engagement_base": engagement_base[i],
            "_decay_rate": decay_rate[i],
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Sessions + Matches + Rounds
# ---------------------------------------------------------------------------

def generate():
    agents_df, maps_df, ranks_df = build_reference_tables()
    players_df = build_players()
    patches_df = build_patches(agents_df)

    agent_ids = agents_df["agent_id"].to_numpy()
    agent_role = dict(zip(agents_df.agent_id, agents_df.role))
    map_ids = maps_df["map_id"].to_numpy()

    session_rows, match_rows, round_rows = [], [], []
    session_id, match_id, round_id = 1, 1, 1

    PARTY_SIZES = [1, 2, 3, 4, 5]
    PARTY_WEIGHTS = [0.55, 0.20, 0.10, 0.08, 0.07]
    PARTY_RETENTION_BOOST = 1.30  # next-week session multiplier if last week had a party session

    for _, p in players_df.iterrows():
        elo = p["_elo"]
        skill = p["_skill"]
        base_rate = p["_engagement_base"]
        decay = p["_decay_rate"]
        had_party_last_week = False

        n_weeks = WINDOW_DAYS // 7
        for week in range(n_weeks):
            week_start = WINDOW_START + timedelta(days=week * 7)
            expected_sessions = base_rate * np.exp(-decay * week / n_weeks)
            if had_party_last_week:
                expected_sessions *= PARTY_RETENTION_BOOST
            n_sessions_this_week = int(RNG.poisson(max(expected_sessions, 0.01)))
            n_sessions_this_week = min(n_sessions_this_week, 6)
            had_party_this_week = False

            for _ in range(n_sessions_this_week):
                day_offset = int(RNG.integers(0, 7))
                session_date = week_start + timedelta(days=day_offset)
                if session_date > WINDOW_END:
                    continue

                start_hour = int(np.clip(RNG.normal(19, 3.5), 6, 23))
                duration_min = int(np.clip(RNG.lognormal(mean=4.0, sigma=0.5), 15, 300))
                n_matches = max(1, int(round(duration_min / 32)))
                party_size = int(RNG.choice(PARTY_SIZES, p=PARTY_WEIGHTS))
                if party_size > 1:
                    had_party_this_week = True

                session_rows.append({
                    "session_id": session_id,
                    "player_id": p["player_id"],
                    "session_date": session_date.date().isoformat(),
                    "session_start": f"{start_hour:02d}:00:00",
                    "session_duration_min": duration_min,
                    "matches_played": n_matches,
                    "party_size": party_size,
                })

                active_patch = active_patch_for_date(patches_df, session_date)
                patch_id = int(active_patch["patch_id"]) if active_patch is not None else None
                buffed_agent = int(active_patch["buffed_agent_id"]) if active_patch is not None else None
                nerfed_agent = int(active_patch["nerfed_agent_id"]) if active_patch is not None else None

                for _m in range(n_matches):
                    opponent_skill = float(np.clip(skill + RNG.normal(0, 0.12), 0, 1))
                    win_prob = 1 / (1 + np.exp(-6 * (skill - opponent_skill)))

                    map_id = int(RNG.choice(map_ids))
                    role_bias = RNG.random()
                    if role_bias < 0.45:
                        candidate_roles = ["Duelist"]
                    elif role_bias < 0.70:
                        candidate_roles = ["Initiator"]
                    elif role_bias < 0.88:
                        candidate_roles = ["Controller"]
                    else:
                        candidate_roles = ["Sentinel"]
                    pool = [a for a in agent_ids if agent_role[a] in candidate_roles]

                    # patch-driven pick-rate weighting
                    weights = np.ones(len(pool))
                    for idx, a in enumerate(pool):
                        if a == buffed_agent:
                            weights[idx] *= PATCH_EFFECT_STRENGTH
                        elif a == nerfed_agent:
                            weights[idx] *= PATCH_NERF_STRENGTH
                    weights = weights / weights.sum()
                    agent_id = int(RNG.choice(pool, p=weights))

                    # patch-driven performance/win-prob shift for the picked agent
                    if agent_id == buffed_agent:
                        win_prob = float(np.clip(win_prob + PATCH_PERF_DELTA, 0.02, 0.98))
                    elif agent_id == nerfed_agent:
                        win_prob = float(np.clip(win_prob - PATCH_PERF_DELTA, 0.02, 0.98))

                    result = RNG.choice(["Win", "Loss"], p=[win_prob, 1 - win_prob])
                    rr_change = int(RNG.integers(16, 26)) if result == "Win" else -int(RNG.integers(16, 26))
                    elo = float(np.clip(elo + rr_change, 0, 2499))
                    rank_id_now = elo_to_rank_id(elo)

                    rounds_won = int(RNG.integers(13, 14)) if result == "Win" else int(RNG.integers(3, 12))
                    rounds_lost = int(RNG.integers(3, 12)) if result == "Win" else 13
                    total_rounds = rounds_won + rounds_lost

                    perf = float(np.clip(skill + RNG.normal(0, 0.15), 0.05, 1.0))
                    if agent_id == buffed_agent:
                        perf = float(np.clip(perf + PATCH_PERF_DELTA, 0.05, 1.0))
                    elif agent_id == nerfed_agent:
                        perf = float(np.clip(perf - PATCH_PERF_DELTA, 0.05, 1.0))

                    kills = int(np.clip(RNG.normal(14 + perf * 10, 4), 2, 35))
                    deaths = int(np.clip(RNG.normal(16 - perf * 5, 4), 3, 25))
                    assists = int(np.clip(RNG.normal(5 + perf * 3, 2), 0, 15))
                    acs = round(float(np.clip(RNG.normal(150 + perf * 130, 35), 40, 420)), 1)
                    adr = round(float(np.clip(RNG.normal(110 + perf * 90, 25), 30, 300)), 1)
                    hs_pct = round(float(np.clip(RNG.normal(20 + perf * 15, 6), 5, 55)), 1)
                    first_bloods = int(np.clip(RNG.poisson(1 + perf * 2), 0, 8))
                    kast = round(float(np.clip(RNG.normal(65 + perf * 15, 10), 30, 95)), 1)

                    match_rows.append({
                        "match_id": match_id,
                        "session_id": session_id,
                        "player_id": p["player_id"],
                        "map_id": map_id,
                        "agent_id": agent_id,
                        "rank_id": rank_id_now,
                        "patch_id": patch_id,
                        "match_date": session_date.date().isoformat(),
                        "match_result": result,
                        "rounds_won": rounds_won,
                        "rounds_lost": rounds_lost,
                        "kills": kills,
                        "deaths": deaths,
                        "assists": assists,
                        "acs": acs,
                        "adr": adr,
                        "headshot_pct": hs_pct,
                        "first_bloods": first_bloods,
                        "kast_pct": kast,
                        "rr_change": rr_change,
                    })

                    prev_lost = False
                    for rnum in range(1, total_rounds + 1):
                        side = "Attack" if (rnum <= total_rounds // 2) else "Defense"
                        if rnum == 1:
                            buy = "Eco"
                        elif prev_lost and RNG.random() < 0.5:
                            buy = RNG.choice(["Eco", "Force Buy"], p=[0.55, 0.45])
                        else:
                            buy = RNG.choice(["Full Buy", "Half Buy"], p=[0.75, 0.25])

                        loadout_value = {
                            "Full Buy": RNG.integers(3800, 4900),
                            "Half Buy": RNG.integers(2200, 3800),
                            "Eco": RNG.integers(400, 1500),
                            "Force Buy": RNG.integers(1500, 2600),
                        }[buy]

                        buy_strength = {"Full Buy": 0.62, "Half Buy": 0.5, "Force Buy": 0.42, "Eco": 0.22}[buy]
                        round_win_prob = float(np.clip(win_prob * buy_strength * 1.6, 0.05, 0.9))
                        round_result = RNG.choice(["Won", "Lost"], p=[round_win_prob, 1 - round_win_prob])
                        prev_lost = (round_result == "Lost")

                        win_condition = None
                        if round_result == "Won":
                            win_condition = RNG.choice(
                                ["Elimination", "Spike Detonation", "Spike Defused", "Time Expired"],
                                p=[0.55, 0.25, 0.15, 0.05],
                            )

                        round_rows.append({
                            "round_id": round_id,
                            "match_id": match_id,
                            "round_number": rnum,
                            "side": side,
                            "buy_type": buy,
                            "loadout_value": int(loadout_value),
                            "round_result": round_result,
                            "win_condition": win_condition,
                        })
                        round_id += 1

                    match_id += 1
                session_id += 1
            had_party_last_week = had_party_this_week

    players_out = players_df[["player_id", "player_name", "account_created", "starting_rank_id", "region"]].copy()

    return (
        players_out,
        pd.DataFrame(session_rows),
        pd.DataFrame(match_rows),
        pd.DataFrame(round_rows),
        agents_df, maps_df, ranks_df, patches_df,
    )


if __name__ == "__main__":
    import os
    os.makedirs(OUT_DIR, exist_ok=True)

    players, sessions, matches, rounds, agents_df, maps_df, ranks_df, patches_df = generate()

    players.to_csv(f"{OUT_DIR}/players.csv", index=False)
    sessions.to_csv(f"{OUT_DIR}/player_sessions.csv", index=False)
    matches.to_csv(f"{OUT_DIR}/matches.csv", index=False)
    rounds.to_csv(f"{OUT_DIR}/rounds.csv", index=False)
    agents_df.to_csv(f"{OUT_DIR}/agents.csv", index=False)
    maps_df.to_csv(f"{OUT_DIR}/maps.csv", index=False)
    ranks_df.to_csv(f"{OUT_DIR}/ranks.csv", index=False)
    patches_df.to_csv(f"{OUT_DIR}/patches.csv", index=False)

    print(f"players:  {len(players)}")
    print(f"sessions: {len(sessions)}")
    print(f"matches:  {len(matches)}")
    print(f"rounds:   {len(rounds)}")
    print(f"patches:  {len(patches_df)}")
