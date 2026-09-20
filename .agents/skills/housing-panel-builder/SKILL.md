---
name: housing-panel-builder
description: Design, implement, or validate the harmonized Indiana-Minnesota housing panel, including transaction contracts, county-month aggregation, ACS/FRED joins, baseline price tiers, and coverage diagnostics. Use after source ingestion is sufficiently reconciled; do not use for raw parser work or regression interpretation.
---

# Housing Panel Builder

Read `AGENTS.md` and [references/panel-contract.md](references/panel-contract.md).
Inspect actual normalized outputs and ingestion audits before assuming either state
is ready. Stop and report a source-readiness blocker when required periods or
eligibility fields are absent; do not turn missing source coverage into zero sales.

## Workflow

1. State the intended panel grain, period, eligible cohort, outcome variables,
   and whether recent data are provisional.
2. Build an explicit state-to-canonical mapping before concatenating records.
   Preserve source identifiers and eligibility provenance.
3. Validate one transaction per source key before aggregation. Aggregate child
   records separately and join only one-row-per-key summaries.
4. Assign geography from versioned county crosswalks. Keep `metro` and
   `tier_type` conceptually separate from county names.
5. Join time-varying external series on asserted keys. Report unmatched and
   duplicated join keys before calculating derived measures.
6. Fit or freeze baseline price tiers only from the declared 2015–2019 baseline
   within each metro. Do not refit tiers on post-treatment outcomes.
7. Materialize a panel-balance/coverage report alongside the panel and verify
   that every zero is supported by observed source coverage.

Keep panel construction separate from model estimation. The handoff must specify
the panel grain, keys, source snapshot/manifest, row counts, missingness policy,
tier boundaries, joins, and checks actually run.
