"""Build the Minnesota counterpart of ``sdf_indiana.csv``.

The established Indiana squeeze pipeline (``00_data_pipeline.py``) keeps
arm's-length residential sales with a valid property ZIP and assigns entry,
move-up, and luxury segments from a k-means fit on 2021–2025 prices. This
module applies the same rules to the harmonized Twin Cities eCRV transactions.

``price_basis="nominal"`` follows the published 2021–2025 method, which fits
and assigns segments on reported nominal prices. ``price_basis="real"``
follows the later constant-2025-dollar revision of that pipeline. Segment
breaks are refit on Minnesota sales either way; the Indiana breaks for the
same basis are carried as a comparison column only.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

# The original Indiana study covers 2021–2025 sales, and its segments are fit
# on the same years. Segmentation settings are copied from 00_data_pipeline.py
# so both metros use one method: raw (unlogged) price, k = 4, top two clusters
# collapsed.
STUDY_YEARS = (2021, 2022, 2023, 2024, 2025)
FIT_YEARS = STUDY_YEARS
KMEANS_CLUSTERS = 4
KMEANS_SEED = 42
KMEANS_INITS = 10
PRICE_CAP = 15_000_000
PRICE_LABELS = ["entry", "move_up", "luxury"]
# Indiana breaks by price basis: the published nominal breaks used by the
# original panel script, and the later constant-2025-dollar breaks.
INDIANA_BREAKS = {"nominal": (380_000, 1_050_000), "real": (407_000, 1_097_000)}
PRICE_BASES = ("nominal", "real")
PRICE_COLUMNS = {"nominal": "sale_price", "real": "sale_price_2025"}

# Indiana's residential classes cover one- to three-family dwellings, condos,
# and mobile homes; four or more units and care facilities are commercial
# there. The Minnesota counterpart is an explicit list of those dwelling types
# across both schemas. Vacant lots, 4-unit apartments, care facilities, parks,
# garages, and ambiguous rental or unspecified uses are excluded.
SINGLE_FAMILY_USES = {"RESID:SINGLEFAM", "RES:HOUSESGL"}
RESIDENTIAL_USES = SINGLE_FAMILY_USES | {
    "RESID:RESCONDO", "RES:CONDODW", "RESID:COOP",
    "RESID:TOWNHOUSE", "RES:TOWNHOUSE",
    "RESID:DUPLEX", "RES:DUPLEX", "RESID:TRIPLEX", "RES:TRIPLEX",
    "RES:MOBILEHOME", "RESID:MANUHOME",
    "RESID:CABVACHOME", "RES:CABIN",
}
COHORTS = ("residential", "single_family")

TRANSACTION_COLUMNS = [
    "source_key", "metro", "county", "tier_type", "core_city_status",
    "sale_date", "sale_year", "sale_month", "gross_sale_price",
    "eligible_current_study", "property_type_evidence",
]


def use_tokens(evidence: pd.Series) -> pd.Series:
    """Split eCRV use evidence into one ``tier:use`` token per row."""
    return evidence.fillna("").astype(str).str.split(r"[;|]").explode().str.strip()


def classify_uses(evidence: pd.Series) -> pd.DataFrame:
    """Flag sales whose every before-sale use is residential or single-family.

    ``evidence`` holds the ``property_type_evidence`` strings from the
    harmonized transactions. A sale with no use evidence fails both flags.
    """
    tokens = use_tokens(evidence)
    flags = pd.DataFrame({
        "residential": tokens.isin(RESIDENTIAL_USES).groupby(level=0).all(),
        "single_family": tokens.isin(SINGLE_FAMILY_USES).groupby(level=0).all(),
    })
    return flags.reindex(evidence.index, fill_value=False)


def normalize_zip(value) -> str | None:
    """Return a 5-digit ZIP under the Indiana pipeline's rules, else None."""
    if value is None or pd.isna(value):
        return None
    text = str(value).strip().split("-")[0]
    if "." in text:
        integer_part, decimal_part = text.split(".", 1)
        if decimal_part.lstrip("0") == "":
            text = integer_part
    if not text.isdigit():
        return None
    if 3 <= len(text) <= 5:
        text = text.zfill(5)
    if len(text) != 5 or text == "00000":
        return None
    return text


def property_zips(addresses: pd.DataFrame) -> pd.DataFrame:
    """Pick one property ZIP per sale from the eCRV address rows.

    The lowest-ordinal address with a valid ZIP is used. ``zip_count`` records
    how many distinct valid ZIPs the sale carried so multi-ZIP sales can be
    audited.
    """
    frame = addresses[["source_key", "ordinal", "zip"]].copy()
    frame["zip_code"] = frame["zip"].map(normalize_zip)
    frame = frame[frame["zip_code"].notna()]
    counts = frame.groupby("source_key")["zip_code"].nunique().rename("zip_count")
    first = (
        frame.sort_values(["source_key", "ordinal"])
        .drop_duplicates("source_key")
        .set_index("source_key")["zip_code"]
    )
    return pd.concat([first, counts], axis=1).reset_index()


