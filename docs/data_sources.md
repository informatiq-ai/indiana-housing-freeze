# Data Sources

This document describes each data source used in the analysis, the filters and transformations applied during ingestion, and the role each source plays in the final analytical dataset. Four primary sources contribute to the panel and deed-record datasets: STATS Indiana Sales Disclosure Form records, Redfin county market tracker data, U.S. Census Bureau American Community Survey estimates, and FRED mortgage rate series.

## STATS Indiana Sales Disclosure Form (SDF) Deed Records

STATS Indiana SDF records provide the core transaction-level dataset. Annual flat files (`SALEDISC20XX.txt`, paired with `SALEPARCEL20XX.txt` for parcel-ZIP linkage) cover arm's-length residential transactions recorded with Indiana county assessors. Files for 2021 through 2025 are ingested by `scripts/00_data_pipeline.py`.

The following filters are applied to isolate arm's-length residential sales meeting assessor quality standards:

- Residential-only parcels: `C10` use-code flag present
- Arm's-length qualification: `B1_Valuable_Consider = Y`, excluding sheriff sales, short sales, and quitclaim deeds
- Assessor quality gate: `P2_16_Valid_Trending = Y`
- Sale price at or above $50,000
- Total assessed value above $10,000
- Sales ratio winsorized at the 99th percentile

SALEPARCEL files are used to join ZIP codes to deed records. When a parcel appears in multiple annual SALEPARCEL files, the record from the most recent year is retained to reflect current assessor data. The five-county study area (Marion, Hamilton, Boone, Hendricks, Johnson) is enforced by FIPS code filter. After all filters, the dataset contains 198,407 arm's-length residential transactions. This file is distributed in `data/processed/sdf_indiana.csv` as the pre-processed substitute; the original SDF flat files are not redistributed.

## Redfin County Market Tracker

Redfin publishes a public county-level market tracker updated monthly. The file is downloaded directly by `scripts/00_data_pipeline.py` from Redfin's data download portal and cached locally at `data/processed/redfin_indiana.csv` to avoid repeated downloads. The tracker supplies monthly aggregated metrics at the county level: median sale price, median days on market, sale-to-list ratio, months of supply, share of homes sold above list price, and share with price drops. Only the five study counties and the period January 2021 through December 2025 are retained. Days-on-market figures from Redfin are subject to delist-relist cycling and represent a lower bound on true time-to-sale.

## U.S. Census Bureau American Community Survey (ACS)

Two separate ACS queries are used, both drawing on the 2023 5-year estimates (the most recent available at time of analysis).

**County-level controls** are pulled by `scripts/01_data_pipeline.R` via the Census API (variable `B19013_001E` for median household income and `B01001_001E` for total population) for the five study counties. These are used as controls in the county-month panel regression models. Results are cached at `data/processed/census_county_controls.csv` after the first successful API call.

**ZCTA-level median household income** is pulled by `scripts/00_data_pipeline.py` (Step 3c) via the Census API for all ZIP Code Tabulation Areas in Indiana. Records are filtered to the ZIP codes present in the SDF deed records. The ZCTA-level HHI is joined to the deed record dataset to support ZIP-code-level affordability analysis and the squeeze map (Figure 10). Results are cached at `data/processed/hhi_zcta.csv`.

The ACS 2023 5-year estimates are cross-sectional and applied uniformly across all study years. This means year-over-year variation in county or ZIP income is not captured; the income controls reflect end-of-study conditions rather than a true time-varying series.

## FRED MORTGAGE30US

The Federal Reserve Bank of St. Louis publishes the weekly 30-year fixed mortgage rate series (MORTGAGE30US) through the FRED API. `scripts/01_data_pipeline.R` queries this series for the period January 2021 through December 2025 and converts weekly observations to monthly averages. The `rate_gap` variable is then computed as `mortgage_rate - 3.0`, where 3.0 percentage points represents the approximate 2021 baseline rate. The post-shock indicator is set to 1 when `rate_gap >= 2.0`. Access requires a `FRED_API_KEY` set in `.Renviron`. If the December 2025 rate observation is not yet available, the pipeline falls back to the most recent available month with a console warning.

## Study Area

The analysis covers five counties in the Indianapolis metropolitan statistical area (MSA). Marion County (Indianapolis proper) serves as the DiD control group on the basis that its income structure ($63,450 median HHI) structurally limits mid-luxury demand independent of interest rate conditions. The four suburban counties constitute the treated group.

| County | Geography | Median HHI | Population |
|--------|-----------|------------|------------|
| Marion | Metro (control) | $63,450 | 971,822 |
| Hamilton | Suburb (treated) | $117,957 | 357,176 |
| Boone | Suburb (treated) | $104,865 | 72,827 |
| Hendricks | Suburb (treated) | $99,988 | 179,379 |
| Johnson | Suburb (treated) | $87,227 | 163,983 |

Source: Census ACS 2023 5-year estimates.

## Derived Variables

The following variables are computed during pipeline construction and are not present in any raw source file.

`rate_gap` is the monthly 30-year fixed mortgage rate (%) minus 3.0, in percentage points. It measures the spread above the 2021 baseline and is the primary continuous treatment measure.

`post` is a binary indicator equal to 1 when `rate_gap >= 2.0` (i.e., when the mortgage rate exceeds 5.0%). It marks the onset of the rate lock-in shock period.

`treated` is a binary indicator equal to 1 for suburban counties (Hamilton, Boone, Hendricks, Johnson) and 0 for Marion County.

`did` is the product of `treated` and `post`, the standard DiD interaction term.

`affordability_ratio` is the estimated monthly mortgage payment as a share of median household income. The monthly payment assumes an 80% LTV ratio and the prevailing 30-year fixed rate for the observation month.

`price_segment` is assigned by k-means clustering (k = 4 on log(sale_price)) with the top two clusters collapsed to luxury. The entry/mid-luxury breakpoint falls at approximately $388,000 and the mid-luxury/luxury breakpoint at approximately $1,040,000.

`log_av` is the natural log of total assessor-reported assessed value, used in the continuous quadratic robustness model.
