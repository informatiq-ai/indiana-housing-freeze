# Minnesota weekly eCRV ingestion and Twin Cities price sensitivity

Status: implementation proposal, with a working pre-ingestion audit utility. Reviewed 2026-09-19 against repository commit `3e147ee11cf6dc4389c15cf3822507ea5c96ca11`.

## Recommendation

Add a separate Minnesota source adapter: immutable ZIP archives → versioned transaction store → Parquet analytical snapshots → county-month CSV/RDS panel for R. Process XML directly inside ZIPs, once per new archive content hash. Preserve revisions and repeated child records; count a sale once regardless of parcel count. Begin with the seven-county Twin Cities planning region, with county identifiers explicitly mapped to Census FIPS.

The eCRV sample supports transaction prices, activity, financing mix and seller-paid-points measures. It cannot by itself establish buyer demand elasticity: completed sales omit unsold listings and do not reveal how buyers respond to asking-price reductions. Add listing data for that question, and describe rate/price/volume associations as descriptive unless an identification strategy supports causal interpretation.

This PR implements the audit and documents the production design. It does not implement the persistent ingestion store, automatic download, monthly panel, or a price-sensitivity model. One archive cannot establish cross-week amendment/deletion behavior or an adequate time series. The next implementation should validate those source behaviors with overlapping weeks and a recent extract before publishing research outputs.

## Repository fit

Inspected `README.md`, `requirements.txt`, `.gitignore`, `docs/data_sources.md`, `scripts/00_data_pipeline.py`, and `scripts/01_data_pipeline.R`, plus the recursive repository tree. No AGENTS.md, test suite, package structure, or CI workflow appeared in that tree.

* `00_data_pipeline.py` is a top-level Python script using pandas, NumPy, requests and scikit-learn. It caches Redfin data, reads annual Indiana tab-delimited files, applies residential and sale-quality filters, joins parcel ZIPs, fits price clusters, enriches income, and writes CSVs.
* `01_data_pipeline.R` consumes those outputs, joins Redfin, ACS and FRED, and writes county-month `panel_data.csv`/`.rds`. The study years, county names, price cutoffs and Marion/suburban treatment are hard-coded.
* Scripts 02 and 03 and the Streamlit map are downstream Indiana analyses. Minnesota should have separate outputs until their geography, identifiers and analysis assumptions are parameterized.
* Preserve `data/raw`, `data/processed`, `scripts`, `docs` and `outputs` conventions. Namespace Minnesota caches so an Indiana cache cannot satisfy a Minnesota request. Do not import the existing Python pipeline for helper functions: it performs work at module import.
* Do not copy Indiana's cents-to-dollars conversion: sample Minnesota amounts are decimal dollar values. Do not reuse Indiana's fitted $380K/$1.05M tiers or its geographic treatment assignment as Minnesota facts.
* The existing R panel uses single-family Redfin data, while the Indiana transaction filter is broader residential. For Minnesota, explicitly align property type across sources and retain missing coverage separately from true zero transactions.

## Sample inspection

The requested `/mnt/data` location was absent in this desktop environment. The same named attachment was recovered through the referenced conversation and inspected locally.

| Check | Observed result |
|---|---:|
| ZIP file | `2020-12-28-07-10-27_eCRVExtract.zip` |
| Compressed / uncompressed | 3,673,647 / 13,880,876 bytes |
| Members | 2,260 XML files; no nested archives |
| Strict UTF-8 parsing | 2,061 successes; 199 failures |
| Explicit Windows-1252 fallback after UTF-8 decoding fails | 2,260 successes; zero remaining failures |
| Unique `(countyCde, crvNumberId)` | 2,260 |
| Duplicate member names / duplicate transaction keys | 0 / 0 |
| Header/property county disagreement | 0 |
| Seven-county records, before housing/quality filters | 1,042 |
| Deed/contract dates | 2003-08-08 through 2020-12-24 |
| Dates in 2020 / earlier | 2,251 / 9 |
| Records containing multiple parcels | 174 |
| Records containing multiple property addresses | 23 |
| Records containing multiple prior/planned uses | 11 / 12 |
| Nonempty property ZIP / parcel ID | 2,119 / 2,132 records |
| Records containing financing-arrangement interest rate | 85 |

Archive SHA-256: `3cedaa70a0a0781c0939c0f1084ca9314179765ca774e80d2940c87299bc7762`.

