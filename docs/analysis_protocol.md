# Longitudinal housing analysis protocol

## Status and change control

This document is the prospective contract for the 2015–2025 Indianapolis and
Twin Cities analysis. It separates primary choices from exploratory work. It
does not retroactively validate existing results. Before the first release-
candidate run, record a protocol version, date, Git commit, input-manifest
hashes, and analysis-snapshot hashes below.

| Field | Release-candidate value |
|---|---|
| Protocol version | Pending |
| Freeze date | Pending |
| Git commit | Pending |
| Indiana manifest hash | Pending |
| Minnesota manifest hash | Pending |
| Panel snapshot hash | Pending |

After the freeze, record substantive changes in `docs/decision_log.md`. Do not
overwrite the original choice. Mark unplanned analyses as exploratory.

## Research questions

1. How is monthly mortgage-rate exposure associated with completed-sale prices
   and transaction volumes across fixed price tiers and suburban versus urban-
   core counties within each metro?
2. Does the Indianapolis differential reproduce in the Twin Cities?
3. How did real prices, transaction volume, household income, and modeled
   payment burden evolve across the baseline, pandemic/low-rate, and high-rate
   regimes?

## Study population and periods

- Analysis window: January 2015 through December 2025.
- `BASELINE`: 2015–2019.
- `PANDEMIC_LOW_RATE`: 2020–2021.
- `HIGH_RATE_LOCK_IN`: 2022–2025.
- Indianapolis: Marion urban core; Boone, Hamilton, Hendricks, and Johnson
  suburban collar.
- Twin Cities: Hennepin and Ramsey urban core; Anoka, Carver, Dakota, Scott, and
  Washington suburban collar.
- The Twin Cities definition is the seven-county planning region, not the full
  federal metropolitan statistical area.
- Partial 2026 records may remain in ingestion stores but cannot enter models.

Indiana's primary transaction cohort is `eligible_current_study == true`, with
every observed parcel classified 510–515. Its strict-comparable cohort is a
sensitivity. Minnesota's primary and strict rules must follow the harmonized
single-family and explicit nonmarket-flag definitions in
`docs/longitudinal_research.md`. Both states require an in-window date and
`$50,000 < gross_price <= $15,000,000`.

## Exposure and price measurement

- Primary rate exposure is monthly `MORTGAGE30US` minus 3.0%, expressed in
  percentage points.
- Primary price is gross reported sale price converted to constant 2025 dollars
  using monthly CPI-U and the 2025 annual-average index.
- Nominal price remains the basis for the common source-level price bounds and
  mortgage-payment scenario at the transaction date.
- Minnesota adjusted price is a sensitivity only where all required source
  components and their units are validated.
- CPI interpolation and ACS carry-forward are never silent; affected rows carry
  flags and are excluded in designated sensitivities.

## Fixed price tiers

Fit tiers independently within each metro using eligible single-family sales
from 2015–2019:

1. Transform constant-2025-dollar sale price with the natural logarithm.
2. Fit three-cluster k-means with seed 42 and 50 initializations.
3. Order centers and label them `ENTRY`, `MOVE_UP_MID_LUXURY`, and `HIGH_END`.
4. Define boundaries at the midpoint between adjacent ordered centers in log
   space and convert them back to 2025 dollars.
5. Freeze those boundaries for 2020–2025.
6. Persist the training cohort count and hash, centers, boundaries, seed,
   initializations, CPI base, implementation version, and fit date.

Because observed sale price assigns a transaction to a tier, tier-specific
price estimates remain completed-sale heterogeneity. A stronger causal subgroup
claim requires a price-independent, pre-exposure classification such as stable
parcel characteristics or prior assessed/value history.

## Panel contracts

### Transaction panel

- Grain: metro × county × sale month × fixed price tier.
- Complete grid: January 2015 through December 2025.
- Outcomes: eligible transaction count; median and selected quantiles of real
  gross price; available real adjusted price; price-to-income; modeled mortgage-
  payment-to-income.
- Insert zero counts only when the applicable source-coverage audit proves that
  the county-month was observed. Otherwise retain missingness.

### Listing panel

- Grain: metro × county × month.
- Source restriction: Redfin single-family, one-month county observations.
- Outcomes: median days on market, inventory, months of supply, sale-to-list
  ratio, and price-drop share.
