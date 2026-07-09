-- =====================================================================
-- Phase 3 - Analysis Queries
-- 18 queries. Each is labeled with: SQL techniques used, and which
-- business question (docs/03_BUSINESS_QUESTIONS.md) it answers.
-- =====================================================================

-- Q1. Daily active players + 7-day rolling average (window function: AVG OVER)
-- Answers: engagement trend over time (DAU/rolling-WAU proxy)
SELECT session_date,
       COUNT(DISTINCT player_id) AS daily_active_players,
       ROUND(AVG(COUNT(DISTINCT player_id)) OVER (
           ORDER BY session_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
       ), 1) AS rolling_7d_avg
FROM player_sessions
GROUP BY session_date
ORDER BY session_date;


-- Q2. New player conversion: % of players whose first-ever session was
-- followed by a second session within 7 days (CTE + self-join)
-- Answers: new player retention / onboarding health
WITH first_two AS (
    SELECT player_id, session_date,
           ROW_NUMBER() OVER (PARTITION BY player_id ORDER BY session_date) AS rn
    FROM player_sessions
),
first_session AS (SELECT player_id, session_date FROM first_two WHERE rn = 1),
second_session AS (SELECT player_id, session_date FROM first_two WHERE rn = 2)
SELECT
    COUNT(f.player_id) AS total_new_players,
    SUM(CASE WHEN julianday(s.session_date) - julianday(f.session_date) <= 7 THEN 1 ELSE 0 END) AS returned_within_7d,
    ROUND(100.0 * SUM(CASE WHEN julianday(s.session_date) - julianday(f.session_date) <= 7 THEN 1 ELSE 0 END)
          / COUNT(f.player_id), 1) AS pct_converted
FROM first_session f
LEFT JOIN second_session s ON s.player_id = f.player_id;


-- Q3. Current rank distribution across all players (join to the current-rank view)
-- Answers: competitive ecosystem health / rank ladder shape
SELECT rank_name, rank_tier_order, COUNT(*) AS players
FROM v_player_current_rank
GROUP BY rank_name, rank_tier_order
ORDER BY rank_tier_order;


-- Q4. Win rate and average performance by rank tier (join)
-- Answers: does skill/performance scale consistently with rank
SELECT r.rank_name, r.rank_tier_order,
       COUNT(*) AS matches,
       ROUND(100.0 * SUM(CASE WHEN m.match_result = 'Win' THEN 1 ELSE 0 END) / COUNT(*), 1) AS win_pct,
       ROUND(AVG(m.acs), 1) AS avg_acs,
       ROUND(AVG(m.kast_pct), 1) AS avg_kast
FROM matches m
JOIN ranks r ON r.rank_id = m.rank_id
GROUP BY r.rank_name, r.rank_tier_order
ORDER BY r.rank_tier_order;


-- Q5. [PRODUCT ANALYTICS] Queue frequency by rank tier
-- Answers business question 6: "How does queue frequency differ across ranks?"
SELECT * FROM v_queue_frequency_by_rank;


-- Q6. Agent overall pick rate, ranked (window function: RANK)
-- Answers: which agents are most popular in the current meta
SELECT agent_name, role, picks,
       RANK() OVER (ORDER BY picks DESC) AS pick_rank
FROM (
    SELECT a.agent_name, a.role, COUNT(*) AS picks
    FROM matches m JOIN agents a ON a.agent_id = m.agent_id
    GROUP BY a.agent_name, a.role
);


-- Q7. Which agents dominate low elo but underperform at high elo
-- (CTE + window function: RANK within each rank bucket, then compare rank position)
-- CAVEAT: current simulation doesn't model true agent-power-by-rank-tier signal,
-- and the "High" bucket has small per-agent sample sizes (often <25 picks) -
-- treat this as a query-writing demonstration, not a validated finding, unless
-- the underlying data generator is extended to add real tier-affinity signal.
WITH bucket_ranked AS (
    SELECT rank_bucket, agent_name, win_pct,
           RANK() OVER (PARTITION BY rank_bucket ORDER BY win_pct DESC) AS win_rank
    FROM v_agent_meta_by_rank_bucket
)
SELECT low.agent_name,
       low.win_pct AS low_elo_win_pct, low.win_rank AS low_elo_rank,
       high.win_pct AS high_elo_win_pct, high.win_rank AS high_elo_rank,
       (low.win_rank - high.win_rank) AS rank_drop_at_high_elo
