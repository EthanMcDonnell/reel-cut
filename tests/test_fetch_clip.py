"""scrape/fetch_clip.py: finding a page's videos, and cutting a silent clip from a download."""
import asyncio
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent / "scrape"))
_SPEC = importlib.util.spec_from_file_location(
    "rc_fetch_clip", Path(__file__).parent.parent / "scrape" / "fetch_clip.py"
)
fetch_clip = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(fetch_clip)


def test_specific_videos_are_kept_and_channel_links_dropped():
    found = {
        "files": ["https://cdn.example.com/demo.mp4"],
        "frames": ["https://www.youtube.com/embed/abc123", "https://ads.example.com/frame"],
        "links": [
            "https://www.youtube.com/@company",               # channel, not a video
            "https://youtu.be/xyz789",
            "https://x.com/company/status/1234567890",
            "https://x.com/company",                          # profile
            "https://vimeo.com/76979871",
            "https://www.youtube.com/embed/abc123",           # already found as an embed
        ],
    }

    assert fetch_clip.video_urls(found) == [
        {"kind": "file", "url": "https://cdn.example.com/demo.mp4"},
        {"kind": "embed", "url": "https://www.youtube.com/embed/abc123"},
        {"kind": "link", "url": "https://youtu.be/xyz789"},
        {"kind": "link", "url": "https://x.com/company/status/1234567890"},
        {"kind": "link", "url": "https://vimeo.com/76979871"},
    ]


def _test_video(path: Path, seconds: int = 6) -> Path:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc=size=1920x1080:rate=10:d={seconds}",
         "-f", "lavfi", "-i", f"sine=d={seconds}", "-shortest", "-pix_fmt", "yuv420p", str(path)],
        check=True,
    )
    return path


def test_list_finds_the_pages_own_video_and_embeds(tmp_path):
    pytest.importorskip("playwright")
    page = tmp_path / "post.html"
    page.write_text(
        "<article><p>Launch</p>"
        '<video src="demo.mp4" autoplay muted></video>'
        '<video><source data-src="lazy.webm"></video>'
        '<iframe src="https://www.youtube.com/embed/abc123"></iframe>'
        '<a href="https://www.youtube.com/@company">Our channel</a></article>'
    )

    result = asyncio.run(fetch_clip.list_videos(page.as_uri()))

    assert [v["url"] for v in result["videos"]] == [
        (tmp_path / "demo.mp4").as_uri(),
        (tmp_path / "lazy.webm").as_uri(),
        "https://www.youtube.com/embed/abc123",
    ]


def test_contact_sheet_labels_a_frame_every_second(tmp_path):
    src = _test_video(tmp_path / "v.mp4", seconds=6)

    every = fetch_clip.contact_sheet(src, tmp_path / "v.sheet.jpg")

    assert every == 1
    sheet = Image.open(tmp_path / "v.sheet.jpg")
    assert sheet.size == (fetch_clip.SHEET_COLS * fetch_clip.THUMB_W, 2 * 180)  # 6 frames, 2 rows


def test_cut_is_silent_h264_no_wider_than_1080(tmp_path):
    src = _test_video(tmp_path / "v.mp4")

    fetch_clip.cut(src, tmp_path / "clips" / "c.mp4", 1.0, 3.5)

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,width",
         "-of", "csv=p=0", str(tmp_path / "clips" / "c.mp4")],
        capture_output=True, text=True, check=True,
    ).stdout.split()
    assert probe == ["h264,video,1080"]
    assert fetch_clip._duration(tmp_path / "clips" / "c.mp4") == pytest.approx(2.5, abs=0.15)


def test_fetch_reuses_a_download_and_ignores_its_sheet(tmp_path):
    (tmp_path / "demo.sheet.jpg").write_bytes(b"")
    (tmp_path / "demo.webm").write_bytes(b"")

    assert fetch_clip.fetch("https://unused.example.com/v", tmp_path, "demo") == tmp_path / "demo.webm"


def test_fetch_passes_the_embedding_page_as_referer(tmp_path, monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        (tmp_path / "demo.mp4").write_bytes(b"")
        return subprocess.CompletedProcess(cmd, 0, stdout=f"{tmp_path / 'demo.mp4'}\n", stderr="")

    monkeypatch.setattr(fetch_clip.subprocess, "run", fake_run)
    fetch_clip.fetch("https://player.vimeo.com/video/1", tmp_path, "demo", "https://blog.example.com/post")

    i = calls[0].index("--referer")
    assert calls[0][i + 1] == "https://blog.example.com/post"
