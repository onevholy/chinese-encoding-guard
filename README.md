# chinese-encoding-guard-skill-cli

NPM-installable CLI wrapper for:
- `scripts/check_encoding.py` (UTF-8 + mojibake detection)
- `scripts/fix_to_utf8.py` (auto-fix to UTF-8 with backups)

## Install

Global install from npm:

```bash
npm install -g chinese-encoding-guard-skill-cli
```

Or run directly with npx:

```bash
npx chinese-encoding-guard-skill-cli check --help
```

## Commands

Check encoding:

```bash
ceg check --paths ./frontend/src --strict
ceg check --git-tracked --strict
```

Auto-fix to UTF-8 (with backups):

```bash
ceg fix --paths ./backend/src/main/resources
ceg fix --git-tracked
ceg fix --paths ./some/file.sql --dry-run
```

One-command safe flow:

```bash
ceg fix --git-tracked && ceg check --git-tracked --strict
```

## Requirements

- Node.js >= 18
- Python 3 available in PATH (`py -3`, `python`, or `python3`)

## Publish

From this folder:

```bash
npm pack --dry-run
npm publish --access public
```

If the package name is already taken, change the `name` in `package.json`.

