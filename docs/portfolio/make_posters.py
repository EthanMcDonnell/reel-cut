#!/usr/bin/env python3
"""Regenerate the ReelCut portfolio posters.

The two stills are the *same instant* of the same take: output 31.500s maps back
to source 57.031s through the EDL in the package's .captions.json, so the pair
shows one moment before and after the pipeline rather than two unrelated frames.
`python3 docs/portfolio/make_posters.py --map` reprints that mapping if the
timestamps below ever move.

Reads the source take and the finished render; writes only into
docs/portfolio/posters/.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
PKG = "ht-ghd-better-gitcli"
SRC = ROOT / "assets" / PKG / "DF4506C5-2F13-40FB-AC7A-8EC4943DAB22.MOV"
OUT = ROOT / "output" / PKG / "git-cli-isnt-a-personality.mp4"
CAPTIONS = SRC.with_suffix(".captions.json")
POSTERS = ROOT / "docs" / "portfolio" / "posters"
FONTS = ROOT / "reelcut" / "fonts"

SRC_T = 57.031   # seconds into the raw take
OUT_T = 31.500   # the same spoken word in the finished render

GOLD = (243, 200, 78)
WHITE = (255, 255, 255)
GREY = (138, 133, 128)
CHARCOAL = (13, 12, 11)


def source_time(out_t: float) -> float:
    """Walk the EDL's kept segments to turn an output time into a source time."""
    edl = json.loads(CAPTIONS.read_text())["edl"]
    elapsed = 0.0
    for seg in edl:
        if not seg["keep"]:
            continue
        span = seg["end"] - seg["start"]
        if elapsed <= out_t < elapsed + span:
            return seg["start"] + (out_t - elapsed)
        elapsed += span
    raise SystemExit(f"{out_t}s is past the {elapsed:.3f}s render")


def grab(video: Path, t: float, dest: Path) -> Image.Image:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t), "-i", str(video),
         "-frames:v", "1", "-q:v", "2", str(dest)],
        check=True,
    )
    return Image.open(dest).convert("RGB")


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), size)


def centred(draw: ImageDraw.ImageDraw, y: int, width: int, text: str, f, fill):
    w = draw.textlength(text, font=f)
    draw.text(((width - w) / 2, y), text, font=f, fill=fill)


def banded(frame: Image.Image, at_top: bool, title: str, sub: str) -> Image.Image:
    """A label band drawn *over* the frame, so the poster keeps its 9:16 shape."""
    img = frame.copy()
    d = ImageDraw.Draw(img, "RGBA")
    h = 112
    y = 0 if at_top else img.height - h
    d.rectangle([0, y, img.width, y + h], fill=(*CHARCOAL, 240))
    centred(d, y + 28, img.width, title, font("Inter.ttf", 34), WHITE)
    centred(d, y + 76, img.width, sub, font("Inter.ttf", 19), GOLD)
    return img


def side_by_side(before: Image.Image, after: Image.Image) -> Image.Image:
    panel = (540, 960)
    header = 170
    img = Image.new("RGB", (1080, header + panel[1]), CHARCOAL)
    img.paste(before.resize(panel, Image.LANCZOS), (0, header))
    img.paste(after.resize(panel, Image.LANCZOS), (540, header))

    d = ImageDraw.Draw(img)
    d.text((44, 30), "BEFORE / AFTER", font=font("Inter.ttf", 40), fill=WHITE)
    d.text((44, 86), f"THE SAME INSTANT OF THE TAKE - {SRC_T:.1f}s IN THE SOURCE, "
                     f"{OUT_T:.1f}s IN THE RENDER",
           font=font("Inter.ttf", 20), fill=GREY)
    d.text((44, 130), "BEFORE / SOURCE TAKE", font=font("Inter.ttf", 26), fill=WHITE)
    d.text((584, 130), "AFTER / REELCUT OUTPUT", font=font("Inter.ttf", 26), fill=GOLD)
    # A hairline so the two panels do not read as one photograph.
    d.line([(540, header), (540, img.height)], fill=CHARCOAL, width=2)
    return img


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--map", action="store_true",
                    help="print the output->source time mapping and exit")
    args = ap.parse_args()

    if args.map:
        print(f"output {OUT_T}s -> source {source_time(OUT_T):.3f}s "
              f"(this file uses {SRC_T})")
        return

    for path in (SRC, OUT, CAPTIONS):
        if not path.exists():
            sys.exit(f"missing {path}")

    POSTERS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        before = grab(SRC, SRC_T, tmp / "before.jpg")
        after = grab(OUT, OUT_T, tmp / "after.jpg")

    banded(before, True, "SOURCE TAKE / UNEDITED",
           f"88.4 SECOND ORIGINAL PHONE TAKE - FRAME AT {SRC_T:.1f}s"
           ).save(POSTERS / "01-source-take.jpg", quality=92)
    banded(after, False, "REELCUT OUTPUT",
           f"39.6 SECOND FINAL RENDER - THE SAME WORD AT {OUT_T:.1f}s"
           ).save(POSTERS / "02-final-render.jpg", quality=92)
    side_by_side(before, after).save(POSTERS / "03-before-after.jpg", quality=92)
    print(f"wrote 3 posters into {POSTERS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
