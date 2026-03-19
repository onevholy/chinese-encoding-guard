---
name: chinese-encoding-guard
description: Prevent Chinese text mojibake when writing or modifying code and docs. Use this skill whenever work may touch non-ASCII text, UTF-8/GBK/GB18030 encoding, Windows PowerShell file writes, i18n strings, SQL comments, logs, CSV import/export, or any report of garbled characters.
---

# Chinese Encoding Guard

Use this skill to keep Chinese text readable and encoding-safe during code changes.

## Core Goal

Keep edited text files valid UTF-8 and block common mojibake patterns before delivery.

## Trigger Conditions

Apply this skill immediately when any of these are true:
- The user mentions encoding errors, mojibake, or Chinese text corruption.
- The task edits files that may contain Chinese text.
- The task writes files from Windows PowerShell.
- You see suspicious symbols like U+FFFD or known corruption tokens.

## Workflow

1. Scope the files that will be edited.
2. Run pre-check on those files.
3. If needed, run auto-fix to normalize UTF-8 (with backups).
4. Edit with UTF-8-safe methods.
5. Run post-check on the same scope.
6. If any issue remains, stop and fix before final response.

## Commands

From repository root:

```bash
python .agents/skills/chinese-encoding-guard/scripts/check_encoding.py --paths <file-or-dir>
```

Strict mode (recommended before final delivery):

```bash
python .agents/skills/chinese-encoding-guard/scripts/check_encoding.py --paths <file-or-dir> --strict
```

JSON output for CI/logging:

```bash
python .agents/skills/chinese-encoding-guard/scripts/check_encoding.py --paths <file-or-dir> --strict --json
```

For tracked files only:

```bash
python .agents/skills/chinese-encoding-guard/scripts/check_encoding.py --git-tracked --strict
```

Auto-fix with backup:

```bash
python .agents/skills/chinese-encoding-guard/scripts/fix_to_utf8.py --paths <file-or-dir>
```

Auto-fix tracked files only:

```bash
python .agents/skills/chinese-encoding-guard/scripts/fix_to_utf8.py --git-tracked
```

Auto-fix dry-run:

```bash
python .agents/skills/chinese-encoding-guard/scripts/fix_to_utf8.py --paths <file-or-dir> --dry-run
```

## UTF-8 Safe Editing Rules

- Prefer `apply_patch` when editing non-ASCII text.
- Avoid shell redirection that depends on current code page.
- In PowerShell, always set explicit encoding:
  - `Out-File -Encoding utf8`
  - `Set-Content -Encoding utf8`
- Keep the final encoding as UTF-8.
- Never ignore U+FFFD in review output.

## Decision Rules

- `FAIL`: invalid UTF-8 bytes, decode errors, or U+FFFD.
- `WARN`: suspicious mojibake pattern/token.
- In strict mode, both FAIL and WARN block completion.

## Response Contract

When using this skill, report:
1. Checked files or directories.
2. Whether strict checks passed.
3. Any suspicious lines/tokens found.
4. What was fixed.

## Example Output

```text
Encoding check: PASSED (strict)
Checked files: 12
FAIL: 0, WARN: 0
Notes: No UTF-8 decode errors, no U+FFFD, no mojibake patterns.
```

## One-Command Safe Flow

```bash
python .agents/skills/chinese-encoding-guard/scripts/fix_to_utf8.py --git-tracked && python .agents/skills/chinese-encoding-guard/scripts/check_encoding.py --git-tracked --strict
```
