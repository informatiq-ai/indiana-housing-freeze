---
name: housing-econometrics
description: Specify, implement, diagnose, or interpret the project's housing econometric models, including continuous-rate interactions, difference-in-differences, event studies, pre-trends, and robustness checks. Use for research design and model claims; do not use for ingestion or panel assembly alone.
---

# Housing Econometrics

Read `AGENTS.md` and
[references/identification-checklist.md](references/identification-checklist.md).
Inspect the actual panel contract, sample window, and treatment/tier definitions.
Do not inherit a narrative estimand from existing prose when the implemented
formula or available variation differs.

## Workflow

- Write the outcome, estimand, comparison groups, treatment timing/exposure, and
  identifying assumption before selecting a formula.
- Distinguish descriptive rate sensitivity from a causal DiD. National mortgage
  rates are common across counties; full time fixed effects absorb their main
  effect, leaving only interactions with predetermined exposure.
- Keep all lower-order terms implied by an interaction unless a clearly stated
  parameterization justifies otherwise.
- Use fixed pre-period tier boundaries. Do not let post-treatment sale price
  determine the treatment subgroup in the primary causal model.
- Test pre-trends with coefficients and uncertainty. A visually plausible chart
  is supporting evidence, not the test itself.
- Address the small number of county clusters explicitly. Conventional clustered
  standard errors alone may be unreliable; report an appropriate sensitivity or
  qualify inference.
- Run cohort, price-bound, lag, recovered-record, property-type, metro-specific,
  and composition sensitivities that materially affect the estimand.

Every reported percentage must identify its coefficient transformation and
units. Separate statistically estimated effects from scenario calculations and
avoid demand-elasticity language without listings/unsold inventory or another
defensible identification source.
