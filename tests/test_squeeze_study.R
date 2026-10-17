#!/usr/bin/env Rscript
# Contract checks for the squeeze study settings used by scripts 01–03.
# Run from the project root: Rscript tests/test_squeeze_study.R

suppressPackageStartupMessages({
  library(dplyr)
  library(here)
})
source(here::here("scripts/squeeze_study.R"))

previous <- Sys.getenv("SQUEEZE_STUDY", NA)
Sys.unsetenv("SQUEEZE_STUDY")

# The default study keeps the published Indiana paths, window, and geography.
indiana <- squeeze_study_settings()
stopifnot(
  indiana$name == "indiana",
  identical(indiana$years, 2021:2025),
  indiana$panel_rds == "data/processed/panel_data.rds",
  indiana$sdf_file == "data/processed/sdf_indiana.csv",
  indiana$models_dir == "data/processed",
  indiana$output_root == "outputs",
  identical(indiana$core_counties, "Marion"),
  length(indiana$redfin_regions) == 5L
)

# Minnesota writes every artifact to its own paths.
minnesota <- squeeze_study_settings("minnesota")
paths <- c("panel_rds", "panel_csv", "sdf_file", "zip_prices_file", "hhi_zcta_file",
           "breaks_file", "models_dir", "output_root", "census_cache", "redfin_file")
stopifnot(
  identical(minnesota$years, 2021:2025),
  identical(minnesota$core_counties, c("Hennepin", "Ramsey")),
  length(minnesota$redfin_regions) == 7L,
  length(minnesota$county_fips) == 7L,
  all(names(minnesota$county_colors) %in%
        sub(minnesota$redfin_suffix, "", minnesota$redfin_regions)),
  !any(unlist(minnesota[paths]) %in% unlist(indiana[paths])),
  is.null(minnesota$map_zip_regex),
  identical(sort(names(minnesota$text)), sort(names(indiana$text)))
)

# Redfin breaks come from each study's fitted k-means file when it exists.
for (study in list(indiana, minnesota)) {
  if (file.exists(here::here(study$breaks_file))) {
    breaks <- squeeze_redfin_breaks(study)
    stopifnot(length(breaks) == 2L, breaks[1] < breaks[2])
  }
}

stopifnot(inherits(try(squeeze_study_settings("ohio"), silent = TRUE), "try-error"))

# The core HHI label keeps the published single-county format.
panel <- tibble(county = c("Marion", "Marion", "Hamilton"),
                median_hhi = c(63450, 63450, 117957))
stopifnot(core_hhi_label(panel, indiana) == "$63K")
two <- tibble(county = c("Ramsey", "Hennepin"), median_hhi = c(81004, 96339))
stopifnot(core_hhi_label(two, minnesota) == "Hennepin $96K, Ramsey $81K")

if (!is.na(previous)) Sys.setenv(SQUEEZE_STUDY = previous)
cat("Squeeze study settings contract checks passed.\n")
