---
name: housing-commit-staging
description: Prepare this repository's changes for commit by grouping them into focused commits and staging one group at a time, including staging only some hunks of a file that mixes unrelated work. Use whenever the user asks to commit, stage, split, or organize changes, prepare a PR, or clean up a large uncommitted diff in this repo. Claude stages and proposes messages; the user runs git commit. Do not use for reviewing code quality (use code-review).
---

# Housing Commit Staging

The repository owner commits every change personally. Claude's job is to make
each commit easy to review: one coherent change per commit, staged precisely,
with a proposed message. The rules come from `CLAUDE.md`, and they exist
because this is research code headed for publication: a reviewer must be able
to tell which commit changed a cohort rule, a model, or a number.

## Hard rules

- **Never run `git commit`**, `git push`, or anything that rewrites history.
  Stage only, then hand over with a message the user can paste.
- Never commit on `main`. Work on the current feature branch; if on `main`,
  propose a branch name and stop.
- Commits are authored by Phillip Johnson <phil@informatiq.ai>. Do not add
  Claude attribution trailers unless the user asks.
- Do not combine unrelated changes in one commit.
- `CLAUDE.md` and `TESTING.md` are listed in `.git/info/exclude` on purpose.
  Never stage them or remove them from the exclude file.
- Never stage raw data (`data/raw/`), the SQLite store, `.env`, or generated
  research outputs; check `git check-ignore -v` when unsure.
- Commit messages must not mention prohibited institutions or academic
  context (see `housing-docs-style`).

## Workflow

1. **Inventory.** `git status --short`, `git diff --stat`, and
   `git diff --cached --stat`. If something is already staged, find out
   whether the user staged it before reorganizing.
2. **Group.** Propose commit groups by purpose (for example: repository
   hygiene; Minnesota ingestion; Indiana real-price extension; longitudinal
   research; documentation). For each group list files and, for mixed files,
   which hunks.
3. **Order by dependency.** A group must not import or reference code from a
   later group. Check imports (`grep -n "^from\|^import\|source("`) across
   groups. In this repo `scripts/research/` imports `mn_ecrv.store`, so
   Minnesota ingestion goes first.
4. **Stage one group.** The index holds one commit at a time, so stage only
   the next group and let the user commit before staging the following one.
   - Whole files: `git add <paths>`; deletions from tracking:
     `git rm --cached <path>` (the file stays on disk).
   - Part of a mixed file: list and stage hunks with the bundled script:

     ```bash
     python3 .agents/skills/housing-commit-staging/scripts/stage_hunks.py scripts/00_data_pipeline.py --list
     python3 .agents/skills/housing-commit-staging/scripts/stage_hunks.py scripts/00_data_pipeline.py 2 5
     ```

   - When a single hunk mixes two concerns, build the staged version from
     `HEAD` instead: `git show HEAD:<path>`, apply only the intended change,
     then `git hash-object -w --stdin` and
     `git update-index --cacheinfo 100644,<hash>,<path>`. The working tree
     keeps all edits.
5. **Verify.** Show `git diff --cached` (or `--stat` for large data files) and
   confirm nothing from another group leaked in. Run the test suite against
   the working tree (`.venv/bin/python -m unittest discover -s tests -v`;
   `Rscript tests/test_longitudinal_research.R`), and say plainly that
   intermediate commits were not tested in isolation unless you did so.
6. **Hand over** with a proposed message: imperative subject under ~70
   characters, optional body explaining why. Then list the remaining groups
   and wait for the user to confirm the commit before staging the next one.
