# CLAUDE.md — Indiana Housing Market Analysis

## Project Overview

This repository contains quantitative research on the Indiana mid-luxury housing market squeeze, originally developed for MBA 611. The analysis uses Difference-in-Differences (DiD) models to examine housing affordability dynamics, drawing on Redfin listing data and STATS Indiana demographic/economic data.

The current focus is **file cleanup/reorganization** and **documenting findings for publication**.

---

## Repository Structure

Maintain this structure. Do not reorganize without explicit instruction:

```
/data/
  raw/          # Original source files — never modify
  processed/    # Cleaned/merged outputs from R scripts
/docs/          # Write-ups, findings, publication drafts
/outputs/
  figures/      # Plots and charts (.png, .pdf)
  interactive/  # Interactive visualizations (HTML, etc.)
  tables/       # Regression tables, summary stats (.csv, .txt)
/scripts/       # All R analysis scripts
README.md
CLAUDE.md
```

If raw data files or scripts are found outside these directories during cleanup, ask before moving them.

---

## Code Standards (R)

### Style
- Follow the [tidyverse style guide](https://style.tidyverse.org/): snake_case for variables and functions, 2-space indentation, `<-` for assignment.
- Match the conventions already present in existing scripts — do not reformat code that wasn't touched.
- Pipe operator: use `|>` (base R) unless the file already uses `%>%` (magrittr), in which case stay consistent.

### Comments
- Every function needs a header comment describing its purpose, inputs, and outputs.
- Non-obvious transformations and model specifications must have inline comments.
- Regression model calls must include a comment explaining the specification choice (e.g., which fixed effects, why a particular DiD window).

### Reproducibility (non-negotiable)
- No hardcoded absolute paths. Use `here::here()` for all file references.
- Set `set.seed()` at the top of any script involving random processes (bootstrap, sampling).
- All data loading must reference `/data/raw/` or `/data/processed/` — never a local desktop path.
- `sessionInfo()` output should be capturable; do not use packages that can't be installed from CRAN or documented alternatives.

---

## Cleanup Instructions

When reorganizing files:
1. Identify the file's role (raw data, processed data, analysis script, output, documentation) before moving it.
2. Do not delete any file — move to an `/archive/` folder if it appears redundant, and note why.
3. Update any `source()` or file path references broken by the move.
4. After reorganizing, verify at least one end-to-end script still runs without errors before committing.

---

## Documentation & Publication Standards

### Writing style (for docs/ and README)
- Direct declarative sentences. No ordinal transitions ("First, Second, Third").
- Each section opens with a thesis sentence followed by a preview of what follows.
- One paragraph per topic. Moderate formality — written for a policy or academic audience, not a blog.
- No em dashes.

### Figures
- All figures must have axis labels, a descriptive title, and a caption explaining the key finding.
- Save in both `.png` (for documents) and `.pdf` (for publication-quality output).
- File names should be descriptive: `did_model_price_index_2019_2023.png`, not `plot1.png`.

### Tables
- Regression tables exported via `modelsummary` or `stargazer`. Include standard errors, significance stars, and a note on the data source.
- Summary statistics tables must include N, mean, median, SD, min, and max.

---

## What Not to Do

- Do not modify files in `/data/raw/` under any circumstances.
- Do not introduce new packages without checking if the functionality already exists in the current dependency set.
- Do not reformat working code for style alone — only reformat code that is being actively edited.
- Do not combine multiple unrelated changes in a single commit.

---

## Attribution & Academic Reference Rules

**Never include references to Ball State University, BSU, or the Indianapolis Business Journal (IBJ) in any file in this repository** — not in comments, documentation, README, commit messages, or output metadata. This applies to all file types.

Acceptable data source attributions: Redfin, STATS Indiana, U.S. Census Bureau, FRED (Federal Reserve Bank of St. Louis), or other primary sources directly.

---

## Script Comment Standards

- Comments in R scripts must be concise and technical — describe *what* the code does and *why* a particular approach was chosen.
- **Never reference rubrics, course assignments, grading criteria, submission requirements, or academic deliverables** in any comment or documentation string.
- Acceptable comment framing: data provenance, model specification rationale, transformation logic, known data limitations.
- If a comment currently references a class or assignment context, remove it and replace with a methodological note if the context is still relevant.