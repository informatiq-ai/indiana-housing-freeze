# ══════════════════════════════════════════════════════════════════════════════
# Study settings for the move-up squeeze scripts (01–03)
#
# SQUEEZE_STUDY selects the study. Both studies run the published 2021–2025
# method unchanged: nominal sale prices, k-means price segments fit on each
# metro's own sales, the rate-gap and post-shock definitions, and the same
# models. Only geography, input files, and source labels differ.
#   indiana    Indianapolis five-county study (default; the published paths)
#   minnesota  Twin Cities seven-county study, Hennepin and Ramsey as the core
#
# Indiana interpretive text (for example, the Marion income-constraint
# argument) is kept word for word. The Minnesota study uses neutral captions
# because those conclusions have not been tested there.
# ══════════════════════════════════════════════════════════════════════════════

# Return the settings list for one study.
# Input:  study name (defaults to the SQUEEZE_STUDY environment variable).
# Output: named list consumed by 01_data_pipeline.R, 02_eda_descriptive_stats.R,
#         and 03_regression_hypothesis_tests.R.
squeeze_study_settings <- function(name = Sys.getenv("SQUEEZE_STUDY", "indiana")) {
  indiana <- list(
    name               = "indiana",
    metro_label        = "Indianapolis metro",
    region_label       = "Indiana",
    redfin_file        = "data/processed/redfin_indiana.csv",
    redfin_regions     = c("Boone County, IN", "Hamilton County, IN",
                           "Hendricks County, IN", "Marion County, IN",
                           "Johnson County, IN"),
    redfin_suffix      = " County, IN",
    census_cache       = "data/processed/census_county_controls.csv",
    census_state       = "18",
    census_counties    = "011,057,063,081,097",
    census_suffix      = " County, Indiana",
    county_fips        = c("18097", "18057", "18011", "18063", "18081"),
    tiger_state        = "IN",
    sdf_file           = "data/processed/sdf_indiana.csv",
    zip_prices_file    = "data/processed/zip_median_prices.csv",
    hhi_zcta_file      = "data/processed/hhi_zcta.csv",
    breaks_file        = "data/processed/price_segment_breaks_indiana.json",
    panel_rds          = "data/processed/panel_data.rds",
    panel_csv          = "data/processed/panel_data.csv",
    models_dir         = "data/processed",
    output_root        = "outputs",
    core_counties      = "Marion",
    core_label         = "Marion County (metro)",
    core_control_label = "Marion County (control)",
    core_short_label   = "Metro (Marion)",
    core_cat_label     = "Marion",
    suburb_detail_label = "Suburbs (Hamilton/Boone/Hendricks/Johnson)",
    sdf_source_long    = "Indiana Sales Disclosure Form deed records, STATS Indiana",
    sdf_source_short   = "STATS Indiana SDF deed records",
    sdf_source_map     = "STATS Indiana SDF",
    sdf_table_label    = "STATS Indiana SDF",
    county_colors      = c("Marion" = "#4472C4", "Hamilton" = "#ED7D31",
                           "Boone" = "#70AD47", "Hendricks" = "#FFC000",
                           "Johnson" = "#9B59B6"),
    map_title          = "The Indy Squeeze: Housing Vulnerability by Zip Code",
    map_zip_regex      = "^(460|461|462)",
    city_points        = tibble::tibble(
      city = c("Indianapolis", "Carmel", "Fishers", "Noblesville", "Zionsville",
               "Whitestown", "Avon", "Brownsburg", "Greenwood", "Plainfield",
               "Mooresville", "Franklin", "Greenfield"),
      lat  = c(39.7684, 39.9784, 39.9567, 40.0456, 39.9506,
               39.9914, 39.7626, 39.8437, 39.6137, 39.7042,
               39.6128, 39.4806, 39.7870),
      lon  = c(-86.1581, -86.1180, -85.9669, -85.9669, -86.2661,
               -86.3522, -86.3994, -86.3969, -86.1066, -86.3994,
               -86.3730, -86.0558, -85.7697)
    ),
    # Indiana interpretive captions, unchanged from the published analysis.
    text = list(
      fig4_core_note = function(core_hhi_lbl) paste0(
        " in this market.\nMarion County absence of move-up reflects income ",
        "constraint (median HHI ", core_hhi_lbl, "), not a rate shock response."
      ),
      fig5_subtitle = "Post-shock: bidding wars trend down while price cuts trend up | Faint lines = monthly raw values | Trend = LOESS smoother",
      fig6_subtitle = "Suburban move-up volume collapse is the rate lock-in market freeze made visible",
      fig7_subtitle = "Two mechanisms, same outcome — Marion via income constraint, suburbs via rate shock",
      fig8_annotation = "Both trend upward at similar rates → parallel trends ✓",
      fig8_subtitle = "Both geographies trend together pre-shock — parallel trends assumption supported",
      fig8_note = function(core_hhi_lbl) paste0(
        "Geography proxies for buyer type — Marion income constraint (",
        core_hhi_lbl, " HHI) implies conservative lower bound."
      ),
      fig9_subtitle = "Entry tier appreciation outpaced move-up — the squeeze in dollar terms",
      fig9_luxury_note = ". Luxury decline reflects thin market volatility, not rate sensitivity.",
      ovb_note = paste0(
        "OVB candidates: new construction (Hamilton County Eli Lilly/Amazon expansion), ",
        "school district premiums (Carmel/Fishers), corporate relocations."
      ),
      table7_note = function(core_hhi_lbl) paste0(
        "Treatment = suburban counties (proxy for move-up buyers). ",
        "Control = Marion County (proxy for necessity-driven buyers). ",
        "Geography is imperfect proxy for buyer type — HMDA data needed. ",
        "Marion income constraint (median HHI ", core_hhi_lbl,
        ") implies conservative lower bounds."
      ),
      fig12_title = "The Rate Penalty: Move-Up Market Bears the Brunt of Rate Hikes",
      fig12_subtitle = "Entry-level buyers remain insulated, while move-up properties face severe price degradation | N = ",
      fig12_luxury_note = "%/pp) reflects thin market volatility, not behavioral rate sensitivity\n"
    )
  )

  minnesota <- list(
    name               = "minnesota",
    metro_label        = "Twin Cities metro",
    region_label       = "Twin Cities",
    redfin_file        = "data/processed/mn/redfin_minnesota.csv",
    redfin_regions     = c("Anoka County, MN", "Carver County, MN",
                           "Dakota County, MN", "Hennepin County, MN",
                           "Ramsey County, MN", "Scott County, MN",
                           "Washington County, MN"),
    redfin_suffix      = " County, MN",
    census_cache       = "data/processed/mn/census_county_controls_mn.csv",
    census_state       = "27",
    census_counties    = "003,019,037,053,123,139,163",
    census_suffix      = " County, Minnesota",
    county_fips        = c("27003", "27019", "27037", "27053", "27123",
                           "27139", "27163"),
    tiger_state        = "MN",
    sdf_file           = "data/processed/mn/sdf_minnesota_nominal.csv",
    zip_prices_file    = "data/processed/mn/zip_median_prices_mn_nominal.csv",
    hhi_zcta_file      = "data/processed/mn/hhi_zcta_mn.csv",
    breaks_file        = "outputs/mn/squeeze/price_segment_breaks_nominal.json",
    panel_rds          = "data/processed/mn/panel_data_mn.rds",
    panel_csv          = "data/processed/mn/panel_data_mn.csv",
    models_dir         = "data/processed/mn/squeeze_models",
    output_root        = "outputs/mn/squeeze_2021_2025",
    core_counties      = c("Hennepin", "Ramsey"),
    core_label         = "Hennepin and Ramsey (metro)",
    core_control_label = "Hennepin and Ramsey (control)",
    core_short_label   = "Metro (Hennepin, Ramsey)",
    core_cat_label     = "Hennepin and Ramsey",
    suburb_detail_label = "Suburbs (Anoka/Carver/Dakota/Scott/Washington)",
    sdf_source_long    = "Minnesota Department of Revenue eCRV records",
    sdf_source_short   = "Minnesota Department of Revenue eCRV records",
    sdf_source_map     = "Minnesota Department of Revenue eCRV",
    sdf_table_label    = "Minnesota eCRV",
    county_colors      = c("Hennepin" = "#4472C4", "Ramsey" = "#2E4A7D",
                           "Anoka" = "#ED7D31", "Carver" = "#70AD47",
                           "Dakota" = "#FFC000", "Scott" = "#9B59B6",
                           "Washington" = "#C00000"),
    map_title          = "The Twin Cities Squeeze: Housing Vulnerability by Zip Code",
    # Sample ZIPs are already limited to the seven counties.
    map_zip_regex      = NULL,
    city_points        = tibble::tibble(
      city = c("Minneapolis", "St. Paul", "Bloomington", "Plymouth", "Maple Grove",
               "Eden Prairie", "Woodbury", "Eagan", "Lakeville", "Blaine",
               "Coon Rapids", "Shakopee", "Chaska", "Stillwater", "Burnsville"),
      lat  = c(44.9778, 44.9537, 44.8408, 45.0105, 45.0725,
               44.8547, 44.9239, 44.8041, 44.6497, 45.1608,
               45.1732, 44.7974, 44.7894, 45.0564, 44.7677),
      lon  = c(-93.2650, -93.0900, -93.2983, -93.4555, -93.4558,
               -93.4708, -92.9594, -93.1669, -93.2428, -93.2349,
               -93.3030, -93.5273, -93.6022, -92.8060, -93.2777)
    ),
    # Neutral captions: the Indiana mechanism claims are not assumed here.
    text = list(
      fig4_core_note = function(core_hhi_lbl) paste0(
        " in this market.\nSegments are assigned from the county median sale price; ",
        "core-county median HHI ", core_hhi_lbl, "."
      ),
      fig5_subtitle = "Faint lines = monthly raw values | Trend = LOESS smoother",
      fig6_subtitle = "Completed sales by segment and geography",
      fig7_subtitle = "Estimated mortgage payment relative to county median income",
      fig8_annotation = "",
      fig8_subtitle = "Pre-shock trends shown without imposing a parallel-trends conclusion",
      fig8_note = function(core_hhi_lbl) paste0(
        "Geography proxies for buyer type. Core-county median HHI ",
        core_hhi_lbl, "."
      ),
      fig9_subtitle = "Segment medians indexed to 2021",
      fig9_luxury_note = ".",
      ovb_note = "",
      table7_note = function(core_hhi_lbl) paste0(
        "Treatment = suburban counties (proxy for move-up buyers). ",
        "Control = Hennepin and Ramsey counties. ",
        "Geography is imperfect proxy for buyer type. ",
        "Core-county median HHI ", core_hhi_lbl, "."
      ),
      fig12_title = "Modeled Sale Price by Mortgage-Rate Gap and Segment",
      fig12_subtitle = "Associational predictions from the price interaction model | N = ",
      fig12_luxury_note = "%/pp) is estimated from a thin luxury sample.\n"
    )
  )

  studies <- list(indiana = indiana, minnesota = minnesota)
  if (!name %in% names(studies)) {
    stop("Unknown SQUEEZE_STUDY '", name, "'. Use one of: ",
         paste(names(studies), collapse = ", "))
  }
  study <- studies[[name]]
  study$start_year <- 2021L
  study$end_year   <- 2025L
  study$years      <- 2021:2025
  study
}

