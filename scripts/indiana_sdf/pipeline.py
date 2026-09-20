"""Normalize legacy and modern Indiana Sales Disclosure Form extracts.

The module deliberately reads only analytical fields. Buyer, seller, contact,
mailing-address, and title-company fields never enter the normalized frames.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Iterable

import pandas as pd

from . import PARSER_VERSION


MIN_PRICE = 50_000
MAX_PRICE = 15_000_000

COUNTIES = {
    "06": {"county": "Boone", "county_fips": "18011", "tier_type": "SUBURBAN_COLLAR"},
    "29": {"county": "Hamilton", "county_fips": "18057", "tier_type": "SUBURBAN_COLLAR"},
    "32": {"county": "Hendricks", "county_fips": "18063", "tier_type": "SUBURBAN_COLLAR"},
    "41": {"county": "Johnson", "county_fips": "18081", "tier_type": "SUBURBAN_COLLAR"},
    "49": {"county": "Marion", "county_fips": "18097", "tier_type": "URBAN_CORE"},
}

LEGACY_REQUIRED = {
    "SDF_ID", "County_ID", "Conveyance_Date", "C6_Sales_Price", "PropZip",
    "Parcel1", "Parcel2", "Parcel3", "P2_6_Prop_Class_Code",
    "P2_16_Valid_Trending", "P2_17_Validation_Complete",
}
LEGACY_OPTIONAL = {
    "B3_Vacant_Land_Assessor", "B4_Trade_Assessor",
    "B7_Relationship_Assessor", "B8_Land_Contract_Assessor",
    "B11_Partial_Interest_Assessor", "B14_Charity_Assessor",
    "Foreclosure", "Quitclaim",
}
MODERN_REQUIRED = {
    "SDF_ID", "County_ID", "C7_Conveyance_Date", "E1_Sales_Price",
    "B1_Valuable_Consider", "C1_Sheriff_Sale", "C2_Short_Sale",
    "C3_Quitclaim", "C10_Residential_Property",
    "C10_Agricultural_Property", "C10_Commercial_Property",
    "C10_Industrial_Property", "P2_16_Valid_Trending",
    "P2_17_Validation_Complete",
}
MODERN_OPTIONAL = {"C8_Market_Days", "B4_Trade", "B6_Partial_Interest", "B10_Charity"}
PARCEL_REQUIRED = {
    "SDF_ID", "Parcel_Instance_No", "A1_Parcel_Number", "A3_Land",
    "A4_Improvement", "A5_ZipCode", "P2_6_Prop_Class_Code",
}

OUTPUT_COLUMNS = [
    "source_key", "source_format", "source_year", "source_file", "sdf_id",
    "county_dlgf_code", "county", "county_fips", "metro", "tier_type",
    "sale_date", "sale_year", "sale_month", "gross_sale_price",
    "property_zip", "parcel_count", "property_class_codes", "dom_reported",
    "validation_complete", "valid_for_trending", "valuable_consideration",
    "residential_property", "agricultural_property", "commercial_property",
    "industrial_property", "vacant_land", "trade", "related_party",
    "land_contract", "partial_interest", "charity_transfer", "sheriff_sale",
    "short_sale", "quitclaim", "all_parcels_improved_residential",
    "eligible_current_study", "eligible_strict_comparable",
    "exclusion_reasons_current", "exclusion_reasons_strict",
]
PRE_ELIGIBILITY_COLUMNS = [column for column in OUTPUT_COLUMNS if column not in {
    "eligible_current_study", "eligible_strict_comparable",
    "exclusion_reasons_current", "exclusion_reasons_strict",
}]

COMPARISON_COLUMNS = [column for column in OUTPUT_COLUMNS if column not in {
    "source_key", "source_year", "source_file", "eligible_current_study",
    "eligible_strict_comparable", "exclusion_reasons_current",
    "exclusion_reasons_strict",
}]

QUALITY_COLUMNS = [
    "source_year", "source_format", "source_file", "county", "source_key",
    "issue_code", "severity", "record_count", "details",
]


@dataclass(frozen=True)
class SourceSpec:
    year: int
    source_format: str
    sales_path: Path
    parcel_path: Path | None = None


def _header(path: Path, encoding: str, separator: str) -> list[str]:
    with path.open("r", encoding=encoding, newline="") as stream:
        first_line = stream.readline().rstrip("\r\n")
    return [value.strip().strip('"') for value in first_line.split(separator)]


def detect_sdf_format(path: Path) -> str:
    """Return the supported SDF format identified from the file header."""
    errors = []
    for encoding, separator, source_format, required in (
        ("utf-16", "\t", "modern_multifile_v1", MODERN_REQUIRED),
        ("cp1252", "|", "legacy_pipe_v1", LEGACY_REQUIRED),
    ):
        try:
            fields = set(_header(path, encoding, separator))
        except UnicodeError as exc:
            errors.append(f"{encoding}: {exc}")
            continue
        if required.issubset(fields):
            return source_format
    raise ValueError(f"Unsupported Indiana SDF header in {path}: {'; '.join(errors)}")


def discover_sources(input_dir: Path) -> list[SourceSpec]:
    """Discover supported annual SDF sources without relying on year for format."""
    candidates = []
    for path in input_dir.iterdir():
        legacy_match = re.fullmatch(r"(\d{4})\.txt", path.name, re.I)
        modern_match = re.fullmatch(r"SALEDISC(\d{4})\.txt", path.name, re.I)
        if not path.is_file() or not (legacy_match or modern_match):
            continue
        year = int((legacy_match or modern_match).group(1))
        source_format = detect_sdf_format(path)
        parcel_path = None
        if source_format == "modern_multifile_v1":
            parcel_path = input_dir / f"SALEPARCEL{year}.txt"
            if not parcel_path.exists():
                raise FileNotFoundError(
                    f"Modern source {path.name} requires parcel partner {parcel_path.name}"
                )
            parcel_fields = set(_header(parcel_path, "utf-16", "\t"))
            missing = PARCEL_REQUIRED - parcel_fields
            if missing:
                raise ValueError(
                    f"Unsupported SALEPARCEL header in {parcel_path}: missing {sorted(missing)}"
                )
        candidates.append(SourceSpec(year, source_format, path, parcel_path))
    if not candidates:
        raise FileNotFoundError(f"No annual Indiana SDF files found in {input_dir}")
    duplicate_years = pd.Series([source.year for source in candidates]).duplicated(False)
    if duplicate_years.any():
        years = sorted({source.year for source, duplicate in zip(candidates, duplicate_years) if duplicate})
        raise ValueError(f"Multiple Indiana SDF transaction sources found for years {years}")
    return sorted(candidates, key=lambda source: source.year)


def normalize_zip(value) -> str | None:
    """Normalize a property ZIP to five digits, or return None."""
    if pd.isna(value):
        return None
    text = str(value).strip().split("-", 1)[0]
    if text.endswith(".0"):
        text = text[:-2]
    if not text.isdigit() or not 3 <= len(text) <= 5:
        return None
    text = text.zfill(5)
    return None if text == "00000" else text


def _flag(series: pd.Series) -> pd.Series:
    values = series.astype("string").str.strip().str.upper()
    result = values.map({"Y": True, "YES": True, "1": True,
                         "N": False, "NO": False, "0": False})
    return result.astype("boolean")


def _optional(frame: pd.DataFrame, name: str) -> pd.Series:
    if name in frame:
        return frame[name]
    return pd.Series(pd.NA, index=frame.index, dtype="string")


def _parse_dates(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", format="mixed")


def _is_improved_class(value: str) -> bool:
    return bool(re.fullmatch(r"5[1-9][0-9]", value))


def _county_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["county_dlgf_code"] = result["County_ID"].astype("string").str.strip().str.zfill(2)
    for column in ("county", "county_fips", "tier_type"):
        result[column] = result["county_dlgf_code"].map(
            {code: metadata[column] for code, metadata in COUNTIES.items()}
        )
    result["metro"] = "INDY"
    return result


def _base_frame(frame: pd.DataFrame, year: int, source_format: str, source_file: str,
                date_column: str, price_column: str, price_divisor: int) -> pd.DataFrame:
    result = _county_columns(frame)
    result["sdf_id"] = result["SDF_ID"].astype("string").str.strip()
    valid_id = result["sdf_id"].str.fullmatch(r"[A-Za-z0-9-]+", na=False)
    result["source_key"] = result["sdf_id"].where(valid_id).map(
        lambda value: f"IN:SDF:{value}" if pd.notna(value) else pd.NA
    )
    dates = _parse_dates(result[date_column])
    result["sale_date"] = dates.dt.strftime("%Y-%m-%d")
    result["sale_year"] = dates.dt.year.astype("Int64")
    result["sale_month"] = dates.dt.strftime("%Y-%m")
    result["gross_sale_price"] = pd.to_numeric(result[price_column], errors="coerce") / price_divisor
    result["source_format"] = source_format
    result["source_year"] = year
    result["source_file"] = source_file
    return result


def normalize_legacy_frame(frame: pd.DataFrame, year: int, source_file: str) -> pd.DataFrame:
    """Normalize an already-loaded legacy frame at transaction grain."""
    result = _base_frame(frame, year, "legacy_pipe_v1", source_file,
                         "Conveyance_Date", "C6_Sales_Price", 1)
    result["property_zip"] = result["PropZip"].map(normalize_zip)
    parcel_columns = [column for column in ("Parcel1", "Parcel2", "Parcel3") if column in result]
    result["parcel_count"] = result[parcel_columns].notna().sum(axis=1).astype("Int64")
    classes = result["P2_6_Prop_Class_Code"].astype("string").str.strip()
    result["property_class_codes"] = classes.replace("", pd.NA)
    result["all_parcels_improved_residential"] = classes.map(
        lambda value: _is_improved_class(value) if pd.notna(value) else False
    ).astype("boolean")
    result["dom_reported"] = pd.Series(pd.NA, index=result.index, dtype="Int64")
    result["validation_complete"] = _flag(result["P2_17_Validation_Complete"])
    result["valid_for_trending"] = _flag(result["P2_16_Valid_Trending"])
    result["valuable_consideration"] = pd.Series(pd.NA, index=result.index, dtype="boolean")
    result["residential_property"] = classes.str.fullmatch(r"5[0-9]{2}", na=False).astype("boolean")
    result["agricultural_property"] = classes.str.fullmatch(r"[1-2][0-9]{2}", na=False).astype("boolean")
    result["commercial_property"] = classes.str.fullmatch(r"4[0-9]{2}", na=False).astype("boolean")
    result["industrial_property"] = classes.str.fullmatch(r"3[0-9]{2}", na=False).astype("boolean")
    result["vacant_land"] = _flag(_optional(result, "B3_Vacant_Land_Assessor"))
    result["trade"] = _flag(_optional(result, "B4_Trade_Assessor"))
    result["related_party"] = _flag(_optional(result, "B7_Relationship_Assessor"))
    result["land_contract"] = _flag(_optional(result, "B8_Land_Contract_Assessor"))
    result["partial_interest"] = _flag(_optional(result, "B11_Partial_Interest_Assessor"))
    result["charity_transfer"] = _flag(_optional(result, "B14_Charity_Assessor"))
    result["sheriff_sale"] = _flag(_optional(result, "Foreclosure"))
    result["short_sale"] = pd.Series(pd.NA, index=result.index, dtype="boolean")
    result["quitclaim"] = _flag(_optional(result, "Quitclaim"))
    return result[PRE_ELIGIBILITY_COLUMNS]


def _aggregate_parcels(parcels: pd.DataFrame) -> pd.DataFrame:
    parcels = parcels.drop_duplicates().copy()
    parcels["_instance"] = pd.to_numeric(parcels["Parcel_Instance_No"], errors="coerce")
    parcels["_zip"] = parcels["A5_ZipCode"].map(normalize_zip)
    parcels["_class"] = parcels["P2_6_Prop_Class_Code"].astype("string").str.strip().replace("", pd.NA)
    parcels = parcels.sort_values(["SDF_ID", "_instance"], na_position="last")
    if parcels.empty:
        return pd.DataFrame(columns=["SDF_ID", "property_zip", "parcel_count",
                                     "property_class_codes", "all_parcels_improved_residential"])
    grouped = parcels.groupby("SDF_ID", sort=False, dropna=False)
    summary = pd.DataFrame({
        "parcel_count": grouped.size(),
        "property_zip": grouped["_zip"].first(),
    })
    unique_classes = (
        parcels[["SDF_ID", "_class"]]
        .dropna(subset=["_class"])
        .drop_duplicates()
        .sort_values(["SDF_ID", "_class"])
    )
    if unique_classes.empty:
        summary["property_class_codes"] = None
        summary["all_parcels_improved_residential"] = False
    else:
        class_groups = unique_classes.groupby("SDF_ID", sort=False)["_class"]
        summary["property_class_codes"] = class_groups.agg(";".join)
        unique_classes["_improved"] = unique_classes["_class"].map(_is_improved_class)
        summary["all_parcels_improved_residential"] = unique_classes.groupby(
            "SDF_ID", sort=False
        )["_improved"].all()
        summary["all_parcels_improved_residential"] = summary[
            "all_parcels_improved_residential"
        ].fillna(False)
    return summary.reset_index()


def normalize_modern_frames(sales: pd.DataFrame, parcels: pd.DataFrame, year: int,
                            source_file: str) -> pd.DataFrame:
    """Normalize loaded modern transaction and parcel frames."""
    parcel_summary = _aggregate_parcels(parcels)
    result = _base_frame(sales, year, "modern_multifile_v1", source_file,
                         "C7_Conveyance_Date", "E1_Sales_Price", 100)
    result = result.merge(parcel_summary, on="SDF_ID", how="left", validate="many_to_one")
    result["parcel_count"] = result["parcel_count"].astype("Int64")
    result["all_parcels_improved_residential"] = result[
        "all_parcels_improved_residential"
    ].fillna(False).astype("boolean")
    result["dom_reported"] = pd.to_numeric(_optional(result, "C8_Market_Days"), errors="coerce").astype("Int64")
    result["validation_complete"] = _flag(result["P2_17_Validation_Complete"])
    result["valid_for_trending"] = _flag(result["P2_16_Valid_Trending"])
    result["valuable_consideration"] = _flag(result["B1_Valuable_Consider"])
    result["residential_property"] = _flag(result["C10_Residential_Property"])
    result["agricultural_property"] = _flag(result["C10_Agricultural_Property"])
    result["commercial_property"] = _flag(result["C10_Commercial_Property"])
    result["industrial_property"] = _flag(result["C10_Industrial_Property"])
    result["vacant_land"] = pd.Series(pd.NA, index=result.index, dtype="boolean")
    result["trade"] = _flag(_optional(result, "B4_Trade"))
    result["related_party"] = pd.Series(pd.NA, index=result.index, dtype="boolean")
    result["land_contract"] = pd.Series(pd.NA, index=result.index, dtype="boolean")
    result["partial_interest"] = _flag(_optional(result, "B6_Partial_Interest"))
    result["charity_transfer"] = _flag(_optional(result, "B10_Charity"))
    result["sheriff_sale"] = _flag(result["C1_Sheriff_Sale"])
    result["short_sale"] = _flag(result["C2_Short_Sale"])
    result["quitclaim"] = _flag(result["C3_Quitclaim"])
    return result[PRE_ELIGIBILITY_COLUMNS]


def _read_columns(path: Path, separator: str, encoding: str,
                  required: set[str], optional: set[str],
                  county_filter: bool = False) -> pd.DataFrame:
    fields = set(_header(path, encoding, separator))
    missing = required - fields
    if missing:
        raise ValueError(f"{path.name} is missing required fields: {sorted(missing)}")
    usecols = sorted(required | (optional & fields))
    chunks = []
    for chunk in pd.read_csv(path, sep=separator, encoding=encoding, usecols=usecols,
                             dtype=str, chunksize=100_000, low_memory=False):
        if county_filter:
            county_codes = chunk["County_ID"].astype("string").str.strip().str.zfill(2)
            chunk = chunk[county_codes.isin(COUNTIES)].copy()
            chunk["County_ID"] = county_codes[county_codes.isin(COUNTIES)]
        if not chunk.empty:
            chunks.append(chunk)
    if not chunks:
        return pd.DataFrame(columns=usecols)
    return pd.concat(chunks, ignore_index=True)


def load_source(source: SourceSpec) -> pd.DataFrame:
    """Read and normalize one source, retaining only the five study counties."""
    if source.source_format == "legacy_pipe_v1":
        frame = _read_columns(source.sales_path, "|", "cp1252", LEGACY_REQUIRED,
                              LEGACY_OPTIONAL, county_filter=True)
        return normalize_legacy_frame(frame, source.year, source.sales_path.name)
    if source.source_format == "modern_multifile_v1":
        sales = _read_columns(source.sales_path, "\t", "utf-16", MODERN_REQUIRED,
                              MODERN_OPTIONAL, county_filter=True)
        parcel_header = set(_header(source.parcel_path, "utf-16", "\t"))
        target_ids = set(sales["SDF_ID"].dropna())
        parcel_chunks = []
        for chunk in pd.read_csv(source.parcel_path, sep="\t", encoding="utf-16",
                                 usecols=sorted(PARCEL_REQUIRED & parcel_header), dtype=str,
                                 chunksize=100_000, low_memory=False):
            chunk = chunk[chunk["SDF_ID"].isin(target_ids)]
            if not chunk.empty:
                parcel_chunks.append(chunk)
        parcels = (pd.concat(parcel_chunks, ignore_index=True) if parcel_chunks else
                   pd.DataFrame(columns=sorted(PARCEL_REQUIRED)))
        return normalize_modern_frames(sales, parcels, source.year, source.sales_path.name)
    raise ValueError(f"Unsupported source format: {source.source_format}")


def _event(row: pd.Series | None, issue_code: str, severity: str,
           record_count: int, details: str, **fallback) -> dict:
    def value(name):
        if row is not None and name in row and pd.notna(row[name]):
            return row[name]
        return fallback.get(name)
    return {
        "source_year": value("source_year"), "source_format": value("source_format"),
        "source_file": value("source_file"), "county": value("county"),
        "source_key": value("source_key"), "issue_code": issue_code,
        "severity": severity, "record_count": record_count, "details": details,
    }


def deduplicate_records(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Remove invalid keys, collapse exact repeats, and quarantine conflicts."""
    working = frame.copy()
    events = []
    dispositions = []
    invalid = working["source_key"].isna()
    for _, row in working[invalid].iterrows():
        events.append(_event(row, "invalid_transaction_key", "error", 1,
                             "Missing or malformed SDF_ID"))
        dispositions.append({"source_year": row["source_year"], "source_format": row["source_format"],
                             "county": row["county"], "invalid_key_rows": 1,
                             "exact_duplicate_rows_removed": 0, "conflicting_rows_quarantined": 0})
    working = working[~invalid].copy()

    duplicate_mask = working["source_key"].duplicated(keep=False)
    keep_indices = working.index[~duplicate_mask].tolist()
    duplicates = working[duplicate_mask].copy()
    if not duplicates.empty:
        comparison = duplicates[["source_key"] + COMPARISON_COLUMNS].astype("string").fillna("<NA>")
        distinct_counts = comparison.drop_duplicates().groupby("source_key", sort=False).size()
        exact_keys = set(distinct_counts[distinct_counts == 1].index)
        exact = duplicates[duplicates["source_key"].isin(exact_keys)].copy()
        conflicts = duplicates[~duplicates["source_key"].isin(exact_keys)].copy()

        if not exact.empty:
            exact["_preferred"] = exact["sale_year"] == exact["source_year"]
            selected = exact.sort_values(
                ["source_key", "_preferred", "source_year"], na_position="first"
            ).drop_duplicates("source_key", keep="last")
            keep_indices.extend(selected.index.tolist())
            removed = exact.drop(index=selected.index)
            counts = exact.groupby("source_key", sort=False).size().sub(1)
            event_rows = selected.set_index("source_key").loc[counts.index].reset_index()
            for _, row in event_rows.iterrows():
                events.append(_event(row, "exact_duplicate_collapsed", "info",
                                     int(counts[row["source_key"]]),
                                     "Analytically identical duplicate rows collapsed"))
            for _, row in removed.iterrows():
                dispositions.append({"source_year": row["source_year"], "source_format": row["source_format"],
                                     "county": row["county"], "invalid_key_rows": 0,
                                     "exact_duplicate_rows_removed": 1, "conflicting_rows_quarantined": 0})

        if not conflicts.empty:
            counts = conflicts.groupby("source_key", sort=False).size()
            representatives = conflicts.drop_duplicates("source_key").set_index("source_key")
            for source_key, count in counts.items():
                events.append(_event(representatives.loc[source_key],
                                     "conflicting_duplicate_quarantined", "error", int(count),
                                     "Duplicate SDF_ID has conflicting analytical values"))
            for _, row in conflicts.iterrows():
                dispositions.append({"source_year": row["source_year"], "source_format": row["source_format"],
                                     "county": row["county"], "invalid_key_rows": 0,
                                     "exact_duplicate_rows_removed": 0, "conflicting_rows_quarantined": 1})
    result = working.loc[keep_indices].copy() if keep_indices else working.iloc[0:0].copy()
    return result, pd.DataFrame(events, columns=QUALITY_COLUMNS), pd.DataFrame(dispositions)


