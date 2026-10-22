"""Motion — the springs, moves and looks every animated layer shares.

Every movement is a pure function of time, so a frame renders the same however it is reached.
A move turns progress (0 → 1, overshooting past 1 on a spring) into a `Pose`: an offset, scale,
rotation, opacity and an optional reveal mask, drawn by `draw`.

What a video uses is a `Motion`, resolved from layers: `config.yaml` `motion:` → the slug's
`motion.json` → an images.json entry's `motion`. A layer's `look` resets every field to that
look's bundle before its own fields apply, so `{"look": "calm", "hold": "still"}` is calm with
still holds.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

# (stiffness, damping, mass). None of these is Remotion's default spring (100/10/1), whose
# slow wobble is the tell of a stock template.
SPRINGS = {
    "snappy": (420.0, 30.0, 1.0),   # quick, a hair of overshoot
    "bouncy": (320.0, 15.0, 1.0),   # visible overshoot and one rebound
    "gentle": (140.0, 24.0, 1.0),   # no overshoot, eases in over ~0.6s
    "heavy": (200.0, 22.0, 2.2),    # slow, weighty single overshoot
}
ENTERS = ("snap", "fade", "pop", "rise", "drop", "slide", "swing", "stamp", "slot", "wipe", "iris", "shutter")
# An exit plays an entrance backwards: lift = drop reversed (leaves upward), sink = rise reversed.
EXITS = {"snap": "snap", "fade": "fade", "lift": "drop", "sink": "rise", "shrink": "pop",
         "slot": "slot", "wipe": "wipe", "iris": "iris", "shutter": "shutter"}
HOLDS = ("still", "drift", "push")
TRANSITIONS = ("cut", "swap", "push", "stack", "dissolve")
CAPTIONS = ("none", "pop", "words")
HEADINGS = ("none", "slot", "ink")

LOOKS = {
    "none": dict(spring="snappy", enter="fade", exit="fade", hold="still", transition="cut",
                 tilt=0.0, captions="none", heading="none"),
    "editorial": dict(spring="snappy", enter="swing", exit="lift", hold="drift", transition="stack",
                      tilt=1.5, captions="pop", heading="slot"),
    "punchy": dict(spring="bouncy", enter="stamp", exit="snap", hold="still", transition="push",
                   tilt=0.0, captions="words", heading="slot"),
    "calm": dict(spring="gentle", enter="rise", exit="fade", hold="push", transition="dissolve",
                 tilt=0.0, captions="pop", heading="ink"),
}
_CHOICES = {"spring": SPRINGS, "enter": ENTERS, "exit": EXITS, "hold": HOLDS,
            "transition": TRANSITIONS, "captions": CAPTIONS, "heading": HEADINGS}
_FIELDS = (*_CHOICES, "tilt")

EXIT_S = 0.22        # an exit's length (a fade's is images.fade_duration_s)
DISSOLVE_S = 0.3
_SETTLE_EPS = 0.004  # a spring has settled once it stays this close to 1


@dataclass(frozen=True)
class Motion:
    spring: str = "snappy"
    enter: str = "fade"
    exit: str = "fade"
    hold: str = "still"
    transition: str = "cut"
    tilt: float = 0.0
    captions: str = "none"
    heading: str = "none"


def resolve(*layers: dict | None) -> Motion:
    """The Motion for these override layers, earliest first (see module docstring)."""
    vals = dict(LOOKS["none"])
    for layer in layers:
        for key, value in (layer or {}).items():
            if value is None:
                continue
            if key == "look":
                if value not in LOOKS:
                    raise ValueError(f"unknown motion look {value!r} — one of {', '.join(LOOKS)}")
                vals.update(LOOKS[value])
            elif key == "tilt":
                vals["tilt"] = float(value)
            elif key in _CHOICES:
                if value not in _CHOICES[key]:
                    raise ValueError(f"unknown motion {key} {value!r} — one of {', '.join(_CHOICES[key])}")
                vals[key] = value
            else:
                raise ValueError(f"unknown motion key {key!r} — one of look, {', '.join(_FIELDS)}")
    return Motion(**vals)


def load_motion(path: Path) -> dict:
    """A slug's motion.json — one override layer. Missing file → {}."""
    path = Path(path)
    if not path.exists():
        return {}
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must be a JSON object")
    return raw


