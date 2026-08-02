#!/usr/bin/env python3
"""Publish a slug's rendered hook reels to the social-cockpit publish endpoint.

For each ``output/<slug>/*.mp4`` this POSTs the local file path to social-cockpit's
``/api/publish/local``, which manages the whole chain server-side (read file ->
upload to R2 -> presign -> call Instagram -> reclaim the object). Each hook is
captioned from ``assets/<slug>/title.json`` and posted as a trial reel. One post
per hook variant, spaced by a random 3-7 minute interval so they don't all fire
at once.

Already-published hooks are recorded in ``output/.published`` and skipped on
re-run, so publishing to Instagram is never accidentally repeated.

Env (read from the repo-root ``.env``):
  COCKPIT_URL   optional, default http://localhost:3000

Usage:
  .venv/bin/python scrape/post_video.py <slug> [--dry-run]
"""

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

COCKPIT = os.environ.get("COCKPIT_URL", "http://localhost:3000").rstrip("/")
MIN_INTERVAL_S = 180     # 3 minutes
MAX_INTERVAL_S = 420     # 7 minutes
# When automation is attached the cockpit waits up to 5 min for the reel to
# finish processing (so it can return a media_id and attach), so allow headroom.
REQUEST_TIMEOUT_S = 360


def captions_for(slug):
    """Map each hook slug -> pretty caption from assets/<slug>/title.json."""
    path = ROOT / "assets" / slug / "title.json"
    if not path.exists():
        return {}
    return {e["slug"]: e["title"] for e in json.loads(path.read_text()) if e.get("slug")}


def automation_for(slug):
    """Load the optional per-slug comment automation from assets/<slug>/automation.json.

    Every hook of this slug is a variation of the same video, so they all share a
    single automation flow: the ``key`` defaults to the slug, and the cockpit
    creates the flow on the first hook and appends each later hook to it. Returns
    the spec dict (with ``key`` defaulted), or None when the file is absent — in
    which case hooks post exactly as before, with no automation.
    """
    path = ROOT / "assets" / slug / "automation.json"
    if not path.exists():
        return None
    spec = json.loads(path.read_text())
    spec.setdefault("key", slug)
    return spec


def publish(video_path, caption, automation=None):
    payload = {
        "video_path": str(video_path.resolve()),
        "caption": caption,
        "trial_params": {"graduation_strategy": "MANUAL"},
    }
    if automation:
        payload["automation"] = automation
    r = requests.post(
        f"{COCKPIT}/api/publish/local",
        json=payload,
        timeout=REQUEST_TIMEOUT_S,
    )
    r.raise_for_status()
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug", help="video slug (an output/<slug>/ folder of rendered hooks)")
    ap.add_argument("--dry-run", action="store_true",
                    help="show what would be posted without publishing")
    args = ap.parse_args()

    out_dir = ROOT / "output" / args.slug
    if not out_dir.is_dir():
        sys.exit(f"No rendered output for slug '{args.slug}' (missing {out_dir})")

    mp4s = sorted(out_dir.glob("*.mp4"))
    if not mp4s:
        sys.exit(f"No .mp4 files in {out_dir}")

    captions = captions_for(args.slug)
    automation = automation_for(args.slug)
    log = ROOT / "output" / ".published"
    done = set(log.read_text().splitlines()) if log.exists() else set()

    to_post = []
    for mp4 in mp4s:
        key = f"{args.slug}/{mp4.name}"
        if key in done:
            print(f"skip (already published): {key}")
            continue
        to_post.append((mp4, captions.get(mp4.stem, mp4.stem)))

    if not to_post:
        print("Nothing to publish — every hook is already in output/.published.")
        return

    print(f"Will publish {len(to_post)} hook(s) for '{args.slug}', "
          f"random {MIN_INTERVAL_S//60}-{MAX_INTERVAL_S//60} min apart:")
    for mp4, caption in to_post:
        print(f"  - {mp4.name}  ->  {caption!r}")

    if automation:
        kws = ", ".join(automation.get("trigger_keywords", [])) or "(none)"
        print(f"\nAutomation: key={automation['key']!r} keywords=[{kws}] "
              f"type={automation.get('template_type', 'comment_to_dm')} "
              f"— all hooks share one flow (created on the first, appended after).")
    else:
        print("\nAutomation: none (no assets/"
              f"{args.slug}/automation.json) — posting without an automation.")

    if args.dry_run:
        print("\n(dry run — nothing posted)")
        return

    for i, (mp4, caption) in enumerate(to_post):
        print(f"\n[{i+1}/{len(to_post)}] {mp4.name}")
        resp = publish(mp4, caption, automation)
        print(f"  published: {caption!r}")
        if automation:
            act = (resp.json().get("automation") or {})
            if act.get("skipped"):
                print(f"  ⚠ automation not attached: {act.get('reason')}")
            else:
                print(f"  automation {act.get('action')} -> flow {act.get('flow_id')} "
                      f"({len(act.get('media_ids', []))} post(s) on it)")
        with log.open("a") as f:
            f.write(f"{args.slug}/{mp4.name}\n")

        if i < len(to_post) - 1:
            wait = random.uniform(MIN_INTERVAL_S, MAX_INTERVAL_S)
            print(f"  waiting {wait/60:.1f} min before the next post…")
            time.sleep(wait)

    print(f"\nDone — published {len(to_post)} hook(s).")


if __name__ == "__main__":
    main()
