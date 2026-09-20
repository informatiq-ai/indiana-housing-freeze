# Unified panel contract

## Transaction input

Require or derive these concepts without discarding source provenance:

- `source_key`, `source_state`, `source_schema`, and source snapshot/version.
- Sale date/month/year and gross sale price.
- County name and Census FIPS.
- `metro`: `INDY` or `MSP`.
- `tier_type`: `URBAN_CORE` or `SUBURBAN_COLLAR`.
- Property-type evidence and parcel count.
- Current-study and strict/comparable eligibility with exclusion reasons.
- Recovery, revision-conflict, or source-quality flags.

Do not force fields unavailable in one state into false or zero. Use null plus
documented availability.

## Analytical grains

- Canonical transaction table: one row per source transaction.
- Primary aggregate: county × sale month × fixed baseline price tier.
- Coverage table: source state × county × source/extract period, with observed,
  incomplete, provisional, and missing states.

If a property-type stratification is used, add it to every panel key and require
one-to-one joins at that expanded grain.

## Joins

- Mortgage rates: month key; retain level and spread over the declared 3.0%
  baseline. Consider lagged rate exposure as a sensitivity, not a silent default.
- Income/population: county FIPS plus estimate year/vintage. Retain ACS estimate
  vintage and margins of error when available.
- Listing data: county FIPS, month, property type, and one period duration.
  Assert uniqueness before joining.

Never forward-fill unavailable outcomes or interpret feed absence as zero.

## Price tiers

- Estimate independently by metro using eligible 2015–2019 transactions.
- Record random seed, transformation, outlier rule, number of clusters, centers,
  and final collapsed labels.
- Freeze the resulting boundaries for later years and sensitivity runs.
- Treat contemporaneous sold-price tiers as descriptive because the outcome
  determines membership.

## Required diagnostics

- Raw-to-eligible counts by state/county/year.
- Duplicate-key and join-cardinality assertions.
- Unmatched ACS, FRED, listing, and geography keys.
- Panel balance and missing-period matrix.
- Tier counts and boundaries by metro/baseline year.
- Provisional-period and reporting-lag flags.
