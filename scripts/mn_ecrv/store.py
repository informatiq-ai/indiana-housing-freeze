"""Standard-library SQLite registry and version store for Minnesota eCRV."""
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3

import pyarrow as pa
import pyarrow.parquet as pq

from . import PARSER_VERSION


def connect(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    database = sqlite3.connect(path)
    database.execute("PRAGMA foreign_keys=ON")
    database.execute("PRAGMA journal_mode=WAL")
    database.execute("PRAGMA synchronous=NORMAL")
    database.execute("PRAGMA cache_size=-262144")
    database.execute("PRAGMA temp_store=MEMORY")
    database.executescript("""
        CREATE TABLE IF NOT EXISTS ingest_batches (
          batch_id TEXT PRIMARY KEY, archive_sha256 TEXT, archive_name TEXT,
          archive_path TEXT, extract_timestamp TEXT, archive_bytes INTEGER,
          parser_version TEXT, status TEXT, member_count INTEGER, valid_count INTEGER,
          recovered_count INTEGER, error_count INTEGER,
          ingested_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_batches_archive
          ON ingest_batches(archive_sha256, parser_version);
        CREATE TABLE IF NOT EXISTS record_versions (
          version_id TEXT PRIMARY KEY, source_key TEXT, raw_member_sha256 TEXT,
          parser_version TEXT, analytical_hash TEXT, schema_variant TEXT,
          encoding TEXT, parse_recovered INTEGER, recovery_method TEXT,
          mn_county_code TEXT, county_name TEXT, county_fips TEXT,
          is_twin_cities INTEGER, ecrv_id TEXT, sale_date TEXT, sale_year INTEGER,
          sale_month TEXT, gross_sale_price TEXT, downpayment_equity TEXT,
          seller_paid_points TEXT, special_assessment_amount TEXT,
          finance_type TEXT, deed_type TEXT, transaction_json TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_versions_source_key ON record_versions(source_key);
        CREATE TABLE IF NOT EXISTS record_observations (
          batch_id TEXT, member_ordinal INTEGER, member_name TEXT,
          source_key TEXT, version_id TEXT, raw_member_sha256 TEXT,
          PRIMARY KEY(batch_id, member_ordinal),
          FOREIGN KEY(batch_id) REFERENCES ingest_batches(batch_id),
          FOREIGN KEY(version_id) REFERENCES record_versions(version_id)
        );
        CREATE TABLE IF NOT EXISTS child_rows (
          version_id TEXT, child_type TEXT, ordinal INTEGER, row_json TEXT,
          PRIMARY KEY(version_id, child_type, ordinal),
          FOREIGN KEY(version_id) REFERENCES record_versions(version_id)
        );
        CREATE TABLE IF NOT EXISTS quality_events (
          batch_id TEXT, archive_name TEXT, member_ordinal INTEGER,
          member_name TEXT, raw_member_sha256 TEXT, issue_code TEXT,
          severity TEXT, recovery_method TEXT
        );
    """)
    return database


def batch_complete(database, archive_hash):
    row = database.execute(
        "SELECT status FROM ingest_batches WHERE archive_sha256=? AND parser_version=?",
        [archive_hash, PARSER_VERSION],
    ).fetchone()
    return bool(row and row[0] in {"complete", "incomplete"})


def insert_version(database, record):
    return insert_versions(database, [record])[0]


def insert_versions(database, records):
    """Insert one archive's parsed versions and children with bounded batches."""
    version_rows = []
    child_values = []
    version_ids = []
    for record in records:
        version_id = f"{record.raw_sha256}:{PARSER_VERSION}"
        version_ids.append(version_id)
        t = record.transaction
        version_rows.append([
            version_id, t["source_key"], record.raw_sha256, PARSER_VERSION,
            record.analytical_hash, record.schema_variant, record.encoding,
            record.parse_recovered, record.recovery_method, t["mn_county_code"],
            t["county_name"], t["county_fips"], t["is_twin_cities"], t["ecrv_id"],
            t["sale_date"], t["sale_year"], t["sale_month"], t["gross_sale_price"],
            t["downpayment_equity"], t["seller_paid_points"],
            t["special_assessment_amount"], t["finance_type"], t["deed_type"],
            json.dumps(t, sort_keys=True),
        ])
        for child_type, rows in (
            ("parcel", record.parcels), ("address", record.addresses),
            ("use", record.uses), ("financing", record.financing),
            ("personal_property", record.personal_property),
        ):
            child_values.extend(
                [version_id, child_type, ordinal, json.dumps(row, sort_keys=True)]
                for ordinal, row in enumerate(rows, 1)
            )
    database.executemany("""
        INSERT OR IGNORE INTO record_versions VALUES (
          ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
        )
    """, version_rows)
    database.executemany(
        "INSERT OR IGNORE INTO child_rows VALUES (?,?,?,?)", child_values
    )
    return version_ids


def refresh_views(database):
    database.execute("DROP VIEW IF EXISTS current_transactions")
    database.execute(f"""
      CREATE VIEW current_transactions AS
      WITH conflicts AS (
        SELECT o.source_key, b.extract_timestamp
        FROM record_observations o
        JOIN ingest_batches b USING (batch_id)
        JOIN record_versions v USING (version_id)
        WHERE v.parser_version='{PARSER_VERSION}'
        GROUP BY o.source_key, b.extract_timestamp
        HAVING count(DISTINCT v.analytical_hash) > 1
      ), candidates AS (
        SELECT v.*, b.extract_timestamp, b.archive_name, o.member_name,
          min(b.extract_timestamp) OVER (
            PARTITION BY v.source_key
          ) AS first_extract_timestamp,
          CASE WHEN c.source_key IS NULL THEN 0 ELSE 1 END AS revision_conflict,
          row_number() OVER (
            PARTITION BY v.source_key
            ORDER BY b.extract_timestamp DESC, b.archive_name DESC,
                     o.member_ordinal DESC, v.version_id DESC
          ) AS selection_rank
        FROM record_observations o
        JOIN ingest_batches b USING (batch_id)
        JOIN record_versions v USING (version_id)
        LEFT JOIN conflicts c ON c.source_key=o.source_key
          AND c.extract_timestamp=b.extract_timestamp
        WHERE b.status IN ('complete', 'incomplete')
          AND v.parser_version='{PARSER_VERSION}'
      )
      SELECT * FROM candidates WHERE selection_rank=1
    """)


def _write_query(database, query, path):
    cursor = database.execute(query)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        with temporary.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(column[0] for column in cursor.description)
            while True:
                rows = cursor.fetchmany(10_000)
                if not rows:
                    break
                writer.writerows(rows)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_query_parquet(database, query, path, schema, parameters=()):
    """Stream a SQLite result to an atomic, compressed Parquet file."""
    cursor = database.execute(query, parameters)
    columns = [column[0] for column in cursor.description]
    if columns != schema.names:
        raise ValueError(
            f"Parquet schema mismatch for {path}: query returned {columns}, "
            f"expected {schema.names}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    writer = None
    rows_written = 0
    try:
        while True:
            rows = cursor.fetchmany(50_000)
            if not rows:
                break
            arrays = []
            for position, field in enumerate(schema):
                values = [row[position] for row in rows]
                if pa.types.is_string(field.type):
                    values = [None if value is None else str(value) for value in values]
                elif pa.types.is_integer(field.type):
                    values = [None if value is None else int(value) for value in values]
                arrays.append(pa.array(values, type=field.type))
            table = pa.Table.from_arrays(arrays, schema=schema)
            if writer is None:
                writer = pq.ParquetWriter(
                    temporary, schema, compression="zstd", compression_level=3,
                    use_dictionary=True,
                )
            writer.write_table(table)
            rows_written += len(rows)
        if writer is None:
            pq.write_table(
                pa.Table.from_arrays(
                    [pa.array([], type=field.type) for field in schema], schema=schema
                ),
                temporary,
                compression="zstd",
            )
        else:
            writer.close()
            writer = None
        os.replace(temporary, path)
    finally:
        if writer is not None:
            writer.close()
        if temporary.exists():
            temporary.unlink()
    return rows_written


def _research_snapshot(database, start_year, end_year):
    archive_hashes = [
        row[0] for row in database.execute(
            """SELECT archive_sha256 FROM ingest_batches
               WHERE parser_version=? AND status IN ('complete', 'incomplete')
               ORDER BY archive_sha256""",
            [PARSER_VERSION],
        )
    ]
    digest = hashlib.sha256("\n".join(archive_hashes).encode("ascii")).hexdigest()
    return {
        "parser_version": PARSER_VERSION,
        "start_year": start_year,
        "end_year": end_year,
        "archive_count": len(archive_hashes),
        "archive_set_sha256": digest,
    }


def export_research_parquet(
    database, processed_dir, start_year=2015, end_year=2025, reuse_if_current=True
):
    """Export a version-pinned Twin Cities research slice directly from SQLite."""
    processed_dir = Path(processed_dir)
    processed_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = processed_dir / "ecrv_research_extract_manifest.json"
    snapshot = _research_snapshot(database, start_year, end_year)
    filenames = (
        "ecrv_transactions.parquet", "ecrv_uses.parquet",
        "ecrv_parcels.parquet", "ecrv_personal_property.parquet",
    )
    if reuse_if_current and manifest_path.exists() and all(
        (processed_dir / filename).exists() for filename in filenames
    ):
        current = json.loads(manifest_path.read_text(encoding="utf-8"))
        if current.get("source_snapshot") == snapshot:
            return {**current, "cached": True}

    refresh_views(database)
    database.execute("PRAGMA temp_store=FILE")
    database.execute("DROP TABLE IF EXISTS temp.mn_research_current")
    transaction_sql = """SELECT source_key, schema_variant, sale_date, sale_year,
      sale_month, county_name, county_fips, is_twin_cities, gross_sale_price,
      seller_paid_points,
      json_extract(transaction_json, '$.personal_property_included') AS personal_property_included,
      revision_conflict, parse_recovered, recovery_method, first_extract_timestamp,
      extract_timestamp, archive_name, version_id, deed_type,
      json_extract(transaction_json, '$.new_buildings_sale_year') AS new_buildings_sale_year,
      json_extract(transaction_json, '$.related') AS related,
      json_extract(transaction_json, '$.gift') AS gift,
      json_extract(transaction_json, '$.government') AS government,
      json_extract(transaction_json, '$.legal_action') AS legal_action,
      json_extract(transaction_json, '$.name_change') AS name_change,
      json_extract(transaction_json, '$.non_market_price') AS non_market_price,
      json_extract(transaction_json, '$.tax_exempt') AS tax_exempt,
      json_extract(transaction_json, '$.buyer_part_interest') AS buyer_part_interest,
      json_extract(transaction_json, '$.deed_payoff') AS deed_payoff,
      json_extract(transaction_json, '$.like_kind_exchange') AS like_kind_exchange,
      json_extract(transaction_json, '$.received_in_trade') AS received_in_trade
      FROM current_transactions
      WHERE is_twin_cities=1 AND sale_year BETWEEN ? AND ?"""
    database.execute(
        f"CREATE TEMP TABLE mn_research_current AS {transaction_sql}",
        [start_year, end_year],
    )
    database.execute(
        "CREATE INDEX temp.idx_mn_research_version ON mn_research_current(version_id)"
    )
    database.execute(
        "CREATE INDEX temp.idx_mn_research_key ON mn_research_current(source_key)"
    )

    string = pa.string()
    integer = pa.int64()
    transaction_schema = pa.schema([
        ("source_key", string), ("schema_variant", string), ("sale_date", string),
        ("sale_year", integer), ("sale_month", string), ("county_name", string),
        ("county_fips", string), ("is_twin_cities", integer),
        ("gross_sale_price", string), ("seller_paid_points", string),
        ("personal_property_included", integer), ("revision_conflict", integer),
        ("parse_recovered", integer), ("recovery_method", string),
        ("first_extract_timestamp", string), ("extract_timestamp", string),
        ("archive_name", string), ("version_id", string), ("deed_type", string),
        ("new_buildings_sale_year", integer), ("related", integer), ("gift", integer),
        ("government", integer), ("legal_action", integer), ("name_change", integer),
        ("non_market_price", integer), ("tax_exempt", integer),
        ("buyer_part_interest", integer), ("deed_payoff", integer),
        ("like_kind_exchange", integer), ("received_in_trade", integer),
    ])
    child_schemas = {
        "uses": pa.schema([
            ("version_id", string), ("source_key", string), ("ordinal", integer),
            ("use_timing", string), ("id", string), ("tier1Cde", string),
            ("tier2Cde", string), ("tier3Cde", string), ("primaryInd", string),
            ("propertyTypeCode", string), ("propertyUseCode", string),
        ]),
        "parcels": pa.schema([
            ("version_id", string), ("source_key", string), ("ordinal", integer),
            ("id", string), ("parcelId", string), ("primary", string),
        ]),
        "personal_property": pa.schema([
            ("version_id", string), ("source_key", string), ("ordinal", integer),
            ("id", string), ("selected", string),
            ("propertyDescription", string), ("propertyValue", string),
        ]),
    }
    child_fields = {
        "uses": ("use", ("use_timing", "id", "tier1Cde", "tier2Cde", "tier3Cde",
                         "primaryInd", "propertyTypeCode", "propertyUseCode")),
        "parcels": ("parcel", ("id", "parcelId", "primary")),
        "personal_property": (
            "personal_property", ("id", "selected", "propertyDescription", "propertyValue")
        ),
    }
    counts = {}
    try:
        counts["transactions"] = _write_query_parquet(
            database,
            "SELECT * FROM mn_research_current ORDER BY sale_date, source_key",
            processed_dir / "ecrv_transactions.parquet",
            transaction_schema,
        )
        for filename, (child_type, fields) in child_fields.items():
            extracts = ", ".join(
                f"json_extract(c.row_json, '$.{field}') AS \"{field}\"" for field in fields
            )
            query = f"""SELECT c.version_id, t.source_key, c.ordinal, {extracts}
              FROM child_rows c JOIN mn_research_current t USING (version_id)
              WHERE c.child_type='{child_type}' ORDER BY t.source_key, c.ordinal"""
            counts[filename] = _write_query_parquet(
                database, query, processed_dir / f"ecrv_{filename}.parquet",
                child_schemas[filename],
            )
    finally:
        database.execute("DROP TABLE IF EXISTS temp.mn_research_current")

    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_snapshot": snapshot,
        "format": "parquet",
        "compression": "zstd",
        "rows": counts,
        "files": {
            filename: (processed_dir / filename).stat().st_size for filename in filenames
        },
        "cached": False,
    }
    temporary_manifest = manifest_path.with_suffix(".json.tmp")
    temporary_manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary_manifest, manifest_path)
    return manifest


