# Indiana Move-Up Housing Market Squeeze

Quantitative research examining how mortgage rate lock-in has disproportionately suppressed the move-up residential market ($363K–$1.05M) across the Indianapolis metropolitan area, 2021–2025. The analysis combines Difference-in-Differences (DiD) models, individual deed records, and a county-month panel to distinguish two mechanisms driving the same affordability outcome: rate payment shock in suburban markets and structural income constraint in Marion County.

## Research Question

Does mortgage rate lock-in disproportionately suppress move-up transaction volumes and prices in Indianapolis suburbs relative to Marion County, controlling for income levels and pre-existing price trends?

## Key Findings

Move-up properties are 5.6 times more sensitive to the rate lock-in gap than entry-tier homes (−5.0%/pp vs. −0.9%/pp, derived from the price interaction model, N = 201,754). The multiplier is best read as move-up prices falling while entry prices barely moved: the move-up slope and the move-up minus entry gap are significant under HC1 errors and under errors clustered by sale month (p < 0.001), but the entry slope is not significant once errors are clustered by sale month (p = 0.097), so the ratio itself is imprecise. At the current 3.2 percentage point gap above the 2021 baseline, move-up prices are estimated approximately 15.0% below their pre-shock trajectory. The DiD triple interaction (Suburb × Post × Move-up) is statistically significant (p < 0.01), confirming that suburban move-up properties bear a disproportionate burden from the rate shock relative to the Marion County baseline. A Welch two-sample t-test shows entry-tier prices appreciated 8.2% post-shock while move-up appreciated only 2.6%, with both differences rejecting the null hypothesis (p < 2.2e-16). Marion County never produces meaningful move-up volume, not because of rate sensitivity, but because its median household income ($63,450) structurally precludes sustained demand in that price range. The two mechanisms converge on the same market freeze through different channels.

These figures count each sale once. An earlier version counted every row of the source disclosure files, where one sale filed on several forms appears more than once (269,992 rows for 201,754 sales, concentrated in the suburbs), and reported a 4.5× multiplier and a 16.2% suburban move-up offset. Counting each sale once strengthens both results: the offset is 17.2% and the suburban move-up volume decline is 340 sales per month (p < 0.001). See the [decision log](docs/decision_log.md).

## Data

**STATS Indiana Sales Disclosure Form (SDF) deed records** provide 201,754 arm's-length residential sales across five Indianapolis-area counties, 2021–2025. Filters applied: residential-only parcels (C10 flags), arm's-length qualification (B1_Valuable_Consider = Y; no sheriff, short, or quitclaim sales), sale price above $50K, and one row per `SDF_ID`.

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

Price tiers are derived from k-means clustering (k = 4) on raw nominal `sale_price` for 2021–2025 (with a pre-fit cap at $15M to suppress data-entry outliers), with the top two clusters collapsed because the ultra-luxury cluster is thin. Natural breakpoints fall at $363,424 and $1,047,851. The fitted breaks are written to `data/processed/price_segment_breaks_indiana.json` and also segment the Redfin county medians in the panel.

| Segment | Price range | N (2021–2025) |
|---------|-------------|---------------|
| Entry | Below $363K | 142,911 |
| Move-up | $363K to $1.05M | 55,745 |
| Luxury | Above $1.05M | 3,098 |

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

**`scripts/00_data_pipeline.py`** processes STATS Indiana SDF deed records for 2021–2025, keeps one row per `SDF_ID`, fits the k-means price segments, joins ZCTA-level HHI, and computes ZIP-level affordability ratios. Outputs: `data/processed/sdf_indiana.csv`, `data/processed/zip_median_prices.csv`, and `data/processed/price_segment_breaks_indiana.json`.

