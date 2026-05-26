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
_WORDS_PER_LINE = 10

_MARGIN = 40        # fallback; overridden at render time by config.margin_pct
_SHADOW_OFFSET = 3  # solid black drop shadow shift (px)
_LINE_SPACING = 10  # px between wrapped rows


def write_srt(words: list[WordTimestamp], path: str | Path) -> None:
    """Write word-grouped captions to an SRT subtitle file."""
    path = Path(path)
    lines = _group_into_lines(words, _WORDS_PER_LINE)
    with path.open("w", encoding="utf-8") as f:
        for i, line_words in enumerate(lines, 1):
            start = line_words[0].start
            end = line_words[-1].end
            text = " ".join(w.word for w in line_words)
            f.write(f"{i}\n{_srt_ts(start)} --> {_srt_ts(end)}\n{text}\n\n")


def _srt_ts(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds % 1) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


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
        cache_key = tuple(w.word for w in line_words)

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

    text = " ".join(word.word for word in line_words)
    margin = int(w * config.margin_pct / 100)
    _draw_text_wrapped(draw, text, font, config, w, y_pos, margin)

    return img


def _draw_text_wrapped(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    config: CaptionsConfig,
    canvas_w: int,
    y: int,
    margin: int = _MARGIN,
) -> None:
    """Draw text centered with solid black shadow, wrapping so no line exceeds canvas width."""
    max_w = canvas_w - 2 * margin
    words = text.split()

    display_lines: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join(current + [word])
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_w or not current:
            current.append(word)
        else:
            display_lines.append(" ".join(current))
            current = [word]
    if current:
        display_lines.append(" ".join(current))

    sample_bbox = draw.textbbox((0, 0), display_lines[0], font=font)
    line_h = sample_bbox[3] - sample_bbox[1]

    total_h = line_h * len(display_lines) + _LINE_SPACING * (len(display_lines) - 1)
    start_y = y - total_h // 2

    for i, line in enumerate(display_lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        line_w = bbox[2] - bbox[0]
        x = (canvas_w - line_w) // 2
        x = max(margin, min(x, canvas_w - margin - line_w))
        cur_y = start_y + i * (line_h + _LINE_SPACING)

        draw.text((x + _SHADOW_OFFSET, cur_y + _SHADOW_OFFSET), line, font=font, fill=(0, 0, 0, 255))
        draw.text((x, cur_y), line, font=font, fill=config.color)


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
