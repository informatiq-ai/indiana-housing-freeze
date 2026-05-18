# ══════════════════════════════════════════════════════════════════════════════
# Indiana Move-Up Housing Squeeze — Panel Data Construction
#
# Research Question: Does the mortgage rate lock-in effect disproportionately
# impact move-up ($380K–$1.05M) homes in Indianapolis suburbs vs Marion County?
#
# Two-mechanism hypothesis:
#   Suburbs:       Rate lock-in freezes move-up buyers (payment shock)
#   Marion County: Income constraint structurally thins the move-up buyer pool
#
# Data sources:
#   - Redfin county market tracker (DOM, sale-to-list, median price)
#   - STATS Indiana SDF deed records (transaction-level price band counts)
#   - FRED MORTGAGE30US (30-yr fixed mortgage rate)
#   - Census ACS 2023 5-year (median HHI, population — county and ZIP level)
#
# Output: panel_data.rds / panel_data.csv
#         zip_median_prices.csv (with ZCTA-level HHI)
#
# Unit of analysis: county × month cell
#   5 counties × 60 months = 300 rows
# ══════════════════════════════════════════════════════════════════════════════

# ── Package setup ─────────────────────────────────────────────────────────────
if (!require("pacman")) install.packages("pacman")
pacman::p_load(tidyverse, fredr, httr, jsonlite, here, scales)

# ── API keys (stored in .Renviron) ────────────────────────────────────────────
CENSUS_API_KEY <- Sys.getenv("CENSUS_API_KEY")
fredr_set_key(Sys.getenv("FRED_API_KEY"))

# ══════════════════════════════════════════════════════════════════════════════
# STEP 1: REDFIN COUNTY MARKET TRACKER
# Source: redfin-public-data.s3.us-west-2.amazonaws.com/redfin_market_tracker/
#         county_market_tracker.tsv000.gz
# Downloaded nationally, pre-filtered to 5 Indianapolis-area counties:
#   Marion (metro/control), Hamilton, Boone, Hendricks, Johnson (suburbs/treated)
# All 5 property types present — filter to Single Family Residential only
# Year range in file: 2012–2026 — filter to 2021–2025 (full rate cycle)
# ══════════════════════════════════════════════════════════════════════════════

target_counties <- c("Boone County, IN", "Hamilton County, IN",
                     "Hendricks County, IN", "Marion County, IN",
                     "Johnson County, IN")

redfin <- read_csv(here::here("data/processed/redfin_indiana.csv"), na = c("", "NA", "--")) %>%
  rename_with(~ str_to_lower(str_replace_all(., "[ /]", "_"))) %>%
  mutate(
    period_begin      = as.Date(period_begin),
    year              = year(period_begin),
    month             = month(period_begin),
    median_sale_price = as.numeric(str_remove_all(
      as.character(median_sale_price), "[$,]"))
  ) %>%
  filter(
    region        %in% target_counties,               # restrict to 5-county study area
    year          >= 2021, year <= 2025,               # rate cycle window
    property_type == "Single Family Residential",      # exclude condo/townhouse
    !is.na(median_sale_price),
    !is.na(median_dom),
    !is.na(avg_sale_to_list),
    !is.na(sold_above_list),
    !is.na(price_drops)
  )

cat("Redfin rows after filter:", nrow(redfin), "\n")
cat("Expected: ~300 (5 counties × 60 months)\n")
redfin %>% count(region, property_type) %>% print()

# ══════════════════════════════════════════════════════════════════════════════
# STEP 2: CENSUS ACS — COUNTY-LEVEL HHI AND POPULATION
# ACS 2023 5-year estimates — used as time-invariant controls
# FIPS: Indiana=18, Boone=011, Hamilton=057, Hendricks=063, Johnson=081, Marion=097
# Results cached to census_county_controls.csv to avoid repeated API calls
# ZCTA-level HHI is pulled separately in 00_data_pipeline.py (Step 3c).
# This step covers county-level controls only.
# ══════════════════════════════════════════════════════════════════════════════

