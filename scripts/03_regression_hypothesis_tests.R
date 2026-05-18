# ══════════════════════════════════════════════════════════════════════════════
# Regression, Hypothesis Tests & Forecast
# Indiana Move-Up Housing Market Analysis
#
# Analyses:
#   Histogram:        log sale price distribution (fig11_histogram_price.png)
#   Hypothesis test:  Welch t-test, pre vs post rate shock
#   Scatterplot:      HHI vs sale price by ZIP (fig10 produced in 02_eda)
#   Simple OLS:       m_simple — log(price) ~ rate_gap
#   Multiple OLS:     m_price_interact, m_did_price_triple (interactions)
#   Tables:           modelsummary with HC1 robust SEs; HTML chosen for vcov support
#
# Model naming convention: m_{outcome}_{specification}
#   outcome:       simple, dom, stl, price, did_dom, did_price, did_volume
#   specification: base, controls, interact, county_fe, twoway_fe, simple, fe, triple
#
# Unit of analysis:
#   Redfin panel:     County-month cell (5 counties × 60 months;
#                     nrow(panel_data) printed at runtime via cat())
#   SDF transactions: Individual deed record (study window 2021–2025;
#                     nrow(sdf) printed at runtime via cat())
#
# Key methodological notes:
#   1. Geography proxies for buyer type — not direct identification
#      Future research: HMDA data for direct move-up buyer identification
#   2. Marion income constraint (median HHI carried in `marion_hhi`)
#      means DiD is a conservative lower bound on the true suburban
#      treatment effect
#   3. DOM subject to delist-relist gaming — lower bound caveat
#   4. luxury tier driven by thin market volatility, not rate sensitivity
#   5. OVB candidates: Hamilton County new construction (Eli Lilly/Amazon),
#      school district premiums (Carmel/Fishers), corporate relocations
# ══════════════════════════════════════════════════════════════════════════════

# ── Package setup ─────────────────────────────────────────────────────────────
if (!require("pacman")) install.packages("pacman")
pacman::p_load(tidyverse, modelsummary, lmtest, sandwich, scales, webshot2,
               here, sf, tigris, ggrepel)

# ── Analysis constants ────────────────────────────────────────────────────────
RATE_BASELINE <- 3.0     # 2021 avg 30-yr fixed rate used as lock-in baseline
luxury_CAP     <- 15e6    # $15M — removes data entry errors from luxury tier
MIN_PRICE     <- 50000   # $50K — removes implausible deed transfers
LTV_RATIO     <- 0.80    # 80% LTV assumption for affordability calculation

# ── Load data ─────────────────────────────────────────────────────────────────
panel_data <- readRDS(here::here("data/processed/panel_data.rds"))

sdf_raw <- read_csv(here::here("data/processed/sdf_indiana.csv"),
                    show_col_types = FALSE) %>%
  filter(!(price_segment == "luxury" & sale_price > luxury_CAP))

# ── Factor releveling — entry tier and metro as reference groups ──────────────
panel_data <- panel_data %>%
  mutate(
    price_segment = relevel(factor(price_segment), ref = "entry"),
    geography     = relevel(factor(geography),     ref = "metro"),
    county        = factor(county),
    year          = factor(year)
  )

# ── Robust SE helper ──────────────────────────────────────────────────────────
# HC1 corrects for heteroskedasticity — appropriate here because low-priced
# Marion transactions and higher-priced suburban transactions exhibit
# substantially different error variance.
# Standard OLS SEs would be artificially small without this correction.
robust_se <- function(model) {
  coeftest(model, vcov = vcovHC(model, type = "HC1"))
}

# ── County controls and rate lookup for SDF join ─────────────────────────────
county_controls <- panel_data %>%
  distinct(county, geography, median_hhi, population) %>%
  mutate(county = as.character(county))

rate_lookup <- panel_data %>%
  distinct(year, month, mortgage_rate, rate_gap, post) %>%
  mutate(year = as.integer(as.character(year)))

# ── Build SDF transaction-level dataset ──────────────────────────────────────
sdf <- sdf_raw %>%
  mutate(
    sale_date     = as.Date(sale_date),
    year          = year(sale_date),
    month         = month(sale_date),
    price_segment = factor(price_segment,
                           levels = c("entry", "move_up", "luxury"))
  ) %>%
  left_join(county_controls, by = "county") %>%
  left_join(rate_lookup,     by = c("year", "month")) %>%
  mutate(
    treated = if_else(geography == "suburb", 1L, 0L),
    did     = treated * post,
    monthly_payment = (sale_price * LTV_RATIO *
                         (mortgage_rate / 1200 *
                            (1 + mortgage_rate / 1200)^360) /
                         ((1 + mortgage_rate / 1200)^360 - 1)),
    affordability_ratio = monthly_payment / (median_hhi / 12),
    log_sale_price      = log(sale_price),
    county              = factor(county),
    year                = factor(year),
    price_segment       = relevel(price_segment,       ref = "entry"),
    geography           = relevel(factor(geography),   ref = "metro")
  ) %>%
  filter(!is.na(rate_gap), !is.na(sale_price), sale_price > MIN_PRICE)

n_sdf   <- formatC(nrow(sdf), format = "f", digits = 0, big.mark = ",")
n_label <- n_sdf
n_panel <- formatC(nrow(panel_data), format = "f", digits = 0, big.mark = ",")
year_range_label <- paste(
  min(as.integer(as.character(sdf$year))),
  max(as.integer(as.character(sdf$year))),
  sep = "–"
)

# ── Derived labels for figures and captions ──────────────────────────────────
# Tier breakpoints are derived from the price_segment factor (k-means output).
entry_max_p      <- max(sdf$sale_price[sdf$price_segment == "entry"],      na.rm = TRUE)
midlux_max_p     <- max(sdf$sale_price[sdf$price_segment == "move_up"],    na.rm = TRUE)
entry_break_k    <- round(entry_max_p  / 1000)
midlux_break_m   <- round(midlux_max_p / 1e6, 2)
midlux_break_lbl <- if (isTRUE(all.equal(midlux_break_m, round(midlux_break_m))))
  paste0(as.integer(round(midlux_break_m)), "M") else paste0(midlux_break_m, "M")
entry_label  <- paste0("Entry (<$",      entry_break_k, "K)")
midlux_label <- paste0("Move-up ($",     entry_break_k, "K–$", midlux_break_lbl, ")")
luxury_label <- paste0("Luxury (>$",     midlux_break_lbl, ")")

# Current rate gap and corresponding mortgage rate — derived from latest panel month
latest_row    <- panel_data %>%
  arrange(as.integer(as.character(year)), month) %>%
  slice_tail(n = 1)
current_gap   <- round(latest_row$rate_gap[1], 1)
current_rate  <- round(latest_row$mortgage_rate[1], 1)

