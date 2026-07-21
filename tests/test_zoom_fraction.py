from reelcut.config import ReelCutConfig
from reelcut.renderer import _zoom_fraction


def _cfg(enabled: bool, mn: float = 0.96, mx: float = 1.0) -> ReelCutConfig:
    cfg = ReelCutConfig()
    cfg.output.zoom.enabled = enabled
    cfg.output.zoom.min = mn
    cfg.output.zoom.max = mx
    return cfg


def test_disabled_is_noop():
    assert _zoom_fraction("anything", _cfg(enabled=False)) == 1.0


def test_deterministic_in_stem():
    cfg = _cfg(enabled=True)
    assert _zoom_fraction("hook-one", cfg) == _zoom_fraction("hook-one", cfg)


def test_distinct_stems_differ():
    cfg = _cfg(enabled=True)
    assert _zoom_fraction("hook-one", cfg) != _zoom_fraction("hook-two", cfg)


def test_within_range():
    cfg = _cfg(enabled=True, mn=0.96, mx=1.0)
    for stem in ("a", "b", "c", "hook-1", "hook-2", "hook-3", "spotify-wrapped"):
        frac = _zoom_fraction(stem, cfg)
        assert 0.96 <= frac < 1.0


def test_degenerate_range_is_noop():
    # max <= min must not zoom (avoids a nonsensical crop).
    assert _zoom_fraction("x", _cfg(enabled=True, mn=1.0, mx=1.0)) == 1.0
