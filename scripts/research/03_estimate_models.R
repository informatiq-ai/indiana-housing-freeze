#!/usr/bin/env Rscript

# Estimate parallel metro models and the pooled cross-metro generalizability test.

required_packages <- c("dplyr", "tidyr", "readr", "lubridate", "stringr",
                       "sandwich", "here")
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
  library(stringr)
})

research_dir <- here::here("data", "processed", "research")
output_root <- here::here("outputs", "research")
dir.create(output_root, recursive = TRUE, showWarnings = FALSE)

tier_path <- file.path(research_dir, "county_month_tier.rds")
quantile_path <- file.path(research_dir, "county_month_tier_quantile.rds")
market_path <- file.path(research_dir, "county_month_market.rds")
transaction_path <- file.path(research_dir, "transactions_tiered.rds")
required_inputs <- c(tier_path, quantile_path, market_path, transaction_path)
if (any(!file.exists(required_inputs))) {
  stop("Missing research panels; run scripts/research/02_build_panels.R first")
}

tier_panel <- readRDS(tier_path)
quantile_panel <- readRDS(quantile_path)
market_panel <- readRDS(market_path)
transactions <- readRDS(transaction_path)
bootstrap_reps <- as.integer(Sys.getenv("WILD_BOOTSTRAP_REPS", "9999"))
if (is.na(bootstrap_reps) || bootstrap_reps < 99L) bootstrap_reps <- 9999L

prepare_panel <- function(data) {
  if (!"price_to_income" %in% names(data)) data$price_to_income <- NA_real_
  if (!"payment_to_income" %in% names(data)) data$payment_to_income <- NA_real_
  data %>% mutate(
    price_tier = relevel(factor(as.character(price_tier), levels = c(
      "ENTRY", "MOVE_UP_MID_LUXURY", "HIGH_END"), ordered = FALSE), ref = "ENTRY"),
    tier_type = relevel(factor(tier_type,
                               levels = c("URBAN_CORE", "SUBURBAN_COLLAR")),
                        ref = "URBAN_CORE"),
    metro = relevel(factor(metro, levels = c("INDY", "MSP")), ref = "INDY"),
    sale_month_date = as.Date(paste0(sale_month, "-01")),
    calendar_quarter = paste0(year(sale_month_date), "Q", quarter(sale_month_date)),
    month_of_year = month(sale_month_date), calendar_year = year(sale_month_date),
    log_median_real_price = if_else(median_real_price > 0,
                                    log(median_real_price), NA_real_),
    log_price_to_income = if_else(price_to_income > 0,
                                  log(price_to_income), NA_real_),
    log_payment_to_income = if_else(payment_to_income > 0,
                                    log(payment_to_income), NA_real_),
    log_median_hhi_real = if_else(median_hhi_real > 0,
                                  log(median_hhi_real), NA_real_)
  )
}

tier_panel <- prepare_panel(tier_panel)
quantile_panel <- prepare_panel(quantile_panel)
market_panel <- market_panel %>% mutate(
  tier_type = relevel(factor(tier_type,
                             levels = c("URBAN_CORE", "SUBURBAN_COLLAR")),
                      ref = "URBAN_CORE"),
  log_median_hhi_real = if_else(median_hhi_real > 0, log(median_hhi_real), NA_real_)
)

cluster_vcov <- function(model, cluster) {
  sandwich::vcovCL(model, cluster = cluster, type = "HC1")
}

tidy_cluster <- function(model, cluster, metro_name, outcome, specification) {
  vcov_matrix <- cluster_vcov(model, cluster)
  estimates <- coef(model)
  kept <- names(estimates)[!is.na(estimates)]
  standard_errors <- sqrt(diag(vcov_matrix))[kept]
  is_log_scale <- outcome %in% c(
    "log_median_real_price", "log_price_to_income", "log_payment_to_income",
    "transactions"
  )
  tibble(
    metro = metro_name, outcome = outcome, specification = specification,
    term = kept, estimate = estimates[kept], std_error = standard_errors,
    statistic = estimate / std_error,
    p_value = 2 * pnorm(abs(statistic), lower.tail = FALSE),
    conf_low = estimate - qnorm(0.975) * std_error,
    conf_high = estimate + qnorm(0.975) * std_error,
    effect_percent = if (is_log_scale) 100 * (exp(estimate) - 1) else NA_real_,
    effect_percent_low = if (is_log_scale) {
      100 * (exp(conf_low) - 1)
    } else NA_real_,
    effect_percent_high = if (is_log_scale) {
      100 * (exp(conf_high) - 1)
    } else NA_real_,
    clusters = n_distinct(cluster), observations = nobs(model)
  )
}

target_term <- function(model, required_tokens, forbidden_tokens = character()) {
  candidates <- names(coef(model))[vapply(names(coef(model)), function(term) {
    all(vapply(required_tokens, grepl, logical(1), x = term, fixed = TRUE)) &&
      !any(vapply(forbidden_tokens, grepl, logical(1), x = term, fixed = TRUE))
  }, logical(1))]
  candidates <- candidates[!is.na(coef(model)[candidates])]
  if (length(candidates) != 1L) {
    stop("Expected one coefficient containing ", paste(required_tokens, collapse = " + "),
         "; found: ", paste(candidates, collapse = ", "))
  }
  candidates
}