# Peak rate gap observed across the panel — used in figure 12 caption to
# anchor the historical maximum without a hard-coded value
peak_gap_pp   <- round(max(panel_data$rate_gap, na.rm = TRUE), 1)
peak_rate_pct <- round(peak_gap_pp + RATE_BASELINE, 1)

# Marion HHI carried forward from panel_data for any narrative references
marion_hhi <- panel_data %>%
  filter(county == "Marion") %>%
  pull(median_hhi) %>%
  first()
marion_hhi_short <- paste0("$", formatC(round(marion_hhi / 1000), format = "f",
                                        digits = 0, big.mark = ","), "K")

cat("Unit of analysis 1: County-month cell —", nrow(panel_data), "obs\n")
cat("Unit of analysis 2: Individual deed record —", nrow(sdf), "transactions\n\n")

# ══════════════════════════════════════════════════════════════════════════════
# FIGURE 11 — Distribution of log sale price
# Right skew on raw scale → log transformation normalizes distribution
# Justifies log-linear regression specification throughout
# ══════════════════════════════════════════════════════════════════════════════

median_log   <- median(sdf$log_sale_price, na.rm = TRUE)
median_price <- exp(median_log)
median_label <- paste0("$", round(median_price / 1000, 0), "K")
entry_pct    <- round(sum(sdf$price_segment == "entry") / nrow(sdf) * 100, 0)

sdf %>%
  ggplot(aes(x = log_sale_price)) +
  geom_histogram(bins = 60, fill = "#4472C4", color = "white",
                 alpha = 0.8, na.rm = TRUE) +
  geom_vline(xintercept = median_log,
             linetype = "dashed", color = "red", linewidth = 1) +
  annotate("text",
           x = median_log + 0.05, y = 15000,
           label = paste0("Median: ", median_label),
           hjust = 0, size = 3.5, color = "red") +
  scale_x_continuous(
    limits = c(log(MIN_PRICE), log(1500000)),
    breaks = log(c(75000, 150000, 250000, entry_break_k * 1000,
                   600000, midlux_max_p)),
    labels = c("$75K", "$150K", "$250K",
               paste0("$", entry_break_k, "K"),
               "$600K",
               paste0("$", midlux_break_lbl))
  ) +
  labs(
    title    = "Distribution of Single Family Residential Sale Prices",
    subtitle = paste0("Log scale | Indianapolis metro ", year_range_label,
                      " | N = ", n_label, " transactions"),
    x       = "Sale price (log scale)",
    y       = "Count of transactions",
    caption = paste0(
      "Source: STATS Indiana SDF deed records.\n",
      "Raw sale prices are right-skewed. Log transformation normalizes the distribution.\n",
      "Median ", median_label, " reflects entry-tier dominance (",
      entry_pct, "% of transactions)."
    )
  ) +
  theme_minimal(base_size = 13) +
  theme(
    plot.title            = element_text(face = "bold", size = 14, hjust = 0.5),
    plot.subtitle         = element_text(color = "grey40", size = 11, hjust = 0.5),
    plot.title.position   = "plot",
    plot.caption          = element_text(color = "grey50", size = 9,
                                         hjust = 0, margin = margin(t = 8)),
    plot.caption.position = "plot",
    panel.grid.minor      = element_blank()
  )

ggsave(here::here("outputs/figures/fig11_histogram_price.png"), width = 9, height = 5, dpi = 300)
ggsave(here::here("outputs/figures/fig11_histogram_price.pdf"), width = 9, height = 5)
cat("Saved fig11_histogram_price.png/.pdf — median:", median_label, "\n")

# ══════════════════════════════════════════════════════════════════════════════
# FIGURE 10 NOTE — HHI vs median sale price (produced in 02_eda_descriptive_stats.R)
# Shows median sale price (DV) vs median household income (key IV/control)
# Illustrates two-mechanism hypothesis: Marion clusters bottom-left (income-constrained), Hamilton top-right (rate lock-in exposed)
# ══════════════════════════════════════════════════════════════════════════════

fig10_stats <- readRDS(here::here("data/processed/fig10_correlation_stats.rds"))
cat("ZIP-level HHI-price correlation: r =", fig10_stats$r,
    "| R² =", fig10_stats$r2,
    "| N =", fig10_stats$n_zip, "zip codes\n\n")

# ══════════════════════════════════════════════════════════════════════════════
# TABLE 2 — Hypothesis test: Welch two-sample t-test, pre vs post rate shock
# H0: Mean log sale price is equal pre vs post rate shock
# H1: Mean log sale price differs post rate shock
# Method: Welch two-sample t-test (unequal variances — var.equal = FALSE)
# ══════════════════════════════════════════════════════════════════════════════

pre_shock  <- sdf %>% filter(post == 0) %>% pull(log_sale_price)
post_shock <- sdf %>% filter(post == 1) %>% pull(log_sale_price)
t_overall  <- t.test(pre_shock, post_shock,
                     alternative = "two.sided", var.equal = FALSE)

# ── Helper functions ───────────────────────────────────────────────────────────
fmt_p <- function(p) {
  if (p < 2.2e-16) "< 2.2e-16"
  else format(p, scientific = TRUE, digits = 3)
}

fmt_price <- function(x) {
  paste0("$", formatC(round(exp(mean(x)) / 1000, 0),
                      format = "f", digits = 0, big.mark = ","), "K")
}

fmt_pct <- function(pre, post) {
  pct <- (exp(mean(post)) / exp(mean(pre)) - 1) * 100
  paste0(ifelse(pct >= 0, "+", ""), round(pct, 1), "%")
}

fmt_decision <- function(p) {
  if      (p < 0.001) "Reject H\u2080 ***"
  else if (p < 0.01)  "Reject H\u2080 **"
  else if (p < 0.05)  "Reject H\u2080 *"
  else                "Fail to reject H\u2080"
}

overall_row <- tibble(
  Group      = "All segments (overall)",
  N_Pre      = formatC(length(pre_shock),  format = "f", digits = 0, big.mark = ","),
  N_Post     = formatC(length(post_shock), format = "f", digits = 0, big.mark = ","),
  Mean_Pre   = fmt_price(pre_shock),
  Mean_Post  = fmt_price(post_shock),
  Pct_Change = fmt_pct(pre_shock, post_shock),
  t_stat     = as.character(round(t_overall$statistic, 3)),
  p_value    = fmt_p(t_overall$p.value),
  Decision   = fmt_decision(t_overall$p.value)
)

seg_results <- sdf %>%
  filter(price_segment != "luxury") %>%
  mutate(Group = case_when(
    price_segment == "entry"      ~ entry_label,
    price_segment == "move_up"    ~ midlux_label
  )) %>%
  group_by(Group) %>%
  summarise(
    N_Pre      = formatC(sum(post == 0), format = "f", digits = 0, big.mark = ","),
    N_Post     = formatC(sum(post == 1), format = "f", digits = 0, big.mark = ","),
    Mean_Pre   = fmt_price(log_sale_price[post == 0]),
    Mean_Post  = fmt_price(log_sale_price[post == 1]),
    Pct_Change = fmt_pct(log_sale_price[post == 0], log_sale_price[post == 1]),
    t_stat     = as.character(round(
      t.test(log_sale_price[post == 0],
             log_sale_price[post == 1])$statistic, 3)),
    p_value    = fmt_p(t.test(log_sale_price[post == 0],
                              log_sale_price[post == 1])$p.value),
    Decision   = fmt_decision(t.test(log_sale_price[post == 0],
                                     log_sale_price[post == 1])$p.value),
    .groups    = "drop"
  )

