"""
00_data_pipeline.py
────────────────────────────────────────────────────────────────────────────────
Indiana Move-Up Housing Study — Clean Data Pipeline

Methodology:
  County normalization  — strips trailing "COUNTY" suffix and uppercases County_Name
                          before filtering, resolving format inconsistencies in SDF data
  Property type         — requires C10_Residential_Property = Y and all other C10
                          flags = N; excludes mixed-use parcels
  Arm's-length criteria — requires B1_Valuable_Consider = Y; excludes sheriff sales,
                          short sales, and quitclaim deeds
  Price segmentation    — k-means (k=4) on raw sale_price (no log transform); top two
                          tiers collapsed into luxury; natural breaks at ~$380K and ~$1.05M

Outputs:
  sdf_indiana.csv       — transaction-level cleaned data
  zip_median_prices.csv — zip-level summary for mapping
  hhi_zcta.csv          — ZCTA-level median household income (Census ACS 2023 5-yr)
"""

import os
import requests
import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.cluster import KMeans

ROOT = Path(__file__).resolve().parents[1]

# Download and cache Redfin data — skip download if cache already exists
REDFIN_CACHE = str(ROOT / "data/processed/redfin_indiana.csv")
REDFIN_URL   = (
    "https://redfin-public-data.s3.us-west-2.amazonaws.com/"
    "redfin_market_tracker/county_market_tracker.tsv000.gz"
)
target_counties = ["Marion", "Hamilton", "Boone", "Hendricks", "Johnson"]

if os.path.exists(REDFIN_CACHE):
    print(f"Redfin cache found — skipping download ({REDFIN_CACHE})")
else:
    print("Downloading Redfin national tracker... this may take a few minutes")
    df = pd.read_csv(
        REDFIN_URL,
        sep="\t",
        compression="gzip",
        na_values=["", "NA", "--"],
        low_memory=False
    )
    print(f"Full file loaded: {df.shape[0]:,} rows")

    redfin_indiana = df[
        (df["STATE_CODE"] == "IN") &
        (df["REGION"].str.contains("|".join(target_counties), na=False))
    ].copy()

    print(f"Indiana filtered: {redfin_indiana.shape[0]:,} rows")
    redfin_indiana.to_csv(REDFIN_CACHE, index=False)
    print(f"Cached to {REDFIN_CACHE}")

# ── Configuration ─────────────────────────────────────────────────────────────

CENSUS_API_KEY  = os.environ.get("CENSUS_API_KEY", "")
HHI_ZCTA_CACHE  = str(ROOT / "data/processed/hhi_zcta.csv")

TARGET_COUNTIES = {"MARION", "HAMILTON", "BOONE", "HENDRICKS", "JOHNSON"}

YEARS     = [2021, 2022, 2023, 2024, 2025]
INPUT_DIR = str(ROOT)
OUTPUT_FILE = str(ROOT / "data/processed/sdf_indiana.csv")

KEEP_COLS = [
    "SDF_ID",
    "County_Name",
    "C7_Conveyance_Date",
    "C8_Market_Days",
    "C10_Residential_Property",
    "C10_Agricultural_Property",
    "C10_Commercial_Property",
    "C10_Industrial_Property",
    "E1_Sales_Price",
    "B1_Valuable_Consider",
    "C1_Sheriff_Sale",
    "C2_Short_Sale",
    "C3_Quitclaim"
]

# Price segments confirmed via k-means (k=4, top two tiers collapsed into luxury)
# Natural breaks at $380K and $1.05M
PRICE_LABELS = ["entry", "move_up", "luxury"]

# ── Step 1: Load and filter SALEDISC files ────────────────────────────────────

all_years = []

