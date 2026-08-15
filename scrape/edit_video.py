#!/usr/bin/env python3
"""
Trim spans out of an already-prepared video, without re-transcribing.

After /prepare-video has run, exactly one field in the pipeline is safe to change:
`edl[i].keep`. Word timings, `source_clips` and the `words` array are load-bearing —
the render and the EDL are both timed off them. So this tool does one thing: it
splits the EDL at word boundaries and flips the enclosed span to `keep: false`.

Why cuts are restricted to the tail:
  `videos.json` hook windows are **output-timeline** seconds. Removing anything
  before the body ends shifts every later word earlier, so the burned-in title
  cards would silently land on the wrong words. A cut that starts after the last
  hook window moves nothing upstream of it, so it is always safe.

Usage:
  python scrape/edit_video.py --slug <video-slug>                  # gate + word report
  python scrape/edit_video.py --slug <video-slug> --cut 82.2-88.0  # apply (repeatable)
  python scrape/edit_video.py --slug <video-slug> --cut 82.2-88.0 --dry-run

Times are **source-clip seconds** (the same units as `words` and `edl`).
Boundaries falling inside a word are snapped outwards to that word's edges, so a
cut can never leave half a word behind.

Output (stdout): JSON report.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from reelcut.captions_doc import EdlEntry, load_captions_doc, save_captions_doc
from reelcut.cli import _build_edl_remap
from reelcut.video_spec import load_videos

ROOT = Path(__file__).parent.parent

CUT_REASON = "manual-cut"
SLIVER_REASON = "sliver-absorbed"

# A keep span shorter than this cannot be extracted: h264_videotoolbox fails to open
# an encoder at all ("Could not open encoder before EOF"), which kills the whole render.
MIN_KEEP_S = 0.1


def _fail(msg: str, **extra) -> dict:
    return {"error": msg, **extra}


def _gate(slug: str) -> tuple[dict | None, Path | None]:
    """Verify the slug has been through /prepare-video and /produce-video.

    Returns (error_report, captions_path) — exactly one of the two is None.
    """
    folder = ROOT / "assets" / slug
    if not folder.is_dir():
        return _fail(f"no such slug folder: assets/{slug}"), None

    captions = sorted(folder.glob("*.captions.json"))
    if not captions:
        return _fail(
            f"assets/{slug} has no .captions.json — run /prepare-video {slug} first"
        ), None
    if len(captions) > 1:
        return _fail(
            f"assets/{slug} has {len(captions)} .captions.json files; expected exactly one",
            files=[p.name for p in captions],
        ), None

    doc = load_captions_doc(captions[0])
    if not doc.edl or not doc.words:
        return _fail(
            f"{captions[0].name} has an empty edl/words — /prepare-video did not complete"
        ), None

    videos = load_videos(folder / "videos.json")
    if not any(v.title for v in videos):
        return _fail(
            f"assets/{slug}/videos.json has no titled entries — run /produce-video {slug} first"
        ), None

    return None, captions[0]


def _last_hook_end(folder: Path) -> float | None:
    """Output-timeline second at which the last hook window closes.

    Base entries only — a mirror (`of`) inherits its hook's window. Returns None
    when no entry carries a window, which makes the tail guard uncomputable.
    """
    ends = [v.end for v in load_videos(folder / "videos.json") if not v.of and v.end > 0]
    return max(ends) if ends else None


def _snap(cut_start: float, cut_end: float, words: list) -> tuple[float, float, list]:
    """Widen a cut so neither boundary falls strictly inside a word.

    A boundary inside a word would render a clipped syllable, so the word is
    taken whole instead. Returns (start, end, snaps) — `snaps` describes each
    adjustment for the report.
    """
    snaps = []
    for w in words:
        if w.start < cut_start < w.end:
            snaps.append({"boundary": "start", "from": cut_start, "to": w.start, "word": w.word})
            cut_start = w.start
        if w.start < cut_end < w.end:
            snaps.append({"boundary": "end", "from": cut_end, "to": w.end, "word": w.word})
            cut_end = w.end
    return cut_start, cut_end, snaps


def _apply_cut(edl: list[EdlEntry], cut_start: float, cut_end: float) -> list[EdlEntry]:
    """Split the EDL at the cut boundaries and flip the enclosed spans to keep=False.

    The EDL is a flat contiguous list, so every span is either untouched, wholly
    inside the cut, or split into the pieces that fall outside it.
    """
    out: list[EdlEntry] = []
    for e in edl:
        if e.end <= cut_start or e.start >= cut_end:
            out.append(e)
            continue
        if e.start < cut_start:
            out.append(EdlEntry(e.source_clip, e.start, cut_start, e.keep, e.reason))
        out.append(
            EdlEntry(
                e.source_clip,
                max(e.start, cut_start),
                min(e.end, cut_end),
                False,
                CUT_REASON,
            )
        )
        if e.end > cut_end:
            out.append(EdlEntry(e.source_clip, cut_end, e.end, e.keep, e.reason))
    return out


def _absorb_slivers(
    edl: list[EdlEntry], tail_start: float
) -> tuple[list[EdlEntry], list[dict]]:
    """Flip keep spans too short to render into the cut.

    A cut boundary landing a few ms inside a keep span leaves a remnant of that
    span behind — 10ms of silence is enough. The encoder cannot open a segment
    that short, so the render dies with an error that never names the segment.

    Only the tail is swept. A sliver before `tail_start` predates the cut and is
    already rendering fine, and removing it would shift the output timeline out
    from under the burned-in title cards.
    """
    out, absorbed = [], []
    for e in edl:
        if e.keep and e.start >= tail_start and e.end - e.start < MIN_KEEP_S:
            absorbed.append(
                {"start": e.start, "end": e.end, "duration": round(e.end - e.start, 3)}
            )
            out.append(EdlEntry(e.source_clip, e.start, e.end, False, SLIVER_REASON))
        else:
            out.append(e)
    return out, absorbed


def _durations(edl: list[EdlEntry]) -> tuple[float, float]:
    keep = sum(e.end - e.start for e in edl if e.keep)
    cut = sum(e.end - e.start for e in edl if not e.keep)
    return round(keep, 3), round(cut, 3)


def _orphaned_images(folder: Path, cuts: list[tuple[float, float]]) -> list[dict]:
    """Overlays whose window intersects a cut — they will silently vanish from the render."""
    path = folder / "images.json"
    if not path.exists():
        return []
    entries = json.loads(path.read_text() or "[]")
    hits = []
    for img in entries:
        s, e = float(img.get("start", 0)), float(img.get("end", 0))
        for cs, ce in cuts:
            if s < ce and e > cs:
                hits.append({
                    "type": img.get("type"),
                    "name": img.get("name") or Path(img.get("path", "")).name,
                    "start": s,
                    "end": e,
                })
                break
    return hits


def _parse_cut(spec: str) -> tuple[float, float]:
    lo, _, hi = spec.partition("-")
    return float(lo), float(hi)


def _write_editlog(captions_path: Path, slug: str, report: dict) -> Path:
    """Append this edit to <clip-stem>.debug.8.editlog.txt (8 sorts after prepare's fixlog)."""
    stem = captions_path.name[: -len(".captions.json")]
    log = captions_path.parent / f"{stem}.debug.8.editlog.txt"
    before_k, before_c = report["keep_s_before"], report["cut_s_before"]
    after_k, after_c = report["keep_s_after"], report["cut_s_after"]

    lines = [
        f"EDIT LOG — {slug}",
        f"run: {datetime.now().isoformat(timespec='seconds')}   clip: {stem}",
        f"keep/cut duration:  before {before_k}s / {before_c}s  →  "
        f"after {after_k}s / {after_c}s   (Δ {round(after_k - before_k, 3)}s kept)",
        "",
        f"CUTS APPLIED ({len(report['cuts'])})",
    ]
    for c in report["cuts"]:
        lines.append(f"  {c['start']:.3f}s → {c['end']:.3f}s  ({c['duration']}s)   {c['text']}")
        for s in c["snapped"]:
            lines.append(
                f"      snapped {s['boundary']} {s['from']:.3f} → {s['to']:.3f} "
                f"(mid-word '{s['word']}')"
            )
    if report["absorbed_slivers"]:
        lines += [
            "",
            f"KEEP SLIVERS ABSORBED ({len(report['absorbed_slivers'])}) "
            f"— remnants under {MIN_KEEP_S}s, too short for the encoder to open",
        ]
        for s in report["absorbed_slivers"]:
            lines.append(f"  {s['start']:.3f}s → {s['end']:.3f}s  ({s['duration']}s)")
    if report["orphaned_images"]:
        lines += ["", f"OVERLAYS REMOVED BY THESE CUTS ({len(report['orphaned_images'])})"]
        for img in report["orphaned_images"]:
            lines.append(f"  {img['start']:.3f}s → {img['end']:.3f}s  {img['type']}  {img['name']}")
    lines.append("")

    with log.open("a") as fh:
        fh.write("\n".join(lines) + "\n")
    return log


def edit(slug: str, cut_specs: list[str], dry_run: bool) -> dict:
    err, captions_path = _gate(slug)
    if err:
        return err
    folder = captions_path.parent

    doc = load_captions_doc(captions_path)
    remap, _ = _build_edl_remap(doc.edl)
    keep_before, cut_before = _durations(doc.edl)

    hook_end = _last_hook_end(folder)
    # Earliest source-clip second a cut may start at: the first kept word that
    # lands at or after the last hook window closes.
    tail_start = None
    if hook_end is not None:
        for w in doc.words:
            if remap(w.source_clip, w.start) >= hook_end:
                tail_start = w.start
                break

    if not cut_specs:
        return {
            "slug": slug,
            "captions": str(captions_path.relative_to(ROOT)),
            "keep_s": keep_before,
            "cut_s": cut_before,
            "last_hook_end_output_s": hook_end,
            "earliest_cuttable_source_s": tail_start,
            "words": [
                {
                    "source_s": w.start,
                    "end_s": w.end,
                    "output_s": remap(w.source_clip, w.start),
                    "word": w.word,
                    "cuttable": tail_start is not None and w.start >= tail_start,
                }
                for w in doc.words
            ],
        }

    if hook_end is None:
        return _fail(
            "no hook windows in videos.json (every base entry has end=0), so the "
            "tail guard cannot be computed — re-run /produce-video to fill them in"
        )
    if tail_start is None:
        return _fail(
            f"no kept word lands after the last hook window ({hook_end}s output) — "
            "there is nothing after the hooks to cut"
        )

    edl = list(doc.edl)
    applied = []
    for spec in cut_specs:
        try:
            cs, ce = _parse_cut(spec)
        except ValueError:
            return _fail(f"bad --cut '{spec}': expected START-END in source-clip seconds")
        if ce <= cs:
            return _fail(f"bad --cut '{spec}': end must be greater than start")
        cs, ce, snaps = _snap(cs, ce, doc.words)
        if cs < tail_start:
            return _fail(
                f"cut {cs}-{ce} starts before the body ends. Cuts must begin at or after "
                f"{tail_start}s (source), where the last hook window closes — an earlier cut "
                f"would shift the output timeline and slide every burned-in title card onto "
                f"the wrong words. Re-run /produce-video to re-time the cards if you need this."
            )
        edl = _apply_cut(edl, cs, ce)
        applied.append({
            "start": cs,
            "end": ce,
            "duration": round(ce - cs, 3),
            "snapped": snaps,
            "text": " ".join(w.word for w in doc.words if w.start >= cs and w.end <= ce),
        })

    edl, absorbed = _absorb_slivers(edl, tail_start)

    keep_after, cut_after = _durations(edl)
    report = {
        "slug": slug,
        "captions": str(captions_path.relative_to(ROOT)),
        "dry_run": dry_run,
        "cuts": applied,
        "absorbed_slivers": absorbed,
        "keep_s_before": keep_before,
        "cut_s_before": cut_before,
        "keep_s_after": keep_after,
        "cut_s_after": cut_after,
        "orphaned_images": _orphaned_images(folder, [(c["start"], c["end"]) for c in applied]),
    }

    if not dry_run:
        doc.edl = edl
        save_captions_doc(doc, captions_path)
        report["editlog"] = str(_write_editlog(captions_path, slug, report).relative_to(ROOT))

    return report


def main() -> None:
    ap = argparse.ArgumentParser(description="Trim spans out of a prepared video's EDL.")
    ap.add_argument("--slug", required=True, help="video slug under assets/")
    ap.add_argument(
        "--cut",
        action="append",
        default=[],
        metavar="START-END",
        help="source-clip seconds to cut, e.g. 82.2-88.0 (repeatable). Omit to report only.",
    )
    ap.add_argument("--dry-run", action="store_true", help="report only; do not write captions.json")
    args = ap.parse_args()
    result = edit(args.slug, args.cut, args.dry_run)
    print(json.dumps(result, indent=2))
    sys.exit(1 if "error" in result else 0)


if __name__ == "__main__":
    main()
