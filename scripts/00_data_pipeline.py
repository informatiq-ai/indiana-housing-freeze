"""
00_data_pipeline.py
────────────────────────────────────────────────────────────────────────────────
Indiana Mid-Luxury Housing Study — Clean Data Pipeline

Methodology:
  County normalization  — strips trailing "COUNTY" suffix and uppercases County_Name
                          before filtering, resolving format inconsistencies in SDF data
  Property type         — requires C10_Residential_Property = Y and all other C10
                          flags = N; excludes mixed-use parcels
  Arm's-length criteria — requires B1_Valuable_Consider = Y; excludes sheriff sales,
                          short sales, and quitclaim deeds
  Assessor quality gate — requires P2_16_Valid_Trending = Y; removes data-entry errors
                          and non-market transfers
  AV cleaning           — excludes total_av <= $10K; winsorizes sales_ratio at P99
  Price segmentation    — k-means (k=4) on log(sale_price); top two tiers collapsed
                          into luxury; natural breaks at ~$388K and ~$1.04M

Outputs:
  sdf_indiana.csv       — transaction-level cleaned data
  zip_median_prices.csv — zip-level summary for mapping
  hhi_zcta.csv          — ZCTA-level median household income (Census ACS 2023 5-yr)
"""

import os
import requests
import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

# Download and cache Redfin data — skip download if cache already exists
REDFIN_CACHE = "data/processed/redfin_indiana.csv"
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
HHI_ZCTA_CACHE  = "data/processed/hhi_zcta.csv"

TARGET_COUNTIES = {"MARION", "HAMILTON", "BOONE", "HENDRICKS", "JOHNSON"}

YEARS     = [2021, 2022, 2023, 2024, 2025]
INPUT_DIR = "."
OUTPUT_FILE = "data/processed/sdf_indiana.csv"

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
    "C3_Quitclaim",
    "P2_16_Valid_Trending",
]

# Price segments confirmed via k-means (k=4, top two tiers collapsed into luxury)
# Natural breaks at $388K and $1.04M
PRICE_LABELS = ["entry", "mid_luxury", "luxury"]

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

    # ── Assessor quality flag ─────────────────────────────────────────────────
    # P2_16_Valid_Trending = Y means the assessor validated this sale for use
    # in trending/mass appraisal. Non-Y records include data entry errors,
    # related-party transfers, and non-market transactions.
    df = df[df["P2_16_Valid_Trending"] == "Y"].copy()

    # ── Price conversion (cents → dollars) ────────────────────────────────────
    df["sale_price"] = pd.to_numeric(df["E1_Sales_Price"], errors="coerce") / 100
    df = df[df["sale_price"] >= 50_000].copy()

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
        "C8_Market_Days":     "dom_reported",
        "P2_16_Valid_Trending": "valid_trending",
    })

    df["data_year"] = year
    print(f"  SALEDISC{year}: {len(df):,} qualifying transactions")
    all_years.append(df)

# ── Combine years ─────────────────────────────────────────────────────────────

final = pd.concat(all_years, ignore_index=True)
print(f"Combined: {len(final):,} transactions across {final['county'].nunique()} counties")

