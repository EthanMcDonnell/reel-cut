from reelcut.config import ReelCutConfig
from reelcut.renderer import _VT_BASE_BITRATE_K, _X264_BASE_CRF, _encode_variation


def _cfg(enabled: bool, crf_jitter: int = 1, bitrate_jitter: float = 0.08) -> ReelCutConfig:
    cfg = ReelCutConfig()
    cfg.output.encode_variation.enabled = enabled
    cfg.output.encode_variation.crf_jitter = crf_jitter
    cfg.output.encode_variation.bitrate_jitter = bitrate_jitter
    return cfg


def test_disabled_is_noop():
    assert _encode_variation("anything", _cfg(enabled=False), "libx264") == {}


def test_deterministic_in_stem():
    cfg = _cfg(enabled=True)
    assert _encode_variation("hook-one", cfg, "libx264") == _encode_variation(
        "hook-one", cfg, "libx264"
    )


def test_distinct_stems_differ():
    cfg = _cfg(enabled=True)
    a = _encode_variation("hook-one", cfg, "libx264")
    b = _encode_variation("hook-two", cfg, "libx264")
    assert a != b


def test_x264_uses_crf_within_jitter():
    cfg = _cfg(enabled=True, crf_jitter=1)
    for stem in ("a", "b", "c", "hook-1", "hook-2", "hook-3", "spotify-wrapped"):
        kw = _encode_variation(stem, cfg, "libx264")
        assert "b:v" not in kw
        assert abs(kw["crf"] - _X264_BASE_CRF) <= 1


def test_videotoolbox_uses_bitrate_within_jitter():
    cfg = _cfg(enabled=True, bitrate_jitter=0.08)
    for stem in ("a", "b", "hook-1", "hook-2", "hook-3"):
        kw = _encode_variation(stem, cfg, "h264_videotoolbox")
        assert "crf" not in kw
        kbps = int(kw["b:v"].rstrip("k"))
        assert abs(kbps - _VT_BASE_BITRATE_K) <= _VT_BASE_BITRATE_K * 0.08 + 1


def test_gop_stays_in_a_sane_range():
    # 4-8s of frames: long enough not to inflate file size, short enough to stay seekable.
    cfg = _cfg(enabled=True)
    fps = cfg.output.fps
    for stem in ("a", "b", "hook-1", "hook-2", "hook-3", "x"):
        g = _encode_variation(stem, cfg, "libx264")["g"]
        assert 4 * fps <= g <= 8 * fps


def test_metadata_tag_present_and_varies():
    cfg = _cfg(enabled=True)
    a = _encode_variation("hook-one", cfg, "libx264")["metadata"]
    b = _encode_variation("hook-two", cfg, "libx264")["metadata"]
    assert a.startswith("comment=rc-") and b.startswith("comment=rc-")
    assert a != b


def test_zero_jitter_pins_to_baseline():
    cfg = _cfg(enabled=True, crf_jitter=0)
    assert _encode_variation("hook-one", cfg, "libx264")["crf"] == _X264_BASE_CRF