def catalog() -> str:
    """Every valid name, for `reelcut motion --list`."""
    rows = [f"look        {', '.join(LOOKS)}"]
    rows += [f"{k:<11} {', '.join(v)}" for k, v in _CHOICES.items()]
    rows.append("tilt        resting angle in degrees, alternating sign per overlay")
    rows += ["", "looks:"] + [f"  {name:<10} " + " ".join(f"{k}={v}" for k, v in vals.items())
                              for name, vals in LOOKS.items()]
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# Timing
# ---------------------------------------------------------------------------

def spring(t: float, name: str = "snappy") -> float:
    """A spring released from 0 toward 1 at t=0 (seconds), at rest. Underdamped springs overshoot.
    Exactly 1 from settle_s on, so a settled frame matches a still one."""
    if t >= settle_s(name):
        return 1.0
    return _spring(t, name)


def _spring(t: float, name: str) -> float:
    if t <= 0:
        return 0.0
    k, c, m = SPRINGS[name]
    w0 = math.sqrt(k / m)
    zeta = c / (2 * math.sqrt(k * m))
    if zeta < 1:
        wd = w0 * math.sqrt(1 - zeta * zeta)
        return 1 - math.exp(-zeta * w0 * t) * (math.cos(wd * t) + zeta * w0 / wd * math.sin(wd * t))
    if zeta == 1:
        return 1 - math.exp(-w0 * t) * (1 + w0 * t)
    r1 = -w0 * (zeta - math.sqrt(zeta * zeta - 1))
    r2 = -w0 * (zeta + math.sqrt(zeta * zeta - 1))
    return 1 - (r2 * math.exp(r1 * t) - r1 * math.exp(r2 * t)) / (r2 - r1)


@lru_cache(maxsize=None)
def settle_s(name: str = "snappy") -> float:
    """Seconds until the spring stays within _SETTLE_EPS of 1."""
    step = 1 / 240
    last = 0.0
    for i in range(1, 240 * 3):
        if abs(1 - _spring(i * step, name)) > _SETTLE_EPS:
            last = i * step
    return last + step


def ease_in(q: float) -> float:
    return q * q * q


def ease_in_out(q: float) -> float:
    return 4 * q ** 3 if q < 0.5 else 1 - (-2 * q + 2) ** 3 / 2


def css_vars(name: str = "snappy") -> str:
    """`--spring` (a CSS linear() easing traced from the spring) and `--spring-s`, for cards."""
    dur = settle_s(name)
    n = max(8, round(dur * 60))
    pts = ", ".join(f"{_spring(dur * i / n, name) if i < n else 1:.4f}".rstrip("0").rstrip(".") for i in range(n + 1))
    return f":root {{ --spring: linear({pts}); --spring-s: {dur:.3f}s; }}"


def noise(seed: int, t: float) -> float:
    """Smooth value noise in [-1, 1], one new random level per unit of t."""
    i = math.floor(t)
    f = t - i
    a, b = _hash(seed, i), _hash(seed, i + 1)
    return a + (b - a) * f * f * (3 - 2 * f)


def _hash(seed: int, n: int) -> float:
    x = math.sin(n * 127.1 + seed * 311.7) * 43758.5453
    return (x - math.floor(x)) * 2 - 1


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


# ---------------------------------------------------------------------------
# Poses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Pose:
    dx: float = 0.0
    dy: float = 0.0
    scale: float = 1.0
    rot: float = 0.0          # degrees, counter-clockwise
    alpha: float = 1.0
    reveal: str = ""          # "slot" | "wipe" | "ink" | "iris" | "shutter"
    amount: float = 1.0       # how much of the reveal is open
    pivot: float = 0.5        # where on the sprite's height it rotates about: 0 top, 0.5 centre

    def __add__(self, o: "Pose") -> "Pose":
        reveal, amount = self.reveal, self.amount
        if o.reveal and (not reveal or o.amount < amount):
            reveal, amount = o.reveal, o.amount
        return Pose(self.dx + o.dx, self.dy + o.dy, self.scale * o.scale, self.rot + o.rot,
                    self.alpha * o.alpha, reveal, amount, o.pivot if o.pivot != 0.5 else self.pivot)

    def key(self) -> tuple:
        """Rounded to what can show, so frames that look the same share one file."""
        return (round(self.dx * 2) / 2, round(self.dy * 2) / 2, round(self.scale, 4),
                round(self.rot, 2), round(self.alpha, 3), self.reveal,
                round(clamp(self.amount), 3) if self.reveal else 1.0, self.pivot)


