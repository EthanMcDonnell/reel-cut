"""End-to-end check of video overlays: the clip plays in its box only during its window,
starts from `clip_start`, sits under the caption layer, and dims the footage when full screen.

Renders 2s of blue footage with a clip overlay at 0.5–1.5s and inspects decoded frames.
"""
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from reelcut.caption import CaptionFrame
from reelcut.config import ReelCutConfig
from reelcut.image_finder import ImageCue
from reelcut.image_overlay import Placement
from reelcut.renderer import _final_encode, _prepare_caption_sequence

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

W = H = 320
FPS = 30
BLUE = (0, 0, 255)
RED = (255, 0, 0)
YELLOW = (255, 255, 0)
GREEN = (0, 255, 0)


def _cfg() -> ReelCutConfig:
    cfg = ReelCutConfig()
    cfg.output.resolution = [W, H]
    cfg.output.fps = FPS
    cfg.output.zoom.enabled = False
    cfg.output.encode_variation.enabled = False
    return cfg


# The 160px clips drawn 1:1 in the middle of the frame.
CENTRE = Placement(x=(W - 160) // 2, y=(H - 160) // 2, w=160, h=160, band="top")


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", *args], capture_output=True, check=True)


def _footage(tmp: Path) -> Path:
    out = tmp / "src.mkv"
    _ffmpeg("-f", "lavfi", "-i", f"color=c=blue:s={W}x{H}:r={FPS}:d=2",
            "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
            "-t", "2", "-pix_fmt", "yuv420p", "-c:a", "flac", str(out))
    return out


def _clip(tmp: Path) -> Path:
    """2s clip: red for the first second, yellow for the second."""
    out = tmp / "clip.mp4"
    _ffmpeg("-f", "lavfi", "-i", f"color=c=red:s=160x160:r={FPS}:d=1",
            "-f", "lavfi", "-i", f"color=c=yellow:s=160x160:r={FPS}:d=1",
            "-filter_complex", "[0][1]concat=n=2:v=1", "-pix_fmt", "yuv420p", str(out))
    return out


def _frame(video: Path, tmp: Path, n: int) -> Image.Image:
    shot = tmp / f"frame{n}.png"
    _ffmpeg("-i", str(video), "-vf", f"select=eq(n\\,{n})", "-vframes", "1", str(shot))
    return Image.open(shot).convert("RGB")


def _close(actual, expected, tol=60) -> bool:
    return all(abs(a - e) <= tol for a, e in zip(actual, expected))


def _render(tmp: Path, clip_start: float = 0.0, caption_seq=None, place=CENTRE) -> Path:
    cfg = _cfg()
    cue = ImageCue(keyword="clip", start=0.5, end=1.5, image_path=str(_clip(tmp)),
                   type="video", clip_start=clip_start)
    out = tmp / "out.mp4"
    _final_encode(_footage(tmp), out, cfg, caption_seq, None, False, [(cue, place)])
    return out


def test_clip_shows_only_inside_its_window(tmp_path):
    out = _render(tmp_path)
    centre = (W // 2, H // 2)
    assert _close(_frame(out, tmp_path, 6).getpixel(centre), BLUE), "before the window"
    assert _close(_frame(out, tmp_path, 24).getpixel(centre), RED), "inside the window"
    assert _close(_frame(out, tmp_path, 54).getpixel(centre), BLUE), "after the window"
    assert _close(_frame(out, tmp_path, 24).getpixel((10, 10)), BLUE), "clip stays centred"


def test_full_screen_clip_dims_the_footage_around_it(tmp_path):
    out = _render(tmp_path, place=Placement(**{**CENTRE.__dict__, "band": "full"}))
    corner = _frame(out, tmp_path, 24).getpixel((10, 10))
    assert corner[2] < 140, "footage dimmed during the window"
    assert _close(_frame(out, tmp_path, 54).getpixel((10, 10)), BLUE), "undimmed after it"


def test_clip_start_skips_into_the_file(tmp_path):
    out = _render(tmp_path, clip_start=1.0)
    assert _close(_frame(out, tmp_path, 24).getpixel((W // 2, H // 2)), YELLOW)


def test_captions_sit_on_top_of_the_clip(tmp_path):
    cfg = _cfg()
    frame_dir = tmp_path / "frames"
    frame_dir.mkdir()
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    overlay.paste(Image.new("RGBA", (40, 40), GREEN + (255,)), (W // 2 - 20, H // 2 - 20))
    path = frame_dir / "cap.png"
    overlay.save(path)
    frames = [CaptionFrame(frame_number=i, image_path=str(path)) for i in range(2 * FPS)]
    out = _render(tmp_path, caption_seq=_prepare_caption_sequence(frames, cfg, str(tmp_path)))
    assert _close(_frame(out, tmp_path, 24).getpixel((W // 2, H // 2)), GREEN)


def test_transparent_webm_shows_footage_through(tmp_path):
    """Animations ship as webm with alpha: only their opaque pixels should cover the footage."""
    png = tmp_path / "ring.png"
    img = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
    img.paste(Image.new("RGBA", (40, 40), RED + (255,)), (60, 60))
    img.save(png)
    clip = tmp_path / "anim.webm"
    _ffmpeg("-loop", "1", "-i", str(png), "-t", "1", "-r", str(FPS),
            "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", str(clip))

    cue = ImageCue(keyword="anim", start=0.5, end=1.5, image_path=str(clip), type="video")
    out = tmp_path / "out.mp4"
    _final_encode(_footage(tmp_path), out, _cfg(), None, None, False, [(cue, CENTRE)])
    px = _frame(out, tmp_path, 24)
    assert _close(px.getpixel((W // 2, H // 2)), RED), "opaque part of the animation"
    assert _close(px.getpixel((W // 2 - 60, H // 2 - 60)), BLUE), "transparent part shows footage"


def test_short_clip_holds_its_last_frame(tmp_path):
    """A 1s clip in a 1s+ window: once it runs out, its final frame stays up until the window ends."""
    cfg = _cfg()
    clip = tmp_path / "short.mp4"
    _ffmpeg("-f", "lavfi", "-i", f"color=c=red:s=160x160:r={FPS}:d=0.5",
            "-f", "lavfi", "-i", f"color=c=yellow:s=160x160:r={FPS}:d=0.5",
            "-filter_complex", "[0][1]concat=n=2:v=1", "-pix_fmt", "yuv420p", str(clip))
    cue = ImageCue(keyword="short", start=0.2, end=1.8, image_path=str(clip), type="video")
    out = tmp_path / "out.mp4"
    _final_encode(_footage(tmp_path), out, cfg, None, None, False, [(cue, CENTRE)])
    centre = (W // 2, H // 2)
    assert _close(_frame(out, tmp_path, 45).getpixel(centre), YELLOW), "held on the last frame"
    assert _close(_frame(out, tmp_path, 57).getpixel(centre), BLUE), "gone after the window"
