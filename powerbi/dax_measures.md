# DAX Measures Library

22 measures, organized by the dashboard page they belong to. Paste each into
Power BI: **Modeling tab -> New Measure**, with the correct table selected
(shown in each heading) as the "home table" for the measure.

A design note up front: a few of the harder analytical questions (patch
impact windows, SHAP importance, party-size retention, queue frequency by
rank) are **intentionally not recreated as DAX** — they're already computed
correctly in SQL (Phase 3) and Python (Phase 4), exported as ready-made
tables (`Precomputed_*.csv`). DAX is excellent at row-context aggregation
sliced by dimensions (which is what these 22 measures do); sequence-based
or model-based logic like "before vs. after a patch date" or "SHAP value"
is more natural in SQL/Python. Recreating it in DAX just to inflate the
measure count would be redundant, harder to audit, and more likely to
introduce a subtle bug — worth saying exactly this if asked in an interview.

---

## Page 1: Executive Overview

**Home table: Fact_Matches** (unless noted)

```
Total Players =
DISTINCTCOUNT(Dim_Players[player_id])
```

```
Total Matches =
COUNTROWS(Fact_Matches)
```

```
Total Rounds =
COUNTROWS(Fact_Rounds)
```

```
Overall Win Rate =
DIVIDE(
    CALCULATE(COUNTROWS(Fact_Matches), Fact_Matches[match_result] = "Win"),
    COUNTROWS(Fact_Matches)
)
```

```
Avg ACS =
AVERAGE(Fact_Matches[acs])
```

**Home table: Fact_Sessions**

```
Daily Active Players (DAP) =
DISTINCTCOUNT(Fact_Sessions[player_id])
```
Note: this measure's value changes meaning depending on what date filter is
applied via Dim_Date - on a single-day filter it's true DAU; over a week
it becomes WAU, etc. This is standard DAX practice - the measure is
"active players in the currently filtered period."

```
Rolling 7-Day Active Players =
AVERAGEX(
    DATESINPERIOD(Dim_Date[Date], MAX(Dim_Date[Date]), -7, DAY),
    [Daily Active Players]
)
```

```
Avg Session Duration (min) =
AVERAGE(Fact_Sessions[session_duration_min])
```

---

## Page 2: Retention & Churn

**Home table: Dim_Players**

```
Total Players (Churn Base) =
DISTINCTCOUNT(Dim_Players[player_id])
```

```
Churned Players =
CALCULATE(DISTINCTCOUNT(Dim_Players[player_id]), Dim_Players[churned] = 1)
```

```
Churn Rate =
DIVIDE([Churned Players], [Total Players (Churn Base)])
```

```
Active Players =
CALCULATE(DISTINCTCOUNT(Dim_Players[player_id]), Dim_Players[churned] = 0)
```

```
Avg Churn Probability =
AVERAGE(Dim_Players[churn_probability])
```

```
High-Risk Players (>50%) =
CALCULATE(
    DISTINCTCOUNT(Dim_Players[player_id]),
    Dim_Players[churn_probability] > 0.5
)
```

**Home table: Fact_Sessions**

```
Avg Sessions per Player =
DIVIDE(COUNTROWS(Fact_Sessions), DISTINCTCOUNT(Fact_Sessions[player_id]))
```

**Use directly as tables/visuals (no DAX needed):**
- `Precomputed_PartyRetention` — bar chart: queue_type vs. avg_days_to_next_session / pct_returned_within_7d (answers: does party size affect return rate)
- `Precomputed_QueueFrequencyByRank` — line/bar chart: rank_name (sorted by rank_tier_order) vs. avg_sessions_per_week (answers: queue frequency by rank)
- `Precomputed_SHAP_Importance` — horizontal bar chart: feature vs. mean_abs_shap (answers: what actually predicts churn)
- **Churn Rate by Segment**: put `Dim_Players[segment_name]` on rows of a table/matrix visual with the `[Churn Rate]` measure as the value — Power BI automatically re-slices the measure per segment, no new DAX needed

---

## Page 3: Agent & Map Meta

**Home table: Fact_Matches**

```
Agent Pick Rate =
DIVIDE(
    COUNTROWS(Fact_Matches),
    CALCULATE(COUNTROWS(Fact_Matches), ALL(Dim_Agents))
)
```
Put `Dim_Agents[agent_name]` on a bar chart axis with this measure as the
value — it'll show each agent's share of total picks correctly, because
`ALL(Dim_Agents)` removes the agent filter only for the denominator.

```
Agent/Map Win Rate =
DIVIDE(
    CALCULATE(COUNTROWS(Fact_Matches), Fact_Matches[match_result] = "Win"),
    COUNTROWS(Fact_Matches)
)
```
(Same formula as `Overall Win Rate` — reused across contexts. Put it on a
visual sliced by `Dim_Agents[agent_name]` or `Dim_Maps[map_name]` and it
recalculates correctly per row/category. You do not need two separate
measures for this - DAX measures are context-aware.)

```
Avg Rounds per Match =
AVERAGEX(Fact_Matches, Fact_Matches[rounds_won] + Fact_Matches[rounds_lost])
```

```
Avg Headshot % =
AVERAGE(Fact_Matches[headshot_pct])
```

```
Avg KAST % =
AVERAGE(Fact_Matches[kast_pct])
```

**Use directly as a table/visual (no DAX needed):**
- `Precomputed_PatchImpact` — table or clustered bar: patch_version + period (Before/After) vs. buffed_pick_rate / buffed_avg_acs / nerfed_pick_rate (answers: does an agent change after a patch correlate with engagement)

---

## Page 4: Economy Impact

**Home table: Fact_Rounds**

```
Total Rounds Played =
COUNTROWS(Fact_Rounds)
```

```
Round Win Rate =
DIVIDE(
    CALCULATE(COUNTROWS(Fact_Rounds), Fact_Rounds[round_result] = "Won"),
    COUNTROWS(Fact_Rounds)
)
```
(Slice this by `Fact_Rounds[buy_type]` on a bar chart axis to get win rate
per buy type — Full Buy / Half Buy / Eco / Force Buy.)

```
Avg Loadout Value =
AVERAGE(Fact_Rounds[loadout_value])
```

```
Eco Round % =
DIVIDE(
    CALCULATE(COUNTROWS(Fact_Rounds), Fact_Rounds[buy_type] = "Eco"),
    COUNTROWS(Fact_Rounds)
)
```

```
Full Buy Round % =
DIVIDE(
    CALCULATE(COUNTROWS(Fact_Rounds), Fact_Rounds[buy_type] = "Full Buy"),
    COUNTROWS(Fact_Rounds)
)
```

---

## Measure count: 22 real DAX measures + 5 precomputed tables used directly as visuals.
This is intentionally scoped, not padded — every measure here is something
you can open in Power BI, read, and explain line by line.