for year in YEARS:
    fname = os.path.join(INPUT_DIR, f"SALEDISC{year}.txt")
    if not os.path.exists(fname):
        print(f"[SKIP] {fname} not found")
        continue

    print(f"Loading {fname}...")

    df = pd.read_csv(
        fname,
        sep="\t",
        encoding="utf-16",
        usecols=KEEP_COLS,
        dtype=str,
        low_memory=False,
    )
    print(f"  Raw rows: {len(df):,}")

    # ── Normalize county name before filtering ────────────────────────────────
    # Source data uses mixed formats: "MARION COUNTY", "Hamilton", etc.
    # Strip trailing "COUNTY", uppercase, and trim whitespace for consistent matching
    df["County_Name_norm"] = (
        df["County_Name"]
        .str.upper()
        .str.replace(r"\s*COUNTY\s*$", "", regex=True)
        .str.strip()
    )
    df = df[df["County_Name_norm"].isin(TARGET_COUNTIES)].copy()

    # ── Property type: residential only, explicitly excluding others ───────────
    # C10_Residential_Property = Y is seller-reported on the disclosure form.
    # Also require the other three flags = N to exclude mixed-use parcels
    # (e.g. a farm with a house that checks both Residential and Agricultural).
    df = df[
        (df["C10_Residential_Property"]  == "Y") &
        (df["C10_Agricultural_Property"] == "N") &
        (df["C10_Commercial_Property"]   == "N") &
        (df["C10_Industrial_Property"]   == "N")
    ].copy()

    # ── Arm's-length sales only ───────────────────────────────────────────────
    df = df[
        (df["B1_Valuable_Consider"] == "Y") &
        (df["C1_Sheriff_Sale"]      == "N") &
        (df["C2_Short_Sale"]        == "N") &
        (df["C3_Quitclaim"]         == "N")
    ].copy()

    # ── Price conversion (cents → dollars) ────────────────────────────────────
    # Strict floor (> $50K) matches `MIN_PRICE` in 03_regression_hypothesis_tests.R
    # (line 105), so the two pipelines agree on which rows survive.
    # Strict ceiling (<= $15M) matches `luxury_CAP` in 03 (line 41) and removes
    # data-entry outliers (e.g. $244B rows) that survive k-means binning.
    df["sale_price"] = pd.to_numeric(df["E1_Sales_Price"], errors="coerce") / 100
    df = df[
        (df["sale_price"] > 50_000)
        & (df["sale_price"] <= 15_000_000)
    ].copy()

    # ── Date parsing ──────────────────────────────────────────────────────────
    df["sale_date"] = pd.to_datetime(df["C7_Conveyance_Date"], errors="coerce")
    df["year"]      = df["sale_date"].dt.year
    df["month"]     = df["sale_date"].dt.month

    # ── Standardize county name for output ────────────────────────────────────
    county_map = {
        "MARION":    "Marion",
        "HAMILTON":  "Hamilton",
        "BOONE":     "Boone",
        "HENDRICKS": "Hendricks",
        "JOHNSON":   "Johnson",
    }
    df["county"] = df["County_Name_norm"].map(county_map)

    # ── Rename columns ────────────────────────────────────────────────────────
    df = df.rename(columns={
        "C8_Market_Days":     "dom_reported"
    })

    df["data_year"] = year
    print(f"  SALEDISC{year}: {len(df):,} qualifying transactions")
    all_years.append(df)

# ── Combine years ─────────────────────────────────────────────────────────────

final = pd.concat(all_years, ignore_index=True)
print(f"Combined: {len(final):,} transactions across {final['county'].nunique()} counties")

final = final[[
    "SDF_ID", "county", "year", "month", "sale_date",
    "sale_price", "dom_reported", "data_year"
]]

print(f"Total rows after all filters: {len(final):,}")

final.to_csv(OUTPUT_FILE, index=False)
print(f"\nSaved transaction data → {OUTPUT_FILE}")

# ── Step 2: Load SALEPARCEL zip codes ─────────────────────────────────────────

print("\nLoading SALEPARCEL files for zip codes...")