# Read the study's fitted k-means breaks (nominal dollars) written by the
# Python pipeline, so Redfin county medians use the same segment boundaries
# as the transaction records.
squeeze_redfin_breaks <- function(study) {
  jsonlite::fromJSON(here::here(study$breaks_file))$breaks
}

# Resolve output locations relative to the project root.
squeeze_output_root <- function(study) here::here(study$output_root)
squeeze_model_path  <- function(study, filename) {
  dir.create(here::here(study$models_dir), recursive = TRUE, showWarnings = FALSE)
  here::here(study$models_dir, filename)
}

# Format the core-county median HHI for captions.
# Input:  panel data with county and median_hhi; the study settings.
# Output: "$63K" for one core county, "Hennepin $96K, Ramsey $81K" for several.
core_hhi_label <- function(panel, study) {
  values <- panel |>
    dplyr::filter(as.character(county) %in% study$core_counties) |>
    dplyr::distinct(county = as.character(county), median_hhi) |>
    dplyr::arrange(match(county, study$core_counties))
  fmt <- function(x) paste0("$", formatC(round(x / 1000), format = "f",
                                         digits = 0, big.mark = ","), "K")
  if (nrow(values) == 1) return(fmt(values$median_hhi[1]))
  paste(paste(values$county, fmt(values$median_hhi)), collapse = ", ")
}
