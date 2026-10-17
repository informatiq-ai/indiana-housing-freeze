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

### 2026-10-16: Count each Indiana sale once in the established analysis

- **Status:** adopted
- **Scope:** established 2021–2025 Indiana squeeze analysis and its outputs
- **Decision:** Keep one row per `SDF_ID` in `sdf_indiana.csv`, taking the first
  row in file order, and refit the k-means price segments on the distinct sales.
- **Reason:** The STATS Indiana `SALEDISC` files repeat an `SDF_ID` when one sale
  is filed on several forms. The copies differ in form totals, fees, and
  validation fields; 50,265 of the 50,345 repeated sales carry the same date and
  price on every copy. The published sample counted every row, so 269,992 rows
  held 201,754 sales. The repeats fell mostly on the suburbs: 50.7% of Hamilton
  rows, 30.0% of Hendricks, 18.7% of Johnson, 7.4% of Boone, and 2.4% of Marion
  were copies. No `SDF_ID` repeats across annual files.
- **Consequences:** The refit breaks are $363,424 and $1,047,851 (previously
  $379,523 and $1,048,090). The published conclusions hold and strengthen. The
  move-up rate slope is −5.0% per percentage point against −0.9% for entry, a
  5.6× multiplier (previously −4.9%, −1.1%, and 4.5×). The suburb × post ×
  move-up price interaction is +17.2% (previously +16.2%), and the move-up
  volume interaction is −340 sales per month with p < 0.001 (previously −176,
  p = 0.05). The README and the regenerated figures and tables report the
  corrected values.
- **Implementation:** `scripts/00_data_pipeline.py`, which also writes
  `data/processed/price_segment_breaks_indiana.json` so the Redfin panel uses
  the same breaks.
- **Protocol classification:** correction to the established analysis.

### 2026-10-16: Restore the published method for the established squeeze analysis

- **Status:** adopted
- **Scope:** established 2021–2025 squeeze scripts (`00`–`03`); supersedes the
  2026-09-22 constant-dollar decision for that analysis only
- **Decision:** Run the established scripts with the published method: the
  2021–2025 window, nominal sale prices, k-means segments fit on nominal 2021–2025
  prices, and the published models. Indiana and the Twin Cities run from the same
  scripts through `scripts/squeeze_study.R`, which changes only geography, input
  files, and source labels.
- **Reason:** The constant-dollar revision also extended the window to
  2015–2025 and refit the segments, so the scripts no longer reproduced the
  published results. Rerunning the published scripts on the published input
  reproduced them exactly, which establishes the published method as the
  baseline for the cross-metro replication.
- **Alternatives considered:** Keep the constant-dollar 2015–2025 version as the
  established analysis; keep both behind a setting.
- **Consequences:** Constant-dollar 2015–2025 prices remain in the longitudinal
  workflow. The constant-dollar version of the established scripts remains in
  the Git history at commit `08d636f`.
- **Implementation:** `scripts/01_data_pipeline.R`,
  `scripts/02_eda_descriptive_stats.R`, `scripts/03_regression_hypothesis_tests.R`,
  `scripts/squeeze_study.R`, and `tests/test_squeeze_study.R`.
- **Protocol classification:** correction to the established analysis.

### 2026-10-16: Refit the squeeze price segments on Twin Cities sales

- **Status:** adopted
- **Scope:** Twin Cities replication of the established 2021–2025 squeeze analysis
- **Decision:** Fit the Twin Cities entry, move-up, and luxury segments with the
  published Indiana method rather than reuse Indiana's dollar breaks: k-means
  with four clusters on nominal sale price, seed 42, ten initializations,
  2021–2025 sales at or below $15,000,000, and the top two clusters collapsed
  into luxury. The fitted breaks are $463,375 and $1,042,466, against $363,424
  and $1,047,851 in Indiana.
- **Reason:** Twin Cities prices sit higher than Indianapolis prices, so the
  Indiana entry break would place much of the Twin Cities middle market in the
  move-up segment. Refitting keeps "move-up" defined as the middle of each
  metro's own market.
