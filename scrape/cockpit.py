#!/usr/bin/env python
"""Fetch top-performing posts (full transcripts + insights) from social-cockpit.

This is the data feed for the script pipeline's voice/hook analysis: the user's
own best-performing reels, ranked by a real engagement metric, with the spoken
transcript of each. A Claude command (`/voice-profile`) turns this into the
`proven-hooks.md` and `voice-profile.md` reference artifacts the scripts/hooks
skills read.

Prints a JSON array to stdout, ranked best-first. Run from the repo root:

    .venv/bin/python scrape/cockpit.py --metric engagement --limit 12

Set COCKPIT_URL (env or .env) to point at a non-default host
(default http://localhost:3000).
"""
import argparse
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

BASE = os.environ.get("COCKPIT_URL", "http://localhost:3000").rstrip("/")
METRICS = [
    "likes", "comments", "reach", "views", "saved", "shares",
    "total_interactions", "avg_watch_time", "engagement",
]
INSIGHT_KEYS = (
    "reach", "views", "likes", "comments", "shares", "saved",
    "total_interactions", "ig_reels_avg_watch_time",
)


def fetch_top(metric, limit, media_type):
    params = {"metric": metric, "limit": limit, "fullText": "1"}
    if media_type:
        params["mediaType"] = media_type
    r = requests.get(f"{BASE}/api/scripts/top", params=params, timeout=30)
    r.raise_for_status()
    return r.json().get("data", [])


def transcript_text(item):
    """Full transcript text. Prefers the inline `text` (fullText=1); falls back
    to following the per-post href for a cockpit that predates that param."""
    t = item.get("transcript") or {}
    if t.get("text"):
        return t["text"]
    href = t.get("href")
    if not href:
        return ""
    try:
        r = requests.get(f"{BASE}{href}", timeout=30)
        r.raise_for_status()
    except requests.RequestException:
        return ""
    return (r.json() or {}).get("text", "")


def main():
    ap = argparse.ArgumentParser(
        description="Top-performing posts + transcripts from social-cockpit."
    )
    ap.add_argument("--metric", default="engagement", choices=METRICS)
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument(
        "--type", dest="media_type", default="VIDEO,REEL",
        help="comma-separated media types, or empty string for all",
    )
    args = ap.parse_args()

    try:
        items = fetch_top(args.metric, args.limit, args.media_type)
    except requests.RequestException as e:
        print(
            json.dumps({"error": f"could not reach cockpit at {BASE}: {e}"}),
            file=sys.stderr,
        )
        sys.exit(1)

    out = []
    for rank, it in enumerate(items, 1):
        ins = it.get("insights") or {}
        out.append({
            "rank": rank,
            "metric": args.metric,
            "metricValue": it.get("metricValue"),
            "permalink": it.get("permalink"),
            "caption": it.get("caption"),
            "timestamp": it.get("timestamp"),
            "durationSec": (it.get("transcript") or {}).get("duration"),
            "insights": {k: ins.get(k) for k in INSIGHT_KEYS},
            "transcript": transcript_text(it),
        })
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
