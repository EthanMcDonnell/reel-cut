---
name: probe-source
description: "Probe a blog/engineering homepage to find the best fetch method (RSS, scrape, or playwright) for adding it to sources.yaml. Triggers on: probe this source, add this blog, what fetch method, check if this has rss."
---

# Probe Source

Discover the best fetch method for a new sources.yaml entry.

## Steps

1. Run the probe script (all 3 methods run in parallel):
```
.venv/bin/python scrape/probe_source.py <homepage-url> [name] [company]
```

2. Read the output — it will print a ready-to-paste YAML snippet under `── Recommendation`.

3. Copy the snippet into the appropriate `scrape/sources-<table>.yaml` (gitignored; format and table naming in `scrape/sources.example.yaml`).

That's it. No edits needed — the script handles RSS discovery, HTTP scraping, and Playwright.