parcels = []
for year in YEARS:
    fname = os.path.join(INPUT_DIR, f"SALEPARCEL{year}.txt")
    if not os.path.exists(fname):
        print(f"  [SKIP] {fname} not found")
        continue

    p = pd.read_csv(
        fname,
        sep="\t",
        encoding="utf-16",
        usecols=["SDF_ID", "A5_ZipCode"],
        dtype=str,
        low_memory=False,
    )
    p["parcel_year"] = year  # track source year for deterministic deduplication
    parcels.append(p)
    print(f"  {fname}: {len(p):,} rows")

parcel_df = pd.concat(parcels, ignore_index=True)
parcel_df = parcel_df.rename(columns={
    "A5_ZipCode": "zip_code",
})
# Keep the most-recent year's parcel record when an SDF_ID appears across files
parcel_df = (
    parcel_df
    .sort_values("parcel_year", ascending=False)
    .drop_duplicates("SDF_ID")
    .drop(columns="parcel_year")
)

def normalize_zip(z):
    """Coerce a raw zip_code value to a valid 5-digit string or None.

    Accepts trailing whitespace, ZIP+4 ("46202-0001"), float strings
    ("46202.0"), and 3- or 4-digit truncations (left-padded to 5).
    Rejects null/empty values, non-digit strings, lengths > 5, and
    the placeholder "00000".
    """
    if pd.isna(z):
        return None
    s = str(z).strip().split("-")[0]
    # Strip float-format suffix (e.g. "46202.0" → "46202") before digit check
    if "." in s:
        integer_part, decimal_part = s.split(".", 1)
        if decimal_part.lstrip("0") == "":
            s = integer_part
    if not s.isdigit():
        return None
    if 3 <= len(s) <= 5:
        s = s.zfill(5)
    if len(s) != 5 or s == "00000":
        return None
    return s


parcel_df["zip_code"] = parcel_df["zip_code"].map(normalize_zip)
n_parcel_total = len(parcel_df)
parcel_df = parcel_df[parcel_df["zip_code"].notna()].copy()
n_parcel_dropped = n_parcel_total - len(parcel_df)
print(f"Unique parcels loaded: {len(parcel_df):,} "
      f"(dropped {n_parcel_dropped:,} with malformed/empty zip_code)")

# ── Step 3: Join zip codes to transaction data ────────────────────────────────

print("\nJoining zip codes to transaction data...")

sdf = pd.read_csv(OUTPUT_FILE)
sdf_with_zip = sdf.merge(parcel_df, on="SDF_ID", how="left")

match_rate = sdf_with_zip["zip_code"].notna().mean()
print(f"Zip match rate: {match_rate:.1%}")

# ── Filter to matched, valid zip codes only ──────────────────────────────────
# parcel_df has already been normalized by `normalize_zip` above, so any
# remaining NaN here is a transaction whose SDF_ID had no matching parcel
# record OR whose parcel had a malformed zip that we dropped earlier.
n_before_zip_filter = len(sdf_with_zip)
sdf_with_zip = sdf_with_zip[sdf_with_zip["zip_code"].notna()].copy()
n_dropped_zip = n_before_zip_filter - len(sdf_with_zip)
print(f"Rows with valid zip code: {len(sdf_with_zip):,} "
      f"(dropped {n_dropped_zip:,} unmatched/invalid)")

# ── Step 3b: K-means price segmentation ──────────────────────────────────────
# K-means (k=4) on raw sale_price — no scaling, no log transform.
# Raw Euclidean distances on dollar values naturally find market-gap breaks.
# Confirmed breakpoints (2021–2025 data): $380K (entry/move_up),
# $1.05M (move_up/luxury). Top two clusters (luxury + ultra-luxury)
# collapsed due to thin ultra-luxury sample (n≈112).

# Cap at $15M before fitting — data entry errors above this threshold
# catastrophically distort raw-price k-means cluster centers.
# pd.cut below is still applied to the full sdf_with_zip dataset.
prices_capped = sdf_with_zip.loc[
    sdf_with_zip["sale_price"] <= 15_000_000, ["sale_price"]
]

