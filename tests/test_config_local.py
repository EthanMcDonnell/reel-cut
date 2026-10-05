"""config.local.yaml is deep-merged over config.yaml."""
from reelcut.config import load_config


def test_local_overrides_merge_over_base(tmp_path):
    (tmp_path / "config.yaml").write_text(
        "whisper:\n  model: medium\n  beam_size: 4\nproduction:\n  ai_provider: claude-cli\n"
    )
    (tmp_path / "config.local.yaml").write_text(
        'whisper:\n  initial_prompt: "Sourdough, levain."\nproduction:\n  ai_provider: mission-control\n'
    )
    cfg = load_config(tmp_path / "config.yaml")
    assert cfg.whisper.initial_prompt == "Sourdough, levain."
    assert cfg.whisper.model == "medium" and cfg.whisper.beam_size == 4  # siblings kept
    assert cfg.production.ai_provider == "mission-control"


def test_no_local_file_uses_base_only(tmp_path):
    (tmp_path / "config.yaml").write_text("whisper:\n  model: medium\n")
    assert load_config(tmp_path / "config.yaml").whisper.initial_prompt is None
