"""Image overlay renderer — composites logo PNGs over video frames with fade in/out."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from .caption import CaptionFrame
from .config import ImagesConfig
from .image_finder import ImageCue


def render_image_frames(
    cues: list[ImageCue],
    config: ImagesConfig,
    output_dir: Path,
    fps: int,
    resolution: tuple[int, int],
) -> list[CaptionFrame]:
    """Generate per-frame transparent PNG overlays for each image cue.

    Steady-state frames (alpha=1) share a single file per cue to minimise disk I/O.
    Only fade-in and fade-out frames get unique files.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    w, h = resolution
    fade_frames = int(config.fade_duration_s * fps)
    margin_px = int(h * config.margin_pct / 100)

    frames: list[CaptionFrame] = []

    for cue in cues:
        try:
            logo = Image.open(cue.image_path).convert("RGBA")
        except Exception:
            continue

        size_pct = config.logo_overlay_size_pct if cue.type == "logo" else config.overlay_size_pct
        target_w = int(w * size_pct / 100)

        # Resize maintaining aspect ratio
        logo_h = int(target_w * logo.height / logo.width)
        logo = logo.resize((target_w, logo_h), Image.LANCZOS)

        # Vertical position
        if config.position == "top":
            y = margin_px
        elif config.position == "bottom":
            y = h - logo_h - margin_px
        else:
            y = (h - logo_h) // 2
        x = (w - target_w) // 2

        start_frame = int(cue.start * fps)
        end_frame = int(cue.end * fps)
        total = end_frame - start_frame
        if total <= 0:
            continue

        # Clamp fade so it doesn't exceed half the display window
        effective_fade = min(fade_frames, total // 2)

        # Write the steady-state (full-opacity) frame once and reuse it
        steady_canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        steady_canvas.alpha_composite(logo, (x, y))
        steady_path = str(output_dir / f"img_{cue.keyword}_steady.png")
        steady_canvas.save(steady_path, format="PNG")

        for i in range(total):
            frame_num = start_frame + i

            if effective_fade > 0 and i < effective_fade:
                alpha = i / effective_fade
            elif effective_fade > 0 and i >= total - effective_fade:
                alpha = (total - i) / effective_fade
            else:
                frames.append(CaptionFrame(frame_number=frame_num, image_path=steady_path))
                continue

            if alpha <= 0:
                continue

            faded_path = str(output_dir / f"img_{frame_num:06d}.png")
            _write_faded_frame(logo, alpha, w, h, x, y, faded_path)
            frames.append(CaptionFrame(frame_number=frame_num, image_path=faded_path))

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

def _write_faded_frame(
    logo: Image.Image,
    alpha: float,
    w: int,
    h: int,
    x: int,
    y: int,
    path: str,
) -> None:
    r, g, b, a = logo.split()
    a_faded = a.point(lambda v, _a=alpha: int(v * _a))
    faded = Image.merge("RGBA", (r, g, b, a_faded))
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    canvas.alpha_composite(faded, (x, y))
    canvas.save(path, format="PNG")