wild_cluster_draws <- function(model, data, cluster_column, terms, reps, seed = 42L) {
  cluster <- as.character(data[[cluster_column]])
  if (length(cluster) != nobs(model)) {
    stop("Wild-bootstrap data do not match the estimation sample")
  }
  unique_clusters <- unique(cluster)
  webb_weights <- c(-sqrt(1.5), -1, -sqrt(0.5), sqrt(0.5), 1, sqrt(1.5))
  fitted_values <- fitted(model)
  residual_values <- residuals(model)
  design <- model.matrix(model)
  model_weights <- weights(model)
  if (is.null(model_weights)) model_weights <- rep(1, nrow(design))
  draws <- matrix(NA_real_, nrow = reps, ncol = length(terms),
                  dimnames = list(NULL, terms))
  set.seed(seed)
  for (index in seq_len(reps)) {
    cluster_weights <- sample(webb_weights, length(unique_clusters), replace = TRUE)
    names(cluster_weights) <- unique_clusters
    bootstrap_response <- fitted_values + residual_values * cluster_weights[cluster]
    coefficients <- lm.wfit(
      design, bootstrap_response, w = model_weights, singular.ok = TRUE
    )$coefficients
    names(coefficients) <- colnames(design)
    draws[index, ] <- coefficients[terms]
  }
  draws
}

summarize_wild_draws <- function(draws, observed, reps, term) {
  values <- draws[, term]
  values <- values[is.finite(values)]
  minimum_successful <- ceiling(0.80 * reps)
  if (length(values) < minimum_successful) {
    stop("Wild bootstrap produced ", length(values), " successful draws for ", term,
         "; required at least ", minimum_successful)
  }
  tibble(
    term = term, estimate = observed, bootstrap_reps_requested = reps,
    bootstrap_reps_successful = length(values),
    p_value = (1 + sum(abs(values - observed) >= abs(observed))) /
      (length(values) + 1),
    conf_low = unname(quantile(values, 0.025)),
    conf_high = unname(quantile(values, 0.975)),
    bootstrap_method = "Webb six-point wild cluster percentile sensitivity"
  )
}

wild_cluster_bootstrap <- function(model, data, cluster_column, term, reps, seed = 42L) {
  draws <- wild_cluster_draws(model, data, cluster_column, term, reps, seed)
  summarize_wild_draws(draws, unname(coef(model)[term]), reps, term)
}

wild_cluster_bootstrap_terms <- function(
    model, data, cluster_column, terms, reps, seed = 42L) {
  draws <- wild_cluster_draws(model, data, cluster_column, terms, reps, seed)
  bind_rows(lapply(terms, function(term) {
    summary <- summarize_wild_draws(
      draws, unname(coef(model)[term]), reps, term
    )
    standard_error <- sd(draws[, term], na.rm = TRUE)
    summary %>% transmute(
      term, estimate, std_error = standard_error,
      statistic = estimate / std_error, p_value, conf_low, conf_high,
      effect_percent = 100 * (exp(estimate) - 1),
      effect_percent_low = 100 * (exp(conf_low) - 1),
      effect_percent_high = 100 * (exp(conf_high) - 1)
    )
  }))
}

joint_wald <- function(model, cluster, terms) {
  terms <- intersect(terms, names(coef(model))[!is.na(coef(model))])
  if (length(terms) == 0L) {
    return(tibble(statistic = NA_real_, degrees_freedom = 0L, p_value = NA_real_))
  }
  beta <- coef(model)[terms]
  covariance <- cluster_vcov(model, cluster)[terms, terms, drop = FALSE]
  decomposition <- eigen((covariance + t(covariance)) / 2, symmetric = TRUE)
  tolerance <- max(dim(covariance)) * max(abs(decomposition$values)) * .Machine$double.eps
  retained <- decomposition$values > tolerance
  if (!any(retained)) {
    return(tibble(statistic = NA_real_, degrees_freedom = 0L, p_value = NA_real_))
  }
  inverse <- decomposition$vectors[, retained, drop = FALSE] %*%
    diag(1 / decomposition$values[retained], nrow = sum(retained)) %*%
    t(decomposition$vectors[, retained, drop = FALSE])
  statistic <- as.numeric(t(beta) %*% inverse %*% beta)
  rank <- sum(retained)
  tibble(statistic = statistic, degrees_freedom = rank,
         p_value = pchisq(statistic, df = rank, lower.tail = FALSE))
}

