"""End-to-end check of the one property that makes flipping usable: the footage mirrors,
the burned-in overlay does not.

Renders a 1s clip whose left half is red and right half is blue, with an opaque green
overlay square in the left quarter, and inspects a decoded frame.
"""
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from reelcut.caption import CaptionFrame
from reelcut.config import ReelCutConfig
from reelcut.renderer import _final_encode, _prepare_caption_sequence

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

W = H = 320
RED = (255, 0, 0)
BLUE = (0, 0, 255)
GREEN = (0, 255, 0)


def _cfg() -> ReelCutConfig:
    cfg = ReelCutConfig()
    cfg.output.resolution = [W, H]
    cfg.output.zoom.enabled = False            # a crop would muddy the half-frame sampling
    cfg.output.encode_variation.enabled = False
    return cfg


def _source_clip(tmp: Path) -> Path:
    """1s video, left half red / right half blue, with a silent audio track."""
    src_png = tmp / "halves.png"
    img = Image.new("RGB", (W, H), RED)
    img.paste(Image.new("RGB", (W // 2, H), BLUE), (W // 2, 0))
    img.save(src_png)

    out = tmp / "src.mkv"
    subprocess.run(
        ["ffmpeg", "-y", "-loop", "1", "-i", str(src_png),
         "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
         "-t", "1", "-r", "30", "-pix_fmt", "yuv420p", "-c:a", "flac", str(out)],
        capture_output=True, check=True,
    )
    return out


def _caption_seq(tmp: Path, cfg: ReelCutConfig) -> tuple[Path, int]:
    """Overlay frames carrying an opaque green square in the LEFT quarter."""
    frame_dir = tmp / "frames"
    frame_dir.mkdir()
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    overlay.paste(Image.new("RGBA", (60, 60), GREEN + (255,)), (20, 20))
    path = frame_dir / "overlay.png"
    overlay.save(path)
    frames = [CaptionFrame(frame_number=i, image_path=str(path)) for i in range(30)]
    return _prepare_caption_sequence(frames, cfg, str(tmp))


def _frame_pixels(video: Path, tmp: Path) -> Image.Image:
    shot = tmp / "frame.png"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video), "-vf", "select=eq(n\\,5)", "-vframes", "1", str(shot)],
        capture_output=True, check=True,
    )
    return Image.open(shot).convert("RGB")


def _close(actual, expected, tol=60) -> bool:
    return all(abs(a - e) <= tol for a, e in zip(actual, expected))


def _render(tmp_path: Path, flip: bool) -> Image.Image:
    cfg = _cfg()
    src = _source_clip(tmp_path)
    out = tmp_path / f"out-{flip}.mp4"
    _final_encode(src, out, cfg, _caption_seq(tmp_path, cfg), None, flip)
    assert out.exists()
    return _frame_pixels(out, tmp_path)


def test_unflipped_baseline(tmp_path):
    px = _render(tmp_path, flip=False)
    assert _close(px.getpixel((80, 200)), RED), "left half should be the red source half"
    assert _close(px.getpixel((240, 200)), BLUE), "right half should be the blue source half"
    assert _close(px.getpixel((50, 50)), GREEN), "overlay square sits in the left quarter"


def test_flip_mirrors_footage_but_not_the_overlay(tmp_path):
    px = _render(tmp_path, flip=True)
    # Footage mirrored: the halves have swapped sides.
    assert _close(px.getpixel((80, 200)), BLUE), "flip should bring the blue half to the left"
    assert _close(px.getpixel((240, 200)), RED), "flip should bring the red half to the right"
    # Overlay untouched: still drawn left-side-up, not mirrored to the right.
    assert _close(px.getpixel((50, 50)), GREEN), "burned-in overlay must NOT be mirrored"
    assert not _close(px.getpixel((W - 50, 50)), GREEN), "overlay must not appear mirrored on the right"
