# Business Questions

This project is built to answer specific business/product questions, not just display charts.
Each question below maps to a query in `sql/04_queries.sql` (Phase 3) and/or a Power BI page (Phase 5).

## Core retention questions
1. Why do lower-rank players stop queueing ranked?
2. Which players are likely to churn, and what predicts it? (Phase 4 ML model)
3. Which agents/maps over- or under-perform at each rank tier?
4. Does economy management (buy type) predict round win probability?

## Product analytics questions (added after Phase 2)
5. **Which agent changes after a patch correlate with increased player engagement?**
   Answered via `patches` table joined to `matches` — compares pick rate and performance
   (ACS, win rate) for the buffed/nerfed agent in the window before vs. after each patch date.
6. **How does queue frequency differ across ranks?**
   Answered via `player_sessions` joined to `matches`/`ranks` — average sessions per week,
   grouped by rank tier.
7. **Which session patterns are associated with long-term retention?**
   Answered via session recency/frequency features (used directly in the Phase 4 churn model)
   — session gap trends, time-of-day consistency, session duration trends.
8. **How does party size affect return rate?**
   Answered via the new `party_size` column on `player_sessions` — compares next-session
   likelihood/gap for players who queued in a party vs. solo.

## Data note
Questions 5 and 8 required schema additions (`patches` table, `party_size` column) made
after Phase 2 — see `sql/01_schema.sql` and the updated ER diagram. Both effects are
built into the data generation logic itself (not just placeholder columns): patch effects
shift agent pick-rate/performance before vs. after the patch date, and party sessions boost
the following week's session probability for that player. Validated in Phase 2.1:
- Buffed agent pick rate: 5.5% (before) → 9.7% (after) in the ±15 day window around a patch
- Players who ever queued in a party averaged far more total sessions than solo-only players
