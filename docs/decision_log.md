# Research decision log

## Purpose

Use this append-only log for decisions that change the scientific meaning,
comparability, or reproducibility of the study. It is not a general development
changelog. Record a decision before or when it is implemented, cite the code or
artifact that implements it, and never rewrite an older entry to make a later
choice look pre-specified.

## Entry template

### YYYY-MM-DD — Short decision title

- **Status:** proposed, adopted, superseded, or rejected
- **Scope:** established Indiana, longitudinal Indianapolis, Twin Cities, or
  pooled analysis
- **Decision:** What was chosen.
- **Reason:** Scientific or source-quality rationale.
- **Alternatives considered:** Other defensible options.
- **Consequences:** Changes to estimand, cohort, comparability, interpretation,
  or expected outputs.
- **Implementation:** Code, configuration, tests, and artifacts affected.
- **Sensitivity:** Analysis that evaluates dependence on this choice.
- **Protocol classification:** pre-specified amendment or exploratory change.

## Recorded decisions

### 2026-09-22 — Use constant 2025 dollars for longitudinal price analysis

- **Status:** adopted
- **Scope:** established Indiana extension and longitudinal analyses
- **Decision:** Preserve nominal gross consideration and add a transaction-month
  price normalized with CPI-U to the 2025 annual-average index.
- **Reason:** Nominal prices are not comparable across the 2015–2025 window.
- **Alternatives considered:** Nominal prices only; annual CPI; a regional house-
  price index.
- **Consequences:** Price trends, price tiers, and price-model coefficients must
  identify whether they use nominal or constant dollars. Nominal consideration
  remains the source price and the basis for common eligibility bounds.
- **Implementation:** `scripts/inflation.py`, established Indiana pipeline, and
  generated real-price analysis outputs.
- **Sensitivity:** Report nominal specifications as a secondary comparison.
- **Protocol classification:** adopted before the longitudinal release candidate.

### 2026-09-22 — Flag the missing October 2025 CPI observation

- **Status:** adopted
- **Scope:** 2015–2025 analyses
- **Decision:** Linearly interpolate the interior October 2025 CPI-U gap and flag
  affected rows; never extrapolate endpoint gaps.
- **Reason:** A complete monthly real-price series is needed while retaining a
  visible record of source-series incompleteness.
- **Alternatives considered:** Drop October 2025; use September or November CPI;
  use annual CPI for every month.
- **Consequences:** Results including the affected month must preserve the
  `cpi_imputed` indicator and include a sensitivity excluding it.
- **Implementation:** Inflation utility and external-data adjustment audit.
- **Sensitivity:** Exclude CPI-imputed periods.
- **Protocol classification:** adopted before the longitudinal release candidate.

### 2026-09-22 — Fit longitudinal price tiers on the baseline only

- **Status:** adopted for the prospective longitudinal protocol
- **Scope:** longitudinal Indianapolis, Twin Cities, and pooled analysis
- **Decision:** Fit three metro-specific k-means tiers on eligible 2015–2019 log
  real prices with seed 42 and 50 initializations, then freeze their boundaries.
- **Reason:** Tiers fitted with post-shock outcomes would allow later price
  changes to redefine group membership.
- **Alternatives considered:** Full-window k-means; fixed nominal cutoffs;
  baseline quantiles; parcel-characteristic strata.
- **Consequences:** Existing 2021–2025/full-window tier results remain historical
  or exploratory and cannot serve as the primary longitudinal specification.
  Sale-price-defined tiers still describe completed-sale heterogeneity.
- **Implementation:** Prospective requirement in `docs/analysis_protocol.md`;
  release-candidate code/artifact pending.
- **Sensitivity:** Baseline quantile tiers and, where data permit, stable parcel-
  characteristic groups.
- **Protocol classification:** pre-specified for the release candidate.

### 2026-09-22 — Treat DOM as a secondary measured outcome

- **Status:** adopted
- **Scope:** both metros
- **Decision:** Do not use Redfin county DOM as primary evidence of true
  cumulative marketing time or agent relisting behavior.
- **Reason:** Listing removal, relisting, and local MLS reset rules can make the
  reported metric differ from property-level cumulative days on market, and no
  defensible single national start date for such behavior is established.
- **Alternatives considered:** Treat reported DOM as true time-to-sale; exclude
  DOM entirely; obtain MLS cumulative DOM histories.
- **Consequences:** DOM findings require a measurement caveat and cannot identify
  gaming. A stronger analysis depends on listing histories or MLS CDOM.
- **Implementation:** `docs/dom_measurement_research.md` and the protocol.
- **Sensitivity:** Compare definitions or sources if property-level history
  becomes available.
- **Protocol classification:** adopted before the longitudinal release candidate.

### 2026-09-22 — Require associational language when pre-trends fail

- **Status:** adopted
- **Scope:** metro-specific and pooled models
- **Decision:** A failed joint lead test or substantively nonparallel baseline
  trend prevents causal DiD language for that specification.
- **Reason:** The identifying counterfactual is not supported when treated and
  comparison groups were already evolving differently.
- **Alternatives considered:** Rely on visual inspection; treat pre-trend failure
  as a pipeline error; omit lead results.
- **Consequences:** Results may still describe conditional associations and
  completed-sale heterogeneity, but not causal effects or counterfactual price
  penalties.
- **Implementation:** Econometrics skill, analysis protocol, claim ledger, and
  release checklist.
- **Sensitivity:** Alternative comparison groups, trends, windows, composition
  controls, and design-based approaches must be labeled as such.
- **Protocol classification:** pre-specified for the release candidate.

### 2026-10-16: Accept latest-observed selection for Minnesota revisions

- **Status:** adopted
- **Scope:** Twin Cities and pooled analysis
- **Decision:** Treat the weekly extract archive as the complete revision record
  for this historical study. Select each transaction's latest-observed version
  by extract timestamp, retain every earlier version in the store, and do not
  seek source confirmation of amendment or withdrawal rules.
- **Reason:** The study window (2015–2025) is closed and every weekly archive
  for it is on hand. Reconciliation shows the feed republishes amended CRVs:
  1,637 of 1,549,541 transactions (0.11%) reappear with changed analytical
  content, including 591 Twin Cities sales dated 2015–2025 (0.08% of 699,377).
  The most common changes are property-use rows (345), gross price (142), and
  parcel rows (95); six revisions moved a sale to a different year. A later
  correction that never reached a weekly extract cannot be recovered from any
  source available to this project.
- **Alternatives considered:** Contact the Minnesota Department of Revenue for
  authoritative revision rules; use the first-observed version; exclude every
  revised transaction.
- **Consequences:** Results reflect the latest-observed version. Withdrawals are
  not modeled because the feed carries no deletion signal, and absence from a
  later extract is not treated as deletion. The `revision_conflict` field counts
  only conflicting versions within a single extract and does not measure
  cross-extract revision.
- **Implementation:** `scripts/mn_ecrv/reconcile.py`, the `reconcile` command in
  `scripts/00_mn_ecrv_pipeline.py`, `tests/test_mn_ecrv_reconcile.py`, and
  `outputs/mn/quality/ecrv_revision_summary.csv`.
- **Sensitivity:** Rerun primary Twin Cities estimates excluding the 591 revised
  in-window transactions.
- **Protocol classification:** adopted before the longitudinal release candidate.