kmeans = KMeans(n_clusters=4, random_state=42, n_init=10)
kmeans.fit(prices_capped)

centers_price = np.sort(kmeans.cluster_centers_.flatten())
print(f"\nK-means cluster centers (price): {[f'${c:,.0f}' for c in centers_price]}")

breaks = [
    (centers_price[0] + centers_price[1]) / 2,
    (centers_price[1] + centers_price[2]) / 2,
]
print(f"Derived breakpoints: entry/move_up=${breaks[0]:,.0f}  move_up/luxury=${breaks[1]:,.0f}")

EXPECTED_ENTRY_BREAK  = 380_000
EXPECTED_LUXURY_BREAK = 1_050_000
BREAK_TOLERANCE       = 50_000
if abs(breaks[0] - EXPECTED_ENTRY_BREAK) > BREAK_TOLERANCE:
    raise ValueError(
        f"entry/move_up break ${breaks[0]:,.0f} deviates more than "
        f"${BREAK_TOLERANCE:,} from expected ${EXPECTED_ENTRY_BREAK:,}. "
        "Check arm's-length filters and input data before proceeding."
    )
if abs(breaks[1] - EXPECTED_LUXURY_BREAK) > BREAK_TOLERANCE:
    raise ValueError(
        f"move_up/luxury break ${breaks[1]:,.0f} deviates more than "
        f"${BREAK_TOLERANCE:,} from expected ${EXPECTED_LUXURY_BREAK:,}. "
        "Check arm's-length filters and input data before proceeding."
    )

PRICE_BINS   = [0, breaks[0], breaks[1], 15_000_000]
PRICE_LABELS = ["entry", "move_up", "luxury"]

sdf_with_zip["price_segment"] = pd.cut(
    sdf_with_zip["sale_price"],
    bins=PRICE_BINS,
    labels=PRICE_LABELS,
)

# `pd.cut` returns NaN for rows that fall on a bin edge or outside the range
# (in particular sale_price == 0, == breaks[0]/breaks[1] under right=True
# semantics, or > 15M which the price filter should already exclude).
# Backfill any remaining NA categories by direct comparison to the derived
# break points so every row carries an explicit segment label.
na_segment_mask = sdf_with_zip["price_segment"].isna()
n_na_segment = int(na_segment_mask.sum())
if n_na_segment:
    fallback_prices = sdf_with_zip.loc[na_segment_mask, "sale_price"]
    fallback_labels = np.where(
        fallback_prices <= breaks[0], "entry",
        np.where(fallback_prices <= breaks[1], "move_up", "luxury"),
    )
    # pandas refuses .loc assignment of a Categorical with non-identical
    # categories, so cast the column to object, fill the NAs, then rebuild
    # the Categorical with the canonical ordered label set.
    seg = sdf_with_zip["price_segment"].astype("object")
    seg.loc[na_segment_mask] = fallback_labels
    sdf_with_zip["price_segment"] = pd.Categorical(seg, categories=PRICE_LABELS)
    print(f"[WARN] Re-assigned {n_na_segment:,} NA price_segment rows "
          f"to nearest tier by sale_price vs derived breakpoints "
          f"(${breaks[0]:,.0f}, ${breaks[1]:,.0f})")

print(f"\nPrice segment distribution:")
print(sdf_with_zip["price_segment"].value_counts().sort_index())
print(f"\nBy county and segment:")
print(sdf_with_zip.groupby(["county", "price_segment"]).size().unstack(fill_value=0))

# ── Step 3c: ZCTA HHI — Census ACS 2023 5-year ───────────────────────────────
# Median household income at ZCTA level (B19013_001E).
# ACS ZCTA endpoint requires a national pull; filtered to study-area zip codes.
# Cached to hhi_zcta.csv — re-run only if the cache is missing.
# County-level Census controls (median_hhi, population) are pulled separately
# in 01_data_pipeline.R — different geography, different analytical purpose.

