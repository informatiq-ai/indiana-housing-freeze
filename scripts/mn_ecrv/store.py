"""Standard-library SQLite registry and version store for Minnesota eCRV."""
import csv
import json
import sqlite3

from . import PARSER_VERSION


def connect(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    database = sqlite3.connect(path)
    database.execute("PRAGMA foreign_keys=ON")
    database.execute("PRAGMA journal_mode=WAL")
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
    version_id = f"{record.raw_sha256}:{PARSER_VERSION}"
    t = record.transaction
    database.execute("""
        INSERT OR IGNORE INTO record_versions VALUES (
          ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
        )
    """, [version_id, t["source_key"], record.raw_sha256, PARSER_VERSION,
          record.analytical_hash, record.schema_variant, record.encoding,
          record.parse_recovered, record.recovery_method, t["mn_county_code"],
          t["county_name"], t["county_fips"], t["is_twin_cities"], t["ecrv_id"],
          t["sale_date"], t["sale_year"], t["sale_month"], t["gross_sale_price"],
          t["downpayment_equity"], t["seller_paid_points"], t["special_assessment_amount"],
          t["finance_type"], t["deed_type"], json.dumps(t, sort_keys=True)])
    for child_type, rows in (("parcel", record.parcels), ("address", record.addresses),
                             ("use", record.uses), ("financing", record.financing),
                             ("personal_property", record.personal_property)):
        for ordinal, row in enumerate(rows, 1):
            database.execute("INSERT OR IGNORE INTO child_rows VALUES (?,?,?,?)",
                             [version_id, child_type, ordinal, json.dumps(row, sort_keys=True)])
    return version_id


def refresh_views(database):
    database.execute("DROP VIEW IF EXISTS current_transactions")
    database.execute("""
      CREATE VIEW current_transactions AS
      WITH conflicts AS (
        SELECT o.source_key, b.extract_timestamp
        FROM record_observations o
        JOIN ingest_batches b USING (batch_id)
        JOIN record_versions v USING (version_id)
        GROUP BY o.source_key, b.extract_timestamp
        HAVING count(DISTINCT v.analytical_hash) > 1
      ), candidates AS (
        SELECT v.*, b.extract_timestamp, b.archive_name, o.member_name,
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
      )
      SELECT * FROM candidates WHERE selection_rank=1
    """)


def _write_query(database, query, path):
    cursor = database.execute(query)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(column[0] for column in cursor.description)
        while True:
            rows = cursor.fetchmany(10_000)
            if not rows:
                break
            writer.writerows(rows)


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
      revision_conflict, extract_timestamp, archive_name, member_name, version_id"""
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
    _write_query(database, """SELECT archive_name, member_ordinal, member_name,
      raw_member_sha256, issue_code, severity, recovery_method
      FROM quality_events ORDER BY archive_name, member_ordinal, issue_code""",
      quality_dir / "ecrv_quality_events.csv")
    _write_query(database, """SELECT coalesce(substr(b.extract_timestamp,1,4), 'unknown') AS extract_year,
      CASE WHEN q.member_name GLOB '[0-9][0-9]_*'
           THEN substr(q.member_name, 1, instr(q.member_name, '_') - 1)
           ELSE 'unknown' END AS mn_county_code,
      q.issue_code, q.severity, count(*) AS records
      FROM quality_events q LEFT JOIN ingest_batches b USING (batch_id)
      GROUP BY 1,2,3,4 ORDER BY 1,2,3,4""", quality_dir / "ecrv_quality_summary.csv")
    return {
        "transactions": database.execute("SELECT count(*) FROM current_transactions").fetchone()[0],
        "recovered": database.execute("SELECT count(*) FROM current_transactions WHERE parse_recovered=1").fetchone()[0],
        "quarantined": database.execute("SELECT count(*) FROM quality_events WHERE severity='error'").fetchone()[0],
    }