geo_results <- sdf %>%
  mutate(Group = if_else(geography == "metro",
                         "Marion County (metro)", "Suburbs (treated)")) %>%
  group_by(Group) %>%
  summarise(
    N_Pre      = formatC(sum(post == 0), format = "f", digits = 0, big.mark = ","),
    N_Post     = formatC(sum(post == 1), format = "f", digits = 0, big.mark = ","),
    Mean_Pre   = fmt_price(log_sale_price[post == 0]),
    Mean_Post  = fmt_price(log_sale_price[post == 1]),
    Pct_Change = fmt_pct(log_sale_price[post == 0], log_sale_price[post == 1]),
    t_stat     = as.character(round(
      t.test(log_sale_price[post == 0],
             log_sale_price[post == 1])$statistic, 3)),
    p_value    = fmt_p(t.test(log_sale_price[post == 0],
                              log_sale_price[post == 1])$p.value),
    Decision   = fmt_decision(t.test(log_sale_price[post == 0],
                                     log_sale_price[post == 1])$p.value),
    .groups    = "drop"
  )

blank_row <- function(label) {
  tibble(Group = label, N_Pre = "", N_Post = "", Mean_Pre = "", Mean_Post = "",
         Pct_Change = "", t_stat = "", p_value = "", Decision = "")
}

section_seg <- blank_row(
  "\u2500\u2500 By price segment \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500"
)
section_geo <- blank_row(
  "\u2500\u2500 By geography (DiD motivation) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500"
)

tbl_combined <- bind_rows(overall_row, section_seg, seg_results,
                          section_geo, geo_results) %>%
  rename(` `           = Group,
         `N (pre)`     = N_Pre,
         `N (post)`    = N_Post,
         `Mean pre`    = Mean_Pre,
         `Mean post`   = Mean_Post,
         `% Change`    = Pct_Change,
         `t-statistic` = t_stat,
         `p-value`     = p_value,
         `Decision`    = Decision)

datasummary_df(
  tbl_combined,
  title = "Table 2: Hypothesis Test \u2014 Welch Two-Sample T-Test, Pre vs Post Rate Shock",
  notes = paste0(
    "H\u2080: \u03bc_pre = \u03bc_post \u00b7 ",
    "H\u2081: \u03bc_pre \u2260 \u03bc_post (two-tailed) \u00b7 ",
    "Welch t-test (unequal variances) \u00b7 ",
    "Pre = rate_gap < 2.0 (early 2021\u2013mid-2022) \u00b7 Post = rate_gap \u2265 2.0 (mid-2022\u20132025) \u00b7 ",
    "Means transformed back to dollars \u00b7 N = ", n_label,
    " \u00b7 *** p<0.001 ** p<0.01 * p<0.05"
  ),
  output = here::here("outputs/tables/table2_hypothesis_test.html")
)

webshot2::webshot(
  url   = paste0("file://", here::here("outputs/tables/table2_hypothesis_test.html")),
  file  = here::here("outputs/tables/table2_hypothesis_test.png"),
  delay = 2, zoom = 1.5, vwidth = 1200
)
file.remove(here::here("outputs/tables/table2_hypothesis_test.html"))
cat("Saved table2_hypothesis_test.png\n")

# ══════════════════════════════════════════════════════════════════════════════
# TABLE 3 and TABLE 4 — Pearson correlation matrix and standard error by segment
# ══════════════════════════════════════════════════════════════════════════════

cat("── Standard Errors ──────────────────────────────────────────────────\n")
se <- function(x) sd(x, na.rm = TRUE) / sqrt(sum(!is.na(x)))

sdf %>%
  group_by(price_segment) %>%
  summarise(n          = n(),
            mean_price = dollar(exp(mean(log_sale_price, na.rm = TRUE))),
            sd_price   = dollar(exp(sd(log_sale_price, na.rm = TRUE))),
            se_price   = round(se(log_sale_price), 6),
            .groups    = "drop") %>%
  print()

cat("\n── Pearson correlation matrix ───────────────────────────────────────\n")
cor_data <- sdf %>%
  select(`Log sale price`    = log_sale_price,
         `Rate gap (pp)`     = rate_gap,
         `Mortgage rate (%)` = mortgage_rate,
         `Median HHI`        = median_hhi,
         `Affordability`     = affordability_ratio,
         `Monthly payment`   = monthly_payment,
         `Population`        = population) %>%
  filter(complete.cases(.))

cat("Correlation matrix N =", nrow(cor_data), "\n\n")
print(round(cor(cor_data, method = "pearson"), 3))

# Dynamic correlations referenced in Table 6 notes ----------------------------
cor_txn_hhi_logprice <- cor(cor_data[["Median HHI"]],
                            cor_data[["Log sale price"]],
                            method = "pearson")
cor_txn_label <- format(round(cor_txn_hhi_logprice, 3), nsmall = 3)
cor_zip_label <- format(round(fig10_stats$r,         3), nsmall = 3)
n_cor_label   <- formatC(nrow(cor_data), format = "f", digits = 0, big.mark = ",")
cat("Transaction-level r(HHI, log price) =", cor_txn_label,
    "| ZIP-level r (fig10) =", cor_zip_label, "\n")

datasummary_correlation(
  cor_data,
  title  = "Table 3: Pearson Correlation Matrix — Key Continuous Variables",
  notes = paste0(
    "N = ", n_cor_label, " individual transactions. Pearson r. ",
    "Note: transaction-level r = ", cor_txn_label,
    " for HHI vs log sale price is lower than ",
    "ZIP-level r = ", cor_zip_label, " (fig10) because individual transactions include ",
    "substantial idiosyncratic variance (fixer-uppers, estate sales, income-stretching). ",
    "Aggregation to ZIP code smooths this noise, revealing the income-price relationship. ",
    "Both values are correct at their respective units of analysis."
  ),
  output = here::here("outputs/tables/table3_correlation.html")
)
webshot2::webshot(
  url   = paste0("file://", here::here("outputs/tables/table3_correlation.html")),
  file  = here::here("outputs/tables/table3_correlation.png"),
  delay = 2, zoom = 1.5, vwidth = 900
)
file.remove(here::here("outputs/tables/table3_correlation.html"))
cat("Saved outputs/tables/table3_correlation.png\n")

