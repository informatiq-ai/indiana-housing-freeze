---
name: housing-docs-style
description: Write or edit this project's prose (README, docs/*.md, findings, methodology, manuscript drafts, figure and table captions, R/Python comments) to the repository's writing and attribution rules. Use whenever adding or revising any documentation or narrative text in this repo, including small README edits and new docs pages, even if the user does not mention style. Do not use for code logic changes that touch no prose.
---

# Housing Docs Style

This repository's prose is written for a policy or academic audience. The rules
below come from `CLAUDE.md`; they exist because the work is headed for journal
submission, and stylistic or attribution slips are cheap to prevent and costly
to catch in review.

## Writing rules

- **Thesis first.** Open each section with a thesis sentence, then a sentence
  previewing what the section covers. A reader skimming first sentences should
  get the argument.
- **One topic per paragraph.** Split paragraphs that change subject.
- **Direct declarative sentences** at moderate formality. Avoid blog voice,
  rhetorical questions, and hype ("striking", "dramatic").
- **No ordinal transitions.** Do not start sentences with "First,", "Second,",
  "Third,", "Lastly,". Numbered lists are fine when order matters.
- **No em dashes** (U+2014). Use a colon, comma, parentheses, or two sentences.
  En dashes in numeric ranges (2015–2025) are fine.
- **Claim discipline.** Use associational language ("is associated with") unless
  the claim ledger marks a causal claim as verified. State units (percentage
  points, constant 2025 dollars), sample, window, and geography with numbers.
  Never copy a number from older prose; trace it to an artifact listed in
  `docs/claim_ledger.md`.

## Attribution rules

- Never mention the institutions and publications named in the attribution
  rules of the local `CLAUDE.md` anywhere: prose, comments, commit messages, or
  output metadata. Their names are kept out of tracked files, so the checker
  reads them from the untracked `prohibited_terms.local.txt` beside its script
  (one regular expression per line; `#` starts a comment). Create that file
  from `CLAUDE.md` on a new clone.
- Never reference coursework, rubrics, grading, assignments, submissions, or
  instructors. If a comment carries that context, replace it with the
  methodological reason it encoded.
- Attribute data to primary sources only: Redfin, STATS Indiana, Minnesota
  Department of Revenue (eCRV), U.S. Census Bureau, FRED (Federal Reserve Bank
  of St. Louis).

## Workflow

1. Draft or edit the text.
2. Run the checker on every file you touched:

   ```bash
   python3 .agents/skills/housing-docs-style/scripts/check_style.py README.md docs/findings.md
   ```

   It reports em dashes and ordinal openers in Markdown, and prohibited
   references in any file type, with line numbers. It exits nonzero on findings.
3. Fix each finding by rewriting the sentence, not by swapping characters
   mechanically. A sentence that needed an em dash usually wants a colon or a
   split.
4. Reread section openers as a sequence; if they do not state the argument,
   revise them.

The checker cannot judge thesis sentences, paragraph focus, or claim
discipline. Those need a reading pass.

## Scope notes

- `CLAUDE.md` and `TESTING.md` are local-only (listed in `.git/info/exclude`);
  edit them when asked but do not stage them.
- Code comments follow the same attribution rules and must be concise and
  technical (what the code does and why). The em-dash rule is enforced for
  Markdown prose; existing comment box-drawing characters in scripts are fine.
