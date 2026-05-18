# Indiana Move-Up Housing Market Squeeze

Quantitative research examining how mortgage rate lock-in has disproportionately suppressed the move-up residential market ($380K–$1.05M) across the Indianapolis metropolitan area, 2021–2025. The analysis combines Difference-in-Differences (DiD) models, individual deed records, and a county-month panel to distinguish two mechanisms driving the same affordability outcome: rate payment shock in suburban markets and structural income constraint in Marion County.

## Research Question

Does mortgage rate lock-in disproportionately suppress move-up transaction volumes and prices in Indianapolis suburbs relative to Marion County, controlling for income levels and pre-existing price trends?

## Key Findings

Move-up properties are 4.5 times more sensitive to the rate lock-in gap than entry-tier homes (−4.9%/pp vs. −1.1%/pp, derived from the price interaction model, N = 269,992). At the current 3.2 percentage point gap above the 2021 baseline, move-up prices are estimated approximately 14.9% below their pre-shock trajectory. The DiD triple interaction (Suburb × Post × Move-up) is statistically significant (p < 0.01), confirming that suburban move-up properties bear a disproportionate burden from the rate shock relative to the Marion County baseline. A Welch two-sample t-test shows entry-tier prices appreciated 7.2% post-shock while move-up appreciated only 3.0%, with both differences rejecting the null hypothesis (p < 2.2e-16). Marion County never produces meaningful move-up volume, not because of rate sensitivity, but because its median household income ($63,450) structurally precludes sustained demand in that price range. The two mechanisms converge on the same market freeze through different channels.

## Data

**STATS Indiana Sales Disclosure Form (SDF) deed records** provide 269,992 arm's-length residential transactions across five Indianapolis-area counties, 2021–2025. Filters applied: residential-only parcels (C10 flags), arm's-length qualification (B1_Valuable_Consider = Y; no sheriff, short, or quitclaim sales), and sale price above $50K.

**Redfin county market tracker** supplies monthly county-level median sale price, days on market, sale-to-list ratio, months of supply, and seller stress indicators (share sold above list, share with price drops), filtered to the five study counties for 2021–2025.

**U.S. Census Bureau American Community Survey 2023 5-year estimates** provide county-level median household income and population, plus ZCTA-level median household income for ZIP codes across the study area.

**Federal Reserve Bank of St. Louis (FRED) MORTGAGE30US** supplies the monthly 30-year fixed mortgage rate series used to construct the rate lock-in gap variable.

## Study Area

Five counties in the Indianapolis metropolitan area are included. Marion County (Indianapolis proper) serves as the control group. The four suburban counties serve as the treated group.

| County | Geography | Median HHI | Population |
|--------|-----------|------------|------------|
| Marion | Metro (control) | $63,450 | 971,822 |
| Hamilton | Suburb (treated) | $117,957 | 357,176 |
| Boone | Suburb (treated) | $104,865 | 72,827 |
| Hendricks | Suburb (treated) | $99,988 | 179,379 |
| Johnson | Suburb (treated) | $87,227 | 163,983 |

Source: Census ACS 2023 5-year estimates.

## Price Segmentation

Price tiers are derived from k-means clustering (k = 4) on raw sale_price (with a pre-fit cap at $15M to suppress data-entry outliers), with the top two clusters collapsed due to insufficient ultra-luxury sample size (n = 112 ultra-luxury vs. 4,700 luxury). Natural breakpoints fall at approximately $380K and $1.05M.

| Segment | Price Range | N (2021–2025) |
|---------|-------------|---------------|
| Entry | Below $380K | 186,820 |
| Move-up | $380K to $1.05M | 78,360 |
| Luxury | Above $1.05M | 4,812 |

## Identification Strategy

