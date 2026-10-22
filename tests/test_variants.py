"""The variant plan decides what every rendered video of a slug contains, and it is recorded
on the slug's videos.json — so a wrong plan, or one that shifts between renders, changes
files that may already be posted.
"""
import json

from reelcut.cli import _plan_videos, _titled_hooks
from reelcut.config import ReelCutConfig, VariantsConfig
from reelcut.variants import plan_variants, trim_cycle
from reelcut.video_spec import load_videos


def test_default_config_renders_one_plain_video_per_hook():
    v = ReelCutConfig().output.variants
    assert plan_variants([v.copies] * 3, v.flip, v.trim, [1, 2]) == [[(False, [])]] * 3


def test_core_video_is_never_flipped_or_trimmed():
    for flip in ("alternate", "copies", "all"):
        assert plan_variants([2, 2], flip, "rotate", [1, 2])[0][0] == (False, [])


def test_alternate_flips_every_second_hook_like_the_old_in_place_setting():
    # Slugs rendered under output.flip {mode: alternate, apply: in_place} re-render the same.
    plan = plan_variants([1, 1, 1, 1], "alternate", "off", [])
    assert [flip for [(flip, _)] in plan] == [False, True, False, True]


def test_trims_cycle_all_then_each_alone_then_pairs_then_none():
    assert trim_cycle([1, 2, 3]) == [[1, 2, 3], [1], [2], [3], [1, 2], [1, 3], [2, 3], []]


def test_copies_of_a_hook_get_different_trims_when_the_cycle_would_repeat():
    # 4 hooks and a 4-long cycle would hand each hook's second copy its first copy's trims.
    plan = plan_variants([2, 2, 2, 2], "off", "rotate", [1, 2])
    assert all(first[1] != second[1] for first, second in plan)


def test_bare_yaml_off_parses_as_off():
    assert VariantsConfig(flip=False, trim=False).flip == "off"


def _videos_file(tmp_path):
    path = tmp_path / "videos.json"
    path.write_text(json.dumps([
        {"id": "a", "title": "A", "start": 0.0, "end": 2.0, "filename": "hook-a"},
        {"id": "b", "title": "B", "start": 2.0, "end": 4.0, "filename": "hook-b"},
    ]))
    return path


def _plan(path, **variants):
    cfg = ReelCutConfig()
    cfg.output.variants = VariantsConfig(**variants)
    videos = load_videos(path)
    return _plan_videos(videos, _titled_hooks(videos), cfg, [1, 2], path)


def test_missing_copies_are_recorded_as_named_stub_entries(tmp_path):
    path = _videos_file(tmp_path)
    per_hook = _plan(path, copies=2, flip="copies", trim="rotate")
    stub = per_hook[1][1]
    assert (stub.id, stub.of, stub.filename, stub.flip) == ("b-2", "b", "hook-b-2", True)
    assert [e["id"] for e in json.loads(path.read_text())] == ["a", "b", "a-2", "b-2"]


def test_a_recorded_plan_survives_a_config_change(tmp_path):
    path = _videos_file(tmp_path)
    first = _plan(path, flip="alternate", trim="rotate")
    again = _plan(path, flip="all", trim="off")
    assert [(e.flip, e.trim) for e, in again] == [(e.flip, e.trim) for e, in first]