se_table <- sdf %>%
  mutate(Segment = case_when(
    price_segment == "entry"      ~ entry_label,
    price_segment == "move_up"    ~ midlux_label,
    price_segment == "luxury"     ~ luxury_label
  )) %>%
  mutate(Segment = factor(Segment, levels = c(entry_label, midlux_label, luxury_label))) %>%
  group_by(Segment) %>%
  summarise(
    N                = formatC(n(), format = "f", digits = 0, big.mark = ","),
    `Mean log price` = round(mean(log_sale_price, na.rm = TRUE), 4),
    `SD`             = round(sd(log_sale_price,   na.rm = TRUE), 4),
    `Std. Error`     = round(se(log_sale_price), 4),
    `95% CI lower`   = round(mean(log_sale_price, na.rm = TRUE) -
                               1.96 * se(log_sale_price), 4),
    `95% CI upper`   = round(mean(log_sale_price, na.rm = TRUE) +
                               1.96 * se(log_sale_price), 4),
    .groups = "drop"
  )

datasummary_df(
  se_table,
  title  = "Table 4: Standard Error of Log Sale Price by Price Segment",
  notes  = paste0("SE = SD / \u221aN \u00b7 95% CI = mean \u00b1 1.96 \u00d7 SE \u00b7 ",
                  "DV = log sale price \u00b7 N = ", n_label),
  output = here::here("outputs/tables/table4_standard_error.html"),
  fmt    = 3
)
webshot2::webshot(
  url   = paste0("file://", here::here("outputs/tables/table4_standard_error.html")),
  file  = here::here("outputs/tables/table4_standard_error.png"),
  delay = 2, zoom = 1.5, vwidth = 1000
)
file.remove(here::here("outputs/tables/table4_standard_error.html"))
cat("Saved table4_standard_error.png\n")

# ══════════════════════════════════════════════════════════════════════════════
# REGRESSION MODELS — produces Tables 5, 6, and 7
# Model naming: m_{outcome}_{specification}
# ══════════════════════════════════════════════════════════════════════════════

# ── Simple linear regression — single IV baseline ────────────────────────────
# DV: log sale price | IV: rate_gap only | Baseline single-predictor model
m_simple <- lm(log_sale_price ~ rate_gap, data = sdf)
cat("\n── Simple regression (6b): log(price) ~ rate_gap ────────────────────\n")
cat("Adj R²:", round(summary(m_simple)$adj.r.squared, 3), "\n")
print(robust_se(m_simple))

# ── Redfin panel: DOM models ──────────────────────────────────────────────────
# DV: median days on market | Source: Redfin county-month panel
# (N matches nrow(panel_data); printed via cat() above as n_panel)
m_dom_base      <- lm(median_dom ~ rate_gap, data = panel_data)
m_dom_controls  <- lm(median_dom ~ rate_gap + price_segment + geography +
                        median_hhi + population + months_of_supply,
                      data = panel_data)
m_dom_interact  <- lm(median_dom ~ rate_gap * price_segment + geography +
                        median_hhi + population + months_of_supply,
                      data = panel_data)
m_dom_county_fe <- lm(median_dom ~ rate_gap * price_segment + geography +
                        median_hhi + population + months_of_supply +
                        factor(county),
                      data = panel_data)
m_dom_twoway_fe <- lm(median_dom ~ rate_gap * price_segment + geography +
                        median_hhi + population + months_of_supply +
                        factor(county) + factor(year),
                      data = panel_data)

# ── Redfin panel: sale-to-list models ────────────────────────────────────────
# DV: avg sale-to-list ratio | Source: Redfin county-month panel
m_stl_interact  <- lm(avg_sale_to_list ~ rate_gap * price_segment + geography +
                        median_hhi + population + affordability_ratio,
                      data = panel_data)
m_stl_fe        <- lm(avg_sale_to_list ~ rate_gap * price_segment + geography +
                        median_hhi + population + affordability_ratio +
                        factor(county) + factor(year),
                      data = panel_data)

# ── Redfin panel: DiD models on DOM ──────────────────────────────────────────
# Treatment = suburbs (proxy for move-up buyers)
# Control   = Marion County (proxy for necessity-driven buyers)
# Limitation: geography is an imperfect proxy for buyer type
# Marion income constraint (median HHI carried in `marion_hhi`)
# makes DiD a conservative lower bound
m_did_dom_simple <- lm(median_dom ~ treated + post + did, data = panel_data)
m_did_dom_fe     <- lm(median_dom ~ did + factor(county) + factor(year),
                       data = panel_data)
m_did_dom_triple <- lm(median_dom ~ treated * post * price_segment +
                         median_hhi + population + months_of_supply +
                         affordability_ratio + factor(county) + factor(year),
                       data = panel_data)
m_did_stl_triple <- lm(avg_sale_to_list ~ treated * post * price_segment +
                         median_hhi + population + affordability_ratio +
                         factor(county) + factor(year),
                       data = panel_data)

# ── SDF transaction-level: log sale price ────────────────────────────────────
# DV: log sale price | Source: SDF deed records
# (N matches nrow(sdf); printed via cat() above as n_sdf)
m_price_base    <- lm(log_sale_price ~ rate_gap + price_segment + geography +
                        median_hhi + affordability_ratio,
                      data = sdf)

# Core squeeze test — rate_gap × price_segment interaction
# (move-up vs entry slope differential printed at runtime below)
m_price_interact <- lm(log_sale_price ~ rate_gap * price_segment + geography +
                         median_hhi + affordability_ratio,
                       data = sdf)

# Variant excluding affordability_ratio — tests collinearity sensitivity
m_price_interact_check <- lm(log_sale_price ~ rate_gap * price_segment + geography +
                         median_hhi,
                       data = sdf)

m_price_fe      <- lm(log_sale_price ~ rate_gap * price_segment + geography +
                        median_hhi + affordability_ratio +
                        factor(county) + factor(year),
                      data = sdf)

# ── SDF: DiD models on log sale price ────────────────────────────────────────
m_did_price_simple <- lm(log_sale_price ~ treated + post + did, data = sdf)
m_did_price_fe     <- lm(log_sale_price ~ treated * post +
                           median_hhi + affordability_ratio +
                           factor(county) + factor(year),
                         data = sdf)

# Headline DiD — triple interaction isolates suburban move-up effect
# post × move_up: Marion move-up fell post-shock
# treated × post × move_up: suburban offset (conservative lower bound)
m_did_price_triple <- lm(log_sale_price ~ treated * post * price_segment +
                           median_hhi + affordability_ratio +
                           factor(county) + factor(year),
                         data = sdf)

# ── SDF: transaction volume DiD ──────────────────────────────────────────────
# DV: transaction count | confirms market freeze in suburban move-up
sdf_counts <- sdf_raw %>%
  mutate(year = year(as.Date(sale_date)), month = month(as.Date(sale_date))) %>%
  count(county, year, month, price_segment, name = "transactions") %>%
  left_join(county_controls, by = "county") %>%
  left_join(rate_lookup,     by = c("year", "month")) %>%
  mutate(
    treated       = if_else(geography == "suburb", 1L, 0L),
    did           = treated * post,
    price_segment = relevel(factor(price_segment,
                                   levels = c("entry", "move_up", "luxury")),
                            ref = "entry"),
    county = factor(county),
    year   = factor(year)
  ) %>%
  filter(!is.na(rate_gap))

