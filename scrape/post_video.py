#!/usr/bin/env python3
"""Publish one rendered hook reel to the social-cockpit publish endpoint.

POSTs a local ``output/<slug>/*.mp4`` path to social-cockpit's
``/api/publish/local``, which manages the whole chain server-side (read file ->
upload to R2 -> presign -> call Instagram -> reclaim the object). The hook is
captioned from ``assets/<slug>/title.json`` and posted as a trial reel.

**Exactly one hook is posted per invocation.** Every hook of a slug shares an
identical body and a byte-identical voiceover, so posting them close together
gets the later ones clustered as near-duplicates and throttled to ~no reach
(see ``INSTAGRAM_DEDUP_EVASION_PLAN.md``). ``--min-gap-days`` enforces the
spacing: if the last post went out more recently than that, this exits without
posting — so it is safe to run on a daily schedule, with the gap check deciding
when a hook is actually due.

With no slug it drains the global queue — the oldest unpublished hook across
all of ``output/``. Published hooks are recorded in ``output/.published`` as
``<slug>/<file>.mp4<TAB><iso8601>`` and skipped on re-run, so publishing to
Instagram is never accidentally repeated.

``output/.published`` is shared with ``/schedule-video``, which books hooks into
social-cockpit's scheduler instead of posting them now. It writes the same lines
at booking time, stamped with the hook's future *slot*. So a line here means "this
hook is committed to going out", not strictly "this hook has already gone out" —
which is what stops the two paths from both claiming the same hook. Two
consequences for the code below: the newest timestamp may be in the future, in
which case the gap check holds off until that slot has passed (use
``--ignore-gap`` to post anyway), and a scheduled job that later fails leaves a
line behind that has to be removed before its hook is eligible again.

Timestamps here are naive local time; ``read_published`` converts an
offset-aware one rather than choking on it.

Env (read from the repo-root ``.env``):
  COCKPIT_URL   optional, default http://localhost:3000

Usage:
  .venv/bin/python scrape/post_video.py [<slug>] [--dry-run] [--min-gap-days N]
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

COCKPIT = os.environ.get("COCKPIT_URL", "http://localhost:3000").rstrip("/")
# Days between posts. Two near-identical hooks landing closer than this is what
# tanks the second one's reach.
DEFAULT_MIN_GAP_DAYS = 2
# When automation is attached the cockpit waits up to 5 min for the reel to
# finish processing (so it can return a media_id and attach), so allow headroom.
REQUEST_TIMEOUT_S = 360


def captions_for(slug):
    """Map each rendered file stem -> pretty caption from assets/<slug>/videos.json.

    One entry per rendered video, so a mirrored duplicate (the entry with ``of``) is keyed by
    its own stem and posts under its own caption.
    """
    from reelcut.video_spec import load_videos, stem_for

    return {
        stem_for(v): v.caption
        for v in load_videos(ROOT / "assets" / slug / "videos.json")
        if v.caption
    }


def caption_for(slug, stem):
    """Caption for one rendered file, from its videos.json entry.

    A mirrored duplicate that videos.json doesn't describe is written as its hook's stem plus
    the flip suffix, so an exact miss falls back to the longest stem the filename starts
    with — that copy posts with the same caption as the hook it mirrors.
    """
    titles = captions_for(slug)
    if stem in titles:
        return titles[stem]
    matches = [k for k in titles if stem.startswith(k)]
    return titles[max(matches, key=len)] if matches else stem


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


def read_published(log):
    """Parse output/.published -> (set of published keys, datetime of last post).

    Lines are ``<slug>/<file>.mp4<TAB><iso8601>``. Lines written before
    timestamping was added have no tab and no date; they still count as
    published, they just can't date the last post (so they never hold up the
    gap check).

    Stamps are naive local time. An offset-aware one is converted rather than
    trusted: this file is also written by ``/schedule-video``, and mixing the two
    kinds would raise "can't compare offset-naive and offset-aware datetimes"
    from the gap check — an opaque crash a long way from the line that caused it.
    """
    if not log.exists():
        return set(), None
    keys, last = set(), None
    for line in log.read_text().splitlines():
        if not line.strip():
            continue
        key, _, stamp = line.partition("\t")
        keys.add(key)
        if not stamp:
            continue
        try:
            when = datetime.fromisoformat(stamp)
        except ValueError:
            continue
        if when.tzinfo is not None:
            when = when.astimezone().replace(tzinfo=None)
        if last is None or when > last:
            last = when
    return keys, last


def pending(slug, done):
    """Unpublished hooks as (slug, mp4) pairs, oldest render first.

    Ordering is by mtime so a backlog drains in the order it was rendered. A
    slug's hooks are all written by one render-hooks run, so they stay
    contiguous; the name is a tiebreak to keep the order stable.
    """
    out = ROOT / "output"
    dirs = [out / slug] if slug else sorted(p for p in out.iterdir() if p.is_dir())
    hooks = [
        (d.name, mp4)
        for d in dirs
        for mp4 in sorted(d.glob("*.mp4"))
        if f"{d.name}/{mp4.name}" not in done
    ]
    hooks.sort(key=lambda pair: (pair[1].stat().st_mtime, pair[1].name))
    return hooks


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
    ap.add_argument("slug", nargs="?",
                    help="video slug (an output/<slug>/ folder of rendered hooks). "
                         "Omit to post the oldest unpublished hook across all slugs.")
    ap.add_argument("--dry-run", action="store_true",
                    help="show what would be posted without publishing")
    ap.add_argument("--min-gap-days", type=float, default=DEFAULT_MIN_GAP_DAYS,
                    help=f"minimum days since the last post (default {DEFAULT_MIN_GAP_DAYS}); "
                         "exits without posting if the gap isn't met")
    ap.add_argument("--ignore-gap", action="store_true",
                    help="post now even if the minimum gap hasn't elapsed")
    args = ap.parse_args()

    if args.slug and not (ROOT / "output" / args.slug).is_dir():
        sys.exit(f"No rendered output for slug '{args.slug}' "
                 f"(missing {ROOT / 'output' / args.slug})")

    log = ROOT / "output" / ".published"
    done, last_post = read_published(log)

    queue = pending(args.slug, done)
    if not queue:
        where = f"for '{args.slug}'" if args.slug else "anywhere in output/"
        print(f"Nothing to publish {where} — every hook is already in output/.published.")
        return

    if last_post and not args.ignore_gap:
        due = last_post + timedelta(days=args.min_gap_days)
        if datetime.now() < due:
            print(f"Last post was {last_post:%Y-%m-%d %H:%M}; next hook is due "
                  f"{due:%Y-%m-%d %H:%M} (min gap {args.min_gap_days}d). Nothing posted.")
            print(f"{len(queue)} hook(s) waiting — next up: {queue[0][0]}/{queue[0][1].name}")
            return

    slug, mp4 = queue[0]
    caption = caption_for(slug, mp4.stem)
    automation = automation_for(slug)

    print(f"Will publish 1 hook ({len(queue) - 1} more queued after it):")
    print(f"  - {slug}/{mp4.name}  ->  {caption!r}")

    if automation:
        kws = ", ".join(automation.get("trigger_keywords", [])) or "(none)"
        print(f"\nAutomation: key={automation['key']!r} keywords=[{kws}] "
              f"type={automation.get('template_type', 'comment_to_dm')} "
              f"— all hooks share one flow (created on the first, appended after).")
    else:
        print(f"\nAutomation: none (no assets/{slug}/automation.json) "
              "— posting without an automation.")

    if args.dry_run:
        print("\n(dry run — nothing posted)")
        return

    resp = publish(mp4, caption, automation)
    print(f"\n  published: {caption!r}")
    if automation:
        act = (resp.json().get("automation") or {})
        if act.get("skipped"):
            print(f"  ⚠ automation not attached: {act.get('reason')}")
        else:
            print(f"  automation {act.get('action')} -> flow {act.get('flow_id')} "
                  f"({len(act.get('media_ids', []))} post(s) on it)")
    with log.open("a") as f:
        f.write(f"{slug}/{mp4.name}\t{datetime.now().isoformat(timespec='seconds')}\n")

    if len(queue) > 1:
        nxt = datetime.now() + timedelta(days=args.min_gap_days)
        print(f"\nDone. {len(queue) - 1} hook(s) left; next due {nxt:%Y-%m-%d %H:%M}.")
    else:
        print("\nDone — queue is empty.")


if __name__ == "__main__":
    main()