study_zips = set(
    sdf_with_zip["zip_code"]
    .dropna()
    .loc[lambda s: s != "00000"]
)

if os.path.exists(HHI_ZCTA_CACHE):
    hhi_zcta = pd.read_csv(HHI_ZCTA_CACHE, dtype={"zip_code": str})
    hhi_zcta["zip_code"] = hhi_zcta["zip_code"].str.zfill(5)
    print(f"Loaded ZCTA HHI from cache: {len(hhi_zcta)} zip codes")
else:
    if not CENSUS_API_KEY:
        raise EnvironmentError(
            "CENSUS_API_KEY is not set. Export the variable before running "
            "this script, or place it in a .env file."
        )
    print("Fetching ZCTA HHI from Census API (national pull, one-time)...")
    resp = requests.get(
        "https://api.census.gov/data/2023/acs/acs5",
        params={
            "get": "NAME,B19013_001E",
            "for": "zip code tabulation area:*",
            "key": CENSUS_API_KEY,
        },
        timeout=120,
    )
    resp.raise_for_status()
    raw = resp.json()
    hhi_zcta = pd.DataFrame(raw[1:], columns=raw[0])
    hhi_zcta = hhi_zcta.rename(
        columns={"zip code tabulation area": "zip_code", "B19013_001E": "zcta_hhi"}
    )[["zip_code", "zcta_hhi"]]
    hhi_zcta["zcta_hhi"] = pd.to_numeric(hhi_zcta["zcta_hhi"], errors="coerce")
    hhi_zcta = hhi_zcta[
        hhi_zcta["zip_code"].isin(study_zips)
        & hhi_zcta["zcta_hhi"].notna()
        & (hhi_zcta["zcta_hhi"] > 0)
    ].copy()
    hhi_zcta.to_csv(HHI_ZCTA_CACHE, index=False)
    print(f"Saved {HHI_ZCTA_CACHE}: {len(hhi_zcta)} zip codes")

# ── Step 4: Zip-level summary ─────────────────────────────────────────────────

print("\nBuilding zip-level summary...")

zip_summary = (
    sdf_with_zip[sdf_with_zip["sale_price"] > 50_000]
    .groupby(["zip_code", "county"])
    .agg(
        median_sale_price = ("sale_price", "median"),
        transactions      = ("sale_price", "count"),
        pct_move_up       = ("price_segment", lambda x: (x == "move_up").mean() * 100),
    )
    .reset_index()
    .query("transactions >= 10")
)

# Join ZCTA-level median household income — hhi_zcta already loaded in Step 3c
zip_summary = zip_summary.merge(hhi_zcta, on="zip_code", how="left")

missing_hhi = zip_summary["zcta_hhi"].isna().sum()
print(f"Zip codes missing HHI: {missing_hhi}")

# Monthly payment assumes 80% LTV and the latest available FRED 30-yr fixed rate.
# This rate is used only for the zip-level affordability summary in zip_median_prices.csv.
# The canonical affordability computation for regression models uses the monthly FRED
# rate from 01_data_pipeline.R, which is time-varying and always current.
RATE_MONTHLY = 0.062 / 12
zip_summary["monthly_payment"] = (
    zip_summary["median_sale_price"] * 0.8
    * (RATE_MONTHLY * (1 + RATE_MONTHLY) ** 360)
    / ((1 + RATE_MONTHLY) ** 360 - 1)
)
# Affordability ratio: annual mortgage cost as share of median HHI
zip_summary["afford_ratio_zip"] = (
    zip_summary["monthly_payment"] * 12 / zip_summary["zcta_hhi"]
)

print(f"Zip codes with >= 10 transactions: {len(zip_summary)}")
print("\nBy county:")
print(zip_summary.groupby("county")[["zip_code", "median_sale_price"]].agg(
    zip_count=("zip_code", "count"),
    median_price=("median_sale_price", "median")
))

print("\nTop 10 zip codes by median price:")
print(zip_summary.sort_values("median_sale_price", ascending=False).head(10).to_string())

