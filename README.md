# Indiana Mid-Luxury Housing Market Squeeze

Quantitative research examining how mortgage rate lock-in has disproportionately suppressed the mid-luxury residential market ($388K–$1M) across the Indianapolis metropolitan area, 2021–2025. The analysis combines Difference-in-Differences (DiD) models, individual deed records, and a county-month panel to distinguish two mechanisms driving the same affordability outcome: rate payment shock in suburban markets and structural income constraint in Marion County.

## Research Question

Does mortgage rate lock-in disproportionately suppress mid-luxury transaction volumes and prices in Indianapolis suburbs relative to Marion County, controlling for income levels and pre-existing price trends?

## Key Findings

Mid-luxury properties are 3.9 times more sensitive to the rate lock-in gap than entry-tier homes (−7.1%/pp vs. −1.8%/pp, derived from the price interaction model, N = 198,407). At the current 3.1 percentage point gap above the 2021 baseline, mid-luxury prices are estimated approximately 20% below their pre-shock trajectory. The DiD triple interaction (Suburb × Post × Mid-luxury) is negative and statistically significant (p < 0.01), confirming that suburban mid-luxury properties bear a disproportionate burden from the rate shock. A Welch two-sample t-test shows entry-tier prices appreciated 10.2% post-shock while mid-luxury appreciated only 3%, with both differences rejecting the null hypothesis (p < 2.2e-16). Marion County never produces meaningful mid-luxury volume, not because of rate sensitivity, but because its median household income ($63,450) structurally precludes sustained demand in that price range. The two mechanisms converge on the same market freeze through different channels.

## Data

**STATS Indiana Sales Disclosure Form (SDF) deed records** provide 198,407 arm's-length residential transactions across five Indianapolis-area counties, 2021–2025. Filters applied: residential-only parcels (C10 flags), arm's-length qualification (B1_Valuable_Consider = Y; no sheriff, short, or quitclaim sales), assessor quality gate (P2_16_Valid_Trending = Y), sale price at or above $50K, and total assessed value above $10K with sales ratio winsorized at the 99th percentile.

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

Price tiers are derived from k-means clustering (k = 4) on log(sale_price), with the top two clusters collapsed due to insufficient ultra-luxury sample size (n = 48 ultra-luxury vs. 3,547 luxury). Natural breakpoints fall at approximately $388K and $1.04M.

| Segment | Price Range | N (2021–2025) |
|---------|-------------|---------------|
| Entry | Below $388K | 139,557 |
| Mid-luxury | $388K to $1M | 55,556 |
| Luxury | Above $1M | 3,294 |

## Identification Strategy

The DiD design exploits the 2022 Federal Reserve tightening cycle as a quasi-natural experiment. The rate lock-in gap (`rate_gap = mortgage_rate − 3.0`) measures percentage points above the 2021 baseline. The post-shock indicator activates when `rate_gap >= 2.0`. Treatment is defined by geography: suburban counties (Hamilton, Boone, Hendricks, Johnson) vs. Marion County (control). The triple interaction (Suburb × Post × Mid-luxury) isolates the differential rate-shock effect on suburban mid-luxury properties net of geography and time main effects.

The parallel trends assumption is verified graphically for the pre-shock period (Figure 7): Marion County and suburban sale prices track together at similar growth rates from 2021 through early 2022 and diverge only after the rate shock, supporting DiD validity.

## Repository Structure

```
data/
  raw/           # Original source files -- do not modify
  processed/     # Cleaned outputs from pipeline scripts
outputs/
  figures/       # Static charts (.png)
  tables/        # Regression and summary tables (.png)
  interactive/   # Interactive HTML maps
scripts/         # All analysis scripts (R and Python)
docs/            # Write-ups and publication drafts
```

## Scripts

**`scripts/data_pipeline.py`** processes STATS Indiana SDF deed records. It loads SALEDISC files for 2021–2025, applies all arm's-length and quality filters, assigns price segments via k-means, joins SALEPARCEL zip codes, joins ZCTA-level HHI, and computes zip-level affordability ratios. Outputs: `data/processed/sdf_indiana.csv` and `data/processed/zip_median_prices.csv`.

**`scripts/01_data_pipeline.R`** builds the county-month panel used in all regression models. It joins Redfin listing data, Census county demographics, ZCTA HHI, and FRED mortgage rates. Computed variables include `rate_gap`, `affordability_ratio`, DiD indicators (`post`, `treated`, `did`), and per-capita transaction counts by segment. Outputs: `data/processed/panel_data.rds` and `data/processed/panel_data.csv`. Requires `CENSUS_API_KEY` and `FRED_API_KEY` in `.Renviron`.

**`scripts/02_eda_descriptive_stats.R`** produces Figures 1 through 8, Figure 12, and Table 1. It loads `panel_data.rds` and `sdf_indiana.csv` and generates descriptive statistics, time series plots, the parallel trends check, price index by segment, affordability ratios, and DOM distributions.