The DiD design exploits the 2022 Federal Reserve tightening cycle as a quasi-natural experiment. The rate lock-in gap (`rate_gap = mortgage_rate − 3.0`) measures percentage points above the 2021 baseline. The post-shock indicator activates when `rate_gap >= 2.0` percentage points (a roughly 5% prevailing mortgage rate), which is crossed in mid-2022 in the FRED series. Treatment is defined by geography: suburban counties (Hamilton, Boone, Hendricks, Johnson) vs. Marion County (control). The triple interaction (Suburb × Post × Move-up) isolates the differential rate-shock effect on suburban move-up properties net of geography and time main effects.

The parallel trends assumption is verified graphically for the pre-shock period (Figure 8): Marion County and suburban sale prices track together at similar growth rates from 2021 through early 2022 and diverge only after the rate shock, supporting DiD validity.

## Repository Structure

```
data/
  raw/           # Original source files -- do not modify
  processed/     # Cleaned outputs from pipeline scripts
outputs/
  figures/       # Static charts (.png and .pdf)
  tables/        # Regression and summary tables (.png)
scripts/         # All analysis scripts (R and Python)
docs/            # Write-ups and publication drafts
```

## Interactive Map App

The primary deliverable is a Streamlit application displaying three ZIP-level choropleth maps across the five-county metro.

```bash
# One-time pre-processing (required before first run)
python scripts/build_simplified_geojson.py

# Launch the app
streamlit run scripts/housing_map_app.py
```

`build_simplified_geojson.py` simplifies the Indiana ZIP GeoJSON from 791K to 145K coordinates and writes the result to `data/zip_geojson_simplified.json`. The app reads this file directly at startup; without it the app will fail to load. Re-run the script if `data/processed/indiana_zips.geojson` is regenerated.

The app provides three switchable views via radio button:

- **Median Household Income** — ZCTA-level medians from the 2023 ACS 5-year estimates, weighted by transaction count. Hover shows HHI, median sale price, affordability ratio, move-up share, and transaction count.
- **Median Sale Price** — Transaction-weighted median sale price by ZIP, 2021–2025. Hover shows price, transaction count, and move-up share.
- **Affordability Stress Ratio** — Price-to-income ratio (median sale price ÷ median HHI) by ZIP; 4× marks the stress threshold. Hover shows HHI, median price, and stress ratio with continuous blue-to-red gradient.

## Scripts

**`scripts/00_data_pipeline.py`** processes STATS Indiana SDF deed records. It loads SALEDISC files for 2021–2025, applies all arm's-length and quality filters, assigns price segments via k-means, joins SALEPARCEL zip codes, joins ZCTA-level HHI, and computes zip-level affordability ratios. Outputs: `data/processed/sdf_indiana.csv` and `data/processed/zip_median_prices.csv`.

**`scripts/01_data_pipeline.R`** builds the county-month panel used in all regression models. It joins Redfin listing data, Census county demographics, ZCTA HHI, and FRED mortgage rates. Computed variables include `rate_gap`, `affordability_ratio`, DiD indicators (`post`, `treated`, `did`), and per-capita transaction counts by segment. Outputs: `data/processed/panel_data.rds` and `data/processed/panel_data.csv`. Requires `CENSUS_API_KEY` and `FRED_API_KEY` in `.Renviron`.

**`scripts/02_eda_descriptive_stats.R`** produces Figures 1 through 10 and Table 1. It loads `panel_data.rds` and `sdf_indiana.csv` and generates descriptive statistics, time series plots, the parallel trends check, price index by segment, affordability ratios, and DOM distributions.

**`scripts/03_regression_hypothesis_tests.R`** estimates all regression models and generates Figures 11 through 13 and Tables 2 through 8. Models include DOM regressions on the panel (N = 300), price models on individual deed records, triple-interaction DiD specifications for price and volume, Welch two-sample t-tests, and the Pearson correlation matrix.

**`scripts/build_simplified_geojson.py`** pre-computes `data/zip_geojson_simplified.json` from the cached Indiana ZIP GeoJSON. Run once before launching the Streamlit app, and again whenever the source GeoJSON is refreshed.

## Outputs

### Figures

