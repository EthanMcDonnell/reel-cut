"""Per-hook output grouping — which title card and filename each rendered variant gets.

A flipped duplicate is otherwise a text-identical clone of its hook: same burned-in card,
same caption. `alt_title`/`alt_slug` break that, at the cost of a second render pass — so
these tests pin both the alt naming AND the shared pass when no alt text is authored.
"""
from pathlib import Path

from reelcut.cli import _flip_plan, _hook_variant_groups
from reelcut.config import FlipConfig
from reelcut.heading import HeadingSpec
from reelcut.title import TitleSpec

OUT = Path("/out")
PLAN = _flip_plan(1, FlipConfig(mode="all", apply="duplicate", suffix="-flipped"))[0]
CARD = HeadingSpec(title="What Are\nAI Tokens?", start=0.0, end=3.1, subtitle="Day 1")


def test_duplicate_without_alt_text_shares_one_render_pass():
    groups = _hook_variant_groups(
        PLAN, "ai-tokens", CARD, TitleSpec(title="what are ai tokens?", slug="ai-tokens"), OUT
    )
    assert groups == [(CARD.title, [(OUT / "ai-tokens.mp4", False),
                                    (OUT / "ai-tokens-flipped.mp4", True)])]


def test_alt_title_splits_the_duplicate_into_its_own_card():
    card = HeadingSpec(title="What Are\nAI Tokens?", start=0.0, end=3.1,
                       alt_title="You Pay\nBy The Syllable")
    groups = _hook_variant_groups(
        PLAN, "ai-tokens", card, TitleSpec(title="what are ai tokens?", slug="ai-tokens"), OUT
    )
    assert groups == [
        (card.title, [(OUT / "ai-tokens.mp4", False)]),
        (card.alt_title, [(OUT / "ai-tokens-flipped.mp4", True)]),
    ]


def test_alt_slug_names_the_duplicate_instead_of_the_flip_suffix():
    # post_video captions by exact stem, so the duplicate's file must carry the alt slug.
    title = TitleSpec(title="what are ai tokens?", slug="ai-tokens",
                      alt_title="you pay by the syllable 💸", alt_slug="pay-by-the-syllable")
    groups = _hook_variant_groups(PLAN, "ai-tokens", CARD, title, OUT)
    assert [p for _, variants in groups for p, _ in variants] == [
        OUT / "ai-tokens.mp4",
        OUT / "pay-by-the-syllable.mp4",
    ]


def test_alt_title_alone_still_renames_the_duplicate():
    # No alt_slug: the stem is derived from alt_title, matching post_video's lookup key.
    title = TitleSpec(title="what are ai tokens?", slug="ai-tokens",
                      alt_title="you pay by the syllable 💸")
    groups = _hook_variant_groups(PLAN, "ai-tokens", CARD, title, OUT)
    assert [p for _, variants in groups for p, _ in variants] == [
        OUT / "ai-tokens.mp4",
        OUT / "you-pay-by-the-syllable.mp4",
    ]


def test_single_output_hook_never_uses_alt_text():
    # in_place / flip off produce one video per hook — that video IS the hook, so it keeps
    # the hook's card and title slug even when alt text is authored.
    plan = _flip_plan(1, FlipConfig(mode="all", apply="in_place"))[0]
    card = HeadingSpec(title="What Are\nAI Tokens?", start=0.0, end=3.1, alt_title="Alt Card")
    title = TitleSpec(title="t", slug="ai-tokens", alt_title="alt", alt_slug="alt-slug")
    assert _hook_variant_groups(plan, "ai-tokens", card, title, OUT) == [
        (card.title, [(OUT / "ai-tokens.mp4", True)]),
    ]


def test_missing_title_entry_falls_back_to_the_positional_stem():
    groups = _hook_variant_groups(PLAN, "hook1", CARD, None, OUT)
    assert [p for _, variants in groups for p, _ in variants] == [
        OUT / "hook1.mp4",
        OUT / "hook1-flipped.mp4",
    ]