linear_combination <- function(model, covariance, terms, weights, label) {
  available <- names(coef(model))[!is.na(coef(model))]
  if (!all(terms %in% available)) {
    stop("Unavailable terms for linear combination ", label, ": ",
         paste(setdiff(terms, available), collapse = ", "))
  }
  estimate <- sum(coef(model)[terms] * weights)
  variance <- as.numeric(t(weights) %*% covariance[terms, terms, drop = FALSE] %*% weights)
  standard_error <- sqrt(variance)
  tibble(
    contrast = label, estimate = estimate, std_error = standard_error,
    conf_low = estimate - qnorm(0.975) * standard_error,
    conf_high = estimate + qnorm(0.975) * standard_error,
    effect_percent = 100 * (exp(estimate) - 1),
    effect_percent_low = 100 * (exp(conf_low) - 1),
    effect_percent_high = 100 * (exp(conf_high) - 1)
  )
}

ratio_from_model <- function(model) {
  coefficients <- coef(model)
  entry_term <- "rate_gap_pp"
  move_term <- target_term(
    model, c("rate_gap_pp", "price_tierMOVE_UP_MID_LUXURY"),
    "tier_typeSUBURBAN_COLLAR"
  )
  suburban_term <- target_term(
    model, c("rate_gap_pp", "tier_typeSUBURBAN_COLLAR"),
    c("price_tierMOVE_UP_MID_LUXURY", "price_tierHIGH_END")
  )
  triple <- target_term(model, c(
    "rate_gap_pp", "price_tierMOVE_UP_MID_LUXURY", "tier_typeSUBURBAN_COLLAR"
  ))
  entry_slope <- coefficients[[entry_term]] + coefficients[[suburban_term]]
  move_slope <- entry_slope + coefficients[[move_term]] + coefficients[[triple]]
  c(entry = entry_slope, move_up = move_slope,
    ratio = abs(move_slope) / abs(entry_slope))
}

bootstrap_slope_ratio <- function(data, reps, observed_ratio, seed = 42L) {
  cluster_strata <- data %>% distinct(county_fips, tier_type) %>%
    mutate(county_fips = as.character(county_fips))
  draws <- rep(NA_real_, reps)
  set.seed(seed)
  for (index in seq_len(reps)) {
    sampled <- bind_rows(lapply(split(cluster_strata, cluster_strata$tier_type),
                                function(stratum) {
      tibble(
        county_fips = sample(stratum$county_fips, nrow(stratum), replace = TRUE),
        draw = seq_len(nrow(stratum)), tier_type = as.character(stratum$tier_type[[1]])
      )
    }))
    pieces <- lapply(seq_len(nrow(sampled)), function(draw) {
      data %>% filter(county_fips == sampled$county_fips[[draw]]) %>%
        mutate(bootstrap_county = paste0(
          sampled$tier_type[[draw]], "_", sampled$county_fips[[draw]], "_",
          sampled$draw[[draw]]
        ))
    })
    bootstrap_data <- bind_rows(pieces)
    if (n_distinct(bootstrap_data$tier_type) < 2L) next
    bootstrap_model <- tryCatch(lm(
      log_median_real_price ~ rate_gap_pp * price_tier * tier_type +
        log_median_hhi_real + factor(bootstrap_county) + factor(calendar_year) +
        factor(month_of_year), data = bootstrap_data, weights = transactions
    ), error = function(error) NULL)
    if (!is.null(bootstrap_model)) {
      draws[[index]] <- tryCatch(
        unname(ratio_from_model(bootstrap_model)[["ratio"]]),
        error = function(error) NA_real_
      )
    }
  }
  draws <- draws[is.finite(draws)]
  minimum_successful <- ceiling(0.80 * reps)
  if (length(draws) < minimum_successful) {
    stop("Slope-ratio bootstrap produced ", length(draws),
         " successful draws; required at least ", minimum_successful)
  }
  benchmark <- 4.5
  tibble(
    bootstrap_reps_requested = reps, bootstrap_reps_successful = length(draws),
    ratio_conf_low = unname(quantile(draws, 0.025)),
    ratio_conf_high = unname(quantile(draws, 0.975)),
    benchmark_ratio = benchmark,
    p_value_vs_4_5 = (1 + sum(abs(draws - observed_ratio) >=
                                abs(observed_ratio - benchmark))) /
      (length(draws) + 1),
    bootstrap_method = "geography-stratified county pairs bootstrap"
  )
}

continuous_formula <- function(outcome = "log_median_real_price",
                               exposure = "rate_gap_pp") {
  as.formula(paste0(
    outcome, " ~ ", exposure,
    " * price_tier * tier_type + log_median_hhi_real + ",
    "factor(county_fips) + factor(sale_month)"
  ))
}

volume_formula <- function(exposure = "rate_gap_pp") {
  as.formula(paste0(
    "transactions ~ ", exposure,
    " * price_tier * tier_type + log_median_hhi_real + ",
    "factor(county_fips) + factor(sale_month) + offset(log_households)"
  ))
}

estimate_continuous <- function(data, outcome = "log_median_real_price",
                                exposure = "rate_gap_pp") {
  sample <- data %>% filter(transactions > 0, !is.na(.data[[outcome]]),
                            !is.na(.data[[exposure]]), !is.na(log_median_hhi_real))
  model <- lm(continuous_formula(outcome, exposure), data = sample,
              weights = transactions)
  list(model = model, data = sample)
}