**`scripts/00_indiana_sdf_pipeline.py`** builds the audited Indiana transaction history from legacy annual pipe-delimited files (`2015.txt` through `2020.txt`) and modern `SALEDISC`/`SALEPARCEL` pairs. Format detection is header-based, so later modern years are discovered automatically. It writes `data/processed/indiana_sdf_history.csv` plus a county-year filter funnel, quality events, and a hashed input manifest under `outputs/indiana/quality/`. The longitudinal workflow consumes this history; the established 2021–2025 analysis does not.

**`scripts/squeeze_study.R`** holds the study settings for scripts 01–03. `SQUEEZE_STUDY=indiana` (the default) runs the published Indianapolis analysis; `SQUEEZE_STUDY=minnesota` runs the same method on the Twin Cities. Only geography, input files, and source labels differ.

**`scripts/01_data_pipeline.R`** builds the county-month panel used in all regression models. It joins Redfin listing data, Census county demographics, ZCTA HHI, and FRED mortgage rates. Computed variables include `rate_gap`, `affordability_ratio`, DiD indicators (`post`, `treated`, `did`), and per-capita transaction counts by segment. Outputs: `data/processed/panel_data.rds` and `data/processed/panel_data.csv`. Requires `CENSUS_API_KEY` and `FRED_API_KEY` in `.Renviron`.

**`scripts/02_eda_descriptive_stats.R`** produces Figures 1 through 10 and Table 1. It loads `panel_data.rds` and `sdf_indiana.csv` and generates descriptive statistics, time series plots, the parallel trends check, price index by segment, affordability ratios, and DOM distributions.

**`scripts/03_regression_hypothesis_tests.R`** estimates all regression models and generates Figures 11 through 13 and Tables 2 through 8. Models include DOM regressions on the 300-row county-month panel, price models on individual deed records, triple-interaction DiD specifications for price and volume, Welch two-sample t-tests, and the Pearson correlation matrix.

**`scripts/research/`** contains the independent longitudinal workflow. It harmonizes audited Indiana and Minnesota transactions for 2015–2025, fits fixed 2015–2019 price tiers separately by metro, builds county-month transaction and listing panels, estimates matching metro-specific models, and then tests cross-metro generalizability. Generated research data and results are namespaced separately from the established Indiana analysis.

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

Research governance for the longitudinal study is documented separately from
the established headline findings:

- [Analysis protocol](docs/analysis_protocol.md) freezes the prospective sample,
  estimands, tier construction, models, inference, and claim boundaries.
- [Journal-readiness roadmap](docs/journal_readiness_roadmap.md) defines the
  evidence gates that must pass before submission.
- [Claim ledger](docs/claim_ledger.md) traces public statements to current
  machine-readable artifacts and generating code.
- [Reproducibility guide](docs/reproducibility.md) defines the clean rebuild and
  release manifest.
- [Decision log](docs/decision_log.md) preserves substantive methodological
  choices and deviations from the frozen protocol.

Planned work in these documents is not evidence that a method has been
implemented or a result verified. `docs/methodology.md` describes implemented
methods; release-candidate artifacts and the verified claim ledger govern
reported numerical results.

All R scripts use `here::here()` for file paths. Python scripts use `pathlib.Path` anchored to the repository root. Set `CENSUS_API_KEY` and `FRED_API_KEY` in `.Renviron` before running `01_data_pipeline.R`. The `00_data_pipeline.py` script requires STATS Indiana SDF flat files (`SALEDISC20XX.txt` and `SALEPARCEL20XX.txt`) placed in `data/raw/in/`; these files are not redistributed here.

```bash
python scripts/00_data_pipeline.py
Rscript scripts/01_data_pipeline.R
Rscript scripts/02_eda_descriptive_stats.R
Rscript scripts/03_regression_hypothesis_tests.R
```

The audited history used by the longitudinal workflow is built separately:

```bash
python scripts/00_indiana_sdf_pipeline.py \
  --input-dir data/raw/in \
  --output data/processed/indiana_sdf_history.csv \
  --quality-dir outputs/indiana/quality

# Optional inclusive range or repeated individual years
python scripts/00_indiana_sdf_pipeline.py --year 2015:2020
```

