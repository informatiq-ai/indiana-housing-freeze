# Minnesota eCRV ingestion

## Routing

- `scripts/mn_ecrv/schema.py` parses supported XML variants without party data.
- `scripts/mn_ecrv/store.py` owns the versioned SQLite registry, current-record
  view, child rows, and exports.
- `scripts/00_mn_ecrv_pipeline.py` is the incremental ingest/export CLI.
- `scripts/audit_mn_ecrv.py` audits archives without changing the canonical store.
- `docs/minnesota_ecrv_architecture.md` records source-specific limitations and
  the implemented/proposed boundary.

## Invariants

- Study geography is the seven-county planning region configured in
  `config/mn_ecrv.json`; it is not the full federal MSA.
- A transaction key is county plus eCRV number. A parcel is not a transaction
  key and a multi-parcel conveyance counts once.
- Preserve raw-member versions and archive observations. Choose the
  latest-observed record only by validated extract timestamp; ingestion time and
  filesystem mtime are not revision authority.
- An incomplete batch may contain usable validated records, but its quarantines
  must remain visible. Absence from a later archive is not a deletion.
- Keep nullable source flags nullable. Unknown suitability is not affirmative
  evidence of an arm's-length sale.
- Do not join all child tables into the transaction fact or use mailing-party
  addresses as property geography.
- Encoding or invalid-character recovery must be deterministic and recorded.

## Backfill audit

Before panel work, query `ingest_batches` by extract year and status, compare the
available archives with the intended research window, inspect quality summaries,
and distinguish extract year from deed year. Verify overlapping archives and
source amendment/withdrawal behavior before treating latest-observed selection
as historically complete.

```bash
.venv/bin/python scripts/00_mn_ecrv_pipeline.py all
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python .agents/skills/housing-ingestion-audit/scripts/summarize_ingestion.py \
  --repo-root . --state minnesota
```

The ingestion engine being operational does not imply that 2015–present archive
coverage, research eligibility, adjusted price, or the county-month panel is
complete.