def _reason_strings(frame: pd.DataFrame, strict: bool) -> pd.Series:
    reasons = pd.Series("", index=frame.index, dtype="string")

    def add(mask: pd.Series, code: str):
        nonlocal reasons
        mask = mask.fillna(True) if mask.dtype.name == "boolean" else mask.fillna(False)
        reasons.loc[mask] = reasons.loc[mask].map(lambda current: f"{current};{code}" if current else code)

    add(frame["sale_date"].isna(), "invalid_sale_date")
    add(frame["sale_year"] != frame["source_year"], "sale_year_mismatch")
    add(frame["gross_sale_price"].isna(), "invalid_sale_price")
    add(frame["gross_sale_price"] <= MIN_PRICE, "price_at_or_below_floor")
    add(frame["gross_sale_price"] > MAX_PRICE, "price_above_cap")
    legacy = frame["source_format"] == "legacy_pipe_v1"
    modern = ~legacy

    add(legacy & (frame["validation_complete"] != True), "validation_incomplete")  # noqa: E712
    add(legacy & (frame["valid_for_trending"] != True), "not_valid_for_trending")  # noqa: E712
    add(legacy & (frame["all_parcels_improved_residential"] != True),  # noqa: E712
        "not_improved_residential")

    add(modern & (frame["valuable_consideration"] != True), "not_valuable_consideration")  # noqa: E712
    residential_only = (
        (frame["residential_property"] == True)  # noqa: E712
        & (frame["agricultural_property"] == False)  # noqa: E712
        & (frame["commercial_property"] == False)  # noqa: E712
        & (frame["industrial_property"] == False)  # noqa: E712
    )
    add(modern & ~residential_only.fillna(False), "not_residential_only")
    add(modern & (frame["sheriff_sale"] != False), "sheriff_sale_or_unknown")  # noqa: E712
    add(modern & (frame["short_sale"] != False), "short_sale_or_unknown")  # noqa: E712
    add(modern & (frame["quitclaim"] != False), "quitclaim_or_unknown")  # noqa: E712
    if strict:
        add(modern & (frame["validation_complete"] != True), "validation_incomplete")  # noqa: E712
        add(modern & (frame["valid_for_trending"] != True), "not_valid_for_trending")  # noqa: E712
        add(modern & (frame["parcel_count"].isna() | (frame["parcel_count"] <= 0)), "missing_parcel")
        add(modern & (frame["all_parcels_improved_residential"] != True),  # noqa: E712
            "not_all_parcels_improved_residential")
    return reasons


