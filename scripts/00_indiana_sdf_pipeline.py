#!/usr/bin/env python3
"""Build the audited 2015-present Indiana SDF transaction history."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from indiana_sdf.pipeline import run_pipeline


def parse_years(values):
    """Expand repeated years and inclusive YEAR:YEAR ranges."""
    if not values:
        return None
    years = set()
    for value in values:
        if ":" in value:
            start, end = (int(part) for part in value.split(":", 1))
            if end < start:
                raise argparse.ArgumentTypeError(f"Invalid descending year range: {value}")
            years.update(range(start, end + 1))
        else:
            years.add(int(value))
    return sorted(years)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path,
                        default=Path("data/processed/indiana_sdf_history.csv"))
    parser.add_argument("--quality-dir", type=Path,
                        default=Path("outputs/indiana/quality"))
    parser.add_argument("--year", action="append",
                        help="year or inclusive YEAR:YEAR range; may be repeated")
    args = parser.parse_args()
    manifest = run_pipeline(args.input_dir, args.output, args.quality_dir,
                            parse_years(args.year))
    print(json.dumps(manifest["totals"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

