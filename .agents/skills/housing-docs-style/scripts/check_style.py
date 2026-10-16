#!/usr/bin/env python3
"""Check repository prose for style and attribution violations.

Reports em dashes and ordinal sentence openers in Markdown files, and
prohibited institutional or academic-context references in any text file.
Exits 1 when any finding is reported, 0 otherwise.
"""

import argparse
from pathlib import Path
import re
import sys

ACADEMIC_TERMS = [
    r"rubric", r"grading", r"graded", r"syllabus", r"coursework", r"homework",
    r"professor", r"instructor", r"course\s+assignment", r"class\s+assignment",
    r"class\s+project", r"submission\s+requirement",
]
# Prohibited institution and publication names must not appear in tracked
# files, so they live in an untracked list beside this script.
LOCAL_TERMS_FILE = Path(__file__).resolve().parent / "prohibited_terms.local.txt"
ORDINAL_OPENER = re.compile(
    r"(^|[.!?]\s+|^\s*[-*]\s+)(First|Second|Third|Fourth|Fifth|Lastly)\b,?",
)
EM_DASH = "—"
MARKDOWN_SUFFIXES = {".md", ".markdown", ".qmd", ".rmd"}
# Lines in this checker and in the docs-style skill name the prohibited terms
# on purpose; skip them so the rules themselves do not fail the check.
SELF_REFERENCE = re.compile(r"housing-docs-style")


def load_prohibited(terms_file):
    """Compile academic terms plus local institution terms into one pattern.

    Returns (pattern, local_loaded); local_loaded is False when the untracked
    terms file is absent, so the caller can warn that coverage is partial.
    """
    terms = list(ACADEMIC_TERMS)
    local_loaded = terms_file.is_file()
    if local_loaded:
        for line in terms_file.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                terms.append(line)
    pattern = re.compile(r"\b(" + "|".join(terms) + r")\b", re.IGNORECASE)
    return pattern, local_loaded


def check_file(path, prohibited):
    """Return (line_number, kind, text) findings for one file."""
    findings = []
    if SELF_REFERENCE.search(str(path)):
        return findings
    is_markdown = path.suffix.lower() in MARKDOWN_SUFFIXES
    in_code_block = False
    text = path.read_text(encoding="utf-8", errors="replace")
    for number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("```"):
            in_code_block = not in_code_block
        for match in prohibited.finditer(line):
            findings.append((number, "prohibited-reference", match.group(0)))
        if not is_markdown or in_code_block:
            continue
        if EM_DASH in line:
            findings.append((number, "em-dash", line.strip()[:100]))
        for match in ORDINAL_OPENER.finditer(line):
            findings.append((number, "ordinal-opener", match.group(2)))
    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--terms-file", type=Path, default=LOCAL_TERMS_FILE,
                        help="untracked list of prohibited name patterns")
    args = parser.parse_args()
    prohibited, local_loaded = load_prohibited(args.terms_file)
    if not local_loaded:
        print(f"warning: {args.terms_file} not found; institution names are "
              "not checked", file=sys.stderr)
    total = 0
    for path in args.paths:
        if not path.is_file():
            print(f"{path}: not a file, skipped", file=sys.stderr)
            continue
        for number, kind, detail in check_file(path, prohibited):
            total += 1
            print(f"{path}:{number}: {kind}: {detail}")
    print(f"{total} finding(s)")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
