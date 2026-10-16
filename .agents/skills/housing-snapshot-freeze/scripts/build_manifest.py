#!/usr/bin/env python3
"""Build or verify a hashed snapshot manifest for analysis inputs and outputs.

Build:   build_manifest.py build --label rc1 --output docs/snapshots/rc1.json PATH...
Verify:  build_manifest.py verify docs/snapshots/rc1.json

A manifest records each file's size and SHA-256, a combined snapshot digest,
the Git commit and dirty state, and Python/R versions. Directories are expanded
recursively. Verification recomputes every hash and exits 1 on any mismatch,
missing file, or added file under a recorded directory.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys

CHUNK = 1 << 20


def sha256(path):
    """Stream a file's SHA-256 so multi-gigabyte inputs stay bounded in memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expand(paths):
    """Return sorted files under the given files or directories."""
    files = set()
    for path in paths:
        if path.is_dir():
            files.update(p for p in path.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
        elif path.is_file():
            files.add(path)
        else:
            raise FileNotFoundError(path)
    return sorted(files)


def snapshot_digest(entries):
    """Combine per-file hashes into one order-independent snapshot digest."""
    lines = "".join(f"{e['path']}\t{e['sha256']}\n" for e in sorted(entries, key=lambda e: e["path"]))
    return hashlib.sha256(lines.encode()).hexdigest()


def run(command):
    """Return stripped stdout, or None when the tool is unavailable."""
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return (result.stdout or result.stderr).strip()


def build(args):
    """Hash the requested paths and write the manifest JSON."""
    entries = [
        {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}
        for path in expand(args.paths)
    ]
    status = run(["git", "status", "--porcelain", "--untracked-files=no"])
    r_version = run(["Rscript", "--version"])
    manifest = {
        "label": args.label,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": run(["git", "rev-parse", "HEAD"]),
        "git_branch": run(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
        "git_tracked_changes": bool(status),
        "python_version": platform.python_version(),
        "r_version": r_version.splitlines()[0] if r_version else None,
        "roots": [str(p) for p in args.paths],
        "file_count": len(entries),
        "total_bytes": sum(e["bytes"] for e in entries),
        "snapshot_sha256": snapshot_digest(entries),
        "files": entries,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Wrote {args.output}: {len(entries)} files, snapshot {manifest['snapshot_sha256']}")
    if manifest["git_tracked_changes"]:
        print("WARNING: tracked files have uncommitted changes; the commit does not fully describe the code")
    return 0


def verify(args):
    """Recompute hashes for a manifest and report every discrepancy."""
    manifest = json.loads(args.manifest.read_text())
    recorded = {e["path"]: e["sha256"] for e in manifest["files"]}
    problems = []
    for path_text, expected in recorded.items():
        path = Path(path_text)
        if not path.is_file():
            problems.append(f"missing: {path_text}")
        elif sha256(path) != expected:
            problems.append(f"changed: {path_text}")
    current = {str(p) for p in expand([Path(r) for r in manifest["roots"] if Path(r).exists()])}
    problems.extend(f"added: {p}" for p in sorted(current - set(recorded)))
    for problem in problems:
        print(problem)
    print(f"{manifest['label']}: {len(recorded)} files checked, {len(problems)} problem(s)")
    return 1 if problems else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    build_parser = sub.add_parser("build")
    build_parser.add_argument("--label", required=True)
    build_parser.add_argument("--output", type=Path, required=True)
    build_parser.add_argument("paths", nargs="+", type=Path)
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    return build(args) if args.command == "build" else verify(args)


if __name__ == "__main__":
    sys.exit(main())