estimate_price <- function(data, exposure = "rate_gap_pp") {
  estimate_continuous(data, "log_median_real_price", exposure)
}

estimate_volume <- function(data, exposure = "rate_gap_pp") {
  sample <- data %>% filter(!is.na(.data[[exposure]]), households > 0,
                            !is.na(log_median_hhi_real))
  model <- glm(volume_formula(exposure), data = sample, family = poisson(link = "log"))
  list(model = model, data = sample)
}

all_coefficients <- list()
wild_results <- list()
pretrend_results <- list()
event_study_results <- list()
saved_models <- list()

for (metro_name in c("INDY", "MSP")) {
  metro_dir <- file.path(output_root, tolower(metro_name))
  dir.create(metro_dir, recursive = TRUE, showWarnings = FALSE)
  metro_panel <- tier_panel %>% filter(metro == metro_name)
  price <- estimate_price(metro_panel)
  volume <- estimate_volume(metro_panel)
  triple_term <- target_term(price$model, c(
    "rate_gap_pp", "price_tierMOVE_UP_MID_LUXURY", "tier_typeSUBURBAN_COLLAR"
  ))
  all_coefficients[[length(all_coefficients) + 1L]] <- tidy_cluster(
    price$model, price$data$county_fips, metro_name, "log_median_real_price", "primary"
  )
  all_coefficients[[length(all_coefficients) + 1L]] <- tidy_cluster(
    volume$model, volume$data$county_fips, metro_name, "transactions", "primary_ppml"
  )
  wild_results[[length(wild_results) + 1L]] <- wild_cluster_bootstrap(
    price$model, price$data, "county_fips", triple_term, bootstrap_reps
  ) %>% mutate(metro = metro_name, outcome = "log_median_real_price")
  volume_wild_data <- metro_panel %>%
    mutate(log_transactions_plus_half = log(transactions + 0.5)) %>%
    filter(!is.na(rate_gap_pp), !is.na(log_median_hhi_real))
  volume_wild_model <- lm(
    continuous_formula("log_transactions_plus_half", "rate_gap_pp"),
    data = volume_wild_data
  )
  volume_wild_term <- target_term(volume_wild_model, c(
    "rate_gap_pp", "price_tierMOVE_UP_MID_LUXURY", "tier_typeSUBURBAN_COLLAR"
  ))
  wild_results[[length(wild_results) + 1L]] <- wild_cluster_bootstrap(
    volume_wild_model, volume_wild_data, "county_fips", volume_wild_term,
    bootstrap_reps
  ) %>% mutate(
    metro = metro_name,
    outcome = "transactions_auxiliary_log_count_plus_half"
  )
  saved_models[[paste0(metro_name, "_volume_wild_auxiliary")]] <- volume_wild_model

  for (ratio_outcome in c("log_price_to_income", "log_payment_to_income")) {
    ratio_model <- estimate_continuous(metro_panel, ratio_outcome)
    ratio_term <- target_term(ratio_model$model, c(
      "rate_gap_pp", "price_tierMOVE_UP_MID_LUXURY", "tier_typeSUBURBAN_COLLAR"
    ))
    all_coefficients[[length(all_coefficients) + 1L]] <- tidy_cluster(
      ratio_model$model, ratio_model$data$county_fips, metro_name,
      ratio_outcome, "primary"
    )
    wild_results[[length(wild_results) + 1L]] <- wild_cluster_bootstrap(
      ratio_model$model, ratio_model$data, "county_fips", ratio_term, bootstrap_reps
    ) %>% mutate(metro = metro_name, outcome = ratio_outcome)
    saved_models[[paste(metro_name, ratio_outcome, sep = "_")]] <- ratio_model$model
  }

  event_month <- metro_panel %>% filter(sale_year == 2022L, mortgage_rate_pct >= 5) %>%
    arrange(sale_month) %>% slice_head(n = 1) %>% pull(sale_month_date)
  event_quarter_index <- year(event_month) * 4L + quarter(event_month)
  event_data <- metro_panel %>% filter(transactions > 0, !is.na(log_median_real_price)) %>%
    mutate(event_quarter = year(sale_month_date) * 4L + quarter(sale_month_date) -
             event_quarter_index,
           event_quarter = pmax(-28L, pmin(15L, event_quarter)),
           event_quarter_factor = relevel(factor(event_quarter), ref = "-1"))
  event_model <- lm(
    log_median_real_price ~ event_quarter_factor * tier_type * price_tier +
      log_median_hhi_real + factor(county_fips) + factor(calendar_quarter),
    data = event_data, weights = transactions
  )
  event_coefficients <- tidy_cluster(
    event_model, event_data$county_fips, metro_name, "log_median_real_price", "event_study"
  )
  all_coefficients[[length(all_coefficients) + 1L]] <- event_coefficients
  event_interactions <- event_coefficients %>%
    filter(str_detect(term, "event_quarter_factor-?[0-9]+"),
           str_detect(term, "tier_typeSUBURBAN_COLLAR")) %>%
    mutate(event_quarter = as.integer(str_match(
      term, "event_quarter_factor(-?[0-9]+)"
    )[, 2]),
    comparison = case_when(
      str_detect(term, "price_tierMOVE_UP_MID_LUXURY") ~
        "MOVE_UP_MINUS_ENTRY_SUBURBAN_DIFFERENTIAL",
      str_detect(term, "price_tierHIGH_END") ~
        "HIGH_END_MINUS_ENTRY_SUBURBAN_DIFFERENTIAL",
      TRUE ~ "ENTRY_SUBURBAN_MINUS_CORE"
    ))
  event_bootstrap <- wild_cluster_bootstrap_terms(
    event_model, event_data, "county_fips", event_interactions$term,
    bootstrap_reps, seed = 420L + match(metro_name, c("INDY", "MSP"))
  )
  event_interactions <- event_interactions %>%
    select(-any_of(c(
      "estimate", "std_error", "statistic", "p_value", "conf_low", "conf_high",
      "effect_percent", "effect_percent_low", "effect_percent_high"
    ))) %>%
    left_join(event_bootstrap, by = "term") %>%
    mutate(inference_method = "Webb six-point wild cluster percentile")
  event_cells <- event_data %>% group_by(event_quarter, tier_type, price_tier) %>%
    summarise(transactions = sum(transactions), county_tier_month_cells = n(),
              .groups = "drop") %>%
    mutate(cell = paste(tier_type, price_tier, sep = "__")) %>%
    select(-tier_type, -price_tier) %>%
    pivot_wider(names_from = cell,
                values_from = c(transactions, county_tier_month_cells),
                values_fill = 0)
  event_study_results[[length(event_study_results) + 1L]] <- bind_rows(
    event_interactions,
    tidyr::crossing(
      metro = metro_name, outcome = "log_median_real_price",
      specification = "event_study", term = "reference_quarter",
      estimate = 0, std_error = NA_real_, statistic = NA_real_, p_value = NA_real_,
      conf_low = 0, conf_high = 0, effect_percent = 0,
      effect_percent_low = 0, effect_percent_high = 0,
      clusters = n_distinct(event_data$county_fips), observations = nrow(event_data),
      event_quarter = -1L,
      inference_method = "reference category",
      comparison = c(
        "ENTRY_SUBURBAN_MINUS_CORE",
        "MOVE_UP_MINUS_ENTRY_SUBURBAN_DIFFERENTIAL",
        "HIGH_END_MINUS_ENTRY_SUBURBAN_DIFFERENTIAL"
      )
    )
  ) %>% left_join(event_cells, by = "event_quarter") %>%
    mutate(event_month = format(event_month, "%Y-%m"))

  lead_table <- event_interactions %>% filter(
    event_quarter < -1L,
    comparison == "MOVE_UP_MINUS_ENTRY_SUBURBAN_DIFFERENTIAL"
  )
  lead_sets <- list(
    all_pre_shock = lead_table$term,
    baseline_2015_2019 = lead_table %>% filter(
      ((event_quarter_index + event_quarter - 1L) %/% 4L) <= 2019L
    ) %>% pull(term),
    transition_2020_2021 = lead_table %>% filter(
      ((event_quarter_index + event_quarter - 1L) %/% 4L) %in% 2020:2021
    ) %>% pull(term)
  )
  for (scope in names(lead_sets)) {
    terms <- lead_sets[[scope]]
    pretrend_results[[length(pretrend_results) + 1L]] <- joint_wald(
      event_model, event_data$county_fips, terms
    ) %>% mutate(metro = metro_name, scope = scope, reference_quarter = -1L,
                 event_month = format(event_month, "%Y-%m"),
                 leads_tested = length(terms))
  }

  metro_market <- market_panel %>% filter(metro == metro_name, listing_observed)
  for (outcome in c("median_dom", "inventory", "months_of_supply",
                    "avg_sale_to_list", "price_drops")) {
    market_sample <- metro_market %>% filter(
      !is.na(.data[[outcome]]), !is.na(rate_gap_pp), !is.na(log_median_hhi_real)
    )
    formula <- as.formula(paste0(
      outcome, " ~ rate_gap_pp * tier_type + log_median_hhi_real + ",
      "factor(county_fips) + factor(sale_month)"
    ))
    model <- lm(formula, data = market_sample)
    all_coefficients[[length(all_coefficients) + 1L]] <- tidy_cluster(
      model, market_sample$county_fips, metro_name, outcome, "listing_primary"
    )
    listing_term <- target_term(
      model, c("rate_gap_pp", "tier_typeSUBURBAN_COLLAR")
    )
    wild_results[[length(wild_results) + 1L]] <- wild_cluster_bootstrap(
      model, market_sample, "county_fips", listing_term, bootstrap_reps
    ) %>% mutate(metro = metro_name, outcome = outcome)
    saved_models[[paste(metro_name, outcome, sep = "_")]] <- model
  }
  saved_models[[paste0(metro_name, "_price")]] <- price$model
  saved_models[[paste0(metro_name, "_volume")]] <- volume$model
  saved_models[[paste0(metro_name, "_event")]] <- event_model
}