FROM bucket_ranked low
JOIN bucket_ranked high ON high.agent_name = low.agent_name AND high.rank_bucket = 'High (Ascendant-Radiant)'
WHERE low.rank_bucket = 'Low (Iron-Silver)'
ORDER BY rank_drop_at_high_elo DESC
LIMIT 10;


-- Q8. Map win rate and average round count (join)
-- Answers: which maps are unbalanced / produce lopsided outcomes
SELECT * FROM v_map_stats ORDER BY win_pct DESC;


-- Q9. Economy: round win rate by buy type
-- Answers: does buy-type decision predict round outcome
SELECT * FROM v_economy_round_win_rate ORDER BY win_pct DESC;


-- Q10. Eco-round cascade effect: probability of an eco/force buy round
-- immediately following a lost round (window function: LAG)
-- Answers: does losing a round trigger a defensive economy decision
WITH round_seq AS (
    SELECT match_id, round_number, buy_type, round_result,
           LAG(round_result) OVER (PARTITION BY match_id ORDER BY round_number) AS prev_result
    FROM rounds
)
SELECT prev_result,
       COUNT(*) AS rounds,
       ROUND(100.0 * SUM(CASE WHEN buy_type IN ('Eco','Force Buy') THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_eco_or_force
FROM round_seq
WHERE prev_result IS NOT NULL
GROUP BY prev_result;


-- Q11. First blood impact on match win probability (CTE bucket + aggregate)
-- Answers: how much does an early kill advantage matter
SELECT CASE
           WHEN first_bloods = 0 THEN '0'
           WHEN first_bloods BETWEEN 1 AND 2 THEN '1-2'
           ELSE '3+'
       END AS first_blood_bucket,
       COUNT(*) AS matches,
       ROUND(100.0 * SUM(CASE WHEN match_result = 'Win' THEN 1 ELSE 0 END) / COUNT(*), 1) AS win_pct
FROM matches
GROUP BY first_blood_bucket
ORDER BY first_blood_bucket;


-- Q12. [PRODUCT ANALYTICS] Patch impact on agent pick rate/performance
-- Answers business question 5: "Which agent changes after a patch correlate
-- with increased player engagement?"
SELECT * FROM v_patch_impact;


-- Q13. [PRODUCT ANALYTICS] Party size vs. return rate
-- Answers business question 8: "How does party size affect return rate?"
SELECT * FROM v_party_retention;


-- Q14. [PRODUCT ANALYTICS] Session recency/frequency -> churn candidates
-- Answers business question 7: "Which session patterns are associated
-- with long-term retention?" Surfaces players trending toward churn.
-- (window function via v_session_gaps, RANK to prioritize highest-risk players)
SELECT player_id, last_session_date, total_sessions, days_since_last_session,
       avg_gap_days, churned,
       RANK() OVER (ORDER BY days_since_last_session DESC) AS churn_risk_rank
FROM v_player_retention_features
ORDER BY churn_risk_rank
LIMIT 20;


-- Q15. Rank progression: cumulative RR change over time per player
-- (window function: SUM OVER with an ordered running total)
-- Answers: what a player's rank trajectory looks like match-by-match
SELECT player_id, match_date, rr_change,
       SUM(rr_change) OVER (PARTITION BY player_id ORDER BY match_date, match_id
                             ROWS UNBOUNDED PRECEDING) AS cumulative_rr
FROM matches
WHERE player_id = 1
ORDER BY match_date;


-- Q16. Performance quartiles by ACS (window function: NTILE)
-- Answers: player segmentation input for Phase 4 clustering
SELECT player_id, avg_acs,
       NTILE(4) OVER (ORDER BY avg_acs) AS performance_quartile
FROM v_player_kpis
WHERE total_matches >= 10
ORDER BY avg_acs DESC;


-- Q17. Session duration distribution by rank tier (join + aggregate)
-- Answers: do higher-rank players play longer/shorter sessions
SELECT r.rank_name, r.rank_tier_order,
       ROUND(AVG(s.session_duration_min), 1) AS avg_session_min,
       COUNT(*) AS sessions
FROM player_sessions s
JOIN v_player_current_rank r ON r.player_id = s.player_id
GROUP BY r.rank_name, r.rank_tier_order
ORDER BY r.rank_tier_order;


-- Q18. Regional player distribution and average performance (join + aggregate)
-- Answers: regional engagement/performance comparison
SELECT region, COUNT(*) AS players,
       ROUND(AVG(win_pct), 1) AS avg_win_pct,
       ROUND(AVG(avg_acs), 1) AS avg_acs,
       ROUND(AVG(total_sessions), 1) AS avg_sessions_per_player
FROM v_player_kpis
GROUP BY region
ORDER BY players DESC;
