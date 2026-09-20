# Ingestion quality contract

## Separate these counts

Report, at the narrowest supported time/geography grain:

1. Source rows or archive members discovered.
2. Rows outside the study geography.
3. Invalid required keys or malformed records.
4. Exact repetitions collapsed.
5. Conflicting versions quarantined or retained as versions.
6. Normalized transaction facts.
7. Current-study eligible facts.
8. Strict/comparable eligible facts.
9. Missing periods, incomplete batches, and unavailable checks.

Never combine malformed input, duplicate versions, and research exclusions into
one generic “dropped” total.

## Completion report

State each check as `passed`, `failed`, `skipped`, or `unavailable`. Include:

- Input years/archive timestamps and hashes or manifest coverage.
- Transaction-key uniqueness and child-to-parent join coverage.
- County/year or county/month reconciliation.
- Schema variants observed and unsupported structures.
- PII-column exclusion.
- Unit and full-suite test commands.
- Real-data integration command, when run.
- Material attrition patterns requiring research judgment.

A pipeline is ingestion-complete only for the source periods actually reconciled.
It is analysis-ready only after eligibility, geographic/property-type alignment,
and time coverage have also been validated.
