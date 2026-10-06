"""Designed cards: an HTML fragment renders to a transparent PNG beside it, re-renders once
edited, and is placed as a centre overlay at card_overlay_size_pct of the video width."""
import os

import pytest
from PIL import Image

pytest.importorskip("playwright")

from reelcut.card import card_png
from reelcut.cli import _resolve_image_spec
from reelcut.config import ImagesConfig
from reelcut.image_overlay import render_image_frames
from reelcut.image_spec import ImageSpec


def test_card_renders_to_transparent_png_beside_fragment(tmp_path):
    html = tmp_path / "points.html"
    html.write_text('<ol class="points"><li>One</li><li>Two</li></ol>')

    png = card_png(html)

    assert png == tmp_path / "points.png"
    im = Image.open(png)
    assert im.mode == "RGBA" and im.width == 1000
    assert im.getpixel((0, 0))[3] == 0                        # rounded corner shows the video
    assert im.getpixel((im.width // 2, im.height // 2))[3] > 200  # card body is opaque


def test_edited_fragment_is_rendered_again(tmp_path):
    html = tmp_path / "c.html"
    html.write_text("<p>One line</p>")
    first = Image.open(card_png(html)).height
    os.utime(html.with_suffix(".png"), (0, 0))  # PNG now older than the fragment

    html.write_text("<p>One line</p><p>Two</p><p>Three</p>")
    assert Image.open(card_png(html)).height > first


def test_card_spec_resolves_to_its_rendered_png(tmp_path):
    html = tmp_path / "flow.html"
    html.write_text('<div class="flow"><div>A</div><div>B</div></div>')

    cue = _resolve_image_spec(ImageSpec(type="card", start=1.0, end=3.0, path=str(html)), 1.0)

    assert cue.type == "card"
    assert cue.image_path == str(tmp_path / "flow.png")
    assert (cue.start, cue.end) == (1.0, 3.0)


def test_card_is_drawn_at_card_overlay_width(tmp_path):
    html = tmp_path / "c.html"
    html.write_text("<p>Text</p>")
    cue = _resolve_image_spec(ImageSpec(type="card", start=0.0, end=0.2, path=str(html)), 1.0)
    cfg = ImagesConfig(position="center", card_overlay_size_pct=80, start_delay_s=0)

    frames = render_image_frames([cue], cfg, tmp_path / "frames", fps=10, resolution=(500, 900))

    bbox = Image.open(frames[0].image_path).getchannel("A").getbbox()
    assert bbox[2] - bbox[0] == 400