The history retains records that fail research filters and exposes both
`eligible_current_study` and `eligible_strict_comparable` with machine-readable
exclusion reasons. Gross sale price remains the canonical price; cross-era
personal-property and seller-concession adjustments are intentionally deferred.

## Data Sources

- STATS Indiana, Sales Disclosure Form deed records, 2021–2025
- Redfin, county market tracker public data
- U.S. Census Bureau, American Community Survey 2023 5-year estimates
- Federal Reserve Bank of St. Louis (FRED), MORTGAGE30US series

## Minnesota eCRV extension

See [Minnesota ingestion architecture](docs/minnesota_ecrv_architecture.md) for the weekly ZIP findings, schema mapping, malformed-record policy, Twin Cities geography and price-sensitivity research plan. The ingestion pipeline reads XML directly from ZIPs, records processed archive hashes in a local SQLite database, and retains transaction versions and child rows. Full compatibility exports remain CSV; the longitudinal workflow materializes its seven-county, 2015–2025 research slice directly from SQLite as compressed Parquet. Raw archives and generated data remain excluded from Git.

```bash
# Incrementally process every ZIP under data/raw/mn/ecrv and export CSVs
python3 scripts/00_mn_ecrv_pipeline.py all

# Process selected years; reruns skip archives already committed
python3 scripts/00_mn_ecrv_pipeline.py ingest --year 2015 --year 2016
python3 scripts/00_mn_ecrv_pipeline.py export

# Build or reuse the filtered, snapshot-pinned Parquet research extract
python3 scripts/00_mn_ecrv_pipeline.py research-export \
  --start-year 2015 --end-year 2025

# Python 3.11+; audit one ZIP or recursively scan a folder
python3 scripts/audit_mn_ecrv.py /path/to/weekly-zips --output outputs/mn/quality/strict.json
# Explicit recovery for legacy files containing Windows-1252 bytes
python3 scripts/audit_mn_ecrv.py /path/to/weekly-zips --allow-cp1252 --output outputs/mn/quality/recovered.json
python3 -m unittest discover -s tests -v
```

## Longitudinal cross-metro analysis

The expanded study uses 2015–2019 as its baseline, 2020–2021 as the
pandemic/low-rate transition, and 2022–2025 as the high-rate lock-in period.
Gross sale price remains the canonical cross-state measure. Price-tier results
describe heterogeneity among completed transactions and are not demand
elasticities.

Run the audited state builds before the research workflow:

```bash
.venv/bin/python scripts/00_indiana_sdf_pipeline.py --input-dir data/raw/in
.venv/bin/python scripts/00_mn_ecrv_pipeline.py all

.venv/bin/python scripts/research/01_prepare_transactions.py \
  --start-year 2015 --end-year 2025
Rscript scripts/research/02_build_panels.R
Rscript scripts/research/03_estimate_models.R
```

The panel build is cache-first for FRED, ACS, and Redfin inputs. A FRED API key
is required when its cache is absent; the Census endpoint may also require a
key. The builder accepts `CENSUS_API_KEY` or `CENSUS_APIKEY` from the environment
or local ignored `.env`. The R
workflow requires `dplyr`, `tidyr`, `readr`, `lubridate`, `purrr`, `stringr`,
`fredr`, `httr`, `jsonlite`, `here`, `digest`, and `sandwich`.

Generated research data are written under `data/processed/research/`. Audit,
metro-specific, event-study, sensitivity, bootstrap, and pooled-comparison
tables are written under `outputs/research/`; both locations are reproducible
and ignored by Git. Set `WILD_BOOTSTRAP_REPS=99` for a model smoke test; the
release run defaults to 9,999 repetitions.

See [the longitudinal methodology](docs/longitudinal_research.md) for cohort,
panel, inference, and claim-boundary details.
