"""Per-hook output grouping — which videos.json entry describes each rendered variant.

A mirrored duplicate the file doesn't describe is a text-identical clone of its hook: same
burned-in card, same caption, suffixed filename. An entry with `of` gives it its own card,
caption and name, at the cost of a second render pass — so these tests pin both the naming
AND the shared pass when no mirror entry is authored.
"""
from pathlib import Path

from reelcut.cli import _flip_plan, _hook_variant_groups
from reelcut.config import FlipConfig
from reelcut.video_spec import VideoSpec

OUT = Path("/out")
PLAN = _flip_plan(1, FlipConfig(mode="all", apply="duplicate", suffix="-flipped"))[0]
BASE = VideoSpec(id="tokens", title="What Are\nAI Tokens?", start=0.0, end=3.1,
                 caption="what are ai tokens? 🤔", slug="what-are-ai-tokens")
MIRROR = VideoSpec(id="tokens-flipped", of="tokens", title="You Pay\nBy The Syllable",
                   caption="you pay by the syllable 💸", slug="pay-by-the-syllable")


def _paths(groups):
    return [p for _, variants in groups for p, _ in variants]


def test_undescribed_duplicate_shares_one_render_pass():
    groups = _hook_variant_groups(PLAN, BASE, None, OUT)
    assert groups == [(BASE, [(OUT / "what-are-ai-tokens.mp4", False),
                              (OUT / "what-are-ai-tokens-flipped.mp4", True)])]


def test_mirror_entry_splits_the_duplicate_into_its_own_render():
    groups = _hook_variant_groups(PLAN, BASE, MIRROR, OUT)
    assert groups == [
        (BASE, [(OUT / "what-are-ai-tokens.mp4", False)]),
        (MIRROR, [(OUT / "pay-by-the-syllable.mp4", True)]),
    ]


def test_mirror_is_named_from_its_own_entry_not_the_flip_suffix():
    # post_video captions by exact stem, so the duplicate's file must carry its own name.
    assert _paths(_hook_variant_groups(PLAN, BASE, MIRROR, OUT))[1] == OUT / "pay-by-the-syllable.mp4"


def test_mirror_without_a_slug_is_named_from_its_caption():
    mirror = VideoSpec(id="tokens-flipped", of="tokens", caption="you pay by the syllable 💸")
    assert _paths(_hook_variant_groups(PLAN, BASE, mirror, OUT))[1] == OUT / "you-pay-by-the-syllable.mp4"


def test_single_output_hook_never_uses_the_mirror_entry():
    # in_place / flip off produce one video per hook — that video IS the hook, so it keeps
    # the hook's card and name even when a mirror entry exists.
    plan = _flip_plan(1, FlipConfig(mode="all", apply="in_place"))[0]
    assert _hook_variant_groups(plan, BASE, MIRROR, OUT) == [
        (BASE, [(OUT / "what-are-ai-tokens.mp4", True)]),
    ]


def test_entry_with_no_slug_or_caption_falls_back_to_its_id():
    base = VideoSpec(id="hook1", title="Untitled", start=0.0, end=3.1)
    assert _paths(_hook_variant_groups(PLAN, base, None, OUT)) == [
        OUT / "hook1.mp4",
        OUT / "hook1-flipped.mp4",
    ]
