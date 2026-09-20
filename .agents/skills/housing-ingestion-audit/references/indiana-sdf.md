# Indiana SDF ingestion

## Routing

- `scripts/00_data_pipeline.py` is the established enriched 2021–2025 analysis
  path and owns `data/processed/sdf_indiana.csv`.
- `scripts/00_indiana_sdf_pipeline.py` is the independent longitudinal
  normalizer and owns `data/processed/indiana_sdf_history.csv` plus
  `outputs/indiana/quality/`.
- Shared adapter behavior belongs in `scripts/indiana_sdf/`; do not import the
  established enriched script because it executes work at import time.

## Source eras

- Legacy root files `YYYY.txt`: header-dispatched pipe-delimited data,
  Windows-1252-compatible, gross sale price in dollars, embedded parcel fields.
- Modern `SALEDISCYYYY.txt` plus `SALEPARCELYYYY.txt`: UTF-16 tab-delimited,
  monetary transaction fields in cents, one-to-many parcel rows.
- Modern transaction files require the matching parcel file. Missing partners or
  unsupported headers are hard source errors.

## Invariants

- Counties: Boone `06`, Hamilton `29`, Hendricks `32`, Johnson `41`, Marion `49`.
- One normalized row per nonconflicting `source_key`.
- Collapse analytically identical duplicates. Quarantine every row in a
  conflicting duplicate group because the extracts provide no authoritative
  revision timestamp.
- Aggregate parcel fields before joining to transaction facts.
- Keep `eligible_current_study` and `eligible_strict_comparable` separate.
- The common analytical bounds are an in-file-year sale date and
  `$50,000 < gross_sale_price <= $15,000,000`.
- Gross price is canonical; do not subtract personal property or concessions
  until cross-era units and meanings are validated.

## Commands and acceptance evidence

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/00_indiana_sdf_pipeline.py --input-dir .
.venv/bin/python .agents/skills/housing-ingestion-audit/scripts/summarize_ingestion.py \
  --repo-root . --state indiana
```

Expected five-county legacy raw counts are 55,025 (2015), 56,236 (2016),
58,531 (2017), 57,678 (2018), 53,323 (2019), and 53,968 (2020). A valid run also
requires unique non-null output keys, no party columns, exact funnel
reconciliation, and manifest coverage for every discovered input.
