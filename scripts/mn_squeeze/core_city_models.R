# ══════════════════════════════════════════════════════════════════════════════
# Core-city comparison: the published headline transaction models on
# alternative core/suburb geographies
#
# Marion County is consolidated with the city of Indianapolis; Hennepin and
# Ramsey each combine a core city with affluent suburbs. This script re-runs
# the three headline models from 03_regression_hypothesis_tests.R
# (m_price_interact, m_did_price_triple, m_did_volume_triple) with the same
# specifications on:
#   indiana                     Marion vs. four suburban counties (validation:
#                               must equal the 03 script's Indiana results)
#   minnesota_counties          Hennepin and Ramsey vs. five suburban counties
#   stpaul_vs_collar            St. Paul vs. five suburban counties
#   core_cities_vs_collar       Minneapolis and St. Paul vs. five counties
#   core_cities_vs_all_suburbs  both cities vs. counties and county balances
#
# Inputs:  sdf and controls files written by 00_data_pipeline.py,
#          00_mn_data_pipeline.py, and 01_data_pipeline.R (both studies).
# Output:  outputs/mn/squeeze/core_city_comparison.csv
# Run from the project root after the Indiana and Minnesota 01 panels exist.
# ══════════════════════════════════════════════════════════════════════════════

suppressPackageStartupMessages({
  library(tidyverse); library(lmtest); library(sandwich); library(here)
})

luxury_CAP <- 15e6   # $15M — removes data entry errors from luxury tier
MIN_PRICE  <- 50000  # $50K — removes implausible deed transfers
LTV_RATIO  <- 0.80   # 80% LTV assumption for affordability calculation

# Two-sided normal p-value for the sum of selected coefficients.
# Inputs:  a fitted model, the coefficient names to add, and a covariance
#          matrix for the model's coefficients (for example HC1 or clustered).
# Output:  the p-value of the test that the coefficient sum equals zero.
combination_p <- function(model, terms, vc) {
  b <- coef(model)
  stopifnot(all(terms %in% names(b)))
  w <- setNames(as.numeric(names(b) %in% terms), names(b))
  se <- sqrt(drop(t(w) %*% vc[names(b), names(b)] %*% w))
  2 * pnorm(-abs(sum(w * b) / se))
}

