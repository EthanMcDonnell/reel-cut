"""Image overlay renderer — composites logo PNGs over video frames, moving by reelcut.motion."""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path

from PIL import Image, ImageDraw

from .caption import CaptionFrame, FrameWriter
from .config import ImagesConfig
from .image_finder import ImageCue
from .motion import (
    DISSOLVE_S, EXIT_S, Motion, Pose, draw, ease_in_out, enter_pose, exit_pose, hold_pose,
    resolve, settle_s, spring, transition_poses, with_band,
)

# Where an overlay sits. "top" is the default inset band; while the hook's title card is up
# it moves to "under_title" (or "lower" when images.json asks). "full" is a card covering the frame.
TOP, UNDER_TITLE, LOWER, FULL = "top", "under_title", "lower", "full"


@dataclass
class Placement:
    """An overlay's box on the frame, in output pixels, and the band it sits in."""
    x: int
    y: int
    w: int
    h: int
    band: str


def _band(cue: ImageCue, title_windows) -> str:
    """The band a cue sits in: its images.json `layout` (full only for a card), else the top
    inset — pushed under the title while a title card is on screen."""
    if cue.layout in (LOWER, FULL) and (cue.layout == LOWER or cue.type == "card" or cue.kind == "card"):
        return cue.layout
    if any(s < cue.end and cue.start < e for s, e in title_windows):
        return UNDER_TITLE
    return TOP


def _aspect(cue: ImageCue) -> float | None:
    """Height / width of the overlay as drawn, or None if its file can't be read."""
    try:
        if cue.type == "video":
            import ffmpeg
            st = next(s for s in ffmpeg.probe(cue.image_path)["streams"] if s["codec_type"] == "video")
            return st["height"] / st["width"]
        with Image.open(cue.image_path) as im:
            ar = im.height / im.width
    except Exception:
        return None
    # A figure is drawn on a padded card (see _figure_card): 4.5% padding each side.
    return ar * 0.91 + 0.09 if cue.type == "figure" else ar


def _inset_width_pct(cue: ImageCue, config: ImagesConfig) -> float:
    if cue.type == "logo":
        return config.logo_overlay_size_pct
    if cue.type == "figure":
        return config.figure_overlay_size_pct
    if cue.type == "card" or cue.kind == "card":
        return config.card_overlay_size_pct
    return config.overlay_size_pct


