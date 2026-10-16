#!/usr/bin/env python3
"""List or stage selected unstaged hunks of one file without interactive git.

Usage:
  stage_hunks.py PATH --list        show numbered unstaged hunks
  stage_hunks.py PATH 1 3           stage hunks 1 and 3 into the index

Hunks are numbered from the current unstaged diff, so rerun --list after each
staging step. Only the index changes; the working tree is left untouched.
"""

import argparse
import subprocess
import sys


def unstaged_diff(path):
    """Return the unstaged diff text for one path."""
    return subprocess.run(
        ["git", "diff", "--no-color", "--no-ext-diff", "-U3", "--", path],
        check=True, capture_output=True, text=True,
    ).stdout


def split_hunks(diff_text):
    """Split a single-file diff into (header_lines, [hunk_lines, ...])."""
    header, hunks = [], []
    for line in diff_text.splitlines(keepends=True):
        if line.startswith("@@"):
            hunks.append([line])
        elif hunks:
            hunks[-1].append(line)
        else:
            header.append(line)
    return header, hunks


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path")
    parser.add_argument("hunks", nargs="*", type=int)
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    header, hunks = split_hunks(unstaged_diff(args.path))
    if not hunks:
        print(f"No unstaged hunks in {args.path}")
        return 0
    if any(line.startswith("Binary files") for line in header):
        print("Binary file: stage it whole with git add", file=sys.stderr)
        return 1

    if args.list or not args.hunks:
        for number, hunk in enumerate(hunks, start=1):
            changed = sum(1 for line in hunk[1:] if line[:1] in "+-")
            print(f"--- hunk {number} ({changed} changed lines) {hunk[0].strip()}")
            for line in hunk[1:]:
                if line[:1] in "+-":
                    print("   " + line.rstrip("\n")[:160])
        return 0

    invalid = [n for n in args.hunks if n < 1 or n > len(hunks)]
    if invalid:
        print(f"Unknown hunk number(s): {invalid}; file has {len(hunks)}", file=sys.stderr)
        return 1

    patch = "".join(header)
    for number in sorted(set(args.hunks)):
        patch += "".join(hunks[number - 1])
    # --recount tolerates line-number offsets from skipped earlier hunks.
    result = subprocess.run(
        ["git", "apply", "--cached", "--recount", "-"],
        input=patch, capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        return result.returncode
    print(f"Staged hunk(s) {sorted(set(args.hunks))} of {args.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
