from reelcut.cli import _flip_plan
from reelcut.config import FlipConfig, ReelCutConfig


def _cfg(mode: str, apply: str = "duplicate", suffix: str = "-flipped") -> FlipConfig:
    return FlipConfig(mode=mode, apply=apply, suffix=suffix)


def test_default_is_off():
    # Flipping must stay opt-in: an untouched config renders exactly one video per hook.
    assert ReelCutConfig().output.flip.mode == "off"
    assert _flip_plan(3, ReelCutConfig().output.flip) == [[("", False)]] * 3


def test_off_ignores_apply():
    for apply in ("in_place", "duplicate"):
        assert _flip_plan(3, _cfg("off", apply)) == [[("", False)]] * 3


def test_alternate_in_place_flips_every_second_hook():
    # 3 hooks -> 3 videos, the middle one flipped.
    assert _flip_plan(3, _cfg("alternate", "in_place")) == [
        [("", False)],
        [("", True)],
        [("", False)],
    ]


def test_alternate_duplicate_adds_one_extra_video():
    # 3 hooks -> 4 videos: hook 2 keeps its normal render and gains a flipped copy.
    plan = _flip_plan(3, _cfg("alternate", "duplicate"))
    assert plan == [
        [("", False)],
        [("", False), ("-flipped", True)],
        [("", False)],
    ]
    assert sum(len(p) for p in plan) == 4


def test_all_in_place_flips_every_video_without_adding_any():
    plan = _flip_plan(3, _cfg("all", "in_place"))
    assert plan == [[("", True)]] * 3
    assert sum(len(p) for p in plan) == 3


def test_all_duplicate_doubles_the_output_count():
    # The user-facing headline case: 3 hooks -> 6 videos.
    plan = _flip_plan(3, _cfg("all", "duplicate"))
    assert plan == [[("", False), ("-flipped", True)]] * 3
    assert sum(len(p) for p in plan) == 6


def test_duplicate_suffix_is_configurable():
    assert _flip_plan(1, _cfg("all", "duplicate", suffix="-b")) == [
        [("", False), ("-b", True)],
    ]


def test_in_place_never_suffixes():
    # An in-place flip IS the hook's video, so it must keep the title-derived filename —
    # post_video.py captions from that stem.
    for mode in ("alternate", "all"):
        for hook in _flip_plan(4, _cfg(mode, "in_place")):
            assert all(suffix == "" for suffix, _ in hook)


def test_zero_hooks_is_empty():
    assert _flip_plan(0, _cfg("all", "duplicate")) == []


def test_bare_yaml_off_parses_as_off():
    # `mode: off` in YAML is the boolean False, not the string "off".
    assert FlipConfig(mode=False).mode == "off"