def place_cues(
    cues: list[ImageCue],
    config: ImagesConfig,
    resolution: tuple[int, int],
    title_windows: list[tuple[float, float]] = (),
) -> list[Placement | None]:
    """Each cue's box, parallel to `cues` (None when its file can't be read).

    An inset keeps its configured width unless that would overflow its band's height, and
    hugs the band's outer edge: the top of the top bands, the bottom of the lower band. A
    full-screen card covers the frame.
    """
    w, h = resolution
    out: list[Placement | None] = []
    for cue in cues:
        aspect = _aspect(cue)
        if not aspect:
            out.append(None)
            continue
        band = _band(cue, title_windows)
        if band == FULL:
            out.append(Placement(x=0, y=0, w=w, h=h, band=FULL))
            continue
        pct = {TOP: config.top_band_pct, UNDER_TITLE: config.under_title_band_pct,
               LOWER: config.lower_band_pct}[band]
        top, bottom = int(h * pct[0] / 100), int(h * pct[1] / 100)
        max_w = w * _inset_width_pct(cue, config) / 100
        bw = int(min(max_w, (bottom - top) / aspect)) // 2 * 2  # even, for ffmpeg's scaler
        bh = int(bw * aspect)
        if band == LOWER:
            y = bottom - bh
        else:
            y = top
        out.append(Placement(x=(w - bw) // 2, y=y, w=bw, h=bh, band=band))
    return out


def _shown(cues: list[ImageCue], t: float) -> int | None:
    """Index of the one overlay on screen at `t`: the newest active one. A video clip hides
    the stills, and a logo never hides a non-logo — it only replaces another logo."""
    active = [i for i, c in enumerate(cues) if c.start <= t < c.end]
    if not active:
        return None
    rank = lambda i: (cues[i].type == "video", cues[i].type != "logo", cues[i].start)
    return max(active, key=rank)


def caption_lifts(
    cues: list[ImageCue],
    placements: list[Placement | None],
    resolution: tuple[int, int],
) -> list[tuple[float, float, int]]:
    """(start, end, bottom_px) windows where captions must sit above a lower-band overlay."""
    gap = int(resolution[1] * 0.015)
    edges = sorted({t for c in cues for t in (c.start, c.end)})
    lifts = []
    for a, b in zip(edges, edges[1:]):
        i = _shown(cues, (a + b) / 2)
        if i is not None and placements[i] and placements[i].band == LOWER:
            lifts.append((a, b, placements[i].y - gap))
    return lifts


# A stretch with no overlay at least this long is reported as a coverage gap.
COVERAGE_GAP_S = 1.0

# A screenshot's highlight sweeps in over this share of its time on screen, within these bounds.
SWEEP_SHARE = 0.6
SWEEP_MIN_S = 0.6
SWEEP_MAX_S = 2.5


def clamp_to_hook(cues: list[ImageCue], hook_end: float) -> list[ImageCue]:
    """End every cue that starts inside the hook by `hook_end`.

    In a per-hook video an overlay that starts in the hook belongs to that hook
    alone; left running it would spill into the shared body in this variant only.
    A cue left shorter than a frame or two is dropped.
    """
    out = []
    for c in cues:
        if c.start < hook_end and c.end > hook_end:
            c = replace(c, end=hook_end)
        if c.end - c.start >= 0.05:
            out.append(c)
    return out


def coverage_gaps(
    cues: list[ImageCue], total_s: float, min_gap_s: float = COVERAGE_GAP_S,
) -> list[tuple[float, float]]:
    """Output-timeline stretches of at least `min_gap_s` with no overlay on screen."""
    gaps = []
    t = 0.0
    for c in sorted(cues, key=lambda c: c.start):
        if c.start > t and c.start - t >= min_gap_s:
            gaps.append((t, c.start))
        t = max(t, c.end)
    if total_s > t and total_s - t >= min_gap_s:
        gaps.append((t, total_s))
    return gaps


def render_image_frames(
    cues: list[ImageCue],
    config: ImagesConfig,
    output_dir: Path,
    fps: int,
    resolution: tuple[int, int],
    title_windows: list[tuple[float, float]] = (),
    motion: Motion | None = None,
) -> list[CaptionFrame]:
    """Generate per-frame transparent PNG overlays, one overlay per frame (see _shown) in
    its band (see place_cues).
    `title_windows` are the output-timeline spans a title card is on screen.

    Each overlay moves by `motion` with its own images.json overrides on top: it plays its
    entrance when it appears from nothing, its transition when it takes over from another
    overlay, and its exit when nothing follows or an older overlay comes back from under it.
    A `fade` lasts images.fade_duration_s. Frames that look the same share one file.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    w, h = resolution
    frame = (w, h)
    base = motion or resolve()
    fade_frames = int(config.fade_duration_s * fps)
    placements = place_cues(cues, config, resolution, title_windows)

    prepared: dict[int, dict] = {}
    for i, (cue, place) in enumerate(zip(cues, placements)):
        if cue.type == "video" or place is None:
            continue  # a video is drawn by the renderer; here it only hides the stills
        try:
            logo = Image.open(cue.image_path).convert("RGBA")
        except Exception:
            continue

        # Figures (article charts/diagrams) sit on an opaque padded card so transparent
        # or wide images read against the footage; the card's total width is place.w.
        sweep = None
        if cue.type == "figure":
            logo = _figure_card(logo, place.w)
        else:
            logo = logo.resize((place.w, place.h), Image.LANCZOS)
            if cue.type == "screenshot":
                sweep = _load_sweep(cue.image_path, place.w, place.h)

        delay_frames = int(config.start_delay_s * fps)
        start_frame = max(int(cue.start * fps), delay_frames)
        total = int(cue.end * fps) - start_frame
        if total <= 0:
            continue

        sweep_frames = 0
        if sweep:
            sweep_frames = min(total, max(int(SWEEP_MIN_S * fps),
                                          min(int(SWEEP_MAX_S * fps), int(total * SWEEP_SHARE))))
        m = resolve(asdict(base), cue.motion) if cue.motion else base
        prepared[i] = {
            "logo": logo, "x": place.x, "y": place.y,
            "start": start_frame, "total": total,
            "sweep": sweep, "sweep_frames": sweep_frames,
            "motion": with_band(m, place.band == FULL), "k": len(prepared),
        }

    if not prepared:
        return []

    min_frame = min(p["start"] for p in prepared.values())
    max_frame = max(p["start"] + p["total"] for p in prepared.values())

    # What each frame shows, as runs [overlay, first frame, end frame): None is nothing,
    # -1 a video clip (drawn by the renderer, so a still leaving for it just goes).
    runs: list[list] = []
    for f in range(min_frame, max_frame):
        idx = _shown(cues, (f + 0.5) / fps)
        p = prepared.get(idx)
        if p is None:
            d = -1 if idx is not None and cues[idx].type == "video" else None
        else:
            d = idx if p["start"] <= f < p["start"] + p["total"] else None
        if runs and runs[-1][0] == d:
            runs[-1][2] = f + 1
        else:
            runs.append([d, f, f + 1])

    def held(ix: int, f: int) -> Pose:
        q = prepared[ix]
        mq = q["motion"]
        el = f - q["start"]
        tilt = Pose(rot=mq.tilt if q["k"] % 2 == 0 else -mq.tilt)
        return tilt + hold_pose(mq.hold, el / q["total"], el / fps, ix + 1, frame)

    def length(move: str, m: Motion) -> int:
        return fade_frames if move == "fade" else 0 if move == "snap" else round(settle_s(m.spring) * fps)

    def progress(i: int, n: int, timing: str, m: Motion) -> float:
        if timing == "linear":
            return i / n
        if timing == "ease":
            return ease_in_out(i / n)
        natural = settle_s(m.spring) * fps  # a window too short for the spring plays it faster
        return spring(i / fps * max(1.0, natural / n), m.spring)

    frames: list[CaptionFrame] = []
    cache: dict[tuple, str] = {}  # what's drawn → composited file path
    writer = FrameWriter()

    for r, (idx, f0, f1) in enumerate(runs):
        if idx is None or idx < 0:
            continue
        prev = runs[r - 1][0] if r else None
        nxt = runs[r + 1][0] if r + 1 < len(runs) else None
        prev = prev if prev is not None and prev >= 0 else None
        p, m, n = prepared[idx], prepared[idx]["motion"], f1 - f0
        takeover = prev is not None and cues[idx].start >= cues[prev].start
        exit_over = nxt is not None and nxt >= 0 and cues[nxt].start < cues[idx].start
        exits = nxt is None or exit_over

        if takeover:
            n_in = {"cut": 0, "swap": length(m.enter, m), "stack": length(m.enter, m),
                    "push": round(settle_s(m.spring) * fps),
                    "dissolve": round(DISSOLVE_S * fps)}[m.transition]
        else:  # a resumed overlay was under the one leaving; it is already in place
            n_in = 0 if prev is not None else length(m.enter, m)
        n_out = 0
        if exits:
            n_out = fade_frames if m.exit == "fade" else 0 if m.exit == "snap" else round(EXIT_S * fps)
        n_in, n_out = min(n_in, n // 2), min(n_out, n // 2)
        enter_timing = "linear" if m.enter == "fade" else "spring"

        for f in range(f0, f1):
            i, j = f - f0, f1 - f
            layers: list[tuple[int, Pose]] = []
            pose = held(idx, f)
            if i < n_in:
                inc = None
                if takeover:
                    tp = progress(i, n_in, "ease" if m.transition == "dissolve" else "spring", m)
                    out, inc = transition_poses(m.transition, tp, i / n_in, frame)
                    if out is not None:
                        layers.append((prev, held(prev, f) + out))
                if inc is None:
                    inc = enter_pose(m.enter, progress(i, n_in, enter_timing, m), frame, p["k"])
                pose = pose + inc
            if exits and j <= n_out:
                pose = pose + exit_pose(m.exit, 1 - j / n_out, frame, p["k"])
                if exit_over:
                    layers.insert(0, (nxt, held(nxt, f)))
            layers.append((idx, pose))
            layers = [(ix, ps) for ix, ps in layers if ps.alpha > 0]
            if not layers:
                continue

            # Frames still sweeping are each distinct; -1 marks the settled highlight.
            steps = [(f - prepared[ix]["start"]) for ix, _ in layers]
            steps = [s if s < prepared[ix]["sweep_frames"] else -1 for s, (ix, _) in zip(steps, layers)]
            sig = tuple((ix, s, ps.key()) for (ix, ps), s in zip(layers, steps))
            path = cache.get(sig)
            if path is None:
                canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                for (ix, ps), s in zip(layers, steps):
                    q = prepared[ix]
                    img = q["logo"]
                    if s >= 0:
                        img = _sweep_frame(img, *q["sweep"], (s + 1) / q["sweep_frames"])
                    draw(canvas, img, q["x"], q["y"], ps)
                path = str(output_dir / f"img_{f:06d}.png")
                writer.save(canvas, path)
                cache[sig] = path
            frames.append(CaptionFrame(frame_number=f, image_path=path))

    writer.wait()
    return frames


def merge_with_caption_frames(
    caption_frames: list[CaptionFrame],
    image_frames: list[CaptionFrame],
    resolution: tuple[int, int],
) -> list[CaptionFrame]:
    """Composite image frames (bottom layer) under caption frames (top layer).

    Frames that appear in only one list are passed through unchanged.
    When both have a frame, they are composited and written to a merged file.
    Consecutive frames with identical source paths reuse the same merged file.
    """
    if not image_frames:
        return caption_frames
    if not caption_frames:
        return image_frames

    cap_map: dict[int, str] = {cf.frame_number: cf.image_path for cf in caption_frames}
    img_map: dict[int, str] = {cf.frame_number: cf.image_path for cf in image_frames}

    merged_dir = Path(image_frames[0].image_path).parent / "merged"
    merged_dir.mkdir(exist_ok=True)

    w, h = resolution
    result: list[CaptionFrame] = []
    prev_cap = prev_img = prev_merged_path = None
    writer = FrameWriter()

    for fn in sorted(set(cap_map) | set(img_map)):
        cap_path = cap_map.get(fn)
        img_path = img_map.get(fn)

        if cap_path and not img_path:
            result.append(CaptionFrame(frame_number=fn, image_path=cap_path))
            prev_cap = prev_img = prev_merged_path = None
        elif img_path and not cap_path:
            result.append(CaptionFrame(frame_number=fn, image_path=img_path))
            prev_cap = prev_img = prev_merged_path = None
        else:
            # Reuse merged file when both source frames are unchanged
            if cap_path == prev_cap and img_path == prev_img and prev_merged_path:
                result.append(CaptionFrame(frame_number=fn, image_path=prev_merged_path))
                continue

            merged_path = str(merged_dir / f"merged_{fn:06d}.png")
            canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            canvas.alpha_composite(Image.open(img_path).convert("RGBA"))
            canvas.alpha_composite(Image.open(cap_path).convert("RGBA"))
            writer.save(canvas, merged_path)

            prev_cap, prev_img, prev_merged_path = cap_path, img_path, merged_path
            result.append(CaptionFrame(frame_number=fn, image_path=merged_path))

    writer.wait()
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_sweep(path: str, w: int, h: int) -> tuple[Image.Image, list] | None:
    """The un-highlighted crop and highlighted line boxes saved beside a screenshot.

    `scrape/screenshot.py` writes `<stem>.plain.png` and `<stem>.rects.json` (line boxes as
    fractions of the crop). Returns the plain image at (w, h) and the boxes in its pixels,
    or None when either is missing, so older screenshots keep showing as a still.
    """
    import json

    base = Path(path)
    plain_path = base.with_name(f"{base.stem}.plain.png")
    rects_path = base.with_name(f"{base.stem}.rects.json")
    if not (plain_path.exists() and rects_path.exists()):
        return None
    try:
        plain = Image.open(plain_path).convert("RGBA").resize((w, h), Image.LANCZOS)
        rects = [(rx * w, ry * h, rw * w, rh * h) for rx, ry, rw, rh in json.loads(rects_path.read_text())]
    except Exception:
        return None
    return (plain, rects) if rects else None


def _sweep_frame(highlighted: Image.Image, plain: Image.Image, rects: list, progress: float) -> Image.Image:
    """The plain crop with the highlight revealed left to right, line by line, to `progress`.

    Eased out so the sweep starts quickly and settles onto the end of the line.
    """
    reveal = (1 - (1 - min(1.0, progress)) ** 3) * sum(r[2] for r in rects)
    out = plain.copy()
    for x, y, w, h in rects:
        if reveal <= 0:
            break
        box = (int(x), int(y), int(x + min(w, reveal)), int(y + h))
        if box[2] > box[0] and box[3] > box[1]:
            out.paste(highlighted.crop(box), box[:2])
        reveal -= w
    return out


def _figure_card(img: Image.Image, card_w: int) -> Image.Image:
    """Place a figure image on an opaque white rounded card of total width `card_w`.

    The image is padded inside the card so transparent/wide article charts and diagrams
    read against the video footage instead of floating as bare fragments. Card height
    grows to fit the image at its aspect ratio.
    """
    pad = max(1, int(card_w * 0.045))
    radius = max(1, int(card_w * 0.04))
    inner_w = max(1, card_w - 2 * pad)
    inner_h = max(1, int(inner_w * img.height / img.width))
    img = img.resize((inner_w, inner_h), Image.LANCZOS)

    card_h = inner_h + 2 * pad
    card = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
    mask = Image.new("L", (card_w, card_h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, card_w - 1, card_h - 1], radius=radius, fill=255)
    card.paste((255, 255, 255, 255), (0, 0), mask)
    card.alpha_composite(img, (pad, pad))
    return card
