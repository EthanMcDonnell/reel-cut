"""Tests for transcript-word → logo-slug variant generation, incl. brand aliases."""
from reelcut.image_resolver import normalize_slug, LOGO_ALIASES
from reelcut.image_finder import _slug_variants


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