def apply_eligibility(frame: pd.DataFrame) -> pd.DataFrame:
    """Attach current-study and strict-comparable eligibility decisions."""
    result = frame.copy()
    result["exclusion_reasons_current"] = _reason_strings(result, strict=False)
    result["exclusion_reasons_strict"] = _reason_strings(result, strict=True)
    result["eligible_current_study"] = result["exclusion_reasons_current"].eq("")
    result["eligible_strict_comparable"] = result["exclusion_reasons_strict"].eq("")
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_csv(frame: pd.DataFrame, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".csv", dir=path.parent,
                                     delete=False, encoding="utf-8", newline="") as stream:
        temporary = Path(stream.name)
    try:
        frame.to_csv(temporary, index=False)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _build_funnel(raw: pd.DataFrame, normalized: pd.DataFrame,
                  dispositions: pd.DataFrame) -> pd.DataFrame:
    keys = ["source_year", "source_format", "county"]
    raw_counts = raw.groupby(keys, dropna=False).size().rename("raw_target_rows").reset_index()
    normalized_counts = normalized.groupby(keys, dropna=False).agg(
        normalized_rows=("source_key", "size"),
        current_study_eligible_rows=("eligible_current_study", "sum"),
        strict_comparable_eligible_rows=("eligible_strict_comparable", "sum"),
    ).reset_index()
    if dispositions.empty:
        disposition_counts = pd.DataFrame(columns=keys + ["invalid_key_rows",
            "exact_duplicate_rows_removed", "conflicting_rows_quarantined"])
    else:
        disposition_counts = dispositions.groupby(keys, dropna=False)[
            ["invalid_key_rows", "exact_duplicate_rows_removed", "conflicting_rows_quarantined"]
        ].sum().reset_index()
    funnel = raw_counts.merge(disposition_counts, on=keys, how="left").merge(
        normalized_counts, on=keys, how="left"
    ).fillna(0)
    count_columns = [column for column in funnel if column not in keys]
    funnel[count_columns] = funnel[count_columns].astype(int)
    funnel["current_study_excluded_rows"] = (
        funnel["normalized_rows"] - funnel["current_study_eligible_rows"]
    )
    funnel["strict_comparable_excluded_rows"] = (
        funnel["normalized_rows"] - funnel["strict_comparable_eligible_rows"]
    )
    reconciled = (
        funnel["invalid_key_rows"] + funnel["exact_duplicate_rows_removed"]
        + funnel["conflicting_rows_quarantined"] + funnel["normalized_rows"]
    )
    if not reconciled.equals(funnel["raw_target_rows"]):
        raise AssertionError("Indiana SDF filter funnel does not reconcile to raw target rows")
    return funnel.sort_values(keys).reset_index(drop=True)


