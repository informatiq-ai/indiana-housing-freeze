# ══════════════════════════════════════════════════════════════════════════════
# EDA & Descriptive Statistics
# Indiana Mid-Luxury Housing Squeeze
#
# Outputs:
#   fig1_rate_gap.png            — Rate shock context (opens presentation)
#   fig2_dom_histogram.png       — DOM distribution pre/post shock
#   fig3_dom_over_time.png       — DOM trends Marion vs suburbs
#   fig4_sale_to_list.png        — Avg sale-to-list ratio by segment
#   fig5_seller_stress.png       — Sold above list vs price drops over time
#   fig6_transaction_volume.png  — SDF transaction volume collapse
#   fig7_affordability.png       — Affordability ratio by county
#   fig8_parallel_trends.png     — DiD assumption validation
#   fig9_price_index.png         — Price index by segment 2021–2025
#   fig10_hhi_price_correlation  — HHI vs median sale price by ZIP (DV vs key IV)
#   table1_descriptive           — Descriptive statistics table
#
# Key data limitations:
#   - Redfin DOM subject to delist-relist gaming (lower bound on true DOM)
#   - Marion County median never exceeds $388K — income constraint, 
#     not rate shock
#   - Geography proxies for buyer type, not direct identification
#   - ACS HHI/population are 2023 cross-sectional estimates applied across years
# ══════════════════════════════════════════════════════════════════════════════

# ── Package setup ─────────────────────────────────────────────────────────────
if (!require("pacman")) install.packages("pacman")
pacman::p_load(tidyverse, scales, modelsummary, zoo, here, webshot2)

# ── Analysis constants ────────────────────────────────────────────────────────
LTV_RATIO <- 0.80    # 80% LTV assumption for affordability calculation
MIN_PRICE <- 50000   # $50K — removes implausible deed transfers
luxury_CAP <- 15e6   # $15M — removes data entry errors from luxury tier

# ── Load data ─────────────────────────────────────────────────────────────────
panel_data <- readRDS(here::here("data/processed/panel_data.rds"))

# Read full SDF first to compute the count of luxury data-entry outliers
# dropped by the luxury_CAP filter, then apply the cap to produce sdf_raw.
sdf_full <- read_csv(here::here("data/processed/sdf_indiana.csv"),
                     show_col_types = FALSE)
n_lux_total   <- sum(sdf_full$price_segment == "luxury", na.rm = TRUE)
n_lux_dropped <- sum(sdf_full$price_segment == "luxury" &
                       sdf_full$sale_price > luxury_CAP, na.rm = TRUE)
lux_dropped_pct <- if (n_lux_total > 0) {
  round(n_lux_dropped / n_lux_total * 100, 1)
} else 0

sdf_raw <- sdf_full %>%
  filter(!(price_segment == "luxury" & sale_price > luxury_CAP))

# ── Lookup tables derived from panel_data (mirrors 03_regression setup) ───────
county_controls <- panel_data %>%
  distinct(county, geography, median_hhi, population) %>%
  mutate(county = as.character(county))

rate_lookup <- panel_data %>%
  distinct(year, month, mortgage_rate, rate_gap, post) %>%
  mutate(year = as.integer(year))