# ── Step 4b: Post-filter validation ───────────────────────────────────────────
# Asserts the invariants that 03_regression_hypothesis_tests.R relies on:
#   * no null zip_code / sale_price / sale_date / price_segment
#   * no rows at the strict price floor ($50,000 exactly)
#   * no rows above the strict price ceiling ($15,000,000)
#   * every zip_code is exactly 5 digits
# Raises AssertionError if any invariant is violated — the pipeline should
# fail loudly rather than write a contaminated CSV.

n_final     = len(sdf_with_zip)
null_zip    = int(sdf_with_zip["zip_code"].isna().sum())
null_price  = int(sdf_with_zip["sale_price"].isna().sum())
null_date   = int(sdf_with_zip["sale_date"].isna().sum())
null_seg    = int(sdf_with_zip["price_segment"].isna().sum())
n_at_floor  = int((sdf_with_zip["sale_price"] == 50_000).sum())
n_above_cap = int((sdf_with_zip["sale_price"] > 15_000_000).sum())
zip_ok      = sdf_with_zip["zip_code"].astype(str).str.match(r"^\d{5}$").fillna(False)
n_bad_zip   = int((~zip_ok).sum())
price_min   = sdf_with_zip["sale_price"].min()
price_max   = sdf_with_zip["sale_price"].max()

print("\n── Validation ─────────────────────────────────────────────────────")
print(f"  Final rows                : {n_final:,}")
print(f"  Null zip_code             : {null_zip}")
print(f"  Null sale_price           : {null_price}")
print(f"  Null sale_date            : {null_date}")
print(f"  Null price_segment        : {null_seg}")
print(f"  sale_price == 50,000      : {n_at_floor}")
print(f"  sale_price >  15,000,000  : {n_above_cap}")
print(f"  Malformed zip_code        : {n_bad_zip}")
print(f"  sale_price min / max      : ${price_min:,.0f} / ${price_max:,.0f}")

assert null_zip    == 0, f"zip_code has {null_zip} null values"
assert null_price  == 0, f"sale_price has {null_price} null values"
assert null_date   == 0, f"sale_date has {null_date} null values"
assert null_seg    == 0, f"price_segment has {null_seg} null values"
assert n_at_floor  == 0, f"{n_at_floor} rows at sale_price == 50,000"
assert n_above_cap == 0, f"{n_above_cap} rows above sale_price 15,000,000"
assert n_bad_zip   == 0, f"{n_bad_zip} malformed zip_code values"

# ── Step 5: Save final outputs ────────────────────────────────────────────────

os.makedirs(ROOT / "data/processed", exist_ok=True)
sdf_with_zip.to_csv(ROOT / "data/processed/sdf_indiana.csv", index=False)
zip_summary.to_csv(ROOT / "data/processed/zip_median_prices.csv", index=False)

print("\n── Complete ──────────────────────────────────────────────────────────")
print(f"  sdf_indiana.csv  — {len(sdf_with_zip):,} transactions")
print(f"  Columns: {list(sdf_with_zip.columns)}")
print(f"  zip_median_prices.csv  — {len(zip_summary):,} zip codes")

# ── Step 6: Sanity check — price distribution on final clean data ─────────────

print("\nFinal price distribution:")
for floor, ceil in [
    (50_000,    300_000),
    (300_000,   600_000),
    (600_000,  1_000_000),
    (1_000_000, 15_000_000),
]:
    n = sdf_with_zip["sale_price"].between(floor, ceil).sum()
    pct = n / len(sdf_with_zip) * 100
    ceil_label = f"${ceil/1e3:.0f}K" if ceil < 1_000_000 else f"${ceil/1e6:.0f}M"
    print(f"  ${floor/1e3:.0f}K–{ceil_label}: {n:,}  ({pct:.1f}%)")

print("\nMedian sale price by county:")
print(
    sdf_with_zip.groupby("county")["sale_price"]
    .median()
    .round(0)
    .to_string()
)