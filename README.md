# chinese-encoding-guard

Chinese encoding protection skill with:
- UTF-8 + mojibake detection
- Auto-fix to UTF-8 with backups

## One-command skill install (recommended)

Install directly as a Claude/Codex skill:

```bash
npx skills add https://github.com/onevholy/chinese-encoding-guard --skill chinese-encoding-guard
```

## Optional: install as npm CLI

```bash
npm install -g chinese-encoding-guard-skill-cli
```

Then run:

```bash
ceg check --paths ./frontend/src --strict
ceg fix --git-tracked
```

## Skill location

The installable skill files are in:

`skills/chinese-encoding-guard/`

