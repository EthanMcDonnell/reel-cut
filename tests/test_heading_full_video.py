"""`headings.full_video` controls how long a hook's title card stays up.

render-hooks writes a one-card temp headings.json per render. Its `end` used to always be
the hook's own duration, so the card vanished when the body started. With full_video on it
writes -1 ("until the end of the video") instead.
"""
import json
from pathlib import Path

import pytest
import yaml

from reelcut import cli
from reelcut.captions_doc import CaptionsDoc, CaptionWord, EdlEntry, save_captions_doc


@pytest.fixture
def assets(tmp_path, monkeypatch):
    """A minimal slug dir (captions + two hook cards + a 6s clip) with _phase2 stubbed out."""
    slug_dir = tmp_path / "a-slug"
    slug_dir.mkdir()
    cap = slug_dir / "clip.captions.json"
    save_captions_doc(
        CaptionsDoc(
            source_clips=["clip.mov"],
            edl=[EdlEntry(source_clip="clip.mov", start=0.0, end=6.0, keep=True, reason="speech")],
            words=[CaptionWord(word="hi", start=0.0, end=0.5, source_clip="clip.mov")],
        ),
        cap,
    )
    # hook 1 = [0,2), hook 2 = [2,4), body = [4,6)
    (slug_dir / "headings.json").write_text(json.dumps([
        {"title": "one", "start": 0.0, "end": 2.0},
        {"title": "two", "start": 2.0, "end": 4.0},
    ]))
    (slug_dir / "images.json").write_text("[]")

    captured: list[dict] = []

    def fake_phase2(cfg, doc, outputs, verbose, headings_path=None, **kwargs):
        captured.extend(json.loads(Path(headings_path).read_text()))
        return []

    monkeypatch.setattr(cli, "_phase2", fake_phase2)
    return slug_dir, cap, captured


def _config(tmp_path: Path, full_video: bool) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({
        "output": {"location": str(tmp_path / "output"), "flip": {"mode": "off"}},
        "headings": {"full_video": full_video},
    }))
    return path


def test_full_video_keeps_the_card_up_until_the_end(assets, tmp_path):
    slug_dir, cap, captured = assets
    cli.render_hooks(str(_config(tmp_path, True)), str(cap), slug="a-slug", verbose=False)
    assert [c["end"] for c in captured] == [-1, -1]


def test_card_ends_with_the_hook_by_default(assets, tmp_path):
    slug_dir, cap, captured = assets
    cli.render_hooks(str(_config(tmp_path, False)), str(cap), slug="a-slug", verbose=False)
    assert [c["end"] for c in captured] == [2.0, 2.0]
