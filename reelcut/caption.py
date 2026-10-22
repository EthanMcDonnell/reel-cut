"""Caption renderer — Pillow frame-by-frame word-highlight overlay."""
from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .config import CaptionsConfig
from .motion import STILL, Pose, clamp, draw, spring
from .transcriber import WordTimestamp, is_sentence_boundary, SENTENCE_PAUSE_S

CaptionStyle = Literal["word_highlight", "full_line", "none"]

_MARGIN = 40        # fallback; overridden at render time by config.margin_pct



def censor_word(word: str, stems: list[str]) -> str:
    """Star the first vowel after the first letter of a word starting with a censored stem
    ("Fucking," → "F*cking,"). Burned-in text is read as on-screen text, so a swear there
    can cost reach even when the audio carries it anyway."""
    core = re.sub(r"[^a-z]", "", word.lower())
    if not any(core.startswith(stem) for stem in stems):
        return word
    return re.sub(r"(?<=[A-Za-z])[aeiouAEIOU]", "*", word, count=1)


@dataclass
class CaptionFrame:
    frame_number: int
    image_path: str


class FrameWriter:
    """Writes frame PNGs on worker threads — Pillow releases the GIL while encoding, so this
    is several times faster than saving inline. `wait()` returns once every write is done,
    re-raising the first that failed. A saved image must not be changed afterwards."""

    def __init__(self, workers: int = 8):
        self._pool = ThreadPoolExecutor(max_workers=workers)
        self._futures = []

    def save(self, img: Image.Image, path: str | Path) -> None:
        self._futures.append(self._pool.submit(img.save, str(path), format="PNG"))

    def wait(self) -> None:
        self._pool.shutdown(wait=True)
        for f in self._futures:
            f.result()


def render_caption_frames(
    words: list[WordTimestamp],
    config: CaptionsConfig,
    output_dir: str | Path,
    fps: int = 30,
    resolution: tuple[int, int] = (1080, 1920),
    sentence_pause_s: float = SENTENCE_PAUSE_S,
    lifts: list[tuple[float, float, int]] = (),
    motion: str = "none",
    spring_name: str = "snappy",
) -> list[CaptionFrame]:
    """Generate per-frame PNG caption overlays.

    `lifts` are (start, end, bottom_px) output-timeline windows where the caption block sits
    with its bottom at bottom_px instead of at config.position (above a lower-band overlay).

    `motion` (reelcut.motion CAPTIONS): "pop" springs each new line in, "words" springs each
    word in as it is spoken. Either way a highlighted word grows into its highlight size.

    Returns a list of CaptionFrame(frame_number, image_path).
    Frames with no caption are not written (callers treat missing frames as blank).
    """
    if config.style == "none" or not words:
        return []

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if config.censor:
        words = [replace(w, word=censor_word(w.word, config.censor)) for w in words]
    font, font_highlight = _load_fonts(config)
    lines = _group_into_lines(words, config.words_per_line, config.grace_s, sentence_pause_s)
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
    writer = FrameWriter()

    for frame_num, cache_entry in frame_cache.items():
        if cache_entry is None:
            continue

        line_words, active_idx = cache_entry
        t = frame_num / fps
        y_bottom = next((b for s, e, b in lifts if s <= t < e), None)
        poses = _token_poses(line_words, active_idx, t, config, motion, spring_name, h)
        cache_key = (tuple(w.word for w in line_words), active_idx, y_bottom,
                     poses and (poses[0].key(), tuple(p.key() for p in poses[1])))

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
            y_bottom=y_bottom,
            poses=poses,
        )

        path = str(output_dir / f"caption_{frame_num:06d}.png")
        writer.save(img, path)
        frames.append(CaptionFrame(frame_number=frame_num, image_path=path))
        prev_key = cache_key
        prev_path = path

    writer.wait()
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


