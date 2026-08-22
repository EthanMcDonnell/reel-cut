"""Tests for the Telegram script chunker — the 4096-char cap is a hard reject."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from send_script import LIMIT, chunk  # noqa: E402


def _rejoined(parts):
    """Content with whitespace collapsed, for comparing against the input."""
    return "".join(parts).replace("\n", "").replace(" ", "")


class TestChunk:
    def test_short_text_stays_one_message(self):
        assert chunk("hello world") == ["hello world"]

    def test_exactly_at_limit_is_not_split(self):
        assert len(chunk("x" * LIMIT)) == 1

    def test_one_over_limit_splits(self):
        assert len(chunk("x" * (LIMIT + 1))) == 2

    @pytest.mark.parametrize("text", [
        "\n\n".join(f"para {i} " + "y" * 500 for i in range(20)),   # paragraph breaks
        "z" * (LIMIT * 3 + 7),                                      # one unbroken line
        "\n".join("line " + "w" * 200 for _ in range(60)),          # lines, no blanks
    ])
    def test_every_chunk_fits_and_nothing_is_lost(self, text):
        parts = chunk(text)
        assert all(len(p) <= LIMIT for p in parts)
        assert _rejoined(parts) == text.replace("\n", "").replace(" ", "")

    def test_prefers_paragraph_boundaries(self):
        # Paragraphs that fit should not be cut mid-way.
        text = "\n\n".join("p" * 1000 for _ in range(6))
        parts = chunk(text)
        assert all(len(p) <= LIMIT for p in parts)
        assert not any(p.startswith("\n") for p in parts)

    def test_header_still_fits_telegram_cap(self):
        # send_script prefixes each chunk with "📄 <slug> (i/n)\n\n" — the
        # LIMIT must leave room for that under Telegram's real 4096 ceiling.
        header = "📄 some-fairly-long-video-slug-name (10/10)\n\n"
        assert LIMIT + len(header) <= 4096
