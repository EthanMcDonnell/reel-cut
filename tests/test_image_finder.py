"""Tests for transcript-word → logo-slug variant generation, incl. brand aliases."""
from reelcut.cli import _heading_reset_boundaries
from reelcut.config import ImagesConfig
from reelcut.heading import HeadingSpec
from reelcut.image_finder import _slug_variants, detect_image_cues
from reelcut.image_resolver import normalize_slug, LOGO_ALIASES
from reelcut.transcriber import WordTimestamp


def _w(word: str, start: float) -> WordTimestamp:
    return WordTimestamp(word=word, start=start, end=start + 0.4)


class TestSlugVariants:
    def test_bare_product_name_appends_namespaced_alias(self):
        variants = _slug_variants("OneDrive", normalize_slug)
        assert "onedrive" in variants
        # alias is appended after the bare form so an exact slug still wins first
        assert variants.index("onedrive") < variants.index("microsoft-onedrive")

    def test_possessive_still_resolves_alias(self):
        variants = _slug_variants("OneDrive's", normalize_slug)
        assert "microsoft-onedrive" in variants

    def test_non_aliased_word_unchanged(self):
        assert _slug_variants("Anthropic", normalize_slug) == ["anthropic"]

    def test_every_alias_target_is_namespaced(self):
        # guards against typo'd alias values (bare == target would be pointless)
        for bare, target in LOGO_ALIASES.items():
            assert target.endswith(bare) or bare in target.split("-")
            assert "-" in target


class TestLogoReset:
    def test_fires_once_without_boundaries(self):
        words = [_w("Salesforce", 1.0), _w("Salesforce", 5.0), _w("Salesforce", 9.0)]
        cues = detect_image_cues(words, ImagesConfig())
        assert [round(c.start, 1) for c in cues] == [1.0]

    def test_refires_once_per_section(self):
        words = [_w("Salesforce", 1.0), _w("Salesforce", 5.0), _w("Salesforce", 9.0)]
        # resets at 4 and 8 → three sections, each with its own first occurrence
        cues = detect_image_cues(words, ImagesConfig(), reset_boundaries=[4.0, 8.0])
        assert [round(c.start, 1) for c in cues] == [1.0, 5.0, 9.0]

    def test_still_deduped_within_a_section(self):
        # two mentions in the same section → still one logo
        words = [_w("Salesforce", 1.0), _w("Salesforce", 2.0), _w("Salesforce", 6.0)]
        cues = detect_image_cues(words, ImagesConfig(), reset_boundaries=[4.0])
        assert [round(c.start, 1) for c in cues] == [1.0, 6.0]


class TestHeadingResetBoundaries:
    def test_card_edges_become_boundaries(self):
        heads = [
            HeadingSpec(title="Hook 1", start=0.0, end=3.0),
            HeadingSpec(title="Hook 2", start=3.0, end=6.0),
            HeadingSpec(title="Hook 3", start=6.0, end=9.0),
        ]
        # starts ∪ ends, dropping 0 (a reset before the first word is a no-op)
        assert _heading_reset_boundaries(heads, total_output_s=30.0) == [3.0, 6.0, 9.0]

    def test_empty_title_stub_is_ignored(self):
        heads = [HeadingSpec(title="", start=0.0, end=3.0)]
        assert _heading_reset_boundaries(heads, total_output_s=30.0) == []

    def test_open_ended_card_resolves_to_total(self):
        heads = [HeadingSpec(title="Only", start=2.0, end=-1)]
        assert _heading_reset_boundaries(heads, total_output_s=12.0) == [2.0, 12.0]
