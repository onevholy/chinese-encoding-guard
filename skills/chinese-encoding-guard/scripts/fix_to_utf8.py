#!/usr/bin/env python3
"""
Auto-fix text files to UTF-8 with backups.

Capabilities:
1) Convert non-UTF-8 text files to UTF-8
2) Attempt common mojibake reverse fixes on UTF-8 text
3) Save original bytes to backup folder before writing
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional, Tuple


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
    "\u951f\u65a4\u62f7",
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

NON_UTF8_CANDIDATE_ENCODINGS = [
    "gb18030",
    "gbk",
    "big5",
    "utf-16",
    "utf-16le",
    "utf-16be",
    "latin1",
]


@dataclass
class FixResult:
    path: str
    changed: bool
    method: str
    before_score: int
    after_score: int
    backup_path: Optional[str]
    message: str


def is_probably_text_file(path: Path) -> bool:
    if path.suffix.lower() in TEXT_EXTENSIONS:
        return True

    try:
        sample = path.read_bytes()[:4096]
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


def text_risk_score(text: str) -> int:
    score = 0
    score += text.count("\uFFFD") * 12

    for token in SUSPICIOUS_LITERAL_TOKENS:
        score += text.count(token) * 3

    for regex in SUSPICIOUS_REGEXES:
        score += len(regex.findall(text)) * 4

    bad_controls = 0
    for ch in text:
        cp = ord(ch)
        if cp in (9, 10, 13):
            continue
        if cp < 32:
            bad_controls += 1
    score += bad_controls * 2
    return score


def try_reverse_mojibake(text: str) -> Tuple[str, int, str]:
    baseline_score = text_risk_score(text)
    best_text = text
    best_score = baseline_score
    best_method = "none"

    transforms = [
        ("reinterpret_gb18030_to_utf8", "gb18030"),
        ("reinterpret_gbk_to_utf8", "gbk"),
        ("reinterpret_latin1_to_utf8", "latin1"),
        ("reinterpret_cp1252_to_utf8", "cp1252"),
    ]

    for method, src_encoding in transforms:
        try:
            candidate = text.encode(src_encoding, errors="strict").decode(
                "utf-8", errors="strict"
            )
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        score = text_risk_score(candidate)
        if score < best_score:
            best_text = candidate
            best_score = score
            best_method = method

    return best_text, best_score, best_method


def decode_non_utf8(raw: bytes) -> Tuple[Optional[str], Optional[str], Optional[int]]:
    best_text: Optional[str] = None
    best_encoding: Optional[str] = None
    best_score: Optional[int] = None

    for enc in NON_UTF8_CANDIDATE_ENCODINGS:
        try:
            candidate = raw.decode(enc, errors="strict")
        except UnicodeDecodeError:
            continue
        score = text_risk_score(candidate)
        if best_score is None or score < best_score:
            best_text = candidate
            best_encoding = enc
            best_score = score

    return best_text, best_encoding, best_score


def backup_rel_path(path: Path, root: Path) -> Path:
    try:
        return path.resolve().relative_to(root.resolve())
    except ValueError:
        resolved = path.resolve()
        drive = resolved.drive.replace(":", "") or "drive"
        rel = Path("__external__") / drive
        for part in resolved.parts[1:]:
            rel /= part.replace(":", "_")
        return rel


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def process_file(path: Path, root: Path, backup_dir: Path, dry_run: bool) -> FixResult:
    try:
        raw = path.read_bytes()
    except OSError as e:
        return FixResult(
            path=str(path),
            changed=False,
            method="read_error",
            before_score=0,
            after_score=0,
            backup_path=None,
            message=f"Cannot read file: {e}",
        )

    try:
        text = raw.decode("utf-8", errors="strict")
        before_score = text_risk_score(text)
        fixed_text, after_score, method = try_reverse_mojibake(text)

        if method == "none" or after_score >= before_score:
            return FixResult(
                path=str(path),
                changed=False,
                method="none",
                before_score=before_score,
                after_score=before_score,
                backup_path=None,
                message="Already UTF-8 or no safer reverse transform found.",
            )

        if before_score - after_score < 2:
            return FixResult(
                path=str(path),
                changed=False,
                method="none",
                before_score=before_score,
                after_score=after_score,
                backup_path=None,
                message="Improvement too small; skipped to avoid risky rewrite.",
            )

        rel = backup_rel_path(path, root)
        backup_path = backup_dir / rel
        if not dry_run:
            ensure_parent(backup_path)
            backup_path.write_bytes(raw)
            path.write_text(fixed_text, encoding="utf-8")

        return FixResult(
            path=str(path),
            changed=True,
            method=method,
            before_score=before_score,
            after_score=after_score,
            backup_path=str(backup_path),
            message="Applied mojibake reverse transform and normalized UTF-8.",
        )
    except UnicodeDecodeError:
        decoded, source_enc, decoded_score = decode_non_utf8(raw)
        if decoded is None or source_enc is None or decoded_score is None:
            return FixResult(
                path=str(path),
                changed=False,
                method="unfixed_non_utf8",
                before_score=999,
                after_score=999,
                backup_path=None,
                message="Invalid UTF-8 and no fallback decoding succeeded.",
            )

        rel = backup_rel_path(path, root)
        backup_path = backup_dir / rel
        if not dry_run:
            ensure_parent(backup_path)
            backup_path.write_bytes(raw)
            path.write_text(decoded, encoding="utf-8")

        return FixResult(
            path=str(path),
            changed=True,
            method=f"decode_{source_enc}_to_utf8",
            before_score=999,
            after_score=decoded_score,
            backup_path=str(backup_path),
            message="Converted non-UTF-8 text to UTF-8.",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Auto-fix text files to UTF-8 with backup copies."
    )
    parser.add_argument(
        "--paths",
        nargs="*",
        default=["."],
        help="Files or directories to process. Default: current directory.",
    )
    parser.add_argument(
        "--git-tracked",
        action="store_true",
        help="Process git tracked files from current directory only.",
    )
    parser.add_argument(
        "--exclude",
        nargs="*",
        default=[],
        help="Glob/path fragments to exclude.",
    )
    parser.add_argument(
        "--backup-dir",
        default="",
        help="Backup root directory. Default: .encoding_backups/<timestamp>",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Analyze and report only; do not write backup or modify files.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON output.",
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
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = (
        Path(args.backup_dir).resolve()
        if args.backup_dir
        else (root / ".encoding_backups" / timestamp).resolve()
    )

    if args.git_tracked:
        files = [
            f
            for f in collect_git_tracked_files(root)
            if not should_exclude(f, args.exclude)
        ]
    else:
        files = list(
            iter_files([Path(p).resolve() for p in args.paths], args.exclude)
        )
    files = sorted(set(files))

    results: List[FixResult] = []
    for fp in files:
        results.append(process_file(fp, root, backup_dir, args.dry_run))

    changed = [r for r in results if r.changed]
    unresolved = [
        r
        for r in results
        if (not r.changed) and r.method in {"read_error", "unfixed_non_utf8"}
    ]

    payload = {
        "status": "FAILED" if unresolved else "OK",
        "dry_run": args.dry_run,
        "checked_files": len(results),
        "changed_files": len(changed),
        "unresolved_files": len(unresolved),
        "backup_dir": None if args.dry_run or not changed else str(backup_dir),
        "results": [asdict(r) for r in results],
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"UTF-8 repair status: {payload['status']}{' (dry-run)' if args.dry_run else ''}")
        print(f"Checked files: {payload['checked_files']}")
        print(f"Changed files: {payload['changed_files']}")
        print(f"Unresolved files: {payload['unresolved_files']}")
        if payload["backup_dir"]:
            print(f"Backup directory: {payload['backup_dir']}")
        for r in results:
            state = "CHANGED" if r.changed else "SKIP"
            print(
                f"[{state}] {r.path} | method={r.method} | "
                f"score {r.before_score}->{r.after_score} | {r.message}"
            )

    return 1 if unresolved else 0


if __name__ == "__main__":
    sys.exit(main())

