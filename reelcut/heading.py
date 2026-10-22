"""Heading renderer — static styled title cards burned in as overlay frames.

A heading is one title card on the **output-timeline** (the final video's clock), built by
the caller from the hand-authored `assets/<slug>/videos.json` (see `video_spec`). Each
heading is rendered once to a transparent PNG — an optional dark scrim, a soft-shadowed gold serif title, and an optional
italic subtitle — and that single PNG is reused for every frame in its `[start, end)` window.
The styling matches the approved Playfair-Display gold look.

A title's `*starred*` words are its accent: drawn in the style's accent colour, or with a
marker swept under them. A named style (`headings.styles`) lays its font, colours and case over
the base settings, so each series can look its own.

With motion (reelcut.motion HEADINGS) the lines enter — rising out of a slot, inked on left to
right, stamped down from big, or split in from both sides — then push in slowly while held,
and leave. The reel's first frame
then has no title on it, so the render writes a cover from a frame after `settled_s`.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .caption import CaptionFrame, FrameWriter, _resolve_font
from .config import HeadingsConfig
from .motion import Pose, clamp, draw, ease_in, ease_in_out, settle_s, spring

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
    style: str = ""            # a headings.styles name; "" → the base settings
    motion: str = ""           # this card's entrance (reelcut.motion HEADINGS); "" → the video's


def headings_from_videos(videos) -> list[HeadingSpec]:
    """Title cards for the combined render: one per titled base entry of videos.json."""
    from .video_spec import base_videos
    return [
        HeadingSpec(title=v.title, start=v.start, end=v.end, subtitle=v.subtitle, scrim=v.scrim,
                    style=v.style, motion=v.motion)
        for v in base_videos(videos)
        if v.title
    ]


def plain_title(text: str) -> str:
    """A title as plain text, without its accent stars."""
    return text.replace("*", "")


def styled(config: HeadingsConfig, style: str) -> HeadingsConfig:
    """`config` with the named title style laid over it; "" is the base settings."""
    if not style:
        return config
    if style not in config.styles:
        raise ValueError(f"unknown title style {style!r} — one of {', '.join(config.styles) or 'none set'}")
    return HeadingsConfig.model_validate({**config.model_dump(), **config.styles[style]})


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
        cfg = styled(config, h.style)
        if cfg.case == "upper":
            h = replace(h, title=h.title.upper())
        elif cfg.case == "lower":
            h = replace(h, title=h.title.lower())
        png = _render_heading_png(h, cfg, resolution, output_dir / f"heading_{idx:02d}.png")
        first, last = int(h.start * fps), int(end * fps)
        card_motion = h.motion or motion
        if card_motion == "none":
            frames.extend(CaptionFrame(frame_number=fn, image_path=png) for fn in range(first, last))
            continue
        exits = h.end >= 0 and (total_output_s <= 0 or end < total_output_s)
        frames.extend(_moving_frames(h, cfg, resolution, output_dir / f"heading_{idx:02d}",
                                     fps, first, last, exits, card_motion, spring_name))
    return frames


_LINE_STAGGER_S = 0.08


_MARK_S = 0.45  # an accent marker's sweep, once the lines are in


def settled_s(spring_name: str) -> float:
    """Seconds after its start by which a moving title card has fully entered — up to four
    lines once the title wraps, then its accent marker."""
    return 4 * _LINE_STAGGER_S + settle_s(spring_name) + _MARK_S + 0.1
_HEADING_EXIT_S = 0.3
_PUSH = 0.025  # how far the title pushes in over its window


def _moving_frames(h, config, resolution, out_dir: Path, fps, first, last, exits, motion, spring_name):
    """One frame per output frame of a moving title card (see the module docstring)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    w, hgt = resolution
    use_scrim = config.scrim if h.scrim is None else h.scrim
    scrim = _scrim(w, hgt, config.scrim_strength) if use_scrim else None
    lines, marks = _line_sprites(h, config, resolution)
    x0 = min(x for _, x, _ in lines)
    x1 = max(x + sp.width for sp, x, _ in lines)
    y0 = min(y for _, _, y in lines)
    y1 = max(y + sp.height for sp, _, y in lines)
    gcx, gcy = (x0 + x1) / 2, (y0 + y1) / 2
    n_out = round(_HEADING_EXIT_S * fps) if exits else 0
    landed = (len(lines) - 1) * _LINE_STAGGER_S + settle_s(spring_name)

    def line_pose(i: int, t: float, out_q: float) -> Pose:
        """Line i's entrance (and exit) pose, before the push-in."""
        if motion == "stamp":  # the whole title lands at once, from big
            p = spring(t, spring_name)
            pose = Pose(scale=1.25 - 0.25 * p, alpha=clamp(p * 3))
        elif motion == "split":  # lines slide in from alternate sides
            p = spring(t - i * _LINE_STAGGER_S, spring_name)
            pose = Pose(dx=(1 - p) * 0.6 * w * (-1 if i % 2 == 0 else 1), alpha=clamp(p * 2))
        else:
            p = spring(t - i * _LINE_STAGGER_S, spring_name)
            amount = min(p, 1 - ease_in(out_q)) if out_q else p
            return Pose(reveal="slot" if motion == "slot" else "ink", amount=amount)
        return pose + Pose(alpha=1 - ease_in(out_q)) if out_q else pose

    frames = []
    cache: dict[tuple, str] = {}
    writer = FrameWriter()
    for fn in range(first, last):
        t, left = (fn - first) / fps, (last - fn) / fps
        # Stepped in under half a pixel across the title, so held frames can share files.
        push = round((1 + _PUSH * ease_in_out((fn - first) / max(1, last - first - 1))) * 2000) / 2000
        out_q = clamp(1 - left / _HEADING_EXIT_S) if n_out else 0.0
        a = clamp(t / 0.25) * (1 - out_q)
        poses = []
        for i, (sprite, x, y) in enumerate(lines):
            cx, cy = x + sprite.width / 2, y + sprite.height / 2
            pose = line_pose(i, t, out_q)
            # Scale (stamp, push-in) is about the whole title's centre, so it grows as one.
            sc = pose.scale * push
            poses.append(pose + Pose(scale=push, dx=(sc - 1) * (cx - gcx), dy=(sc - 1) * (cy - gcy)))
        mark = clamp((t - landed) / _MARK_S)
        mark = min(ease_in_out(mark), 1 - ease_in(out_q)) if out_q else ease_in_out(mark)
        key = (round(a, 3), push, round(mark, 3), tuple(ps.key() for ps in poses))
        if key not in cache:
            canvas = Image.new("RGBA", (w, hgt), (0, 0, 0, 0))
            if scrim is not None:
                draw(canvas, scrim, 0, 0, Pose(alpha=a))
            for i, (sprite, x, y) in enumerate(marks):
                if sprite is not None and mark > 0:
                    lp = poses[i]
                    draw(canvas, sprite, x, y, Pose(scale=lp.scale, dx=lp.dx, dy=lp.dy, alpha=lp.alpha,
                                                    reveal="ink", amount=mark))
            for (sprite, x, y), pose in zip(lines, poses):
                draw(canvas, sprite, x, y, pose)
            cache[key] = str(out_dir / f"{fn:06d}.png")
            writer.save(canvas, cache[key])
        frames.append(CaptionFrame(frame_number=fn, image_path=cache[key]))
    writer.wait()
    return frames


