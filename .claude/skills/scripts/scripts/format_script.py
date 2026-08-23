#!/usr/bin/env python3
"""Put one sentence per line in a saved script's spoken body.

The body is written as one long paragraph, which is hard to read off a phone
while filming. This re-flows the `**SCRIPT**` and `**CONCLUSION**` sections to
one sentence per line, leaving every other section (hooks are already one per
line, CTA, references, resources) exactly as written.

Wording is never changed — only where the line breaks fall. Re-running is safe:
the section is re-joined before it is re-split, so an edited body re-flows.

Usage:
    .venv/bin/python .claude/skills/scripts/scripts/format_script.py <script.md>
"""
import re
import sys
from pathlib import Path

# The spoken body. Hooks are one per line already and the CTA is a tag, so both
# are left alone — this matches what lint_script.py counts as the body.
BODY_SECTIONS = {"**SCRIPT**", "**CONCLUSION**"}

# A sentence boundary: terminal punctuation, then whitespace. The lookbehind
# keeps initialisms ("U.S. government") from being cut after the final letter.
SENTENCE_END = re.compile(r"(?<=[.!?])(?<!\b[A-Z]\.)\s+")


def format_script(text: str) -> str:
    """`text` with the body sections re-flowed to one sentence per line."""
    out: list[str] = []
    buf: list[str] = []
    section = None

    def flush():
        if buf:
            out.extend(SENTENCE_END.split(" ".join(buf)))
            buf.clear()

    lines = text.split("\n")
    while lines and lines[-1] == "":  # trailing newline, re-added on the way out
        lines.pop()

    for raw in lines:
        line = raw.strip()
        if line.startswith("**") and line.endswith("**"):
            flush()
            section = line
            out.append(line)
        elif section in BODY_SECTIONS and line:
            buf.append(line)
        else:
            flush()
            out.append(raw)
    flush()
    return "\n".join(out) + "\n"


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: format_script.py <script.md>")
    path = Path(sys.argv[1])
    try:
        before = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        sys.exit(f"format_script: file not found: {path}")

    after = format_script(before)
    if after == before:
        print(f"✓ {path} already one sentence per line")
        return
    path.write_text(after, encoding="utf-8")
    print(f"✓ {path} re-flowed to one sentence per line "
          f"({len(before.splitlines())} → {len(after.splitlines())} lines)")


if __name__ == "__main__":
    main()
