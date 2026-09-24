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

``--youtube`` adds the cross-post. Every hook is booked with the slug set, so
publishing it enrols the file in that slug's **content pool** in social-cockpit
(see its ``docs/slug-scheduling.md``). The YouTube job carries no file at all --
it books the *pool*, and the cockpit picks the highest-viewed member when the
slot arrives, hours after the last hook went out and earned its numbers. A
candidate already posted to a platform is never picked for that platform again,
so the cross-post can only ever draw a clip YouTube has not seen.

Env (read from the repo-root ``.env``):
  COCKPIT_URL   optional, default http://localhost:3000

``--order`` prints the slug's unclaimed hooks in the order to book them, so the
skill pairs them to slots without two flipped copies landing back to back.

Usage:
  .venv/bin/python scrape/schedule_video.py <slug> --order
  .venv/bin/python scrape/schedule_video.py <slug> <hook.mp4>=<scheduled-at-iso> [...]
      [--youtube <scheduled-at-iso>] [--dry-run]
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

# How the YouTube cross-post picks its video. The pool ranks on real numbers from
# the Instagram run that precedes it, so "most successful" is literally most
# views, summed across every platform a candidate has been posted to.
YT_SELECTION = "most_views"

# The ledger key that claims the cross-post. It is deliberately not an mp4 name:
# a slug job books the *pool*, not a file, so there is no hook to claim -- but
# without a claim a second run of this script would book a second YouTube post
# for the same slug. `read_published` matches on the key alone, and no rendered
# file can ever collide with this one.
YT_LEDGER_KEY = "@youtube"


def parse_pair(raw):
    """``<hook>.mp4=<scheduled-at-iso>`` -> (filename, iso string)."""
    name, sep, when = raw.partition("=")
    if not sep or not name or not when:
        sys.exit(f"Bad hook/time pair {raw!r} — expected <hook>.mp4=<scheduled-at-iso>")
    return name, when


def mirrors_for(slug, stems):
    """Map each flipped hook's stem -> the stem of the hook it mirrors.

    A mirror is known by its videos.json entry's ``of``; one videos.json doesn't
    describe falls back to the longest described stem it starts with, the same
    rule ``caption_for`` uses to caption it.
    """
    from reelcut.video_spec import load_videos, stem_for

    videos = load_videos(ROOT / "assets" / slug / "videos.json")
    by_id = {v.id: v for v in videos}
    by_stem = {stem_for(v): v for v in videos}
    mirrors = {}
    for stem in stems:
        v = by_stem.get(stem)
        if v:
            if v.of:
                mirrors[stem] = stem_for(by_id[v.of])
            continue
        bases = [k for k in by_stem if stem.startswith(k)]
        if bases:
            mirrors[stem] = max(bases, key=len)
    return mirrors


def booking_order(stems, mirrors):
    """Order hooks so flipped copies are spread between the unflipped ones.

    Every hook of a slug gets its own slot, one gap apart, in this order. Taken
    alphabetically, the flipped copies (which carry their own filenames) could
    land back to back. Here the shorter group is spread evenly through the
    longer one, so two flipped hooks only sit side by side when there are more
    of them than unflipped hooks to put between. Of the rotations of the
    flipped list, the first that keeps each copy off its own original's
    neighbouring slots wins (or the one with the fewest such neighbours).
    """
    originals = [s for s in stems if s not in mirrors]
    flipped = [s for s in stems if s in mirrors]

    def clashes(seq):
        return sum(mirrors.get(a) == b or mirrors.get(b) == a for a, b in zip(seq, seq[1:]))

    best = None
    for k in range(max(len(flipped), 1)):
        seq = _spread(originals, flipped[k:] + flipped[:k])
        if best is None or clashes(seq) < clashes(best):
            best = seq
    return best


