"""Tests for the non-interactive production worker."""
import sys
from pathlib import Path
from types import SimpleNamespace

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import production_queue  # noqa: E402


def test_worker_waits_for_long_running_claude_background_tasks(tmp_path, monkeypatch):
    queue = tmp_path / "queue"
    intake = tmp_path / ".reelcut-intake.json"
    intake.write_text("{}")

    def fake_run(_args, **kwargs):
        assert kwargs["env"]["CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS"] == "3600000"
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(production_queue, "notify", lambda _: None)
    monkeypatch.setattr(production_queue, "claude_binary", lambda: "/fake/claude")
    monkeypatch.setattr(production_queue.subprocess, "run", fake_run)
    monkeypatch.setattr(production_queue, "output_is_complete", lambda *args: False)

    job = production_queue.enqueue("hot-take-20260824T141002Z", intake, queue)
    final = production_queue.run_job(production_queue.claim_next(queue), tmp_path, queue)

    assert final == "blocked"
    assert production_queue.find_job(job["id"], queue)[1]["status"] == "blocked"


def test_worker_forwards_configured_model_to_claude(tmp_path, monkeypatch):
    queue = tmp_path / "queue"
    intake = tmp_path / ".reelcut-intake.json"
    intake.write_text("{}")
    (tmp_path / "config.yaml").write_text("production:\n  ai_provider: claude-cli\n  ai_model: opus\n")

    seen = {}

    def fake_run(args, **kwargs):
        seen["args"] = args
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(production_queue, "notify", lambda _: None)
    monkeypatch.setattr(production_queue, "claude_binary", lambda: "/fake/claude")
    monkeypatch.setattr(production_queue.subprocess, "run", fake_run)
    monkeypatch.setattr(production_queue, "output_is_complete", lambda *args: True)

    production_queue.enqueue("hot-take-20260824T141002Z", intake, queue)
    production_queue.run_job(production_queue.claim_next(queue), tmp_path, queue)

    assert seen["args"][-2:] == ["--model", "opus"]


def test_worker_omits_model_flag_when_unconfigured(tmp_path, monkeypatch):
    queue = tmp_path / "queue"
    intake = tmp_path / ".reelcut-intake.json"
    intake.write_text("{}")
    (tmp_path / "config.yaml").write_text("production:\n  ai_provider: claude-cli\n")

    seen = {}

    def fake_run(args, **kwargs):
        seen["args"] = args
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(production_queue, "notify", lambda _: None)
    monkeypatch.setattr(production_queue, "claude_binary", lambda: "/fake/claude")
    monkeypatch.setattr(production_queue.subprocess, "run", fake_run)
    monkeypatch.setattr(production_queue, "output_is_complete", lambda *args: True)

    production_queue.enqueue("hot-take-20260824T141002Z", intake, queue)
    production_queue.run_job(production_queue.claim_next(queue), tmp_path, queue)

    assert "--model" not in seen["args"]