| File | Description |
|------|-------------|
| `fig1_rate_gap.png` | 30-year fixed mortgage rate 2021–2025 with the lock-in gap shaded above the 3% baseline |
| `fig2_dom_histogram.png` | Distribution of median days on market, pre-shock (2021) vs. post-shock (2022–2025), by geography |
| `fig3_dom_over_time.png` | Monthly median DOM with 3-month rolling average, Marion County vs. suburbs |
| `fig4_sale_to_list.png` | Average sale-to-list ratio by price segment and geography, annual boxplots |
| `fig5_seller_stress.png` | Share of transactions sold above list price and share with price drops, LOESS smoothed |
| `fig6_transaction_volume.png` | Annual transaction volume by price segment and geography, 2021–2025 |
| `fig7_affordability.png` | Monthly mortgage payment as a share of median HHI by county, relative to the 30% stress threshold |
| `fig8_parallel_trends.png` | Mean sale price by geography on log scale; pre-shock parallel trends verification |
| `fig9_price_index.png` | Median sale price indexed to 2021 = 100, by price segment and geography |
| `fig10_hhi_price_correlation.png` | ZIP-level median HHI vs. median sale price; Pearson correlation across ZIPs |
| `fig11_histogram_price.png` | Distribution of sale prices on log scale, with median annotated and entry-tier share noted |
| `fig12_marginal_effects.png` | Predicted price penalty by rate gap and segment; squeeze multiplier annotated |
| `fig13_zip_squeeze_map.png` | ZIP-level price-to-income stress ratio across the Indianapolis metro |

### Tables

| File | Description |
|------|-------------|
| `table1_descriptive.png` | Descriptive statistics by geography: DOM, sale-to-list, median price, mortgage rate, HHI, population |
| `table2_hypothesis_test.png` | Welch two-sample t-test results: pre vs. post price means by segment and geography |
| `table3_correlation.png` | Pearson correlation matrix for key continuous variables across SDF transactions |
| `table4_standard_error.png` | Standard error of log sale price by price segment with 95% confidence intervals |
| `table5_dom_models.png` | Regression models for median days on market; simple, controlled, interaction, and two-way FE specifications |
| `table6_price_models.png` | Rate lock-in effect on log sale price; rate gap x segment interactions across SDF transactions |
| `table7_did_models.png` | DiD estimates for price and volume; triple-interaction specifications with county and year fixed effects |
| `table8_rate_sensitivity.png` | Rate sensitivity summary derived from the m_price_interact model |

### Interactive Maps

Served by `scripts/housing_map_app.py` (Streamlit). Not committed to the repository; run the app locally with `streamlit run scripts/housing_map_app.py`.

## Limitations

Days-on-market figures from Redfin are subject to delist-relist cycling and represent a lower bound on true time-to-sale. Marion County's near-absence from the move-up segment reflects its income structure ($63,450 median HHI) rather than rate sensitivity, which makes the geography-as-treatment interpretation conservative. ACS income estimates are cross-sectional (2023) and applied uniformly across all study years. County-level geography proxies for buyer type rather than directly measuring it. Known omitted variable candidates include Hamilton County new construction activity driven by Eli Lilly and Amazon expansions, school district quality premiums in Carmel and Fishers, and suburban corridor corporate relocations.

## Reproducibility

All R scripts use `here::here()` for file paths. Python scripts use `pathlib.Path` anchored to the repository root. Set `CENSUS_API_KEY` and `FRED_API_KEY` in `.Renviron` before running `01_data_pipeline.R`. The `00_data_pipeline.py` script requires STATS Indiana SDF flat files (`SALEDISC20XX.txt` and `SALEPARCEL20XX.txt`) placed in the repository root; these files are not redistributed here.

## Data Sources

- STATS Indiana, Sales Disclosure Form deed records, 2021–2025
- Redfin, county market tracker public data
- U.S. Census Bureau, American Community Survey 2023 5-year estimates
- Federal Reserve Bank of St. Louis (FRED), MORTGAGE30US series
