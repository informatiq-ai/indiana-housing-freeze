# Longitudinal Indianapolis and Twin Cities research

## Research boundary

The longitudinal workflow is separate from the published 2021–2025 Indiana
analysis. It studies completed single-family transactions in Indianapolis and
the seven-county Twin Cities planning region from 2015 through 2025. The three
descriptive regimes are `BASELINE` (2015–2019), `PANDEMIC_LOW_RATE`
(2020–2021), and `HIGH_RATE_LOCK_IN` (2022–2025). Monthly mortgage rates and
their percentage-point spread over 3.0% remain the principal exposure.

The data can support conditional sale-price, transaction-volume, affordability,
and listing-market associations. It cannot identify a demand curve or buyer
response to asking-price changes without listing histories and unsold inventory.

## Comparable cohorts

Indiana's primary cohort applies the existing current-study conveyance rules and
requires every observed parcel to carry a one-family class code from 510 through
515. Minnesota requires an exclusively single-family before-sale use:
`RES/HOUSESGL` in the 2015 schema or `RESID/SINGLEFAM` in later schemas. Positive
Minnesota nonmarket, related-party, government, legal, partial-interest, payoff,
exchange, trade, and quitclaim evidence is excluded. Unknown source flags remain
unknown and fail the strict sensitivity cohort.

Both states use `$50,000 < gross price <= $15,000,000`. Minnesota adjusted price
is populated only when the personal-property inclusion record, selected item
values, and seller-paid points are complete. Gross price remains primary.
Minnesota reporting lag is measured from the first weekly extract in which a
transaction appears; latest revisions therefore do not inflate initial lag.

The canonical Minnesota history remains the versioned SQLite store. The
research preparation command creates or reuses a snapshot-pinned, Zstandard-
compressed Parquet extract containing only the seven counties, study years,
and required child tables. It writes the harmonized contract as Parquet and a
CSV compatibility copy for the current R toolchain. Input hashes and output
sizes are recorded in the research manifest.

## Panels and tiers

The transaction panel is county × sale month × fixed price tier. The listing
panel remains county × month because Redfin county metrics are not tier-specific.
Zero transaction cells are created only after annual Indiana and weekly
Minnesota source coverage pass their completeness gates; missing listing metrics
remain missing.

Three price clusters are fit independently by metro on log price in constant
2025 dollars using eligible 2015–2019 sales, seed 42, and 50 initializations.
Boundaries are frozen for later years and stored with their cohort hashes. Since
realized sale price still determines a transaction's tier, tier-specific price
results are descriptive heterogeneity rather than a predetermined causal cohort.

FRED returned one interior CPI-U gap for October 2025 in the current data pull.
The panel builder linearly interpolates only interior CPI gaps, flags the month
as `cpi_imputed`, and writes `external_data_adjustments.csv`. Endpoint gaps are
not extrapolated, and missing mortgage-rate months remain fatal.

## Estimation and inference

Indianapolis and MSP models are estimated separately before pooling. Primary
price and volume specifications interact rate spread, price tier, and suburban
geography with county and calendar-month fixed effects. Calendar-month effects
absorb the national rate main effect, so only differential exposure interactions
are interpreted. County-clustered covariance is reported, with a Webb six-point
wild-cluster-bootstrap sensitivity for the headline interaction.

Model tables also report `100 * (exp(beta) - 1)` for log-link coefficients.
Price-to-income and modeled payment-to-income use the same interaction hierarchy.
The Poisson transaction-count model retains county-clustered covariance; its
wild-bootstrap check is an explicitly labeled auxiliary `log(count + 0.5)`
linear specification so bootstrap draws cannot create invalid negative counts.

Quarterly event studies report suburban-versus-core leads and lags around the
first 2022 month with an average 30-year rate of at least 5%. A joint lead test is
reported rather than treating a chart as proof of parallel trends. Every
reported lead and lag receives a Webb-weight wild-cluster-bootstrap interval;
this remains defined when the conventional few-county covariance matrix is
indefinite. Failed pre-trend tests require associational language.

Sensitivity output covers strict cohorts, Minnesota recovery and adjusted-price
availability, zero/three/six-month rate exposure, the 2020–2021 transition,
quantile tiers, alternate price bounds, source-schema eras, carried-forward
income, recent reporting periods, and every estimable county leave-one-out case.
Removing Marion is reported as unavailable because it removes Indianapolis's
only urban-core comparison rather than producing a misleading coefficient.

The pooled model adds the metro interaction to test whether the Indianapolis
triple interaction differs from MSP. The previously reported 4.5× sensitivity
ratio is treated as a hypothesis to test, not a maintained assumption.