m_did_volume_triple <- lm(transactions ~ treated * post * price_segment +
                            median_hhi + population +
                            factor(county) + factor(year),
                          data = sdf_counts)

# ══════════════════════════════════════════════════════════════════════════════
# HEADLINE RESULTS
# ══════════════════════════════════════════════════════════════════════════════

cat("\n── Core squeeze: m_price_interact (rate_gap × price_segment) ────────\n")
coef_price      <- coef(m_price_interact)
rate_gap_entry  <- round(coef_price["rate_gap"] * 100, 1)
rate_gap_midlux <- round((coef_price["rate_gap"] +
                            coef_price["rate_gap:price_segmentmove_up"]) * 100, 1)

cat("Adj R²:", round(summary(m_price_interact)$adj.r.squared, 3), "\n")
cat("rate_gap:", rate_gap_entry, "%/pp for entry |",
    rate_gap_midlux, "%/pp for move-up\n")
print(robust_se(m_price_interact))

cat("\n── Triple DiD headline: m_did_price_triple ──────────────────────────\n")
coef_did_triple <- coef(m_did_price_triple)
post_midlux     <- round((exp(coef_did_triple["post:price_segmentmove_up"]) - 1) * 100, 1)
triple_did      <- round((exp(coef_did_triple["treated:post:price_segmentmove_up"]) - 1) * 100, 1)

cat("Adj R²:", round(summary(m_did_price_triple)$adj.r.squared, 3), "\n")
cat("post × move_up =", post_midlux,
    "% (Marion) | treated × post × move_up = +", triple_did,
    "% (suburban offset)\n")
print(robust_se(m_did_price_triple))

cat("\n── Volume DiD: m_did_volume_triple ──────────────────────────────────\n")
coef_vol    <- coef(m_did_volume_triple)
vol_did_est <- round(coef_vol["treated:post:price_segmentmove_up"], 0)
cat("treated × post × move_up =", vol_did_est,
    "transactions/month (market freeze)\n")
print(robust_se(m_did_volume_triple))

# ══════════════════════════════════════════════════════════════════════════════
# TABLES 5, 6, 7 — DOM models, price models, DiD models
# modelsummary chosen over stargazer for HTML output and vcov argument support
# ══════════════════════════════════════════════════════════════════════════════

coef_map <- c(
  "rate_gap"                          = "Rate gap (pp)",
  "price_segmentmove_up"              = "Move-up tier",
  "price_segmentluxury"               = paste0("Luxury tier (>$", midlux_break_lbl, ")"),
  "geographysuburb"                   = "Suburb",
  "median_hhi"                        = "Median HHI",
  "population"                        = "Population",
  "months_of_supply"                  = "Months of supply",
  "affordability_ratio"               = "Affordability ratio",
  "rate_gap:price_segmentmove_up"     = "Rate gap \u00d7 Move-up",
  "rate_gap:price_segmentluxury"      = "Rate gap \u00d7 Luxury",
  "treated"                           = "Suburb (treated)",
  "post"                              = "Post shock",
  "did"                               = "DiD (suburb \u00d7 post)",
  "treated:post"                      = "Suburb \u00d7 Post (DiD)",
  "treated:price_segmentmove_up"      = "Suburb \u00d7 Move-up",
  "treated:price_segmentluxury"       = "Suburb \u00d7 Luxury",
  "post:price_segmentmove_up"         = "Post \u00d7 Move-up",
  "post:price_segmentluxury"          = "Post \u00d7 Luxury",
  "treated:post:price_segmentmove_up" = "Suburb \u00d7 Post \u00d7 Move-up",
  "treated:post:price_segmentluxury"  = "Suburb \u00d7 Post \u00d7 Luxury"
)

# ── TABLE 5: Simple + DOM models (Redfin panel) ───────────────────────────────
modelsummary(
  list(
    "Simple"           = m_simple,
    "DOM (baseline)"   = m_dom_base,
    "DOM (controls)"   = m_dom_controls,
    "DOM (interact)"   = m_dom_interact,
    "DOM (two-way FE)" = m_dom_twoway_fe
  ),
  vcov      = "HC1",
  stars     = c("*" = 0.1, "**" = 0.05, "***" = 0.01),
  coef_map  = coef_map,
  coef_omit = "factor\\(county\\)|factor\\(year\\)",
  gof_map   = c("nobs", "r.squared", "adj.r.squared"),
  title     = "Table 5: Simple and Multiple Regression — Days on Market (Redfin Panel)",
  notes     = paste0(
    "Simple DV is log sale price. DOM models DV is median DOM, ",
    "Redfin county-month panel (N=", n_panel, "). HC1 robust SEs. ",
    "DOM subject to delist-relist gaming — lower bound interpretation."
  ),
  output    = here::here("outputs/tables/table5_dom_models.html")
)

# ── TABLE 6: SDF price models — core squeeze evidence ────────────────────────
modelsummary(
  list(
    "Log price (base)"     = m_price_base,
    "Log price (interact)" = m_price_interact,
    "Log price (FE)"       = m_price_fe
  ),
  vcov      = "HC1",
  stars     = c("*" = 0.1, "**" = 0.05, "***" = 0.01),
  coef_map  = coef_map,
  coef_omit = "factor\\(county\\)|factor\\(year\\)",
  gof_map   = c("nobs", "r.squared", "adj.r.squared"),
  title     = "Table 6: Rate Lock-In Effect on Sale Prices",
  notes     = paste0(
    "Source: STATS Indiana SDF deed records. ",
    "DV: log sale price. N=", n_label, " transactions. HC1 robust SEs. ",
    "Luxury tier capped at ", dollar(luxury_CAP),
    ". County and year FE omitted from display. ",
    "OVB candidates: new construction (Hamilton County Eli Lilly/Amazon expansion), ",
    "school district premiums (Carmel/Fishers), corporate relocations."
  ),
  output    = here::here("outputs/tables/table6_price_models.html")
)

# ── TABLE 7: DiD models ────────────────────────────────────────────────────────
modelsummary(
  list(
    "Price DiD (simple)"  = m_did_price_simple,
    "Price DiD (FE)"      = m_did_price_fe,
    "Price DiD (triple)"  = m_did_price_triple,
    "Volume (triple DiD)" = m_did_volume_triple
  ),
  vcov      = "HC1",
  stars     = c("*" = 0.1, "**" = 0.05, "***" = 0.01),
  coef_map  = coef_map,
  coef_omit = "factor\\(county\\)|factor\\(year\\)",
  gof_map   = c("nobs", "r.squared", "adj.r.squared"),
  title     = "Table 7: Difference-in-Differences Estimates — Price and Volume",
  notes     = paste0(
    "Treatment = suburban counties (proxy for move-up buyers). ",
    "Control = Marion County (proxy for necessity-driven buyers). ",
    "Geography is imperfect proxy for buyer type — HMDA data needed. ",
    "Marion income constraint (median HHI ", marion_hhi_short,
    ") implies conservative lower bounds."
  ),
  output    = here::here("outputs/tables/table7_did_models.html")
)

