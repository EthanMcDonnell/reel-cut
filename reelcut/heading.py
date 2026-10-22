"""Heading renderer — static styled title cards burned in as overlay frames.

A heading is one title card on the **output-timeline** (the final video's clock), built by
the caller from the hand-authored `assets/<slug>/videos.json` (see `video_spec`). Each
heading is rendered once to a transparent PNG — an optional dark scrim, a soft-shadowed gold serif title, and an optional
italic subtitle — and that single PNG is reused for every frame in its `[start, end)` window.
The styling matches the approved Playfair-Display gold look.

With motion (reelcut.motion HEADINGS) the lines enter — rising out of a slot, or inked on
left to right — then push in slowly while held, and leave the same way. A card starting on the
video's first frame skips its entrance: that frame is the reel's cover, so it shows the card.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .caption import CaptionFrame, FrameWriter, _resolve_font
from .config import HeadingsConfig
from .motion import Pose, clamp, draw, ease_in, ease_in_out, spring

_SS = 2  # supersample factor — render large, downscale for crisp edges
_FONTS_DIR = Path(__file__).parent / "fonts"
_POSITION_TOP_FRAC = {"top": 0.05, "upper-third": 0.08, "center": 0.40}

# `{n:<series>}` in a title/subtitle → this video's 1-based episode number within <series>.
_SERIES_TOKEN_RE = re.compile(r"\{n:([a-z0-9][a-z0-9\-]*)\}")


@dataclass
class HeadingSpec:
    title: str                 # may contain "\n" for explicit line breaks
    start: float               # output-timeline seconds
    end: float                 # output-timeline seconds
    subtitle: str = ""
    scrim: bool | None = None  # None → use config default


def headings_from_videos(videos) -> list[HeadingSpec]:
    """Title cards for the combined render: one per titled base entry of videos.json."""
    from .video_spec import base_videos
    return [
        HeadingSpec(title=v.title, start=v.start, end=v.end, subtitle=v.subtitle, scrim=v.scrim)
        for v in base_videos(videos)
        if v.title
    ]


def render_heading_frames(
    headings: list[HeadingSpec],
    config: HeadingsConfig,
    output_dir: Path,
    fps: int,
    resolution: tuple[int, int],
    total_output_s: float = 0.0,
    slug: str | None = None,
    registry_path: Path | None = None,
    motion: str = "none",
    spring_name: str = "snappy",
) -> list[CaptionFrame]:
    """Render each heading to one static PNG and emit a CaptionFrame per output frame in its
    [start, end) window — the same PNG path is reused for every frame (no animation).
    An end of -1 means "until the end of the video" (requires total_output_s).

    A `{n:<series>}` token in a title/subtitle is replaced with this video's episode number
    in that series, allocated once via the `series_index.json` registry (needs slug +
    registry_path)."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    frames: list[CaptionFrame] = []
    for idx, h in enumerate(headings):
        if not h.title:
            continue
        end = total_output_s if h.end < 0 else h.end
        if total_output_s > 0:
            end = min(end, total_output_s)
        if end <= h.start:
            continue
        h = replace(
            h,
            title=_resolve_series_tokens(h.title, slug, registry_path),
            subtitle=_resolve_series_tokens(h.subtitle, slug, registry_path),
        )
        png = _render_heading_png(h, config, resolution, output_dir / f"heading_{idx:02d}.png")
        first, last = int(h.start * fps), int(end * fps)
        if motion == "none":
            frames.extend(CaptionFrame(frame_number=fn, image_path=png) for fn in range(first, last))
            continue
        exits = h.end >= 0 and (total_output_s <= 0 or end < total_output_s)
        frames.extend(_moving_frames(h, config, resolution, output_dir / f"heading_{idx:02d}",
                                     fps, first, last, exits, motion, spring_name))
    return frames


_LINE_STAGGER_S = 0.08
_HEADING_EXIT_S = 0.3
_PUSH = 0.025  # how far the title pushes in over its window