STILL = Pose()


def enter_pose(move: str, p: float, frame: tuple[int, int], k: int = 0) -> Pose:
    """The pose `p` of the way into entrance `move` (p may overshoot 1). `k` is the overlay's
    order, so alternating moves (slide, swing) take turns sides."""
    fw, fh = frame
    side = 1 if k % 2 == 0 else -1
    a = clamp(p * 2.5)
    if move == "snap" or p >= 1 and move in ("fade", "slot", "wipe", "iris", "shutter"):
        return STILL
    if move == "fade":
        return Pose(alpha=clamp(p))
    if move == "pop":
        return Pose(scale=0.86 + 0.14 * p, alpha=a)
    if move == "rise":
        return Pose(dy=(1 - p) * 0.05 * fh, alpha=a)
    if move == "drop":
        return Pose(dy=-(1 - p) * 0.05 * fh, alpha=a)
    if move == "slide":
        return Pose(dx=side * (1 - p) * 0.5 * fw, alpha=a)
    if move == "swing":
        return Pose(rot=side * (1 - p) * 9, dy=-(1 - p) * 0.015 * fh, alpha=a, pivot=0.0)
    if move == "stamp":
        return Pose(scale=1.22 - 0.22 * p, alpha=clamp(p * 4))
    return Pose(reveal=move, amount=clamp(p))


def exit_pose(move: str, q: float, frame: tuple[int, int], k: int = 0) -> Pose:
    """The pose `q` of the way out (0 = still settled, 1 = gone)."""
    if move == "fade":
        return Pose(alpha=clamp(1 - q))
    return enter_pose(EXITS[move], 1 - ease_in(clamp(q)), frame, k)


def hold_pose(hold: str, u: float, t: float, seed: int, frame: tuple[int, int]) -> Pose:
    """The pose while held: `u` is the share of the overlay's time gone, `t` its seconds on screen."""
    if hold == "push":
        return Pose(scale=1 + 0.035 * ease_in_out(clamp(u)))
    if hold == "drift":
        amp = 0.006 * frame[0]
        s = t * 0.4
        return Pose(dx=amp * noise(seed, s), dy=amp * noise(seed + 101, s),
                    rot=0.6 * noise(seed + 202, s))
    return STILL


def transition_poses(kind: str, p: float, lin: float, frame: tuple[int, int]) -> tuple[Pose | None, Pose | None]:
    """(outgoing pose or None to drop it, incoming pose or None to play its own entrance).
    `p` is the transition's eased progress, `lin` its share of frames gone."""
    fw, fh = frame
    if kind == "push":
        return Pose(dx=-p * 0.6 * fw, alpha=clamp(1 - p)), Pose(dx=(1 - p) * 0.6 * fw)
    if kind == "stack":  # the old one sinks back and stays under until the new one lands
        return Pose(scale=1 - 0.06 * lin, dy=0.012 * fh * lin, alpha=1 - ease_in(lin)), None
    if kind == "dissolve":
        return Pose(alpha=clamp(1 - p)), Pose(alpha=clamp(p))
    if kind == "swap":
        return None, None
    return None, STILL  # cut


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

def draw(canvas: Image.Image, sprite: Image.Image, x: float, y: float, pose: Pose = STILL) -> None:
    """Alpha-composite `sprite`, whose resting top-left is (x, y), onto `canvas` in `pose`."""
    if pose.alpha <= 0:
        return
    if pose.reveal and pose.amount < 1:
        sprite = _reveal(sprite, pose.reveal, clamp(pose.amount))
    w, h = sprite.size
    if pose.scale == 1 and pose.rot == 0:
        _paste(canvas, _faded(sprite, pose.alpha), round(x + pose.dx), round(y + pose.dy))
        return

    s, th = pose.scale, math.radians(pose.rot)
    cos, sin = math.cos(th), math.sin(th)
    vy = (pose.pivot - 0.5) * h * s   # pivot offset from the centre; rotation keeps it fixed
    cx = x + w / 2 + pose.dx - vy * sin
    cy = y + h / 2 + pose.dy + vy - vy * cos
    bw = s * (abs(w * cos) + abs(h * sin))
    bh = s * (abs(w * sin) + abs(h * cos))
    ox, oy = math.floor(cx - bw / 2) - 1, math.floor(cy - bh / 2) - 1
    size = (math.ceil(bw) + 3, math.ceil(bh) + 3)
    # Output pixel → sprite pixel: undo the rotation and scale about the centre.
    data = (cos / s, -sin / s, ((ox - cx) * cos - (oy - cy) * sin) / s + w / 2,
            sin / s, cos / s, ((ox - cx) * sin + (oy - cy) * cos) / s + h / 2)
    # Premultiplied, so transparent edges don't resample into dark fringes.
    out = sprite.convert("RGBa").transform(size, Image.AFFINE, data, Image.BICUBIC).convert("RGBA")
    _paste(canvas, _faded(out, pose.alpha), ox, oy)