cat("Saved: table5, table6, table7 HTML — rendering to PNG\n")

for (tbl in c("table5_dom_models", "table6_price_models", "table7_did_models")) {
  tbl_html <- here::here("outputs/tables", paste0(tbl, ".html"))
  tbl_png  <- here::here("outputs/tables", paste0(tbl, ".png"))
  webshot2::webshot(
    url   = paste0("file://", tbl_html),
    file  = tbl_png,
    delay = 2, zoom = 1.5, vwidth = 1200
  )
  file.remove(tbl_html)
  cat("Saved outputs/tables/", paste0(tbl, ".png"), "\n")
}

# ══════════════════════════════════════════════════════════════════════════════
# FIGURE 12 — Marginal effects: predicted price by rate gap and segment
# Derived from m_price_interact using segment-specific median controls
# ══════════════════════════════════════════════════════════════════════════════

coef_price   <- coef(m_price_interact)
slope_entry  <- round((exp(coef_price["rate_gap"]) - 1) * 100, 1)
slope_midlux <- round((exp(coef_price["rate_gap"] +
                             coef_price["rate_gap:price_segmentmove_up"]) - 1) * 100, 1)
slope_luxury  <- round((exp(coef_price["rate_gap"] +
                              coef_price["rate_gap:price_segmentluxury"]) - 1) * 100, 1)

luxury_annual <- round(sum(sdf$price_segment == "luxury") /
                         (length(unique(sdf$county)) *
                            length(unique(as.character(sdf$year)))), 0)

# Squeeze multiplier (move-up slope / entry slope, exp-scale percent)
# Computed once here for reuse in fig12 annotation and the rate-sensitivity table.
squeeze_mult <- round(slope_midlux / slope_entry, 1)

cat("Slopes — Entry:", slope_entry, "%/pp | Move-up:", slope_midlux,
    "%/pp | luxury:", slope_luxury, "%/pp\n")
cat("Squeeze multiplier (move-up/entry):", squeeze_mult, "x\n")
cat("luxury transactions/county/year:", luxury_annual, "\n")

segment_medians <- sdf %>%
  group_by(price_segment) %>%
  summarise(median_hhi          = median(median_hhi,          na.rm = TRUE),
            affordability_ratio = median(affordability_ratio, na.rm = TRUE),
            .groups = "drop")

rate_grid <- bind_rows(lapply(c("entry", "move_up", "luxury"), function(seg) {
  expand.grid(
    rate_gap            = seq(-0.3, 4.6, by = 0.1),
    price_segment       = factor(seg, levels = c("entry", "move_up", "luxury")),
    geography           = factor("suburb", levels = c("metro", "suburb")),
    median_hhi          = segment_medians$median_hhi[
      segment_medians$price_segment == seg],
    affordability_ratio = segment_medians$affordability_ratio[
      segment_medians$price_segment == seg]
  )
}))

preds      <- predict(m_price_interact, newdata = rate_grid, interval = "confidence")
rate_grid <- cbind(rate_grid, as.data.frame(preds)) %>%
  mutate(fit_dollars = exp(fit), lwr_dollars = exp(lwr), upr_dollars = exp(upr))

y_range    <- max(rate_grid$upr_dollars) - min(rate_grid$lwr_dollars)

# Labels at x = 4.5 (right edge)
end_labels <- rate_grid %>%
  filter(abs(rate_gap - 4.5) < 0.01) %>%
  mutate(label   = paste0("$", round(fit_dollars / 1000, 0), "K"),
         label_y = fit_dollars + y_range * 0.04)

baseline_labels <- rate_grid %>%
  filter(abs(rate_gap - 0) < 0.01) %>%
  mutate(
    label   = paste0("$", round(fit_dollars / 1000, 0), "K"),
    label_y = case_when(
      price_segment == "luxury"      ~ fit_dollars + y_range * 0.08,
      TRUE                          ~ fit_dollars + y_range * 0.04
    )
  )

# Labels at current rate gap (derived from latest panel observation)
current_labels <- rate_grid %>%
  filter(abs(rate_gap - current_gap) < 0.05) %>%
  group_by(price_segment) %>%
  slice(1) %>%
  ungroup() %>%
  mutate(label   = paste0("$", round(fit_dollars / 1000, 0), "K"),
         label_y = fit_dollars + y_range * 0.04)

slope_label_data <- rate_grid %>%
  filter(abs(rate_gap - 1.0) < 0.01) %>%
  mutate(
    slope_label = case_when(
      price_segment == "entry"      ~ paste0(slope_entry,  "% per pp"),
      price_segment == "move_up"    ~ paste0(slope_midlux, "% per pp"),
      price_segment == "luxury"      ~ paste0(slope_luxury,  "% per pp")
    ),
    label_y = case_when(
      price_segment == "entry"      ~ fit_dollars + 80000,
      price_segment == "move_up"    ~ fit_dollars + 120000,
      price_segment == "luxury"      ~ fit_dollars + 180000
    )
  )

ggplot(rate_grid, aes(x = rate_gap, y = fit_dollars,
                      color = price_segment, fill = price_segment)) +
  geom_line(linewidth = 1.3) +
  geom_text(data = slope_label_data, aes(y = label_y, label = slope_label),
            hjust = 0.5, size = 3.2, fontface = "bold", show.legend = FALSE) +
  # Labels at 0pp (2021 baseline)
  geom_text(data = baseline_labels,
            aes(x = rate_gap, y = label_y, label = label, color = price_segment),
            hjust = 1.2, vjust = 0.5, size = 3.2, fontface = "bold",
            show.legend = FALSE, inherit.aes = FALSE) +
  # Labels at 3.1pp (current gap)
  geom_text(data = current_labels,
            aes(x = rate_gap, y = label_y, label = label, color = price_segment),
            hjust = 0.5, vjust = -0.5, size = 3.5, fontface = "bold",
            show.legend = FALSE, inherit.aes = FALSE) +
  # Labels at 4.5pp (right edge)
  geom_text(data = end_labels,
            aes(x = rate_gap, y = label_y, label = label, color = price_segment),
            hjust = -0.1, vjust = 0.5, size = 3.2, fontface = "bold",
            show.legend = FALSE, inherit.aes = FALSE) +
  geom_vline(xintercept = 0,            linetype = "dashed", color = "grey50") +
  geom_vline(xintercept = 2,            linetype = "dotted", color = "grey50") +
  geom_vline(xintercept = current_gap,  linetype = "dashed", color = "grey30") +
  annotate("text", x = 0.1,  y = 120000, label = "2021 baseline",
           hjust = 0, size = 3.0, color = "grey50") +
  annotate("text", x = 2.1,  y = 120000, label = "Post threshold",
           hjust = 0, size = 3.0, color = "grey50") +
  annotate("text", x = current_gap + 0.1, y = 120000,
           label = paste0("Current gap (", current_gap, "pp)"),
           hjust = 0, size = 3.0, color = "grey30") +
  
  # Segment labels annotating key rate-sensitivity findings
  annotate("text", x = 1.5, y = 1000000,
           label = paste0("Move-up:\nHighly vulnerable to rate hikes\n(",
                          squeeze_mult, "× Squeeze Multiplier)"),
           color = "#ED7D31", fontface = "bold", hjust = 0, size = 3.5, lineheight = 0.9) +
  annotate("text", x = 1.5, y = 400000, label = "Entry-Level:\nResilient to rate shocks",
           color = "#70AD47", fontface = "bold", hjust = 0, size = 3.5, lineheight = 0.9) +

