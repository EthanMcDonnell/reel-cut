"""Extract the spoken narration from a saved video script .md.

A script file holds structural markers (**HOOK**, **SCRIPT**, **CONCLUSION**,
**REFERENCES:**), optional "HOOK N:" labels, a references list, and an appended
resources block — none of which are spoken aloud. Only the hook lines and the body
are read by the presenter, so only those should bias transcription. This strips
everything else to a single line of plain spoken text, fed to Whisper as `hotwords`
so technical terms (proper nouns, "lol" vs "lull") transcribe correctly throughout.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# A section marker is a whole line of bold ALL-CAPS, e.g. **HOOK**, **SCRIPT**,
# **CONCLUSION**, **REFERENCES:**.
_MARKER = re.compile(r"^\*\*[A-Z][A-Z &]*:?\*\*$")
_HOOK_LABEL = re.compile(r"^HOOK\s+\d+:\s*", re.IGNORECASE)


def extract_spoken_text(md: str) -> str:
    """Return the spoken narration (hooks + body), markers/labels/references stripped."""
    lines = md.splitlines()
    i = 0

    # Skip a leading YAML frontmatter block if present.
    if i < len(lines) and lines[i].strip() == "---":
        i += 1
        while i < len(lines) and lines[i].strip() != "---":
            i += 1
        i += 1  # consume closing ---

    spoken: list[str] = []
    for raw in lines[i:]:
        line = raw.strip()
        if not line:
            continue
        if _MARKER.match(line):
            # The references section and anything appended after it (links, the
            # resources/CTA block) is never spoken — stop here.
            if "REFERENCES" in line.upper():
                break
            continue  # drop other section markers (**HOOK**, **SCRIPT**, **CONCLUSION**)
        line = _HOOK_LABEL.sub("", line)      # "HOOK 1: <text>" → "<text>"
        line = re.sub(r"[*_#`]+", "", line)   # strip markdown emphasis / heading marks
        line = line.strip()
        if line:
            spoken.append(line)
    return " ".join(spoken)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: python -m reelcut.script_text <script.md> <out.txt>", file=sys.stderr)
        return 2
    src, out = Path(argv[1]), Path(argv[2])
    text = extract_spoken_text(src.read_text())
    if not text:
        print(f"no spoken text extracted from {src}", file=sys.stderr)
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