def _moving_frames(h, config, resolution, out_dir: Path, fps, first, last, exits, motion, spring_name):
    """One frame per output frame of a moving title card (see the module docstring)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    w, hgt = resolution
    use_scrim = config.scrim if h.scrim is None else h.scrim
    scrim = _scrim(w, hgt, config.scrim_strength) if use_scrim else None
    lines = _line_sprites(h, config, resolution)
    x0 = min(x for _, x, _ in lines)
    x1 = max(x + sp.width for sp, x, _ in lines)
    y0 = min(y for _, _, y in lines)
    y1 = max(y + sp.height for sp, _, y in lines)
    gcx, gcy = (x0 + x1) / 2, (y0 + y1) / 2
    reveal = "slot" if motion == "slot" else "ink"
    enters = first > 0
    n_out = round(_HEADING_EXIT_S * fps) if exits else 0

    frames = []
    cache: dict[tuple, str] = {}
    writer = FrameWriter()
    for fn in range(first, last):
        t, left = (fn - first) / fps, (last - fn) / fps
        # Stepped in under half a pixel across the title, so held frames can share files.
        push = round((1 + _PUSH * ease_in_out((fn - first) / max(1, last - first - 1))) * 2000) / 2000
        out_q = clamp(1 - left / _HEADING_EXIT_S) if n_out else 0.0
        a = (clamp(t / 0.25) if enters else 1.0) * (1 - out_q)
        amounts = [spring(t - i * _LINE_STAGGER_S, spring_name) if enters else 1.0
                   for i in range(len(lines))]
        if out_q:
            amounts = [min(am, 1 - ease_in(out_q)) for am in amounts]
        key = (round(a, 3), push, tuple(round(clamp(am), 3) for am in amounts))
        if key not in cache:
            canvas = Image.new("RGBA", (w, hgt), (0, 0, 0, 0))
            if scrim is not None:
                draw(canvas, scrim, 0, 0, Pose(alpha=a))
            for (sprite, x, y), amount in zip(lines, amounts):
                cx, cy = x + sprite.width / 2, y + sprite.height / 2
                draw(canvas, sprite, x, y, Pose(scale=push, dx=(push - 1) * (cx - gcx),
                                                dy=(push - 1) * (cy - gcy), reveal=reveal, amount=amount))
            cache[key] = str(out_dir / f"{fn:06d}.png")
            writer.save(canvas, cache[key])
        frames.append(CaptionFrame(frame_number=fn, image_path=cache[key]))
    writer.wait()
    return frames


def _line_sprites(h: HeadingSpec, config: HeadingsConfig, resolution: tuple[int, int]):
    """Each title line and the subtitle as (sprite with its shadow, x, y) at output size,
    placed exactly where _render_heading_png draws them."""
    w, hgt = resolution
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    max_w = w * _SS * (1 - 2 * config.margin_pct / 100)
    title_font, title_lines = _fit_title(probe, h.title, config, max_w)
    ascent, descent = title_font.getmetrics()
    y = int(hgt * _POSITION_TOP_FRAC.get(config.position, 0.08) * _SS)
    rows = []
    for ln in title_lines:
        rows.append((ln, title_font, config.color, y))
        y += int((ascent + descent) * 1.02)
    if h.subtitle:
        sub_font = _load_font(config.subtitle_font, config.subtitle_size, ("Italic", "Medium Italic", "Regular"))
        rows.append((h.subtitle, sub_font, config.subtitle_color, y + int(18 * _SS)))

    out = []
    for text, font, fill, top in rows:
        txt = Image.new("RGBA", (w * _SS, hgt * _SS), (0, 0, 0, 0))
        _draw_centered(ImageDraw.Draw(txt), txt.width, [text], font, fill, top)
        layer = Image.new("RGBA", (w, hgt), (0, 0, 0, 0))
        if config.shadow:
            layer.alpha_composite(_soft_shadow(txt, config.shadow_blur, config.shadow_opacity, w, hgt), (0, 5))
        layer.alpha_composite(txt.resize((w, hgt), Image.LANCZOS))
        box = layer.getbbox()
        if box:
            out.append((layer.crop(box), box[0], box[1]))
    return out


# ---------------------------------------------------------------------------
# Series episode counter
# ---------------------------------------------------------------------------

def _resolve_series_tokens(text: str, slug: str | None, registry_path: Path | None) -> str:
    """Replace every `{n:<series>}` in `text` with this slug's 1-based number in that series."""
    if not text or "{n:" not in text:
        return text
    if slug is None or registry_path is None:
        raise ValueError("a {n:<series>} heading token needs both slug and registry_path")
    return _SERIES_TOKEN_RE.sub(
        lambda m: str(_series_number(m.group(1), slug, Path(registry_path))), text
    )


