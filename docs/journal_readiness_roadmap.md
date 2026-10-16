# Journal readiness roadmap

## Purpose

This roadmap defines the work required before the Indianapolis and Twin Cities
results can support a journal submission. It is a release gate, not a statement
that every planned analysis has been completed. The established 2021–2025
Indianapolis outputs remain separate from the longitudinal 2015–2025 study
until the latter passes the gates below.

## Proposed paper boundary

The primary paper should ask whether changes in mortgage rates are associated
with different completed-sale prices and transaction volumes across fixed price
tiers and urban-core versus suburban counties, and whether those associations
replicate in Indianapolis and the Twin Cities.

The evidence presently supports associational language. Causal difference-in-
differences language requires credible pre-trends, a defensible comparison
group, and inference that remains reliable with five Indianapolis and seven
Twin Cities counties. Completed sales alone do not identify buyer demand
elasticity, listing success, cancellations, or true cumulative days on market.

## Release gates

### Gate 1: Transaction histories

- Indiana 2015–2025 inputs appear in a hashed manifest and county-year funnels
  reconcile accepted, excluded, duplicate, and quarantined records.
- Minnesota weekly archive coverage reconciles by year, all supported schema
  eras parse, reporting lag is measured, and 2026 is excluded from models.
- Transaction keys are unique at the accepted grain and child records do not
  multiply prices or counts.
- Analytical outputs contain no party, contact, mailing-address, or title-
  company fields.
- Primary and sensitivity cohorts are defined before model estimation.

### Gate 2: Frozen analysis protocol

- The primary estimand, outcomes, sample, dates, exposure units, controls,
  fixed effects, clustering, and coefficient transformations are recorded in
  `docs/analysis_protocol.md`.
- Metro-specific real-price tiers are fitted only on the 2015–2019 baseline,
  then frozen for 2020–2025. Their centers, boundaries, seed, inflation base,
  training counts, and cohort hash are persisted.
- Any result that assigns tiers from contemporaneous sale price is described as
  completed-sale heterogeneity, not a predetermined causal subgroup effect.
- Deviations from the protocol are dated in `docs/decision_log.md` and labeled
  exploratory in tables and prose.

### Gate 3: Panel and external-data integrity

- Both metros have a complete January 2015–December 2025 county-month grid.
- Zero transactions appear only where source coverage proves observation;
  unavailable listing metrics remain missing.
- FRED, CPI-U, ACS, and Redfin joins are unique and unmatched periods are
  reported.
- Constant-dollar measures use the documented 2025 CPI base and imputed or
  carried-forward observations are flagged.
- Source and panel snapshots are immutable or reproducibly addressable by hash.

### Gate 4: Primary estimates and identification checks

- Indianapolis and Twin Cities models run independently before pooling.
- Specifications contain the full estimable lower-order interaction hierarchy,
  county fixed effects, and calendar-month fixed effects.
- Quarterly event studies report all leads and lags, confidence intervals,
  sample counts, the reference quarter, and joint pre-trend tests.
- Inference reports county-clustered estimates and an appropriate few-cluster
  sensitivity such as wild-cluster bootstrap.
- Count outcomes use a count model with an exposure offset where appropriate;
  interpretations use contrasts or predicted counts rather than treating a
  nonlinear interaction coefficient as a standalone effect.
- Failed pre-trend or support checks change the claim language; they do not get
  hidden or treated as pipeline errors.

### Gate 5: Robustness and external validity

- Cohort, rate-lag, transition-period, tier, price-bound, schema-era, income-
  vintage, reporting-lag, adjusted-price, and county leave-one-out results are
  complete.
- Composition changes are quantified and, where feasible, addressed with
  hedonic controls, stable property cells, or repeat-sales evidence.
- Days on market remains secondary unless cumulative listing history or an MLS
  measure with a stable definition becomes available.
- The pooled model reports both metro-specific effects and the formal cross-
  metro difference. It tests the historical 4.5x result rather than imposing it.

### Gate 6: Manuscript and reproducibility release

- Every headline statement passes the claim ledger in
  `docs/claim_ledger.md`.
- Tables and figures identify sample, dates, units, cohort, uncertainty, and
  limitations; captions agree with the generating code.
- The abstract, manuscript, supplement, README, methodology, and findings do
  not contradict the current artifacts.
- A clean environment can reproduce the analytical outputs using
  `docs/reproducibility.md`, subject to documented raw-data access constraints.
- The submission includes data availability, code availability, conflicts,
  funding, author contributions, and ethical/privacy statements as required by
  the selected journal.

## Current status

| Area | Status | Principal remaining work |
|---|---|---|
| Indiana ingestion | In progress | Final reconciliation and frozen research snapshot |
| Minnesota ingestion | In progress | Full weekly rebuild, coverage audit, and cohort validation |
| Real-price conversion | Implemented for established Indiana workflow | Reconcile CPI treatment across both longitudinal metros |
| Primary tiers | Not release-ready | Refit on 2015–2019 eligible real-price baseline and persist metadata |
| Indianapolis longitudinal models | Exploratory | Freeze specification, rerun inference, and resolve pre-trend interpretation |
| Twin Cities models | Not release-ready | Complete source history and run matched specifications |
| Pooled comparison | Blocked by metro gates | Run only after both independent analyses pass |
| DOM analysis | Secondary/exploratory | Obtain defensible cumulative DOM or retain strong measurement caveat |
| Manuscript claim audit | Not started | Populate ledger from regenerated final artifacts |

## Recommended sequence

1. Finish and reconcile both transaction histories.
2. Freeze the protocol and baseline tier artifacts.
3. Build and validate metro-specific panels.
4. Estimate each metro and complete pre-trend and robustness checks.
5. Run the pooled external-validity test.
6. Generate final tables and figures from immutable snapshots.
7. Populate the claim ledger and conduct an independent release audit.
8. Select a target journal and conform the manuscript only after the scientific
   specification is stable.

The study is journal-ready only when all six gates pass. A successful script
run or statistically significant coefficient is not, by itself, a release
decision.