# Fit the three headline models for one geography and summarize them.
# Inputs:  sdf_raw (transactions with county, sale_date, sale_price,
#          price_segment), county_controls (county, geography, median_hhi,
#          population), rate_lookup (year, month, mortgage_rate, rate_gap,
#          post), and a label.
# Output:  one-row tibble of slopes with HC1 and sale-month-clustered p-values,
#          the squeeze multiplier, and the triple interaction estimates with
#          HC1 p-values, as reported by 03.
headline_models <- function(sdf_raw, county_controls, rate_lookup, label) {
  sdf_raw <- sdf_raw %>%
    filter(!(price_segment == "luxury" & sale_price > luxury_CAP))

  # Transaction-level dataset built exactly as in 03; inner_join drops areas
  # outside the geography (for example, Minneapolis when St. Paul is the core).
  sdf <- sdf_raw %>%
    mutate(sale_date = as.Date(sale_date), year = year(sale_date), month = month(sale_date),
           price_segment = factor(price_segment, levels = c("entry", "move_up", "luxury"))) %>%
    inner_join(county_controls, by = "county") %>%
    left_join(rate_lookup, by = c("year", "month")) %>%
    mutate(
      treated = if_else(geography == "suburb", 1L, 0L),
      did     = treated * post,
      monthly_payment = (sale_price * LTV_RATIO *
                           (mortgage_rate / 1200 * (1 + mortgage_rate / 1200)^360) /
                           ((1 + mortgage_rate / 1200)^360 - 1)),
      affordability_ratio = monthly_payment / (median_hhi / 12),
      log_sale_price = log(sale_price),
      county = factor(county), year = factor(year),
      price_segment = relevel(price_segment, ref = "entry"),
      geography = relevel(factor(geography), ref = "metro"),
      sale_month = paste(year, month, sep = "-")   # cluster id for slope tests
    ) %>%
    filter(!is.na(rate_gap), !is.na(sale_price), sale_price > MIN_PRICE)

  # Core squeeze test — rate_gap × price_segment interaction (03 specification)
  m_price_interact <- lm(log_sale_price ~ rate_gap * price_segment + geography +
                           median_hhi + affordability_ratio, data = sdf)
  # Headline DiD — triple interaction with county and year fixed effects
  m_did_price_triple <- lm(log_sale_price ~ treated * post * price_segment +
                             median_hhi + affordability_ratio +
                             factor(county) + factor(year), data = sdf)
  # Volume DiD — monthly transaction counts by area and segment
  sdf_counts <- sdf_raw %>%
    mutate(year = year(as.Date(sale_date)), month = month(as.Date(sale_date))) %>%
    count(county, year, month, price_segment, name = "transactions") %>%
    inner_join(county_controls, by = "county") %>%
    left_join(rate_lookup, by = c("year", "month")) %>%
    mutate(treated = if_else(geography == "suburb", 1L, 0L), did = treated * post,
           price_segment = relevel(factor(price_segment,
                                          levels = c("entry", "move_up", "luxury")),
                                   ref = "entry"),
           county = factor(county), year = factor(year)) %>%
    filter(!is.na(rate_gap))
  m_did_volume_triple <- lm(transactions ~ treated * post * price_segment +
                              median_hhi + population + factor(county) + factor(year),
                            data = sdf_counts)

  b <- coef(m_price_interact)
  slope_entry  <- round((exp(b["rate_gap"]) - 1) * 100, 1)
  slope_midlux <- round((exp(b["rate_gap"] + b["rate_gap:price_segmentmove_up"]) - 1) * 100, 1)
  # Slope tests: the move-up slope is the sum rate_gap + rate_gap:move_up, so it
  # is tested as a linear combination. HC1 matches the published inference;
  # clustering by sale month allows for errors shared by sales in the same month.
  vc_hc1 <- vcovHC(m_price_interact, type = "HC1")
  vc_month <- vcovCL(m_price_interact, cluster = ~ sale_month, type = "HC1")
  slope_p <- function(terms, vc) signif(combination_p(m_price_interact, terms, vc), 2)
  entry_terms  <- "rate_gap"
  move_terms   <- c("rate_gap", "rate_gap:price_segmentmove_up")
  diff_terms   <- "rate_gap:price_segmentmove_up"
  tp <- coeftest(m_did_price_triple, vcov = vcovHC(m_did_price_triple, type = "HC1"))
  tv <- coeftest(m_did_volume_triple, vcov = vcovHC(m_did_volume_triple, type = "HC1"))
  k <- "treated:post:price_segmentmove_up"
  tibble(
    geography = label, sales = nrow(sdf),
    core_sales = sum(sdf$geography == "metro"), suburb_sales = sum(sdf$geography == "suburb"),
    core_areas = paste(sort(unique(as.character(sdf$county[sdf$geography == "metro"]))),
                       collapse = "; "),
    entry_pct_per_pp = slope_entry, move_up_pct_per_pp = slope_midlux,
    squeeze_multiplier = round(slope_midlux / slope_entry, 1),
    entry_slope_p = slope_p(entry_terms, vc_hc1),
    move_up_slope_p = slope_p(move_terms, vc_hc1),
    move_up_minus_entry_p = slope_p(diff_terms, vc_hc1),
    entry_slope_p_month_cluster = slope_p(entry_terms, vc_month),
    move_up_slope_p_month_cluster = slope_p(move_terms, vc_month),
    move_up_minus_entry_p_month_cluster = slope_p(diff_terms, vc_month),
    sale_months = n_distinct(sdf$sale_month),
    post_move_up_pct = round((exp(tp["post:price_segmentmove_up", 1]) - 1) * 100, 1),
    suburb_post_move_up_pct = round((exp(tp[k, 1]) - 1) * 100, 1),
    suburb_post_move_up_p = signif(tp[k, 4], 2),
    move_up_volume_per_month = round(tv[k, 1], 0),
    move_up_volume_p = signif(tv[k, 4], 2)
  )
}

# Rate lookup and county controls from a study's 01 panel.
panel_inputs <- function(panel_rds) {
  panel <- readRDS(here::here(panel_rds))
  list(
    controls = panel %>%
      distinct(county = as.character(county), geography = as.character(geography),
               median_hhi, population),
    rates = panel %>%
      distinct(year, month, mortgage_rate, rate_gap, post) %>%
      mutate(year = as.integer(as.character(year)))
  )
}

indiana   <- panel_inputs("data/processed/panel_data.rds")
minnesota <- panel_inputs("data/processed/mn/panel_data_mn.rds")
read_sdf  <- function(path) read_csv(here::here(path), show_col_types = FALSE)
mn_cities <- read_sdf("data/processed/mn/sdf_minnesota_core_cities_nominal.csv")

results <- bind_rows(
  headline_models(read_sdf("data/processed/sdf_indiana.csv"),
                  indiana$controls, indiana$rates, "indiana"),
  headline_models(read_sdf("data/processed/mn/sdf_minnesota_nominal.csv"),
                  minnesota$controls, minnesota$rates, "minnesota_counties"),
  map_dfr(c("stpaul_vs_collar", "core_cities_vs_collar", "core_cities_vs_all_suburbs"),
          function(name) {
            controls <- read_csv(here::here(paste0("data/processed/mn/core_city_controls_",
                                                   name, ".csv")),
                                 show_col_types = FALSE)
            headline_models(mn_cities, controls, minnesota$rates, name)
          })
)

out_dir <- here::here("outputs/mn/squeeze")
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
write_csv(results, file.path(out_dir, "core_city_comparison.csv"))
print(as.data.frame(results))
cat("Saved outputs/mn/squeeze/core_city_comparison.csv\n")
