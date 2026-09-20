# Housing research release checklist

## Data lineage

- Input manifests/hashes identify the source snapshot.
- Requested years and counties are present; missing/incomplete periods are shown.
- Normalized keys, eligibility rules, and filter funnels reconcile.
- Panel keys are unique and external joins report unmatched coverage.
- Recent/provisional periods are identified.

## Models

- Formula matches the stated estimand and includes required lower-order terms.
- Treatment, reference groups, tier boundaries, and rate units are documented.
- Pre-trend and robustness results accompany the primary estimate.
- Standard errors/inference acknowledge the number of clusters.
- Saved model artifacts were generated from the current panel snapshot.

## Tables and figures

- Every headline coefficient, N, date range, and tier label reproduces.
- Captions name the source, sample, units, and relevant limitations.
- Axes and legends distinguish metro, geography, tier, and pre/post definitions.
- PNG/PDF pairs and table exports are current where the project requires them.
- Empty or missing cells are not plotted as zeros.

## Narrative and application

- README, methodology, findings, and application labels agree with artifacts.
- Claims distinguish observed association, model estimate, and scenario result.
- No invented biography, metric, citation, or source capability appears.
- Completed-sale data are not described as identifying listing demand elasticity.
- Known source-quality attrition and cohort sensitivity are disclosed.

## Reproducibility and handoff

- Commands, environment requirements, and required API keys are documented.
- Tests and end-to-end checks list actual outcomes.
- Generated/ignored artifacts are distinguished from tracked source changes.
- No raw data, PII, credentials, or local-only paths are staged for release.
- The release decision names blockers and remaining risks explicitly.
