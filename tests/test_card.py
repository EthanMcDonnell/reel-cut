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
    cfg = ImagesConfig(card_overlay_size_pct=80, start_delay_s=0)

    frames = render_image_frames([cue], cfg, tmp_path / "frames", fps=10, resolution=(500, 900))

    bbox = Image.open(frames[0].image_path).getchannel("A").getbbox()
    assert bbox[2] - bbox[0] == 400


def _bright_rows(png) -> int:
    """Rows of the frame holding opaque white text pixels."""
    im = Image.open(png).convert("RGBA")
    px = im.load()
    return sum(
        any(px[x, y][3] > 200 and min(px[x, y][:3]) > 200 for x in range(0, im.width, 4))
        for y in range(im.height)
    )


def _frame_at(webm, t, out):
    import subprocess
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-c:v", "libvpx-vp9", "-ss", str(t),
                    "-i", str(webm), "-frames:v", "1", str(out)], check=True)
    return out


def test_beat_element_enters_at_its_beat(tmp_path):
    from reelcut.card import card_webm

    html = tmp_path / "c.html"
    html.write_text('<p>Always</p><p data-beat="1">Later</p>')

    webm, top_beat = card_webm(html, [0.8], fps=10)

    assert top_beat == 1
    before = _bright_rows(_frame_at(webm, 0.5, tmp_path / "before.png"))
    after = _bright_rows(_frame_at(webm, 1.1, tmp_path / "after.png"))
    assert after > before * 1.5  # the second line has appeared


def test_card_with_beats_resolves_to_a_card_sized_video(tmp_path):
    html = tmp_path / "c.html"
    html.write_text('<p data-beat="1">A</p>')

    cue = _resolve_image_spec(
        ImageSpec(type="card", start=2.0, end=4.0, path=str(html), beats=[2.5]), 1.0, 10)

    assert (cue.type, cue.kind) == ("video", "card")
    assert cue.image_path.endswith(".webm")


def test_still_card_shows_its_own_animations_finished(tmp_path):
    html = tmp_path / "c.html"
    html.write_text(
        "<style>@keyframes hide { from { opacity: 0 } to { opacity: 0 } }"
        " p.late { animation: hide 5s 1s backwards; }</style>"
        '<p>One</p><p class="late">Two</p><p class="late">Three</p>'
    )
    plain = tmp_path / "plain.html"
    plain.write_text("<p>One</p><p>Two</p><p>Three</p>")

    assert _bright_rows(card_png(html)) == _bright_rows(card_png(plain))


def _gold_rows(png) -> set[int]:
    """Rows of the frame holding accent-gold pixels."""
    im = Image.open(png).convert("RGBA")
    px = im.load()
    return {
        y for y in range(im.height)
        if any(px[x, y][3] > 200 and px[x, y][0] > 200 and px[x, y][1] > 150 and px[x, y][2] < 120
               for x in range(0, im.width, 2))
    }


def _last_frame(webm, out):
    import subprocess
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-c:v", "libvpx-vp9", "-sseof", "-0.3",
                    "-i", str(webm), "-update", "1", str(out)], check=True)
    return out


def test_hot_highlight_moves_to_the_next_element(tmp_path):
    from reelcut.card import card_webm

    html = tmp_path / "c.html"
    html.write_text('<p data-hot="1">First</p><p data-hot="2">Second</p>')

    webm, top_beat = card_webm(html, [0.2, 1.0], fps=10)

    assert top_beat == 2
    mid = Image.open(_frame_at(webm, 0.7, tmp_path / "mid.png")).height // 2
    first = _gold_rows(_frame_at(webm, 0.7, tmp_path / "a.png"))
    second = _gold_rows(_last_frame(webm, tmp_path / "b.png"))
    assert first and max(first) < mid           # only the first line is lit
    assert second and min(second) >= mid        # the highlight has moved to the second


def _bright_cols(png) -> int:
    im = Image.open(png).convert("RGBA")
    px = im.load()
    return sum(
        any(px[x, y][3] > 200 and min(px[x, y][:3]) > 200 for y in range(0, im.height, 2))
        for x in range(im.width)
    )


def test_count_counts_up_to_its_number(tmp_path):
    from reelcut.card import card_webm

    html = tmp_path / "c.html"
    html.write_text('<p data-beat="1"><span class="count">1888</span></p>')
    ref = tmp_path / "ref.html"
    ref.write_text('<p><span class="count">1888</span></p>')  # the still render

    webm, _ = card_webm(html, [0.0], fps=10)

    early = _bright_cols(_frame_at(webm, 0.05, tmp_path / "early.png"))
    final = _bright_cols(_last_frame(webm, tmp_path / "final.png"))
    assert early < final                                   # starts low, with fewer digits lit
    assert abs(final - _bright_cols(card_png(ref))) <= 4   # ends showing the number itself


def test_still_card_shows_count_as_written(tmp_path):
    html = tmp_path / "c.html"
    html.write_text('<p><span class="count">42</span></p>')
    ref = tmp_path / "ref.html"
    ref.write_text("<p>42</p>")

    assert abs(_bright_cols(card_png(html)) - _bright_cols(card_png(ref))) <= 4  # no counter "0" added