def _series_number(series: str, slug: str, registry_path: Path) -> int:
    """Return this slug's episode number in `series`. New slugs increment `last`; re-renders
    reuse the stored number so a video's episode number never drifts."""
    registry = json.loads(registry_path.read_text()) if registry_path.exists() else {}
    entry = registry.setdefault(series, {"last": 0, "slugs": {}})
    if slug not in entry["slugs"]:
        entry["last"] += 1
        entry["slugs"][slug] = entry["last"]
        registry_path.write_text(json.dumps(registry, indent=2) + "\n")
    return entry["slugs"][slug]


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _render_heading_png(
    h: HeadingSpec, config: HeadingsConfig, resolution: tuple[int, int], out_path: Path
) -> str:
    """Compose one heading: scrim (bottom) → soft shadow → gold title + subtitle (top)."""
    w, hgt = resolution
    overlay = Image.new("RGBA", (w, hgt), (0, 0, 0, 0))

    use_scrim = config.scrim if h.scrim is None else h.scrim
    if use_scrim:
        overlay.alpha_composite(_scrim(w, hgt, config.scrim_strength))

    # Draw text on a supersampled canvas for crisp downscaled edges.
    txt = Image.new("RGBA", (w * _SS, hgt * _SS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(txt)
    sub_font = _load_font(config.subtitle_font, config.subtitle_size, ("Italic", "Medium Italic", "Regular"))

    # Word-wrap the title and shrink the font until it fits inside the side margins.
    max_w = txt.width * (1 - 2 * config.margin_pct / 100)
    title_font, title_lines = _fit_title(draw, h.title, config, max_w)

    top = int(hgt * _POSITION_TOP_FRAC.get(config.position, 0.08) * _SS)
    y = _draw_centered(draw, txt.width, title_lines, title_font, config.color, top)
    if h.subtitle:
        y += int(18 * _SS)
        _draw_centered(draw, txt.width, [h.subtitle], sub_font, config.subtitle_color, y)

    if config.shadow:
        overlay.alpha_composite(_soft_shadow(txt, config.shadow_blur, config.shadow_opacity, w, hgt), (0, 5))
    overlay.alpha_composite(txt.resize((w, hgt), Image.LANCZOS))

    overlay.save(str(out_path), format="PNG")
    return str(out_path)


def _scrim(w: int, h: int, strength: int) -> Image.Image:
    """Vertical dark gradient, opaque at the top fading to clear by ~42% height."""
    grad = Image.new("L", (1, h))
    for yy in range(h):
        grad.putpixel((0, yy), int(strength * max(0.0, 1 - yy / (h * 0.42))))
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    layer.putalpha(grad.resize((w, h)))
    return layer


def _soft_shadow(txt: Image.Image, blur: int, opacity: float, w: int, h: int) -> Image.Image:
    """Blurred black copy of the text alpha, scaled to the final resolution."""
    shadow = Image.new("RGBA", txt.size, (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 255), (0, 0), txt.split()[3])
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur * _SS))
    r, g, b, a = shadow.split()
    a = a.point(lambda v: int(v * opacity))
    return Image.merge("RGBA", (r, g, b, a)).resize((w, h), Image.LANCZOS)


def _fit_title(draw, text, config: HeadingsConfig, max_w: float):
    """Return (font, lines) for the title — word-wrapped, then shrunk until every line fits
    within max_w. Explicit "\\n" breaks are always honored. Stops shrinking at half the
    configured size; if a single word is still too wide it's left to overflow (rare)."""
    prefer = ("Black", "ExtraBold", "Bold", "SemiBold")
    floor = max(1, int(config.title_size * 0.5))
    size = config.title_size
    while True:
        font = _load_font(config.font, size, prefer)
        lines = _wrap_lines(draw, text, font, max_w)
        widest = max((_line_w(draw, ln, font) for ln in lines), default=0)
        if widest <= max_w or size <= floor:
            return font, lines
        size -= 4


def _wrap_lines(draw, text, font, max_w: float) -> list[str]:
    """Greedy word-wrap each explicit "\\n" paragraph so no line exceeds max_w."""
    out: list[str] = []
    for para in text.split("\n"):
        words = para.split()
        if not words:
            out.append("")
            continue
        cur = words[0]
        for word in words[1:]:
            trial = f"{cur} {word}"
            if _line_w(draw, trial, font) <= max_w:
                cur = trial
            else:
                out.append(cur)
                cur = word
        out.append(cur)
    return out


def _line_w(draw, line, font) -> float:
    bbox = draw.textbbox((0, 0), line, font=font)
    return bbox[2] - bbox[0]


def _draw_centered(draw, canvas_w, lines, font, fill, top_y) -> int:
    """Draw centered lines from top_y. Returns the y below the block."""
    ascent, descent = font.getmetrics()
    line_h = int((ascent + descent) * 1.02)
    y = top_y
    for ln in lines:
        bbox = draw.textbbox((0, 0), ln, font=font)
        x = (canvas_w - (bbox[2] - bbox[0])) / 2 - bbox[0]
        draw.text((x, y), ln, font=font, fill=fill)
        y += line_h
    return y


def _load_font(name: str, size: int, prefer: tuple[str, ...]) -> ImageFont.FreeTypeFont:
    """Load a (possibly variable) font and select the preferred named weight/style.

    Checks bundled `reelcut/fonts/<name>.ttf` first, then the shared system resolver.
    """
    bundled = _FONTS_DIR / f"{name}.ttf"
    resolved = str(bundled) if bundled.exists() else (_resolve_font(name) or (None,))[0]
    if not resolved:
        return ImageFont.load_default()

    font = ImageFont.truetype(resolved, int(size * _SS))
    try:
        names = font.get_variation_names()
    except Exception:
        return font  # static font — nothing to select
    for want in prefer:
        for n in names:
            label = n.decode("latin-1") if isinstance(n, (bytes, bytearray)) else n
            if want.lower() in label.lower():
                try:
                    font.set_variation_by_name(n)
                    return font
                except Exception:
                    pass
    return font