def export_outputs(database, processed_dir, quality_dir):
    processed_dir.mkdir(parents=True, exist_ok=True)
    quality_dir.mkdir(parents=True, exist_ok=True)
    refresh_views(database)
    transaction_columns = """source_key, mn_county_code, county_name, county_fips,
      is_twin_cities, ecrv_id, sale_date, sale_year, sale_month, gross_sale_price,
      downpayment_equity, seller_paid_points, special_assessment_amount, finance_type,
      deed_type, schema_variant, encoding, parse_recovered, recovery_method,
      json_extract(transaction_json, '$.principal_residence') AS principal_residence,
      json_extract(transaction_json, '$.new_buildings_sale_year') AS new_buildings_sale_year,
      json_extract(transaction_json, '$.what_included') AS what_included,
      json_extract(transaction_json, '$.personal_property_included') AS personal_property_included,
      json_extract(transaction_json, '$.related') AS related,
      json_extract(transaction_json, '$.gift') AS gift,
      json_extract(transaction_json, '$.government') AS government,
      json_extract(transaction_json, '$.legal_action') AS legal_action,
      json_extract(transaction_json, '$.name_change') AS name_change,
      json_extract(transaction_json, '$.non_market_price') AS non_market_price,
      json_extract(transaction_json, '$.non_listed') AS non_listed,
      json_extract(transaction_json, '$.tax_exempt') AS tax_exempt,
      json_extract(transaction_json, '$.buyer_part_interest') AS buyer_part_interest,
      json_extract(transaction_json, '$.deed_payoff') AS deed_payoff,
      json_extract(transaction_json, '$.agreement2_yrs_old') AS agreement2_yrs_old,
      json_extract(transaction_json, '$.like_kind_exchange') AS like_kind_exchange,
      json_extract(transaction_json, '$.received_in_trade') AS received_in_trade,
      revision_conflict, first_extract_timestamp, extract_timestamp, archive_name,
      member_name, version_id"""
    _write_query(database, f"SELECT {transaction_columns} FROM current_transactions ORDER BY sale_date, source_key",
                 processed_dir / "ecrv_transactions.csv")
    _write_query(database, """SELECT c.version_id, c.child_type, c.ordinal, c.row_json
      FROM child_rows c JOIN current_transactions t USING (version_id)
      ORDER BY c.child_type, c.version_id, c.ordinal""", processed_dir / "ecrv_children.csv")
    child_columns = {
        "parcels": ("parcel", ("id", "parcelId", "primary")),
        "addresses": ("address", ("id", "city", "street1", "street2", "zip")),
        "uses": ("use", ("use_timing", "id", "tier1Cde", "tier2Cde", "tier3Cde",
                         "primaryInd", "propertyTypeCode", "propertyUseCode")),
        "financing": ("financing", ("id", "selected", "contractMortgageAmt", "interestRate",
                                    "interestRateType", "monthlyPaymentAmt", "numberPayments",
                                    "paymentFor", "paymentType", "paymentTypeOther",
                                    "balloonPaymentAmt", "balloonPaymentDate")),
        "personal_property": ("personal_property", ("id", "selected", "propertyDescription",
                                                    "propertyValue")),
    }
    for filename, (child_type, fields) in child_columns.items():
        extracts = ", ".join(
            f"json_extract(c.row_json, '$.{field}') AS \"{field}\"" for field in fields
        )
        _write_query(database, f"""SELECT c.version_id, t.source_key, c.ordinal, {extracts}
          FROM child_rows c JOIN current_transactions t USING (version_id)
          WHERE c.child_type='{child_type}' ORDER BY t.source_key, c.ordinal""",
          processed_dir / f"ecrv_{filename}.csv")
    _write_query(database, f"""SELECT q.archive_name, q.member_ordinal, q.member_name,
      q.raw_member_sha256, q.issue_code, q.severity, q.recovery_method
      FROM quality_events q JOIN ingest_batches b USING (batch_id)
      WHERE b.parser_version='{PARSER_VERSION}'
      ORDER BY q.archive_name, q.member_ordinal, q.issue_code""",
      quality_dir / "ecrv_quality_events.csv")
    _write_query(database, f"""SELECT coalesce(substr(b.extract_timestamp,1,4), 'unknown') AS extract_year,
      CASE WHEN q.member_name GLOB '[0-9][0-9]_*'
           THEN substr(q.member_name, 1, instr(q.member_name, '_') - 1)
           ELSE 'unknown' END AS mn_county_code,
      q.issue_code, q.severity, count(*) AS records
      FROM quality_events q JOIN ingest_batches b USING (batch_id)
      WHERE b.parser_version='{PARSER_VERSION}'
      GROUP BY 1,2,3,4 ORDER BY 1,2,3,4""", quality_dir / "ecrv_quality_summary.csv")
    _write_query(database, f"""SELECT archive_name, archive_sha256, archive_bytes,
      extract_timestamp, substr(extract_timestamp,1,4) AS extract_year, status,
      member_count, valid_count, recovered_count, error_count, parser_version
      FROM ingest_batches WHERE parser_version='{PARSER_VERSION}'
      ORDER BY extract_timestamp, archive_name""",
      quality_dir / "ecrv_archive_coverage.csv")
    _write_query(database, f"""SELECT sale_year, mn_county_code, county_name,
      schema_variant, count(*) AS current_transactions,
      sum(parse_recovered) AS recovered_transactions,
      sum(revision_conflict) AS revision_conflicts
      FROM current_transactions
      GROUP BY sale_year, mn_county_code, county_name, schema_variant
      ORDER BY sale_year, mn_county_code, schema_variant""",
      quality_dir / "ecrv_schema_counts.csv")

    lag_rows = list(database.execute("""SELECT sale_year, mn_county_code, county_name,
      sale_date, substr(first_extract_timestamp,1,10) AS extract_date
      FROM current_transactions WHERE first_extract_timestamp IS NOT NULL"""))
    lag_groups = {}
    for sale_year, county_code, county_name, sale_date, extract_date in lag_rows:
        try:
            lag = (datetime.fromisoformat(extract_date).date()
                   - datetime.fromisoformat(sale_date).date()).days
        except (TypeError, ValueError):
            continue
        lag_groups.setdefault((sale_year, county_code, county_name), []).append(lag)
    lag_path = quality_dir / "ecrv_reporting_lag.csv"
    lag_temporary = lag_path.with_suffix(lag_path.suffix + ".tmp")
    try:
        with lag_temporary.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(("sale_year", "mn_county_code", "county_name", "records",
                             "lag_days_median", "lag_days_p95", "lag_days_max"))
            for key, values in sorted(lag_groups.items()):
                ordered = sorted(values)
                median = ordered[(len(ordered) - 1) // 2]
                p95 = ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]
                writer.writerow((*key, len(ordered), median, p95, ordered[-1]))
        os.replace(lag_temporary, lag_path)
    finally:
        if lag_temporary.exists():
            lag_temporary.unlink()

    batches = list(database.execute(f"""SELECT archive_name, archive_sha256,
      extract_timestamp, status, member_count, valid_count, recovered_count,
      error_count FROM ingest_batches WHERE parser_version='{PARSER_VERSION}'
      ORDER BY extract_timestamp, archive_name"""))
    schema_counts = {
        row[0]: row[1] for row in database.execute(
            "SELECT schema_variant, count(*) FROM current_transactions GROUP BY schema_variant"
        )
    }
    manifest = {
        "parser_version": PARSER_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "archive_count": len(batches),
        "archives": [
            {
                "archive_name": row[0], "sha256": row[1],
                "extract_timestamp": row[2], "status": row[3],
                "member_count": row[4], "valid_count": row[5],
                "recovered_count": row[6], "error_count": row[7],
            }
            for row in batches
        ],
        "schema_counts": schema_counts,
        "totals": {
            "current_transactions": database.execute(
                "SELECT count(*) FROM current_transactions"
            ).fetchone()[0],
            "twin_cities_transactions": database.execute(
                "SELECT count(*) FROM current_transactions WHERE is_twin_cities=1"
            ).fetchone()[0],
            "recovered_transactions": database.execute(
                "SELECT count(*) FROM current_transactions WHERE parse_recovered=1"
            ).fetchone()[0],
            "revision_conflicts": database.execute(
                "SELECT count(*) FROM current_transactions WHERE revision_conflict=1"
            ).fetchone()[0],
        },
    }
    manifest_path = quality_dir / "ecrv_ingestion_manifest.json"
    temporary_manifest = manifest_path.with_suffix(".json.tmp")
    temporary_manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary_manifest, manifest_path)
    return {
        "transactions": database.execute("SELECT count(*) FROM current_transactions").fetchone()[0],
        "recovered": database.execute("SELECT count(*) FROM current_transactions WHERE parse_recovered=1").fetchone()[0],
        "quarantined": database.execute(f"""SELECT count(*) FROM quality_events q
          JOIN ingest_batches b USING (batch_id)
          WHERE q.severity='error' AND b.parser_version='{PARSER_VERSION}'""").fetchone()[0],
    }
