"""Caption renderer — Pillow frame-by-frame word-highlight overlay."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw, ImageFont

from .config import CaptionsConfig
from .transcriber import WordTimestamp

CaptionStyle = Literal["word_highlight", "full_line", "none"]

# Words grouped into display lines (max N words per line)
_WORDS_PER_LINE = 4


@dataclass
class CaptionFrame:
    frame_number: int
    image_path: str


def render_caption_frames(
    words: list[WordTimestamp],
    config: CaptionsConfig,
    output_dir: str | Path,
    fps: int = 30,
    resolution: tuple[int, int] = (1080, 1920),
) -> list[CaptionFrame]:
    """Generate per-frame PNG caption overlays.

    Returns a list of CaptionFrame(frame_number, image_path).
    Frames with no caption are not written (callers treat missing frames as blank).
    """
    if config.style == "none" or not words:
        return []

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    font, font_highlight = _load_fonts(config)
    lines = _group_into_lines(words, _WORDS_PER_LINE)
    total_duration = words[-1].end

    frames: list[CaptionFrame] = []
    total_frames = int(total_duration * fps) + 1

    # Cache: map frame_number → (line_words, active_word_idx | None)
    # Build a lookup: for each frame, which line is active and which word is highlighted
    frame_cache = _build_frame_cache(lines, fps, total_frames)

    w, h = resolution
    y_positions = {"top": int(h * 0.12), "center": int(h * 0.72), "bottom": int(h * 0.87)}
    y_pos = y_positions.get(config.position, int(h * 0.72))

    prev_key: tuple | None = None
    prev_path: str | None = None

    for frame_num, cache_entry in frame_cache.items():
        if cache_entry is None:
            continue

        line_words, active_idx = cache_entry
        cache_key = (tuple(w.word for w in line_words), active_idx)

        # Reuse previous frame image if nothing changed
        if cache_key == prev_key and prev_path:
            frames.append(CaptionFrame(frame_number=frame_num, image_path=prev_path))
            continue

        img = _render_frame(
            line_words=line_words,
            active_idx=active_idx,
            config=config,
            font=font,
            font_highlight=font_highlight,
            canvas_size=(w, h),
            y_pos=y_pos,
        )

        path = str(output_dir / f"caption_{frame_num:06d}.png")
        img.save(path, format="PNG")
        frames.append(CaptionFrame(frame_number=frame_num, image_path=path))
        prev_key = cache_key
        prev_path = path

    return frames


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _render_frame(
    line_words: list[WordTimestamp],
    active_idx: int | None,
    config: CaptionsConfig,
    font: ImageFont.FreeTypeFont,
    font_highlight: ImageFont.FreeTypeFont,
    canvas_size: tuple[int, int],
    y_pos: int,
) -> Image.Image:
    """Render a single transparent caption frame."""
    w, h = canvas_size
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    if config.style == "full_line":
        text = " ".join(word.word for word in line_words)
        _draw_text_centered(draw, text, font, config, w, y_pos)

    elif config.style == "word_highlight":
        # Measure total line width to center it
        parts: list[tuple[str, bool]] = [
            (word.word, i == active_idx) for i, word in enumerate(line_words)
        ]
        _draw_highlighted_line(draw, parts, font, font_highlight, config, w, y_pos)

    return img


def _draw_text_centered(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    config: CaptionsConfig,
    canvas_w: int,
    y: int,
) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    x = (canvas_w - text_w) // 2

    if config.stroke:
        draw.text((x, y), text, font=font, fill=config.stroke_color,
                  stroke_width=config.stroke_width, stroke_fill=config.stroke_color)
    draw.text((x, y), text, font=font, fill=config.color)


def _draw_highlighted_line(
    draw: ImageDraw.ImageDraw,
    parts: list[tuple[str, bool]],  # (word, is_active)
    font: ImageFont.FreeTypeFont,
    font_highlight: ImageFont.FreeTypeFont,
    config: CaptionsConfig,
    canvas_w: int,
    y: int,
) -> None:
    gap = 14  # pixel gap between words
    pad_x, pad_y = 14, 8  # block background padding
    offset = 5  # black block offset (shadow shift in px)

    # Measure all word widths and heights
    widths: list[int] = []
    heights: list[int] = []
    for word, active in parts:
        f = font_highlight if active else font
        bbox = draw.textbbox((0, 0), word, font=f)
        widths.append(bbox[2] - bbox[0])
        heights.append(bbox[3] - bbox[1])

    text_h = max(heights) if heights else 0
    # Active words carry pad_x*2 extra width for their highlight box; inactive do not
    total_w = sum(
        (w + pad_x * 2) if active else w
        for w, (_, active) in zip(widths, parts)
    ) + gap * (len(parts) - 1)
    x = (canvas_w - total_w) // 2

    for i, (word, active) in enumerate(parts):
        f = font_highlight if active else font
        w = widths[i]
        h = text_h

        if active:
            box_x0, box_y0 = x, y - pad_y
            box_x1, box_y1 = x + w + pad_x * 2, y + h + pad_y
            # Shadow block behind the active word highlight
            draw.rectangle(
                [box_x0 + offset, box_y0 + offset, box_x1 + offset, box_y1 + offset],
                fill=(0, 0, 0, 180),
            )
            draw.rectangle([box_x0, box_y0, box_x1, box_y1], fill=config.highlight_color)
            draw.text((x + pad_x, y), word, font=f, fill="#FFFFFF")
            x += w + pad_x * 2 + gap
        else:
            # Inactive words: plain white text with a subtle drop shadow
            draw.text((x + 2, y + 2), word, font=f, fill=(0, 0, 0, 160))
            draw.text((x, y), word, font=f, fill=config.color)
            x += w + gap


# ---------------------------------------------------------------------------
# Font loading
# ---------------------------------------------------------------------------

def _load_fonts(config: CaptionsConfig) -> tuple[ImageFont.FreeTypeFont, ImageFont.FreeTypeFont]:
    """Load font at config.size. Falls back to Pillow default if not found."""
    result = _resolve_font(config.font)
    try:
        if result:
            path, index = result
            font = ImageFont.truetype(path, config.size, index=index)
            font_highlight = ImageFont.truetype(path, int(config.size * 1.1), index=index)
        else:
            font = ImageFont.load_default()
            font_highlight = font
    except (OSError, IOError):
        font = ImageFont.load_default()
        font_highlight = font
    return font, font_highlight


def _resolve_font(name: str) -> tuple[str, int] | None:
    """Find a font file by name. Returns (path, face_index) or None.

    For .ttc collections, scans faces and prefers Bold variants.
    Checks bundled fonts first, then system directories.
    """
    bundled_dir = Path(__file__).parent / "fonts"
    direct_candidates = [
        bundled_dir / f"{name}.ttf",
        bundled_dir / f"{name}.otf",
        Path(name),  # absolute path
    ]
    for path in direct_candidates:
        if path.exists():
            return (str(path), _best_face_index(str(path)))

    # Search system font directories
    system_dirs = [
        Path("/System/Library/Fonts"),
        Path("/Library/Fonts"),
        Path.home() / "Library/Fonts",
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
    ]
    name_lower = name.lower().replace("-", "").replace("_", "")
    for d in system_dirs:
        if not d.exists():
            continue
        for ext in ("ttf", "ttc", "otf"):
            for f in sorted(d.glob(f"*.{ext}")):
                if name_lower in f.stem.lower().replace("-", "").replace("_", ""):
                    return (str(f), _best_face_index(str(f)))

    return None


def _best_face_index(path: str) -> int:
    """For .ttc collections, return the index of the Bold (or first Latin) face.

    Falls back to 0 for plain .ttf/.otf files.
    """
    if not path.endswith(".ttc"):
        return 0
    try:
        best_idx = 0
        for idx in range(20):
            try:
                f = ImageFont.truetype(path, 12, index=idx)
                name_lower = " ".join(f.getname()).lower()
                # Prefer bold, heavy, or black weight; skip non-Latin scripts
                if any(w in name_lower for w in ("bold", "heavy", "black")):
                    if not any(w in name_lower for w in ("hebrew", "arabic", "cjk", "chinese", "japanese", "korean")):
                        return idx
            except OSError:
                break
    except Exception:
        pass
    return best_idx


# ---------------------------------------------------------------------------
# Frame cache builder
# ---------------------------------------------------------------------------

def _group_into_lines(
    words: list[WordTimestamp],
    words_per_line: int,
) -> list[list[WordTimestamp]]:
    return [words[i : i + words_per_line] for i in range(0, len(words), words_per_line)]


def _build_frame_cache(
    lines: list[list[WordTimestamp]],
    fps: int,
    total_frames: int,
) -> dict[int, tuple[list[WordTimestamp], int | None] | None]:
    """Map frame_number → (active_line_words, active_word_index_in_line | None)."""
    cache: dict[int, tuple[list[WordTimestamp], int | None] | None] = {}

    # Flatten words with their line membership
    word_to_line: list[tuple[list[WordTimestamp], int]] = []  # (line_words, word_idx_in_line)
    for line in lines:
        for idx, w in enumerate(line):
            word_to_line.append((line, idx))

    # For each frame, binary-search for the active word
    all_words_flat = [w for line in lines for w in line]

    for frame_num in range(total_frames):
        t = frame_num / fps
        active_word_idx = _active_word_at(all_words_flat, t)
        if active_word_idx is None:
            cache[frame_num] = None
            continue
        line_words, word_idx_in_line = word_to_line[active_word_idx]
        cache[frame_num] = (line_words, word_idx_in_line)

    return cache


def _active_word_at(words: list[WordTimestamp], t: float) -> int | None:
    """Return index of the word active at time t, or None if between words."""
    # Show the line of the most recently spoken word (keeps line visible until next line)
    last_idx = None
    for i, w in enumerate(words):
        if w.start <= t:
            last_idx = i
        else:
            break
    if last_idx is None:
        return None
    # Hide after a short grace period past the last word's end
    if t > words[last_idx].end + 0.3:
        return None
    return last_idx