def _line_sprites(h: HeadingSpec, config: HeadingsConfig, resolution: tuple[int, int]):
    """Each title line and the subtitle as (sprite with its shadow, x, y) at output size,
    placed exactly where _render_heading_png draws them — and, parallel to them, each line's
    accent marker as (sprite, x, y), or (None, 0, 0) when it has none."""
    w, hgt = resolution
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    max_w = w * _SS * (1 - 2 * config.margin_pct / 100)
    title_font, title_lines = _fit_title(probe, h.title, config, max_w)
    ascent, descent = title_font.getmetrics()
    y = int(hgt * _POSITION_TOP_FRAC.get(config.position, 0.08) * _SS)
    rows = []
    for ln in title_lines:
        rows.append((ln, title_font, config.color, y))
        y += int((ascent + descent) * config.line_height)
    if h.subtitle:
        sub_font = _load_font(config.subtitle_font, config.subtitle_size, ("Italic", "Medium Italic", "Regular"))
        rows.append((h.subtitle, sub_font, config.subtitle_color, y + int(18 * _SS)))

    out, marks = [], []
    accent = False  # an accent can carry over a line break
    for text, font, fill, top in rows:
        txt = Image.new("RGBA", (w * _SS, hgt * _SS), (0, 0, 0, 0))
        rects: list = []
        accent = _draw_centered(ImageDraw.Draw(txt), txt.width, [text], font, fill, top,
                                config, rects, accent)[1]
        layer = Image.new("RGBA", (w, hgt), (0, 0, 0, 0))
        if config.shadow:
            layer.alpha_composite(_soft_shadow(txt, config.shadow_blur, config.shadow_opacity, w, hgt), (0, 5))
        layer.alpha_composite(txt.resize((w, hgt), Image.LANCZOS))
        box = layer.getbbox()
        if not box:
            continue
        out.append((layer.crop(box), box[0], box[1]))
        marker = _marks(rects, config, w, hgt) if rects else None
        mbox = marker.getbbox() if marker else None
        marks.append((marker.crop(mbox), mbox[0], mbox[1]) if mbox else (None, 0, 0))
    return out, marks


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
    rects: list = []
    y, _ = _draw_centered(draw, txt.width, title_lines, title_font, config.color, top, config, rects)
    if h.subtitle:
        y += int(18 * _SS)
        _draw_centered(draw, txt.width, [h.subtitle], sub_font, config.subtitle_color, y)

    if config.shadow:
        overlay.alpha_composite(_soft_shadow(txt, config.shadow_blur, config.shadow_opacity, w, hgt), (0, 5))
    if rects:
        overlay.alpha_composite(_marks(rects, config, w, hgt))
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
    bbox = draw.textbbox((0, 0), plain_title(line), font=font)
    return bbox[2] - bbox[0]


