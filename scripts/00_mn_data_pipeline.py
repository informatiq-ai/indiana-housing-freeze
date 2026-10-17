#!/usr/bin/env python3
"""Build the Minnesota inputs for the established move-up squeeze analysis.

Requires ``scripts/research/01_prepare_transactions.py`` to have written the
harmonized transactions and the eCRV address export, and the research panel
step to have cached the national Redfin county tracker. Writes, under
``data/processed/mn/``:

  sdf_minnesota_nominal.csv   sales in the Indiana SDF contract, 2021–2025,
                              segmented on nominal prices (the published method)
  redfin_minnesota.csv        Redfin county-tracker rows for the seven counties
  hhi_zcta_mn.csv             ACS 2023 5-year ZCTA median household income
  zip_median_prices_mn_nominal.csv  ZIP summary in the Indiana map-input contract
  sdf_minnesota_core_cities_nominal.csv  the same sales with Hennepin and Ramsey
                              split into Minneapolis, St. Paul, and balances
  core_city_controls_<geography>.csv     ACS income and population per area

plus segment-fit audit files under ``outputs/mn/squeeze/``. ``--price-basis
real`` writes the constant-dollar variant without the ``_nominal`` suffix.
The Census pulls need ``CENSUS_API_KEY`` and are cached after the first run.
"""

import argparse
import json
import os
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from inflation import load_monthly_cpi
from mn_squeeze.core_cities import (
    GEOGRAPHIES, fetch_acs_controls, geography_controls, relabel_core_cities,
)
from mn_squeeze.external import extract_redfin, fetch_zcta_hhi, zip_summary
from mn_squeeze.sample import (
    COHORTS, PRICE_BASES, build_sample, read_inputs, segment_counts,
)

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data/processed/mn"
CPI_CACHE = ROOT / "data/processed/cpi_u_monthly_2015_2025.csv"
CPI_RESEARCH_FALLBACK = ROOT / "data/processed/research/external/fred_monthly.csv"
REDFIN_NATIONAL = ROOT / "data/processed/research/external/county_market_tracker.tsv000.gz"
REDFIN_CACHE = PROCESSED / "redfin_minnesota.csv"
HHI_ZCTA_CACHE = PROCESSED / "hhi_zcta_mn.csv"
ACS_CONTROLS_CACHE = PROCESSED / "acs_controls_mn.csv"


def load_zcta_hhi(study_zips: set[str]) -> pd.DataFrame:
    """Return cached ZCTA income, refreshing the cache if study ZIPs are absent."""
    if HHI_ZCTA_CACHE.exists():
        cached = pd.read_csv(HHI_ZCTA_CACHE, dtype={"zip_code": str})
        cached["zip_code"] = cached["zip_code"].str.zfill(5)
        if study_zips <= set(cached["zip_code"]) | _zips_without_income(cached):
            return cached
    hhi = fetch_zcta_hhi(study_zips, os.environ.get("CENSUS_API_KEY", ""))
    hhi.to_csv(HHI_ZCTA_CACHE, index=False)
    # Record ZIPs the ACS does not publish so the cache is not refetched each run.
    missing = sorted(study_zips - set(hhi["zip_code"]))
    (PROCESSED / "hhi_zcta_mn_unpublished.json").write_text(json.dumps(missing) + "\n")
    return hhi


def _zips_without_income(cached: pd.DataFrame) -> set[str]:
    path = PROCESSED / "hhi_zcta_mn_unpublished.json"
    return set(json.loads(path.read_text())) if path.exists() else set()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", choices=COHORTS, default="residential")
    # nominal = the published 2021–2025 method; real = the constant-dollar revision.
    parser.add_argument("--price-basis", choices=PRICE_BASES, default="nominal")
    args = parser.parse_args()

    suffix = "" if args.cohort == "residential" else f"_{args.cohort}"
    if args.price_basis == "nominal":
        suffix += "_nominal"
    audit_dir = ROOT / "outputs/mn/squeeze"
    audit_dir.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)

    transactions, addresses = read_inputs(ROOT)
    cpi = load_monthly_cpi(CPI_CACHE, 2015, 2025, fallback_path=CPI_RESEARCH_FALLBACK)
    sample, fit, funnel = build_sample(
        transactions, addresses, cpi, args.cohort, args.price_basis
    )

    sample_path = PROCESSED / f"sdf_minnesota{suffix}.csv"
    sample.to_csv(sample_path, index=False)
    funnel.to_csv(audit_dir / f"sample_funnel{suffix}.csv", index=False)
    segment_counts(sample).to_csv(audit_dir / f"segment_counts{suffix}.csv", index=False)
    (audit_dir / f"price_segment_breaks{suffix}.json").write_text(
        json.dumps(fit, indent=2) + "\n"
    )

    if not REDFIN_CACHE.exists():
        extract_redfin(REDFIN_NATIONAL).to_csv(REDFIN_CACHE, index=False)
    hhi = load_zcta_hhi(set(sample["zip_code"]))
    zips = zip_summary(sample, hhi, args.price_basis)
    zips.to_csv(PROCESSED / f"zip_median_prices_mn{suffix}.csv", index=False)

    # City-based core geographies for the published transaction models.
    if not ACS_CONTROLS_CACHE.exists():
        fetch_acs_controls(os.environ.get("CENSUS_API_KEY", "")).to_csv(
            ACS_CONTROLS_CACHE, index=False
        )
    acs = pd.read_csv(ACS_CONTROLS_CACHE)
    cities = relabel_core_cities(sample)
    cities.to_csv(PROCESSED / f"sdf_minnesota_core_cities{suffix}.csv", index=False)
    for geography in GEOGRAPHIES:
        geography_controls(acs, geography).to_csv(
            PROCESSED / f"core_city_controls_{geography}.csv", index=False
        )
    print(f"Core-city sample: {len(cities):,} sales "
          f"({len(sample) - len(cities):,} Hennepin/Ramsey sales not placed in a city)")

    print(funnel.to_string(index=False))
    print("Segment breaks:", [round(value) for value in fit["breaks"]])
    print(f"Wrote {sample_path.relative_to(ROOT)}: {len(sample):,} sales")
    print(f"ZIP summary: {len(zips)} ZIP-county cells, "
          f"{int(zips['zcta_hhi'].isna().sum())} without ZCTA income")


if __name__ == "__main__":
    main()
