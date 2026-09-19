#!/usr/bin/env python3
"""Incrementally ingest Minnesota weekly eCRV ZIPs and export analytical files."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).parent))
from mn_ecrv import PARSER_VERSION
from mn_ecrv.schema import RecordError, parse_record
from mn_ecrv.store import batch_complete, connect, export_outputs, insert_version, refresh_views

ARCHIVE_DATE = re.compile(r"(?P<date>\d{4}-\d{2}-\d{2})-(?P<hour>\d{2})-(?P<minute>\d{2})-(?P<second>\d{2})")
MEMBER_KEY = re.compile(r"(?P<county>\d{2})_(?P<ecrv_id>\d+)\.xml$", re.I)


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def extract_timestamp(path):
    match = ARCHIVE_DATE.search(path.name)
    if not match:
        return None
    return datetime.fromisoformat(match.group("date") + "T" + ":".join(match.group(x) for x in ("hour", "minute", "second")))


def quality_event(database, batch_id, archive, ordinal, member, raw_hash, code, severity="error", recovery=None):
    database.execute("INSERT INTO quality_events VALUES (?,?,?,?,?,?,?,?)",
                     [batch_id, archive.name, ordinal, member, raw_hash, code, severity, recovery])


def ingest_archive(database, archive, config):
    archive_hash = sha256_file(archive)
    batch_id = f"{archive_hash}:{PARSER_VERSION}"
    if batch_complete(database, archive_hash):
        return "skipped", 0, 0
    valid = recovered = errors = 0
    with zipfile.ZipFile(archive) as source:
        members = [item for item in source.infolist() if not item.is_dir()]
        if len(members) > config["max_members"] or sum(item.file_size for item in members) > config["max_archive_bytes"]:
            raise ValueError("archive_limits_exceeded")
        database.execute("BEGIN TRANSACTION")
        try:
            observed_at = extract_timestamp(archive)
            database.execute("INSERT INTO ingest_batches VALUES (?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)",
                             [batch_id, archive_hash, archive.name, str(archive),
                              observed_at.isoformat() if observed_at else None, archive.stat().st_size,
                              PARSER_VERSION, "processing", len(members), 0, 0, 0])
            seen_member_names = set()
            seen_source_keys = set()
            for ordinal, info in enumerate(members, 1):
                if info.filename in seen_member_names:
                    quality_event(database, batch_id, archive, ordinal, info.filename, None, "duplicate_member_name")
                    errors += 1
                    continue
                seen_member_names.add(info.filename)
                if not info.filename.lower().endswith(".xml"):
                    quality_event(database, batch_id, archive, ordinal, info.filename, None, "non_xml_member")
                    errors += 1
                    continue
                if info.file_size > config["max_member_bytes"]:
                    quality_event(database, batch_id, archive, ordinal, info.filename, None, "oversize_member")
                    errors += 1
                    continue
                raw = source.read(info)
                raw_hash = hashlib.sha256(raw).hexdigest()
                try:
                    record = parse_record(raw, config["twin_cities_counties"])
                except RecordError as exc:
                    quality_event(database, batch_id, archive, ordinal, info.filename, raw_hash, exc.code)
                    errors += 1
                    continue
                filename_key = MEMBER_KEY.search(info.filename)
                if filename_key and (
                    filename_key.group("county") != record.transaction["mn_county_code"]
                    or filename_key.group("ecrv_id") != record.transaction["ecrv_id"]
                ):
                    quality_event(database, batch_id, archive, ordinal, info.filename, raw_hash, "filename_key_mismatch")
                    errors += 1
                    continue
                if record.transaction["source_key"] in seen_source_keys:
                    quality_event(database, batch_id, archive, ordinal, info.filename, raw_hash, "duplicate_source_key")
                    errors += 1
                    continue
                seen_source_keys.add(record.transaction["source_key"])
                version_id = insert_version(database, record)
                database.execute("INSERT INTO record_observations VALUES (?,?,?,?,?,?)",
                                 [batch_id, ordinal, info.filename, record.transaction["source_key"], version_id, raw_hash])
                valid += 1
                if record.parse_recovered:
                    recovered += 1
                    quality_event(database, batch_id, archive, ordinal, info.filename, raw_hash,
                                  "parse_recovered", "warning", record.recovery_method)
            status = "complete" if errors == 0 else "incomplete"
            database.execute("""UPDATE ingest_batches
              SET status=?, valid_count=?, recovered_count=?, error_count=?
              WHERE batch_id=?""", [status, valid, recovered, errors, batch_id])
            database.execute("COMMIT")
        except Exception:
            database.execute("ROLLBACK")
            raise
    return status, valid, errors


def load_config(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("ingest", "export", "all"), nargs="?", default="all")
    parser.add_argument("--config", type=Path, default=Path("config/mn_ecrv.json"))
    parser.add_argument("--year", type=int, action="append", help="ingest only these extract years")
    parser.add_argument("--archive", type=Path, action="append", help="ingest only these ZIP files")
    parser.add_argument("--limit", type=int, help="limit archives for validation runs")
    args = parser.parse_args()
    config = load_config(args.config)
    database = connect(Path(config["database"]))
    if args.command in {"ingest", "all"}:
        archives = args.archive or sorted(Path(config["input_dir"]).rglob("*.zip"))
        if args.year:
            archives = [path for path in archives if extract_timestamp(path) and extract_timestamp(path).year in args.year]
        if args.limit:
            archives = archives[:args.limit]
        totals = {"archives": 0, "skipped": 0, "valid": 0, "errors": 0}
        for archive in archives:
            status, valid, errors = ingest_archive(database, archive, config)
            totals["archives"] += 1
            totals["skipped"] += status == "skipped"
            totals["valid"] += valid
            totals["errors"] += errors
            print(f"{archive.name}: {status}; {valid} valid, {errors} quarantined")
        refresh_views(database)
        print(json.dumps(totals, sort_keys=True))
    if args.command in {"export", "all"}:
        summary = export_outputs(database, Path(config["processed_dir"]), Path(config["quality_dir"]))
        print("Exported " + json.dumps(summary, sort_keys=True))
    database.close()


if __name__ == "__main__":
    main()
