# Methodology

This document describes the Indianapolis workflow for 2015 through 2025. The
analysis combines a 660-row county-month panel with 438,427 deed records after
the upstream nominal price floor of $50,000 and ceiling of $15,000,000. The
current models are associational: the 2022 rate increase provides timing, but
the expanded pre-period does not establish the parallel-trends assumption
needed to describe the estimates as causal.

## Identification Strategy

The rate lock-in gap (`rate_gap`) is the monthly 30-year fixed mortgage rate
minus a 3.0% baseline. `post` begins when that gap reaches two percentage
points. Hamilton, Boone, Hendricks, and Johnson form the suburban comparison
group and Marion is the urban core. The triple interaction describes the
post-2022 suburban move-up differential; it does not, by itself, isolate a
causal effect of mortgage rates.

## Parallel Trends Verification

Figure 8 displays the full 2015–May 2022 pre-period in constant 2025 dollars.
The chart is diagnostic evidence only and does not impose a parallel-trends
conclusion. Formal lead tests and small-cluster inference are required before
causal DiD language is appropriate.

## Price Tier Segmentation

The source consideration remains in nominal `sale_price`. Monthly FRED
`CPIAUCSL` converts it to `sale_price_2025` using the 2025 annual-average CPI-U
as the base. October 2025 is linearly interpolated and flagged. K-means (k = 4)
is fitted on 2021–2025 `sale_price_2025`; the two highest clusters are combined.
The real-dollar boundaries are approximately $407,000 and $1.097 million.

## Panel Construction

The panel covers five counties over 132 months (January 2015–December 2025),
producing 660 county-month observations. Redfin prices are also converted to
constant 2025 dollars. Redfin DOM is reported listing duration, not verified
property-level cumulative marketing time; see
[`dom_measurement_research.md`](dom_measurement_research.md).

## Model Specifications

**Days-on-market models** (Table 5) use the county-month panel (N = 300) with median DOM (untransformed) as the outcome. A baseline specification regresses median DOM on `rate_gap` alone (R²adj = 0.296). A controlled specification adds `price_segment`, `geography`, `median_hhi`, `population`, and `months_of_supply`. An interaction specification swaps the `rate_gap` main effect for `rate_gap × price_segment` to detect differential rate sensitivity by tier. A two-way fixed-effects specification adds county and year fixed effects to the interaction model. All panel models use OLS with HC1 heteroskedasticity-robust standard errors.

**Price models** (Table 6) use individual deed records (N = 269,992 after model filters) with log(sale_price) as the outcome. Assessed value was excluded from the pipeline due to measurement noise introduced by county-level appraisal timing lags; the valid_trending filter was dropped to retain full transaction coverage. The baseline specification (`m_price_base`) regresses log price on `rate_gap`, `price_segment`, `geography` (suburb indicator), `median_hhi`, and `affordability_ratio`. The primary interaction specification (`m_price_interact`) replaces the `rate_gap` main effect with `rate_gap × price_segment`, which generates `rate_gap × move_up` and `rate_gap × luxury` interactions so rate sensitivity can vary by tier. A two-way fixed-effects variant (`m_price_fe`) adds county and year fixed effects to the interaction model. All price models use OLS with HC1 robust standard errors via the `sandwich` and `lmtest` packages in R.

**DiD models** (Table 7) estimate the treatment effect on both price and transaction volume. The price DiD triple-interaction specification (`m_did_price_triple`) regresses log(sale_price) on `treated × post × price_segment` (a full three-way expansion that includes all main effects and pairwise interactions) with controls for `median_hhi` and `affordability_ratio` plus county and year fixed effects. Simpler companion specifications (`m_did_price_simple` and `m_did_price_fe`) are also reported in Table 7. The volume DiD (`m_did_volume_triple`) uses monthly transaction counts at the county-segment level (N = 867) and includes controls for `median_hhi`, `population`, and county and year fixed effects. The triple-interaction coefficient is the primary causal estimand: a negative sign on Suburb × Post × Move-up indicates that suburban move-up properties bear a disproportionate price or volume penalty relative to Marion County after the rate shock.

## Hypothesis Tests

Welch two-sample t-tests (Table 2) compare mean log(sale_price) between the pre-shock period (rate_gap < 2.0, N_pre = 82,288) and the post-shock period (rate_gap ≥ 2.0, N_post = 187,704), separately for each price segment and for each geography. The post indicator is inherited from `panel_data.rds` via the `rate_lookup` join in `scripts/03_regression_hypothesis_tests.R` and reflects the rate-gap threshold (rate_gap ≥ 2.0 percentage points above the 2021 baseline), which is first crossed in mid-2022. Welch's test is used in preference to a pooled-variance t-test because unequal group variances are expected given the different segment compositions and sample sizes across periods. The null hypothesis in all cases is that the pre-shock and post-shock population means are equal; the alternative is two-tailed.

## Correlation Analysis

Pearson correlations are computed on the post-filter deed record dataset (N = 269,992; restricted to complete cases of the seven variables) among log(sale_price), rate_gap, mortgage rate, median HHI, affordability ratio, estimated monthly payment, and population (Table 3). A separate ZIP-code-level correlation between median HHI and median sale price is computed on 82 ZIP codes (Figure 10; values stored in `data/processed/fig10_correlation_stats.rds`), where aggregation to ZIP codes eliminates idiosyncratic transaction-level noise (fixer-uppers, estate sales, income-stretching) and reveals the income-price relationship more clearly (r = 0.797 at ZIP level versus r = 0.43 at transaction level).

## Software and Reproducibility

All R scripts use `here::here()` for file path construction and `pacman::p_load()` for package management. Python scripts use `pathlib.Path` anchored to the repository root. The pipeline is executed in order: `00_data_pipeline.py` processes SDF deed records and produces ZIP-level HHI; `01_data_pipeline.R` builds the county-month panel; `02_eda_descriptive_stats.R` produces descriptive figures and tables; `03_regression_hypothesis_tests.R` estimates all models and generates inferential output. `set.seed()` is fixed where applicable. The FRED and Census API calls are cached after the first successful pull; subsequent runs use cached files without re-querying the APIs.
