#!/usr/bin/env Rscript

# Build harmonized 2015-2025 county-month panels for Indianapolis and MSP.

required_packages <- c("dplyr", "tidyr", "readr", "lubridate", "purrr",
                       "stringr", "fredr", "httr", "jsonlite", "here", "digest")
missing_packages <- required_packages[!vapply(required_packages, requireNamespace,
                                               logical(1), quietly = TRUE)]
if (length(missing_packages) > 0) {
  stop("Missing R packages: ", paste(missing_packages, collapse = ", "))
}

suppressPackageStartupMessages({
  library(dplyr)
  library(tidyr)
  library(readr)
  library(lubridate)
  library(purrr)
  library(stringr)
})

START_YEAR <- 2015L
END_YEAR <- 2025L
RATE_BASELINE <- 3.0
LTV_RATIO <- 0.80
TERM_MONTHS <- 360
TIER_SEED <- 42L
TIER_NSTART <- 50L
TIER_LABELS <- c("ENTRY", "MOVE_UP_MID_LUXURY", "HIGH_END")

research_dir <- here::here("data", "processed", "research")
external_dir <- file.path(research_dir, "external")
quality_dir <- here::here("outputs", "research", "quality")
dir.create(research_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(external_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(quality_dir, recursive = TRUE, showWarnings = FALSE)

transactions_path <- file.path(research_dir, "transactions.csv")
if (!file.exists(transactions_path)) {
  stop("Missing ", transactions_path,
       "; run scripts/research/01_prepare_transactions.py first")
}

counties <- tribble(
  ~county,      ~county_fips, ~metro, ~tier_type,          ~state_code,
  "Boone",      "18011",     "INDY", "SUBURBAN_COLLAR", "IN",
  "Hamilton",   "18057",     "INDY", "SUBURBAN_COLLAR", "IN",
  "Hendricks",  "18063",     "INDY", "SUBURBAN_COLLAR", "IN",
  "Johnson",    "18081",     "INDY", "SUBURBAN_COLLAR", "IN",
  "Marion",     "18097",     "INDY", "URBAN_CORE",      "IN",
  "Anoka",      "27003",     "MSP",  "SUBURBAN_COLLAR", "MN",
  "Carver",     "27019",     "MSP",  "SUBURBAN_COLLAR", "MN",
  "Dakota",     "27037",     "MSP",  "SUBURBAN_COLLAR", "MN",
  "Hennepin",   "27053",     "MSP",  "URBAN_CORE",      "MN",
  "Ramsey",     "27123",     "MSP",  "URBAN_CORE",      "MN",
  "Scott",      "27139",     "MSP",  "SUBURBAN_COLLAR", "MN",
  "Washington", "27163",     "MSP",  "SUBURBAN_COLLAR", "MN"
)

month_grid <- tibble(sale_month_date = seq.Date(as.Date("2015-01-01"),
                                                as.Date("2025-12-01"), by = "month")) %>%
  mutate(sale_month = format(sale_month_date, "%Y-%m"),
         sale_year = year(sale_month_date),
         regime = case_when(
           sale_year <= 2019 ~ "BASELINE",
           sale_year <= 2021 ~ "PANDEMIC_LOW_RATE",
           TRUE ~ "HIGH_RATE_LOCK_IN"
         ))

read_local_env_value <- function(names) {
  env_path <- here::here(".env")
  if (!file.exists(env_path)) return("")
  lines <- readLines(env_path, warn = FALSE)
  for (name in names) {
    matches <- grep(paste0("^\\s*", name, "\\s*="), lines, value = TRUE)
    if (length(matches) == 0L) next
    value <- trimws(sub("^[^=]*=", "", matches[[1]]))
    value <- sub("^['\"]", "", value)
    value <- sub("['\"]$", "", value)
    if (nzchar(value)) return(value)
  }
  ""
}

complete_fred_months <- function(result) {
  result <- result %>% arrange(sale_month)
  prior_imputed <- if ("cpi_imputed" %in% names(result)) {
    replace_na(as.logical(result$cpi_imputed), FALSE)
  } else {
    rep(FALSE, nrow(result))
  }
  missing_cpi <- is.na(result$cpi)
  if (any(missing_cpi)) {
    observed <- which(!missing_cpi)
    result$cpi <- approx(
      x = observed, y = result$cpi[observed], xout = seq_len(nrow(result)),
      rule = 1
    )$y
  }
  result$cpi_imputed <- prior_imputed | missing_cpi
  result
}

read_or_fetch_fred <- function() {
  cache <- file.path(external_dir, "fred_monthly.csv")
  if (file.exists(cache)) {
    result <- complete_fred_months(read_csv(cache, show_col_types = FALSE))
    write_csv(result, cache)
    return(result)
  }
  key <- Sys.getenv("FRED_API_KEY")
  if (!nzchar(key)) stop("FRED_API_KEY is required when fred_monthly.csv is absent")
  fredr::fredr_set_key(key)
  rates <- fredr::fredr(series_id = "MORTGAGE30US",
                        observation_start = as.Date("2015-01-01"),
                        observation_end = as.Date("2025-12-31")) %>%
    transmute(sale_month = format(date, "%Y-%m"), mortgage_rate_pct = value) %>%
    group_by(sale_month) %>%
    summarise(mortgage_rate_pct = mean(mortgage_rate_pct, na.rm = TRUE), .groups = "drop")
  cpi <- fredr::fredr(series_id = "CPIAUCSL",
                      observation_start = as.Date("2015-01-01"),
                      observation_end = as.Date("2025-12-31")) %>%
    transmute(sale_month = format(date, "%Y-%m"), cpi = value) %>%
    group_by(sale_month) %>%
    summarise(cpi = mean(cpi, na.rm = TRUE), .groups = "drop")
  result <- complete_fred_months(full_join(rates, cpi, by = "sale_month"))
  write_csv(result, cache)
  result
}

fetch_acs_state <- function(estimate_year, state_fips) {
  variables <- paste(c("NAME", "B19013_001E", "B19013_001M", "B01003_001E",
                       "B01003_001M", "B11001_001E", "B11001_001M"), collapse = ",")
  query <- list(get = variables, `for` = "county:*", `in` = paste0("state:", state_fips))
  key <- Sys.getenv("CENSUS_API_KEY")
  if (!nzchar(key)) key <- Sys.getenv("CENSUS_APIKEY")
  if (!nzchar(trimws(key))) {
    key <- read_local_env_value(c("CENSUS_API_KEY", "CENSUS_APIKEY"))
  }
  key <- trimws(key)
  if (nzchar(key)) query$key <- key
  response <- httr::RETRY(
    "GET", paste0("https://api.census.gov/data/", estimate_year, "/acs/acs5"),
    query = query,
    httr::user_agent("indiana-housing-freeze/longitudinal-research"),
    httr::timeout(60), times = 4L, pause_base = 1, quiet = TRUE
  )
  httr::stop_for_status(response)
  response_text <- httr::content(response, as = "text", encoding = "UTF-8")
  if (!startsWith(trimws(response_text), "[")) {
    stop("Census API returned non-JSON content for ", estimate_year, " state ",
         state_fips, ": ", substr(gsub("[\r\n]+", " ", response_text), 1, 240))
  }
  rows <- jsonlite::fromJSON(response_text, simplifyVector = FALSE)
  headers <- unlist(rows[[1]])
  values <- do.call(rbind, lapply(rows[-1], unlist))
  result <- as_tibble(values, .name_repair = "minimal")
  names(result) <- headers
  result %>% transmute(
    county_fips = paste0(state, county),
    estimate_year = as.integer(estimate_year),
    acs_vintage = as.integer(estimate_year),
    income_carried_forward = FALSE,
    median_hhi = as.numeric(B19013_001E), median_hhi_moe = as.numeric(B19013_001M),
    population = as.numeric(B01003_001E), population_moe = as.numeric(B01003_001M),
    households = as.numeric(B11001_001E), households_moe = as.numeric(B11001_001M)
  )
}

read_or_fetch_acs <- function() {
  cache <- file.path(external_dir, "acs_county_year.csv")
  if (file.exists(cache)) return(read_csv(cache, col_types = cols(county_fips = col_character())))
  base <- map_dfr(START_YEAR:2024L, function(vintage) {
    bind_rows(fetch_acs_state(vintage, "18"), fetch_acs_state(vintage, "27"))
  }) %>% filter(county_fips %in% counties$county_fips)
  acs_2025 <- tryCatch(
    bind_rows(fetch_acs_state(2025L, "18"), fetch_acs_state(2025L, "27")) %>%
      filter(county_fips %in% counties$county_fips),
    error = function(error) NULL
  )
  if (is.null(acs_2025) || nrow(acs_2025) != nrow(counties)) {
    acs_2025 <- base %>% filter(estimate_year == 2024L) %>%
      mutate(estimate_year = 2025L, income_carried_forward = TRUE)
  }
  result <- bind_rows(base, acs_2025) %>% arrange(county_fips, estimate_year)
  write_csv(result, cache)
  result
}

read_or_fetch_redfin <- function() {
  cache <- file.path(external_dir, "redfin_county_month.csv")
  if (file.exists(cache)) return(read_csv(cache, col_types = cols(county_fips = col_character())))
  raw_cache <- file.path(external_dir, "county_market_tracker.tsv000.gz")
  if (!file.exists(raw_cache)) {
    url <- paste0("https://redfin-public-data.s3.us-west-2.amazonaws.com/",
                  "redfin_market_tracker/county_market_tracker.tsv000.gz")
    download.file(url, raw_cache, mode = "wb", quiet = FALSE)
  }
  raw <- read_tsv(raw_cache, na = c("", "NA", "--"), show_col_types = FALSE) %>%
    rename_with(tolower)
  expected_regions <- counties %>%
    transmute(region = paste0(county, " County, ", state_code), county_fips)
  result <- raw %>%
    mutate(period_begin = as.Date(period_begin),
           sale_month = format(period_begin, "%Y-%m")) %>%
    filter(region_type == "county", period_duration == 30,
           property_type == "Single Family Residential",
           state_code %in% c("IN", "MN"),
           year(period_begin) >= START_YEAR, year(period_begin) <= END_YEAR) %>%
    inner_join(expected_regions, by = "region") %>%
    transmute(county_fips, sale_month, median_sale_price_redfin = median_sale_price,
              median_dom, inventory, months_of_supply, avg_sale_to_list,
              price_drops, homes_sold, redfin_last_updated = last_updated)
  duplicates <- result %>% count(county_fips, sale_month) %>% filter(n != 1)
  if (nrow(duplicates) > 0) stop("Redfin county-month keys are not unique")
  write_csv(result, cache)
  result
}

validate_source_coverage <- function() {
  indiana_manifest <- here::here("outputs", "indiana", "quality", "sdf_ingestion_manifest.json")
  mn_coverage <- here::here("outputs", "mn", "quality", "ecrv_archive_coverage.csv")
  if (!file.exists(indiana_manifest) || !file.exists(mn_coverage)) {
    stop("State ingestion manifests/coverage are required before panel construction")
  }
  manifest <- jsonlite::read_json(indiana_manifest, simplifyVector = TRUE)
  in_years <- unique(as.integer(manifest$inputs$source_year))
  if (!all(START_YEAR:END_YEAR %in% in_years)) stop("Indiana source coverage is incomplete")
  mn <- read_csv(mn_coverage, show_col_types = FALSE) %>%
    mutate(extract_year = as.integer(extract_year)) %>%
    filter(extract_year >= START_YEAR, extract_year <= END_YEAR) %>%
    distinct(archive_name, extract_year) %>% count(extract_year, name = "archives")
  if (!all(START_YEAR:END_YEAR %in% mn$extract_year) || any(mn$archives < 52L)) {
    stop("Minnesota weekly archive coverage is incomplete for 2015-2025")
  }
  mn
}

mn_archive_counts <- validate_source_coverage()
fred <- read_or_fetch_fred() %>% arrange(sale_month) %>%
  mutate(rate_gap_pp = mortgage_rate_pct - RATE_BASELINE,
         rate_gap_lag3_pp = lag(rate_gap_pp, 3), rate_gap_lag6_pp = lag(rate_gap_pp, 6),
         cpi_annual = ave(cpi, substr(sale_month, 1, 4), FUN = mean))
acs <- read_or_fetch_acs()
redfin <- read_or_fetch_redfin()

if (anyDuplicated(fred$sale_month)) stop("FRED monthly keys are not unique")
if (anyDuplicated(acs[c("county_fips", "estimate_year")])) stop("ACS keys are not unique")
if (nrow(fred) != 132L || any(is.na(fred$mortgage_rate_pct)) || any(is.na(fred$cpi))) {
  stop("FRED rate/CPI coverage must contain all 132 study months")
}
fred %>% filter(cpi_imputed) %>%
  transmute(sale_month, field = "CPIAUCSL", method = "interior_linear_interpolation") %>%
  write_csv(file.path(quality_dir, "external_data_adjustments.csv"))
cpi_base <- fred %>% filter(str_starts(sale_month, "2025-")) %>%
  summarise(value = mean(cpi, na.rm = TRUE)) %>% pull(value)

transaction_columns <- c(
  "source_key", "source_schema", "sale_year", "sale_month", "county", "county_fips",
  "metro", "tier_type", "core_city_status", "gross_sale_price", "adjusted_price",
  "research_eligible",
  "eligible_strict_comparable", "single_family", "parse_recovered",
  "recent_reporting_period", "regime"
)
transactions <- read_csv(
  transactions_path,
  col_select = all_of(transaction_columns),
  col_types = cols(
    source_key = col_character(), county_fips = col_character(), sale_month = col_character(),
    core_city_status = col_character()
  )
) %>%
  mutate(sale_year = as.integer(sale_year), gross_sale_price = as.numeric(gross_sale_price),
         adjusted_price = as.numeric(adjusted_price), research_eligible = as.logical(research_eligible),
         eligible_strict_comparable = as.logical(eligible_strict_comparable),
         parse_recovered = as.logical(parse_recovered)) %>%
  left_join(fred, by = "sale_month") %>%
  left_join(acs, by = c("county_fips", "sale_year" = "estimate_year")) %>%
  mutate(real_sale_price = gross_sale_price * cpi_base / cpi,
         real_adjusted_price = adjusted_price * cpi_base / cpi,
         median_hhi_real = median_hhi * cpi_base / cpi_annual)

if (any(is.na(transactions$cpi))) stop("Transactions have unmatched CPI months")
if (any(is.na(transactions$median_hhi))) stop("Transactions have unmatched ACS county-years")

fit_tiers <- function(data, metro_name) {
  baseline <- data %>% filter(metro == metro_name, research_eligible,
                              sale_year >= 2015L, sale_year <= 2019L)
  if (nrow(baseline) < 1000L) stop("Insufficient baseline transactions for ", metro_name)
  set.seed(TIER_SEED)
  model <- kmeans(log(baseline$real_sale_price), centers = 3L, nstart = TIER_NSTART)
  centers_log <- sort(as.numeric(model$centers))
  boundaries <- exp((centers_log[-length(centers_log)] + centers_log[-1]) / 2)
  cohort_hash <- baseline %>% arrange(source_key) %>%
    transmute(value = paste(source_key, sprintf("%.10f", real_sale_price), sep = "|")) %>%
    pull(value) %>% paste(collapse = "\n") %>%
    digest::digest(algo = "sha256", serialize = FALSE)
  list(
    metadata = tibble(
      metro = metro_name, training_records = nrow(baseline), seed = TIER_SEED,
      nstart = TIER_NSTART, transformation = "log_2025_dollars",
      algorithm = model$algorithm, r_version = R.version.string,
      lower_center = exp(centers_log[1]), middle_center = exp(centers_log[2]),
      upper_center = exp(centers_log[3]), entry_boundary = boundaries[1],
      high_end_boundary = boundaries[2],
      training_cohort_sha256 = cohort_hash
    ),
    boundaries = boundaries,
    quantiles = quantile(baseline$real_sale_price, probs = c(1/3, 2/3), na.rm = TRUE)
  )
}

tier_models <- setNames(lapply(c("INDY", "MSP"), function(value) fit_tiers(transactions, value)),
                        c("INDY", "MSP"))
tier_metadata <- bind_rows(lapply(tier_models, `[[`, "metadata")) %>%
  mutate(cpi_base_2025 = cpi_base)
write_csv(tier_metadata, file.path(quality_dir, "price_tier_definitions.csv"))
jsonlite::write_json(tier_metadata, file.path(quality_dir, "price_tier_definitions.json"),
                     dataframe = "rows", pretty = TRUE, auto_unbox = TRUE, digits = 12)

assign_tier <- function(prices, boundaries) {
  cut(prices, breaks = c(-Inf, boundaries, Inf), labels = TIER_LABELS,
      ordered_result = TRUE, right = TRUE)
}
transactions <- transactions %>% group_by(metro) %>% group_modify(function(data, key) {
  model <- tier_models[[key$metro]]
  data$price_tier <- assign_tier(data$real_sale_price, model$boundaries)
  data$price_tier_quantile <- assign_tier(data$real_sale_price, model$quantiles)
  data
}) %>% ungroup()

write_csv(transactions, file.path(research_dir, "transactions_tiered.csv"))
saveRDS(transactions, file.path(research_dir, "transactions_tiered.rds"))

aggregate_tier_panel <- function(data, tier_column) {
  tier_symbol <- rlang::sym(tier_column)
  eligible <- data %>% filter(research_eligible, !is.na(!!tier_symbol)) %>%
    mutate(price_tier = as.character(!!tier_symbol))
  observed <- eligible %>% group_by(metro, tier_type, county, county_fips,
                                    sale_month, sale_year, regime, price_tier) %>%
    summarise(
      transactions = n(), median_gross_price = median(gross_sale_price),
      median_real_price = median(real_sale_price),
      p25_real_price = quantile(real_sale_price, 0.25),
      p75_real_price = quantile(real_sale_price, 0.75),
      median_adjusted_price = if (all(is.na(adjusted_price))) NA_real_
                              else median(adjusted_price, na.rm = TRUE),
      adjusted_price_coverage = mean(!is.na(adjusted_price)),
      recovered_share = mean(parse_recovered, na.rm = TRUE),
      recent_reporting_share = mean(recent_reporting_period, na.rm = TRUE),
      source_schema_count = n_distinct(source_schema),
      dominant_source_schema = names(sort(table(source_schema), decreasing = TRUE))[1],
      .groups = "drop"
    )
  grid <- crossing(counties %>% select(county, county_fips, metro, tier_type),
                   month_grid, price_tier = TIER_LABELS)
  grid %>% left_join(observed,
                     by = c("county", "county_fips", "metro", "tier_type", "sale_month",
                            "sale_year", "regime", "price_tier")) %>%
    mutate(transactions = replace_na(transactions, 0L), source_coverage_observed = TRUE) %>%
    left_join(fred, by = "sale_month") %>%
    left_join(acs, by = c("county_fips", "sale_year" = "estimate_year")) %>%
    mutate(
      median_hhi_real = median_hhi * cpi_base / cpi_annual,
      monthly_rate = mortgage_rate_pct / 1200,
      monthly_payment = if_else(
        !is.na(median_gross_price),
        median_gross_price * LTV_RATIO *
          (monthly_rate * (1 + monthly_rate)^TERM_MONTHS) /
          ((1 + monthly_rate)^TERM_MONTHS - 1), NA_real_
      ),
      payment_to_income = monthly_payment / (median_hhi / 12),
      price_to_income = median_gross_price / median_hhi,
      log_households = log(households)
    )
}

tier_panel <- aggregate_tier_panel(transactions, "price_tier")
quantile_panel <- aggregate_tier_panel(transactions, "price_tier_quantile")
if (nrow(tier_panel) != 12L * 132L * 3L) stop("Tier panel is not a complete 4,752-row grid")
if (any(!tier_panel$source_coverage_observed)) stop("Unobserved source periods cannot be zero-filled")

market_panel <- crossing(counties, month_grid) %>%
  left_join(redfin, by = c("county_fips", "sale_month")) %>%
  left_join(fred, by = "sale_month") %>%
  left_join(acs, by = c("county_fips", "sale_year" = "estimate_year")) %>%
  mutate(median_hhi_real = median_hhi * cpi_base / cpi_annual,
         listing_observed = !is.na(median_dom))

write_csv(tier_panel, file.path(research_dir, "county_month_tier.csv"))
saveRDS(tier_panel, file.path(research_dir, "county_month_tier.rds"))
write_csv(quantile_panel, file.path(research_dir, "county_month_tier_quantile.csv"))
saveRDS(quantile_panel, file.path(research_dir, "county_month_tier_quantile.rds"))
write_csv(market_panel, file.path(research_dir, "county_month_market.csv"))
saveRDS(market_panel, file.path(research_dir, "county_month_market.rds"))

balance <- tier_panel %>% group_by(metro, county, county_fips) %>%
  summarise(rows = n(), months = n_distinct(sale_month),
            zero_transaction_cells = sum(transactions == 0),
            missing_income_cells = sum(is.na(median_hhi)),
            missing_rate_cells = sum(is.na(mortgage_rate_pct)), .groups = "drop")
joins <- tibble(
  check = c("tier_panel_income", "tier_panel_rate", "market_panel_redfin"),
  missing_rows = c(sum(is.na(tier_panel$median_hhi)), sum(is.na(tier_panel$mortgage_rate_pct)),
                   sum(!market_panel$listing_observed)),
  total_rows = c(nrow(tier_panel), nrow(tier_panel), nrow(market_panel))
)
unmatched <- bind_rows(
  tier_panel %>% filter(is.na(median_hhi)) %>%
    transmute(source = "ACS", county, county_fips, sale_month),
  tier_panel %>% filter(is.na(mortgage_rate_pct)) %>%
    transmute(source = "FRED", county, county_fips, sale_month),
  market_panel %>% filter(!listing_observed) %>%
    transmute(source = "REDFIN", county, county_fips, sale_month)
) %>% distinct() %>% arrange(source, county_fips, sale_month)
write_csv(balance, file.path(quality_dir, "panel_balance.csv"))
write_csv(joins, file.path(quality_dir, "join_diagnostics.csv"))
write_csv(unmatched, file.path(quality_dir, "unmatched_county_months.csv"))
write_csv(mn_archive_counts, file.path(quality_dir, "mn_archive_counts.csv"))

cat("Built longitudinal research panels:\n")
cat("  tier panel:", nrow(tier_panel), "rows\n")
cat("  market panel:", nrow(market_panel), "rows\n")
cat("  eligible transactions:", sum(transactions$research_eligible), "\n")