pooled_price <- estimate_price(tier_panel)
pooled_model <- lm(
  log_median_real_price ~ metro * rate_gap_pp * price_tier * tier_type +
    log_median_hhi_real + factor(county_fips) + factor(sale_month),
  data = pooled_price$data, weights = transactions
)
pooled_coefficients <- tidy_cluster(
  pooled_model, pooled_price$data$county_fips, "POOLED",
  "log_median_real_price", "pooled_generalizability"
)
four_way_term <- target_term(pooled_model, c(
  "metroMSP", "rate_gap_pp", "price_tierMOVE_UP_MID_LUXURY",
  "tier_typeSUBURBAN_COLLAR"
))
wild_results[[length(wild_results) + 1L]] <- wild_cluster_bootstrap(
  pooled_model, pooled_price$data, "county_fips", four_way_term, bootstrap_reps
) %>% mutate(metro = "POOLED", outcome = "log_median_real_price")
saved_models[["POOLED_price"]] <- pooled_model
pooled_triple_term <- target_term(
  pooled_model,
  c("rate_gap_pp", "price_tierMOVE_UP_MID_LUXURY", "tier_typeSUBURBAN_COLLAR"),
  "metroMSP"
)
pooled_covariance <- cluster_vcov(pooled_model, pooled_price$data$county_fips)
pooled_linear_combinations <- bind_rows(
  linear_combination(
    pooled_model, pooled_covariance, pooled_triple_term, 1,
    "INDY move-up suburban differential"
  ),
  linear_combination(
    pooled_model, pooled_covariance, c(pooled_triple_term, four_way_term), c(1, 1),
    "MSP move-up suburban differential"
  ),
  linear_combination(
    pooled_model, pooled_covariance, four_way_term, 1,
    "MSP minus INDY four-way difference"
  )
)

