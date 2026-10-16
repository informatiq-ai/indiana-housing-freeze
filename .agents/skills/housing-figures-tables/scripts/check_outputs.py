#!/usr/bin/env python3
"""Check saved figures and tables against the repository output contract.

Flags figures without both .png and .pdf versions, generic file names, and
rendered tables (.png/.html) without a machine-readable .csv companion.
Exits 1 when any finding is reported.
"""

import argparse
from collections import defaultdict
from pathlib import Path
import re
import sys

GENERIC_NAME = re.compile(r"^(plot|figure|fig|chart|table|tbl|image|untitled)[_-]?\d*$", re.I)
FIGURE_SUFFIXES = {".png", ".pdf"}
RENDERED_TABLE_SUFFIXES = {".png", ".html"}


def is_table_dir(path):
    """Treat directories named like tables as table outputs."""
    return "table" in path.name.lower()


def check_dir(directory):
    """Return findings for one output directory."""
    findings = []
    stems = defaultdict(set)
    for path in directory.rglob("*"):
        if path.is_file():
            stems[path.with_suffix("")].add(path.suffix.lower())
    for stem, suffixes in sorted(stems.items()):
        name = stem.name
        if GENERIC_NAME.match(name):
            findings.append(f"{stem}: generic file name")
        if is_table_dir(directory):
            if suffixes & RENDERED_TABLE_SUFFIXES and ".csv" not in suffixes:
                findings.append(f"{stem}: rendered table has no .csv companion")
        elif suffixes & FIGURE_SUFFIXES and not FIGURE_SUFFIXES <= suffixes:
            missing = sorted(FIGURE_SUFFIXES - suffixes)
            findings.append(f"{stem}: figure missing {', '.join(missing)}")
    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directories", nargs="+", type=Path)
    args = parser.parse_args()
    findings = []
    for directory in args.directories:
        if not directory.is_dir():
            print(f"{directory}: not a directory, skipped", file=sys.stderr)
            continue
        findings.extend(check_dir(directory))
    for finding in findings:
        print(finding)
    print(f"{len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
