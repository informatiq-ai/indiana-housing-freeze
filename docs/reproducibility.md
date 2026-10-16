# Reproducibility guide

## Scope

This guide describes how a reviewer should rebuild the project without treating
locally cached data or previously generated figures as evidence of success. The
established Indiana analysis and the longitudinal cross-metro analysis are
separate workflows and write to separate output namespaces.

## Environment

- Record the operating system, Python version, R version, and Git commit in the
  release manifest.
- Use the repository virtual environment for Python when available.
- Install Python dependencies from `requirements.txt`.
- Record R package names and versions for a release-candidate build. The current
  scripts may install/load packages through `pacman`; a journal archive should
  add a lockfile or an equivalent version snapshot.
- Store `CENSUS_API_KEY` and `FRED_API_KEY` only in an untracked environment
  file. Never commit `.env`, `.Renviron`, credentials, or tokens.
- Run commands from the repository root.

## Data availability and privacy

Raw Indiana SDF and Minnesota eCRV files are not assumed to be redistributable
with the code archive. A release must provide source URLs, retrieval dates,
expected filenames/archive schedule, and cryptographic hashes where licensing
permits. The reproducibility package should contain code, schemas, manifests,
quality summaries, and non-sensitive aggregate results.

No analytical output may contain buyer, seller, telephone, email, mailing-
address, title-company, or other party data. Treat raw files as immutable.

## Workflow A: established Indiana analysis

Build the audited history before the enriched pipeline:

```bash
.venv/bin/python scripts/00_indiana_sdf_pipeline.py \
  --input-dir data/raw/in \
  --output data/processed/indiana_sdf_history.csv \
  --quality-dir outputs/indiana/quality

.venv/bin/python scripts/00_data_pipeline.py
Rscript scripts/01_data_pipeline.R
Rscript scripts/02_eda_descriptive_stats.R
Rscript scripts/03_regression_hypothesis_tests.R
```

When preserving a historical result, set the documented namespaced analysis
output root rather than overwriting prior release artifacts. Record the exact
environment variable, output directory, and commit in the manifest.

## Workflow B: longitudinal cross-metro analysis

First ingest and reconcile both states:

```bash
.venv/bin/python scripts/00_indiana_sdf_pipeline.py \
  --input-dir data/raw/in \
  --output data/processed/indiana_sdf_history.csv \
  --quality-dir outputs/indiana/quality

.venv/bin/python scripts/00_mn_ecrv_pipeline.py all
```

Then run the namespaced research workflow:

```bash
.venv/bin/python scripts/research/01_prepare_transactions.py \
  --start-year 2015 \
  --end-year 2025

# Minnesota member accounting, revisions, gaps, and the funnel bridge;
# exits nonzero when an identity check fails
.venv/bin/python scripts/00_mn_ecrv_pipeline.py reconcile

Rscript scripts/research/02_build_panels.R
Rscript scripts/research/03_estimate_models.R
```

These commands are the intended public interface. Before release, confirm them
against each script's current `--help` or argument handling and update this guide
if the implementation differs. Do not claim a clean rebuild until the commands
have run in a clean environment with the required raw inputs.

## Verification

Run the complete Python suite:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Run the R contract/assertion checks:

```bash
Rscript tests/test_longitudinal_research.R
```

Also verify manually or with generated audits that:

- all expected input files appear in manifests with hashes;
- county-year funnels and Minnesota weekly schedules reconcile;
- accepted transaction keys and panel keys are unique;
- no child-table join multiplies a transaction price or count;
- no prohibited party/contact fields enter outputs;
- the research panel contains 132 months for each covered county;
- zero transaction cells occur only in proven observed-source periods;
- external joins list all unmatched keys and provisional observations;
- tier artifacts reproduce from the recorded training cohort and seed;
- table and figure values match machine-readable model outputs;
- the claim ledger contains every headline number.

An unavailable full-data test must be reported as unavailable or skipped, not
passed. Preserve stdout/stderr or a concise machine-readable check report for
the release archive.

## Release manifest

Each release candidate should record:

- release identifier, UTC timestamp, Git commit, and dirty/clean worktree state;
- Python and R versions plus dependency snapshots;
- input paths, sizes, hashes, detected schemas, and coverage dates;
- parser, cohort, CPI, tier, panel, and model configuration versions;
- normalized-data, panel, model-table, and figure hashes;
- commands run, exit status, test counts, skipped checks, and failures;
- known provisional periods and data recoveries;
- the final `ready`, `ready with disclosed limitations`, or `not ready`
  decision.

## Clean-room release procedure

1. Create a fresh checkout at the candidate commit.
2. Provision a new Python environment and a version-controlled R environment.
3. Place raw inputs according to the documented source inventory without
   copying prior processed files.
4. Run ingestion, tests, panel construction, models, and artifact generation in
   the documented order.
5. Compare hashes or expected statistical summaries with the candidate release.
6. Audit the claim ledger against regenerated machine-readable artifacts.
7. Inspect rendered tables and figures for clipping, misleading scales, missing
   captions, and stale labels.
8. Archive code, manifests, non-sensitive outputs, dependency locks, and the
   completed release checklist.
