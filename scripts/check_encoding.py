#!/usr/bin/env python3
"""
Encoding safety checker for Chinese text projects.

Checks:
1) UTF-8 decode validity
2) Replacement char U+FFFD
3) Suspicious mojibake tokens/patterns
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List


DEFAULT_SKIP_DIRS = {
    ".git",
    ".idea",
    ".vscode",
    "node_modules",
    "dist",
    "build",
    "target",
    ".next",
    ".nuxt",
    "__pycache__",
}

TEXT_EXTENSIONS = {
    ".java",
    ".kt",
    ".xml",
    ".yml",
    ".yaml",
    ".json",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".vue",
    ".css",
    ".scss",
    ".less",
    ".html",
    ".md",
    ".txt",
    ".sql",
    ".properties",
    ".csv",
    ".sh",
    ".bat",
    ".ps1",
    ".py",
    ".go",
    ".rs",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
}

SUSPICIOUS_LITERAL_TOKENS = {
    "\u951f\u65a4\u62f7",  # common mojibake token in Chinese environments
    "\u70eb\u70eb\u70eb",
    "\u5c6f\u5c6f\u5c6f",
    "\u6d93",
    "\u93c2",
    "\u9365",
    "\u00C3",
    "\u00C2",
    "\u00EF\u00BF\u00BD",
}

SUSPICIOUS_REGEXES = [
    re.compile(r"[\u00C3\u00C2\u00E2]{2,}"),
    re.compile(r"[\u00C0-\u00FF]{3,}"),
    re.compile(r"[\u6d93\u93c2\u9365]{2,}"),
    re.compile(r"\u00EF\u00BF\u00BD"),
]


@dataclass
class Issue:
    level: str
    path: str
    message: str


def is_probably_text_file(path: Path) -> bool:
    if path.suffix.lower() in TEXT_EXTENSIONS:
        return True

    try:
        with path.open("rb") as f:
            sample = f.read(4096)
    except OSError:
        return False

    if not sample:
        return True
    if b"\x00" in sample:
        return False

    control_bytes = 0
    for b in sample:
        if b in (9, 10, 13):
            continue
        if b < 32:
            control_bytes += 1
    return (control_bytes / len(sample)) < 0.20


def should_exclude(path: Path, exclude_patterns: List[str]) -> bool:
    as_posix = path.as_posix()
    for pattern in exclude_patterns:
        if path.match(pattern):
            return True
        if pattern in as_posix:
            return True
    return False


def iter_files(paths: Iterable[Path], exclude_patterns: List[str]) -> Iterable[Path]:
    for p in paths:
        if p.is_file():
            if not should_exclude(p, exclude_patterns) and is_probably_text_file(p):
                yield p
            continue
        if not p.is_dir():
            continue

        for root, dirs, files in os.walk(p):
            dirs[:] = [d for d in dirs if d not in DEFAULT_SKIP_DIRS]
            root_path = Path(root)
            for fn in files:
                fp = root_path / fn
                if should_exclude(fp, exclude_patterns):
                    continue
                if is_probably_text_file(fp):
                    yield fp


def collect_git_tracked_files(root: Path) -> List[Path]:
    try:
        res = subprocess.run(
            ["git", "ls-files"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []

    if res.returncode != 0:
        return []

    out: List[Path] = []
    for line in res.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        p = root / line
        if p.exists() and p.is_file() and is_probably_text_file(p):
            out.append(p)
    return out


def check_file(path: Path) -> List[Issue]:
    issues: List[Issue] = []
    try:
        raw = path.read_bytes()
    except OSError as e:
        issues.append(Issue("FAIL", str(path), f"Cannot read file: {e}"))
        return issues

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        issues.append(
            Issue(
                "FAIL",
                str(path),
                f"Invalid UTF-8 bytes at position {e.start}-{e.end}: {e.reason}",
            )
        )
        return issues

    if "\uFFFD" in text:
        issues.append(
            Issue(
                "FAIL",
                str(path),
                "Contains replacement character U+FFFD, likely corruption.",
            )
        )

    for token in SUSPICIOUS_LITERAL_TOKENS:
        if token in text:
            issues.append(
                Issue("WARN", str(path), f"Contains suspicious token: {token}")
            )

    for regex in SUSPICIOUS_REGEXES:
        m = regex.search(text)
        if m:
            issues.append(
                Issue(
                    "WARN",
                    str(path),
                    f"Suspicious mojibake pattern matched: {m.group(0)[:24]}",
                )
            )

    return issues


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check text files for UTF-8 and Chinese mojibake risks."
    )
    parser.add_argument(
        "--paths",
        nargs="*",
        default=["."],
        help="Files or directories to scan. Default: current directory.",
    )
    parser.add_argument("--strict", action="store_true", help="Treat WARN as failure.")
    parser.add_argument(
        "--git-tracked",
        action="store_true",
        help="Scan git tracked files from current directory only.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument(
        "--exclude",
        nargs="*",
        default=[],
        help="Glob/path fragments to exclude. Example: --exclude node_modules '*.min.js'",
    )
    return parser.parse_args()


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    args = parse_args()
    root = Path.cwd()

    if args.git_tracked:
        files = [
            f
            for f in collect_git_tracked_files(root)
            if not should_exclude(f, args.exclude)
        ]
    else:
        input_paths = [Path(p).resolve() for p in args.paths]
        files = list(iter_files(input_paths, args.exclude))

    files = sorted(set(files))

    all_issues: List[Issue] = []
    for fp in files:
        all_issues.extend(check_file(fp))

    fail_count = sum(1 for i in all_issues if i.level == "FAIL")
    warn_count = sum(1 for i in all_issues if i.level == "WARN")
    blocked = fail_count > 0 or (args.strict and warn_count > 0)
    status = "FAILED" if blocked else "PASSED"

    if args.json:
        payload = {
            "status": status,
            "strict": args.strict,
            "checked_files": len(files),
            "fail_count": fail_count,
            "warn_count": warn_count,
            "issues": [asdict(i) for i in all_issues],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Encoding check: {status}{' (strict)' if args.strict else ''}")
        print(f"Checked files: {len(files)}")
        print(f"FAIL: {fail_count}, WARN: {warn_count}")
        for issue in all_issues:
            print(f"[{issue.level}] {issue.path} - {issue.message}")

    return 1 if blocked else 0


if __name__ == "__main__":
    sys.exit(main())
