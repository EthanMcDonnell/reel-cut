"""The per-video half of the automation spec: what `automation.json` may hold,
and how `automation_spec.build` expands it.

The cockpit is not called here. Whether `casual_replies` still exists is a live
question with a live answer, and a test asserting it would be asserting the
cockpit's contents rather than this code's behaviour.
"""
import importlib.util
from pathlib import Path

SCRAPE = Path(__file__).parent.parent / "scrape"


def _load(name):
    spec = importlib.util.spec_from_file_location(f"rc_{name}", SCRAPE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


automation_spec = _load("automation_spec")
validate_automation = _load("validate_automation")

GOOD = {
    "trigger_keywords": ["S3"],
    "follower_message": "S3 resource:\nhttps://aws.amazon.com/blogs/storage/",
}


def test_a_well_formed_file_passes_clean():
    assert validate_automation.check_file(GOOD) == ([], [])


def test_a_missing_keyword_is_rejected():
    errors, _ = validate_automation.check_file({"follower_message": GOOD["follower_message"]})
    assert any("trigger_keywords is missing" in e for e in errors)


def test_a_multi_word_keyword_is_rejected():
    errors, _ = validate_automation.check_file({**GOOD, "trigger_keywords": ["S3 GUIDE"]})
    assert any("must be a single word" in e for e in errors)


def test_a_missing_reward_is_rejected():
    errors, _ = validate_automation.check_file({"trigger_keywords": ["S3"]})
    assert any("follower_message is missing" in e for e in errors)


def test_a_reward_with_no_url_warns_but_does_not_fail():
    errors, warnings = validate_automation.check_file({**GOOD, "follower_message": "thanks!"})
    assert errors == []
    assert any("carries no URL" in w for w in warnings)


def test_overriding_a_fixed_field_is_rejected():
    # The constants are not per-video. A file that sets one has drifted off the
    # standard, which is the thing holding them in one place exists to prevent.
    errors, _ = validate_automation.check_file({**GOOD, "dm_pack": "chill"})
    assert any("dm_pack is not a per-video field" in e for e in errors)


def test_build_expands_the_two_fields_into_the_full_spec():
    built = automation_spec.build("demo", GOOD)
    assert built["key"] == "demo"
    assert built["template_type"] == "comment_to_follow_dm"
    assert built["trigger_keywords"] == ["S3"]
    assert built["config"] == {
        "comment_reply_fn": automation_spec.COMMENT_REPLY_FN,
        "comment_replies": [],
        "dm_pack": automation_spec.DM_PACK,
        "confirm_keyword": automation_spec.CONFIRM_KEYWORD,
        "resource": automation_spec.RESOURCE,
        "on_check_error": automation_spec.ON_CHECK_ERROR,
        "follower_message": GOOD["follower_message"],
    }


def test_the_key_is_always_the_slug_so_every_hook_joins_one_flow():
    # A per-hook key would create a flow per hook, which is the failure the
    # shared key exists to prevent.
    assert automation_spec.build("demo", GOOD)["key"] == "demo"
    assert "key" not in GOOD  # nothing per-video can override it


def test_a_slug_with_no_file_has_no_automation(tmp_path, monkeypatch):
    monkeypatch.setattr(automation_spec, "ROOT", tmp_path)
    assert automation_spec.for_slug("nope") is None


def test_for_slug_reads_the_file_and_builds_it(tmp_path, monkeypatch):
    import json

    monkeypatch.setattr(automation_spec, "ROOT", tmp_path)
    d = tmp_path / "assets" / "demo"
    d.mkdir(parents=True)
    (d / "automation.json").write_text(json.dumps(GOOD))
    built = automation_spec.for_slug("demo")
    assert built["config"]["follower_message"] == GOOD["follower_message"]
    assert built["config"]["dm_pack"] == automation_spec.DM_PACK