def _draw_centered(draw, canvas_w, lines, font, fill, top_y, config: HeadingsConfig | None = None,
                   marks: list | None = None, accent: bool = False) -> tuple[int, bool]:
    """Draw centered lines from top_y. `*starred*` words are drawn in config.accent_color, or —
    with config.accent "marker" — their boxes are added to `marks` for a marker under them.
    `accent` says whether the first line opens inside a starred run. Returns the y below the
    block and whether the last line ended inside one."""
    ascent, descent = font.getmetrics()
    line_h = int((ascent + descent) * (config.line_height if config else 1.02))
    y = top_y
    for ln in lines:
        plain = plain_title(ln)
        bbox = draw.textbbox((0, 0), plain, font=font)
        x = (canvas_w - (bbox[2] - bbox[0])) / 2 - bbox[0]
        if "*" not in ln and not accent:
            draw.text((x, y), ln, font=font, fill=fill)
        else:
            for i, seg in enumerate(ln.split("*")):
                on = accent if i == 0 else not on
                if seg:
                    seg_w = draw.textlength(seg, font=font)
                    if on and config and config.accent == "marker" and marks is not None:
                        marks.append((x, y + ascent * 0.42, x + seg_w, y + ascent * 1.08))
                    use = config.accent_color if on and config and config.accent == "color" else fill
                    draw.text((x, y), seg, font=font, fill=use)
                    x += seg_w
            accent = on
        y += line_h
    return y, accent


def _marks(rects: list, config: HeadingsConfig, w: int, h: int) -> Image.Image:
    """The accent marker behind starred words: a highlighter stroke per run, at output size."""
    layer = Image.new("RGBA", (w * _SS, h * _SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    fill = tuple(int(config.accent_color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)) + (215,)
    for x0, y0, x1, y1 in rects:
        pad = (y1 - y0) * 0.18
        d.rounded_rectangle([x0 - pad, y0, x1 + pad, y1], radius=(y1 - y0) * 0.22, fill=fill)
    return layer.resize((w, h), Image.LANCZOS)


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
