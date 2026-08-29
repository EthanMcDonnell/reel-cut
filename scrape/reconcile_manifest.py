#!/usr/bin/env python3
"""
Reconcile a screenshot manifest against the delivered script.

The manifest (manifest.json, written by screenshot.py at produce-script time)
maps each captured screenshot to a `script_context` — the verbatim script line
it is meant to be shown under. produce-video uses that `script_context` to place
the screenshot on the timeline. But the script keeps moving after the manifest is
written (re-records, retranscription, edits), so the `script_context` lines drift
away from what was actually said and screenshots end up anchored to lines that no
longer exist.

This re-aligns the manifest to the current transcript (captions.json):

  1. CONTEXT FIX (auto-applied)  — for each screenshot, find the closest run of
     words in the transcript and rewrite `script_context` to that verbatim span.
  2. ORPHANED (flagged only)     — screenshots whose best match is too weak; the
     line they supported was likely cut. Left untouched for a human to re-shoot
     or drop.
  3. UNSUPPORTED (flagged only)  — claim-bearing script sentences (numbers, %,
     $, money words) that no screenshot covers; candidates for a new screenshot.

Usage:
  python scrape/reconcile_manifest.py --slug <video-slug>
  python scrape/reconcile_manifest.py --slug <video-slug> --dry-run

Output (stdout): JSON report of the three buckets.
"""

import argparse
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).parent.parent

# Below this token-similarity ratio, a screenshot's context has no good home in
# the current transcript — treat it as orphaned rather than forcing a placement.
MATCH_THRESHOLD = 0.6

# Terminal punctuation that ends a transcript sentence.
_SENT_END = re.compile(r"[.!?]$")
# A sentence carries a checkable claim worth on-screen evidence if it names a
# number, percentage, or money figure.
_CLAIM = re.compile(r"\d|%|\$|\b(?:million|billion|trillion|percent)\b", re.I)


def _norm(s: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace — for fuzzy compare."""
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def _best_window(context: str, tokens: list[str]) -> tuple[float, int, int]:
    """Slide a window over the transcript; return (ratio, start, end) of the
    span whose normalized text best matches `context`. Window sizes flex around
    the context length so a slightly re-worded line still locks on."""
    ctx_norm = _norm(context)
    ctx_len = len(ctx_norm.split())
    if ctx_len == 0:
        return 0.0, 0, 0
    best = (0.0, 0, 0)
    for size in {max(1, ctx_len - 2), ctx_len, ctx_len + 2}:
        for i in range(0, max(1, len(tokens) - size + 1)):
            window = tokens[i : i + size]
            ratio = SequenceMatcher(None, ctx_norm, _norm(" ".join(window))).ratio()
            if ratio > best[0]:
                best = (ratio, i, i + size)
    return best


def _anchor_missing(trigger: str, context: str) -> bool:
    """True if `trigger` can no longer be found inside `context`.

    `/produce-video` bounds a screenshot's on-screen window by locating the trigger
    words *within* the script_context span, and silently spans the whole line when it
    cannot. Rewriting the context can trim a trigger off its edge, so the screenshot
    widens with nothing said. Compared on normalized token sequences, because the
    rewritten context comes from transcript tokens that carry punctuation the
    hand-written trigger does not ("ASCII," vs "ASCII").
    """
    if not trigger.strip():
        return False                      # empty is the documented "no anchor" value
    needle, hay = _norm(trigger).split(), _norm(context).split()
    if not needle:
        return False
    return not any(hay[i : i + len(needle)] == needle for i in range(len(hay) - len(needle) + 1))


def _sentences(tokens: list[str]) -> list[tuple[int, int, str]]:
    """Split tokens into (start, end, text) sentences on terminal punctuation."""
    out, start = [], 0
    for i, tok in enumerate(tokens):
        if _SENT_END.search(tok):
            out.append((start, i + 1, " ".join(tokens[start : i + 1])))
            start = i + 1
    if start < len(tokens):
        out.append((start, len(tokens), " ".join(tokens[start:])))
    return out


def reconcile(slug: str, dry_run: bool) -> dict:
    asset_dir = ROOT / "assets" / slug
    manifest_path = asset_dir / "manifest.json"
    if not manifest_path.exists():
        return {"error": f"no manifest.json in {asset_dir}"}

    captions = sorted(asset_dir.glob("*.captions.json"))
    if not captions:
        return {"error": f"no .captions.json in {asset_dir}"}
    words = json.loads(captions[0].read_text())["words"]
    tokens = [w["word"] for w in words]

    manifest = json.loads(manifest_path.read_text())

    fixed, orphaned, lost_anchors, covered = [], [], [], set()
    for source in manifest:
        for shot in source.get("screenshots", []):
            old = shot.get("script_context", "")
            ratio, lo, hi = _best_window(old, tokens)
            if ratio >= MATCH_THRESHOLD:
                new = " ".join(tokens[lo:hi])
                covered.update(range(lo, hi))
                if new != old:
                    shot["script_context"] = new
                    fixed.append({"file": shot.get("file"), "ratio": round(ratio, 2),
                                  "old": old, "new": new})
                # The window can land off one edge of the old line and strip a trigger
                # with it. produce-video then spans the whole sentence instead of the
                # claim, and nothing reports the difference — so name it here.
                gone = [
                    field for field in ("trigger_show_word", "trigger_go_away_word")
                    if _anchor_missing(shot.get(field, ""), new)
                ]
                if gone:
                    lost_anchors.append({"file": shot.get("file"), "anchors": gone,
                                         "script_context": new,
                                         **{f: shot.get(f, "") for f in gone}})
            else:
                orphaned.append({"file": shot.get("file"), "ratio": round(ratio, 2),
                                 "script_context": old, "article_snippet": shot.get("article_snippet"),
                                 "closest": " ".join(tokens[lo:hi])})

    unsupported = [
        text for (s, e, text) in _sentences(tokens)
        if _CLAIM.search(text) and not (covered & set(range(s, e)))
    ]

    if not dry_run and fixed:
        manifest_path.write_text(json.dumps(manifest, indent=2))

    return {
        "slug": slug,
        "dry_run": dry_run,
        "context_fixed": fixed,
        "orphaned": orphaned,
        "lost_anchors": lost_anchors,
        "unsupported_claims": unsupported,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Reconcile a screenshot manifest against the transcript.")
    ap.add_argument("--slug", required=True, help="video slug under assets/")
    ap.add_argument("--dry-run", action="store_true", help="report only; do not write the manifest")
    args = ap.parse_args()
    result = reconcile(args.slug, args.dry_run)
    print(json.dumps(result, indent=2))
    sys.exit(1 if "error" in result else 0)


if __name__ == "__main__":
    main()