def _token_poses(
    line_words: list[WordTimestamp],
    active_idx: int | None,
    t: float,
    config: CaptionsConfig,
    motion: str,
    spring_name: str,
    canvas_h: int,
) -> tuple[Pose, list[Pose]] | None:
    """(the whole line's pose, each display token's pose) at `t`, or None once everything has
    settled — the frame then draws exactly as a still one."""
    if motion == "none":
        return None
    starts: list[float] = []
    for w in line_words:  # same merge as _build_display_tokens
        if starts and w.word.startswith(("-", "'", "’")):
            continue
        starts.append(w.start)
    tokens = _build_display_tokens(line_words, active_idx if config.style == "word_highlight" else None)
    poses = []
    for start, (_, is_active) in zip(starts, tokens):
        pose = STILL
        if motion == "words":
            if t < start:
                pose = Pose(alpha=0.0)
            else:
                q = spring(t - start, spring_name)
                pose = Pose(scale=0.7 + 0.3 * q, dy=(1 - q) * 0.008 * canvas_h, alpha=clamp(q * 3))
        if is_active:
            word_start = line_words[active_idx].start
            pose = pose + Pose(scale=1 / 1.1 + (1 - 1 / 1.1) * spring(t - word_start, spring_name))
        poses.append(pose)
    block = STILL
    if motion == "pop":
        p = spring(t - line_words[0].start, spring_name)
        block = Pose(scale=0.9 + 0.1 * p, dy=(1 - p) * 0.008 * canvas_h, alpha=clamp(p * 2.5))
    if all(ps.key() == STILL.key() for ps in [block, *poses]):
        return None
    return block, poses


def _render_frame(
    line_words: list[WordTimestamp],
    active_idx: int | None,
    config: CaptionsConfig,
    font: ImageFont.FreeTypeFont,
    font_highlight: ImageFont.FreeTypeFont,
    canvas_size: tuple[int, int],
    y_pos: int,
    y_bottom: int | None = None,
    poses: tuple[Pose, list[Pose]] | None = None,
) -> Image.Image:
    """Render a single transparent caption frame: soft blurred shadow, then crisp
    stroked text on top (the active word highlighted when style is word_highlight).
    `poses` (see _token_poses) draws the tokens mid-animation."""
    w, h = canvas_size
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    highlight_idx = active_idx if config.style == "word_highlight" else None
    tokens = _build_display_tokens(line_words, highlight_idx)
    margin = int(w * config.margin_pct / 100)
    placed = _layout_tokens(draw, tokens, font, font_highlight, config, w, y_pos, margin, y_bottom)

    stroke_width = config.stroke_width if config.stroke else 0
    if poses is not None:
        return _render_posed(img, placed, *poses, config, stroke_width)

    # Soft drop shadow: render the (outlined) text silhouette to a mask, blur it,
    # tint it, and composite under the crisp text — far less "basic" than a hard offset.
    if config.shadow:
        mask = Image.new("L", (w, h), 0)
        mdraw = ImageDraw.Draw(mask)
        for text, _is_active, x, ty, f in placed:
            mdraw.text((x, ty), text, font=f, fill=255, stroke_width=stroke_width)
        img.alpha_composite(_soft_shadow(mask, config))

    for text, is_active, x, ty, f in placed:
        fill = config.highlight_color if is_active else config.color
        if stroke_width:
            draw.text((x, ty), text, font=f, fill=fill, stroke_width=stroke_width, stroke_fill=config.stroke_color)
        else:
            draw.text((x, ty), text, font=f, fill=fill)

    return img


_SPRITES: dict[tuple, Image.Image] = {}  # a drawn token, reused across frames


def _render_posed(img, placed, block: Pose, poses: list[Pose], config: CaptionsConfig,
                  stroke_width: int) -> Image.Image:
    """Draw each token as a sprite in its pose, inside the line's `block` pose — scaled about
    the line's centre, so the line grows as one piece."""
    boxes = []
    for text, _is_active, x, ty, f in placed:
        l, t, r, b = f.getbbox(text, stroke_width=stroke_width)
        boxes.append((x + l, ty + t, r - l, b - t, l, t))
    bx0 = min(b[0] for b in boxes)
    bx1 = max(b[0] + b[2] for b in boxes)
    by0 = min(b[1] for b in boxes)
    by1 = max(b[1] + b[3] for b in boxes)
    bcx, bcy = (bx0 + bx1) / 2, (by0 + by1) / 2

    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    for (text, is_active, _x, _ty, f), (sx, sy, sw, sh, l, t), pose in zip(placed, boxes, poses):
        if pose.alpha <= 0 or sw <= 0 or sh <= 0:
            continue
        fill = config.highlight_color if is_active else config.color
        key = (text, getattr(f, "path", None), getattr(f, "size", None), fill, stroke_width,
               config.stroke_color)
        sprite = _SPRITES.get(key)
        if sprite is None:
            sprite = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
            kw = dict(stroke_width=stroke_width, stroke_fill=config.stroke_color) if stroke_width else {}
            ImageDraw.Draw(sprite).text((-l, -t), text, font=f, fill=fill, **kw)
            if len(_SPRITES) > 512:
                _SPRITES.clear()
            _SPRITES[key] = sprite
        cx, cy = sx + sw / 2, sy + sh / 2
        shift = Pose(dx=(block.scale - 1) * (cx - bcx), dy=(block.scale - 1) * (cy - bcy))
        draw(layer, sprite, sx, sy, block + shift + pose)
    if config.shadow:
        img.alpha_composite(_soft_shadow(layer.getchannel("A"), config))
    img.alpha_composite(layer)
    return img


