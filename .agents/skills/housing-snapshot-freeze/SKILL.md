---
name: housing-snapshot-freeze
description: Freeze a release-candidate snapshot of the longitudinal Indianapolis and Twin Cities analysis by hashing source extracts, panels, tier definitions, and model outputs into a manifest, filling the protocol freeze table, and recording decision-log entries. Also verifies an existing snapshot is unchanged. Use when the user wants to freeze the protocol, cut a release candidate, record what data a result came from, check whether outputs drifted since a freeze, or log a methodological decision. Do not use for routine ingestion or for designing the models themselves.
---

# Housing Snapshot Freeze

Gate 2 and Gate 3 of `docs/journal_readiness_roadmap.md` require that every
published result be traceable to immutable, hash-addressed inputs and a frozen
protocol. Generated data under `data/processed/research/` and
`outputs/research/` are gitignored, so the manifest is the only durable record
of exactly what a result was computed from.

## Preconditions

Check these first and report any that fail instead of freezing anyway:

- Phases ahead of the freeze are complete or explicitly waived by the user:
  source reconciliation, pre-trend inference, robustness runs.
- Tracked code is committed (`git status`). A manifest built on uncommitted
  code cannot be reproduced from its recorded commit; the builder warns about
  this, and it is the user's call whether to proceed.
- Outputs were regenerated from the current code, not left over from an
  earlier run. Compare file modification times with the latest relevant
  commit as a clue, and rerun when in doubt.

## Build the manifest

Manifests are small JSON files kept in Git at `docs/snapshots/<label>.json`,
for example `rc1`. Hash the analysis inputs and outputs, not raw archives (raw
archive hashes are already recorded by the ingestion manifests listed below):

```bash
.venv/bin/python .agents/skills/housing-snapshot-freeze/scripts/build_manifest.py build \
  --label rc1 --output docs/snapshots/rc1.json \
  data/processed/mn/research_extract \
  data/processed/research \
  outputs/research \
  outputs/mn/quality/ecrv_ingestion_manifest.json \
  outputs/indiana/quality \
  config/mn_ecrv.json
```

Hashing about 1.3 GB takes a few minutes. The output reports the file count and
a combined `snapshot_sha256`.

## Record the freeze

1. Fill the release-candidate table in `docs/analysis_protocol.md`: protocol
   version, freeze date, Git commit, the Indiana and Minnesota manifest hashes
   (the `sha256` recorded in the new manifest for
   `outputs/indiana/quality/sdf_ingestion_manifest.json` and
   `outputs/mn/quality/ecrv_ingestion_manifest.json`), and the panel snapshot
   hash (the manifest's `snapshot_sha256`).
2. Append (never edit) a `docs/decision_log.md` entry using the template at
   the top of that file, with status, scope, decision, reason, alternatives,
   consequences, implementation, sensitivity, and protocol classification.
   Any change after the freeze is labeled an amendment or exploratory.
3. Check the new prose with `housing-docs-style`, then stage the manifest and
   doc changes as their own commit with `housing-commit-staging`.

## Verify an existing snapshot

```bash
.venv/bin/python .agents/skills/housing-snapshot-freeze/scripts/build_manifest.py verify docs/snapshots/rc1.json
```

It reports `changed`, `missing`, and `added` files. Any of these means results
citing that snapshot may no longer reproduce from the current files: report
which claim-ledger rows depend on the affected artifacts rather than
re-freezing silently under the same label. A new freeze gets a new label.
