#!/usr/bin/env python3
"""Build the harmonized 2015-2025 Indianapolis/Twin Cities transactions."""

import argparse
import json
from pathlib import Path
import sys

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mn_ecrv.store import connect, export_research_parquet
from longitudinal import run_prepare


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument(
        "--indiana", type=Path, default=Path("data/processed/indiana_sdf_history.csv")
    )
    parser.add_argument(
        "--minnesota-dir", type=Path,
        default=Path("data/processed/mn/research_extract")
    )
    parser.add_argument(
        "--minnesota-database", type=Path,
        default=Path("data/intermediate/mn/ecrv.sqlite")
    )
    parser.add_argument(
        "--refresh-minnesota-extract", action="store_true",
        help="rebuild the filtered Parquet extract even if its archive snapshot matches",
    )
    parser.add_argument(
        "--output", type=Path, default=Path("data/processed/research/transactions.csv")
    )
    parser.add_argument(
        "--quality-dir", type=Path, default=Path("outputs/research/quality")
    )
    args = parser.parse_args()
    database = connect(args.minnesota_database)
    try:
        extract = export_research_parquet(
            database, args.minnesota_dir, args.start_year, args.end_year,
            reuse_if_current=not args.refresh_minnesota_extract,
        )
    finally:
        database.close()
    print(json.dumps({
        "minnesota_parquet_cached": extract["cached"],
        "minnesota_parquet_rows": extract["rows"],
    }, indent=2, sort_keys=True))
    manifest = run_prepare(
        args.indiana, args.minnesota_dir, args.output, args.quality_dir,
        args.start_year, args.end_year,
    )
    print(json.dumps(manifest["totals"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
