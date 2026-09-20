# Repository Guidance

## Purpose and stack

This repository studies mortgage-rate lock-in, housing affordability, and
move-up transaction activity in Indianapolis and the seven-county Twin Cities
region. The codebase uses Python for raw transaction ingestion, R for panel
construction and econometrics, and Streamlit for the existing Indiana map.

Keep research claims proportional to the available data. Completed-sale
records support price and transaction-volume analysis, but do not by themselves
identify buyer demand elasticity or listing-market behavior.

## Repository map

- `scripts/00_data_pipeline.py` is the established 2021–2025 Indiana analysis
  pipeline. It also performs Redfin and Census enrichment and writes
  `data/processed/sdf_indiana.csv`.
- `scripts/00_indiana_sdf_pipeline.py` is the independent 2015–present Indiana
  SDF normalizer and quality audit. Its output must not silently replace
  `sdf_indiana.csv`.
- `scripts/indiana_sdf/` contains the reusable Indiana format adapters and
  eligibility logic.
- `scripts/00_mn_ecrv_pipeline.py` and `scripts/mn_ecrv/` contain the Minnesota
  XML ingestion, version store, and exports.
- `scripts/01_data_pipeline.R`, `02_eda_descriptive_stats.R`, and
  `03_regression_hypothesis_tests.R` are the established Indiana analytical
  sequence.
- `tests/` contains standard-library `unittest` coverage for both state
  ingestion paths.
- `docs/minnesota_ecrv_architecture.md` is authoritative for Minnesota's current
  implementation status and known research limitations.

## Project skills

- For Indiana or Minnesota raw ingestion, backfills, schemas, duplicates,
  eligibility funnels, or ingestion completion review, read and follow
  `.agents/skills/housing-ingestion-audit/SKILL.md`.
- For unified transaction contracts, county-month aggregation, ACS/FRED joins,
  baseline price tiers, or panel coverage, read and follow
  `.agents/skills/housing-panel-builder/SKILL.md`.
- For DiD, event studies, rate interactions, pre-trends, inference, robustness,
  or interpretation of model results, read and follow
  `.agents/skills/housing-econometrics/SKILL.md`.
- For pre-publication validation of claims, figures, tables, documentation, or
  reproducibility, read and follow
  `.agents/skills/housing-research-release/SKILL.md`.
- Load only the skills relevant to the current request. These skills supplement
  rather than replace the durable repository constraints in this file.

## Study definitions

- Indianapolis geography: Marion is `URBAN_CORE`; Boone, Hamilton, Hendricks,
  and Johnson are `SUBURBAN_COLLAR`.
- Twin Cities geography: Hennepin and Ramsey are the urban core; Anoka, Carver,
  Dakota, Scott, and Washington are the suburban collar. This is the seven-
  county planning region, not the full federal MSA.
- Indiana historical output retains two cohorts:
  `eligible_current_study` reproduces the existing modern transaction rules,
  while `eligible_strict_comparable` adds assessor validation, trending, and
  improved-residential parcel requirements.
- Gross sale price is canonical until cross-era personal-property and seller-
  concession units have been validated.

Do not change county membership, treatment definitions, price floors/caps,
eligibility rules, pandemic boundaries, or price-tier construction without
making the methodological change explicit and updating the audit/tests.

## Data handling

- Treat all raw SDF and eCRV files as immutable. Do not rename, move, delete, or
  commit them without explicit user direction.
- Root-level `YYYY.txt` files are legacy Indiana extracts: pipe-delimited,
  Windows-1252-compatible, with sale prices already in dollars.
- `SALEDISCYYYY.txt` and `SALEPARCELYYYY.txt` are modern Indiana extracts:
  UTF-16 tab-delimited, with transaction monetary values stored in cents.
- Minnesota raw ZIPs belong under `data/raw/mn/ecrv/`; generated SQLite, CSV,
  quality, and Indiana history outputs remain ignored by Git.
- Never export buyer, seller, phone, email, title-company, mailing-address, or
  other party data. Read only analytical columns from raw files.
- Preserve transaction grain. Aggregate child parcels/uses/financing rather
  than joining them in a way that multiplies prices or transaction counts.
- Collapse only analytically identical duplicate transaction records.
  Quarantine conflicting duplicates unless an authoritative revision rule has
  been established.

## Commands

Use the repository virtual environment when it exists:

```bash
.venv/bin/python -m unittest discover -s tests -v

.venv/bin/python scripts/00_indiana_sdf_pipeline.py \
  --input-dir . \
  --output data/processed/indiana_sdf_history.csv \
  --quality-dir outputs/indiana/quality

.venv/bin/python scripts/00_mn_ecrv_pipeline.py all
```

Run the established enriched Indiana pipeline only when its network/API and
cache requirements are in scope:

```bash
.venv/bin/python scripts/00_data_pipeline.py
Rscript scripts/01_data_pipeline.R
Rscript scripts/02_eda_descriptive_stats.R
Rscript scripts/03_regression_hypothesis_tests.R
```

## Verification standard

- Run the complete Python suite after changing either ingestion system.
- For Indiana historical ingestion, verify unique non-null `source_key`, no PII
  columns, all county-year funnels reconcile, all discovered inputs appear in
  the manifest, and legacy raw five-county counts remain:
  55,025 (2015), 56,236 (2016), 58,531 (2017), 57,678 (2018),
  53,323 (2019), and 53,968 (2020).
- Treat an unexecuted manual or full-data check as skipped, never passed.
- Report generated-output findings separately from tracked source changes.
- Do not hide source-quality attrition. Exact duplicates, conflicting records,
  quarantines, missing archives, and incomplete batches belong in the handoff.

## Development and Git rules

- Inspect source, local changes, and generated-data availability before editing.
- Preserve unrelated user work and implement the smallest coherent change.
- Use `here::here()` for R paths and `pathlib.Path` for Python paths.
- Do not introduce a dependency when the standard library or current
  requirements already provide the needed functionality.
- Do not reformat unrelated working code.
- Use a feature branch for non-trivial changes. Do not commit directly to
  `main`, commit on the user's behalf, push, merge, open a pull request, deploy,
  or alter external services unless explicitly requested.
- Never include academic grading language or references prohibited by
  `CLAUDE.md` in code, documentation, commits, or generated metadata.
