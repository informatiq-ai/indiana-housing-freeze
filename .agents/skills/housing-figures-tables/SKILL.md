---
name: housing-figures-tables
description: Create or revise publication figures and regression or summary tables for the Indianapolis and Twin Cities housing analysis (ggplot2 figures, modelsummary tables, event-study plots, price indices, tier comparisons). Use whenever adding a plot or table to an R script, regenerating outputs/figures or outputs/tables, or preparing Minnesota (MSP) or pooled results for the manuscript, even if the user only says "make a chart of X". Do not use for exploratory throwaway plots that will not be saved, or for model specification decisions (use housing-econometrics).
---

# Housing Figures and Tables

Every saved figure and table may end up in the manuscript, so each one must be
self-explanatory, traceable to its data, and consistent with the claim ledger.
These rules come from `CLAUDE.md` and the release gates in
`docs/journal_readiness_roadmap.md`.

## Before plotting

1. Identify the source artifact (for example
   `data/processed/research/county_month_tier.rds` or
   `outputs/research/model_coefficients.csv`) and read it; do not re-derive
   estimates inside plotting code when an estimation artifact exists.
2. Fix the labeling facts you will need: metro (`INDY`, `MSP`, or pooled),
   window, cohort (primary or strict), price units (nominal or constant 2025
   dollars), rate units (percentage points over 3.0%), tier definition (fixed
   2015–2019 baseline k-means or quantile sensitivity), and N.
3. Check `docs/claim_ledger.md`. If the figure or table supports a headline
   claim, the caption must agree with the ledger row's qualification (for
   example associational language when pre-trends fail).

## Figure contract

- Save both formats with the same stem, using the script's `figure_path()`
  helper so `INDIANA_ANALYSIS_OUTPUT_ROOT` isolation keeps working:

  ```r
  ggsave(figure_path("msp_event_study_log_real_price_2015_2025.png"), width = 10, height = 5.5, dpi = 300)
  ggsave(figure_path("msp_event_study_log_real_price_2015_2025.pdf"), width = 10, height = 5.5)
  ```

- **Descriptive file names:** `<metro>_<content>_<window>` in snake_case, for
  example `pooled_rate_sensitivity_by_tier_2015_2025.png`. Never `plot1.png`.
  The legacy Indiana `figN_*` names stay as they are unless that code is being
  edited anyway.
- **Labels:** every axis has a label with units; `x = NULL` is acceptable only
  for a date axis. Title is descriptive, not a slogan.
- **Caption states the key finding and the source**, for example: "Suburban
  move-up prices fell relative to the urban core after mid-2022; intervals are
  95% Webb wild-cluster bootstrap (7 counties). Source: Minnesota Department of
  Revenue eCRV; FRED MORTGAGE30US." The finding sentence must be true of the
  plotted data.
- Show uncertainty for estimates (intervals or ribbons) and name the method.
- Event studies show every lead and lag, the reference period, and a zero line.
- Reuse the theme and color constants already defined in the script
  (`theme_squeeze`, `col_metro`, and related) so figures read as one set. When
  a figure needs more series than those constants cover, choose colors that
  remain distinguishable in grayscale and for common color-vision deficiencies.

## Table contract

- Regression tables use `modelsummary` (already a dependency; chosen over
  stargazer for `vcov` support). Include standard errors, significance stars
  (`c("*" = 0.1, "**" = 0.05, "***" = 0.01)` to match existing tables), the
  covariance type, and a `notes` entry naming data source, sample, window,
  clusters, and fixed effects. Use `coef_map` for readable term names and
  `coef_omit` for fixed-effect dummies.
- Summary-statistics tables report N, mean, median, SD, min, and max.
- Write a machine-readable CSV next to every rendered table (same stem,
  `.csv`) so claim-ledger rows can cite a table cell. The existing scripts
  render HTML to PNG with `webshot2` and delete the HTML; keep that pattern for
  the image, but keep the CSV.
- Do not hand-type numbers into table notes; compute them (for example the N in
  the note) from the data.

## After saving

1. Run the output checker:

   ```bash
   python3 .agents/skills/housing-figures-tables/scripts/check_outputs.py outputs/figures outputs/tables
   ```

   It flags figures missing a `.png` or `.pdf` partner, non-descriptive names,
   and rendered tables without a CSV companion.
2. Open the PNG and confirm labels are legible and nothing is clipped.
3. If the output supports a claim, add or update its row in
   `docs/claim_ledger.md` with the artifact path and generating script.
4. Captions are prose: run the `housing-docs-style` checker on any Markdown
   that embeds them.
