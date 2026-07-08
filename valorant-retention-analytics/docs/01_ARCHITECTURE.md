# VALORANT Player Retention & Meta Analytics Platform
## Phase 1 — Architecture & Planning

---

## 1. Problem statement

Ranked player retention is a core health metric for any live-service game. This project
builds an end-to-end analytics pipeline that ingests match/session data, models player
churn, and surfaces retention and meta-balance insights through a Power BI dashboard.

**Primary business question:** Why do lower-rank players stop queueing ranked, and can we
predict who is about to churn?

**Secondary questions:**
- Which agents/maps are over- or under-performing at each rank tier?
- Does economy management (buy type) predict round win probability?
- How does session length/frequency relate to churn risk?

---

## 2. System architecture

```
┌──────────────┐     ┌───────────────┐     ┌───────────────┐     ┌──────────────┐
│  Data Source  │ --> │  Python ETL   │ --> │  SQLite DB    │ --> │   Power BI   │
│ (generated /  │     │ clean, shape, │     │  normalized   │     │  4 dashboard │
│  API-shaped)  │     │  feature eng. │     │  schema       │     │  pages       │
└──────────────┘     └───────────────┘     └───────────────┘     └──────────────┘
                              │
                              v
                     ┌───────────────┐
                     │  ML pipeline  │
                     │ churn model + │
                     │  SHAP values  │
                     └───────────────┘
```

**Flow:**
1. **Ingest** — player/session/match/round-level data (see `data/README.md` for data
   sourcing note — Riot's production API requires an approved key, so this project uses a
   statistically realistic generated dataset built on real agents/maps/rank tiers, structured
   exactly as the real API would return it. This is documented, not hidden — see Section 5.)
2. **Transform** — Python/Pandas: cleaning, type enforcement, feature engineering
   (rolling win rate, session gap, RR trend, churn label).
3. **Load** — normalized SQLite schema (see `sql/01_schema.sql` and ER diagram above).
4. **Analyze** — SQL views for aggregates, Python for EDA + churn model + SHAP.
5. **Visualize** — Power BI, 4 pages, imported from SQLite via ODBC or from exported CSVs.

---

## 3. Folder structure

```
valorant-analytics/
├── data/
│   ├── raw/              # generated source data (CSV)
│   └── processed/        # cleaned/feature-engineered tables, ready for SQL load
├── sql/
│   ├── 01_schema.sql      # DDL — tables, keys, indexes
│   ├── 02_load_data.sql   # data import statements
│   ├── 03_views.sql       # analytical views (KPIs, aggregates)
│   └── 04_queries.sql     # 15-20 analysis queries (window fns, CTEs, joins)
├── notebooks/
│   └── eda.ipynb          # exploratory analysis, visual sanity checks
├── ml/
│   ├── churn_model.py     # feature prep, train/test, model
│   └── shap_analysis.py   # explainability
├── powerbi/
│   ├── dax_measures.md    # documented DAX measure library
│   └── build_guide.md     # step-by-step page-by-page build instructions
├── docs/
│   ├── 01_ARCHITECTURE.md         (this file)
│   ├── 02_DATA_DICTIONARY.md
│   ├── 03_BUSINESS_QUESTIONS.md
│   └── 04_README.md               (final recruiter-facing summary)
└── scripts/
    └── generate_data.py   # synthetic data generator (Phase 2)
```

---

## 4. Tech stack justification

| Layer | Choice | Why |
|---|---|---|
| Data generation/ETL | Python (Pandas, NumPy) | Standard for data cleaning/feature engineering; directly transferable to real API data later |
| Storage | SQLite | Zero-setup, portable, still lets you write production-style SQL (joins, CTEs, window functions, views, indexes) — swappable for Postgres with near-identical syntax |
| Analysis | SQL + Python | SQL for aggregation/joins close to the data; Python for statistical modeling and ML that SQL can't do well |
| ML | scikit-learn / XGBoost + SHAP | Industry-standard for tabular churn prediction; SHAP gives per-feature explainability, which is what a real analytics team would ask for over a bare accuracy number |
| BI / Dashboard | Power BI | Matches your stated target skill set (Excel/Power BI listed on resume) and is the standard BI tool asked for in Indian analyst job postings |

---

## 5. Data sourcing — the honest version

Riot's official API requires an approved production key (not available to individual
developers on demand), and this environment has no general internet access to pull
live third-party scrapes. Rather than fabricate a "live API pull" you can't reproduce on
demand in an interview, this project:

- Uses **real, verifiable reference data**: actual agent roster, roles, maps, and the
  real Iron→Radiant rank ladder.
- **Generates statistically realistic match/session/round data** on top of that reference
  data — rank-appropriate win rates, realistic agent pick-rate skew, session-gap-driven
  churn — using documented, explainable logic in `scripts/generate_data.py`.
- This is stated explicitly in the README. It is a legitimate, common technique for
  portfolio projects when live access isn't available, and — importantly — it means you
  can explain and defend every number in the dataset, because you generated the logic
  yourself.

If you get real API access later (HenrikDev API is a viable unofficial option), the
same schema and pipeline drop in with only the ingestion step changed.

---

## 6. Project roadmap

| Phase | Deliverable | Status |
|---|---|---|
| 1 | Architecture, folder structure, schema, ER diagram, tech stack, roadmap | ✅ done (this doc) |
| 2 | Data generation, ETL pipeline, SQLite load | Next |
| 3 | Feature engineering, KPIs, SQL views, analytics tables, indexing | Pending |
| 4 | ML: churn prediction, segmentation, SHAP explainability | Pending |
| 5 | Power BI: 4 dashboard pages, DAX measures | Pending |
| 6 | Documentation: README, data dictionary, business questions, resume bullets | Pending |

Each phase produces working, reviewable output before moving to the next — no phase
starts until you've seen and approved the previous one.
