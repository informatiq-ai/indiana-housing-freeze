"""Prepare a PII-free Indiana/Minnesota transaction contract for research."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile

import pandas as pd


MIN_PRICE = 50_000
MAX_PRICE = 15_000_000
INDY_COUNTIES = {"Boone", "Hamilton", "Hendricks", "Johnson", "Marion"}
MSP_COUNTIES = {"Anoka", "Carver", "Dakota", "Hennepin", "Ramsey", "Scott", "Washington"}
MSP_URBAN = {"Hennepin", "Ramsey"}
# eCRV records property city as a county-specific four-digit city/township code
# with no name. These codes were identified from ZIP concordance: their sales
# fall in Minneapolis and St. Paul postal ZIPs (see
# msp_core_city_zip_concordance.csv). The county definition stays primary;
# the city flag supports a core-city sensitivity.
MSP_CORE_CITY_CODES = {"Hennepin": "8800", "Ramsey": "8900"}
CORE_CITY_STATUSES = (
    "CORE_CITY", "COUNTY_BALANCE", "MIXED", "UNKNOWN", "NOT_CORE_COUNTY",
)
MN_DISQUALIFYING_FLAGS = (
    "related", "gift", "government", "legal_action", "name_change",
    "non_market_price", "tax_exempt", "buyer_part_interest", "deed_payoff",
    "like_kind_exchange", "received_in_trade",
)

OUTPUT_COLUMNS = [
    "source_key", "source_state", "source_schema", "source_snapshot",
    "source_version", "sale_date", "sale_year", "sale_month", "county",
    "county_fips", "metro", "tier_type", "core_city_status", "gross_sale_price",
    "adjusted_price",
    "personal_property_total", "seller_paid_points", "parcel_count",
    "property_type_evidence", "single_family", "eligible_current_study",
    "eligible_strict_comparable", "strict_eligibility_available",
    "research_eligible", "exclusion_reasons_current", "exclusion_reasons_strict",
    "exclusion_reasons_research", "source_status_conflict", "revision_conflict",
    "parse_recovered", "recovery_method", "deed_type", "contract_for_deed",
    "trustee_deed", "probate_deed", "limited_warranty_deed", "new_construction",
    "reporting_lag_days", "reporting_maturity_days", "recent_reporting_period",
    "regime",
]


def regime_for_year(year: int) -> str | None:
    if 2015 <= year <= 2019:
        return "BASELINE"
    if 2020 <= year <= 2021:
        return "PANDEMIC_LOW_RATE"
    if 2022 <= year <= 2025:
        return "HIGH_RATE_LOCK_IN"
    return None


def _bool(series: pd.Series) -> pd.Series:
    values = series.astype("string").str.strip().str.lower()
    return values.map({
        "true": True, "1": True, "y": True, "yes": True,
        "false": False, "0": False, "n": False, "no": False,
    }).astype("boolean")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", suffix=".csv", dir=path.parent, delete=False, encoding="utf-8", newline=""
    ) as stream:
        temporary = Path(stream.name)
    try:
        frame.to_csv(temporary, index=False)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        frame.to_parquet(
            temporary, index=False, engine="pyarrow", compression="zstd"
        )
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _append_reason(reasons: pd.Series, mask: pd.Series, code: str) -> pd.Series:
    selected = mask.fillna(False)
    reasons.loc[selected] = reasons.loc[selected].map(
        lambda current: f"{current};{code}" if current else code
    )
    return reasons


def _require_columns(frame: pd.DataFrame, required: set[str], source: Path) -> None:
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(
            f"{source} is missing required longitudinal fields {sorted(missing)}; "
            "rerun the applicable state ingestion pipeline"
        )


def _normalize_contract_types(frame: pd.DataFrame) -> pd.DataFrame:
    """Apply stable cross-state dtypes before CSV/Parquet serialization."""
    integer_columns = {
        "sale_year", "parcel_count", "reporting_lag_days", "reporting_maturity_days",
    }
    numeric_columns = {
        "gross_sale_price", "adjusted_price", "personal_property_total",
        "seller_paid_points",
    }
    boolean_columns = {
        "single_family", "eligible_current_study", "eligible_strict_comparable",
        "strict_eligibility_available", "research_eligible", "source_status_conflict",
        "revision_conflict", "parse_recovered", "contract_for_deed", "trustee_deed",
        "probate_deed", "limited_warranty_deed", "new_construction",
        "recent_reporting_period",
    }
    result = frame.copy()
    for column in OUTPUT_COLUMNS:
        if column in integer_columns:
            result[column] = pd.to_numeric(result[column], errors="coerce").astype("Int64")
        elif column in numeric_columns:
            result[column] = pd.to_numeric(result[column], errors="coerce").astype("Float64")
        elif column in boolean_columns:
            result[column] = _bool(result[column])
        else:
            result[column] = result[column].astype("string")
    result["county_fips"] = result["county_fips"].str.zfill(5)
    return result


def _read_child_rows(path: Path, columns: list[str], source_keys: set[str]) -> pd.DataFrame:
    """Read only study-key child rows so statewide exports stay memory bounded."""
    if path.suffix == ".parquet":
        frame = pd.read_parquet(
            path, columns=columns, engine="pyarrow", dtype_backend="pyarrow"
        )
        return frame.loc[frame["source_key"].isin(source_keys)].copy()
    selected = []
    for chunk in pd.read_csv(
        path, usecols=columns, dtype="string", low_memory=False, chunksize=200_000,
    ):
        matches = chunk["source_key"].isin(source_keys)
        if matches.any():
            selected.append(chunk.loc[matches])
    if not selected:
        return pd.DataFrame(columns=columns, dtype="string")
    return pd.concat(selected, ignore_index=True)


def _table_path(directory: Path, stem: str) -> Path:
    parquet = directory / f"{stem}.parquet"
    if parquet.exists():
        return parquet
    csv_path = directory / f"{stem}.csv"
    if csv_path.exists():
        return csv_path
    raise FileNotFoundError(f"Missing {parquet} and fallback {csv_path}")


def prepare_indiana(path: Path, start_year: int, end_year: int) -> pd.DataFrame:
    required = {
        "source_key", "source_format", "source_file", "sale_date", "sale_year",
        "sale_month", "county", "county_fips", "metro", "tier_type",
        "gross_sale_price", "parcel_count", "property_class_codes",
        "all_parcels_single_family", "eligible_current_study",
        "eligible_strict_comparable", "exclusion_reasons_current",
        "exclusion_reasons_strict", "source_status_conflict",
        "validation_complete", "valid_for_trending",
        "all_parcels_improved_residential",
    }
    frame = pd.read_csv(
        path, usecols=lambda column: column in required,
        low_memory=False,
    )
    _require_columns(frame, required, path)
    frame = frame[frame["sale_year"].between(start_year, end_year)].copy()
    if not set(frame["county"].dropna()).issubset(INDY_COUNTIES):
        raise ValueError("Indiana history contains counties outside the configured study area")

    result = pd.DataFrame(index=frame.index)
    result["source_key"] = frame["source_key"]
    result["source_state"] = "IN"
    result["source_schema"] = frame["source_format"]
    result["source_snapshot"] = frame["source_file"]
    result["source_version"] = pd.NA
    for column in ("sale_date", "sale_year", "sale_month", "county", "county_fips",
                   "metro", "tier_type", "gross_sale_price", "parcel_count"):
        result[column] = frame[column]
    result["core_city_status"] = pd.NA
    result["adjusted_price"] = pd.NA
    result["personal_property_total"] = pd.NA
    result["seller_paid_points"] = pd.NA
    result["property_type_evidence"] = frame["property_class_codes"]
    result["single_family"] = _bool(frame["all_parcels_single_family"])
    result["eligible_current_study"] = _bool(frame["eligible_current_study"])
    result["eligible_strict_comparable"] = _bool(frame["eligible_strict_comparable"])
    result["strict_eligibility_available"] = (
        ~_bool(frame["source_status_conflict"]).fillna(False)
        & _bool(frame["validation_complete"]).notna()
        & _bool(frame["valid_for_trending"]).notna()
        & _bool(frame["all_parcels_improved_residential"]).notna()
    )
    result["exclusion_reasons_current"] = frame["exclusion_reasons_current"].fillna("")
    result["exclusion_reasons_strict"] = frame["exclusion_reasons_strict"].fillna("")
    result["source_status_conflict"] = _bool(frame["source_status_conflict"])
    result["revision_conflict"] = False
    result["parse_recovered"] = False
    result["recovery_method"] = pd.NA
    result["deed_type"] = pd.NA
    result["contract_for_deed"] = pd.NA
    result["trustee_deed"] = pd.NA
    result["probate_deed"] = pd.NA
    result["limited_warranty_deed"] = pd.NA
    result["new_construction"] = pd.NA
    result["reporting_lag_days"] = pd.NA
    result["reporting_maturity_days"] = pd.NA
    result["recent_reporting_period"] = False

    research_reasons = pd.Series("", index=result.index, dtype="string")
    research_reasons = _append_reason(
        research_reasons,
        result["eligible_current_study"].isna()
        | (result["eligible_current_study"] != True),  # noqa: E712
        "not_current_study_eligible",
    )
    research_reasons = _append_reason(
        research_reasons,
        result["single_family"].isna() | (result["single_family"] != True),  # noqa: E712
        "not_single_family",
    )
    result["exclusion_reasons_research"] = research_reasons
    result["research_eligible"] = research_reasons.eq("")
    result["regime"] = result["sale_year"].astype(int).map(regime_for_year)
    return result[OUTPUT_COLUMNS]


def summarize_mn_uses(path: Path, source_keys: set[str] | None = None) -> pd.DataFrame:
    required = {"source_key", "use_timing", "tier1Cde", "tier2Cde",
                "propertyTypeCode", "propertyUseCode"}
    uses = (
        _read_child_rows(path, sorted(required), source_keys)
        if source_keys is not None
        else pd.read_csv(path, dtype="string", low_memory=False)
    )
    _require_columns(uses, required, path)
    before = uses[uses["use_timing"].str.lower() == "before"].copy()
    before["_single_family_row"] = (
        (before["propertyTypeCode"] == "RES")
        & (before["propertyUseCode"] == "HOUSESGL")
    ) | (
        (before["tier1Cde"] == "RESID")
        & (before["tier2Cde"] == "SINGLEFAM")
    )
    legacy = (
        before["propertyTypeCode"].astype("string").fillna("") + ":"
        + before["propertyUseCode"].astype("string").fillna("")
    ).str.strip(":")
    modern = (
        before["tier1Cde"].astype("string").fillna("") + ":"
        + before["tier2Cde"].astype("string").fillna("")
    ).str.strip(":")
    before["_evidence"] = legacy.where(modern.eq(""), legacy + "|" + modern)
    before.loc[legacy.eq(""), "_evidence"] = modern.loc[legacy.eq("")]
    if before.empty:
        return pd.DataFrame(columns=["source_key", "single_family", "property_type_evidence"])
    summary = before.groupby("source_key", sort=False).agg(
        single_family=("_single_family_row", "all"),
        property_type_evidence=("_evidence", lambda values: ";".join(sorted(set(values)))),
    )
    return summary.reset_index()


def summarize_mn_personal_property(
    path: Path, source_keys: set[str] | None = None
) -> pd.DataFrame:
    required = {"source_key", "selected", "propertyValue"}
    personal = (
        _read_child_rows(path, sorted(required), source_keys)
        if source_keys is not None
        else pd.read_csv(path, dtype="string", low_memory=False)
    )
    _require_columns(personal, required, path)
    personal["_selected"] = _bool(personal["selected"])
    personal["_value"] = pd.to_numeric(personal["propertyValue"], errors="coerce")
    selected = personal[personal["_selected"] == True].copy()  # noqa: E712
    if selected.empty:
        return pd.DataFrame(columns=["source_key", "selected_personal_rows",
                                     "personal_property_total", "personal_values_complete"])
    summary = selected.groupby("source_key", sort=False).agg(
        selected_personal_rows=("source_key", "size"),
        personal_property_total=("_value", "sum"),
        personal_values_complete=(
            "_value", lambda values: values.notna().all() and values.ge(0).all()
        ),
    )
    return summary.reset_index()


def _mn_address_codes(path: Path, source_keys: set[str]) -> pd.DataFrame:
    """Return property city codes and 5-digit ZIPs per address row; no street."""
    required = ["source_key", "city", "zip"]
    addresses = _read_child_rows(path, required, source_keys)
    _require_columns(addresses, set(required), path)
    addresses = addresses.astype("string")
    addresses["city"] = addresses["city"].str.strip().replace("", pd.NA)
    addresses["zip"] = addresses["zip"].str.strip().str[:5].replace("", pd.NA)
    return addresses


def classify_core_city(addresses: pd.DataFrame, counties: pd.Series) -> pd.Series:
    """Classify each transaction's property city against its county's core city.

    Inputs are address rows (source_key, city) and a county name per source key.
    Blank codes are ignored when another address carries a code. Returns a
    status per source key: CORE_CITY when every coded address is in the core
    city, COUNTY_BALANCE when none is, MIXED when both occur, UNKNOWN when no
    address carries a code, and NOT_CORE_COUNTY outside Hennepin and Ramsey.
    """
    status = pd.Series("NOT_CORE_COUNTY", index=counties.index, dtype="string")
    core_county = counties.isin(MSP_CORE_CITY_CODES.keys())
    status.loc[core_county] = "UNKNOWN"
    coded = addresses.dropna(subset=["city"])
    coded = coded.loc[coded["source_key"].isin(counties.index[core_county])]
    if coded.empty:
        return status
    core_code = counties.reindex(coded["source_key"]).map(MSP_CORE_CITY_CODES)
    in_core = pd.Series(
        coded["city"].to_numpy() == core_code.to_numpy(), index=coded["source_key"]
    )
    shares = in_core.groupby(level=0).agg(["all", "any"])
    status.loc[shares.index[shares["all"]]] = "CORE_CITY"
    status.loc[shares.index[~shares["any"]]] = "COUNTY_BALANCE"
    status.loc[shares.index[shares["any"] & ~shares["all"]]] = "MIXED"
    return status


def core_city_zip_concordance(
    processed_dir: Path, minnesota: pd.DataFrame
) -> pd.DataFrame:
    """Count core-county address rows by county, ZIP, and core-code match.

    This aggregate is the evidence that the configured codes identify
    Minneapolis and St. Paul; it carries no street or party detail.
    """
    core = minnesota.loc[minnesota["county"].isin(MSP_CORE_CITY_CODES.keys()),
                         ["source_key", "county"]]
    addresses = _mn_address_codes(
        _table_path(processed_dir, "ecrv_addresses"), set(core["source_key"])
    ).merge(core, on="source_key", how="inner")
    addresses["core_code"] = addresses["county"].map(MSP_CORE_CITY_CODES)
    addresses["address_city_class"] = "COUNTY_BALANCE_CODE"
    addresses.loc[addresses["city"].isna(), "address_city_class"] = "BLANK_CODE"
    addresses.loc[addresses["city"].eq(addresses["core_code"]).fillna(False),
                  "address_city_class"] = "CORE_CITY_CODE"
    concordance = addresses.groupby(
        ["county", "zip", "address_city_class"], dropna=False
    ).size().rename("address_rows").reset_index()
    return concordance.pivot_table(
        index=["county", "zip"], columns="address_city_class", values="address_rows",
        fill_value=0, dropna=False,
    ).reset_index().rename_axis(columns=None)


def prepare_minnesota(processed_dir: Path, start_year: int, end_year: int) -> pd.DataFrame:
    required = {
        "source_key", "schema_variant", "sale_date", "sale_year", "sale_month",
        "county_name", "county_fips", "is_twin_cities", "gross_sale_price",
        "seller_paid_points", "personal_property_included", "revision_conflict",
        "parse_recovered", "recovery_method", "first_extract_timestamp",
        "extract_timestamp", "archive_name", "version_id", "deed_type",
        "new_buildings_sale_year", *MN_DISQUALIFYING_FLAGS,
    }
    transaction_path = _table_path(processed_dir, "ecrv_transactions")
    if transaction_path.suffix == ".parquet":
        transactions = pd.read_parquet(
            transaction_path, columns=sorted(required), engine="pyarrow",
            dtype_backend="pyarrow",
        )
    else:
        selected = []
        for chunk in pd.read_csv(
            transaction_path, usecols=sorted(required), low_memory=False,
            chunksize=200_000,
        ):
            mask = (
                chunk["is_twin_cities"].eq(1)
                & chunk["sale_year"].between(start_year, end_year)
            )
            if mask.any():
                selected.append(chunk.loc[mask])
        transactions = (
            pd.concat(selected, ignore_index=True) if selected
            else pd.DataFrame(columns=sorted(required))
        )
    _require_columns(transactions, required, transaction_path)
    transactions = transactions[
        (transactions["is_twin_cities"] == 1)
        & transactions["sale_year"].between(start_year, end_year)
    ].copy()
    if not set(transactions["county_name"].dropna()).issubset(MSP_COUNTIES):
        raise ValueError("Minnesota export contains unexpected Twin Cities county names")
    if transactions["source_key"].duplicated().any():
        raise ValueError("Minnesota current transaction export contains duplicate source keys")

    source_keys = set(transactions["source_key"])
    uses = summarize_mn_uses(_table_path(processed_dir, "ecrv_uses"), source_keys)
    parcels = _read_child_rows(
        _table_path(processed_dir, "ecrv_parcels"),
        ["source_key", "parcelId"], source_keys
    ).drop_duplicates()
    parcel_counts = parcels.groupby("source_key", sort=False).size().rename(
        "parcel_count"
    ).reset_index()
    personal = summarize_mn_personal_property(
        _table_path(processed_dir, "ecrv_personal_property"), source_keys
    )
    frame = transactions.merge(uses, on="source_key", how="left", validate="one_to_one")
    frame = frame.merge(parcel_counts, on="source_key", how="left", validate="one_to_one")
    frame = frame.merge(personal, on="source_key", how="left", validate="one_to_one")
    addresses = _mn_address_codes(_table_path(processed_dir, "ecrv_addresses"), source_keys)
    core_status = classify_core_city(
        addresses, frame.set_index("source_key")["county_name"]
    )

    result = pd.DataFrame(index=frame.index)
    result["source_key"] = frame["source_key"]
    result["source_state"] = "MN"
    result["source_schema"] = frame["schema_variant"]
    result["source_snapshot"] = frame["archive_name"] + "@" + frame["extract_timestamp"]
    result["source_version"] = frame["version_id"]
    result["sale_date"] = frame["sale_date"]
    result["sale_year"] = frame["sale_year"].astype(int)
    result["sale_month"] = frame["sale_month"]
    result["county"] = frame["county_name"]
    result["county_fips"] = frame["county_fips"].astype("string").str.zfill(5)
    result["metro"] = "MSP"
    result["tier_type"] = frame["county_name"].map(
        lambda county: "URBAN_CORE" if county in MSP_URBAN else "SUBURBAN_COLLAR"
    )
    result["core_city_status"] = frame["source_key"].map(core_status)
    result["gross_sale_price"] = pd.to_numeric(frame["gross_sale_price"], errors="coerce")
    result["seller_paid_points"] = pd.to_numeric(frame["seller_paid_points"], errors="coerce")
    result["parcel_count"] = frame["parcel_count"].astype("Int64")
    result["property_type_evidence"] = frame["property_type_evidence"]
    result["single_family"] = _bool(frame["single_family"])
    result["source_status_conflict"] = False
    result["revision_conflict"] = _bool(frame["revision_conflict"])
    result["parse_recovered"] = _bool(frame["parse_recovered"])
    result["recovery_method"] = frame["recovery_method"]
    result["deed_type"] = frame["deed_type"].astype("string").str.upper()
    result["contract_for_deed"] = result["deed_type"].eq("CONFORDEED")
    result["trustee_deed"] = result["deed_type"].eq("TRUSTEE")
    result["probate_deed"] = result["deed_type"].isin(["PROBATE", "PERREPDEED"])
    result["limited_warranty_deed"] = result["deed_type"].eq("LIMWARRNTY")
    result["new_construction"] = _bool(frame["new_buildings_sale_year"])
    first_observed = pd.to_datetime(frame["first_extract_timestamp"], errors="coerce")
    sale_dates = pd.to_datetime(frame["sale_date"], errors="coerce")
    result["reporting_lag_days"] = (first_observed - sale_dates).dt.days.astype("Int64")
    nonnegative_lags = result.loc[
        result["reporting_lag_days"].ge(0), "reporting_lag_days"
    ].dropna()
    maturity_days = (
        int(nonnegative_lags.quantile(0.95, interpolation="higher"))
        if not nonnegative_lags.empty else 0
    )
    result["reporting_maturity_days"] = maturity_days
    latest_extract = first_observed.max()
    if pd.isna(latest_extract):
        result["recent_reporting_period"] = pd.Series(
            pd.NA, index=result.index, dtype="boolean"
        )
    else:
        result["recent_reporting_period"] = sale_dates.gt(
            latest_extract - pd.Timedelta(days=maturity_days)
        ).astype("boolean")

    current_reasons = pd.Series("", index=frame.index, dtype="string")
    strict_reasons = pd.Series("", index=frame.index, dtype="string")
    common_reasons = pd.Series("", index=frame.index, dtype="string")
    valid_price = result["gross_sale_price"].gt(MIN_PRICE) & result[
        "gross_sale_price"
    ].le(MAX_PRICE)
    common_reasons = _append_reason(common_reasons, ~valid_price, "price_out_of_bounds")
    common_reasons = _append_reason(
        common_reasons,
        result["revision_conflict"].isna() | (result["revision_conflict"] != False),  # noqa: E712
        "revision_conflict",
    )
    current_reasons = common_reasons.copy()
    strict_reasons = common_reasons.copy()
    for flag in MN_DISQUALIFYING_FLAGS:
        values = _bool(frame[flag])
        current_reasons = _append_reason(current_reasons, values == True, flag)  # noqa: E712
        strict_reasons = _append_reason(
            strict_reasons, values.isna() | (values != False), f"{flag}_or_unknown"  # noqa: E712
        )
    quitclaim = result["deed_type"].eq("QUITCLAIM")
    current_reasons = _append_reason(current_reasons, quitclaim, "quitclaim")
    strict_reasons = _append_reason(strict_reasons, quitclaim, "quitclaim")
    strict_reasons = _append_reason(
        strict_reasons, result["deed_type"].isna(), "deed_type_unknown"
    )
    result["eligible_current_study"] = current_reasons.eq("")
    result["eligible_strict_comparable"] = strict_reasons.eq("")
    result["strict_eligibility_available"] = result["deed_type"].notna()
    for flag in MN_DISQUALIFYING_FLAGS:
        result["strict_eligibility_available"] &= _bool(frame[flag]).notna()
    result["exclusion_reasons_current"] = current_reasons
    result["exclusion_reasons_strict"] = strict_reasons

    research_reasons = current_reasons.copy()
    research_reasons = _append_reason(
        research_reasons,
        result["single_family"].isna() | (result["single_family"] != True),  # noqa: E712
        "not_single_family",
    )
    result["exclusion_reasons_research"] = research_reasons
    result["research_eligible"] = research_reasons.eq("")

    included = _bool(frame["personal_property_included"])
    selected_rows = frame["selected_personal_rows"].fillna(0)
    values_complete = _bool(frame["personal_values_complete"]).fillna(False)
    personal_complete = (included == False) | (  # noqa: E712
        (included == True) & selected_rows.gt(0) & values_complete  # noqa: E712
    )
    selected_personal_total = frame["personal_property_total"].fillna(0)
    included_personal_total = selected_personal_total.where(included == True, 0)  # noqa: E712
    result["personal_property_total"] = included_personal_total.where(personal_complete)
    adjustment_complete = (
        personal_complete & result["seller_paid_points"].notna()
        & result["seller_paid_points"].ge(0)
    )
    adjusted = (
        result["gross_sale_price"] - included_personal_total
        - result["seller_paid_points"].fillna(0)
    )
    result["adjusted_price"] = adjusted.where(adjustment_complete & adjusted.gt(0))
    result["regime"] = result["sale_year"].map(regime_for_year)
    return result[OUTPUT_COLUMNS]


def build_quality_outputs(transactions: pd.DataFrame, quality_dir: Path) -> None:
    keys = ["source_state", "metro", "county", "sale_year"]
    funnel = transactions.groupby(keys, dropna=False).agg(
        normalized_records=("source_key", "size"),
        single_family_records=("single_family", lambda values: int((values == True).sum())),  # noqa: E712
        current_eligible_records=("eligible_current_study", "sum"),
        strict_eligible_records=("eligible_strict_comparable", "sum"),
        research_eligible_records=("research_eligible", "sum"),
        recovered_records=("parse_recovered", "sum"),
        revision_conflicts=("revision_conflict", "sum"),
        status_conflicts=("source_status_conflict", "sum"),
    ).reset_index()
    _atomic_csv(funnel, quality_dir / "transaction_filter_funnel.csv")

    coverage = transactions.groupby(
        ["source_state", "metro", "county", "county_fips", "sale_month"], dropna=False
    ).agg(
        normalized_records=("source_key", "size"),
        research_eligible_records=("research_eligible", "sum"),
    ).reset_index()
    _atomic_csv(coverage, quality_dir / "transaction_coverage.csv")

    event_frame = transactions.loc[
        transactions["exclusion_reasons_research"].ne(""),
        ["source_state", "metro", "county", "sale_year", "exclusion_reasons_research"],
    ].rename(columns={"exclusion_reasons_research": "reason"}).copy()
    if not event_frame.empty:
        event_frame["reason"] = event_frame["reason"].str.split(";")
        event_frame = event_frame.explode("reason", ignore_index=True)
        event_frame = event_frame.groupby(
            ["source_state", "metro", "county", "sale_year", "reason"], dropna=False
        ).size().rename("records").reset_index()
    _atomic_csv(event_frame, quality_dir / "research_exclusions.csv")

    minnesota = transactions.loc[transactions["source_state"] == "MN"]
    core_city = minnesota.groupby(
        ["county", "sale_year", "core_city_status"], dropna=False
    ).agg(
        normalized_records=("source_key", "size"),
        research_eligible_records=("research_eligible", "sum"),
    ).reset_index()
    _atomic_csv(core_city, quality_dir / "msp_core_city_classification.csv")


def run_prepare(indiana_path: Path, minnesota_dir: Path, output: Path,
                quality_dir: Path, start_year: int, end_year: int) -> dict:
    if start_year > end_year:
        raise ValueError("start_year must not be after end_year")
    indiana = prepare_indiana(indiana_path, start_year, end_year)
    minnesota = prepare_minnesota(minnesota_dir, start_year, end_year)
    combined = pd.concat([indiana, minnesota], ignore_index=True)
    if combined["source_key"].isna().any() or combined["source_key"].duplicated().any():
        raise AssertionError("Harmonized transactions require unique, non-null source keys")
    if set(combined["regime"].dropna()) != {
        "BASELINE", "PANDEMIC_LOW_RATE", "HIGH_RATE_LOCK_IN"
    }:
        raise AssertionError("Harmonized transactions do not cover all three research regimes")
    combined = _normalize_contract_types(combined)
    combined = combined.sort_values(["sale_date", "source_key"]).reset_index(drop=True)
    parquet_output = output.with_suffix(".parquet")
    _atomic_parquet(combined, parquet_output)
    _atomic_csv(combined, output)
    build_quality_outputs(combined, quality_dir)
    _atomic_csv(
        core_city_zip_concordance(minnesota_dir, minnesota),
        quality_dir / "msp_core_city_zip_concordance.csv",
    )
    inputs = [indiana_path] + [
        _table_path(minnesota_dir, stem) for stem in (
            "ecrv_transactions", "ecrv_uses", "ecrv_parcels",
            "ecrv_personal_property", "ecrv_addresses",
        )
    ]
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "start_year": start_year,
        "end_year": end_year,
        "inputs": [
            {"path": str(path), "bytes": path.stat().st_size, "sha256": _sha256(path)}
            for path in inputs
        ],
        "totals": {
            "transactions": len(combined),
            "indiana_transactions": int((combined["source_state"] == "IN").sum()),
            "minnesota_transactions": int((combined["source_state"] == "MN").sum()),
            "research_eligible": int(combined["research_eligible"].sum()),
            "strict_eligible": int(combined["eligible_strict_comparable"].sum()),
        },
        "outputs": {
            "parquet": {"path": str(parquet_output), "bytes": parquet_output.stat().st_size},
            "csv_compatibility": {"path": str(output), "bytes": output.stat().st_size},
        },
    }
    quality_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = quality_dir / "transaction_manifest.json"
    with tempfile.NamedTemporaryFile(
        "w", suffix=".json", dir=quality_dir, delete=False, encoding="utf-8"
    ) as stream:
        stream.write(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        temporary_manifest = Path(stream.name)
    try:
        os.replace(temporary_manifest, manifest_path)
    finally:
        if temporary_manifest.exists():
            temporary_manifest.unlink()
    return manifest