def _soft_shadow(mask: Image.Image, config: CaptionsConfig) -> Image.Image:
    """Blurred, tinted, semi-transparent copy of the text mask, offset downward. Only the
    text's region (plus the blur's reach) is blurred — the rest of the frame stays clear."""
    out = Image.new("RGBA", mask.size, (0, 0, 0, 0))
    box = mask.getbbox()
    if box is None:
        return out
    pad = 4 * config.shadow_blur + 4
    left, top = max(0, box[0] - pad), max(0, box[1] - pad)
    mask = mask.crop((left, top, min(mask.width, box[2] + pad), min(mask.height, box[3] + pad)))
    rgb = _hex_to_rgb(config.shadow_color)
    base = Image.new("RGBA", mask.size, (0, 0, 0, 0))
    base.paste(rgb + (255,), (0, 0), mask)
    base = base.filter(ImageFilter.GaussianBlur(config.shadow_blur))
    r, g, b, a = base.split()
    a = a.point(lambda v: int(v * config.shadow_opacity))
    shadow = Image.merge("RGBA", (r, g, b, a))
    out.alpha_composite(shadow, (left, top + config.shadow_offset))
    return out


def _hex_to_rgb(s: str) -> tuple[int, int, int]:
    s = s.lstrip("#")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _layout_tokens(
    draw: ImageDraw.ImageDraw,
    tokens: list[tuple[str, bool]],
    font: ImageFont.FreeTypeFont,
    font_highlight: ImageFont.FreeTypeFont,
    config: CaptionsConfig,
    canvas_w: int,
    y: int,
    margin: int = _MARGIN,
    y_bottom: int | None = None,
) -> list[tuple[str, bool, float, int, ImageFont.FreeTypeFont]]:
    """Wrap tokens to the canvas width and return positioned tokens, centred on `y` (or with
    the block's bottom at `y_bottom` when given).

    Returns a list of (text, is_active, x, y, font) so the caller can render both
    the shadow mask and the crisp text from identical positions. The active token
    uses font_highlight (baseline-aligned with the surrounding words).
    """
    max_w = canvas_w - 2 * margin
    space_w = draw.textlength(" ", font=font)

    # Wrap tokens into visual lines that each fit within max_w (advance-width based).
    # Use each token's actual font for width so wrap accounts for the larger active word.
    lines: list[list[tuple[str, bool]]] = []
    current: list[tuple[str, bool]] = []
    current_w = 0.0
    for text, is_active in tokens:
        f = font_highlight if is_active else font
        tok_w = draw.textlength(text, font=f)
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
    h_ascent, _ = font_highlight.getmetrics()
    line_h = ascent + descent
    total_h = line_h * len(lines) + config.line_spacing * (len(lines) - 1)
    start_y = y - total_h // 2 if y_bottom is None else y_bottom - total_h

    placed: list[tuple[str, bool, float, int, ImageFont.FreeTypeFont]] = []
    for row, line_tokens in enumerate(lines):
        f_list = [font_highlight if is_active else font for _, is_active in line_tokens]
        widths = [draw.textlength(text, font=f) for (text, _), f in zip(line_tokens, f_list)]
        line_w = sum(widths) + space_w * (len(line_tokens) - 1)
        x = (canvas_w - line_w) / 2
        x = max(margin, min(x, canvas_w - margin - line_w))
        cur_y = start_y + row * (line_h + config.line_spacing)

        for (text, is_active), tok_w, f in zip(line_tokens, widths, f_list):
            # Baseline-align the larger highlight font with surrounding words.
            word_y = cur_y + (ascent - h_ascent) if is_active else cur_y
            placed.append((text, is_active, x, word_y, f))
            x += tok_w + space_w
    return placed


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
    gap_break_s: float,
    sentence_pause_s: float = SENTENCE_PAUSE_S,
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
        sentence_end = is_sentence_boundary(current[-1].word, w.word, gap, sentence_pause_s)
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