scale_color_manual(
  values = c("entry" = "#70AD47", "move_up" = "#ED7D31", "luxury" = "#4472C4"),
  labels = c(entry_label, midlux_label, luxury_label)
) +
  scale_fill_manual(
    values = c("entry" = "#70AD47", "move_up" = "#ED7D31", "luxury" = "#4472C4"),
    guide  = "none"
  ) +
  scale_x_continuous(limits = c(-0.3, 5.4), breaks = 0:4) +
  scale_y_continuous(
    labels = dollar_format(scale = 0.001, suffix = "K"),
    breaks = c(100000, 250000, 500000, 750000, 1000000, 1500000, 2000000)
  ) +
  labs(
    title    = "The Rate Penalty: Move-Up Market Bears the Brunt of Rate Hikes",
    subtitle = paste0("Entry-level buyers remain insulated, while move-up properties face severe price degradation | N = ",
                      n_sdf, " transactions"),
    x        = paste0("Rate Lock-In Gap (PP Above ", RATE_BASELINE, "% Baseline)"),
    y        = "Predicted Rate Penalty ($)",
    color   = "Price segment",
    caption = paste0(
      "Source: STATS Indiana SDF deed records.\n",
      "N = ", n_sdf, " transactions after regression filters ",
      "(matched to FRED rate, sale price >", dollar(MIN_PRICE), ").\n",
      "Luxury slope (", slope_luxury, "%/pp) reflects thin market volatility, ",
      "not behavioral rate sensitivity\n",
      "(~", luxury_annual, " transactions/county/year). ",
      "Peak observed gap of ", peak_gap_pp, "pp = ", peak_rate_pct,
      "% mortgage rate in the panel window.\n",
      "Dashed line at ", current_gap, "pp = current rate gap at time of study."
    )
  ) +
  theme_minimal(base_size = 13) +
  theme(
    legend.position  = "bottom",
    plot.title       = element_text(face = "bold", size = 14),
    plot.subtitle    = element_text(color = "grey40", size = 11),
    plot.caption     = element_text(color = "grey50", size = 9,
                                    hjust = 0, margin = margin(t = 8)),
    panel.grid.minor = element_blank(),
    plot.margin      = margin(5, 50, 5, 5, "pt")
  )

ggsave(here::here("outputs/figures/fig12_marginal_effects.png"), width = 10, height = 5.5, dpi = 300)
ggsave(here::here("outputs/figures/fig12_marginal_effects.pdf"), width = 10, height = 5.5)
cat("Saved fig12_marginal_effects.png\n")

# ══════════════════════════════════════════════════════════════════════════════
# TABLE 8 — Rate sensitivity by price segment
# ══════════════════════════════════════════════════════════════════════════════

# Log-scale slopes used for the per-rate forecast scenarios in forecast_tbl
# below. Exp-scale percent slopes (slope_entry / slope_midlux / slope_luxury)
# and the squeeze multiplier (squeeze_mult) are already defined at the fig12
# step and reused here without recomputation.
entry_slope  <- coef_price["rate_gap"]
midlux_slope <- coef_price["rate_gap"] +
  coef_price["rate_gap:price_segmentmove_up"]

cat("Entry slope:          ", slope_entry,  "%/pp\n")
cat("Move-up slope:        ", slope_midlux, "%/pp\n")
cat("Squeeze multiplier:   ", squeeze_mult, "x\n")

forecast_tbl <- tibble(
  ` `                      = c(entry_label,
                               midlux_label,
                               "Squeeze multiplier"),
  `Rate sensitivity`       = c(paste0(slope_entry,  "%/pp"),
                               paste0(slope_midlux, "%/pp"),
                               paste0(squeeze_mult, "\u00d7")),
  !!paste0("At current gap (", current_gap, "pp)") :=
    c(paste0(round((exp(entry_slope  * current_gap) - 1) * 100, 1), "%"),
      paste0(round((exp(midlux_slope * current_gap) - 1) * 100, 1), "%"),
      "\u2014"),
  `If gap widens to 4pp`   = c(paste0(round((exp(entry_slope  * 4.0) - 1) * 100, 1), "%"),
                               paste0(round((exp(midlux_slope * 4.0) - 1) * 100, 1), "%"),
                               "\u2014")
)

datasummary_df(
  forecast_tbl,
  title = "Rate Sensitivity by Price Segment — Derived From M_Price_Interact Model",
  notes = paste0(
    "Slopes from m_price_interact HC1 robust SEs, N = ", n_sdf, " transactions. ",
    "Squeeze multiplier = move-up slope / entry slope = constant across all rate environments. ",
    "Current gap based on latest panel observation (", current_rate,
    "% mortgage rate vs ", RATE_BASELINE, "% baseline). ",
    "Adj R\u00b2 = ", round(summary(m_price_interact)$adj.r.squared, 3), "."
  ),
  output = here::here("outputs/tables/table8_rate_sensitivity.html")
)

webshot2::webshot(
  url   = paste0("file://", here::here("outputs/tables/table8_rate_sensitivity.html")),
  file  = here::here("outputs/tables/table8_rate_sensitivity.png"),
  delay = 2, zoom = 1.5, vwidth = 900
)
file.remove(here::here("outputs/tables/table8_rate_sensitivity.html"))
cat("Saved outputs/tables/table8_rate_sensitivity.png\n")

# ══════════════════════════════════════════════════════════════════════════════
# FIGURE 13 — Geospatial Map: The Indy Squeeze (Zip-Level)
# ZIP-level price-to-income stress ratio mapped using national ZCTA shapefiles
# ══════════════════════════════════════════════════════════════════════════════

options(tigris_use_cache = TRUE)

# 1. PREP THE SDF PRICE DATA
# ---------------------------------------------------------
# guess_max = 200000 prevents the parsing warnings by scanning all rows first
zip_prices <- read_csv(here::here("data/processed/sdf_indiana.csv"),
                       guess_max = 200000) %>%
  mutate(zip_code = str_pad(as.character(zip_code), width = 5, pad = "0")) %>%
  group_by(zip_code) %>%
  summarise(
    median_sale_price  = median(sale_price, na.rm = TRUE),
    total_transactions = n(),
    .groups = "drop"
  )