def fit_segment_breaks(prices: pd.Series) -> dict:
    """Fit the Indiana k-means segmentation on raw (unlogged) prices.

    ``prices`` should already be limited to the fit years and be on one price
    basis. Returns the sorted cluster centers, the two midpoint breaks, and
    the fit sample size.
    """
    fit = prices[prices.le(PRICE_CAP)].to_frame(prices.name or "price")
    model = KMeans(
        n_clusters=KMEANS_CLUSTERS, random_state=KMEANS_SEED, n_init=KMEANS_INITS
    ).fit(fit)
    centers = np.sort(model.cluster_centers_.flatten())
    breaks = [(centers[0] + centers[1]) / 2, (centers[1] + centers[2]) / 2]
    return {
        "centers": [float(value) for value in centers],
        "breaks": [float(value) for value in breaks],
        "fit_records": int(len(fit)),
    }


def assign_segments(prices: pd.Series, breaks) -> pd.Categorical:
    """Label prices entry, move-up, or luxury with right-closed breaks."""
    labels = np.where(
        prices <= breaks[0], "entry", np.where(prices <= breaks[1], "move_up", "luxury")
    )
    return pd.Categorical(labels, categories=PRICE_LABELS)


def build_sample(
    transactions: pd.DataFrame,
    addresses: pd.DataFrame,
    cpi: pd.DataFrame,
    cohort: str = "residential",
    price_basis: str = "nominal",
) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    """Return the Minnesota squeeze sample, its segment fit, and a funnel.

    ``transactions`` is the harmonized research contract, ``addresses`` the
    eCRV address export without street lines, and ``cpi`` the monthly CPI
    table from ``inflation.load_monthly_cpi``. ``price_basis`` selects the
    price that segments are fit on and assigned from.
    """
    from inflation import add_real_price

    if cohort not in COHORTS:
        raise ValueError(f"cohort must be one of {COHORTS}")
    if price_basis not in PRICE_BASES:
        raise ValueError(f"price_basis must be one of {PRICE_BASES}")
    funnel = []
    frame = transactions.loc[transactions["metro"].eq("MSP"), TRANSACTION_COLUMNS].copy()
    funnel.append(("twin_cities_transactions", len(frame)))
    frame = frame[frame["sale_year"].astype(int).isin(STUDY_YEARS)]
    funnel.append((f"study_years_{STUDY_YEARS[0]}_{STUDY_YEARS[-1]}", len(frame)))
    frame = frame[frame["eligible_current_study"].fillna(False).astype(bool)]
    funnel.append(("arms_length_in_price_bounds", len(frame)))
    flags = classify_uses(frame["property_type_evidence"])
    frame = frame[flags[cohort]]
    funnel.append((f"{cohort}_use", len(frame)))

    frame = frame.merge(
        property_zips(addresses), on="source_key", how="left", validate="one_to_one"
    )
    frame = frame[frame["zip_code"].notna()].copy()
    funnel.append(("valid_property_zip", len(frame)))

    sale_dates = pd.to_datetime(frame["sale_date"], errors="coerce")
    frame["year"] = sale_dates.dt.year.astype(int)
    frame["month"] = sale_dates.dt.month.astype(int)
    frame["data_year"] = frame["sale_year"].astype(int)
    frame["sale_price"] = pd.to_numeric(frame["gross_sale_price"], errors="coerce")
    frame, _ = add_real_price(frame, cpi)

    price_column = PRICE_COLUMNS[price_basis]
    fit = fit_segment_breaks(
        frame.loc[frame["data_year"].isin(FIT_YEARS), price_column]
    )
    frame["price_segment"] = assign_segments(frame[price_column], fit["breaks"])
    frame["price_segment_indiana_breaks"] = assign_segments(
        frame[price_column], INDIANA_BREAKS[price_basis]
    )
    fit.update({
        "price_basis": price_basis,
        "cohort": cohort,
        "fit_years": list(FIT_YEARS),
        "clusters": KMEANS_CLUSTERS,
        "seed": KMEANS_SEED,
        "initializations": KMEANS_INITS,
        "price_cap": PRICE_CAP,
        "indiana_breaks": list(INDIANA_BREAKS[price_basis]),
        "cpi_base_year": int(frame["cpi_base_year"].iloc[0]),
    })

    columns = [
        "source_key", "county", "tier_type", "core_city_status", "year", "month",
        "sale_date", "sale_price", "data_year", "zip_code", "zip_count", "cpi",
        "cpi_imputed", "sale_price_2025", "cpi_base_year", "cpi_base",
        "price_segment", "price_segment_indiana_breaks",
    ]
    funnel_frame = pd.DataFrame(funnel, columns=["step", "records"])
    return frame[columns].reset_index(drop=True), fit, funnel_frame


def segment_counts(sample: pd.DataFrame) -> pd.DataFrame:
    """Count sales by county, segment, and break set for the audit table."""
    counts = []
    for column, breaks in (
        ("price_segment", "minnesota_refit"),
        ("price_segment_indiana_breaks", "indiana"),
    ):
        table = (
            sample.groupby(["county", column], observed=False).size()
            .rename("records").reset_index()
            .rename(columns={column: "price_segment"})
        )
        table.insert(0, "breaks", breaks)
        counts.append(table)
    return pd.concat(counts, ignore_index=True)


def read_inputs(root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load the harmonized transactions and the address export under ``root``."""
    transactions = pd.read_parquet(
        root / "data/processed/research/transactions.parquet", columns=TRANSACTION_COLUMNS
    )
    addresses = pd.read_parquet(
        root / "data/processed/mn/research_extract/ecrv_addresses.parquet",
        columns=["source_key", "ordinal", "zip"],
    )
    return transactions, addresses
