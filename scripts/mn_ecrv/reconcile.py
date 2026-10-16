"""Read-only reconciliation of the Minnesota eCRV store.

Accounts for every archive member under the current parser, separates exact
repeats from substantive revisions across weekly extracts, classifies gaps
between extracts, and bridges current transactions to the research funnel.
Writes aggregate CSVs only; no party data or free text leaves the store.
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path

import pandas as pd

from . import PARSER_VERSION

# Child tables included in the analytical hash. A changed property-use row can
# move a sale into or out of the single-family cohort, so each is reported.
CHILD_TYPES = ("parcel", "address", "use", "financing", "personal_property")
NORMAL_GAP_DAYS = 7
# A weekly run that slips by up to three days still covers its week; a larger
# gap leaves at least one weekly window without its own extract.
PROBABLE_MISSING_GAP_DAYS = 10


def _atomic_csv(frame, path):
    """Write a CSV through a temporary file so readers never see partial output."""
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False)
    os.replace(temporary, path)


def load_observations(database, parser_version=PARSER_VERSION):
    """Return one row per archive member observation under the given parser."""
    return pd.read_sql_query(
        """SELECT o.batch_id, o.member_ordinal, o.source_key, o.version_id,
                  v.analytical_hash, v.sale_year, v.is_twin_cities,
                  b.extract_timestamp, b.archive_name
           FROM record_observations o
           JOIN ingest_batches b USING (batch_id)
           JOIN record_versions v USING (version_id)
           WHERE b.parser_version = ? AND v.parser_version = ?
             AND b.status IN ('complete', 'incomplete')""",
        database, params=[parser_version, parser_version],
    )


def classify_observations(observations):
    """Label each observation first_seen, repeat_identical, or repeat_revised.

    Ordering matches the current_transactions view: extract timestamp, archive
    name, then member ordinal. A repeat is revised when its analytical hash
    differs from the immediately preceding observation of the same key.
    """
    ordered = observations.sort_values(
        ["source_key", "extract_timestamp", "archive_name", "member_ordinal"]
    ).reset_index(drop=True)
    previous_key = ordered["source_key"].shift()
    previous_hash = ordered["analytical_hash"].shift()
    first = ordered["source_key"] != previous_key
    revised = ~first & (ordered["analytical_hash"] != previous_hash)
    ordered["observation_class"] = "repeat_identical"
    ordered.loc[first, "observation_class"] = "first_seen"
    ordered.loc[revised, "observation_class"] = "repeat_revised"
    return ordered


def extract_year_reconciliation(batches, ordered, events):
    """Build the per-extract-year member accounting table."""
    batches = batches.assign(extract_year=batches["extract_timestamp"].str[:4])
    per_batch_obs = ordered.groupby("batch_id").size().rename("observations")
    per_batch_errors = (
        events[events["severity"] == "error"].groupby("batch_id").size()
        .rename("error_events")
    )
    batches = batches.join(per_batch_obs, on="batch_id").join(per_batch_errors, on="batch_id")
    batches[["observations", "error_events"]] = batches[["observations", "error_events"]].fillna(0)

    ordered = ordered.assign(extract_year=ordered["extract_timestamp"].str[:4])
    classes = (
        ordered.pivot_table(index="extract_year", columns="observation_class",
                            values="source_key", aggfunc="size", fill_value=0)
        .reindex(columns=["first_seen", "repeat_identical", "repeat_revised"], fill_value=0)
    )
    codes = events.merge(batches[["batch_id", "extract_year"]], on="batch_id")
    codes = codes[codes["severity"] == "error"].pivot_table(
        index="extract_year", columns="issue_code", values="batch_id",
        aggfunc="size", fill_value=0,
    ).add_prefix("quarantined_")

    table = batches.groupby("extract_year").agg(
        archives=("batch_id", "size"),
        incomplete_archives=("status", lambda s: int((s == "incomplete").sum())),
        members=("member_count", "sum"),
        valid=("valid_count", "sum"),
        quarantined=("error_count", "sum"),
        recovered=("recovered_count", "sum"),
        observations=("observations", "sum"),
        error_events=("error_events", "sum"),
    )
    table = table.join(classes).join(codes).fillna(0)
    table["members_balance"] = table["members"] == table["valid"] + table["quarantined"]
    table["observations_match_valid"] = table["observations"] == table["valid"]
    table["quarantine_events_match"] = table["error_events"] == table["quarantined"]
    numeric = table.columns.difference(
        ["members_balance", "observations_match_valid", "quarantine_events_match"]
    )
    table[numeric] = table[numeric].astype("int64")
    return table.reset_index()


def revision_summary(database, ordered):
    """Count revised transactions by current sale year, geography, and changed field."""
    revised_keys = ordered.loc[ordered["observation_class"] == "repeat_revised", "source_key"].unique()
    if len(revised_keys) == 0:
        return pd.DataFrame(columns=["sale_year", "is_twin_cities", "field", "transactions"])
    subset = ordered[ordered["source_key"].isin(revised_keys)]
    first = subset.groupby("source_key").head(1)
    current = subset.groupby("source_key").tail(1)
    version_ids = list(set(first["version_id"]) | set(current["version_id"]))
    payloads, children = {}, {}
    for start in range(0, len(version_ids), 500):
        chunk = version_ids[start:start + 500]
        marks = ",".join("?" * len(chunk))
        for version_id, payload in database.execute(
            f"SELECT version_id, transaction_json FROM record_versions WHERE version_id IN ({marks})",
            chunk,
        ):
            payloads[version_id] = json.loads(payload)
        for version_id, child_type, row_json in database.execute(
            f"""SELECT version_id, child_type, row_json FROM child_rows
                WHERE version_id IN ({marks}) ORDER BY version_id, child_type, ordinal""",
            chunk,
        ):
            children.setdefault((version_id, child_type), []).append(row_json)
    pairs = first[["source_key", "version_id"]].merge(
        current[["source_key", "version_id", "sale_year", "is_twin_cities"]],
        on="source_key", suffixes=("_first", "_current"),
    )
    rows = []
    for pair in pairs.itertuples(index=False):
        before, after = payloads[pair.version_id_first], payloads[pair.version_id_current]
        changed = [field for field in sorted(set(before) | set(after))
                   if before.get(field) != after.get(field)]
        changed += [
            f"child_{child_type}" for child_type in CHILD_TYPES
            if children.get((pair.version_id_first, child_type))
            != children.get((pair.version_id_current, child_type))
        ]
        for field in changed or ["unexplained"]:
            rows.append((pair.sale_year, pair.is_twin_cities, field, pair.source_key))
        rows.append((pair.sale_year, pair.is_twin_cities, "any_revision", pair.source_key))
    detail = pd.DataFrame(rows, columns=["sale_year", "is_twin_cities", "field", "source_key"])
    return (
        detail.groupby(["sale_year", "is_twin_cities", "field"])["source_key"].nunique()
        .rename("transactions").reset_index()
    )


def extract_gaps(batches):
    """Classify the spacing between consecutive weekly extracts."""
    frame = batches.assign(
        extract_date=pd.to_datetime(batches["extract_timestamp"]).dt.normalize()
    ).sort_values(["extract_date", "archive_name"]).reset_index(drop=True)
    frame["gap_days"] = frame["extract_date"].diff().dt.days
    # Median member count of the four archives either side gauges whether a
    # late extract absorbed extra filings.
    neighbors = frame["member_count"].rolling(9, center=True, min_periods=3).median()
    frame["neighbor_median_members"] = neighbors
    frame["members_to_neighbors"] = (frame["member_count"] / neighbors).round(3)
    frame["weekday"] = frame["extract_date"].dt.day_name()
    frame["gap_class"] = "normal"
    frame.loc[frame["gap_days"] > NORMAL_GAP_DAYS, "gap_class"] = "delayed_run"
    frame.loc[frame["gap_days"] > PROBABLE_MISSING_GAP_DAYS, "gap_class"] = "probable_missing_week"
    frame.loc[frame["gap_days"] == 0, "gap_class"] = "same_day_extract"
    frame.loc[frame["gap_days"].isna(), "gap_class"] = "first_extract"
    gaps = frame[frame["gap_class"] != "normal"]
    return gaps[[
        "archive_name", "extract_date", "weekday", "gap_days", "gap_class",
        "member_count", "neighbor_median_members", "members_to_neighbors",
    ]]


def sale_year_bridge(ordered, funnel_path, start_year, end_year):
    """Compare current Twin Cities transactions with the research funnel by sale year."""
    current = ordered.groupby("source_key").tail(1)
    store = (
        current[(current["is_twin_cities"] == 1)
                & current["sale_year"].between(start_year, end_year)]
        .groupby("sale_year").size().rename("store_current_twin_cities")
    )
    bridge = store.to_frame()
    if funnel_path is not None and Path(funnel_path).exists():
        funnel = pd.read_csv(funnel_path)
        funnel = funnel[funnel["source_state"] == "MN"]
        totals = funnel.groupby("sale_year")[[
            "normalized_records", "single_family_records", "current_eligible_records",
            "strict_eligible_records", "research_eligible_records",
        ]].sum()
        bridge = bridge.join(totals, how="outer").fillna(0).astype("int64")
        bridge["store_matches_funnel"] = (
            bridge["store_current_twin_cities"] == bridge["normalized_records"]
        )
    return bridge.reset_index()


def reconcile(database, quality_dir, funnel_path=None, start_year=2015, end_year=2025,
              parser_version=PARSER_VERSION):
    """Write reconciliation tables and return a summary with pass/fail checks."""
    quality_dir = Path(quality_dir)
    quality_dir.mkdir(parents=True, exist_ok=True)
    batches = pd.read_sql_query(
        """SELECT batch_id, archive_name, extract_timestamp, status, member_count,
                  valid_count, recovered_count, error_count
           FROM ingest_batches WHERE parser_version = ?
             AND status IN ('complete', 'incomplete')""",
        database, params=[parser_version],
    )
    events = pd.read_sql_query(
        """SELECT q.batch_id, q.issue_code, q.severity FROM quality_events q
           JOIN ingest_batches b USING (batch_id) WHERE b.parser_version = ?""",
        database, params=[parser_version],
    )
    ordered = classify_observations(load_observations(database, parser_version))

    by_year = extract_year_reconciliation(batches, ordered, events)
    revisions = revision_summary(database, ordered)
    gaps = extract_gaps(batches)
    bridge = sale_year_bridge(ordered, funnel_path, start_year, end_year)

    _atomic_csv(by_year, quality_dir / "ecrv_reconciliation_by_extract_year.csv")
    _atomic_csv(revisions, quality_dir / "ecrv_revision_summary.csv")
    _atomic_csv(gaps, quality_dir / "ecrv_extract_gaps.csv")
    _atomic_csv(bridge, quality_dir / "ecrv_sale_year_bridge.csv")

    class_counts = ordered["observation_class"].value_counts()
    checks = {
        "members_balance_every_year": bool(by_year["members_balance"].all()),
        "observations_match_valid_every_year": bool(by_year["observations_match_valid"].all()),
        "quarantine_events_match_every_year": bool(by_year["quarantine_events_match"].all()),
        "no_probable_missing_weeks": bool((gaps["gap_class"] != "probable_missing_week").all()),
    }
    if "store_matches_funnel" in bridge:
        checks["store_matches_research_funnel"] = bool(bridge["store_matches_funnel"].all())
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "parser_version": parser_version,
        "archives": int(len(batches)),
        "observations": int(len(ordered)),
        "distinct_transactions": int(ordered["source_key"].nunique()),
        "first_seen": int(class_counts.get("first_seen", 0)),
        "repeat_identical": int(class_counts.get("repeat_identical", 0)),
        "repeat_revised": int(class_counts.get("repeat_revised", 0)),
        "revised_transactions": int(
            ordered.loc[ordered["observation_class"] == "repeat_revised", "source_key"].nunique()
        ),
        "checks": checks,
    }
    (quality_dir / "ecrv_reconciliation_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    return summary