if (file.exists(here::here("data/processed/census_county_controls.csv"))) {
  county_census <- read_csv(here::here("data/processed/census_county_controls.csv"),
                            show_col_types = FALSE)
  income_lookup <- county_census %>% select(county, median_hhi)
  pop_lookup    <- county_census %>% select(county, population)
  cat("Loaded county controls from cache\n")
  print(county_census)
  
} else {
  cat("Cache not found — pulling from Census API...\n")
  
  # Median household income: B19013_001E
  income_resp <- GET(paste0(
    "https://api.census.gov/data/2023/acs/acs5",
    "?get=NAME,B19013_001E",
    "&for=county:011,057,063,081,097",
    "&in=state:18",
    "&key=", CENSUS_API_KEY
  ))
  income_raw    <- fromJSON(content(income_resp, "text", encoding = "UTF-8"))
  income_lookup <- as_tibble(income_raw[-1, ], .name_repair = "minimal") %>%
    setNames(income_raw[1, ]) %>%
    transmute(
      county     = str_remove(NAME, " County, Indiana"),
      median_hhi = as.numeric(B19013_001E)
    )
  
  # Total population: B01003_001E
  pop_resp <- GET(paste0(
    "https://api.census.gov/data/2023/acs/acs5",
    "?get=NAME,B01003_001E",
    "&for=county:011,057,063,081,097",
    "&in=state:18",
    "&key=", CENSUS_API_KEY
  ))
  pop_raw    <- fromJSON(content(pop_resp, "text", encoding = "UTF-8"))
  pop_lookup <- as_tibble(pop_raw[-1, ], .name_repair = "minimal") %>%
    setNames(pop_raw[1, ]) %>%
    transmute(
      county     = str_remove(NAME, " County, Indiana"),
      population = as.numeric(B01003_001E)
    )
  
  county_census <- income_lookup %>%
    left_join(pop_lookup, by = "county")
  
  write_csv(county_census, here::here("data/processed/census_county_controls.csv"))
  cat("Saved census_county_controls.csv\n")
  print(county_census)
}

# ══════════════════════════════════════════════════════════════════════════════
# STEP 3: ZCTA HHI — UPSTREAM DEPENDENCY FROM 00_data_pipeline.py
# ZCTA-level median household income (B19013_001E) is pulled and cached by
# 00_data_pipeline.py (Step 3c) into data/processed/hhi_zcta.csv, then joined
# into data/processed/zip_median_prices.csv before this script runs.
# This script consumes the enriched zip_median_prices.csv directly below
# (Step 7) — no API call is required here. Documented as its own step so the
# pipeline dependency graph is explicit.
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
# STEP 4: FRED — 30-YEAR FIXED MORTGAGE RATE
# Series: MORTGAGE30US | monthly average
# rate_gap = mortgage_rate − 3.0 (2021 baseline ~3%)
# Interpretation: each 1pp above baseline = additional lock-in payment shock
# ══════════════════════════════════════════════════════════════════════════════

rates_raw <- fredr(
  series_id         = "MORTGAGE30US",
  observation_start = as.Date("2021-01-01"),
  observation_end   = as.Date("2025-12-31"),
  frequency         = "m"
) %>%
  transmute(
    year          = year(date),
    month         = month(date),
    mortgage_rate = value
  )

cat("Mortgage rates loaded:", nrow(rates_raw), "months\n")
cat("Rate range:", round(min(rates_raw$mortgage_rate), 2),
    "% –", round(max(rates_raw$mortgage_rate), 2), "%\n")

# ══════════════════════════════════════════════════════════════════════════════
# STEP 5: STATS INDIANA SDF — TRANSACTION COUNTS BY PRICE BAND
# Source: Indiana Dept of Local Government Finance / STATS Indiana
# Arm's-length residential sales only; excludes sheriff sales, quitclaims
# Price segments: entry <$380K, move_up $380K–$1.05M, luxury >$1.05M
# The $15M ceiling is enforced upstream in 00_data_pipeline.py before sdf_indiana.csv
# is written; the filter below is a defensive no-op kept as documentation that this
# step expects price-bounded input and would drop any contaminated rows if reintroduced.
# ══════════════════════════════════════════════════════════════════════════════

sdf_raw <- read_csv(here::here("data/processed/sdf_indiana.csv"), show_col_types = FALSE) %>%
  filter(!(price_segment == "luxury" & sale_price > 15000000))

sdf_counts <- sdf_raw %>%
  mutate(price_segment = factor(price_segment,
                                levels = c("entry", "move_up", "luxury"))) %>%
  group_by(county, year, month, price_segment) %>%
  summarise(
    transactions          = n(),
    median_sale_price_sdf = median(sale_price, na.rm = TRUE),
    .groups = "drop"
  ) %>%
  pivot_wider(
    names_from  = price_segment,
    values_from = c(transactions, median_sale_price_sdf),
    values_fill = 0
  ) %>%
  mutate(
    transactions_total = transactions_entry +
      transactions_move_up +
      transactions_luxury
  )

