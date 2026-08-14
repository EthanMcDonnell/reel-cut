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
spacing by asking **social-cockpit** what is within that window — both what
actually went out and what is booked to go out. So it is safe to run on a daily
schedule, with the calendar deciding when a hook is actually due.

Two separate questions, two separate authorities:

* **"Has this hook been used?"** — ``output/.published``. A key there means the
  hook is spoken for and must never go out again, whether this script posted it
  or ``/schedule-video`` booked it into a future slot. Deleting its line is the
  only way to release it. The timestamp on the line is informational only.
* **"Is now a good time to post?"** — the cockpit's calendar, via
  ``calendar_conflict``. A local text file can't answer this: it doesn't know
  about posts made from the phone, and a slot booked in it is just text.

With no slug it drains the global queue — the oldest unclaimed hook across all
of ``output/``.

One consequence worth knowing: a scheduled job that later fails leaves its line
behind, claiming a hook that never went out. Remove the line to release it.

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
    """Parse output/.published -> set of claimed ``<slug>/<file>.mp4`` keys.

    Lines are ``<slug>/<file>.mp4<TAB><iso8601>``. A key here means the hook is
    spoken for and must never go out again — whether it was posted by this script
    or booked into a future slot by ``/schedule-video``. Removing its line is the
    only way to make a hook eligible again.

    The timestamp is **informational**: a record of when the hook went out or is
    due to. Nothing reads it, because a local text file is the wrong authority on
    what the calendar looks like — ``calendar_conflict`` asks social-cockpit
    instead. Lines written before timestamping was added have no tab and no date,
    which is fine.
    """
    if not log.exists():
        return set()
    return {
        line.partition("\t")[0]
        for line in log.read_text().splitlines()
        if line.strip()
    }


def calendar_conflict(gap_days):
    """Nearest post within ``gap_days`` of now, per social-cockpit. None if clear.

    The cockpit is the authority on the calendar: it knows what actually went out
    (from its media cache) and what is booked to go out (from the scheduler). The
    local ledger knows neither — it can't see posts made from the phone, and a
    booked slot there is just text.

    Returns ``(when, label, kind)`` for the closest conflict, so the caller can
    say precisely what is in the way.
    """
    now = datetime.now()
    window = timedelta(days=gap_days)
    params = {
        "from": int((now - window).timestamp() * 1000),
        "to": int((now + window).timestamp() * 1000),
    }

    found = []
    published = requests.get(f"{COCKPIT}/api/schedule/history", params=params,
                             timeout=30).json()
    for post in published.get("posts", []):
        found.append((datetime.fromtimestamp(post["published_at"] / 1000),
                      post.get("title", "(untitled)"), "published"))

    booked = requests.get(
        f"{COCKPIT}/api/schedule",
        params={**params, "status": "pending,paused,publishing,finalizing", "limit": 1000},
        timeout=30,
    ).json()
    for job in booked.get("jobs", []):
        caption = (job.get("payload") or {}).get("caption") or "(no caption)"
        found.append((datetime.fromtimestamp(job["scheduled_at"] / 1000),
                      caption.split("\n")[0], "scheduled"))

    if not found:
        return None
    return min(found, key=lambda f: abs(f[0] - now))


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
                    help=f"minimum days clear of any other post, published or "
                         f"scheduled (default {DEFAULT_MIN_GAP_DAYS}); exits "
                         "without posting if the gap isn't met")
    ap.add_argument("--ignore-gap", action="store_true",
                    help="post now even if the minimum gap hasn't elapsed")
    args = ap.parse_args()

    if args.slug and not (ROOT / "output" / args.slug).is_dir():
        sys.exit(f"No rendered output for slug '{args.slug}' "
                 f"(missing {ROOT / 'output' / args.slug})")

    log = ROOT / "output" / ".published"
    done = read_published(log)

    queue = pending(args.slug, done)
    if not queue:
        where = f"for '{args.slug}'" if args.slug else "anywhere in output/"
        print(f"Nothing to publish {where} — every hook is already in output/.published.")
        return

    if not args.ignore_gap:
        conflict = calendar_conflict(args.min_gap_days)
        if conflict:
            when, label, kind = conflict
            clear_at = when + timedelta(days=args.min_gap_days)
            print(f"Too close to a {kind} post: {when:%Y-%m-%d %H:%M} {label!r}. "
                  f"Clear after {clear_at:%Y-%m-%d %H:%M} "
                  f"(min gap {args.min_gap_days}d). Nothing posted.")
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
