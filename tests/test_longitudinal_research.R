#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(dplyr)
  library(tidyr)
})

labels <- c("ENTRY", "MOVE_UP_MID_LUXURY", "HIGH_END")
prices <- exp(c(rnorm(200, log(150000), 0.08),
                rnorm(200, log(400000), 0.08),
                rnorm(200, log(900000), 0.08)))

fit_boundaries <- function(values) {
  set.seed(42)
  model <- kmeans(log(values), centers = 3L, nstart = 50L)
  centers <- sort(as.numeric(model$centers))
  exp((centers[-length(centers)] + centers[-1]) / 2)
}

first <- fit_boundaries(prices)
second <- fit_boundaries(prices)
stopifnot(identical(first, second), length(first) == 2L, first[1] < first[2])

months <- format(seq.Date(as.Date("2015-01-01"), as.Date("2025-12-01"), by = "month"),
                 "%Y-%m")
grid <- crossing(county = sprintf("county_%02d", 1:12), sale_month = months,
                 price_tier = labels)
stopifnot(nrow(grid) == 4752L, n_distinct(grid$sale_month) == 132L)

observed <- tibble(county = "county_01", sale_month = "2015-01",
                   price_tier = "ENTRY", transactions = 2L,
                   median_real_price = 200000)
joined <- grid %>% left_join(observed, by = c("county", "sale_month", "price_tier")) %>%
  mutate(transactions = replace_na(transactions, 0L))
missing_cell <- joined %>% filter(county == "county_01", sale_month == "2015-01",
                                  price_tier == "HIGH_END")
stopifnot(missing_cell$transactions == 0L, is.na(missing_cell$median_real_price))

beta <- -0.05
percent_change <- 100 * (exp(beta) - 1)
stopifnot(abs(percent_change - (-4.877058)) < 1e-5)

rate_percent <- 6.5
rate_gap_pp <- rate_percent - 3.0
stopifnot(rate_gap_pp == 3.5)

ordered_tier <- ordered(labels, levels = labels)
model_tier <- relevel(
  factor(as.character(ordered_tier), levels = labels, ordered = FALSE),
  ref = "ENTRY"
)
stopifnot(!is.ordered(model_tier), levels(model_tier)[1] == "ENTRY")

set.seed(42)
bootstrap_fixture <- tibble(
  outcome = rnorm(60), exposure = rep(seq(-1, 1, length.out = 20), 3),
  county = rep(letters[1:3], each = 20), model_weight = sample(1:5, 60, replace = TRUE)
)
weighted_model <- lm(outcome ~ exposure + factor(county), data = bootstrap_fixture,
                     weights = model_weight)
bootstrap_fixture$.bootstrap_weights <- weighted_model$weights
bootstrap_fixture$outcome <- fitted(weighted_model) + residuals(weighted_model)
weighted_refit <- lm(formula(weighted_model), data = bootstrap_fixture,
                     weights = .bootstrap_weights)
stopifnot(is.finite(coef(weighted_refit)[["exposure"]]))

cat("Longitudinal R contract tests passed\n")
