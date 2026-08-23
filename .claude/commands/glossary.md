# Path Glossary

Single source of truth for the **machine-specific absolute paths** used by the ReelCut command workflows (`produce-script`, `prepare-video`, `produce-video`, `debug-video`, `voice-profile`, `video-ideas`). Commands reference these by `{TOKEN}`; resolve each token to the value below before running. Update a path here **once** and every command picks it up.

Repo-relative paths (`scrape/…`, `assets/<slug>/`, `assets/<slug>/script.md`, `output/`, `series/…`, `.claude/…`, `tests/…`, `config.yaml`) are **not** tokenized — they stay written inline in the commands, resolved against `{PROJECT_ROOT}`.

## Machine-specific absolute paths

| Token | Path |
| --- | --- |
| `{PROJECT_ROOT}` | `/Users/ethanmcdonnell/Development/reel-cut` |
| `{SOCIAL_COCKPIT_DIR}` | `/Users/ethanmcdonnell/Development/social-cockpit` |

Run all `.venv/bin/…` and `scrape/…` commands from `{PROJECT_ROOT}`.

## Service endpoints

| Token | Value | Notes |
| --- | --- | --- |
| `{COCKPIT_URL}` | `http://localhost:3000` | social-cockpit dev server (`npm run dev` in `{SOCIAL_COCKPIT_DIR}`) |
| `{TELEGRAM_API}` | `http://localhost:8765` | Local Telegram bot API server (same one used by `scrape/telegram.py`) |