The 199 encoding failures all contain invalid UTF-8 bytes despite the XML declaration. Windows-1252 decoding makes them syntactically parseable; that is evidence for a controlled legacy recovery path, not proof that every text character is semantically correct. Keep original bytes, log recovery per member, and never silently replace or discard characters. Strict mode must fail visibly. Schema validation and business validation are additional steps; successful parsing does not establish either.

The file falls in the Department of Revenue's Schema 3 extract period, beginning November 9, 2020. Weekly extracts contain submitter information for accepted sales, without subsequent county/city-added data. Do not treat their sale-condition flags as an assessor's final arm's-length certification. [Minnesota eCRV documentation](https://www.revenue.state.mn.us/electronic-certificate-real-estate-value-ecrv)

### Observed schema and mapping

Paths below are relative to `ecrvForm`. These observations come from the sample, including the explicit encoding recovery.

| XML path | Proposed analytical field / handling |
|---|---|
| `headerForm/countyCde`, `headerForm/crvNumberId` | Strings `mn_county_code`, `ecrv_id`; compound source key `MN:ecrv:county:id` |
| `propertyForm/county` | Independent consistency check against header |
| `salesAgreementForm/deedContractDate` | Preserve timestamp text/offset; derive local calendar `sale_date`, `sale_month`; not acceptance date |
| `salesAgreementForm/totPurchaseAmt` | `gross_sale_price`, fixed decimal dollars, retain four decimal places |
| `salesAgreementForm/sellerPdPts`, `downPmtEquity`, `specialAssesmtAmt` | Separate decimal measures; never reinterpret zero as missing automatically |
| `salesAgreementForm/financeType`, `deedTypeCde` | Categorical source codes; preserve unknown values with quality flag |
| `salesAgreementForm/financeArrangements/*` | Child table; interest rate/payment information is sparse, not a universal mortgage-rate measure |
| `salesAgreementForm/personalPropertyIncludedInTotal`, `personalProperties/*` | Flag plus child values; distinguish missing item detail from zero personal property |
| `propertyForm/usesBeforeSale/*`, `plannedUses/*` | Separate child tables with source ID, ordinal, tiers 1–3; use prior use for baseline stock classification |
| `propertyForm/parcels/*` | Child table with parcel string, primary flag, ordinal; retain punctuation and leading zeros |
| `propertyForm/mnPropertyAddresses/*` | Child table with property city/ZIP/address; do not substitute buyer/seller mailing addresses |
| `propertyForm/principalResidence`, `newBuildingsOnSaleYear`, `whatIsIncludedInSale` | Source flags/codes; classify new construction and land-only separately |
| `salesAgreementForm/buyerPartInterest`, `deedPayoff`, `agreement2YrsOld`, `likeKindExchange`, `receivedInTrade` | Quality/exclusion flags retained individually |
| `supplementaryForm/relatedInd`, `giftInd`, `governmentInd`, `legalActionInd`, `nameChangeInd`, `nonMarketPriceInd`, `nonListedInd`, `taxExemptInd` | Nullable Boolean source flags; empty/absent is unknown, not false |
| `supplementaryForm/buyerAppraisalAmt`, `sellerAppraisalAmt` and indicators | Optional appraisal measures; validate positive values and applicability before ratios |

Amounts, deed dates, financing type, seller-paid points and downpayment/equity fields occur in all 2,260 recovered records, but presence is not accuracy. No listing history, asking price, DOM, systematic living area, or source revision timestamp was observed. `nonListedInd` is not a measure of listing duration. Names, email, phones and free-text party comments are unnecessary for this analysis and should not enter analytical exports or logs.

