-- =====================================================================
-- Phase 3 - Analytical Views
-- Each view is documented with: purpose, and which business question
-- (docs/03_BUSINESS_QUESTIONS.md) it supports.
-- =====================================================================

-- -----------------------------------------------------------
-- v_player_kpis
-- Per-player rollup: matches, win %, performance averages, session count.
-- Pre-aggregates matches and sessions separately before joining to avoid
-- fan-out (joining two 1-to-many tables directly on player_id would
-- duplicate rows and silently corrupt the averages).
-- -----------------------------------------------------------
CREATE VIEW v_player_kpis AS
WITH match_agg AS (
    SELECT player_id,
           COUNT(*) AS total_matches,
           SUM(CASE WHEN match_result = 'Win' THEN 1 ELSE 0 END) AS wins,
           AVG(acs) AS avg_acs,
           AVG(kast_pct) AS avg_kast,
           AVG(headshot_pct) AS avg_hs_pct,
           MAX(match_date) AS last_match_date
    FROM matches
    GROUP BY player_id
),
session_agg AS (
    SELECT player_id,
           COUNT(*) AS total_sessions,
           MAX(session_date) AS last_session_date,
           AVG(session_duration_min) AS avg_session_min
    FROM player_sessions
    GROUP BY player_id
)
SELECT p.player_id, p.player_name, p.region, p.starting_rank_id,
       COALESCE(ma.total_matches, 0) AS total_matches,
       ROUND(100.0 * COALESCE(ma.wins, 0) / NULLIF(ma.total_matches, 0), 1) AS win_pct,
       ROUND(ma.avg_acs, 1) AS avg_acs,
       ROUND(ma.avg_kast, 1) AS avg_kast,
       ROUND(ma.avg_hs_pct, 1) AS avg_hs_pct,
       ma.last_match_date,
       COALESCE(sa.total_sessions, 0) AS total_sessions,
       sa.last_session_date,
       ROUND(sa.avg_session_min, 1) AS avg_session_min
FROM players p
LEFT JOIN match_agg ma   ON ma.player_id = p.player_id
LEFT JOIN session_agg sa ON sa.player_id = p.player_id;

-- -----------------------------------------------------------
-- v_player_current_rank
-- Each player's rank as of their most recent match (window function
-- ROW_NUMBER to pick the latest row per player).
-- -----------------------------------------------------------
CREATE VIEW v_player_current_rank AS
SELECT t.player_id, t.rank_id, r.rank_name, r.rank_tier_order
FROM (
    SELECT player_id, rank_id,
           ROW_NUMBER() OVER (PARTITION BY player_id ORDER BY match_date DESC, match_id DESC) AS rn
    FROM matches
) t
JOIN ranks r ON r.rank_id = t.rank_id
WHERE t.rn = 1;

-- -----------------------------------------------------------
-- v_session_gaps
-- Gap in days between a player's consecutive sessions (LAG window fn).
-- Building block for retention/churn features.
-- -----------------------------------------------------------
CREATE VIEW v_session_gaps AS
SELECT player_id, session_date,
       julianday(session_date) - julianday(
           LAG(session_date) OVER (PARTITION BY player_id ORDER BY session_date)
       ) AS gap_days
FROM player_sessions;

-- -----------------------------------------------------------
-- v_player_retention_features
-- Churn label + recency/frequency features -> feeds directly into the
-- Phase 4 ML model. churned = 1 if no session in the final 14 days of
-- the observation window (WINDOW_END = 2026-06-30, matches the churn
-- definition used in the data generator).
-- -----------------------------------------------------------
CREATE VIEW v_player_retention_features AS
WITH gaps AS (
    SELECT player_id, AVG(gap_days) AS avg_gap_days, COUNT(*) AS n_gaps
    FROM v_session_gaps
    WHERE gap_days IS NOT NULL
    GROUP BY player_id
),
recency AS (
    SELECT player_id,
           MAX(session_date) AS last_session_date,
           MIN(session_date) AS first_session_date,
           COUNT(*) AS total_sessions,
           julianday('2026-06-30') - julianday(MAX(session_date)) AS days_since_last_session
    FROM player_sessions
    GROUP BY player_id
)
SELECT r.player_id, r.first_session_date, r.last_session_date, r.total_sessions,
       r.days_since_last_session,
       ROUND(COALESCE(g.avg_gap_days, r.days_since_last_session), 2) AS avg_gap_days,
       CASE WHEN r.days_since_last_session > 14 THEN 1 ELSE 0 END AS churned
FROM recency r
LEFT JOIN gaps g ON g.player_id = r.player_id;

-- -----------------------------------------------------------
-- v_agent_meta_by_rank_bucket
-- Agent pick rate / win rate / ACS, grouped into 3 rank bands.
-- Supports: "which agents dominate low elo but underperform at high elo"
-- -----------------------------------------------------------
CREATE VIEW v_agent_meta_by_rank_bucket AS
WITH bucketed AS (
    SELECT m.*,
        CASE
            WHEN r.rank_tier_order <= 9  THEN 'Low (Iron-Silver)'
            WHEN r.rank_tier_order <= 18 THEN 'Mid (Gold-Diamond)'
            ELSE 'High (Ascendant-Radiant)'
        END AS rank_bucket
    FROM matches m
    JOIN ranks r ON r.rank_id = m.rank_id
)
SELECT b.rank_bucket, a.agent_name, a.role,
       COUNT(*) AS picks,
       ROUND(100.0 * SUM(CASE WHEN b.match_result = 'Win' THEN 1 ELSE 0 END) / COUNT(*), 1) AS win_pct,
       ROUND(AVG(b.acs), 1) AS avg_acs
