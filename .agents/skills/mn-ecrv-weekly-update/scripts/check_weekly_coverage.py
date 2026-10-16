#!/usr/bin/env python3
"""Report Minnesota eCRV weekly-extract coverage and quality after an update.

Reads the ingestion quality exports and flags probable missing weeks, archives
with quarantined members, error or recovery rates above the prior-year
baseline, and schema variants first observed in the review window. Exits 1
when a finding needs a human decision.
"""

import argparse
from pathlib import Path
import sys

import pandas as pd

QUALITY_DIR = Path("outputs/mn/quality")
PROBABLE_MISSING_WEEK_DAYS = 10
RATE_MULTIPLIER_ALERT = 2.0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", required=True, help="review window start, YYYY-MM-DD")
    parser.add_argument("--quality-dir", type=Path, default=QUALITY_DIR)
    args = parser.parse_args()
    since = pd.Timestamp(args.since)
    alerts = []

    coverage = pd.read_csv(args.quality_dir / "ecrv_archive_coverage.csv")
    coverage["extract_date"] = pd.to_datetime(coverage["extract_timestamp"]).dt.normalize()
    coverage = coverage.sort_values("extract_date").reset_index(drop=True)
    coverage["gap_days"] = coverage["extract_date"].diff().dt.days
    window = coverage[coverage["extract_date"] >= since]
    prior = coverage[
        (coverage["extract_date"] < since)
        & (coverage["extract_date"] >= since - pd.DateOffset(years=1))
    ]

    latest = coverage["extract_date"].max()
    age = (pd.Timestamp.today().normalize() - latest).days
    print(f"Archives in window: {len(window)} (total {len(coverage)})")
    print(f"Latest extract: {latest.date()} ({age} days ago)")
    if age > 14:
        # Informational: the store may simply not have been refreshed yet.
        print(f"NOTE: about {age // 7} weekly extract(s) may be available but not yet added")

    gaps = window[window["gap_days"] > 7]
    for _, row in gaps.iterrows():
        kind = "PROBABLE MISSING WEEK" if row["gap_days"] > PROBABLE_MISSING_WEEK_DAYS else "delayed run"
        print(f"Gap {int(row['gap_days'])} days before {row['archive_name']}: {kind}")
        if row["gap_days"] > PROBABLE_MISSING_WEEK_DAYS:
            alerts.append("missing week")

    incomplete = window[window["error_count"] > 0]
    for _, row in incomplete.iterrows():
        print(f"Quarantined: {row['archive_name']} has {int(row['error_count'])} error member(s)")

    def rates(frame):
        members = frame["member_count"].sum()
        if members == 0:
            return float("nan"), float("nan")
        return frame["error_count"].sum() / members, frame["recovered_count"].sum() / members

    window_error, window_recovered = rates(window)
    prior_error, prior_recovered = rates(prior)
    print(f"Error rate: window {window_error:.4%}, prior year {prior_error:.4%}")
    print(f"Recovered rate: window {window_recovered:.4%}, prior year {prior_recovered:.4%}")
    for label, current, baseline in (
        ("error", window_error, prior_error),
        ("recovered", window_recovered, prior_recovered),
    ):
        # A zero baseline makes any nonzero rate an alert only for errors.
        if baseline > 0 and current > RATE_MULTIPLIER_ALERT * baseline:
            alerts.append(f"{label} rate above baseline")
            print(f"ALERT: {label} rate is more than {RATE_MULTIPLIER_ALERT}x the prior year")
        elif baseline == 0 and label == "error" and current > 0:
            alerts.append("errors where prior year had none")
            print("ALERT: errors in window where the prior year had none")

    schema = pd.read_csv(args.quality_dir / "ecrv_schema_counts.csv")
    first_year = schema.groupby("schema_variant")["sale_year"].min()
    new_variants = first_year[first_year >= since.year]
    for variant, year in new_variants.items():
        print(f"ALERT: schema variant {variant} first appears in sale year {year}")
        alerts.append("new schema variant")

    print(f"{len(alerts)} alert(s)")
    return 1 if alerts else 0


if __name__ == "__main__":
    sys.exit(main())