final = final[[
    "SDF_ID", "county", "year", "month", "sale_date",
    "sale_price", "dom_reported",
    "valid_trending", "data_year",
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
        usecols=["SDF_ID", "A5_ZipCode", "P2_6_Prop_Class_Code", "P2_5_Total_AV"],
        dtype=str,
        low_memory=False,
    )
    p["parcel_year"] = year  # track source year for deterministic deduplication
    parcels.append(p)
    print(f"  {fname}: {len(p):,} rows")

parcel_df = pd.concat(parcels, ignore_index=True)
parcel_df = parcel_df.rename(columns={
    "A5_ZipCode":          "zip_code",
    "P2_6_Prop_Class_Code": "prop_class_code",
    "P2_5_Total_AV":        "total_av",
})
# Keep the most-recent year's parcel record when an SDF_ID appears across files
parcel_df = (
    parcel_df
    .sort_values("parcel_year", ascending=False)
    .drop_duplicates("SDF_ID")
    .drop(columns="parcel_year")
)

parcel_df["zip_code"] = (
    parcel_df["zip_code"]
    .str.strip()
    .str.split("-").str[0]
    .str.zfill(5)
)

# Convert total_av to numeric (already in dollars, no conversion needed)
parcel_df["total_av"] = pd.to_numeric(parcel_df["total_av"], errors="coerce")

print(f"Unique parcels loaded: {len(parcel_df):,}")

# ── Step 3: Join zip codes to transaction data ────────────────────────────────

print("\nJoining zip codes to transaction data...")

sdf = pd.read_csv(OUTPUT_FILE)
sdf_with_zip = sdf.merge(parcel_df, on="SDF_ID", how="left")

match_rate = sdf_with_zip["zip_code"].notna().mean()
print(f"Zip match rate: {match_rate:.1%}")

# ── Clean total_av ────────────────────────────────────────────────────────────
# Exclude zero/negative AV (land-only or data errors)
# Winsorize sales ratio at 99th percentile to remove extreme outliers
sdf_with_zip = sdf_with_zip[
    sdf_with_zip["zip_code"].notna() &
    (sdf_with_zip["zip_code"] != "00000")
].copy()

sdf_with_zip["total_av"] = pd.to_numeric(sdf_with_zip["total_av"], errors="coerce")
sdf_with_zip = sdf_with_zip[sdf_with_zip["total_av"] > 10_000].copy()

sdf_with_zip["sales_ratio"] = sdf_with_zip["sale_price"] / sdf_with_zip["total_av"]
ratio_cap = sdf_with_zip["sales_ratio"].quantile(0.99)
sdf_with_zip = sdf_with_zip[sdf_with_zip["sales_ratio"] <= ratio_cap].copy()

sdf_with_zip["log_av"] = np.log(sdf_with_zip["total_av"])

print(f"Rows after AV cleaning: {len(sdf_with_zip):,}")
print(f"\nSales ratio by county (median):")
print(sdf_with_zip.groupby("county")["sales_ratio"].median().round(3))

# ── Step 3b: K-means price segmentation ──────────────────────────────────────
# Fits k=4 on log(sale_price) to find natural price tier breaks.
# Log transform prevents high-end outliers from pulling cluster centers.
# Clusters sorted ascending; top two tiers (luxury / ultra-luxury) collapsed
# into a single luxury bracket due to insufficient ultra-luxury sample size
# for county-level DiD analysis (n=48 ultra-luxury vs 3,547 luxury).


# Fit on log-transformed prices; $15M upper bin in pd.cut absorbs extreme outliers
prices_log = np.log(sdf_with_zip["sale_price"].values).reshape(-1, 1)

kmeans = KMeans(n_clusters=4, random_state=42, n_init=10)
kmeans.fit(prices_log)

# Sort cluster centers back into price space
centers_price = np.sort(np.exp(kmeans.cluster_centers_.flatten()))
print(f"\nK-means cluster centers (price): {[f'${c:,.0f}' for c in centers_price]}")

# Breakpoints = midpoints between adjacent sorted cluster centers
breaks = [
    (centers_price[0] + centers_price[1]) / 2,  # entry → mid_luxury
    (centers_price[1] + centers_price[2]) / 2,  # mid_luxury → luxury (top two collapsed)
]
print(f"Derived breakpoints: entry/mid_luxury=${breaks[0]:,.0f}  mid_luxury/luxury=${breaks[1]:,.0f}")

# Validate breakpoints against documented values; warn loudly if data drift has
# shifted them more than the expected tolerance.
EXPECTED_ENTRY_BREAK  = 388_000
EXPECTED_LUXURY_BREAK = 1_040_000
BREAK_TOLERANCE       = 50_000
if abs(breaks[0] - EXPECTED_ENTRY_BREAK) > BREAK_TOLERANCE:
    print(f"WARNING: entry/mid_luxury break ${breaks[0]:,.0f} deviates more than "
          f"${BREAK_TOLERANCE:,} from expected ${EXPECTED_ENTRY_BREAK:,}. "
          "Re-verify price tier labels and downstream analysis.")
if abs(breaks[1] - EXPECTED_LUXURY_BREAK) > BREAK_TOLERANCE:
    print(f"WARNING: mid_luxury/luxury break ${breaks[1]:,.0f} deviates more than "
          f"${BREAK_TOLERANCE:,} from expected ${EXPECTED_LUXURY_BREAK:,}. "
          "Re-verify price tier labels and downstream analysis.")

# k-means derived breaks (confirmed run values: $388K / $1.04M)
PRICE_BINS   = [0, breaks[0], breaks[1], 15_000_000]
PRICE_LABELS = ["entry", "mid_luxury", "luxury"]

# ── Price segments ────────────────────────────────────────────────────────────
# K-means (k=4) natural breaks, ultra-luxury collapsed into luxury
sdf_with_zip["price_segment"] = pd.cut(
    sdf_with_zip["sale_price"],
    bins   = PRICE_BINS,
    labels = PRICE_LABELS,
)

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
    sdf_with_zip[sdf_with_zip["sale_price"] >= 50_000]
    .groupby(["zip_code", "county"])
    .agg(
        median_sale_price = ("sale_price", "median"),
        transactions      = ("sale_price", "count"),
        pct_mid_luxury    = ("price_segment", lambda x: (x == "mid_luxury").mean() * 100),
    )
    .reset_index()
    .query("transactions >= 10")
)

# Join ZCTA-level median household income — hhi_zcta already loaded in Step 3c
zip_summary = zip_summary.merge(hhi_zcta, on="zip_code", how="left")

missing_hhi = zip_summary["zcta_hhi"].isna().sum()
print(f"Zip codes missing HHI: {missing_hhi}")

# Monthly payment assumes 20% down, 30-yr fixed at 6.2% (2024 annual average)
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

# ── Step 5: Save final outputs ────────────────────────────────────────────────

os.makedirs("data/processed", exist_ok=True)
sdf_with_zip.to_csv("data/processed/sdf_indiana.csv", index=False)
zip_summary.to_csv("data/processed/zip_median_prices.csv", index=False)

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