- Preserve missing source periods as missing. Do not infer tier-level listing
  metrics from county-level data.
- Treat DOM as reported listing duration and a secondary outcome because
  relisting and reset rules can obscure cumulative market time.

### External joins

- FRED monthly `MORTGAGE30US` and CPI-U.
- ACS five-year county median household income, population, households,
  estimate vintage, and margins of error.
- Use the latest available ACS vintage for 2025 only with an explicit carried-
  forward flag; run a sensitivity excluding 2025/provisional income.
- Assert uniqueness before every join and report every unmatched key.

## Primary estimands and models

Estimate Indianapolis and Twin Cities separately before pooling. The headline
estimand is the differential association of a one-percentage-point increase in
the mortgage-rate gap with a fixed price tier in suburban versus urban-core
counties.

### Price

Model log monthly median real sale price with the full estimable hierarchy of:

`rate_gap_pp × fixed_price_tier × suburban`

Include county and calendar-month fixed effects. Calendar-month effects absorb
the national rate main effect. Report coefficients, covariance choice, sample
counts, and transformed percentage effects as `100 × (exp(beta) - 1)`.

### Transaction volume

Use a Poisson fixed-effects count model with log households as an offset, the
same interaction hierarchy, and county and calendar-month fixed effects. Report
interpretable linear combinations, incidence-rate ratios, and predicted counts
or rates. Do not interpret one nonlinear interaction coefficient in isolation
as the full treatment effect.

### Listing and affordability outcomes

Estimate the pre-specified county-month outcomes using the same geography and
rate logic where their grain permits it. Income is an annual covariate and a
descriptive capacity measure, not an independently identified causal channel.

### Uncertainty

- Cluster conventional uncertainty by county and disclose the cluster count.
- Add a few-cluster procedure appropriate to the estimator and design, such as
  wild-cluster bootstrap for linear specifications.
- Do not select the inferential method based on which one produces statistical
  significance.

## Dynamic and identification checks

- Estimate quarterly suburban-versus-core event studies around the 2022 rate
  shock; define and record the exact shock quarter before estimation.
- Use the final pre-shock quarter as the reference.
- Report all leads and lags, confidence intervals, cell counts, and a joint test
  of pre-shock leads.
- Show 2015–2019 baseline trends separately from the 2020–2021 transition.
- Examine differential source coverage, reporting lag, and transaction/property
  composition around the event.
- A failed or imprecise pre-trend test requires associational language and may
  rule out the proposed causal interpretation. It is not a software failure.

## Required sensitivity matrix

- Indiana current-study versus strict-comparable cohort.
- Minnesota recovered records included versus excluded.
- Gross versus available adjusted Minnesota price.
- Zero-, three-, and six-month rate lags.
- Inclusion versus exclusion of the 2020–2021 transition.
- K-means versus baseline quantile tiers.
- Alternative price bounds.
- Schema-era indicators and the Indiana pre/post-2021 source discontinuity.
- County leave-one-out estimates, emphasizing Hamilton and Hennepin; mark a
  result inestimable when removal eliminates the only comparison group.
- Exclusion of provisional income, CPI-imputed periods, and recent reporting-
  lag months.
- Composition adjustment using stable observed property characteristics where
  support allows it.

## Pooled external-validity test

After both metro analyses pass independent data and model checks, stack their
identically structured panels while retaining metro-specific frozen tier
boundaries. Estimate the metro-specific triple interactions and the
`metro × suburban × move-up tier × rate_gap_pp` difference with county and
calendar-month fixed effects. Report metro-specific linear combinations,
confidence intervals, and the four-way difference. Estimate the move-up-to-
entry sensitivity ratio separately for each metro with bootstrap uncertainty.
The historical 4.5x result is a hypothesis, not a fixed benchmark.

## Claim policy

Unless the identification checks warrant stronger language, use terms such as
“associated with,” “differential association,” and “completed-sale
heterogeneity.” Do not use “caused,” “effect,” “demand elasticity,” “market
freeze caused by,” or “below counterfactual trajectory” as factual conclusions
without a design that identifies those quantities. Log every proposed
headline result in `docs/claim_ledger.md` before release.