def run_pipeline(input_dir: Path, output: Path, quality_dir: Path,
                 years: Iterable[int] | None = None) -> dict:
    """Run discovery, normalization, audit generation, and atomic output writes."""
    started = time.monotonic()
    sources = discover_sources(input_dir)
    if years is not None:
        selected = set(years)
        sources = [source for source in sources if source.year in selected]
        missing = selected - {source.year for source in sources}
        if missing:
            raise FileNotFoundError(f"Requested Indiana SDF years not found: {sorted(missing)}")
    raw_key_frames = []
    normalized_frames = []
    quality_frames = []
    disposition_frames = []
    manifest_inputs = []
    for source in sources:
        print(f"Loading {source.year} ({source.source_format}) from {source.sales_path.name}...")
        frame = load_source(source)
        raw_key_frames.append(frame[["source_year", "source_format", "county"]].copy())
        deduplicated, source_quality, source_dispositions = deduplicate_records(frame)
        normalized_frames.append(apply_eligibility(deduplicated)[OUTPUT_COLUMNS])
        if not source_quality.empty:
            quality_frames.append(source_quality)
        if not source_dispositions.empty:
            disposition_frames.append(source_dispositions)
        paths = [source.sales_path] + ([source.parcel_path] if source.parcel_path else [])
        for path in paths:
            print(f"  Hashing {path.name}...")
            manifest_inputs.append({
                "path": path.name, "bytes": path.stat().st_size, "sha256": _sha256(path),
                "source_year": source.year, "source_format": source.source_format,
            })
        print(f"  {len(frame):,} target-county rows loaded")
    raw = pd.concat(raw_key_frames, ignore_index=True)
    normalized = pd.concat(normalized_frames, ignore_index=True)
    duplicate_across_sources = normalized["source_key"].duplicated(keep=False)
    if duplicate_across_sources.any():
        unique_rows = normalized[~duplicate_across_sources]
        cross_source, cross_quality, cross_dispositions = deduplicate_records(
            normalized[duplicate_across_sources]
        )
        normalized = pd.concat([unique_rows, cross_source], ignore_index=True)
        if not cross_quality.empty:
            quality_frames.append(cross_quality)
        if not cross_dispositions.empty:
            disposition_frames.append(cross_dispositions)
    quality = (pd.concat(quality_frames, ignore_index=True) if quality_frames else
               pd.DataFrame(columns=QUALITY_COLUMNS))
    dispositions = (pd.concat(disposition_frames, ignore_index=True) if disposition_frames else
                    pd.DataFrame(columns=["source_year", "source_format", "county",
                                          "invalid_key_rows", "exact_duplicate_rows_removed",
                                          "conflicting_rows_quarantined"]))

    missing_parcel = normalized[
        (normalized["source_format"] == "modern_multifile_v1")
        & (normalized["parcel_count"].isna() | (normalized["parcel_count"] <= 0))
    ]
    if not missing_parcel.empty:
        summary = missing_parcel.groupby(
            ["source_year", "source_format", "source_file", "county"], dropna=False
        ).size()
        additions = [
            _event(None, "missing_parcel", "error", int(count),
                   "Modern SDF_ID has no matching SALEPARCEL row",
                   source_year=key[0], source_format=key[1], source_file=key[2], county=key[3])
            for key, count in summary.items()
        ]
        quality = pd.concat([quality, pd.DataFrame(additions, columns=QUALITY_COLUMNS)], ignore_index=True)

    normalized = normalized[OUTPUT_COLUMNS].sort_values(
        ["sale_date", "source_key"], na_position="last"
    ).reset_index(drop=True)
    funnel = _build_funnel(raw, normalized, dispositions)
    if normalized["source_key"].duplicated().any():
        raise AssertionError("Normalized Indiana history contains duplicate source keys")

    _atomic_csv(normalized, output)
    _atomic_csv(funnel, quality_dir / "sdf_filter_funnel.csv")
    _atomic_csv(quality.sort_values(
        ["source_year", "source_file", "issue_code", "source_key"], na_position="last"
    ), quality_dir / "sdf_quality_events.csv")

    manifest = {
        "parser_version": PARSER_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "study_counties": [metadata["county"] for metadata in COUNTIES.values()],
        "inputs": manifest_inputs,
        "totals": {
            "raw_target_rows": int(len(raw)),
            "normalized_rows": int(len(normalized)),
            "current_study_eligible_rows": int(normalized["eligible_current_study"].sum()),
            "strict_comparable_eligible_rows": int(normalized["eligible_strict_comparable"].sum()),
            "quality_events": int(len(quality)),
        },
    }
    quality_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = quality_dir / "sdf_ingestion_manifest.json"
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, manifest_path)
    return manifest
