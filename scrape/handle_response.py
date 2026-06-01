#!/usr/bin/env python3
"""
Called by the Telegram bot when a user clicks Keep or Delete.
Payload is passed as JSON on stdin.

  Keep   → marks article as viewed in the series DB table
  Delete → adds URL to rejected and removes from the series table
"""

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from db import get_db

LOG_PATH = Path(__file__).parent / "db" / "responses.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("handle_response")


def main() -> None:
    body = json.load(sys.stdin)
    response = (body.get("action") or body.get("response") or body.get("button") or "").lower()
    metadata = body.get("metadata") or {}
    url = metadata.get("url", "")
    article_id = metadata.get("article_id", "")

    if response == "delete":
        if not url:
            log.warning(f"Delete received but no URL in metadata for {article_id}")
            sys.exit(1)
        run_type = metadata.get("run_type", "")
        title = metadata.get("title", "")
        conn = get_db()
        conn.execute(
            "INSERT OR IGNORE INTO rejected (series, topic, source_url, reason, rejected_at) VALUES (?, ?, ?, ?, date('now'))",
            (run_type, title or None, url, "telegram:delete"),
        )
        if run_type in ("tbbt", "updates"):
            conn.execute(f"DELETE FROM {run_type} WHERE url = ?", (url,))
        conn.commit()
        log.info(f"Rejected and deleted from {run_type or 'series'}: {url}")
    elif response == "keep":
        run_type = metadata.get("run_type", "")
        if run_type not in ("tbbt", "updates"):
            log.warning(f"Keep received but unknown run_type: {run_type!r}")
            sys.exit(1)
        conn = get_db()
        cur = conn.execute(
            f"UPDATE {run_type} SET status = 'viewed' WHERE url = ?",
            (url,),
        )
        conn.commit()
        if cur.rowcount == 0:
            log.warning(f"Keep received but article not found in {run_type}: {url}")
        else:
            log.info(f"Marked as viewed in {run_type}: {url}")
    else:
        log.warning(f"Unknown response: {response!r} for {url or article_id}")
        sys.exit(1)


if __name__ == "__main__":
    main()