- **Sample:** The Twin Cities counterpart of Indiana's residential, arm's-length
  rules keeps one- to three-family dwellings, condos, cooperatives, townhouses,
  mobile and manufactured homes, and cabins. It excludes vacant land, 4-unit
  apartments, care facilities, mobile home parks, garages, and unspecified or
  rental-investment uses, which Indiana classes as commercial or does not
  report as residential. Of 292,355 Twin Cities eCRVs dated 2021–2025, 274,469
  pass the arm's-length and price rules, 244,486 have only listed dwelling
  uses, and 242,799 carry a valid property ZIP, matching Indiana's ZIP
  requirement. Every eCRV has its own identifier, so the sample has no
  repeated filings.
- **Alternatives considered:** Reuse Indiana's breaks; fit on constant-2025-dollar
  prices (`--price-basis real`), which yields $500,438 and $1,128,592.
- **Consequences:** Segment counts differ by definition across metros, so
  cross-metro comparisons are of each segment's relative response, not of a
  common dollar band.
- **Implementation:** `scripts/00_mn_data_pipeline.py`,
  `scripts/mn_squeeze/sample.py`, `scripts/mn_squeeze/external.py`,
  `tests/test_mn_squeeze_sample.py`, and
  `outputs/mn/squeeze/price_segment_breaks_nominal.json`.
- **Sensitivity:** `price_segment_indiana_breaks` carries the published Indiana
  nominal breaks on every sale.
- **Protocol classification:** exploratory replication outside the
  longitudinal release-candidate protocol.

### 2026-10-16: Compare city-based Twin Cities cores with Marion County

- **Status:** adopted
- **Scope:** Twin Cities replication of the established squeeze analysis
- **Decision:** Report the published headline models on three city-based
  geographies alongside the county geography: St. Paul against the five
  suburban counties, Minneapolis and St. Paul against the five suburban
  counties, and both cities against the suburban counties and the Hennepin and
  Ramsey balances. Minneapolis is excluded where St. Paul is the only core.
- **Reason:** Marion County is consolidated with the city of Indianapolis and
  sits far below its suburbs in income ($63,450). Hennepin ($96,339) falls
  inside the suburban range, and about 70% of its eligible sales lie outside
  Minneapolis. St. Paul ($73,055) is the closest counterpart to Marion.
- **Consequences:** Cities use their own ACS 2023 income and population. A
  county balance uses its parent county's median income and the county
  population minus the city population. The comparison script reproduces the
  Indiana results of `03_regression_hypothesis_tests.R` before it reports any
  Twin Cities geography.
- **Implementation:** `scripts/mn_squeeze/core_cities.py`,
  `scripts/mn_squeeze/core_city_models.R`, and
  `outputs/mn/squeeze/core_city_comparison.csv`.
- **Protocol classification:** exploratory replication outside the
  longitudinal release-candidate protocol.

### 2026-10-17: Test the segment rate slopes in the core-city comparison

- **Status:** adopted
- **Scope:** Twin Cities replication of the established squeeze analysis
- **Decision:** Report p-values for the entry slope, the move-up slope, and the
  move-up minus entry gap from the published price interaction model, each
  under HC1 errors and under errors clustered by the 60 sale months. The
  move-up slope is the sum of the rate gap and its move-up interaction, so it
  is tested as that sum.
- **Reason:** The squeeze multiplier is a ratio of two slopes and carries no
  test of its own. Sales in the same month share one mortgage rate, so HC1
  errors treat as independent the variation that the rate gap cannot supply.
- **Consequences:** The move-up slope and the gap are significant in Indiana
  and every Twin Cities geography under both errors (p < 0.001). Indiana's
  entry slope is not significant under month clustering (p = 0.097), so the
  Indiana multiplier is imprecise even though the gap it summarizes is not.
  Existing comparison columns are unchanged.
- **Implementation:** `scripts/mn_squeeze/core_city_models.R`,
  `tests/test_core_city_models.R`, and
  `outputs/mn/squeeze/core_city_comparison.csv`.
- **Protocol classification:** exploratory replication outside the
  longitudinal release-candidate protocol.