# ══════════════════════════════════════════════════════════════════════════════
# STEP 6: BUILD PANEL DATA — JOIN ALL SOURCES
# Unit of analysis: county × month (300 rows = 5 counties × 60 months)
# ══════════════════════════════════════════════════════════════════════════════

panel_data <- redfin %>%
  mutate(
    # Clean county name from Redfin region field
    county = str_remove(region, " County, IN"),
    
    # Price segment from Redfin county median using k-means confirmed breaks
    # Limitation: county median can shift between segments as prices appreciate
    # SDF transaction-level data resolves this in regression analysis
    price_segment = case_when(
      median_sale_price <  380000  ~ "entry",
      median_sale_price <= 1050000 ~ "move_up",
      TRUE                         ~ "luxury"
    ) %>% factor(levels = c("entry", "move_up", "luxury")),
    
    # Geography: Marion = metro core (control), suburbs = treated
    # Rationale: Marion buyers are necessity-driven; suburban buyers are
    # move-up buyers most exposed to rate lock-in payment shock
    geography = if_else(county == "Marion", "metro", "suburb") %>% factor()
  ) %>%
  left_join(rates_raw,     by = c("year", "month")) %>%
  left_join(income_lookup, by = "county") %>%
  left_join(pop_lookup,    by = "county") %>%
  left_join(sdf_counts,    by = c("county", "year", "month")) %>%
  mutate(
    # Core IV: rate lock-in gap (pp above 2021 baseline of ~3%)
    rate_gap = mortgage_rate - 3.0,
    
    # Affordability ratio: monthly payment as share of median monthly income
    # Captures income constraint mechanism in Marion County
    # Formula: 30-yr fixed amortization on 80% LTV
    monthly_payment = (median_sale_price * 0.80 *
                         (mortgage_rate / 1200 *
                            (1 + mortgage_rate / 1200)^360) /
                         ((1 + mortgage_rate / 1200)^360 - 1)),
    affordability_ratio = monthly_payment / (median_hhi / 12),
    afford_stressed     = if_else(affordability_ratio > 0.30, 1L, 0L),
    
    # DiD treatment indicators
    # post: rate gap >= 2pp = rate shock period (approximately mid-2022 onward)
    # treated: suburban counties (Hamilton, Boone, Hendricks, Johnson)
    post    = if_else(rate_gap >= 2.0, 1L, 0L),
    treated = if_else(geography == "suburb", 1L, 0L),
    did     = post * treated,
    
    # Panel identifiers
    time_id   = year * 100 + month,          # e.g. 202301
    county_id = as.integer(factor(county)),
    
    # Transaction volume per 1,000 residents — size-normalized market activity
    trans_per_capita = (transactions_total / population) * 1000
  )

# ZIP affordability uses the most recent available FRED rate in the dataset.
# Targets December 2025; falls back to the latest observed month if unavailable
# (e.g., data lag when pipeline is re-run mid-year).

dec_2025_row <- rates_raw %>% filter(year == 2025, month == 12)

if (nrow(dec_2025_row) == 1) {
  dec_2025_rate <- dec_2025_row$mortgage_rate / 100
} else {
  dec_2025_rate <- rates_raw %>%
    slice_max(order_by = year * 100 + month, n = 1) %>%
    pull(mortgage_rate) / 100
  cat("WARNING: Dec 2025 FRED rate not available — using most recent month.\n")
}

cat("\nZip affordability rate (FRED end-of-study):",
    scales::percent(dec_2025_rate, accuracy = 0.01), "\n")

# ── Load zip-level data for affordability enrichment ─────────────────────────
# hhi_zcta.csv was produced by 00_data_pipeline.py (Step 3c) and is already
# joined into zip_median_prices.csv, so zcta_hhi is available directly.
zip_data <- read_csv(here::here("data/processed/zip_median_prices.csv"),
                     show_col_types = FALSE) %>%
  filter(zip_code != 0) %>%
  mutate(zip_code = str_pad(as.character(zip_code), 5, pad = "0"))

cat("Zip codes for affordability enrichment:", n_distinct(zip_data$zip_code), "\n")