ratio_models <- list()
ratio_results <- list()
for (metro_name in c("INDY", "MSP")) {
  data <- tier_panel %>% filter(metro == metro_name, transactions > 0,
                                !is.na(log_median_real_price))
  model <- lm(
    log_median_real_price ~ rate_gap_pp * price_tier * tier_type +
      log_median_hhi_real + factor(county_fips) + factor(calendar_year) +
      factor(month_of_year), data = data, weights = transactions
  )
  ratio_values <- ratio_from_model(model)
  ratio_uncertainty <- bootstrap_slope_ratio(
    data, bootstrap_reps, ratio_values[["ratio"]]
  )
  ratio_results[[length(ratio_results) + 1L]] <- tibble(
    metro = metro_name, entry_suburban_log_slope = ratio_values[["entry"]],
    move_up_suburban_log_slope = ratio_values[["move_up"]],
    move_up_to_entry_absolute_ratio = ratio_values[["ratio"]],
    specification = "associational_year_and_season_FE_no_month_FE"
  ) %>% bind_cols(ratio_uncertainty)
  ratio_models[[metro_name]] <- model
}

build_transaction_panel <- function(data, eligibility, price_column = "real_sale_price",
                                    lower = 50000, upper = 15000000,
                                    bound_column = "gross_sale_price") {
  filtered <- data %>% filter({{ eligibility }}, .data[[bound_column]] > lower,
                              .data[[bound_column]] <= upper, !is.na(price_tier)) %>%
    mutate(model_price = .data[[price_column]]) %>%
    group_by(metro, tier_type, county, county_fips, sale_month, sale_year,
             regime, price_tier) %>%
    summarise(transactions = n(), median_real_price = median(model_price),
              mortgage_rate_pct = first(mortgage_rate_pct),
              rate_gap_pp = first(rate_gap_pp), rate_gap_lag3_pp = first(rate_gap_lag3_pp),
              rate_gap_lag6_pp = first(rate_gap_lag6_pp), median_hhi_real = first(median_hhi_real),
              median_hhi = first(median_hhi), households = first(households),
              income_carried_forward = first(income_carried_forward),
              dominant_source_schema = names(sort(table(source_schema), decreasing = TRUE))[1],
              .groups = "drop") %>%
    mutate(log_households = log(households))
  prepare_panel(filtered)
}

