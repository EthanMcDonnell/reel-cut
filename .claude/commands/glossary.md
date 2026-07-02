# Path Glossary

Single source of truth for the **machine-specific absolute paths** used by the ReelCut
command workflows (`produce-script`, `prepare-video`, `produce-video`, `debug-video`,
`voice-profile`). Commands reference these by `{TOKEN}`; resolve each token to the value
below before running. Update a path here **once** and every command picks it up.

Repo-relative paths (`scrape/…`, `assets/<slug>/`, `output/`, `series/…`, `.claude/…`,
`tests/…`, `config.yaml`) are **not** tokenized — they stay written inline in the commands,
resolved against `{PROJECT_ROOT}`.

## Machine-specific absolute paths

| Token | Path |
| --- | --- |
| `{PROJECT_ROOT}` | `/Users/ethanmcdonnell/Development/reel-cut` |
| `{VAULT_VIDEO_IDEAS}` | `/Users/ethanmcdonnell/Library/Mobile Documents/iCloud~md~obsidian/Documents/Vault/Videos/Video Ideas/` |
| `{VAULT_VIDEOS_TODO}` | `/Users/ethanmcdonnell/Library/Mobile Documents/iCloud~md~obsidian/Documents/Vault/Videos/Videos To Do/` |
| `{SOCIAL_COCKPIT_DIR}` | `~/Documents/social-cockpit` |

Run all `.venv/bin/…` and `scrape/…` commands from `{PROJECT_ROOT}`.

## Service endpoints

| Token | Value | Notes |
| --- | --- | --- |
| `{COCKPIT_URL}` | `http://localhost:3000` | social-cockpit dev server (`npm run dev` in `{SOCIAL_COCKPIT_DIR}`) |
| `{TELEGRAM_API}` | `http://localhost:8765` | Local Telegram bot API server (same one used by `scrape/telegram.py`) |
