# Research claim ledger

## Purpose and use

This ledger is the control point between generated artifacts and prose. One row
represents one externally visible quantitative or causal claim. Populate it
from release-candidate artifacts; do not copy numbers from memory or from an
older README. A claim is publishable only when its source snapshot, model,
units, uncertainty, sample, and generating code reproduce.

Status values:

- `PENDING`: proposed claim without a completed release audit.
- `VERIFIED`: exactly reproduced from the named current artifact.
- `QUALIFIED`: reproduced but requires the limitation in the notes.
- `REJECTED`: not supported, stale, or inconsistent with the protocol.
- `SUPERSEDED`: historically reported but replaced by a newer specification.

## Headline claim ledger

| ID | Proposed or existing claim | Study/sample | Estimand or statistic | Artifact and code | Status | Release note |
|---|---|---|---|---|---|---|
| C001 | Move-up prices were 4.5 times more sensitive to the rate gap than entry-tier prices | Established Indianapolis 2021–2025, nominal-price specification | Ratio of model-derived segment slopes | Existing README/findings; `scripts/03_regression_hypothesis_tests.R` | SUPERSEDED | Do not carry into the longitudinal paper as an invariant or benchmark. Re-estimate with real prices and release-candidate specification. |
| C002 | Real-price rerun produces an approximately 2.1x move-up-to-entry sensitivity ratio | Expanded established Indiana output, 2015–2025 records with current tier implementation | Ratio of transformed interaction slopes | `outputs/indiana/analysis_2015_2025_real/`; generating R scripts | PENDING | Exploratory until tiers are trained only on 2015–2019 and uncertainty for the ratio is reported. |
| C003 | Mortgage-rate changes disproportionately suppress suburban move-up prices or volumes | Longitudinal Indianapolis | Triple interaction and required linear combinations | Pending release-candidate model table | PENDING | Use associational language unless pre-trends and identification checks support a causal interpretation. |
| C004 | The Indianapolis result generalizes to the Twin Cities | Pooled 2015–2025 analysis | Metro-specific combinations and four-way difference | Pending | PENDING | Requires both metro pipelines and models to pass independent gates first. |
| C005 | DOM increased because sellers or agents gamed relisting rules | Redfin county-month listing data | Not identified by present data | `docs/dom_measurement_research.md` | REJECTED | Current DOM is a reported listing-duration measure; the timing and direction of reset bias are not identified. |

The rows above document known high-risk claims. Replace `PENDING` entries with
fully specified results only after the release-candidate run; retain rejected or
superseded rows for provenance.

## Required fields for new claims

Copy this row for each manuscript, abstract, README, table-caption, or figure-
caption claim:

| ID | Exact claim text | Destination | State/metro | Cohort | Window | Outcome and units | Exposure and units | Model/statistic | Estimate | SE/CI/p-value | N/cells/clusters | Panel/data hash | Artifact path/table cell | Generating script/commit | Status | Required qualification |
|---|---|---|---|---|---|---|---|---|---:|---|---|---|---|---|---|---|
| CXXX | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Pending | PENDING | Pending |

## Audit rules

1. Record the exact text readers will see, not a paraphrase.
2. Separate raw descriptive statistics, regression coefficients, transformed
   effects, linear combinations, scenario calculations, and causal estimates.
3. State whether rate units are percentage points or proportions and whether
   prices are nominal or constant 2025 dollars.
4. For nonlinear models, store the reported contrast or prediction and the code
   that computes it—not only the underlying interaction coefficient.
5. Record all sample dimensions relevant to the claim, including counties,
   months, transactions or cells, and clusters.
6. Link to a machine-readable table whenever available; an image alone is not
   adequate provenance.
7. Recheck every verified row after any change to ingestion, eligibility, CPI,
   tiering, joins, model formula, inference, or analysis window.
8. If a claim cannot be reproduced exactly, mark it `REJECTED` or `PENDING`;
   never adjust prose merely to resemble a stale output.

## Release sign-off

| Review | Reviewer/date | Result | Notes |
|---|---|---|---|
| Data lineage | Pending | Not reviewed | |
| Statistical specification | Pending | Not reviewed | |
| Tables and figures | Pending | Not reviewed | |
| Narrative consistency | Pending | Not reviewed | |
| Reproducibility from clean environment | Pending | Not reviewed | |
| Final release decision | Pending | Not ready | See `docs/journal_readiness_roadmap.md`. |
