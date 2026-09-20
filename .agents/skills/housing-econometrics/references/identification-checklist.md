# Identification and model checklist

## Before estimation

- Confirm source completeness and the exact eligible cohort.
- Declare pre-period, treatment period, provisional end periods, and excluded
  transition months.
- Verify that treatment, geography, and price-tier definitions are predetermined.
- Tabulate outcome support for every metro × tier × geography × period cell.
- State whether the model targets prices, transaction volume, listing outcomes,
  affordability scenarios, or another mechanism.

## Continuous-rate triple interaction

A candidate specification may interact move-up tier, suburban geography, and
the mortgage-rate spread over a 3.0% legacy baseline. Include the full hierarchy
of lower-order terms plus justified controls and fixed effects. With full month
effects, do not interpret the common rate main effect; the estimable variation is
the differential exposure interaction.

The coefficient on a log-price outcome is converted with
`100 * (exp(beta) - 1)` for a one-unit change in the interacted continuous rate
measure. State whether one unit means one percentage point or one decimal unit.

## Pre-trends and dynamics

- Estimate an event-study or explicit pre-period differential trend test.
- Report coefficients, confidence intervals, joint pre-trend test, reference
  period, and cell counts.
- Inspect differential reporting lags and composition before attributing a break
  to mortgage rates.

## Inference and robustness

- Report the number of clusters. With few counties, consider wild-cluster
  bootstrap, randomization/permutation inference where defensible, or transparent
  sensitivity bounds.
- Compare strict/comparable and broader current-study cohorts.
- Vary rate lags, price bounds, property types, recovered Minnesota records, and
  metro pooling.
- Inspect leverage and thin luxury cells; do not let sparse cells anchor a
  headline conclusion.
- Treat ACS income vintage and margins of error as measurement limitations.

## Claim boundaries

Completed transactions can support conditional price and sales-volume
associations. They cannot alone identify response to asking-price changes,
sale probability, time-to-sale, cancellations, or a demand curve. Those claims
require listing histories, unsold inventory, or a stated structural design.
