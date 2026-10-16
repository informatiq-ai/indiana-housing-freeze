---
name: mn-ecrv-weekly-update
description: Routine runbook for adding new Minnesota eCRV weekly ZIP extracts (one week or a batch) to the project and refreshing downstream Twin Cities data. Use whenever the user says they downloaded new eCRV files, wants to add this week's or this month's Minnesota sales, refresh MSP data, or rerun Minnesota ingestion after new archives arrive. Do not use for diagnosing parser defects, schema changes, or backfill design (use housing-ingestion-audit), or for model changes.
---

# Minnesota eCRV Weekly Update

New weekly extracts arrive from the Minnesota Department of Revenue as ZIP
archives named like `2026-09-21-07-10-03_eCRVExtract.zip`. Ingestion is
incremental and content-hashed, so rerunning is safe; the risk in a routine
update is silently accepting a missing week, a new schema, or a jump in
quarantined records. This runbook makes each of those visible before any panel
or model is refreshed.

## Steps

1. **Place archives.** Copy (do not rename or edit) each ZIP into
   `data/raw/mn/ecrv/<extract year>/`, using the year from the filename
   timestamp. Raw archives are immutable and gitignored.

2. **Ingest only the new year(s), then export:**

   ```bash
   .venv/bin/python scripts/00_mn_ecrv_pipeline.py ingest --year 2026
   .venv/bin/python scripts/00_mn_ecrv_pipeline.py export
   ```

   Each archive prints `complete`, `incomplete` (some members quarantined), or
   `skipped` (already processed, same bytes and parser version). A
   `skipped` line for a file you believe is new means identical bytes were
   already ingested under another name; that is correct behavior, not an error.

3. **Check coverage and quality:**

   ```bash
   .venv/bin/python .agents/skills/mn-ecrv-weekly-update/scripts/check_weekly_coverage.py --since 2026-01-01
   ```

   This reads `outputs/mn/quality/ecrv_archive_coverage.csv` and
   `ecrv_schema_counts.csv` and reports: the latest extract date and its age,
   gaps between consecutive extracts over 7 days (more than 10 days usually
   means a missing week; 8 to 9 days is usually a delayed run), archives with
   quarantined errors, recovery and error rates against the prior-year
   baseline, and any schema variant not seen before the window. Exit status 1
   means something needs a human decision.

4. **Stop and report** instead of continuing when the checker flags a probable
   missing week, a new schema variant, an error rate well above baseline, or a
   `non_xml_member`. Those belong to `housing-ingestion-audit`. Do not delete
   or edit an archive to make the check pass.

5. **Refresh the research extract only when the update touches the study
   window.** The study window is 2015–2025 and is closed; 2026 sales stay in
   the store but must not enter models (`docs/analysis_protocol.md`). Late
   2026 extracts can still carry 2025 sale dates, so check whether any new
   records fall in the window before deciding:

   ```bash
   .venv/bin/python scripts/00_mn_ecrv_pipeline.py research-export --start-year 2015 --end-year 2025
   ```

   The export reuses the cached Parquet when the source snapshot is unchanged.
   If it rewrites, the downstream panel (`scripts/research/01_prepare_transactions.py`,
   `02_build_panels.R`) and any frozen snapshot are stale: say so explicitly
   and, if a protocol freeze exists, record the change with
   `housing-snapshot-freeze` rather than silently regenerating.

6. **Summarize** for the user: archives added, skipped, records valid,
   quarantined and recovered, latest extract date, checker findings, and
   whether the study-window extract changed.

## Notes

- Never commit raw ZIPs, the SQLite store, or generated CSV/Parquet; they are
  gitignored by design.
- The pipeline does not download archives. Acquiring files from the source is
  a separate, manual step.
- The weekly feed does republish some amended CRVs in later extracts; the
  store keeps every version and selects the latest observed. Rerun
  `scripts/00_mn_ecrv_pipeline.py reconcile` after an update to see how many
  transactions were revised and which fields changed.
- Absence of a sale from a later extract is not a deletion. Do not infer
  withdrawals.
