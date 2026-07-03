"""Image overlay renderer — composites logo PNGs over video frames with fade in/out."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PIL import Image

from .caption import CaptionFrame
from .config import ImagesConfig
from .image_finder import ImageCue

# Center is the prime slot. When images of *different* types overlap in time, the
# highest-priority one keeps the center and the rest are displaced to the corners
# in this order. Two logos are the exception: the later one replaces the earlier
# one in the center rather than displacing it (see _resolve_logo_swaps).
_SLOTS = ("center", "top_left", "top_right")

# Lower number = higher priority for the center slot: screenshot > person > concept > logo.
_TYPE_PRIORITY = {"screenshot": 0, "person": 1, "concept": 2, "logo": 3}


def _assign_slots(cues: list[ImageCue]) -> list[str]:
    """Assign each cue a display slot, avoiding center-stacking of overlapping images.

    Higher-priority cues (screenshot > person > concept > logo) claim the center
    first; any cue that overlaps an already-claimed slot in time is bumped to the
    next free slot (center → top_left → top_right). Returns slots parallel to
    `cues`. Callers pass the swap-adjusted ends from `_resolve_logo_swaps`, so a
    replaced logo no longer overlaps its successor and both keep the center.
    """
    order = sorted(
        range(len(cues)),
        key=lambda i: (_TYPE_PRIORITY.get(cues[i].type, 99), cues[i].start),
    )
    occupied: dict[str, list[tuple[float, float]]] = {slot: [] for slot in _SLOTS}
    slots = ["center"] * len(cues)
    for i in order:
        c = cues[i]
        for slot in _SLOTS:
            if not any(c.start < e and s < c.end for s, e in occupied[slot]):
                occupied[slot].append((c.start, c.end))
                slots[i] = slot
                break
        else:
            slots[i] = _SLOTS[-1]  # >3 concurrent: stack on top_right
    return slots


def _resolve_logo_swaps(
    cues: list[ImageCue],
) -> tuple[list[float], list[bool], list[bool]]:
    """Make an overlapping logo *replace* the one before it in the center.

    When a logo fires while an earlier logo is still on screen, we clamp the
    earlier logo's end down to the later logo's start — so it vanishes exactly as
    the new one appears — instead of bumping it to a corner. The swap is a hard
    cut: the outgoing logo doesn't fade out and the incoming one doesn't fade in
    at the seam (their outer fade-in / fade-out edges are untouched).

    Returns three lists parallel to `cues`: the (possibly clamped) end time, and
    whether each cue should suppress its fade-in / fade-out because it sits at a
    swap seam. Non-logo cues are never touched.
    """
    ends = [c.end for c in cues]
    suppress_in = [False] * len(cues)
    suppress_out = [False] * len(cues)

    logo_idx = sorted(
        (i for i, c in enumerate(cues) if c.type == "logo"),
        key=lambda i: cues[i].start,
    )
    for a, b in zip(logo_idx, logo_idx[1:]):
        if cues[b].start < ends[a]:  # b lands while a is still showing
            ends[a] = cues[b].start
            suppress_out[a] = True   # a is cut off, not faded out
            suppress_in[b] = True    # b cuts in, not faded in
    return ends, suppress_in, suppress_out


def render_image_frames(
    cues: list[ImageCue],
    config: ImagesConfig,
    output_dir: Path,
    fps: int,
    resolution: tuple[int, int],
) -> list[CaptionFrame]:
    """Generate per-frame transparent PNG overlays compositing all active image cues.

    Each output frame composites *every* cue active at that frame onto a single canvas
    at its assigned slot — so overlapping images appear together rather than colliding
    on a shared frame number downstream. Frames with an identical set of active cues and
    fade levels share one file (steady-state frames dedup naturally).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    w, h = resolution
    fade_frames = int(config.fade_duration_s * fps)
    margin_px = int(h * config.margin_pct / 100)
    # Drop the corner (displaced) slots a little below the top edge.
    corner_y = margin_px + int(h * config.corner_drop_pct / 100)

    ends, suppress_in, suppress_out = _resolve_logo_swaps(cues)
    slots = _assign_slots([replace(c, end=e) for c, e in zip(cues, ends)])

    prepared: list[dict] = []
    for i, (cue, slot) in enumerate(zip(cues, slots)):
        try:
            logo = Image.open(cue.image_path).convert("RGBA")
        except Exception:
            continue

        size_pct = config.logo_overlay_size_pct if cue.type == "logo" else config.overlay_size_pct
        target_w = int(w * size_pct / 100)

        # Resize maintaining aspect ratio
        logo_h = int(target_w * logo.height / logo.width)
        logo = logo.resize((target_w, logo_h), Image.LANCZOS)

        # Position. Displaced (overlapping) images sit in a top corner, dropped
        # slightly below the edge; the center slot uses the configured base position.
        if slot == "top_left":
            x, y = margin_px, corner_y
        elif slot == "top_right":
            x, y = w - target_w - margin_px, corner_y
        else:
            if config.position == "top":
                y = margin_px
            elif config.position == "bottom":
                y = h - logo_h - margin_px
            else:
                y = (h - logo_h) // 2
            x = (w - target_w) // 2

        delay_frames = int(config.start_delay_s * fps)
        start_frame = max(int(cue.start * fps), delay_frames)
        end_frame = int(ends[i] * fps)
        total = end_frame - start_frame
        if total <= 0:
            continue

        # Clamp fade so it doesn't exceed half the display window. A logo at a
        # swap seam suppresses that edge's fade for a hard cut.
        effective_fade = min(fade_frames, total // 2)
        prepared.append(
            {"logo": logo, "x": x, "y": y, "start": start_frame, "total": total,
             "fade_in": 0 if suppress_in[i] else effective_fade,
             "fade_out": 0 if suppress_out[i] else effective_fade}
        )

    if not prepared:
        return []

    min_frame = min(p["start"] for p in prepared)
    max_frame = max(p["start"] + p["total"] for p in prepared)

    frames: list[CaptionFrame] = []
    cache: dict[tuple, str] = {}  # active-layer signature → composited file path

    for frame_num in range(min_frame, max_frame):
        layers: list[tuple[int, float]] = []  # (prepared index, alpha)
        for idx, p in enumerate(prepared):
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
            if alpha > 0:
                layers.append((idx, round(alpha, 3)))

        if not layers:
            continue

        sig = tuple(layers)
        path = cache.get(sig)
        if path is None:
            canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            for idx, alpha in layers:
                p = prepared[idx]
                _composite_logo(canvas, p["logo"], alpha, p["x"], p["y"])
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
