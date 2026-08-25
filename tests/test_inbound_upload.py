"""Tests for queue-backed phone uploads."""
import http.client
import json
import re
import sys
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from types import SimpleNamespace

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import production_queue  # noqa: E402
import upload_server  # noqa: E402


def _config(repo: Path, series: str = "", ai_provider: str = ""):
    body = "inbound:\n  series:\n"
    if series:
        body += (
            "    hot-take:\n"
            "      slug_prefix: hot-take\n"
            f"      series: {series}\n"
            "      hook_policy: single\n"
        )
    if ai_provider:
        body += f"production:\n  ai_provider: {ai_provider}\n"
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


def test_mission_control_provider_spawns_without_queueing(tmp_path, monkeypatch):
    assets = tmp_path / "assets"
    assets.mkdir()
    _config(tmp_path, "hot-takes", ai_provider="mission-control")
    monkeypatch.setattr(upload_server, "REPO", tmp_path)
    monkeypatch.setattr(upload_server, "ASSETS", assets)

    def fail_enqueue(*args, **kwargs):
        raise AssertionError("mission-control uploads must not use the claude-cli queue")

    monkeypatch.setattr(upload_server, "enqueue", fail_enqueue)
    spawned = []
    monkeypatch.setattr(upload_server.subprocess, "Popen", lambda *a, **kw: spawned.append((a, kw)))
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

    assert response.status == 202
    assert body == {"asset_slug": body["asset_slug"]}
    assert "job_url" not in body
    [(args, kwargs)] = spawned
    assert args[0] == ["mission-control", "--no-wait", "--", "/produce-reel", body["asset_slug"], "--auto"]
    assert kwargs["cwd"] == tmp_path


def test_script_upload_lands_directly_in_the_slug_folder(tmp_path, monkeypatch):
    assets = tmp_path / "assets"
    source = assets / "edge-cache"
    source.mkdir(parents=True)
    (source / "script.md").write_text("**HOOK**\nA hook")
    _config(tmp_path)
    monkeypatch.setattr(upload_server, "REPO", tmp_path)
    monkeypatch.setattr(upload_server, "ASSETS", assets)
    monkeypatch.setattr(upload_server, "enqueue", lambda slug, receipt: {"id": "a" * 32})
    server = ThreadingHTTPServer(("127.0.0.1", 0), upload_server.Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        connection = http.client.HTTPConnection(*server.server_address)
        connection.request("PUT", "/upload/edge-cache?name=take.mov", body=b"video")
        response = connection.getresponse()
        body = json.loads(response.read())
    finally:
        server.shutdown()
        thread.join()

    assert response.status == 202
    assert body["asset_slug"] == "edge-cache"
    assert (source / "take.mov").read_bytes() == b"video"
    assert not (source / ".reelcut-intake.json").exists()
    assert [p.name for p in assets.iterdir()] == ["edge-cache"]


def test_second_script_upload_is_refused(tmp_path, monkeypatch):
    assets = tmp_path / "assets"
    source = assets / "edge-cache"
    source.mkdir(parents=True)
    (source / "script.md").write_text("**HOOK**\nA hook")
    (source / "existing.mov").write_bytes(b"first take")
    _config(tmp_path)
    monkeypatch.setattr(upload_server, "REPO", tmp_path)
    monkeypatch.setattr(upload_server, "ASSETS", assets)

    def fail_enqueue(*args, **kwargs):
        raise AssertionError("a refused upload must never reach the queue")

    monkeypatch.setattr(upload_server, "enqueue", fail_enqueue)
    server = ThreadingHTTPServer(("127.0.0.1", 0), upload_server.Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        connection = http.client.HTTPConnection(*server.server_address)
        connection.request("PUT", "/upload/edge-cache?name=retake.mov", body=b"second take")
        response = connection.getresponse()
        response.read()
    finally:
        server.shutdown()
        thread.join()

    assert response.status == 409
    assert (source / "existing.mov").read_bytes() == b"first take"
    assert not (source / "retake.mov").exists()
    assert source.is_dir()


def test_dropped_upload_never_deletes_the_script_folder(tmp_path, monkeypatch):
    assets = tmp_path / "assets"
    source = assets / "edge-cache"
    source.mkdir(parents=True)
    (source / "script.md").write_text("**HOOK**\nA hook")
    _config(tmp_path)
    monkeypatch.setattr(upload_server, "REPO", tmp_path)
    monkeypatch.setattr(upload_server, "ASSETS", assets)
    server = ThreadingHTTPServer(("127.0.0.1", 0), upload_server.Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        connection = http.client.HTTPConnection(*server.server_address)
        connection.putrequest("PUT", "/upload/edge-cache?name=take.mov")
        connection.putheader("Content-Length", "1000")  # promise more than is ever sent
        connection.endheaders()
        connection.send(b"short")
        connection.close()  # drop the connection mid-upload
    finally:
        server.shutdown()
        thread.join()

    for _ in range(20):
        if not any(source.glob("*.part")):
            break
        time.sleep(0.1)
    assert (source / "script.md").is_file()
    assert not any(source.glob("*.part"))


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