def _spread(originals, flipped):
    """Interleave the shorter list evenly into the longer, the longer leading."""
    long, short = (originals, flipped) if len(originals) >= len(flipped) else (flipped, originals)
    if not short:
        return list(long)
    after = {j * len(long) // len(short): item for j, item in enumerate(short)}
    out = []
    for i, item in enumerate(long):
        out.append(item)
        if i in after:
            out.append(after[i])
    return out


def title_for(slug):
    """A YouTube title for the slug, from the primary entry in ``videos.json``.

    The cross-post books against the *pool*, so which hook goes out is decided by
    the cockpit hours later -- there is no per-hook title to send. What every hook
    does share is the video itself, and its burned-in title card names it: the
    first entry without ``of`` is the original, the rest are its mirrors. Its
    ``title`` carries "\n" for the card's line breaks, which a YouTube title has
    no use for.

    Without this the cockpit falls back to the candidate's stored title, which an
    Instagram publish never sets (it stores a caption), and then to the file's
    name -- so an untitled cross-post would go out as ``randomness-has-a-receipt``.
    """
    from reelcut.video_spec import load_videos

    videos = load_videos(ROOT / "assets" / slug / "videos.json")
    primary = next((v for v in videos if not v.of), videos[0] if videos else None)
    title = " ".join((primary.title or "").split()) if primary else ""
    return title or slug


def schedule(video_path, caption, scheduled_at, slug, automation=None):
    payload = {
        "scheduled_at": scheduled_at,
        "video_path": str(video_path.resolve()),
        "video": slug,
        # Both facets of the one string: `video` groups the hooks in the calendar,
        # `slug` enrols this file in the slug's content pool when it publishes.
        # The pool is what the YouTube cross-post below later draws from, so
        # dropping this would leave that job with nothing to pick at fire time.
        "slug": slug,
        "caption": caption,
        "trial_params": {"graduation_strategy": "MANUAL"},
    }
    if automation:
        payload["automation"] = automation
    r = requests.post(f"{COCKPIT}/api/schedule", json=payload, timeout=REQUEST_TIMEOUT_S)
    return r


def schedule_youtube(scheduled_at, slug, title, method=YT_SELECTION):
    """Book a YouTube slot against the pool, with no file of its own.

    This is the cross-post: by the time it fires, every hook above has published
    to Instagram and carries real view counts, so ``most_views`` picks the one
    that actually landed. A candidate already posted to YouTube is never picked
    for YouTube again, so this cannot repeat itself if a second slot is ever
    booked on the same slug.

    No automation block: the cockpit attaches automations to Instagram posts
    only, and would drop one here anyway.
    """
    payload = {
        "scheduled_at": scheduled_at,
        "platform": "yt",
        "video": slug,
        "slug": slug,
        "selection_method": method,
        "title": title,
    }
    r = requests.post(f"{COCKPIT}/api/schedule", json=payload, timeout=REQUEST_TIMEOUT_S)
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug", help="video slug (an output/<slug>/ folder of rendered hooks)")
    ap.add_argument("pairs", nargs="*", metavar="hook.mp4=scheduled-at-iso",
                    help="one per hook, in the order agreed with the user")
    ap.add_argument("--order", action="store_true",
                    help="print the unclaimed hooks in booking order, one filename per line, "
                         "and exit")
    ap.add_argument("--youtube", metavar="scheduled-at-iso",
                    help="also book a YouTube cross-post at this time, drawing from the slug's "
                         f"pool by {YT_SELECTION} (normally the last hook's slot + 1 day)")
    ap.add_argument("--dry-run", action="store_true",
                    help="show what would be booked without booking")
    args = ap.parse_args()

    out_dir = ROOT / "output" / args.slug
    if not out_dir.is_dir():
        sys.exit(f"No rendered output for slug '{args.slug}' (missing {out_dir})")

    log = ROOT / "output" / ".published"
    done = read_published(log)

    if args.order:
        stems = [p.stem for p in sorted(out_dir.glob("*.mp4"))
                 if f"{args.slug}/{p.name}" not in done]
        for stem in booking_order(stems, mirrors_for(args.slug, stems)):
            print(f"{stem}.mp4")
        return
    if not args.pairs:
        ap.error("give <hook>.mp4=<scheduled-at-iso> pairs, or --order")

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

    if args.youtube:
        book_youtube(args, log, done, booked, failed)

    if args.dry_run:
        return

    print(f"\nBooked {len(booked)}, failed {len(failed)}.")
    if failed:
        print(f"Not claimed in output/.published: {', '.join(failed)}")


def book_youtube(args, log, done, booked, failed):
    """Book the cross-post, after the hooks, and claim it in the ledger.

    Ordered last on purpose: the hooks are what fill the pool, and a run that
    books none of them has nothing to cross-post. It is still booked when some
    hooks fail -- the pool only needs one candidate, and the ones that did book
    will have published long before this slot arrives.
    """
    key = f"{args.slug}/{YT_LEDGER_KEY}"
    if key in done:
        print(f"  ✗ {key}: already in output/.published — skipping")
        failed.append(key)
        return

    title = title_for(args.slug)
    if args.dry_run:
        print(f"  (dry run) would book {key} at {args.youtube} "
              f"-> {title!r} by {YT_SELECTION}")
        return

    resp = schedule_youtube(args.youtube, args.slug, title)
    if resp.status_code >= 400:
        print(f"  ✗ {key} at {args.youtube}: {resp.status_code} {resp.text[:200]}")
        failed.append(key)
        return

    job = resp.json().get("job", {})
    print(f"  ✓ {key} at {args.youtube} -> job {job.get('id')} ({job.get('status')}) "
          f"— {title!r}, picks by {YT_SELECTION} at fire time")
    with log.open("a") as f:
        f.write(f"{key}\t{args.youtube}\n")
    booked.append(key)


if __name__ == "__main__":
    main()
