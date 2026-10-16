"""Bridge audited legacy Indiana rows into the established SDF contract."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


LEGACY_START_YEAR = 2015
LEGACY_END_YEAR = 2020

HISTORY_COLUMNS = [
    "source_format",
    "source_year",
    "sdf_id",
    "county",
    "sale_date",
    "sale_year",
    "sale_month",
    "gross_sale_price",
    "property_zip",
    "dom_reported",
    "eligible_current_study",
]

ESTABLISHED_COLUMNS = [
    "SDF_ID",
    "county",
    "year",
    "month",
    "sale_date",
    "sale_price",
    "dom_reported",
    "data_year",
    "zip_code",
]


def load_legacy_backfill(path: Path) -> tuple[pd.DataFrame, dict[str, int]]:
    """Return eligible 2015-2020 rows in the established pipeline schema.

    The independent historical normalizer remains authoritative for legacy
    parsing, duplicate handling, and eligibility. Rows without a usable ZIP
    are excluded to match the established pipeline's final-output invariant.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"Missing audited Indiana history: {path}. Run "
            "scripts/00_indiana_sdf_pipeline.py before the established pipeline."
        )

    history = pd.read_csv(
        path,
        usecols=HISTORY_COLUMNS,
        dtype={
            "source_format": "string",
            "sdf_id": "string",
            "county": "string",
            "sale_date": "string",
            "sale_month": "string",
            "property_zip": "string",
        },
        low_memory=False,
    )
    legacy = history[
        history["source_format"].eq("legacy_pipe_v1")
        & history["source_year"].between(LEGACY_START_YEAR, LEGACY_END_YEAR)
        & history["eligible_current_study"].eq(True)  # noqa: E712
    ].copy()

    eligible_rows = len(legacy)
    legacy = legacy[legacy["property_zip"].notna()].copy()
    legacy["property_zip"] = legacy["property_zip"].str.strip().str.zfill(5)
    valid_zip = legacy["property_zip"].str.fullmatch(r"\d{5}", na=False)
    legacy = legacy[valid_zip & legacy["property_zip"].ne("00000")].copy()

    legacy["month"] = pd.to_numeric(
        legacy["sale_month"].str.slice(5, 7), errors="coerce"
    ).astype("Int64")
    legacy = legacy.rename(
        columns={
            "sdf_id": "SDF_ID",
            "sale_year": "year",
            "gross_sale_price": "sale_price",
            "source_year": "data_year",
            "property_zip": "zip_code",
        }
    )
    result = legacy[ESTABLISHED_COLUMNS].copy()

    if result["SDF_ID"].isna().any() or result["SDF_ID"].duplicated().any():
        raise AssertionError("Legacy backfill must contain unique non-null SDF_ID values")
    if not result["year"].between(LEGACY_START_YEAR, LEGACY_END_YEAR).all():
        raise AssertionError("Legacy backfill contains a sale outside 2015-2020")
    if not result["year"].eq(result["data_year"]).all():
        raise AssertionError("Legacy backfill sale year does not match its source year")

    audit = {
        "eligible_legacy_rows": int(eligible_rows),
        "legacy_rows_with_valid_zip": int(len(result)),
        "legacy_rows_excluded_for_zip": int(eligible_rows - len(result)),
    }
    return result, audit
