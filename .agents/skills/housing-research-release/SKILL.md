---
name: housing-research-release
description: Validate this project's analysis, figures, tables, documentation, and headline claims before publication or handoff. Use for completion review, reproducibility checks, stale-output detection, and claim-to-artifact tracing; do not use as the primary workflow for implementing ingestion or models.
---

# Housing Research Release

Read `AGENTS.md` and
[references/release-checklist.md](references/release-checklist.md). Establish the
intended audience and release boundary. A review request authorizes inspection
and checks, not regeneration, external publication, or deployment unless the
user also asks for those actions.

## Review method

1. Inventory the source snapshot, normalized data, panel, models, tables,
   figures, application outputs, and narrative documents in scope.
2. Create a claim ledger for headline numbers: claim, artifact, generating code,
   sample/cohort, time window, value reproduced, and status.
3. Compare modification times and embedded labels only as clues; reproduce
   material values from data/model artifacts when possible.
4. Verify that geography, cohort, tier boundaries, rate units, sample sizes, and
   date windows agree across code, tables, figures, captions, README, and docs.
5. Check that limitations match the actual identification design and source
   coverage. Flag causal or elasticity language unsupported by the model/data.
6. Run applicable automated and full-data checks only when dependencies and raw
   inputs are available. Record all skipped or unavailable checks.

Return a release decision of `ready`, `ready with disclosed limitations`, or
`not ready`, followed by blocking findings, nonblocking findings, checks run, and
the minimum fixes required. Never update headline claims merely to match stale
outputs; determine which artifact is authoritative first.
