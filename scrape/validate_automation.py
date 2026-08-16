#!/usr/bin/env python3
"""Check a slug's ``assets/<slug>/automation.json`` before anything posts.

The file holds two fields -- the trigger keyword and the reward -- and
``automation_spec.py`` expands them into the full spec. So there are two ways it
can be wrong, and both are silent until a live post has already gone out:

* the **file** is wrong -- no keyword, a keyword that is a phrase rather than a
  word, a reward with nothing in it;
* the **constants** have gone stale -- a reply function or DM pack renamed in
  social-cockpit. Nothing rejects an unknown pack name; the flow is created,
  fires, and sends an empty message.

So the constants are checked against the cockpit rather than trusted:
``/api/automation-reply-functions`` and ``/api/follow-dm-functions`` list what
actually exists.

With ``--spec`` the resolved spec is printed to stdout on success, which is how
``/schedule-video`` gets the block it hands to ``schedule_posts`` without
composing it by hand.

Exit code is 0 when clean, 1 when anything failed. Warnings never fail the run.

Usage:
  .venv/bin/python scrape/validate_automation.py <slug> [--spec]
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
import automation_spec as spec_mod  # noqa: E402

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

COCKPIT = os.environ.get("COCKPIT_URL", "http://localhost:3000").rstrip("/")
URL_RE = re.compile(r"https?://\S+")


def fetch_names(path):
    """The ``name`` of everything the cockpit lists at ``path``."""
    resp = requests.get(f"{COCKPIT}{path}", timeout=10)
    resp.raise_for_status()
    return [entry["name"] for entry in resp.json()]


def check_constants():
    """Confirm the packs automation_spec.py names still exist in the cockpit."""
    errors = []
    for path, value, field in (
        ("/api/automation-reply-functions", spec_mod.COMMENT_REPLY_FN, "comment_reply_fn"),
        ("/api/follow-dm-functions", spec_mod.DM_PACK, "dm_pack"),
    ):
        names = fetch_names(path)
        if value not in names:
            errors.append(f"{field} {value!r} no longer exists in social-cockpit "
                          f"(it lists: {', '.join(names)}) — fix scrape/automation_spec.py")
    return errors


def check_file(raw):
    """Validate the two per-video fields. Returns (errors, warnings)."""
    errors, warnings = [], []

    keywords = raw.get("trigger_keywords") or []
    if not keywords:
        errors.append("trigger_keywords is missing — the automation has nothing to fire on")
    for keyword in keywords:
        if not isinstance(keyword, str) or not keyword.strip():
            errors.append(f"trigger keyword {keyword!r} must be a non-empty string")
        elif re.search(r"\s", keyword.strip()):
            errors.append(f"trigger keyword {keyword!r} must be a single word — the worker "
                          "matches it as a substring of any comment of ten words or fewer")

    reward = raw.get("follower_message") or ""
    if not isinstance(reward, str) or not reward.strip():
        errors.append("follower_message is missing — a confirmed follower would be sent nothing")
    elif not URL_RE.search(reward):
        warnings.append("follower_message carries no URL — the reward exists to deliver the "
                        "resources, so check that is deliberate")

    # Anything else in the file is a constant somebody has tried to override.
    extra = set(raw) - {"trigger_keywords", "follower_message"}
    for field in sorted(extra):
        errors.append(f"{field} is not a per-video field — the rest of the spec is fixed in "
                      "scrape/automation_spec.py, so remove it")

    return errors, warnings


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("slug")
    parser.add_argument("--spec", action="store_true",
                        help="print the resolved spec to stdout when it validates")
    args = parser.parse_args()

    raw = spec_mod.load(args.slug)
    if raw is None:
        # The correct result for a series with no keyword — not a failure.
        print(f"No assets/{args.slug}/automation.json — this slug posts without an automation.",
              file=sys.stderr)
        return 0

    errors, warnings = check_file(raw)

    try:
        errors += check_constants()
    except requests.RequestException as exc:
        print(f"✗ Could not reach the cockpit at {COCKPIT}: {exc}", file=sys.stderr)
        print("  Start it and re-run — the packs can't be checked without it.", file=sys.stderr)
        return 1

    for warning in warnings:
        print(f"⚠ {warning}", file=sys.stderr)
    for error in errors:
        print(f"✗ {error}", file=sys.stderr)

    if errors:
        print(f"\n{len(errors)} problem(s) in assets/{args.slug}/automation.json.", file=sys.stderr)
        return 1

    resolved = spec_mod.build(args.slug, raw)
    print(f"✓ assets/{args.slug}/automation.json is valid: "
          f"{spec_mod.TEMPLATE_TYPE}, keywords {', '.join(raw['trigger_keywords'])}",
          file=sys.stderr)
    if args.spec:
        print(json.dumps(resolved, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
