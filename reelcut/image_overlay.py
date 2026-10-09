"""Image overlay renderer — composites logo PNGs over video frames with fade in/out."""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from PIL import Image, ImageDraw

from .caption import CaptionFrame
from .config import ImagesConfig
from .image_finder import ImageCue

# Where an overlay sits. "top" is the default inset band; while the hook's title card is up
# it moves to "under_title" (or "lower" when images.json asks). "full" covers the frame.
TOP, UNDER_TITLE, LOWER, FULL = "top", "under_title", "lower", "full"


@dataclass
class Placement:
    """An overlay's box on the frame, in output pixels, and the band it sits in."""
    x: int
    y: int
    w: int
    h: int
    band: str


def _band(cue: ImageCue, config: ImagesConfig, title_windows) -> str:
    """The band a cue sits in: its images.json `layout`, else full for config.full_types,
    else the top inset — pushed under the title while a title card is on screen."""
    layout = cue.layout or (FULL if cue.type in config.full_types else TOP)
    if layout == TOP and any(s < cue.end and cue.start < e for s, e in title_windows):
        return UNDER_TITLE
    return layout


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
    full-screen overlay fills the full box (starting below the title while one is up).
    """
    w, h = resolution
    out: list[Placement | None] = []
    for cue in cues:
        aspect = _aspect(cue)
        if not aspect:
            out.append(None)
            continue
        band = _band(cue, config, title_windows)
        if band == FULL:
            top_pct = config.full_box_pct[0]
            if any(s < cue.end and cue.start < e for s, e in title_windows):
                top_pct = config.under_title_band_pct[0]
            top, bottom = int(h * top_pct / 100), int(h * config.full_box_pct[1] / 100)
            max_w = w * config.full_width_pct / 100
        else:
            pct = {TOP: config.top_band_pct, UNDER_TITLE: config.under_title_band_pct,
                   LOWER: config.lower_band_pct}[band]
            top, bottom = int(h * pct[0] / 100), int(h * pct[1] / 100)
            max_w = w * _inset_width_pct(cue, config) / 100
        bw = int(min(max_w, (bottom - top) / aspect)) // 2 * 2  # even, for ffmpeg's scaler
        bh = int(bw * aspect)
        if band == FULL:
            y = top + (bottom - top - bh) // 2
        elif band == LOWER:
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
) -> list[CaptionFrame]:
    """Generate per-frame transparent PNG overlays, one overlay per frame (see _shown) in
    its band (see place_cues). A full-screen overlay dims the footage behind it.
    `title_windows` are the output-timeline spans a title card is on screen.
    Frames with the same cue, fade level and sweep step share one file.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    w, h = resolution
    fade_frames = int(config.fade_duration_s * fps)
    dim = int(255 * config.full_dim)
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

        # Clamp fade so it doesn't exceed half the display window. An edge another overlay
        # takes over at is a hard cut.
        effective_fade = min(fade_frames, total // 2)
        sweep_frames = 0
        if sweep:
            sweep_frames = min(total, max(int(SWEEP_MIN_S * fps),
                                          min(int(SWEEP_MAX_S * fps), int(total * SWEEP_SHARE))))
        prepared[i] = {
            "logo": logo, "x": place.x, "y": place.y, "full": place.band == FULL,
            "start": start_frame, "total": total,
            "fade_in": 0 if any(c.end == cue.start for c in cues) else effective_fade,
            "fade_out": 0 if any(c.start == cue.end for c in cues) else effective_fade,
            "sweep": sweep, "sweep_frames": sweep_frames,
        }

    if not prepared:
        return []

    min_frame = min(p["start"] for p in prepared.values())
    max_frame = max(p["start"] + p["total"] for p in prepared.values())

    frames: list[CaptionFrame] = []
    cache: dict[tuple, str] = {}  # (cue, alpha, sweep step) → composited file path

    for frame_num in range(min_frame, max_frame):
        idx = _shown(cues, (frame_num + 0.5) / fps)
        p = prepared.get(idx)
        if p is None:
            continue
        i = frame_num - p["start"]
        if i < 0 or i >= p["total"]:
            continue
        fin, fout, total = p["fade_in"], p["fade_out"], p["total"]
        if fin > 0 and i < fin:
            alpha = i / fin
        elif fout > 0 and i >= total - fout:
            alpha = (total - i) / fout
        else:
            alpha = 1.0
        if alpha <= 0:
            continue
        # Frames still sweeping are each distinct; -1 marks the settled highlight.
        step = i if i < p["sweep_frames"] else -1
        sig = (idx, round(alpha, 3), step)
        path = cache.get(sig)
        if path is None:
            canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            if p["full"]:
                canvas.paste((0, 0, 0, int(dim * alpha)), (0, 0, w, h))
            img = p["logo"]
            if step >= 0:
                img = _sweep_frame(img, *p["sweep"], (step + 1) / p["sweep_frames"])
            _composite_logo(canvas, img, alpha, p["x"], p["y"])
            path = str(output_dir / f"img_{frame_num:06d}.png")
            canvas.save(path, format="PNG")
            cache[sig] = path
        frames.append(CaptionFrame(frame_number=frame_num, image_path=path))

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
            canvas.save(merged_path, format="PNG")

            prev_cap, prev_img, prev_merged_path = cap_path, img_path, merged_path
            result.append(CaptionFrame(frame_number=fn, image_path=merged_path))

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


def _composite_logo(
    canvas: Image.Image,
    logo: Image.Image,
    alpha: float,
    x: int,
    y: int,
) -> None:
    """Alpha-composite `logo` onto `canvas` at (x, y), scaling its alpha for fades."""
    if alpha >= 1.0:
        canvas.alpha_composite(logo, (x, y))
        return
    r, g, b, a = logo.split()
    a_faded = a.point(lambda v, _a=alpha: int(v * _a))
    faded = Image.merge("RGBA", (r, g, b, a_faded))
    canvas.alpha_composite(faded, (x, y))