zip_data_enriched <- zip_data %>%
  mutate(
    monthly_payment  = (median_sale_price * 0.80 *
                          (dec_2025_rate / 12 *
                             (1 + dec_2025_rate / 12)^360) /
                          ((1 + dec_2025_rate / 12)^360 - 1)),
    afford_ratio_zip    = monthly_payment / (zcta_hhi / 12),
    afford_stressed_zip = if_else(afford_ratio_zip > 0.28, 1L, 0L)
  )

cat("\nAffordability stress by county:\n")
zip_data_enriched %>%
  group_by(county) %>%
  summarise(
    avg_hhi      = scales::dollar(mean(zcta_hhi,            na.rm = TRUE)),
    pct_stressed = scales::percent(mean(afford_stressed_zip, na.rm = TRUE),
                                   accuracy = 1),
    .groups = "drop"
  ) %>%
  print()

write_csv(zip_data_enriched, here::here("data/processed/zip_median_prices.csv"))
cat("Saved data/processed/zip_median_prices.csv\n")

# ══════════════════════════════════════════════════════════════════════════════
# STEP 7: SANITY CHECKS
# ══════════════════════════════════════════════════════════════════════════════

cat("\n── County demographics ──────────────────────────────────────────────────\n")
panel_data %>%
  distinct(county, geography, median_hhi, population) %>%
  filter(!is.na(median_hhi)) %>%
  mutate(
    hhi_fmt        = scales::dollar(median_hhi),
    pop_fmt        = formatC(population, format = "f", digits = 0, big.mark = ","),
    max_affordable = scales::dollar(median_hhi * 4)
  ) %>%
  arrange(desc(median_hhi)) %>%
  select(county, geography, hhi_fmt, pop_fmt, max_affordable) %>%
  print()

cat("\n── Rate gap distribution by era ─────────────────────────────────────────\n")
panel_data %>%
  mutate(era = case_when(
    year <= 2021             ~ "Baseline (2021)",
    year == 2022             ~ "Rate shock (2022)",
    year %in% c(2023, 2024) ~ "Elevated plateau (2023–24)",
    year == 2025             ~ "Persistent high (2025)"
  )) %>%
  group_by(era) %>%
  summarise(
    avg_rate_gap = mean(rate_gap,              na.rm = TRUE),
    avg_dom      = mean(median_dom,            na.rm = TRUE),
    avg_stl      = mean(avg_sale_to_list,   na.rm = TRUE),
    .groups = "drop"
  ) %>%
  print()

cat("\n── SDF transaction coverage by county ───────────────────────────────────\n")
panel_data %>%
  group_by(county) %>%
  summarise(
    rows             = n(),
    missing_sdf      = sum(is.na(transactions_total)),
    avg_entry_trans  = round(mean(transactions_entry,      na.rm = TRUE)),
    avg_moveup_trans = round(mean(transactions_move_up,    na.rm = TRUE)),
    avg_luxury_trans  = round(mean(transactions_luxury,      na.rm = TRUE)),
    trans_per_1k     = round(mean(trans_per_capita,        na.rm = TRUE), 2),
    .groups = "drop"
  ) %>%
  print()

cat("\n── DiD group sizes ──────────────────────────────────────────────────────\n")
panel_data %>%
  count(treated, post) %>%
  mutate(group = case_when(
    treated == 0 & post == 0 ~ "Marion pre-shock  (control, pre)",
    treated == 0 & post == 1 ~ "Marion post-shock (control, post)",
    treated == 1 & post == 0 ~ "Suburbs pre-shock  (treated, pre)",
    treated == 1 & post == 1 ~ "Suburbs post-shock (treated, post)"
  )) %>%
  select(group, n) %>%
  print()

cat("\n── Panel dimensions:", nrow(panel_data), "rows ×", ncol(panel_data), "cols ──\n")

# ══════════════════════════════════════════════════════════════════════════════
# STEP 8: SAVE
# ══════════════════════════════════════════════════════════════════════════════

saveRDS(panel_data, here::here("data/processed/panel_data.rds"))    # preserves factor levels and types
write_csv(panel_data, here::here("data/processed/panel_data.csv"))  # portable for inspection and sharing

cat("\nSaved: data/processed/panel_data.rds + data/processed/panel_data.csv\n")
cat("Downstream scripts: 02_eda_descriptive_stats.R,",
    "03_regression_hypothesis_tests.R\n")