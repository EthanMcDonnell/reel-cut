"""Heading renderer — static styled title cards burned in as overlay frames.

Headings are hand-authored in `assets/<slug>/headings.json` (a list of title cards on
the **output-timeline**, i.e. the final video's clock). Each heading is rendered once to a
transparent PNG — an optional dark scrim, a soft-shadowed gold serif title, and an optional
italic subtitle — and that single PNG is reused for every frame in its `[start, end)` window.
No animation; the styling matches the approved Playfair-Display gold look.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .caption import CaptionFrame, _resolve_font
from .config import HeadingsConfig

_SS = 2  # supersample factor — render large, downscale for crisp edges
_FONTS_DIR = Path(__file__).parent / "fonts"
_POSITION_TOP_FRAC = {"top": 0.05, "upper-third": 0.08, "center": 0.40}


@dataclass
class HeadingSpec:
    title: str                 # may contain "\n" for explicit line breaks
    start: float               # output-timeline seconds
    end: float                 # output-timeline seconds
    subtitle: str = ""
    scrim: bool | None = None  # None → use config default


def load_headings(path: Path) -> list[HeadingSpec]:
    """Load headings.json (a JSON list of heading objects). Missing keys are tolerated."""
    raw = json.loads(Path(path).read_text())
    if not isinstance(raw, list):
        raise ValueError(f"{path} must be a JSON list of heading objects")
    return [
        HeadingSpec(
            title=h.get("title", ""),
            start=float(h.get("start", 0.0)),
            end=float(h.get("end", 0.0)),
            subtitle=h.get("subtitle", ""),
            scrim=h.get("scrim"),
        )
        for h in raw
    ]


def render_heading_frames(
    headings: list[HeadingSpec],
    config: HeadingsConfig,
    output_dir: Path,
    fps: int,
    resolution: tuple[int, int],
    total_output_s: float = 0.0,
) -> list[CaptionFrame]:
    """Render each heading to one static PNG and emit a CaptionFrame per output frame in its
    [start, end) window — the same PNG path is reused for every frame (no animation).
    An end of -1 means "until the end of the video" (requires total_output_s)."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    frames: list[CaptionFrame] = []
    for idx, h in enumerate(headings):
        if not h.title:
            continue
        end = total_output_s if h.end < 0 else h.end
        if end <= h.start:
            continue
        png = _render_heading_png(h, config, resolution, output_dir / f"heading_{idx:02d}.png")
        for fn in range(int(h.start * fps), int(end * fps)):
            frames.append(CaptionFrame(frame_number=fn, image_path=png))
    return frames


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
