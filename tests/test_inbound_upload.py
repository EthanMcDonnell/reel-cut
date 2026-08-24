"""Tests for queue-backed phone uploads."""
import http.client
import json
import re
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from types import SimpleNamespace

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import production_queue  # noqa: E402
import upload_server  # noqa: E402


def _config(repo: Path, series: str = ""):
    body = "inbound:\n  series:\n"
    if series:
        body += (
            "    hot-take:\n"
            "      slug_prefix: hot-take\n"
            f"      series: {series}\n"
            "      hook_policy: single\n"
        )
    (repo / "config.yaml").write_text(body)


def test_direct_series_link_queues_a_flat_take_workspace(tmp_path, monkeypatch):
    assets = tmp_path / "assets"
    assets.mkdir()
    _config(tmp_path, "hot-takes")
    monkeypatch.setattr(upload_server, "REPO", tmp_path)
    monkeypatch.setattr(upload_server, "ASSETS", assets)
    monkeypatch.setattr(upload_server, "enqueue", lambda slug, receipt: {"id": "a" * 32})
    server = ThreadingHTTPServer(("127.0.0.1", 0), upload_server.Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        connection = http.client.HTTPConnection(*server.server_address)
        connection.request("PUT", "/upload/hot-take?name=take.mov", body=b"video")
        response = connection.getresponse()
        body = json.loads(response.read())
    finally:
        server.shutdown()
        thread.join()

    directory = assets / body["asset_slug"]
    receipt = json.loads((directory / ".reelcut-intake.json").read_text())
    assert response.status == 202
    assert re.fullmatch(r"hot-take-\d{8}T\d{6}Z(?:-\d+)?", directory.name)
    assert receipt["series"] == "hot-takes"
    assert (directory / "take.mov").read_bytes() == b"video"


def test_script_upload_copies_context_without_copying_old_footage(tmp_path, monkeypatch):
    assets = tmp_path / "assets"
    source = assets / "edge-cache"
    (source / "screenshots").mkdir(parents=True)
    (source / "script.md").write_text("**HOOK**\nA hook")
    (source / "manifest.json").write_text("[]")
    (source / "screenshots" / "snippet.png").write_bytes(b"image")
    (source / "old-take.mov").write_bytes(b"video")
    (source / "videos.json").write_text("[]")
    _config(tmp_path)
    monkeypatch.setattr(upload_server, "REPO", tmp_path)
    monkeypatch.setattr(upload_server, "ASSETS", assets)

    directory, metadata = upload_server.allocate_upload("edge-cache")

    assert metadata == {"kind": "scripted", "source_slug": "edge-cache", "hook_policy": "script"}
    assert (directory / "script.md").is_file()
    assert (directory / "screenshots" / "snippet.png").is_file()
    assert not (directory / "old-take.mov").exists()
    assert not (directory / "videos.json").exists()


def test_worker_blocks_a_zero_exit_without_rendered_artifacts(tmp_path, monkeypatch):
    queue = tmp_path / "queue"
    intake = tmp_path / ".reelcut-intake.json"
    intake.write_text("{}")
    command = []

    def fake_run(args, **kwargs):
        command.extend(args)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(production_queue, "notify", lambda _: None)
    monkeypatch.setattr(production_queue, "claude_binary", lambda: "/fake/claude")
    monkeypatch.setattr(production_queue.subprocess, "run", fake_run)
    monkeypatch.setattr(production_queue, "output_is_complete", lambda *args: False)

    job = production_queue.enqueue("hot-take-20260824T153045Z", intake, queue)
    claimed = production_queue.claim_next(queue)
    final = production_queue.run_job(claimed, tmp_path, queue)
    found = production_queue.find_job(job["id"], queue)

    assert final == "blocked"
    assert command[:3] == ["/fake/claude", "-p", "/produce-reel hot-take-20260824T153045Z --auto"]
    assert command[3:] == ["--settings", str(production_queue.WORKER_SETTINGS), "--permission-mode", "default"]
    assert found is not None
    assert found[1]["status"] == "blocked"