sensitivity_specs <- list(
  list(name = "quantile_tiers", panel = quantile_panel, exposure = "rate_gap_pp"),
  list(name = "lag_3_months", panel = tier_panel, exposure = "rate_gap_lag3_pp"),
  list(name = "lag_6_months", panel = tier_panel, exposure = "rate_gap_lag6_pp"),
  list(name = "exclude_transition", panel = tier_panel %>%
         filter(regime != "PANDEMIC_LOW_RATE"), exposure = "rate_gap_pp"),
  list(name = "exclude_carried_income", panel = tier_panel %>%
         filter(!income_carried_forward), exposure = "rate_gap_pp"),
  list(name = "strict_cohort", panel = build_transaction_panel(
    transactions, eligible_strict_comparable & single_family), exposure = "rate_gap_pp"),
  list(name = "exclude_recovered", panel = build_transaction_panel(
    transactions, research_eligible & !parse_recovered), exposure = "rate_gap_pp"),
  list(name = "exclude_recent_reporting_period", panel = build_transaction_panel(
    transactions, research_eligible & !coalesce(recent_reporting_period, FALSE)),
    exposure = "rate_gap_pp"),
  list(name = "alternative_price_bounds", panel = build_transaction_panel(
    transactions, research_eligible, lower = 75000, upper = 10000000), exposure = "rate_gap_pp")
)

if (sum(!is.na(transactions$real_adjusted_price) & transactions$metro == "MSP") > 0) {
  sensitivity_specs[[length(sensitivity_specs) + 1L]] <- list(
    name = "msp_adjusted_price", panel = build_transaction_panel(
      transactions %>% filter(metro == "MSP"),
      research_eligible & !is.na(real_adjusted_price), "real_adjusted_price"
    ), exposure = "rate_gap_pp"
  )
}

sensitivity_results <- list()
sensitivity_availability <- list()
for (spec in sensitivity_specs) {
  for (metro_name in intersect(c("INDY", "MSP"), unique(as.character(spec$panel$metro)))) {
    data <- spec$panel %>% filter(metro == metro_name)
    estimated <- tryCatch(estimate_price(data, spec$exposure), error = function(error) NULL)
    if (is.null(estimated)) next
    term <- tryCatch(target_term(estimated$model, c(
      spec$exposure, "price_tierMOVE_UP_MID_LUXURY", "tier_typeSUBURBAN_COLLAR"
    )), error = function(error) NA_character_)
    if (is.na(term)) next
    table <- tidy_cluster(estimated$model, estimated$data$county_fips, metro_name,
                          "log_median_real_price", spec$name)
    sensitivity_results[[length(sensitivity_results) + 1L]] <- table %>% filter(term == !!term)
  }
}

for (metro_name in c("INDY", "MSP")) {
  schema_data <- tier_panel %>% filter(metro == metro_name, transactions > 0,
                                       !is.na(dominant_source_schema))
  schema_model <- lm(
    log_median_real_price ~ rate_gap_pp * price_tier * tier_type +
      factor(dominant_source_schema) * price_tier * tier_type +
      log_median_hhi_real + factor(county_fips) + factor(sale_month),
    data = schema_data, weights = transactions
  )
  schema_term <- target_term(schema_model, c(
    "rate_gap_pp", "price_tierMOVE_UP_MID_LUXURY", "tier_typeSUBURBAN_COLLAR"
  ))
  sensitivity_results[[length(sensitivity_results) + 1L]] <- tidy_cluster(
    schema_model, schema_data$county_fips, metro_name,
    "log_median_real_price",
    if_else(metro_name == "INDY", "schema_era_and_pre_post_2021",
            "schema_era_controls")
  ) %>% filter(.data$term == schema_term)
  saved_models[[paste0(metro_name, "_schema_sensitivity")]] <- schema_model
}

for (county_name in unique(as.character(tier_panel$county))) {
  metro_name <- unique(as.character(tier_panel$metro[tier_panel$county == county_name]))
  data <- tier_panel %>% filter(metro == metro_name, county != county_name)
  if (n_distinct(data$tier_type) < 2L) {
    sensitivity_availability[[length(sensitivity_availability) + 1L]] <- tibble(
      specification = paste0("leave_out_", tolower(county_name)), metro = metro_name,
      available = FALSE,
      reason = "Removing the only urban-core county eliminates the geography contrast"
    )
    next
  }
  estimated <- estimate_price(data)
  term <- target_term(estimated$model, c(
    "rate_gap_pp", "price_tierMOVE_UP_MID_LUXURY", "tier_typeSUBURBAN_COLLAR"
  ))
  sensitivity_results[[length(sensitivity_results) + 1L]] <- tidy_cluster(
    estimated$model, estimated$data$county_fips, metro_name,
    "log_median_real_price", paste0("leave_out_", tolower(county_name))
  ) %>% filter(.data$term == term)
  sensitivity_availability[[length(sensitivity_availability) + 1L]] <- tibble(
    specification = paste0("leave_out_", tolower(county_name)), metro = metro_name,
    available = TRUE, reason = ""
  )
}

weighted_or_missing <- function(values, weights) {
  valid <- is.finite(values) & is.finite(weights) & weights > 0
  if (!any(valid)) return(NA_real_)
  weighted.mean(values[valid], weights[valid])
}

descriptive <- tier_panel %>% group_by(metro, regime, tier_type, price_tier) %>%
  summarise(
    median_real_price = weighted_or_missing(median_real_price, transactions),
    transactions = sum(transactions),
    median_real_hhi = median(median_hhi_real, na.rm = TRUE),
    median_payment_to_income = median(payment_to_income, na.rm = TRUE),
    months = n_distinct(sale_month), .groups = "drop"
  )