# 2. PREP THE INCOME DATA
# ---------------------------------------------------------
zip_income <- read_csv(here::here("data/processed/hhi_zcta.csv"),
                       show_col_types = FALSE) %>%
  mutate(zip_code = str_pad(as.character(zip_code), width = 5, pad = "0"))

# 3. COMBINE AND CALCULATE STRESS RATIO
# ---------------------------------------------------------
df_map_final <- zip_prices %>%
  inner_join(zip_income, by = "zip_code") %>%
  mutate(stress_ratio = median_sale_price / zcta_hhi) %>%
  # Filter strictly for the Indy Metro (ZIP prefixes 460, 461, 462)
  filter(str_detect(zip_code, "^(460|461|462)"))

# 4. FETCH CENSUS ZCTA SHAPEFILES
# ---------------------------------------------------------
# 2020 is the only vintage with a national cartographic boundary ZCTA file.
us_zctas <- zctas(year = 2020, cb = TRUE)

# 5. JOIN AND ANNOTATE
# ---------------------------------------------------------
# inner_join to df_map_final implicitly filters to Indianapolis metro ZIPs
map_data <- us_zctas %>%
  inner_join(df_map_final, by = c("GEOID20" = "zip_code"))

highlight_zips <- map_data %>%
  filter(GEOID20 %in% c(
    map_data$GEOID20[which.min(map_data$stress_ratio)],
    map_data$GEOID20[which.max(map_data$stress_ratio)]
  )) %>%
  mutate(centroid = st_centroid(geometry))

# 5a. COUNTY BOUNDARIES — five-county study area
# cb = TRUE uses a simplified cartographic boundary file (smaller download)
study_fips <- c("18097", "18057", "18011", "18063", "18081")
study_counties <- counties(state = "IN", cb = TRUE, progress_bar = FALSE) %>%
  filter(GEOID %in% study_fips) %>%
  st_transform(st_crs(map_data))

# 5b. CITY POINT MARKERS — coordinates from housing_map_app.py CITY_POINTS
city_points <- tibble(
  city = c("Indianapolis", "Carmel", "Fishers", "Noblesville", "Zionsville",
           "Whitestown", "Avon", "Brownsburg", "Greenwood", "Plainfield",
           "Mooresville", "Franklin", "Greenfield"),
  lat  = c(39.7684, 39.9784, 39.9567, 40.0456, 39.9506,
           39.9914, 39.7626, 39.8437, 39.6137, 39.7042,
           39.6128, 39.4806, 39.7870),
  lon  = c(-86.1581, -86.1180, -85.9669, -85.9669, -86.2661,
           -86.3522, -86.3994, -86.3969, -86.1066, -86.3994,
           -86.3730, -86.0558, -85.7697)
) %>%
  st_as_sf(coords = c("lon", "lat"), crs = 4326) %>%
  st_transform(st_crs(map_data))

# 6. BUILD THE MAP
# ---------------------------------------------------------
indy_squeeze_map <- ggplot(data = map_data) +
  geom_sf(aes(fill = stress_ratio), color = "white", size = 0.1) +
  geom_sf(data = study_counties, fill = NA, color = "#333333", linewidth = 0.6) +
  geom_sf(data = city_points, size = 2, shape = 21,
          fill = "#333333", color = "white", stroke = 0.5) +
  geom_text_repel(
    data        = city_points,
    aes(label   = city, geometry = geometry),
    stat        = "sf_coordinates",
    size        = 2.8,
    family      = "sans",
    color       = "#111111",
    bg.color    = "white",
    bg.r        = 0.15,
    box.padding = 0.3,
    min.segment.length = 0.3,
    segment.color = "grey50",
    segment.size  = 0.3,
    max.overlaps  = 20
  ) +
  scale_fill_gradientn(
    colors = c("#4472C4", "#F2F2F2", "#ED7D31", "#C00000"),
    values = rescale(c(1, 3, 4.5, 6)),
    name = "Affordability Stress Ratio\n(Price / Income)",
    limits = c(1, 6),
    breaks = c(2, 3, 4, 5, 6),
    labels = c("2.0x", "3.0x", "4.0x", "5.0x", "6.0x+")
  ) +
  geom_label_repel(
    data = highlight_zips,
    aes(geometry = centroid,
        label = paste0("Zip: ", GEOID20, "\nRatio: ", round(stress_ratio, 1), "x")),
    stat = "sf_coordinates",
    size = 3.5, fontface = "bold", fill = alpha("white", 0.9),
    box.padding = 0.8, segment.color = "grey30"
  ) +
  labs(
    title    = "The Indy Squeeze: Housing Vulnerability by Zip Code",
    subtitle = paste0("Calculated using the full population of STATS Indiana SDF Transactions",
                      " (", year_range_label,
                      ").\nAreas in dark red face the most severe price-to-income",
                      " decoupling."),
    caption  = "Source: STATS Indiana SDF & U.S. Census Bureau (ZCTA HHI)."
  ) +
  theme_void(base_size = 14) +
  theme(
    plot.title    = element_text(face = "bold", size = 18, margin = margin(b = 5)),
    plot.subtitle = element_text(color = "grey30", size = 11, margin = margin(b = 20)),
    legend.position = "right",
    plot.margin   = margin(20, 20, 20, 20, "pt")
  )

# 7. EXPORT
# ---------------------------------------------------------
ggsave(here::here("outputs/figures/fig13_zip_squeeze_map.png"),
       plot = indy_squeeze_map, width = 10, height = 8, dpi = 300, bg = "white")
ggsave(here::here("outputs/figures/fig13_zip_squeeze_map.pdf"),
       plot = indy_squeeze_map, width = 10, height = 8)


# ══════════════════════════════════════════════════════════════════════════════
# SAVE MODELS FOR REPRODUCIBILITY
# ══════════════════════════════════════════════════════════════════════════════

saveRDS(m_price_interact,    here::here("data/processed/m_price_interact.rds"))
saveRDS(m_did_price_triple,  here::here("data/processed/m_did_price_triple.rds"))
saveRDS(m_did_volume_triple, here::here("data/processed/m_did_volume_triple.rds"))

cat("Figures: outputs/figures/fig11_histogram_price.png/.pdf,",
    "fig12_marginal_effects.png/.pdf, fig13_zip_squeeze_map.png/.pdf\n")
cat("Tables:  outputs/tables/table5_dom_models.png, table6_price_models.png,",
    "table7_did_models.png, table2_hypothesis_test.png,",
    "table3_correlation.png, table4_standard_error.png,",
    "table8_rate_sensitivity.png\n")
cat("Models:  data/processed/m_price_interact.rds, m_did_price_triple.rds,",
    "m_did_volume_triple.rds\n")
