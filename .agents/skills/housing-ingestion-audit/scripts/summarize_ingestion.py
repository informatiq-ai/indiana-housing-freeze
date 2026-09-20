#!/usr/bin/env python3
"""Read-only status summary for the repository's Indiana and Minnesota ingestion."""

import argparse
import csv
import json
from pathlib import Path
import sqlite3


PII_TOKENS = (
    "buyer_name", "seller_name", "first_name", "last_name", "phone", "email",
    "street_address", "mailing_address", "title_company",
)


def csv_header_and_rows(path):
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.reader(stream)
        header = next(reader)
        return header, sum(1 for _ in reader)


def summarize_indiana(root):
    history = root / "data/processed/indiana_sdf_history.csv"
    funnel = root / "outputs/indiana/quality/sdf_filter_funnel.csv"
    manifest = root / "outputs/indiana/quality/sdf_ingestion_manifest.json"
    result = {"available": all(path.exists() for path in (history, funnel, manifest))}
    if not result["available"]:
        result["missing"] = [str(path.relative_to(root)) for path in (history, funnel, manifest)
                             if not path.exists()]
        return result
    header, rows = csv_header_and_rows(history)
    with funnel.open(encoding="utf-8", newline="") as stream:
        funnel_rows = list(csv.DictReader(stream))
    count_fields = ("raw_target_rows", "invalid_key_rows",
                    "exact_duplicate_rows_removed", "conflicting_rows_quarantined",
                    "normalized_rows", "current_study_eligible_rows",
                    "strict_comparable_eligible_rows")
    totals = {field: sum(int(row[field]) for row in funnel_rows) for field in count_fields}
    result.update({
        "history_rows": rows,
        "manifest_inputs": len(json.loads(manifest.read_text(encoding="utf-8"))["inputs"]),
        "years": sorted({int(row["source_year"]) for row in funnel_rows}),
        "funnel_rows": len(funnel_rows),
        "funnel_reconciles": all(
            int(row["raw_target_rows"]) == int(row["invalid_key_rows"])
            + int(row["exact_duplicate_rows_removed"])
            + int(row["conflicting_rows_quarantined"])
            + int(row["normalized_rows"])
            for row in funnel_rows
        ),
        "pii_like_columns": [column for column in header
                             if any(token in column.lower() for token in PII_TOKENS)],
        "totals": totals,
    })
    return result


def summarize_minnesota(root):
    database_path = root / "data/intermediate/mn/ecrv.sqlite"
    transactions = root / "data/processed/mn/ecrv_transactions.csv"
    result = {"available": database_path.exists() and transactions.exists()}
    if not result["available"]:
        result["missing"] = [str(path.relative_to(root)) for path in (database_path, transactions)
                             if not path.exists()]
        return result
    database = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
    try:
        batches = database.execute("""
          SELECT coalesce(substr(extract_timestamp,1,4), 'unknown') AS extract_year,
                 status, count(*), sum(member_count), sum(valid_count), sum(error_count)
          FROM ingest_batches GROUP BY 1,2 ORDER BY 1,2
        """).fetchall()
        current_transactions = database.execute(
            "SELECT count(*) FROM current_transactions"
        ).fetchone()[0]
    finally:
        database.close()
    header, exported_rows = csv_header_and_rows(transactions)
    result.update({
        "batches": [dict(zip(("extract_year", "status", "batches", "members",
                              "valid", "errors"), row)) for row in batches],
        "current_transactions": current_transactions,
        "exported_transactions": exported_rows,
        "pii_like_columns": [column for column in header
                             if any(token in column.lower() for token in PII_TOKENS)],
    })
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--state", choices=("indiana", "minnesota", "all"), default="all")
    args = parser.parse_args()
    root = args.repo_root.resolve()
    result = {}
    if args.state in {"indiana", "all"}:
        result["indiana"] = summarize_indiana(root)
    if args.state in {"minnesota", "all"}:
        result["minnesota"] = summarize_minnesota(root)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
