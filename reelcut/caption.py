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

_MARGIN = 40        # fallback; overridden at render time by config.margin_pct



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
    lines = _group_into_lines(words, config.words_per_line, config.grace_s)
    total_duration = words[-1].end

    frames: list[CaptionFrame] = []
    total_frames = int(total_duration * fps) + 1

    # Cache: map frame_number → (line_words, active_word_idx | None)
    # Build a lookup: for each frame, which line is active and which word is highlighted
    frame_cache = _build_frame_cache(lines, fps, total_frames, config.grace_s)

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

def _build_display_tokens(
    line_words: list[WordTimestamp], active_idx: int | None
) -> list[tuple[str, bool]]:
    """Merge continuation tokens into single visual tokens and flag the active one.

    Whisper splits some words across tokens that should render without a space
    (e.g. 're-asking' → ['re', '-asking']); these are merged here. A token is
    marked active if it covers active_idx so it can be highlighted.
    Returns a list of (text, is_active).
    """
    tokens: list[tuple[str, bool]] = []
    for idx, w in enumerate(line_words):
        is_active = idx == active_idx
        if tokens and w.word.startswith(("-", "'", "’")):
            prev_text, prev_active = tokens[-1]
            tokens[-1] = (prev_text + w.word, prev_active or is_active)
        else:
            tokens.append((w.word, is_active))
    return tokens


def _render_frame(
    line_words: list[WordTimestamp],
    active_idx: int | None,
    config: CaptionsConfig,
    font: ImageFont.FreeTypeFont,
    font_highlight: ImageFont.FreeTypeFont,
    canvas_size: tuple[int, int],
    y_pos: int,
) -> Image.Image:
    """Render a single transparent caption frame with the active word highlighted."""
    w, h = canvas_size
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    highlight_idx = active_idx if config.style == "word_highlight" else None
    tokens = _build_display_tokens(line_words, highlight_idx)
    margin = int(w * config.margin_pct / 100)
    _draw_tokens_wrapped(draw, tokens, font, config, w, y_pos, margin)

    return img


def _draw_tokens_wrapped(
    draw: ImageDraw.ImageDraw,
    tokens: list[tuple[str, bool]],
    font: ImageFont.FreeTypeFont,
    config: CaptionsConfig,
    canvas_w: int,
    y: int,
    margin: int = _MARGIN,
) -> None:
    """Draw word tokens centered, wrapping so no line exceeds canvas width.

    Each token gets a solid black drop shadow and an optional stroke (when
    config.stroke is set). The active token is painted in highlight_color.
    """
    max_w = canvas_w - 2 * margin
    space_w = draw.textlength(" ", font=font)

    # Wrap tokens into visual lines that each fit within max_w (advance-width based).
    lines: list[list[tuple[str, bool]]] = []
    current: list[tuple[str, bool]] = []
    current_w = 0.0
    for text, is_active in tokens:
        tok_w = draw.textlength(text, font=font)
        added_w = tok_w + (space_w if current else 0)
        if current and current_w + added_w > max_w:
            lines.append(current)
            current, current_w = [(text, is_active)], tok_w
        else:
            current.append((text, is_active))
            current_w += added_w
    if current:
        lines.append(current)

    ascent, descent = font.getmetrics()
    line_h = ascent + descent
    total_h = line_h * len(lines) + config.line_spacing * (len(lines) - 1)
    start_y = y - total_h // 2

    stroke_kwargs: dict = {}
    if config.stroke and config.stroke_width > 0:
        stroke_kwargs = {"stroke_width": config.stroke_width, "stroke_fill": config.stroke_color}

    for row, line_tokens in enumerate(lines):
        widths = [draw.textlength(text, font=font) for text, _ in line_tokens]
        line_w = sum(widths) + space_w * (len(line_tokens) - 1)
        x = (canvas_w - line_w) / 2
        x = max(margin, min(x, canvas_w - margin - line_w))
        cur_y = start_y + row * (line_h + config.line_spacing)

        for (text, is_active), tok_w in zip(line_tokens, widths):
            fill = config.highlight_color if is_active else config.color
            if config.shadow:
                draw.text((x + config.shadow_offset, cur_y + config.shadow_offset), text, font=font, fill=config.shadow_color)
            draw.text((x, cur_y), text, font=font, fill=fill, **stroke_kwargs)
            x += tok_w + space_w


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

def _ends_sentence(word: WordTimestamp) -> bool:
    """True if this word ends with sentence-terminal punctuation."""
    return word.word.rstrip().endswith((".", "!", "?"))


def _group_into_lines(
    words: list[WordTimestamp],
    words_per_line: int,
    gap_break_s: float,
) -> list[list[WordTimestamp]]:
    """Group words into display lines. Breaks on word-count limit, a timing gap >= gap_break_s,
    or a sentence boundary so each caption block starts at the beginning of a sentence.

    gap_break_s matches the grace period in _active_word_at: any gap that would cause the
    caption to expire and reappear gets a line break so the reappearing text is new content.
    """
    if not words:
        return []
    lines: list[list[WordTimestamp]] = []
    current: list[WordTimestamp] = [words[0]]
    for w in words[1:]:
        gap = w.start - current[-1].end
        sentence_end = _ends_sentence(current[-1])
        if len(current) >= words_per_line or gap >= gap_break_s or sentence_end:
            lines.append(current)
            current = [w]
        else:
            current.append(w)
    if current:
        lines.append(current)
    return lines


def _build_frame_cache(
    lines: list[list[WordTimestamp]],
    fps: int,
    total_frames: int,
    grace_s: float,
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
        active_word_idx = _active_word_at(all_words_flat, t, grace_s)
        if active_word_idx is None:
            cache[frame_num] = None
            continue
        line_words, word_idx_in_line = word_to_line[active_word_idx]
        cache[frame_num] = (line_words, word_idx_in_line)

    return cache


def _active_word_at(words: list[WordTimestamp], t: float, grace_s: float) -> int | None:
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
    if t > words[last_idx].end + grace_s:
        return None
    return last_idx
