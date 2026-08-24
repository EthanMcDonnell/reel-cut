"""Tests for exposing the Claude output captured for production jobs."""
import http.client
import json
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from types import SimpleNamespace

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import production_queue  # noqa: E402
import upload_server  # noqa: E402

JOB_ID = "a" * 32


def _request(server, path):
    connection = http.client.HTTPConnection(*server.server_address)
    connection.request("GET", path)
    response = connection.getresponse()
    return response.status, response.read()


def _job_server(monkeypatch, queue):
    monkeypatch.setattr(upload_server, "QUEUE_ROOT", queue)
    monkeypatch.setattr(
        upload_server,
        "find_job",
        lambda job_id: (queue / "succeeded" / f"{job_id}.json", {"id": job_id}),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), upload_server.Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_worker_writes_claude_output_to_its_job_log(tmp_path, monkeypatch):
    queue = tmp_path / "queue"
    intake = tmp_path / ".reelcut-intake.json"
    intake.write_text("{}")

    def fake_run(_args, **kwargs):
        assert kwargs["stderr"] is production_queue.subprocess.STDOUT
        kwargs["stdout"].write("Claude output\n")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(production_queue, "notify", lambda _: None)
    monkeypatch.setattr(production_queue, "claude_binary", lambda: "/fake/claude")
    monkeypatch.setattr(production_queue.subprocess, "run", fake_run)
    monkeypatch.setattr(production_queue, "output_is_complete", lambda *args: False)

    job = production_queue.enqueue("hot-take-20260824T153045Z", intake, queue)
    final = production_queue.run_job(production_queue.claim_next(queue), tmp_path, queue)

    assert final == "blocked"
    assert (queue / "logs" / f"{job['id']}.log").read_text() == "Claude output\n"


def test_job_endpoint_advertises_and_serves_existing_claude_log(tmp_path, monkeypatch):
    queue = tmp_path / "queue"
    log_path = queue / "logs" / f"{JOB_ID}.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text("Claude output\n")
    server, thread = _job_server(monkeypatch, queue)

    try:
        job_status, job_body = _request(server, f"/job/{JOB_ID}?json=1")
        page_status, page_body = _request(server, f"/job/{JOB_ID}")
        log_status, log_body = _request(server, f"/job/{JOB_ID}/log")
    finally:
        server.shutdown()
        thread.join()

    assert job_status == 200
    assert json.loads(job_body)["log_url"] == f"/job/{JOB_ID}/log"
    assert page_status == 200
    assert b"View Claude output" in page_body
    assert log_status == 200
    assert log_body == b"Claude output\n"


def test_job_endpoint_hides_a_log_until_the_worker_creates_it(tmp_path, monkeypatch):
    server, thread = _job_server(monkeypatch, tmp_path / "queue")

    try:
        job_status, job_body = _request(server, f"/job/{JOB_ID}?json=1")
        log_status, log_body = _request(server, f"/job/{JOB_ID}/log")
    finally:
        server.shutdown()
        thread.join()

    assert job_status == 200
    assert "log_url" not in json.loads(job_body)
    assert log_status == 404
    assert log_body == b"no worker output yet"
