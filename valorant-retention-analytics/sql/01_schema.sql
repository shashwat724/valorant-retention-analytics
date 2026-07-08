-- =====================================================================
-- VALORANT Player Retention & Meta Analytics Platform
-- Database Schema (SQLite)
-- =====================================================================

PRAGMA foreign_keys = ON;

-- -----------------------------------------------------------
-- Reference table: Agents
-- -----------------------------------------------------------
CREATE TABLE agents (
    agent_id        INTEGER PRIMARY KEY,
    agent_name      TEXT NOT NULL UNIQUE,
    role            TEXT NOT NULL CHECK (role IN ('Duelist','Controller','Initiator','Sentinel'))
);

-- -----------------------------------------------------------
-- Reference table: Maps
-- -----------------------------------------------------------
CREATE TABLE maps (
    map_id          INTEGER PRIMARY KEY,
    map_name        TEXT NOT NULL UNIQUE,
    site_count      INTEGER NOT NULL
);

-- -----------------------------------------------------------
-- Reference table: Ranks (tier ladder, ordered)
-- -----------------------------------------------------------
CREATE TABLE ranks (
    rank_id         INTEGER PRIMARY KEY,
    rank_name       TEXT NOT NULL UNIQUE,
    rank_tier_order INTEGER NOT NULL  -- 1 = Iron 1 ... 27 = Radiant
);

-- -----------------------------------------------------------
-- Players
-- -----------------------------------------------------------
CREATE TABLE players (
    player_id       INTEGER PRIMARY KEY,
    player_name     TEXT NOT NULL,
    account_created  DATE NOT NULL,
    starting_rank_id INTEGER NOT NULL REFERENCES ranks(rank_id),
    region          TEXT NOT NULL CHECK (region IN ('NA','EU','APAC','KR','LATAM','BR'))
);

-- -----------------------------------------------------------
-- Player Sessions (a play session = one or more matches back-to-back)
-- -----------------------------------------------------------
CREATE TABLE player_sessions (
    session_id      INTEGER PRIMARY KEY,
    player_id       INTEGER NOT NULL REFERENCES players(player_id),
    session_date    DATE NOT NULL,
    session_start   TIME NOT NULL,
    session_duration_min INTEGER NOT NULL,
    matches_played  INTEGER NOT NULL
);

-- -----------------------------------------------------------
-- Matches
-- -----------------------------------------------------------
CREATE TABLE matches (
    match_id        INTEGER PRIMARY KEY,
    session_id      INTEGER NOT NULL REFERENCES player_sessions(session_id),
    player_id       INTEGER NOT NULL REFERENCES players(player_id),
    map_id          INTEGER NOT NULL REFERENCES maps(map_id),
    agent_id        INTEGER NOT NULL REFERENCES agents(agent_id),
    rank_id          INTEGER NOT NULL REFERENCES ranks(rank_id),   -- rank at time of match
    match_date      DATE NOT NULL,
    match_result    TEXT NOT NULL CHECK (match_result IN ('Win','Loss','Draw')),
    rounds_won      INTEGER NOT NULL,
    rounds_lost     INTEGER NOT NULL,
    kills           INTEGER NOT NULL,
    deaths          INTEGER NOT NULL,
    assists         INTEGER NOT NULL,
    acs             REAL NOT NULL,      -- Average Combat Score
    adr             REAL NOT NULL,      -- Average Damage per Round
    headshot_pct    REAL NOT NULL,
    first_bloods    INTEGER NOT NULL,
    kast_pct        REAL NOT NULL,      -- Kill/Assist/Survive/Trade %
    rr_change       INTEGER NOT NULL    -- Rank Rating change, can be negative
);

-- -----------------------------------------------------------
-- Rounds (round-level detail, economy focus)
-- -----------------------------------------------------------
CREATE TABLE rounds (
    round_id        INTEGER PRIMARY KEY,
    match_id        INTEGER NOT NULL REFERENCES matches(match_id),
    round_number    INTEGER NOT NULL,
    side            TEXT NOT NULL CHECK (side IN ('Attack','Defense')),
    buy_type        TEXT NOT NULL CHECK (buy_type IN ('Full Buy','Half Buy','Eco','Force Buy')),
    loadout_value   INTEGER NOT NULL,
    round_result    TEXT NOT NULL CHECK (round_result IN ('Won','Lost')),
    win_condition   TEXT CHECK (win_condition IN ('Elimination','Spike Detonation','Spike Defused','Time Expired', NULL))
);

-- -----------------------------------------------------------
-- Indexes for query performance
-- -----------------------------------------------------------
CREATE INDEX idx_matches_player  ON matches(player_id);
CREATE INDEX idx_matches_date    ON matches(match_date);
CREATE INDEX idx_matches_agent   ON matches(agent_id);
CREATE INDEX idx_matches_map     ON matches(map_id);
CREATE INDEX idx_rounds_match    ON rounds(match_id);
CREATE INDEX idx_sessions_player ON player_sessions(player_id);
