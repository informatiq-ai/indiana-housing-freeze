"""CPI-U utilities for expressing housing prices in constant 2025 dollars."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import pandas as pd
import requests


FRED_CPI_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
CPI_SERIES = "CPIAUCSL"
BASE_YEAR = 2025


def normalize_monthly_cpi(
    frame: pd.DataFrame,
    start_year: int = 2015,
    end_year: int = 2025,
) -> pd.DataFrame:
    """Return a complete monthly CPI table with interior gaps interpolated.

    The input may use FRED's ``DATE``/``CPIAUCSL`` fields or the project's
    ``sale_month``/``cpi`` fields. Leading and trailing gaps are rejected;
    only gaps bounded by observed CPI values are interpolated.
    """
    data = frame.copy()
    if {"DATE", CPI_SERIES}.issubset(data.columns):
        data = data.rename(columns={"DATE": "date", CPI_SERIES: "cpi"})
    elif "sale_month" in data.columns and "cpi" in data.columns:
        data["date"] = pd.to_datetime(data["sale_month"] + "-01")
    elif not {"date", "cpi"}.issubset(data.columns):
        raise ValueError("CPI input must contain DATE/CPIAUCSL or sale_month/cpi")

    if "cpi_imputed" not in data.columns:
        data["cpi_imputed"] = False
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data["cpi"] = pd.to_numeric(data["cpi"], errors="coerce")
    data["cpi_imputed"] = data["cpi_imputed"].astype(str).str.lower().isin(
        ["true", "1", "yes"]
    )
    data = data.loc[data["date"].notna(), ["date", "cpi", "cpi_imputed"]]
    data = data.drop_duplicates("date", keep="last").set_index("date")

    months = pd.date_range(
        f"{start_year}-01-01", f"{end_year}-12-01", freq="MS"
    )
    result = data.reindex(months)
    result["cpi_imputed"] = result["cpi_imputed"].fillna(False) | result["cpi"].isna()
    result["cpi"] = result["cpi"].interpolate(method="linear", limit_area="inside")
    if result["cpi"].isna().any():
        missing = result.index[result["cpi"].isna()].strftime("%Y-%m").tolist()
        raise ValueError(f"CPI coverage has unresolved edge gaps: {missing}")

    result = result.rename_axis("date").reset_index()
    result["sale_month"] = result["date"].dt.strftime("%Y-%m")
    result["year"] = result["date"].dt.year
    result["month"] = result["date"].dt.month
    return result[["sale_month", "year", "month", "cpi", "cpi_imputed"]]


def load_monthly_cpi(
    cache_path: Path,
    start_year: int = 2015,
    end_year: int = 2025,
    fallback_path: Path | None = None,
) -> pd.DataFrame:
    """Load cached CPI, optionally bootstrap from research output, or fetch FRED."""
    if cache_path.exists():
        raw = pd.read_csv(cache_path)
    elif fallback_path is not None and fallback_path.exists():
        raw = pd.read_csv(fallback_path, usecols=["sale_month", "cpi", "cpi_imputed"])
    else:
        response = requests.get(
            FRED_CPI_URL,
            params={
                "id": CPI_SERIES,
                "cosd": f"{start_year}-01-01",
                "coed": f"{end_year}-12-31",
            },
            timeout=120,
        )
        response.raise_for_status()
        raw = pd.read_csv(StringIO(response.text))

    result = normalize_monthly_cpi(raw, start_year, end_year)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(cache_path, index=False)
    return result


def add_real_price(
    transactions: pd.DataFrame,
    cpi: pd.DataFrame,
    price_column: str = "sale_price",
    output_column: str = "sale_price_2025",
    base_year: int = BASE_YEAR,
) -> tuple[pd.DataFrame, float]:
    """Attach CPI metadata and a constant-dollar price to every transaction."""
    base_cpi = cpi.loc[cpi["year"].eq(base_year), "cpi"].mean()
    if pd.isna(base_cpi):
        raise ValueError(f"CPI has no observations for base year {base_year}")

    result = transactions.merge(
        cpi[["year", "month", "cpi", "cpi_imputed"]],
        on=["year", "month"],
        how="left",
        validate="many_to_one",
    )
    if result["cpi"].isna().any():
        missing = (
            result.loc[result["cpi"].isna(), ["year", "month"]]
            .drop_duplicates()
            .to_dict("records")
        )
        raise ValueError(f"Transactions have unmatched CPI months: {missing}")

    result[output_column] = (
        pd.to_numeric(result[price_column], errors="coerce") * base_cpi / result["cpi"]
    ).round(2)
    result["cpi_base_year"] = base_year
    result["cpi_base"] = round(float(base_cpi), 6)
    return result, float(base_cpi)