Consult the [published extract schema](https://www.revenue.state.mn.us/sites/default/files/2020-10/Sales%20Extract%20Schema3%2010-9-2020.txt) for structural validation. Version-pin the approved XSD and its checksum locally; do not resolve external schema references while ingesting untrusted files. Unknown future structures should be quarantined rather than flattened into misleading columns.

## Geography

Default to the seven-county planning region, clearly labeled as such; it is not the full Minneapolis–St. Paul–Bloomington MN–WI MSA. [Met Council region](https://imagine2050.metrocouncil.org/reference-materials/transportation/transportation-overview/)

| County | MN code | Full Census FIPS | Sample sales before filters |
|---|---|---|---:|
| Anoka | 02 | 27003 | 104 |
| Carver | 10 | 27019 | 68 |
| Dakota | 19 | 27037 | 179 |
| Hennepin | 27 | 27053 | 375 |
| Ramsey | 62 | 27123 | 152 |
| Scott | 70 | 27139 | 55 |
| Washington | 82 | 27163 | 109 |

Use an explicit versioned crosswalk, not a numerical formula or a zero-padded MN code. [Minnesota two-digit codes](https://mgsweb2.mngs.umn.edu/cwi_doc/county.asp), [Census FIPS](https://tigerweb.geo.census.gov/tigerwebmain/Files/acs24/tigerweb_acs24_county_2024_bas24_mn.html)

Use the property county, checked against the header, for filtering. Keep statewide normalized history when practical; geography belongs in analytical views so later study-area changes do not require reparsing ZIPs. Keep records without ZIPs in county analyses. Require unambiguous property geography for ZIP or city analyses; multiple addresses can cross ZIPs. Link parcels to geographic boundaries to distinguish Minneapolis/St. Paul from their suburbs—Hennepin and Ramsey contain both. Postal ZIPs and Census ZCTAs require a documented crosswalk rather than unconditional equality.

## Storage and incremental ingestion design

Use an embedded DuckDB database as the single-writer ingestion registry and version store; produce compressed Parquet for analytical interchange and CSV for the current R conventions. This avoids operating a server at this scale. Add DuckDB and PyArrow only when the ingestion/export modules are implemented and tested; the audit requires only Python 3.11+ standard libraries.

### Tables and grains

* `ingest_batches`: one archive content hash; original filename, byte size, source extract timestamp (with known/unknown timezone), discovered timestamp, parser/schema versions, lifecycle status, record/error counts. Same filename with changed bytes is a new batch.
* `record_versions`: one `(source_key, raw_member_sha256, parser_version)`; normalized sale fields, schema/recovery flags and canonical analytical-content hash. Use decimal amounts, local dates, string identifiers and nullable Booleans. Preserve parser-version lineage even when reparsing identical raw bytes.
* `record_observations`: one `(batch_hash, member_ordinal)`; member name, source key, raw-member hash and version reference. This retains repeated appearances without multiplying sales.
* `transaction_parcels`, `transaction_addresses`, `transaction_uses`, `transaction_financing`, `transaction_personal_property`: child rows keyed by version and ordinal/source child ID. Never join all children to the sale fact in a way that multiplies sale prices or counts.
* `current_transactions`: deterministic view over valid versions and observations. One row per source key, retaining a revision-conflict flag. A sale's parcel ID is not its dedup key: a parcel can sell more than once.
* `quality_events`: batch/member references, machine-readable issue codes and severity; no personal text.
* `analytical_snapshots`: committed input batches, parser/filter/config versions, snapshot ID, file checksums and publication state.

### Processing sequence

1. Discover `**/*.zip` recursively in the input folder. Preserve the original ZIP outside Git in `data/raw/mn/ecrv/` or private object storage. A ZIP containing another ZIP is unsupported initially; report it rather than recursively expanding without bounds.
2. Stream SHA-256 over the archive and consult the registry. Skip only a successfully committed batch with the same bytes and parser/config version. Size/mtime can optimize discovery but are not identity. Renaming or copying a ZIP must not double-count records.
3. Stream members with bounded reads. Reject oversized members, excessive total expansion, duplicate member names, unsupported roots, DTD/entities and unexpected member types. Never extract paths to the filesystem. Use strict decoding first; permit the logged Windows-1252 path only under explicit legacy policy.
4. Validate required key/date/amount fields and known schema shape. Retain nullable optional fields. Check filename identifiers against XML but trust neither without validation. Separate parsing, structural, domain and research-filter errors. Quarantine malformed records and retain provenance for replay.
5. Stage a whole archive and commit its registry, observations, versions and children in one database transaction. Default publication should require zero unresolved hard errors; a deliberately partial import must remain labeled incomplete. On failure, rollback and leave the batch retryable. Enforce one writer with a lock.
6. Resolve exact repeats by key plus member hash. Compare analytical hashes to distinguish a relevant price/date/property revision from formatting or excluded-party-text changes. Distinct conflicting records for the same key in one batch are errors, not arbitrary keep-last operations.
7. When no authoritative revision timestamp exists, select the latest *source extract timestamp* as a documented latest-observed policy, not latest ingestion time or ZIP filesystem mtime. Older backfills must never replace later observations. Equal-timestamp conflicting values require adjudication. Retain every version and offer as-of snapshots. Confirm whether the weekly service republishes amendments; this sample does not prove that it does.
8. Absence from a later weekly ZIP is not deletion. Apply withdrawals only from an explicit, validated status/deletion source. If the service never republishes corrections, arrange a separate reconciliation feed or state that historical corrections remain unavailable.
9. Rebuild affected sale-date partitions and both old/new county-month cells after revisions, including changed dates, counties or eligibility. Do not limit corrections to the most recent extract week. Maintain a full rebuild command from retained raw ZIPs.
10. Export to a new immutable snapshot directory, verify checksums/counts, then atomically publish its manifest. Mark exports complete after publication; a crash after database commit must allow export replay without re-ingestion. Readers load only the active manifest, never a half-written directory.

Suggested layout:

```text
data/raw/mn/ecrv/<original archives>
data/intermediate/mn/ecrv.duckdb
data/processed/mn/snapshots/<snapshot_id>/transactions/sale_year=2020/*.parquet
data/processed/mn/snapshots/<snapshot_id>/parcels/*.parquet
data/processed/mn/current_snapshot.json
data/processed/mn/ecrv_transactions.csv
data/processed/mn/panel_county_month.csv
data/processed/mn/panel_county_month.rds
outputs/mn/quality/
outputs/mn/figures/
```

Prefer yearly Parquet partitions initially; weekly/county/ZIP partitions would create many tiny files. Use county/date predicates within each yearly partition and compact after batches. Preserve out-of-window historical records in the canonical store, even if an analytical view selects 2021–2025. A constant-rate extrapolation of this one sample is about 0.72 GB uncompressed XML per 52 archives, which is a sizing illustration, not a forecast of actual weekly volume. Benchmark first; start serially, then use bounded archive parsing workers feeding one writer if needed. Spark, a queue service and a hosted database are unnecessary starting requirements.

## Research eligibility and metrics

Keep eligibility as versioned flags and exclusion reasons, rather than permanently deleting raw or normalized records. Start a comparable single-family cohort using all prior-use rows: require residential single-family and no conflicting other uses; keep condo, townhouse, multifamily, vacant land and mixed-use in separate cohorts. Separate planned use from use before sale. Retain construction and partial-interest indicators.

Exclude or separately analyze gifts, related-party/nonmarket sales, name changes, legal actions, government transfers, deed payoffs and partial interests. Review quitclaim/contract-for-deed and exchange categories explicitly. Unknown flags are not affirmative evidence of an arm's-length transaction. Report a filter funnel by county and week. A price floor/cap may be used as a sensitivity specification for Indiana comparability, but it must not become an unexamined Minnesota data-cleaning rule.

| Metric | Definition and analytical limit |
|---|---|
| Sales and market activity | Unique eligible sales by sale month, county and property type; per 1,000 households/residents using a documented denominator |
| Price distribution | Median, quartiles, log prices, within-type and within-area changes; composition-adjusted/repeat-sales indices when parcel matching supports them |
| Seller-paid-points prevalence/intensity | Share with positive `sellerPdPts`; amount / positive gross price. This field is a narrow concession proxy, not total buyer concessions |
| Financing composition | Cash, mortgage, contract-for-deed and assumed financing shares; unknown category shown explicitly |
| Downpayment/equity ratio | `downPmtEquity / gross_sale_price`, flag outside plausible bounds; label as reported equity/downpayment, not verified cash contribution or mortgage LTV |
| Personal-property adjustment | Gross less valid included item values; unknown adjusted price if the inclusion flag is true but values are incomplete; retain gross alongside it |
| Affordability/payment exposure | Monthly payment for a fixed assumed LTV and term, joined to contemporaneous FRED rates; payment / monthly ACS income. Scenario measure, not the borrower's actual payment |
| Listing outcomes, external data | DOM, sale/original-list and sale/final-list ratios, price-cut incidence, sale hazard, cancellations and inventory; absent from sample |
| Reporting completeness | Extract-date minus deed-date distribution, missing-archive schedule, revision rate and counts by vintage. This is observed reporting lag, not DOM or exact acceptance delay |

For the mortgage scenario, `payment = (price * LTV) * r / (1 - (1+r)^(-360))`, with `r = annual_rate_percent / 1200`; handle zero rates as principal/360. Use dated rates and income vintages. Preserve uncertainty and ACS margins of error where available.

Build a county × sale-month × property-type × fixed baseline price-band panel. Freeze Minnesota baseline bands from a pre-period or use externally defined real-dollar bands; refitting clusters every week changes cohort membership. Contemporaneous sold-price bands remain descriptive and can be endogenous to the outcome. Prefer pre-period property values for causal heterogeneous-effect tests where available.

Join Minnesota Redfin monthly metrics by county FIPS, property type and period; use one period duration and assert one-to-one join keys to avoid overlapping-window duplication. Match FRED to month and use lag sensitivity because rate exposure may predate the deed. Add year-appropriate ACS controls and local supply, employment and construction measures. Do not forward-fill unavailable outcomes or convert missing feed coverage to zero. Publish recent months as provisional until empirically measured reporting lags mature.

A descriptive model can relate log price or sales volume to rates/payment exposure, area effects, seasonality and property mix. Common national rates are absorbed by full month fixed effects; estimating differential effects requires interactions with predetermined local exposure. With only seven counties, conventional cluster inference is fragile. Do not transplant the Indiana Marion-versus-suburbs DiD or claim parallel trends from a chart alone.

To test actual buyer price sensitivity, obtain listing-level price histories and unsold/withdrawn inventory, match to parcel/date with documented ambiguity rules, and estimate sale probability/time-to-sale around price changes with controls for property and seller selection. Price cuts are endogenous; causal demand elasticity requires a defensible exogenous source of price variation or a stated structural model. Completed-sale price and quantity moving together cannot identify a demand curve. No price-sensitivity estimate is justified from this single 2020 extract.

## Concrete changes and implementation order

| File/module | Scope |
|---|---|
| `scripts/audit_mn_ecrv.py` | **Implemented:** bounded local ZIP audit, explicit encoding recovery, key/geography/date/child/field coverage, aggregate JSON output |
| `tests/test_audit_mn_ecrv.py` | **Implemented:** synthetic tests; no real party data or ZIP committed |
| `docs/minnesota_ecrv_architecture.md` | **Implemented:** this design and measured sample findings |
| `README.md` | **Implemented:** link and runnable audit command |
| `.gitignore` | **Implemented:** Minnesota raw/intermediate/processed/quality outputs and Python caches |
| `config/mn_ecrv.json` | **Proposed:** input/output locations, geographic crosswalk, schema periods, filters, study window and frozen segment definitions |
| `scripts/mn_ecrv/schema.py` | **Proposed:** typed normalized fields, schema adapters, XSD validation and safe encoding policy |
| `scripts/mn_ecrv/store.py` | **Proposed:** registry, transactional staging, observations/versions/children, latest/as-of resolution |
| `scripts/mn_ecrv/export.py` | **Proposed:** Parquet snapshots, CSV compatibility and atomic manifests |
| `scripts/00_mn_ecrv_pipeline.py` | **Proposed:** folder CLI with ingest, validate, rebuild and export subcommands |
| `scripts/01_mn_panel.R` | **Proposed:** Minnesota-specific monthly panel with keyed Redfin/ACS/FRED joins |
| `scripts/02_mn_price_sensitivity.R` | **Proposed:** descriptive metrics and explicitly identified models when data permits |
| `requirements.txt` | **Proposed:** tested DuckDB/PyArrow/XML-validation dependencies; no change needed for audit |
| `tests/test_mn_ecrv_ingestion.py` | **Proposed:** replay, rename, changed same-name ZIP, overlapping archives, amendments, out-of-order backfill, child fanout, rollback, partition corrections and schema drift |

First collect adjacent overlapping weekly extracts plus a recent archive and the source's amendment/withdrawal documentation. Then implement the canonical store and verify replay/revision cases. Backfill the desired study years and inspect completeness before building the R panel. Automate a scheduled folder scan only after initial backfill reconciliation; acquiring files from the source virtual room is a separate concern from processing files already on disk.

### Run the implemented audit

```bash
# Python 3.11+; no third-party packages required
python3 scripts/audit_mn_ecrv.py /path/to/weekly-zips --output outputs/mn/quality/strict.json

# Explicit legacy recovery, justified by this sample's encoding diagnostics
python3 scripts/audit_mn_ecrv.py /path/to/weekly-zips --allow-cp1252 --output outputs/mn/quality/recovered.json

python3 -m unittest discover -s tests -p 'test_audit_mn_ecrv.py' -v
```

The audit returns nonzero for unresolved member errors, duplicate keys/names or county mismatches, while saving its report. Reports are per archive: the utility does not deduplicate across archives, validate XSD, certify sale eligibility or write transaction datasets. Missing field counts are distinct from empty values; reported presence counts do not validate numeric contents. For the inspected sample, strict mode returns failure for 199 members; explicit recovery returns success for all 2,260. Ten synthetic tests pass.
