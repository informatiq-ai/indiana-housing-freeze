"""Redfin, Census ZCTA income, and ZIP summaries for the Minnesota squeeze study.

Each function mirrors a step of the established Indiana pipeline
(``00_data_pipeline.py``) so the R scripts receive inputs with the same shape.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

TWIN_CITIES_REDFIN_REGIONS = [
    "Anoka County, MN", "Carver County, MN", "Dakota County, MN",
    "Hennepin County, MN", "Ramsey County, MN", "Scott County, MN",
    "Washington County, MN",
]
ACS_ZCTA_URL = "https://api.census.gov/data/2023/acs/acs5"
# Same fixed rate as the Indiana ZIP affordability summary.
ZIP_SUMMARY_RATE = 0.062
MIN_ZIP_TRANSACTIONS = 10


def extract_redfin(national_path: Path, regions=TWIN_CITIES_REDFIN_REGIONS) -> pd.DataFrame:
    """Return every Redfin county-tracker row for the study regions.

    All property types and columns are kept, as in the Indiana extract; the R
    panel script filters to single-family residential and the study years.
    Region names are matched exactly so no other county can enter.
    """
    selected = []
    for chunk in pd.read_csv(
        national_path, sep="\t", compression="gzip", na_values=["", "NA", "--"],
        low_memory=False, chunksize=250_000,
    ):
        mask = chunk["STATE_CODE"].eq("MN") & chunk["REGION"].isin(regions)
        if mask.any():
            selected.append(chunk.loc[mask])
    if not selected:
        raise ValueError("Redfin tracker contains no Twin Cities county rows")
    return pd.concat(selected, ignore_index=True)


def fetch_zcta_hhi(study_zips: set[str], api_key: str) -> pd.DataFrame:
    """Pull ACS 2023 5-year ZCTA median household income for ``study_zips``.

    Uses the same national request and filters as the Indiana pipeline:
    positive, non-missing B19013_001E values only.
    """
    if not api_key:
        raise EnvironmentError("CENSUS_API_KEY is not set")
    response = requests.get(
        ACS_ZCTA_URL,
        params={
            "get": "NAME,B19013_001E",
            "for": "zip code tabulation area:*",
            "key": api_key,
        },
        timeout=120,
    )
    response.raise_for_status()
    raw = response.json()
    hhi = pd.DataFrame(raw[1:], columns=raw[0]).rename(
        columns={"zip code tabulation area": "zip_code", "B19013_001E": "zcta_hhi"}
    )[["zip_code", "zcta_hhi"]]
    hhi["zcta_hhi"] = pd.to_numeric(hhi["zcta_hhi"], errors="coerce")
    return hhi[
        hhi["zip_code"].isin(study_zips) & hhi["zcta_hhi"].notna() & hhi["zcta_hhi"].gt(0)
    ].reset_index(drop=True)


def zip_summary(
    sample: pd.DataFrame, hhi: pd.DataFrame, price_basis: str = "nominal"
) -> pd.DataFrame:
    """Summarize sales by ZIP and county as the Indiana ``zip_median_prices.csv``.

    Keeps ZIP-county cells with at least ten sales and adds the fixed-rate
    payment and annual payment-to-income ratio used by the map inputs.
    ``median_sale_price`` is nominal under the published method and constant
    2025 dollars under the real-price revision, matching each Indiana version.
    """
    median_column = "sale_price" if price_basis == "nominal" else "sale_price_2025"
    summary = (
        sample[sample["sale_price"] > 50_000]
        .groupby(["zip_code", "county"])
        .agg(
            median_sale_price=(median_column, "median"),
            median_sale_price_nominal=("sale_price", "median"),
            transactions=("sale_price", "count"),
            pct_move_up=("price_segment", lambda x: (x == "move_up").mean() * 100),
        )
        .reset_index()
        .query("transactions >= @MIN_ZIP_TRANSACTIONS")
    )
    summary = summary.merge(hhi, on="zip_code", how="left")
    monthly_rate = ZIP_SUMMARY_RATE / 12
    summary["monthly_payment"] = (
        summary["median_sale_price"] * 0.8
        * (monthly_rate * (1 + monthly_rate) ** 360)
        / ((1 + monthly_rate) ** 360 - 1)
    )
    summary["afford_ratio_zip"] = summary["monthly_payment"] * 12 / summary["zcta_hhi"]
    return summary