FROM bucketed b
JOIN agents a ON a.agent_id = b.agent_id
GROUP BY b.rank_bucket, a.agent_name;

-- -----------------------------------------------------------
-- v_map_stats
-- Map-level pick volume, win rate, avg round count.
-- -----------------------------------------------------------
CREATE VIEW v_map_stats AS
SELECT mp.map_name,
       COUNT(*) AS matches_played,
       ROUND(100.0 * SUM(CASE WHEN m.match_result = 'Win' THEN 1 ELSE 0 END) / COUNT(*), 1) AS win_pct,
       ROUND(AVG(m.rounds_won + m.rounds_lost), 1) AS avg_total_rounds
FROM matches m
JOIN maps mp ON mp.map_id = m.map_id
GROUP BY mp.map_name;

-- -----------------------------------------------------------
-- v_economy_round_win_rate
-- Round win % by buy type. Supports: does economy predict round outcome.
-- -----------------------------------------------------------
CREATE VIEW v_economy_round_win_rate AS
SELECT buy_type,
       COUNT(*) AS rounds,
       ROUND(100.0 * SUM(CASE WHEN round_result = 'Won' THEN 1 ELSE 0 END) / COUNT(*), 1) AS win_pct
FROM rounds
GROUP BY buy_type;

-- -----------------------------------------------------------
-- v_patch_impact
-- Buffed/nerfed agent pick rate + ACS, before vs. after each patch,
-- in a +/-15 day window around the patch date.
-- Supports business question 5 (product analytics).
-- -----------------------------------------------------------
CREATE VIEW v_patch_impact AS
WITH windowed AS (
    SELECT p.patch_version, p.patch_date, p.buffed_agent_id, p.nerfed_agent_id,
           m.agent_id, m.acs, m.match_date,
           CASE WHEN m.match_date < p.patch_date THEN 'Before' ELSE 'After' END AS period
    FROM patches p
    JOIN matches m
      ON m.match_date BETWEEN date(p.patch_date, '-15 days') AND date(p.patch_date, '+15 days')
)
SELECT patch_version, period,
       COUNT(*) AS total_matches_in_window,
       SUM(CASE WHEN agent_id = buffed_agent_id THEN 1 ELSE 0 END) AS buffed_agent_picks,
       ROUND(1.0 * SUM(CASE WHEN agent_id = buffed_agent_id THEN 1 ELSE 0 END) / COUNT(*), 3) AS buffed_pick_rate,
       ROUND(AVG(CASE WHEN agent_id = buffed_agent_id THEN acs END), 1) AS buffed_avg_acs,
       SUM(CASE WHEN agent_id = nerfed_agent_id THEN 1 ELSE 0 END) AS nerfed_agent_picks,
       ROUND(1.0 * SUM(CASE WHEN agent_id = nerfed_agent_id THEN 1 ELSE 0 END) / COUNT(*), 3) AS nerfed_pick_rate,
       ROUND(AVG(CASE WHEN agent_id = nerfed_agent_id THEN acs END), 1) AS nerfed_avg_acs
FROM windowed
GROUP BY patch_version, period
ORDER BY patch_version, period DESC;

-- -----------------------------------------------------------
-- v_party_retention
-- Solo vs. party queue sessions: avg days until the player's next
-- session, and % who returned within 7 days (LEAD window function).
-- Supports business question 8 (product analytics).
-- -----------------------------------------------------------
CREATE VIEW v_party_retention AS
WITH next_session AS (
    SELECT player_id, session_date, party_size,
           LEAD(session_date) OVER (PARTITION BY player_id ORDER BY session_date) AS next_session_date
    FROM player_sessions
)
SELECT CASE WHEN party_size = 1 THEN 'Solo' ELSE 'Party' END AS queue_type,
       COUNT(*) AS sessions,
       ROUND(AVG(julianday(next_session_date) - julianday(session_date)), 2) AS avg_days_to_next_session,
       ROUND(100.0 * SUM(
           CASE WHEN next_session_date IS NOT NULL
                     AND julianday(next_session_date) - julianday(session_date) <= 7
                THEN 1 ELSE 0 END
       ) / COUNT(*), 1) AS pct_returned_within_7d
FROM next_session
GROUP BY queue_type;

-- -----------------------------------------------------------
-- v_queue_frequency_by_rank
-- Average sessions/week, grouped by current rank tier.
-- Supports business question 6 (product analytics).
-- -----------------------------------------------------------
CREATE VIEW v_queue_frequency_by_rank AS
WITH player_weeks AS (
    SELECT player_id,
           COUNT(*) AS total_sessions,
           (julianday(MAX(session_date)) - julianday(MIN(session_date))) / 7.0 AS active_weeks
    FROM player_sessions
    GROUP BY player_id
)
SELECT pr.rank_name, pr.rank_tier_order,
       ROUND(AVG(pw.total_sessions / NULLIF(pw.active_weeks, 0)), 2) AS avg_sessions_per_week
FROM player_weeks pw
JOIN v_player_current_rank pr ON pr.player_id = pw.player_id
GROUP BY pr.rank_name, pr.rank_tier_order
ORDER BY pr.rank_tier_order;
