# Power BI Build Guide

Step-by-step, in order. Don't skip steps 1-4 (data import + relationships) —
if the model isn't set up right, every visual after it will show wrong or
blank numbers, which is confusing to debug later.

**Files you need:** everything in `powerbi/data/` (13 CSVs, built by
`scripts/export_for_powerbi.py`).

---

## Step 1: Import the data

1. Open Power BI Desktop → **Get Data** → **Text/CSV**
2. Navigate to `powerbi/data/`, select **all 13 CSV files at once** (click
   the first, Shift+click the last, or Ctrl+click each) → **Open**
3. Power BI will queue them up one at a time — click **Load** (not "Transform
   Data") for each, unless you hit Step 2 below first
4. If multi-select doesn't work on your Power BI version, just repeat
   **Get Data → Text/CSV** 13 times, once per file — slower, same result

You should end up with 13 tables in the **Fields** pane on the right:
`Dim_Players`, `Dim_Agents`, `Dim_Maps`, `Dim_Ranks`, `Dim_Patches`,
`Dim_Date`, `Fact_Matches`, `Fact_Rounds`, `Fact_Sessions`,
`Precomputed_PatchImpact`, `Precomputed_PartyRetention`,
`Precomputed_QueueFrequencyByRank`, `Precomputed_SHAP_Importance`.

---

## Step 2: Fix date column types

Click **Data view** (left sidebar, the table-grid icon). For each of these
columns, click the column → **Column tools** tab → **Data type** → set to
**Date** (not Date/Time, just Date):
- `Dim_Date[Date]`
- `Fact_Matches[match_date]`
- `Fact_Sessions[session_date]`
- `Dim_Patches[patch_date]`
- `Dim_Players[account_created]`

If any of these already show a calendar icon in the Fields pane, they're
already typed correctly — skip them.

---

## Step 3: Mark Dim_Date as an official Date table

This step is required for the rolling-7-day measure to work correctly.

1. Click on `Dim_Date` table in the Fields pane
2. **Modeling** tab (top ribbon) → **Mark as Date Table** → **Mark as Date Table**
3. When prompted, select `Date` as the date column → **Confirm**

---

## Step 4: Build relationships

Click **Model view** (left sidebar, the 3-boxes-connected icon). Power BI
often auto-detects some relationships from matching column names — verify
each of these exists, and manually drag-and-drop to create any missing ones
(drag from the field in one table to the matching field in the other):

| From (many side) | To (one side) |
|---|---|
| `Fact_Matches[player_id]` | `Dim_Players[player_id]` |
| `Fact_Matches[agent_id]` | `Dim_Agents[agent_id]` |
| `Fact_Matches[map_id]` | `Dim_Maps[map_id]` |
| `Fact_Matches[rank_id]` | `Dim_Ranks[rank_id]` |
| `Fact_Matches[patch_id]` | `Dim_Patches[patch_id]` |
| `Fact_Matches[match_date]` | `Dim_Date[Date]` |
| `Fact_Rounds[match_id]` | `Fact_Matches[match_id]` |
| `Fact_Sessions[player_id]` | `Dim_Players[player_id]` |
| `Fact_Sessions[session_date]` | `Dim_Date[Date]` |

Each relationship line should show **1** on the dimension side and **\*** on
the fact side. If a relationship shows as dotted/inactive, right-click it →
check the cardinality is "Many to one."

---

## Step 5: Add the DAX measures

Open `powerbi/dax_measures.md`. For each measure:
1. Click the table named in that section's heading (e.g., `Fact_Matches`) in the Fields pane
2. **Modeling** tab → **New Measure**
3. Paste the full formula (including the measure name before the `=`)
4. Press Enter

Do this for all 22 measures before moving to Step 6 — trying to build a
visual before its measure exists just gives you a blank/error visual.

---

## Step 6: Build the 4 pages

Rename your 4 default report pages (bottom tabs) to: **Executive Overview**,
**Retention & Churn**, **Agent & Map Meta**, **Economy Impact**.

### Page 1 — Executive Overview
- **4 Card visuals** across the top: `[Total Players]`, `[Total Matches]`,
  `[Overall Win Rate]`, `[Churn Rate]`
- **Line chart**: X-axis = `Dim_Date[Date]`, Y-axis = `[Daily Active Players]`
  and `[Rolling 7-Day Active Players]` (both lines on the same chart)
- **Bar chart**: X-axis = `Dim_Ranks[rank_name]` (sort by `rank_tier_order`
  — click the "..." on the visual → Sort by → rank_tier_order), Y-axis = `[Avg ACS]`
- **Donut chart**: `Dim_Players[region]`, values = `[Total Players]`

### Page 2 — Retention & Churn
- **4 Cards**: `[Churned Players]`, `[Churn Rate]`, `[Active Players]`, `[High-Risk Players (>50%)]`
- **Bar chart**: X-axis = `Dim_Players[segment_name]`, Y-axis = `[Churn Rate]`
- **Bar chart**: import `Precomputed_SHAP_Importance` directly — X-axis =
  `feature`, Y-axis = `mean_abs_shap`, sorted descending — this is your
  "what actually predicts churn" visual
- **Bar chart**: `Precomputed_QueueFrequencyByRank` — X-axis = `rank_name`
  (sort by `rank_tier_order`), Y-axis = `avg_sessions_per_week`
- **Bar chart**: `Precomputed_PartyRetention` — X-axis = `queue_type`,
  Y-axis = `pct_returned_within_7d`
- **Table**: `Dim_Players` filtered to `churn_probability > 0.5` (use a
  visual-level filter), columns: `player_name`, `segment_name`,
  `churn_probability` — sort descending by probability. This is your
  actionable "at-risk player watchlist."

### Page 3 — Agent & Map Meta
- **Bar chart**: X-axis = `Dim_Agents[agent_name]`, Y-axis = `[Agent Pick Rate]`, sorted descending
- **Bar chart**: X-axis = `Dim_Agents[role]`, Y-axis = `[Agent/Map Win Rate]`
- **Bar chart**: X-axis = `Dim_Maps[map_name]`, Y-axis = `[Agent/Map Win Rate]`
- **Table or clustered bar**: `Precomputed_PatchImpact` — rows =
  `patch_version` + `period`, values = `buffed_pick_rate`, `buffed_avg_acs`
  — shows the before/after effect directly
- **Slicer**: `Dim_Agents[role]` — lets you filter the whole page by role

### Page 4 — Economy Impact
- **Bar chart**: X-axis = `Fact_Rounds[buy_type]`, Y-axis = `[Round Win Rate]`
- **3 Cards**: `[Avg Loadout Value]`, `[Eco Round %]`, `[Full Buy Round %]`
- **Column chart**: X-axis = `Fact_Rounds[side]` (Attack/Defense), Y-axis =
  `[Round Win Rate]` — shows attack vs. defense side balance
- **Stacked bar**: X-axis = `Fact_Rounds[buy_type]`, Y-axis = count of rounds,
  legend = `round_result` — shows win/loss volume per buy type

---

## Step 7: Polish (optional but recommended)

- **Theme**: View tab → Themes → pick a dark theme (matches the VALORANT
  aesthetic and looks more intentional than default white)
- **Consistent titles**: rename each visual's default title to something
  specific ("Churn Rate by Player Segment" not "Chart")
- **Page navigation**: Insert tab → Buttons → Blank, add one per page, so
  the dashboard feels like a real product, not 4 disconnected screens

---

## Step 8: Save

Save the file as `powerbi/valorant_dashboard.pbix` inside your project folder.

**One thing to check before committing to git:** with 585K rounds embedded,
the `.pbix` file could end up fairly large (Power BI compresses well, but
check the file size in File Explorer — if it's over ~90MB, GitHub will
reject a normal push since it enforces a 100MB per-file limit). If it's
too big, tell me and we'll either trim the embedded row count or set up
Git LFS for that one file — don't just silently leave it out of the repo
without a note in the README explaining why.
