"""Unit tests for the pure helpers in scrape/screenshot.py.

The Playwright-driven capture flow (parallel snippet capture, find/highlight targeting)
needs a real browser and is exercised end-to-end via /produce-script; here we cover the
deterministic logic: element-sized crop windows and locked manifest writes.
"""
import importlib.util
import json
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "rc_screenshot", Path(__file__).parent.parent / "scrape" / "screenshot.py"
)
screenshot = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(screenshot)


class TestCropWindow:
    def test_short_element_gets_min_height(self):
        _, h = screenshot._crop_window(el_top=400, el_height=20, vh=844)
        assert h == screenshot.SNIPPET_MIN_HEIGHT

    def test_tall_element_clamped_to_max(self):
        _, h = screenshot._crop_window(el_top=100, el_height=2000, vh=844)
        assert h == min(screenshot.SNIPPET_MAX_HEIGHT, 844)

    def test_medium_element_sized_with_padding(self):
        _, h = screenshot._crop_window(el_top=300, el_height=300, vh=844)
        assert h == 300 + 2 * screenshot.SNIPPET_PADDING

    def test_crop_brackets_the_element(self):
        y, h = screenshot._crop_window(el_top=300, el_height=100, vh=844)
        center = 300 + 100 / 2
        assert y <= center <= y + h

    def test_never_exceeds_viewport_bottom(self):
        y, h = screenshot._crop_window(el_top=820, el_height=40, vh=844)
        assert y >= 0
        assert y + h <= 844


class TestWriteManifest:
    def test_creates_manifest(self, tmp_path):
        entry = {"url": "http://a", "screenshots": []}
        screenshot._write_manifest(tmp_path, "http://a", entry)
        assert json.loads((tmp_path / "manifest.json").read_text()) == [entry]

    def test_appends_distinct_urls(self, tmp_path):
        screenshot._write_manifest(tmp_path, "http://a", {"url": "http://a", "screenshots": []})
        screenshot._write_manifest(tmp_path, "http://b", {"url": "http://b", "screenshots": []})
        data = json.loads((tmp_path / "manifest.json").read_text())
        assert [d["url"] for d in data] == ["http://a", "http://b"]

    def test_replaces_same_url(self, tmp_path):
        screenshot._write_manifest(tmp_path, "http://a", {"url": "http://a", "screenshots": [1]})
        screenshot._write_manifest(tmp_path, "http://a", {"url": "http://a", "screenshots": [2]})
        data = json.loads((tmp_path / "manifest.json").read_text())
        assert len(data) == 1
        assert data[0]["screenshots"] == [2]

    def test_migrates_legacy_single_object(self, tmp_path):
        (tmp_path / "manifest.json").write_text(json.dumps({"url": "http://old", "screenshots": []}))
        screenshot._write_manifest(tmp_path, "http://new", {"url": "http://new", "screenshots": []})
        data = json.loads((tmp_path / "manifest.json").read_text())
        assert isinstance(data, list)
        assert {d["url"] for d in data} == {"http://old", "http://new"}
