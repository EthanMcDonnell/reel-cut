# Path Glossary

Single source of truth for the **machine-specific absolute paths** used by the ReelCut command workflows (`produce-script`, `prepare-video`, `produce-video`, `debug-video`, `voice-profile`, `video-ideas`). Commands reference these by `{TOKEN}`; resolve each token to the value below before running. Update a path here **once** and every command picks it up.

Repo-relative paths (`scrape/…`, `assets/<slug>/`, `assets/<slug>/script.md`, `output/`, `series/…`, `.claude/…`, `tests/…`, `config.yaml`) are **not** tokenized — they stay written inline in the commands, resolved against `{PROJECT_ROOT}`.

## Machine-specific absolute paths

| Token | Path |
| --- | --- |
| `{PROJECT_ROOT}` | This repo's root — the git top level (`git rev-parse --show-toplevel`) |
| `{SOCIAL_COCKPIT_DIR}` | The [social-cockpit](https://github.com/EthanMcDonnell/social-cockpit) checkout: the directory two levels above the `mcp/dist/index.js` path in `.mcp.json`; if there's no `.mcp.json`, `../social-cockpit` relative to `{PROJECT_ROOT}` |

Run all `.venv/bin/…` and `scrape/…` commands from `{PROJECT_ROOT}`.

## Service endpoints

| Token | Value | Notes |
| --- | --- | --- |
| `{COCKPIT_URL}` | `http://localhost:3000` | social-cockpit dev server (`npm run dev` in `{SOCIAL_COCKPIT_DIR}`) |
| `{TELEGRAM_API}` | `http://localhost:8765` | Local Telegram bot API server (same one used by `scrape/telegram.py`) |