def _faded(im: Image.Image, alpha: float) -> Image.Image:
    if alpha >= 1:
        return im
    r, g, b, a = im.split()
    return Image.merge("RGBA", (r, g, b, a.point(lambda v: int(v * alpha))))


def _paste(canvas: Image.Image, im: Image.Image, x: int, y: int) -> None:
    """alpha_composite clipped to the canvas (a sprite may hang off any edge)."""
    sx, sy = max(0, -x), max(0, -y)
    w = min(im.width - sx, canvas.width - max(0, x))
    h = min(im.height - sy, canvas.height - max(0, y))
    if w > 0 and h > 0:
        canvas.alpha_composite(im, (max(0, x), max(0, y)), (sx, sy, sx + w, sy + h))


def _reveal(sprite: Image.Image, kind: str, a: float) -> Image.Image:
    """`sprite` with only the opened share `a` of reveal `kind` showing."""
    w, h = sprite.size
    if kind == "slot":  # content rises into its own box from below
        out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        out.paste(sprite, (0, round((1 - a) * h)))
        return out
    if kind == "ink":  # a soft-edged wipe, left to right
        soft = 0.25
        ramp = Image.new("L", (w, 1))
        ramp.putdata([round(255 * clamp((a * (1 + soft) - x / w) / soft)) for x in range(w)])
        out = sprite.copy()
        out.putalpha(ImageChops.multiply(sprite.getchannel("A"), ramp.resize((w, h))))
        return out
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    if kind == "wipe" and a > 0:
        d.rectangle([0, 0, a * w, h], fill=255)
    elif kind == "iris" and a > 0:
        r = a * math.hypot(w, h) / 2
        d.ellipse([w / 2 - r, h / 2 - r, w / 2 + r, h / 2 + r], fill=255)
    elif kind == "shutter":
        n = 5
        for i in range(n):
            open_ = clamp(a * 1.8 - i * 0.2)
            if open_ > 0:
                d.rectangle([0, i * h / n, w, i * h / n + open_ * h / n], fill=255)
    out = sprite.copy()
    out.putalpha(ImageChops.multiply(sprite.getchannel("A"), mask))
    return out


def contact_sheet(frames: list[tuple[str, Image.Image]], cols: int = 6, cell_w: int = 270) -> Image.Image:
    """Labelled frames on a grey ground, row by row — a filmstrip to check a move by eye."""
    if not frames:
        raise ValueError("no frames")
    fw, fh = frames[0][1].size
    cell_h = round(cell_w * fh / fw)
    rows = math.ceil(len(frames) / cols)
    sheet = Image.new("RGB", (cols * cell_w, rows * (cell_h + 28)), (40, 40, 44))
    d = ImageDraw.Draw(sheet)
    for i, (label, im) in enumerate(frames):
        x, y = i % cols * cell_w, i // cols * (cell_h + 28)
        cell = Image.new("RGBA", (fw, fh), (92, 96, 104, 255))
        cell.alpha_composite(im.convert("RGBA"))
        sheet.paste(cell.convert("RGB").resize((cell_w - 4, cell_h), Image.LANCZOS), (x + 2, y + 24))
        d.text((x + 6, y + 6), label, fill=(230, 230, 230))
    return sheet


def with_band(m: Motion, full: bool) -> Motion:
    """A full-screen slide never tilts, drifts or swings: each would bare the frame's edge."""
    if not full:
        return m
    return replace(m, tilt=0.0, hold="still" if m.hold == "drift" else m.hold,
                   enter="rise" if m.enter == "swing" else m.enter)