indexed_monthly <- tier_panel %>%
  group_by(metro, tier_type, price_tier, sale_month, regime) %>%
  summarise(
    transaction_volume = sum(transactions),
    real_price = weighted_or_missing(median_real_price, transactions),
    real_income = weighted_or_missing(median_hhi_real, households),
    payment_burden = weighted_or_missing(payment_to_income, transactions),
    .groups = "drop"
  ) %>%
  group_by(metro, tier_type, price_tier) %>%
  mutate(
    baseline_real_price = mean(real_price[regime == "BASELINE"], na.rm = TRUE),
    baseline_real_income = mean(real_income[regime == "BASELINE"], na.rm = TRUE),
    baseline_payment_burden = mean(
      payment_burden[regime == "BASELINE"], na.rm = TRUE
    ),
    baseline_transactions = mean(
      transaction_volume[regime == "BASELINE"], na.rm = TRUE
    ),
    real_price_index = 100 * real_price / baseline_real_price,
    real_income_index = 100 * real_income / baseline_real_income,
    payment_burden_index = 100 * payment_burden / baseline_payment_burden,
    transaction_volume_index = 100 * transaction_volume / baseline_transactions
  ) %>% ungroup()
indexed_regimes <- indexed_monthly %>%
  group_by(metro, regime, tier_type, price_tier) %>%
  summarise(
    real_price_index = mean(real_price_index, na.rm = TRUE),
    real_income_index = mean(real_income_index, na.rm = TRUE),
    payment_burden_index = mean(payment_burden_index, na.rm = TRUE),
    transaction_volume_index = mean(transaction_volume_index, na.rm = TRUE),
    months = n(), .groups = "drop"
  )

all_coefficients <- bind_rows(all_coefficients, pooled_coefficients)
wild_results <- bind_rows(wild_results)
pretrend_results <- bind_rows(pretrend_results)
event_study_results <- bind_rows(event_study_results)
sensitivity_results <- bind_rows(sensitivity_results)
sensitivity_availability <- bind_rows(sensitivity_availability)
ratio_results <- bind_rows(ratio_results)

write_csv(all_coefficients, file.path(output_root, "model_coefficients.csv"))
write_csv(wild_results, file.path(output_root, "wild_cluster_bootstrap.csv"))
write_csv(pretrend_results, file.path(output_root, "pretrend_tests.csv"))
write_csv(event_study_results, file.path(output_root, "event_study_coefficients.csv"))
write_csv(sensitivity_results, file.path(output_root, "sensitivity_coefficients.csv"))
write_csv(sensitivity_availability,
          file.path(output_root, "sensitivity_availability.csv"))
write_csv(ratio_results, file.path(output_root, "slope_ratios.csv"))
write_csv(pooled_linear_combinations,
          file.path(output_root, "pooled_linear_combinations.csv"))
write_csv(descriptive, file.path(output_root, "regime_descriptives.csv"))
write_csv(indexed_monthly, file.path(output_root, "indexed_monthly_trends.csv"))
write_csv(indexed_regimes, file.path(output_root, "indexed_regime_comparison.csv"))
saveRDS(c(saved_models, ratio_models), file.path(output_root, "longitudinal_models.rds"))

notes <- c(
  "# Longitudinal model notes",
  "",
  "- These models estimate associations among completed transactions and listing aggregates; they do not identify a demand curve.",
  "- The primary price and volume models include county and calendar-month fixed effects, so the national mortgage-rate main effect is absorbed.",
  "- Tier interactions use fixed 2015-2019 metro-specific boundaries, but transaction tier still depends on realized sale price.",
  "- County-clustered covariance is reported throughout; the headline differential also receives a Webb-weight wild-cluster-bootstrap sensitivity.",
  "- Event-study lead/lag intervals use Webb-weight wild-cluster-bootstrap draws so every reported interaction has defined few-county uncertainty.",
  "- Poisson volume coefficients use clustered covariance; their wild-bootstrap check uses an explicitly labeled auxiliary log(count + 0.5) linear model because residual wild bootstrapping a Poisson response can generate invalid counts.",
  "- The move-up-to-entry ratio comes from a secondary year-and-season fixed-effect model because absolute national rate slopes are not identified with calendar-month effects.",
  "- The ratio output reports a county-bootstrap interval and a centered bootstrap test against the prior 4.5 value; 4.5 is not imposed during estimation.",
  "- Percent-effect columns transform log-link coefficients as 100 * (exp(beta) - 1); rate exposure is measured in percentage points.",
  "- Failed pre-trend tests require associational rather than causal DiD language."
)
writeLines(notes, file.path(output_root, "MODEL_NOTES.md"))

cat("Estimated metro and pooled longitudinal models\n")
cat("  coefficient rows:", nrow(all_coefficients), "\n")
cat("  sensitivity rows:", nrow(sensitivity_results), "\n")
cat("  wild bootstrap repetitions:", bootstrap_reps, "\n")