**`scripts/03_regression_hypothesis_tests.R`** estimates all regression models and generates Figure 9 and the interactive squeeze map. Models include DOM regressions on the panel (N = 300), price models on individual deed records (N = 198,407), triple-interaction DiD specifications for price and volume, Welch two-sample t-tests, and the Pearson correlation matrix.

**`scripts/heatmap.py`** generates `outputs/interactive/heatmap_interactive.html`, a Folium choropleth of median sale price by ZIP code using an orange/yellow color scale.

**`scripts/heatmap_hhi.py`** generates `outputs/interactive/heatmap_hhi.html`, a Folium choropleth of median household income by ZIP code using a blue color scale, with affordability ratio and mid-luxury share in the interactive tooltip.

## Outputs

### Figures

| File | Description |
|------|-------------|
| `fig1_rate_gap.png` | 30-year fixed mortgage rate 2021–2025 with the lock-in gap shaded above the 3% baseline |
| `fig2_dom_histogram.png` | Distribution of median days on market, pre-shock (2021) vs. post-shock (2022–2025), by geography |
| `fig3_dom_over_time.png` | Monthly median DOM with 3-month rolling average, Marion County vs. suburbs |
| `fig4_sale_to_list.png` | Average sale-to-list ratio by price segment and geography, annual boxplots |
| `fig4b_seller_stress.png` | Share of transactions sold above list price and share with price drops, LOESS smoothed |
| `fig5_transaction_volume.png` | Annual transaction volume by price segment and geography, 2021–2025 |
| `fig6_affordability.png` | Monthly mortgage payment as a share of median HHI by county, relative to the 30% stress threshold |
| `fig7_parallel_trends.png` | Mean sale price by geography on log scale; pre-shock parallel trends verification |
| `fig8_price_index.png` | Median sale price indexed to 2021 = 100, by price segment and geography |
| `fig9_marginal_effects_updated.png` | Predicted price penalty by rate gap and segment; 3.9x squeeze multiplier annotated |
| `fig12_hhi_price_correlation.png` | ZIP-level median HHI vs. median sale price; r = 0.805, R² = 0.648 (N = 80 ZIP codes) |
| `fig_histogram_price.png` | Distribution of 198,407 sale prices on log scale; median $299K, entry-tier = 70% of transactions |

### Tables

| File | Description |
|------|-------------|
| `table1_descriptive.png` | Descriptive statistics by geography: DOM, sale-to-list, median price, mortgage rate, HHI, population |
| `table2_dom_models.png` | Regression models for median days on market; simple, controlled, interaction, and two-way FE specifications |
| `table3_price_models.png` | Rate lock-in effect on log sale price; rate gap x segment interactions on N = 198,407 transactions |
| `table4_did_models.png` | DiD estimates for price and volume; triple-interaction specifications with county and year fixed effects |
| `table5_hypothesis_test.png` | Welch two-sample t-test results: pre vs. post price means by segment and geography |
| `table6_correlation.png` | Pearson correlation matrix for key continuous variables (N = 198,407) |
| `table6b_standard_error.png` | Standard error of log sale price by price segment with 95% confidence intervals |
| `table_continuous_model.png` | Continuous quadratic model: log(sale_price) ~ rate_gap x (log_av + log_av²) |
| `table_rate_sensitivity.png` | Rate sensitivity summary: −1.8%/pp entry, −7.1%/pp mid-luxury, 3.9x squeeze multiplier |

### Interactive Maps

| File | Description |
|------|-------------|
| `heatmap_interactive.html` | Choropleth of median sale price by ZIP code (orange scale); hover for transaction count and mid-luxury share |
| `heatmap_hhi.html` | Choropleth of median household income by ZIP code (blue scale); hover for affordability ratio and mid-luxury share |
| `indy_squeeze_interactive.html` | Leaflet map of price-to-income stress ratio by ZIP code; stepped 4-color palette with threshold at 4.0x |

## Limitations

Days-on-market figures from Redfin are subject to delist-relist cycling and represent a lower bound on true time-to-sale. Marion County's near-absence from the mid-luxury segment reflects its income structure ($63,450 median HHI) rather than rate sensitivity, which makes the geography-as-treatment interpretation conservative. ACS income estimates are cross-sectional (2023) and applied uniformly across all study years. County-level geography proxies for buyer type rather than directly measuring it. Known omitted variable candidates include Hamilton County new construction activity driven by Eli Lilly and Amazon expansions, school district quality premiums in Carmel and Fishers, and suburban corridor corporate relocations.

## Reproducibility

All R scripts use `here::here()` for file paths. Python scripts use `pathlib.Path` anchored to the repository root. Set `CENSUS_API_KEY` and `FRED_API_KEY` in `.Renviron` before running `01_data_pipeline.R`. The `data_pipeline.py` script requires STATS Indiana SDF flat files (`SALEDISC20XX.txt` and `SALEPARCEL20XX.txt`) placed in the repository root; these files are not redistributed here.

## Data Sources

- STATS Indiana, Sales Disclosure Form deed records, 2021–2025
- Redfin, county market tracker public data
- U.S. Census Bureau, American Community Survey 2023 5-year estimates
- Federal Reserve Bank of St. Louis (FRED), MORTGAGE30US series