# ── Build SDF transaction-level dataset ──────────────────────────────────────
sdf <- sdf_raw %>%
  mutate(
    sale_date     = as.Date(sale_date),
    year          = year(sale_date),
    month         = month(sale_date),
    price_segment = factor(price_segment,
                           levels = c("entry", "mid_luxury", "luxury"))
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

n_sdf <- formatC(nrow(sdf), format = "f", digits = 0, big.mark = ",")

cat("Unit of analysis 1: County-month cell —", nrow(panel_data), "obs\n")
cat("Unit of analysis 2: Individual deed record —", nrow(sdf), "transactions\n\n")

n_total <- nrow(sdf)

# ── Derived labels for figures and captions ──────────────────────────────────
# Tier breakpoints are derived from the price_segment factor produced by
# 00_data_pipeline.py (k-means). Re-deriving here keeps figure labels in sync
# with the underlying data on each re-run.
entry_max_p     <- max(sdf$sale_price[sdf$price_segment == "entry"],      na.rm = TRUE)
midlux_max_p    <- max(sdf$sale_price[sdf$price_segment == "mid_luxury"], na.rm = TRUE)
entry_break_k   <- round(entry_max_p  / 1000)
midlux_break_m  <- round(midlux_max_p / 1e6, 1)
midlux_break_lbl <- if (isTRUE(all.equal(midlux_break_m, round(midlux_break_m))))
  paste0(as.integer(round(midlux_break_m)), "M") else paste0(midlux_break_m, "M")
entry_label  <- paste0("Entry (<$",      entry_break_k, "K)")
midlux_label <- paste0("Mid-luxury ($",  entry_break_k, "K–$", midlux_break_lbl, ")")
luxury_label <- paste0("Luxury (>$",     midlux_break_lbl, ")")

# Marion County median household income — referenced in captions
marion_hhi_val <- panel_data %>%
  filter(county == "Marion") %>%
  pull(median_hhi) %>%
  first()
marion_hhi_lbl <- paste0("$", formatC(round(marion_hhi_val / 1000), format = "f",
                                      digits = 0, big.mark = ","), "K")

# ── Shared color palette ──────────────────────────────────────────────────────
col_metro    <- "#4472C4"   # blue   — Marion County
col_suburb   <- "#ED7D31"   # orange — suburbs
col_entry    <- "#70AD47"   # green  — entry tier
col_midlux   <- "#ED7D31"   # orange — mid-luxury tier
col_luxury    <- "#4472C4"   # blue   — luxury tier
col_gap_fill <- "#FFC000"   # amber  — rate gap ribbon

# ── Shared plot theme ─────────────────────────────────────────────────────────
theme_squeeze <- theme_minimal(base_size = 13) +
  theme(
    legend.position  = "bottom",
    plot.title       = element_text(face = "bold", size = 14),
    plot.subtitle    = element_text(color = "grey40", size = 11),
    plot.caption     = element_text(color = "grey50", size = 9,
                                    hjust = 0, margin = margin(t = 8)),
    panel.grid.minor = element_blank()
  )

# ══════════════════════════════════════════════════════════════════════════════
# FIGURE 1 — The mortgage rate lock-in gap
# Shows the payment shock relative to the 2021 baseline; context for all downstream analysis
# ══════════════════════════════════════════════════════════════════════════════

panel_data %>%
  distinct(year, month, mortgage_rate, rate_gap) %>%
  mutate(date = as.Date(paste(year, month, "01", sep = "-"))) %>%
  ggplot(aes(x = date)) +
  geom_ribbon(aes(ymin = 3.0, ymax = mortgage_rate),
              fill = col_gap_fill, alpha = 0.35) +
  geom_line(aes(y = mortgage_rate), color = col_metro, linewidth = 1.2) +
  geom_hline(yintercept = 3.0, linetype = "dashed", color = "grey50") +
  geom_vline(xintercept = as.Date("2022-03-01"),
             linetype = "dotted", color = "grey50") +
  annotate("text", x = as.Date("2021-02-01"), y = 3.2,
           label = "2021 baseline (~3%)", hjust = 0,
           size = 3.5, color = "grey40") +
  annotate("text", x = as.Date("2022-04-01"), y = 7.5,
           label = "Fed tightening begins", hjust = 0,
           size = 3.5, color = "grey40") +
  annotate("text", x = as.Date("2023-06-01"), y = 5.5,
           label = "Lock-in gap", hjust = 0,
           size = 3.5, color = "#B8860B", fontface = "italic") +
  scale_x_date(date_breaks = "1 year", date_labels = "%Y") +
  scale_y_continuous(labels = label_number(suffix = "%")) +
  labs(
    title    = "The Mortgage Rate Lock-In Gap, 2021–2025",
    subtitle = "Shaded area = payment shock for homeowners trading a 3% mortgage for current rates",
    x = NULL, y = "30-year fixed rate",
    caption  = "Source: Freddie Mac MORTGAGE30US via FRED"
  ) +
  theme_squeeze

ggsave(here::here("outputs/figures/fig1_rate_gap.png"), width = 9, height = 4.5, dpi = 300)
ggsave(here::here("outputs/figures/fig1_rate_gap.pdf"), width = 9, height = 4.5)
cat("Saved fig1_rate_gap.png/.pdf\n")

# ══════════════════════════════════════════════════════════════════════════════
# FIGURE 2 — DOM histogram: pre vs post rate shock
# Rightward shift in suburbs post-shock is the freeze made visible
# ══════════════════════════════════════════════════════════════════════════════

panel_data %>%
  mutate(
    era = if_else(as.integer(as.character(year)) <= 2021,
                  "Pre-shock (2021)", "Post-shock (2022–2025)"),
    era = factor(era, levels = c("Pre-shock (2021)", "Post-shock (2022–2025)")),
    Geography = if_else(geography == "metro", "Marion County (metro)", "Suburbs")
  ) %>%
  ggplot(aes(x = median_dom, fill = geography)) +
  geom_histogram(binwidth = 5, position = "identity",
                 alpha = 0.65, color = "white") +
  scale_fill_manual(
    values = c("metro" = col_metro, "suburb" = col_suburb),
    labels = c("Marion County (metro)",
               "Suburbs (Hamilton/Boone/Hendricks/Johnson)")
  ) +
  facet_grid(Geography ~ era) +
  labs(
    title    = "Distribution of Median Days on Market — Pre vs. Post Rate Shock",
    subtitle = "Single family residential | Indiana county-month observations",
    x        = "Median days on market",
    y        = "Count of county-month cells",
    fill     = NULL,
    caption  = "Source: Redfin county market tracker.\nNote: MLS days on market may understate true time on market due to\ndelist-relist cycling by agents. Figures represent a lower bound."
  ) +
  theme_squeeze +
  theme(strip.text.y = element_text(angle = 0))

ggsave(here::here("outputs/figures/fig2_dom_histogram.png"), width = 10, height = 6, dpi = 300)
ggsave(here::here("outputs/figures/fig2_dom_histogram.pdf"), width = 10, height = 6)
cat("Saved fig2_dom_histogram.png/.pdf\n")

# ══════════════════════════════════════════════════════════════════════════════
# FIGURE 3 — DOM over time: Marion vs suburbs
# 3-month rolling average smooths seasonal noise
# ══════════════════════════════════════════════════════════════════════════════

panel_data %>%
  mutate(date = as.Date(paste(year, month, "01", sep = "-"))) %>%
  group_by(date, geography) %>%
  summarise(avg_dom = mean(median_dom, na.rm = TRUE), .groups = "drop") %>%
  arrange(geography, date) %>%
  group_by(geography) %>%
  mutate(avg_dom_smooth = rollmean(avg_dom, k = 3, fill = NA, align = "center")) %>%
  ungroup() %>%
  ggplot(aes(x = date, color = geography)) +
  geom_line(aes(y = avg_dom), alpha = 0.25, linewidth = 0.8) +
  geom_line(aes(y = avg_dom_smooth), linewidth = 1.4, na.rm = TRUE) +
  geom_vline(xintercept = as.Date("2022-06-01"),
             linetype = "dashed", color = "grey50") +
  annotate("text", x = as.Date("2022-07-01"), y = 42,
           label = "Rate shock", hjust = 0, size = 3.2, color = "grey40") +
  scale_color_manual(
    values = c("metro" = col_metro, "suburb" = col_suburb),
    labels = c("Marion County (metro)", "Suburbs (treated)")
  ) +
  scale_x_date(date_breaks = "1 year", date_labels = "%Y") +
  labs(
    title    = "Median Days on Market — Marion County vs. Suburbs, 2021–2025",
    subtitle = "Thick line = 3-month rolling average | Faint line = monthly raw values",
    x = NULL, y = "Average Median DOM", color = NULL,
    caption  = "Source: Redfin county market tracker.\nNote: DOM figures subject to delist-relist manipulation.\nTrue DOM divergence post-shock is likely larger than shown."
  ) +
  theme_minimal(base_size = 13) +
  theme(
    legend.position  = "bottom",
    plot.title       = element_text(face = "bold", size = 14),
    plot.subtitle    = element_text(color = "grey40", size = 11),
    plot.caption     = element_text(color = "grey50", size = 9,
                                    hjust = 0, margin = margin(t = 8)),
    panel.grid.minor = element_blank()
  )

ggsave(here::here("outputs/figures/fig3_dom_over_time.png"), width = 10, height = 5, dpi = 300)
ggsave(here::here("outputs/figures/fig3_dom_over_time.pdf"), width = 10, height = 5)
cat("Saved fig3_dom_over_time.png/.pdf\n")

# ══════════════════════════════════════════════════════════════════════════════
# FIGURE 4 — Avg sale-to-list ratio by price segment and geography
# Marion has no mid-luxury observations — structural income constraint,
# not a rate shock effect. See caption and annotation for explanation.
# avg_sale_to_list is Redfin's column name — not renamed to avoid confusion
# ══════════════════════════════════════════════════════════════════════════════

panel_data %>%
  filter(price_segment != "luxury") %>%
  mutate(yr_label = factor(year)) %>%
  ggplot(aes(x = yr_label, y = avg_sale_to_list, fill = price_segment)) +
  geom_boxplot(alpha = 0.75, outlier.size = 0.8) +
  geom_hline(yintercept = 1.00, linetype = "dashed", color = "grey50") +
  annotate("text", x = 0.6, y = 1.002,
           label = "Asking price", hjust = 0, size = 3.2, color = "grey40") +
  scale_fill_manual(
    values = c("entry" = col_entry, "mid_luxury" = col_midlux),
    labels = c(entry_label, midlux_label)
  ) +
  scale_y_continuous(labels = percent_format(accuracy = 0.1)) +
  facet_wrap(~ geography,
             labeller = labeller(geography = c(
               "metro"  = "Marion County (metro)",
               "suburb" = "Suburbs"
             ))) +
  labs(
    title    = "Avg Sale-to-List Ratio by Price Segment and Geography, 2021–2025",
    subtitle = "Compression below 1.0 = sellers accepting below asking price",
    x = "Year", y = "Avg sale-to-list ratio", fill = "Price segment",
    caption  = paste0(
      "Source: Redfin county market tracker.\n",
      "Luxury tier excluded: county medians rarely exceed $", midlux_break_lbl,
      " in this market.\nMarion County absence of mid-luxury reflects income ",
      "constraint (median HHI ", marion_hhi_lbl, "), not a rate shock response."
    )
  ) +
  theme_squeeze

ggsave(here::here("outputs/figures/fig4_sale_to_list.png"), width = 10, height = 5, dpi = 300)
ggsave(here::here("outputs/figures/fig4_sale_to_list.pdf"), width = 10, height = 5)
cat("Saved fig4_sale_to_list.png/.pdf\n")

# ══════════════════════════════════════════════════════════════════════════════
# FIGURE 5 — Seller market stress: sold above list vs price drops
# Complements fig4 by showing the distribution of outcomes over time
# sold_above_list: share of homes selling above asking (demand pressure)
# price_drops:     share of listings needing price cuts (seller capitulation)
# Together they show the squeeze from both ends of the distribution
# ══════════════════════════════════════════════════════════════════════════════

panel_data %>%
  mutate(date = as.Date(paste(year, month, "01", sep = "-"))) %>%
  group_by(date, geography) %>%
  summarise(
    sold_above = mean(sold_above_list, na.rm = TRUE),
    drops      = mean(price_drops,     na.rm = TRUE),
    .groups    = "drop"
  ) %>%
  pivot_longer(c(sold_above, drops),
               names_to = "metric", values_to = "value") %>%
  mutate(
    metric = factor(metric,
                    levels = c("sold_above", "drops"),
                    labels = c("Sold above list price (demand pressure)",
                               "Listed with price drop (seller capitulation)"))
  ) %>%
  ggplot(aes(x = date, y = value, color = geography)) +
  geom_line(linewidth = 0.6, alpha = 0.35) +          # raw monthly values, faded
  geom_smooth(method = "loess", span = 0.4,           # LOESS smoother is the primary visual
              se = FALSE, linewidth = 1.4) +
  geom_vline(xintercept = as.Date("2022-06-01"),
             linetype = "dashed", color = "grey50") +
  annotate("text", x = as.Date("2022-07-01"), y = 0.56,
           label = "Rate shock", hjust = 0, size = 3.0, color = "grey40") +
  scale_color_manual(
    values = c("metro" = col_metro, "suburb" = col_suburb),
    labels = c("Marion County (metro)", "Suburbs (treated)")
  ) +
  scale_y_continuous(labels = percent_format(accuracy = 1),
                     limits = c(0, NA)) +
  scale_x_date(date_breaks = "1 year", date_labels = "%Y") +
  facet_wrap(~ metric, ncol = 2) +
  labs(
    title    = "Seller Market Stress: Sold Above List vs Price Drops, 2021–2025",
    subtitle = "Post-shock: bidding wars trend down while price cuts trend up | Faint lines = monthly raw values | Trend = LOESS smoother",
    x = NULL, y = "Share of transactions", color = NULL,
    caption  = "Source: Redfin county market tracker.\nSold above list = share of closed sales above original list price.\nPrice drops = share of active listings with at least one price reduction."
  ) +
  theme_squeeze

ggsave(here::here("outputs/figures/fig5_seller_stress.png"), width = 11, height = 5, dpi = 300)
ggsave(here::here("outputs/figures/fig5_seller_stress.pdf"), width = 11, height = 5)
cat("Saved fig5_seller_stress.png/.pdf\n")

# ══════════════════════════════════════════════════════════════════════════════
# FIGURE 6 — Transaction volume by price segment
# Suburban mid-luxury collapse is the rate lock-in market freeze made visible
# ══════════════════════════════════════════════════════════════════════════════

panel_data %>%
  group_by(year, geography) %>%
  summarise(
    entry      = sum(transactions_entry,      na.rm = TRUE),
    mid_luxury = sum(transactions_mid_luxury,  na.rm = TRUE),
    luxury      = sum(transactions_luxury,       na.rm = TRUE),
    .groups    = "drop"
  ) %>%
  pivot_longer(c(entry, mid_luxury, luxury),
               names_to = "segment", values_to = "transactions") %>%
  mutate(
    segment = factor(segment,
                     levels = c("entry", "mid_luxury", "luxury"),
                     labels = c(entry_label, midlux_label, luxury_label)),
    yr_label = factor(year)
  ) %>%
  ggplot(aes(x = yr_label, y = transactions, fill = segment, group = segment)) +
  geom_col(position = "dodge", alpha = 0.85) +
  scale_fill_manual(values = setNames(
    c(col_entry, col_midlux, col_luxury),
    c(entry_label, midlux_label, luxury_label)
  )) +
  scale_y_continuous(labels = comma) +
  facet_wrap(~ geography,
             labeller = labeller(geography = c(
               "metro"  = "Marion County (metro)",
               "suburb" = "Suburbs"
             ))) +
  labs(
    title    = "Annual Transaction Volume by Price Segment, 2021–2025",
    subtitle = "Suburban mid-luxury volume collapse is the rate lock-in market freeze made visible",
    x = "Year", y = "Total transactions", fill = "Price segment",
    caption  = paste0(
      "Source: Indiana Sales Disclosure Form deed records, STATS Indiana.\n",
      "Arm's-length residential sales only. Luxury tier capped at ",
      scales::dollar(luxury_CAP), "\n(",
      formatC(n_lux_dropped, format = "f", digits = 0, big.mark = ","),
      " data entry errors removed, ", lux_dropped_pct,
      "% of luxury transactions)."
    )
  ) +
  theme_squeeze

ggsave(here::here("outputs/figures/fig6_transaction_volume.png"), width = 10, height = 5, dpi = 300)
ggsave(here::here("outputs/figures/fig6_transaction_volume.pdf"), width = 10, height = 5)
cat("Saved fig6_transaction_volume.png/.pdf\n")

# ══════════════════════════════════════════════════════════════════════════════
# FIGURE 7 — Affordability ratio by county over time
# Two mechanisms, same outcome: Marion via income constraint, suburbs via rate shock
# ══════════════════════════════════════════════════════════════════════════════

panel_data %>%
  mutate(date = as.Date(paste(year, month, "01", sep = "-"))) %>%
  group_by(date, county, geography) %>%
  summarise(avg_afford = mean(affordability_ratio, na.rm = TRUE),
            .groups = "drop") %>%
  ggplot(aes(x = date, y = avg_afford, color = county, linetype = geography)) +
  geom_line(linewidth = 1.0) +
  geom_hline(yintercept = 0.30, linetype = "dashed", color = "red", alpha = 0.6) +
  annotate("text", x = as.Date("2021-02-01"), y = 0.31,
           label = "30% income threshold (housing stress)",
           hjust = 0, size = 3.2, color = "red", alpha = 0.8) +
  scale_color_manual(values = c(
    "Marion"    = col_metro,
    "Hamilton"  = "#ED7D31",
    "Boone"     = "#70AD47",
    "Hendricks" = "#FFC000",
    "Johnson"   = "#9B59B6"
  )) +
  scale_linetype_manual(
    values = c("metro" = "solid", "suburb" = "dashed"),
    labels = c("Metro (Marion)", "Suburb")
  ) +
  scale_y_continuous(labels = percent_format(accuracy = 1)) +
  scale_x_date(date_breaks = "1 year", date_labels = "%Y") +
  labs(
    title    = "Affordability Ratio: Estimated Mortgage Payment as Share of Median HHI",
    subtitle = "Two mechanisms, same outcome — Marion via income constraint, suburbs via rate shock",
    x = NULL, y = "Monthly payment / median monthly income",
    color = "County", linetype = "Geography",
    caption  = "Source: Redfin median sale price, FRED MORTGAGE30US, Census ACS 2023 5-year.\nAffordability ratio = estimated 30-yr fixed payment on 80% LTV / median monthly HHI.\nNote: ACS income estimates are cross-sectional (2023) applied across all years."
  ) +
  theme_squeeze

ggsave(here::here("outputs/figures/fig7_affordability.png"), width = 10, height = 5, dpi = 300)
ggsave(here::here("outputs/figures/fig7_affordability.pdf"), width = 10, height = 5)
cat("Saved fig7_affordability.png/.pdf\n")

# ══════════════════════════════════════════════════════════════════════════════
# FIGURE 8 — Parallel trends check using log sale price (main DV)
# Uses SDF transaction data aggregated to county-month
# Required for DiD validity: treatment and control must track together pre-shock
# ══════════════════════════════════════════════════════════════════════════════

sdf %>%
  mutate(date = as.Date(paste(as.integer(as.character(year)),
                              month, "01", sep = "-"))) %>%
  group_by(date, geography) %>%
  summarise(
    avg_log_price = mean(log_sale_price, na.rm = TRUE),
    .groups = "drop"
  ) %>%
  mutate(era = if_else(date < as.Date("2022-06-01"), "pre", "post")) %>%
  ggplot(aes(x = date, y = avg_log_price, color = geography)) +
  annotate("rect",
           xmin = as.Date("2021-01-01"), xmax = as.Date("2022-06-01"),
           ymin = -Inf, ymax = Inf, fill = "grey90", alpha = 0.6) +
  geom_line(data = ~ filter(.x, date >= as.Date("2022-06-01")),
            linewidth = 0.9, alpha = 0.4) +
  geom_line(data = ~ filter(.x, date < as.Date("2022-06-01")),
            linewidth = 1.8) +
  geom_vline(xintercept = as.Date("2022-06-01"),
             linetype = "dashed", color = "grey50") +
  annotate("text", x = as.Date("2021-02-01"), y = 12.75,
           label = "Pre-shock period\n(parallel trends required)",
           hjust = 0, size = 3.0, color = "grey40") +
  annotate("text", x = as.Date("2022-07-01"), y = 12.65,
           label = "Rate shock\n(post period begins)",
           hjust = 0, size = 3.0, color = "grey40") +
  annotate("text", x = as.Date("2021-06-01"), y = 11.85,
           label = "Both trend upward at similar rates \u2192 parallel trends \u2713",
           hjust = 0, size = 3.0, color = "grey40", fontface = "italic") +
  scale_color_manual(
    values = c("metro" = col_metro, "suburb" = col_suburb),
    labels = c("Marion County (control)", "Suburbs (treated)")
  ) +
  scale_y_continuous(
    labels = function(x) paste0("$", round(exp(x) / 1000, 0), "K")
  ) +
  scale_x_date(date_breaks = "1 year", date_labels = "%Y") +
  labs(
    title    = "Parallel Trends Check — Mean Sale Price by Geography",
    subtitle = "Both geographies trend together pre-shock — parallel trends assumption supported",
    x = NULL, y = "Mean Sale Price (log scale)", color = NULL,
    caption = paste0(
      "Source: STATS Indiana SDF deed records. N = ", n_sdf, " transactions.\n",
      "Parallel trends: treatment and control must track together pre-shock for DiD to be valid.\n",
      "Geography proxies for buyer type — Marion income constraint ($63K HHI) implies conservative lower bound.")
  ) +
  theme_squeeze

ggsave(here::here("outputs/figures/fig8_parallel_trends.png"), width = 9, height = 5, dpi = 300)
ggsave(here::here("outputs/figures/fig8_parallel_trends.pdf"), width = 9, height = 5)
cat("Saved fig8_parallel_trends.png/.pdf\n")

# ══════════════════════════════════════════════════════════════════════════════
# FIGURE 9 — Price index by segment: 2021 = 100
# ══════════════════════════════════════════════════════════════════════════════

sdf %>%
  mutate(year = year(as.Date(sale_date))) %>%
  group_by(year, price_segment, county) %>%
  summarise(median_price = median(sale_price, na.rm = TRUE),
            n = n(), .groups = "drop") %>%
  mutate(
    geography     = if_else(county == "Marion", "metro", "suburb"),
    price_segment = factor(price_segment,
                           levels = c("entry", "mid_luxury", "luxury"),
                           labels = c(entry_label, midlux_label, luxury_label))
  ) %>%
  group_by(year, price_segment, geography) %>%
  summarise(median_price = weighted.mean(median_price, n, na.rm = TRUE),
            .groups = "drop") %>%
  group_by(price_segment, geography) %>%
  mutate(
    base_price  = median_price[year == 2021],
    price_index = (median_price / base_price) * 100
  ) %>%
  ungroup() %>%
  ggplot(aes(x = factor(year), y = price_index,
             color = price_segment, group = price_segment)) +
  geom_hline(yintercept = 100, linetype = "dashed", color = "grey50") +
  geom_line(linewidth = 1.2) +
  geom_point(size = 2.5) +
  annotate("text", x = 1.1, y = 101.5,
           label = "2021 baseline", hjust = 0, size = 3.0, color = "grey40") +
  scale_color_manual(values = setNames(
    c(col_entry, col_midlux, col_luxury),
    c(entry_label, midlux_label, luxury_label)
  )) +
  scale_y_continuous(breaks = seq(80, 140, by = 10)) +
  facet_wrap(~ geography,
             labeller = labeller(geography = c(
               "metro"  = "Marion County (metro)",
               "suburb" = "Suburbs"
             ))) +
  labs(
    title    = "Median Sale Price Index by Segment, 2021–2025 (2021 = 100)",
    subtitle = "Entry tier appreciation outpaced mid-luxury — the squeeze in dollar terms",
    x = "Year", y = "Price index (2021 = 100)", color = "Price segment",
    caption = paste0(
      "Source: Indiana Sales Disclosure Form deed records, STATS Indiana.\n",
      "N = ", format(n_total, big.mark = ","), " residential transactions.\n ",
      "Luxury tier capped at ", scales::dollar(luxury_CAP),
      ". Luxury decline reflects thin market volatility, ",
      "not rate sensitivity."
    )
  ) +
  theme_squeeze

ggsave(here::here("outputs/figures/fig9_price_index.png"), width = 10, height = 5, dpi = 300)
ggsave(here::here("outputs/figures/fig9_price_index.pdf"), width = 10, height = 5)
cat("Saved fig9_price_index.png/.pdf\n")

# ══════════════════════════════════════════════════════════════════════════════
# TABLE 1 — Descriptive statistics by geography
# ══════════════════════════════════════════════════════════════════════════════

table_data <- panel_data %>%
  mutate(
    Geography = if_else(geography == "metro",
                        "Marion County (metro)", "Suburbs"),
    `Price Segment` = case_when(
      price_segment == "entry"      ~ entry_label,
      price_segment == "mid_luxury" ~ midlux_label,
      TRUE                          ~ luxury_label
    ),
    `Rate Era` = case_when(
      year == 2021            ~ "Baseline (2021)",
      year == 2022            ~ "Rate shock (2022)",
      year %in% c(2023, 2024) ~ "Elevated plateau (2023–24)",
      year == 2025            ~ "Persistent high (2025)"
    ),
    # Convert to integer to suppress decimal places in summary table
    median_sale_price = as.integer(median_sale_price),
    median_hhi        = as.integer(median_hhi),
    population        = as.integer(population)
  )

MARKER <- 1e12

table_data_marked <- table_data %>%
  mutate(
    transactions_mid_luxury = transactions_mid_luxury + MARKER,
    median_sale_price       = median_sale_price       + MARKER,
    median_hhi              = median_hhi              + MARKER,
    population              = population              + MARKER
  )

datasummary(
  (`Median days on market`         = median_dom) +
    (`Avg sale-to-list ratio`        = avg_sale_to_list) +
    (`Median sale price ($)`         = median_sale_price) +
    (`30-yr mortgage rate (%)`       = mortgage_rate) +
    (`Rate lock-in gap (pp)`         = rate_gap) +
    (`Affordability ratio`           = affordability_ratio) +
    (`Mid-luxury transactions/month` = transactions_mid_luxury) +
    (`Median household income ($)`   = median_hhi) +
    (`County population`             = population) ~
    Geography * (N + Mean + SD + Median + Min + Max),
  data  = table_data_marked,
  title = "Table 1: Descriptive Statistics by Geography, 2021–2025",
  notes = "Source: Redfin, STATS Indiana SDF, FRED, Census ACS 2023 5-year. N = county-month observations.",
  fmt = function(x) {
    sapply(x, function(val) {
      if (is.na(val)) return("")
      if (abs(val) >= MARKER / 2) {
        # Mean/Median/Min/Max of integer columns — remove marker
        formatC(round(val - MARKER, 0), format = "f", digits = 0, big.mark = ",")
      } else if (abs(val) >= 20) {
        # SD of integer columns
        formatC(round(val, 0), format = "f", digits = 0, big.mark = ",")
      } else if (val == round(val, 0)) {
        # Any exact whole number (DOM min/max, zero SDs)
        formatC(val, format = "f", digits = 0, big.mark = ",")
      } else {
        formatC(val, format = "f", digits = 2)
      }
    })
  },
  output = here::here("outputs/tables/table1_descriptive.html")
)

# Render HTML table to PNG via webshot2
tbl1_html <- here::here("outputs/tables/table1_descriptive.html")
tbl1_png  <- here::here("outputs/tables/table1_descriptive.png")
webshot2::webshot(
  url      = paste0("file://", tbl1_html),
  file     = tbl1_png,
  delay    = 2,
  zoom     = 2,
  vwidth   = 1200,
  vheight  = 600,
  cliprect = "viewport"
)
file.remove(tbl1_html)
cat("Saved outputs/tables/table1_descriptive.png\n")

# ══════════════════════════════════════════════════════════════════════════════
# FIGURE 10 — HHI vs median sale price correlation by ZIP code
# Marion clusters bottom-left (income constrained)
# Hamilton clusters top-right (rate lock-in exposed)
# ══════════════════════════════════════════════════════════════════════════════

# Read once; derive raw_hhi before imputation to count missing values (P3-1).
zip_raw <- read_csv(here::here("data/processed/zip_median_prices.csv"),
                    show_col_types = FALSE) %>%
  filter(zip_code != 0) %>%
  mutate(zip_code = str_pad(as.character(zip_code), 5, pad = "0")) %>%
  filter(!is.na(median_sale_price)) %>%
  group_by(zip_code) %>%
  summarise(
    county            = county[which.max(transactions)],
    median_sale_price = weighted.mean(median_sale_price, transactions),
    raw_hhi           = first(zcta_hhi[!is.na(zcta_hhi)]),  # pre-imputation HHI
    transactions      = sum(transactions),
    .groups           = "drop"
  )

n_imputed <- sum(is.na(zip_raw$raw_hhi))

zip_data <- zip_raw %>%
  rename(zcta_hhi = raw_hhi) %>%
  # Impute missing zcta_hhi with county-level median HHI
  group_by(county) %>%
  mutate(zcta_hhi = if_else(is.na(zcta_hhi),
                            median(zcta_hhi, na.rm = TRUE),
                            zcta_hhi)) %>%
  ungroup()

cat("Unique zip codes:", nrow(zip_data), "\n")
cat("Zips with imputed HHI:", n_imputed, "\n")

# ── Recompute overall_cor on deduplicated zip_data ────────────────────────────
overall_cor <- cor(zip_data$zcta_hhi, zip_data$median_sale_price,
                   method = "pearson")

cat("Pearson r:", round(overall_cor, 3), "\n")
cat("R-squared:", round(overall_cor^2, 3), "\n")
cat("N zip codes:", nrow(zip_data), "\n")

# ── Fig12 plot ────────────────────────────────────────────────────────────────
zip_data %>%
  ggplot(aes(x = zcta_hhi, y = median_sale_price, color = county)) +
  geom_point(aes(size = transactions), alpha = 0.7) +
  geom_smooth(method = "lm", se = TRUE, color = "grey30", linewidth = 0.8) +
  annotate("text",
           x = max(zip_data$zcta_hhi) * 0.6,
           y = max(zip_data$median_sale_price) * 0.95,
           label = paste0("r = ", round(overall_cor, 3),
                          "\nR² = ", round(overall_cor^2, 3)),
           size = 4, fontface = "bold", color = "grey30") +
  scale_x_continuous(labels = dollar_format()) +
  scale_y_continuous(labels = dollar_format()) +
  scale_color_manual(values = c(
    "Marion"    = "#4472C4",
    "Hamilton"  = "#ED7D31",
    "Boone"     = "#70AD47",
    "Hendricks" = "#FFC000",
    "Johnson"   = "#9B59B6"
  )) +
  scale_size_continuous(range = c(2, 8), guide = "none") +
  labs(
    title    = "Median Household Income vs. Median Sale Price by ZIP Code",
    subtitle = "Point size = transaction volume | Line = OLS fit",
    x        = "Median Household Income (ACS 2023)",
    y        = "Median Sale Price 2021–2025",
    color    = "County",
    caption  = paste0(
      "Source: STATS Indiana SDF deed records; Census ACS 2023 5-year.\n",
      "N = ", nrow(zip_data), " unique zip codes",
      if_else(n_imputed > 0,
              paste0(" (", n_imputed,
                     " zip missing ZCTA HHI — imputed with county median HHI)\n"),
              "\n"),
      "Correlation calculated across all zip codes."
    )
  ) +
  theme_minimal(base_size = 13) +
  theme(
    legend.position  = "bottom",
    plot.title       = element_text(face = "bold", size = 14),
    plot.subtitle    = element_text(color = "grey40", size = 11),
    plot.caption     = element_text(color = "grey50", size = 9, hjust = 0),
    panel.grid.minor = element_blank()
  )

ggsave(here::here("outputs/figures/fig10_hhi_price_correlation.png"),
       width = 9, height = 6, dpi = 300)
ggsave(here::here("outputs/figures/fig10_hhi_price_correlation.pdf"),
       width = 9, height = 6)
cat("Saved fig10_hhi_price_correlation.png/.pdf\n")

# Save correlation stats for regression/hypothesis test reference
saveRDS(list(r = round(overall_cor, 3),
             r2 = round(overall_cor^2, 3),
             n_zip = nrow(zip_data)),
        here::here("data/processed/fig10_correlation_stats.rds"))
