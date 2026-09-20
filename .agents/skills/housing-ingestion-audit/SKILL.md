---
name: housing-ingestion-audit
description: Audit or change Indiana SDF and Minnesota eCRV ingestion, including source coverage, schema adapters, deduplication, eligibility, manifests, and filter funnels. Use for new years or archives, ingestion defects, backfills, and raw-to-normalized validation; do not use for panel modeling or publication-only review.
---

# Housing Ingestion Audit

Start by identifying the state and whether the request is diagnosis, implementation,
backfill, or validation. Read `AGENTS.md`, inspect local changes, and preserve raw
inputs and generated outputs unless the user explicitly asks to replace them.

Read only the relevant source guide:

- Indiana SDF work: [references/indiana-sdf.md](references/indiana-sdf.md)
- Minnesota eCRV work: [references/minnesota-ecrv.md](references/minnesota-ecrv.md)
- Completion or handoff audits: [references/quality-contract.md](references/quality-contract.md)

## Required behavior

- Establish actual source coverage before changing code. Do not infer a complete
  longitudinal series from the presence of processed output.
- Preserve transaction grain and exclude party/contact data from analytical
  reads, logs, fixtures, and exports.
- Treat exact repetition, conflicting versions, multiple parcels, missing source
  periods, malformed records, and research ineligibility as different conditions.
- Keep normalized data separate from research eligibility. Retain exclusion
  reasons rather than silently dropping records early.
- Use synthetic fixtures for automated tests. Real ignored data may be used for
  local integration checks but must not be committed.
- When changing behavior, test the smallest relevant unit first, then the full
  Python suite, then the real-data audit when the required local sources exist.
- Never report an unavailable archive or unexecuted full-data run as passing.

Run `scripts/summarize_ingestion.py --repo-root <repo> --state <state>` after an
existing build to obtain a read-only status summary. Treat its output as evidence,
not as a substitute for inspecting unexpected attrition or quality events.

End with tracked changes, generated artifacts, source coverage, counts at each
grain, checks actually run, and unresolved source-quality risks.
