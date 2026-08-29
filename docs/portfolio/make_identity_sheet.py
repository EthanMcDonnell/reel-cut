#!/usr/bin/env python3
"""Compose the ReelCut icon review sheet from the individual option SVGs.

The three option files are the single source of truth; this only lays them out
side by side so one image can be reviewed at a glance. Run it after editing any
of them:

    python3 docs/portfolio/make_identity_sheet.py

Needs rsvg-convert (brew install librsvg) for the PNG.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

IDENTITY = Path(__file__).resolve().parent / "identity"
OPTIONS = [("cut", "CUT"), ("playcut", "PLAYCUT"), ("transcript", "TRANSCRIPT")]

TILE = 400          # rendered tile size on the sheet
GAP = 100
MARGIN = 100
WIDTH = MARGIN * 2 + TILE * 3 + GAP * 2
HEIGHT = 700


def inner(svg: str) -> str:
    """Everything inside the option's <svg> wrapper, ids left as-is.

    Each option file already prefixes its ids with its own name, so three of
    them can share one document without colliding.
    """
    body = re.sub(r"^.*?<svg[^>]*>", "", svg, flags=re.S)
    body = re.sub(r"</svg>\s*$", "", body)
    return re.sub(r"<(title|desc)[^>]*>.*?</\1>", "", body, flags=re.S).strip()


def main() -> None:
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title desc">',
        "  <title id=\"title\">ReelCut icon review directions</title>",
        "  <desc id=\"desc\">Three warm-gold app-icon concepts on charcoal: Cut, "
        "Playcut and Transcript.</desc>",
        f'  <rect width="{WIDTH}" height="{HEIGHT}" fill="#0B0A09"/>',
    ]
    scale = TILE / 512
    for i, (name, label) in enumerate(OPTIONS):
        x = MARGIN + i * (TILE + GAP)
        parts.append(f'  <g transform="translate({x} 110) scale({scale:.5f})">')
        parts.append("    " + inner((IDENTITY / f"{name}.svg").read_text()))
        parts.append("  </g>")
        parts.append(
            f'  <text x="{x + TILE / 2:.0f}" y="620" fill="#F3C84E" font-size="30" '
            'letter-spacing="6" text-anchor="middle" '
            'font-family="Inter, Helvetica, Arial, sans-serif">'
            f"{label}</text>"
        )
    parts.append("</svg>")

    sheet = IDENTITY / "options.svg"
    sheet.write_text("\n".join(parts) + "\n")

    if not shutil.which("rsvg-convert"):
        sys.exit(f"wrote {sheet.name}; rsvg-convert not found, skipping the PNG")
    subprocess.run(
        ["rsvg-convert", "-w", str(WIDTH * 2), str(sheet),
         "-o", str(IDENTITY / "options.png")],
        check=True,
    )
    print(f"wrote {sheet.name} and options.png")


if __name__ == "__main__":
    main()
