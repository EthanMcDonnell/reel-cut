#!/usr/bin/env python3
"""Book already-decided slots for a slug's rendered hooks into social-cockpit's scheduler.

Companion to ``/schedule-video``. That skill decides *when* each hook goes out —
walking ``suggest_slots`` one call per hook, which needs the cockpit's calendar
and the same-video-gap policy, so it stays a conversational MCP step. This
script decides *what* gets sent for each hook: the caption (``videos.json``)
and the automation block (``automation_spec.py``), built the same way
``post_video.py`` already builds them for ``/post-video``.

The point is to remove a step that used to be manual: an agent reading
``validate_automation.py --spec``'s printed JSON and hand-typing it into a
``schedule_posts`` tool call. That step dropped ``template_type`` on a live
video's automation once (see the ``claude-text-watermark`` incident) because
nothing forced the retyped JSON to match the printed one. POSTing directly to
``/api/schedule`` with a payload built in Python removes the retyping
entirely — there is nothing per-hook to transcribe by hand anymore, only a
slug and a list of ``<hook>.mp4=<scheduled-at-iso>`` pairs already agreed with
the user in Step 4.

Each hook is its own request: one succeeding and the next failing (e.g. a
``day_full`` conflict) doesn't roll back the ones already booked, matching
``schedule_posts``'s per-entry semantics. A successfully booked hook is
appended to ``output/.published`` immediately, so a partial run leaves the
ledger consistent with what the cockpit actually holds.

Env (read from the repo-root ``.env``):
  COCKPIT_URL   optional, default http://localhost:3000

Usage:
  .venv/bin/python scrape/schedule_video.py <slug> <hook.mp4>=<scheduled-at-iso> [...] [--dry-run]
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
from post_video import automation_for, caption_for, read_published  # noqa: E402

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

COCKPIT = os.environ.get("COCKPIT_URL", "http://localhost:3000").rstrip("/")
REQUEST_TIMEOUT_S = 30


def parse_pair(raw):
    """``<hook>.mp4=<scheduled-at-iso>`` -> (filename, iso string)."""
    name, sep, when = raw.partition("=")
    if not sep or not name or not when:
        sys.exit(f"Bad hook/time pair {raw!r} — expected <hook>.mp4=<scheduled-at-iso>")
    return name, when


def schedule(video_path, caption, scheduled_at, slug, automation=None):
    payload = {
        "scheduled_at": scheduled_at,
        "video_path": str(video_path.resolve()),
        "video": slug,
        "caption": caption,
        "trial_params": {"graduation_strategy": "MANUAL"},
    }
    if automation:
        payload["automation"] = automation
    r = requests.post(f"{COCKPIT}/api/schedule", json=payload, timeout=REQUEST_TIMEOUT_S)
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug", help="video slug (an output/<slug>/ folder of rendered hooks)")
    ap.add_argument("pairs", nargs="+", metavar="hook.mp4=scheduled-at-iso",
                    help="one per hook, in the order agreed with the user")
    ap.add_argument("--dry-run", action="store_true",
                    help="show what would be booked without booking")
    args = ap.parse_args()

    out_dir = ROOT / "output" / args.slug
    if not out_dir.is_dir():
        sys.exit(f"No rendered output for slug '{args.slug}' (missing {out_dir})")

    log = ROOT / "output" / ".published"
    done = read_published(log)

    automation = automation_for(args.slug)
    if automation:
        kws = ", ".join(automation.get("trigger_keywords", [])) or "(none)"
        print(f"Automation: key={automation['key']!r} keywords=[{kws}] "
              f"type={automation['template_type']} "
              "— all hooks share one flow (created on the first, appended after).")
    else:
        print(f"Automation: none (no assets/{args.slug}/automation.json) "
              "— booking without an automation.")

    booked, failed = [], []
    for raw in args.pairs:
        name, when = parse_pair(raw)
        key = f"{args.slug}/{name}"
        mp4 = out_dir / name
        if not mp4.is_file():
            print(f"  ✗ {key}: no such rendered file")
            failed.append(key)
            continue
        if key in done:
            print(f"  ✗ {key}: already in output/.published — skipping")
            failed.append(key)
            continue

        caption = caption_for(args.slug, mp4.stem)
        if args.dry_run:
            print(f"  (dry run) would book {key} at {when} -> {caption!r}")
            continue

        resp = schedule(mp4, caption, when, args.slug, automation)
        if resp.status_code >= 400:
            print(f"  ✗ {key} at {when}: {resp.status_code} {resp.text[:200]}")
            failed.append(key)
            continue

        job = resp.json().get("job", {})
        print(f"  ✓ {key} at {when} -> job {job.get('id')} ({job.get('status')})")
        with log.open("a") as f:
            f.write(f"{key}\t{when}\n")
        booked.append(key)

    if args.dry_run:
        return

    print(f"\nBooked {len(booked)}, failed {len(failed)}.")
    if failed:
        print(f"Not claimed in output/.published: {', '.join(failed)}")


if __name__ == "__main__":
    main()
