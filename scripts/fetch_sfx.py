#!/usr/bin/env python3
"""Download CC0 sound effects from Freesound for every entry in sfx_catalog.yaml.

    .venv/bin/python scripts/fetch_sfx.py [--per 3] [name ...]

Searches Freesound's public site (no API key) for CC0 sounds under the entry's max_s,
most-downloaded first, and saves the top `--per` HQ previews to
assets/sfx/catalog/<name>-<n>-<id>.mp3, crediting each in assets/sfx/catalog/SOURCES.md.
Files already on disk are skipped, so it is safe to re-run.
"""

import argparse
import html
import re
import sys
import time
from pathlib import Path

import httpx
import yaml

REPO = Path(__file__).resolve().parent.parent
CATALOG = Path(__file__).with_name("sfx_catalog.yaml")
OUT = REPO / "assets" / "sfx" / "catalog"
SEARCH = "https://freesound.org/search/"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def search(client: httpx.Client, query: str, max_s: float) -> list[dict]:
    """CC0 results for `query` no longer than max_s, most-downloaded first."""
    r = client.get(SEARCH, params={
        "q": query,
        "f": f'license:"Creative Commons 0" duration:[0 TO {max_s}]',
        "s": "Downloads (most first)",
    })
    r.raise_for_status()
    results = []
    for block in re.findall(r'class="bw-player"(.*?)tabindex', r.text, re.S):
        attr = dict(re.findall(r'data-([a-z0-9-]+)="([^"]*)"', block))
        if "mp3" in attr:
            results.append({
                "id": attr["sound-id"],
                "user": attr["username"],
                "title": html.unescape(attr["title"]),
                "mp3": attr["mp3"].replace("-lq.mp3", "-hq.mp3"),
            })
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per", type=int, default=3, help="files per catalog entry")
    ap.add_argument("names", nargs="*", help="only these entries (default: all)")
    args = ap.parse_args()

    entries = yaml.safe_load(CATALOG.read_text())
    if args.names:
        entries = [e for e in entries if e["name"] in args.names]
    OUT.mkdir(parents=True, exist_ok=True)
    sources = OUT / "SOURCES.md"
    if not sources.exists():
        sources.write_text("# CC0 sound effects from freesound.org (HQ previews)\n\n"
                           "| File | Title | Source |\n|---|---|---|\n")

    missing = []
    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=30) as client:
        for e in entries:
            found = search(client, e["query"], e.get("max_s", 6))[:args.per]
            if not found:
                missing.append(e["name"])
            for n, s in enumerate(found):
                path = OUT / f"{e['name']}-{n}-{s['id']}.mp3"
                if path.exists():
                    continue
                path.write_bytes(client.get(s["mp3"]).raise_for_status().content)
                with sources.open("a") as f:
                    f.write(f"| {path.name} | {s['title']} by {s['user']} | "
                            f"https://freesound.org/s/{s['id']}/ |\n")
            print(f"{e['name']:<20} {len(found)} file(s)")
            time.sleep(1)

    if missing:
        print(f"\nNo CC0 match: {', '.join(missing)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
