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

### 2026-10-16: Add a Minneapolis/St. Paul core-city sensitivity

- **Status:** adopted
- **Scope:** Twin Cities and pooled analysis
- **Decision:** Keep the county definition primary and add the
  `msp_core_city_definition` sensitivity, which treats Minneapolis and St. Paul
  as the urban core and moves the Hennepin and Ramsey balances to the suburban
  collar. Place each sale with the eCRV property city code: `8800` in Hennepin
  for Minneapolis and `8900` in Ramsey for St. Paul. Exclude sales marked
  `MIXED` or `UNKNOWN` and report their counts.
- **Reason:** The county definition places suburbs such as Bloomington and
  Roseville in the urban core. The eCRV city field is a county-specific code
  with no name, so the codes were validated against ZIP codes: 94.8% of
  Hennepin addresses coded `8800` fall in Minneapolis ZIPs, and 97.6% of Ramsey
  addresses coded `8900` fall in St. Paul ZIPs. The remainder fall in ZIPs that
  cross the city line. The coded share is stable from 2015 through 2025, with
  Minneapolis at 29–31% of Hennepin sales and St. Paul at 53–56% of Ramsey sales.
- **Classification:** Hennepin has 82,990 core-city sales, 187,793 balance sales,
  7,798 unknown, and 8 mixed. Ramsey has 54,745 core-city sales, 43,760 balance
  sales, 2,440 unknown, and 7 mixed. These counts cover all 2015–2025
  transactions. The exclusion removes 10,253 of 379,541 Hennepin and Ramsey
  transactions (2.7%); research-eligible counts are reported in
  `sensitivity_availability.csv` after the longitudinal run.
- **Unknown sales:** The 10,238 unknown sales carry no usable property address.
  Of these, 336 have no address record, and the other 9,904 address rows have
  blank street, city, and ZIP fields in the raw store. No ZIP or geocoding
  fallback is possible. Unknown sales are concentrated in 2015–2018 (1,280 to
  2,076 a year) and fall to 181 in 2025.
- **Alternatives considered:** ZIP-based assignment, which misplaces sales in
  ZIPs that cross the city line; a city-level primary definition, which would
  change the pre-specified geography.
- **Consequences:** The sensitivity estimates on nine geographic units instead
  of seven counties. Split units carry their parent county's ACS income because
  the panel does not join city-level ACS estimates.
- **Follow-up:** Unknown sales still carry parcel IDs. Joining them to current
  Hennepin and Ramsey parcel datasets, which list each parcel's city, could
  recover most of them. Parcels split or renumbered since sale would not match
  and would be counted. Pursue this if the core-city estimates prove sensitive
  to the 2015–2018 coverage gap.
- **Implementation:** `scripts/mn_ecrv/store.py` (address export without street
  lines), `classify_core_city` in `scripts/research/longitudinal.py`,
  `msp_core_city_units` in `scripts/research/03_estimate_models.R`,
  `outputs/research/quality/msp_core_city_classification.csv`, and
  `outputs/research/quality/msp_core_city_zip_concordance.csv`.
- **Protocol classification:** pre-specified sensitivity, added before the
  longitudinal release candidate.
