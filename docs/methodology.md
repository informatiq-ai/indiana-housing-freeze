# Methodology

This document describes the identification strategy, data construction, model specifications, and statistical tests used to examine mortgage rate lock-in effects on the Indianapolis mid-luxury housing market from 2021 through 2025. The analysis combines a county-month panel (N = 300) for time-series models with individual deed records (N = 271,047) for price and volume models, relying on a Difference-in-Differences (DiD) design that treats the 2022 Federal Reserve tightening cycle as a quasi-natural experiment.

## Identification Strategy

The DiD design exploits the abrupt rise in the 30-year fixed mortgage rate beginning in early 2022 as an exogenous shock to housing demand. The rate lock-in gap (`rate_gap`) is defined as the current 30-year fixed mortgage rate minus the 2021 baseline of 3.0 percentage points. The post-shock indicator activates when `rate_gap >= 2.0`, corresponding to sustained rates above 5.0%. Treatment is assigned geographically: the four suburban counties (Hamilton, Boone, Hendricks, Johnson) constitute the treated group, and Marion County (Indianapolis proper) serves as the control. This assignment reflects the theoretical mechanism -- suburban buyers in the mid-luxury tier face payment shock when locking into a rate above their existing mortgage, while Marion County's structural income constraint ($63,450 median HHI) limits sustained mid-luxury demand regardless of rate conditions. The triple interaction (Suburb × Post × Mid-luxury) isolates the differential rate-shock effect on suburban mid-luxury properties net of geography, time, and segment main effects.

## Parallel Trends Verification

The identifying assumption requires that Marion County and suburban sale prices would have followed parallel trends in the absence of the rate shock. Figure 7 documents this graphically: mean sale prices by geography on a log scale track together at similar growth rates from January 2021 through early 2022, then diverge following the Federal Reserve's tightening cycle. The pre-shock period (2021 through `rate_gap < 2.0`) shows no statistically distinguishable trend difference across geographies. Post-shock divergence is concentrated in the mid-luxury segment, consistent with the rate payment mechanism.

## Price Tier Segmentation

Price tiers are derived from k-means clustering (k = 4) applied to log(sale_price) on the full SDF deed record population. K-means is preferred over percentile-based cuts because it identifies natural discontinuities in the price distribution rather than imposing arbitrary quantile boundaries. The two highest clusters are collapsed into a single luxury tier due to thin ultra-luxury sample size (n = 48 ultra-luxury versus 3,547 luxury), which would produce unstable estimates in a separate stratum. The resulting segmentation places the entry/mid-luxury boundary at approximately $388,000 and the mid-luxury/luxury boundary at approximately $1,040,000. These breakpoints are validated against expected values (within a $50,000 tolerance) on each pipeline run to detect data-driven drift across annual refreshes.

## Panel Construction

The county-month panel aggregates five counties over 60 months (January 2021 through December 2025), producing 300 county-month observations. Redfin county market tracker data supplies monthly median sale price, days on market (DOM), sale-to-list ratio, months of supply, and seller stress indicators. FRED MORTGAGE30US supplies the monthly mortgage rate series. Census ACS 2023 5-year estimates supply county-level median household income and population. Per-capita transaction counts by segment are derived from STATS Indiana SDF deed records, grouped to the county-month level. The `did` interaction term is the product of `treated` (suburb geography indicator) and `post` (rate shock indicator), constructed prior to merging into the panel.

## Model Specifications

**Days-on-market models** (Table 2) use the county-month panel (N = 300) with log-transformed median DOM as the outcome. A baseline specification regresses DOM on `rate_gap` alone (R²adj = 0.296). A controlled specification adds `months_of_supply`, county-level `median_hhi`, and `population`. An interaction specification adds `rate_gap × mid_luxury_share` to detect differential rate sensitivity by segment composition. A two-way fixed-effects specification adds county and year fixed effects to the controlled model. All panel models use OLS with HC1 heteroskedasticity-robust standard errors.

**Price models** (Table 3) use individual deed records (N = 271,047) with log(sale_price) as the outcome. A baseline specification regresses log price on `rate_gap`, suburb indicator, and `affordability_ratio`. The primary interaction specification adds `rate_gap × mid_luxury` and `rate_gap × luxury` indicators to allow rate sensitivity to vary by tier. A two-way fixed-effects variant adds county and year fixed effects. All price models use OLS with HC1 robust standard errors via the `sandwich` and `lmtest` packages in R.

**DiD models** (Table 4) estimate the treatment effect on both price and transaction volume. The price DiD (triple interaction) specification regresses log(sale_price) on suburb, post, mid-luxury and luxury tier indicators, all pairwise interactions, the triple interaction Suburb × Post × Mid-luxury, and controls for median HHI, population, and affordability ratio. The volume DiD uses county-month-segment transaction counts (N = 837) as the outcome. Fixed-effects variants replace the geography and year main effects with county and year fixed effects. The triple interaction coefficient is the primary causal estimand: a negative sign on Suburb × Post × Mid-luxury indicates that suburban mid-luxury properties bear a disproportionate price or volume penalty relative to Marion County after the rate shock.

## Hypothesis Tests

Welch two-sample t-tests (Table 5) compare mean log(sale_price) between the pre-shock period (2021, N_pre = 61,779) and the post-shock period (2022--2025, N_post = 136,628), separately for each price segment and geography. Welch's test is used in preference to a pooled-variance t-test because unequal group variances are expected given the different segment compositions and sample sizes across periods. The null hypothesis in all cases is that the pre-shock and post-shock population means are equal; the alternative is two-tailed.

## Correlation Analysis

Pearson correlations are computed on the full deed record population (N = 271,047) among log(sale_price), rate_gap, mortgage rate, median HHI, affordability ratio, estimated monthly payment, and population (Table 6). A separate ZIP-code-level correlation between median HHI and median sale price is computed on approximately 80 ZIP codes (Figure 12), where aggregation to ZIP codes eliminates idiosyncratic transaction-level noise (fixer-uppers, estate sales, income-stretching) and reveals the income-price relationship more clearly (r = 0.805 at ZIP level versus r = 0.56 at transaction level).

## Software and Reproducibility

All R scripts use `here::here()` for file path construction and `pacman::p_load()` for package management. Python scripts use `pathlib.Path` anchored to the repository root. The pipeline is executed in order: `00_data_pipeline.py` processes SDF deed records and produces ZIP-level HHI; `01_data_pipeline.R` builds the county-month panel; `02_eda_descriptive_stats.R` produces descriptive figures and tables; `03_regression_hypothesis_tests.R` estimates all models and generates inferential output. `set.seed()` is fixed where applicable. The FRED and Census API calls are cached after the first successful pull; subsequent runs use cached files without re-querying the APIs.
