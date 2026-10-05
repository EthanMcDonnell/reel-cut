"""Highlight sweep: screenshot capture records one box per highlighted line, and the
renderer reveals the highlight across those boxes as the screenshot plays."""
import importlib.util
import json
import sys
from pathlib import Path

from PIL import Image

from reelcut.image_overlay import _load_sweep, _sweep_frame

SCRAPE = Path(__file__).resolve().parent.parent / "scrape"
sys.path.insert(0, str(SCRAPE))
_SPEC = importlib.util.spec_from_file_location("ss_screenshot", SCRAPE / "screenshot.py")
screenshot = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(screenshot)

CLIP = {screenshot._KX: 0, screenshot._KY: 100, screenshot._KW: 400, screenshot._KH: 200}
YELLOW = (255, 224, 102, 255)
GREY = (200, 200, 200, 255)


class TestLineRects:
    def test_spans_on_one_line_merge(self):
        rects = [[10, 120, 50, 20], [70, 121, 100, 20]]
        assert screenshot._line_rects(rects, CLIP) == [[0.025, 0.1, 0.4, 0.1]]

    def test_lines_ordered_top_to_bottom(self):
        rects = [[10, 160, 80, 20], [10, 120, 200, 20]]
        assert [r[1] for r in screenshot._line_rects(rects, CLIP)] == [0.1, 0.3]


class TestSweep:
    def _images(self):
        hi = Image.new("RGBA", (100, 40), YELLOW)
        plain = Image.new("RGBA", (100, 40), GREY)
        rects = [(0, 0, 100, 20), (0, 20, 50, 20)]
        return hi, plain, rects

    def test_start_is_plain_and_end_is_highlighted(self):
        hi, plain, rects = self._images()
        assert _sweep_frame(hi, plain, rects, 0.0).getpixel((5, 5)) == GREY
        done = _sweep_frame(hi, plain, rects, 1.0)
        assert done.getpixel((95, 5)) == YELLOW and done.getpixel((45, 25)) == YELLOW

    def test_first_line_fills_before_second(self):
        hi, plain, rects = self._images()
        mid = _sweep_frame(hi, plain, rects, 0.3)
        assert mid.getpixel((5, 5)) == YELLOW
        assert mid.getpixel((5, 25)) == GREY

    def test_load_needs_both_sidecars(self, tmp_path):
        shot = tmp_path / "snippet-01.png"
        Image.new("RGBA", (40, 20), YELLOW).save(shot)
        assert _load_sweep(str(shot), 40, 20) is None
        Image.new("RGBA", (40, 20), GREY).save(tmp_path / "snippet-01.plain.png")
        (tmp_path / "snippet-01.rects.json").write_text(json.dumps([[0.5, 0.0, 0.5, 1.0]]))
        plain, rects = _load_sweep(str(shot), 80, 40)
        assert plain.size == (80, 40) and rects == [(40.0, 0.0, 40.0, 40.0)]
