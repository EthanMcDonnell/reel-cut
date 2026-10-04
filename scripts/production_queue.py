#!/usr/bin/env python3
"""Durable, single-worker queue for phone-uploaded ReelCut recordings.

    .venv/bin/python scripts/production_queue.py run
    .venv/bin/python scripts/production_queue.py status <job-id>
    .venv/bin/python scripts/production_queue.py retry <job-id>

Jobs are JSON files moved atomically between state directories. The worker deliberately
never retries a partially run Claude session: an operator must call ``retry``.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from reelcut.config import load_config

QUEUE_ROOT = REPO / ".reelcut" / "production-queue"
WORKER_SETTINGS = Path(__file__).with_name("worker-settings.json")
STATES = ("pending", "running", "succeeded", "blocked", "failed", "interrupted")
TELEGRAM_API = "http://localhost:8765/telegram/send"
TOPIC = "file-exchange"


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def queue_dirs(queue_root: Path = QUEUE_ROOT) -> None:
    for state in (*STATES, "logs"):
        (queue_root / state).mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    temp.replace(path)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def enqueue(asset_slug: str, intake_path: Path, queue_root: Path = QUEUE_ROOT) -> dict[str, Any]:
    """Persist a new pending production job and return its immutable receipt."""
    queue_dirs(queue_root)
    job = {
        "id": uuid.uuid4().hex,
        "asset_slug": asset_slug,
        "intake_path": str(intake_path),
        "status": "pending",
        "created_at": now(),
        "updated_at": now(),
        "attempt": 1,
    }
    _write_json(queue_root / "pending" / f"{job['id']}.json", job)
    notify(f"🎬 queued: {asset_slug} ({job['id'][:8]})")
    return job


def find_job(job_id: str, queue_root: Path = QUEUE_ROOT) -> tuple[Path, dict[str, Any]] | None:
    for state in STATES:
        path = queue_root / state / f"{job_id}.json"
        if path.is_file():
            return path, _read_json(path)
    return None


def _transition(path: Path, status: str, **fields: Any) -> Path:
    if status not in STATES:
        raise ValueError(f"unknown job state: {status}")
    job = _read_json(path)
    job.update(fields, status=status, updated_at=now())
    _write_json(path, job)
    target = path.parent.parent / status / path.name
    path.replace(target)
    return target


def claim_next(queue_root: Path = QUEUE_ROOT) -> Path | None:
    """Atomically claim the oldest pending job, or return None when none exist."""
    queue_dirs(queue_root)
    pending = queue_root / "pending"
    running = queue_root / "running"
    for path in sorted(pending.glob("*.json")):
        claimed = running / path.name
        try:
            path.replace(claimed)
        except FileNotFoundError:
            continue
        job = _read_json(claimed)
        job.update(status="running", started_at=now(), updated_at=now())
        _write_json(claimed, job)
        return claimed
    return None


def recover_interrupted(queue_root: Path = QUEUE_ROOT) -> None:
    """Never assume a job left running at process death is safe to rerun."""
    queue_dirs(queue_root)
    for path in (queue_root / "running").glob("*.json"):
        job = _read_json(path)
        _transition(path, "interrupted", reason="worker restarted while job was running")
        notify(f"⚠️ interrupted: {job['asset_slug']} ({job['id'][:8]})")


def output_is_complete(repo: Path, asset_slug: str) -> bool:
    """A zero Claude exit is not enough: ensure it actually rendered a usable video."""
    cfg = load_config(repo / "config.yaml")
    assets = Path(cfg.assets.location)
    if not assets.is_absolute():
        assets = repo / assets
    output = Path(cfg.output.location)
    if not output.is_absolute():
        output = repo / output

    asset_dir = assets / asset_slug
    captions = list(asset_dir.glob("*.captions.json"))
    videos_path = asset_dir / "videos.json"
    if not captions or not videos_path.is_file() or not any((output / asset_slug).glob("*.mp4")):
        return False
    try:
        videos = json.loads(videos_path.read_text())
    except json.JSONDecodeError:
        return False
    return isinstance(videos, list) and any(video.get("title") for video in videos if isinstance(video, dict))


def claude_binary() -> str:
    configured = os.environ.get("CLAUDE_BIN")
    found = configured or shutil.which("claude")
    if not found:
        raise FileNotFoundError("claude executable not found; reinstall the upload agent")
    path = Path(found).expanduser().resolve()
    if not path.is_absolute() or not path.is_file():
        raise FileNotFoundError(f"invalid CLAUDE_BIN: {path}")
    return str(path)


def run_job(path: Path, repo: Path = REPO, queue_root: Path = QUEUE_ROOT) -> str:
    """Run one claimed job and return its final state."""
    job = _read_json(path)
    log_path = queue_root / "logs" / f"{job['id']}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    prompt = f"/produce-reel {job['asset_slug']} --auto"
    # Production stages run as Claude background tasks and may transcribe for over 10 minutes.
    environment = os.environ | {"CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS": "3600000"}

    argv = [claude_binary(), "-p", prompt, "--settings", str(WORKER_SETTINGS), "--permission-mode", "default"]
    # A bad config.yaml must block this one job (below), not crash the worker loop
    # that has no handler around run_job — so a model lookup failure degrades to
    # the provider default rather than propagating.
    try:
        model = load_config(repo / "config.yaml").production.ai_model
    except Exception as exc:
        print(f"could not read production.ai_model, using default model: {exc}", file=sys.stderr, flush=True)
        model = ""
    if model:
        argv += ["--model", model]

    notify(f"⏳ processing: {job['asset_slug']} ({job['id'][:8]})")
    try:
        with log_path.open("w") as log:
            result = subprocess.run(
                argv,
                cwd=repo,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
    except OSError as exc:
        _transition(path, "failed", error=str(exc), log_path=str(log_path))
        notify(f"❌ failed: {job['asset_slug']} ({job['id'][:8]})")
        return "failed"

    if result.returncode:
        _transition(path, "failed", exit_code=result.returncode, log_path=str(log_path))
        notify(f"❌ failed: {job['asset_slug']} ({job['id'][:8]})")
        return "failed"

    try:
        complete = output_is_complete(repo, job["asset_slug"])
    except Exception as exc:
        _transition(path, "blocked", exit_code=0, log_path=str(log_path), reason=f"could not verify output: {exc}")
        notify(f"⚠️ blocked: {job['asset_slug']} ({job['id'][:8]})")
        return "blocked"
    if complete:
        _transition(path, "succeeded", exit_code=0, log_path=str(log_path))
        notify(f"✅ rendered: {job['asset_slug']} ({job['id'][:8]})")
        return "succeeded"

    _transition(
        path,
        "blocked",
        exit_code=0,
        log_path=str(log_path),
        reason="Claude exited without the expected rendered artifacts",
    )
    notify(f"⚠️ blocked: {job['asset_slug']} ({job['id'][:8]})")
    return "blocked"


def _lock(queue_root: Path) -> tuple[Any, bool]:
    queue_root.mkdir(parents=True, exist_ok=True)
    handle = (queue_root / "worker.lock").open("w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None, False
    return handle, True


def run_worker(once: bool = False, queue_root: Path = QUEUE_ROOT) -> None:
    """Run serially until interrupted, or process one job with ``once``."""
    handle, acquired = _lock(queue_root)
    if not acquired:
        return
    try:
        recover_interrupted(queue_root)
        while True:
            path = claim_next(queue_root)
            if path is None:
                if once:
                    return
                time.sleep(2)
                continue
            run_job(path, queue_root=queue_root)
            if once:
                return
    finally:
        fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()


def retry(job_id: str, queue_root: Path = QUEUE_ROOT) -> None:
    found = find_job(job_id, queue_root)
    if found is None:
        raise ValueError(f"no job named {job_id}")
    path, job = found
    if job["status"] not in {"blocked", "failed", "interrupted"}:
        raise ValueError(f"cannot retry a {job['status']} job")
    _transition(path, "pending", attempt=job["attempt"] + 1, retried_at=now())
    notify(f"🔁 requeued: {job['asset_slug']} ({job['id'][:8]})")


def notify(content: str) -> None:
    """Best-effort operator notification; queue durability never depends on Telegram."""
    try:
        httpx.post(TELEGRAM_API, json={"content": content, "topic": TOPIC}, timeout=10).raise_for_status()
    except httpx.HTTPError as exc:
        print(f"Telegram notification failed: {exc}", file=sys.stderr, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run the serial production worker")
    run.add_argument("--once", action="store_true", help="process at most one job")
    status = sub.add_parser("status", help="print a job receipt")
    status.add_argument("job_id")
    retry_parser = sub.add_parser("retry", help="return a failed job to the queue")
    retry_parser.add_argument("job_id")
    args = parser.parse_args()

    if args.command == "run":
        run_worker(args.once)
    elif args.command == "status":
        found = find_job(args.job_id)
        if found is None:
            sys.exit(f"no job named {args.job_id}")
        print(json.dumps(found[1], indent=2))
    else:
        retry(args.job_id)


if __name__ == "__main__":
    main()
