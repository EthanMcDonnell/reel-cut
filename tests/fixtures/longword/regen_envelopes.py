"""Regenerate tests/fixtures/longword/<slug>.txt from the real clip audio.

Run from the repo root, with the clips present under assets/<slug>/:

    .venv/bin/python tests/fixtures/longword/regen_envelopes.py

Every assets/<slug>/ holding a .debug.3.post-align report gets a fixture listing its
over-long aligned words and their 10 ms speech/silence envelopes; the rest are skipped,
so an archived clip keeps the fixture it shipped with.
"""
import re
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, "tests")
from test_real_clips import _WORD_LINE, _secs  # noqa: E402

from reelcut.audio import extract_audio, normalize_audio
from reelcut.config import load_config
from reelcut.gap_detector import _LONG_WORD_DUR_S, _load_audio

TMP = Path(tempfile.mkdtemp())
cuts = load_config("config.yaml").cuts


def envelope(audio: np.ndarray, sr: int, start: float, end: float) -> str:
    frame = max(64, int(0.010 * sr))
    thr = float(10 ** (cuts.silence_threshold_db / 20))
    flags = []
    for pos in range(int(start * sr), int(end * sr), frame):
        f = audio[pos : pos + frame]
        if len(f) < 64:
            break
        flags.append(float(np.mean(np.abs(f) > thr)) >= cuts.failure_tolerance_ratio)
    runs, cur, n = [], flags[0], 0
    for v in flags:
        if v == cur:
            n += 1
        else:
            runs.append((cur, n))
            cur, n = v, 1
    runs.append((cur, n))
    return " ".join(f"{'S' if v else '.'}{n}" for v, n in runs)


for report in sorted(Path("assets").glob("*/*.debug.3.post-align.txt")):
    slug = report.parent.name
    clips = [p for p in report.parent.glob("*") if p.suffix.lower() in {".mov", ".mp4"}]
    if not clips:
        print(f"{slug}: no clip in assets/ — skipped")
        continue
    long_words = [
        (m.group(3), _secs(m.group(1)), _secs(m.group(2)))
        for m in (_WORD_LINE.search(ln) for ln in report.read_text().splitlines())
        if m and _secs(m.group(2)) - _secs(m.group(1)) > _LONG_WORD_DUR_S
    ]
    if not long_words:
        print(f"{slug}: no over-long words — skipped")
        continue

    wav = TMP / f"{slug}.wav"
    extract_audio(clips[0], wav)
    normalize_audio(wav)
    audio, sr = _load_audio(wav)

    out = Path(f"tests/fixtures/longword/{slug}.txt")
    header = out.read_text().split("# word")[0] if out.exists() else ""
    lines = [f"{w:<8}  {s:<8.3f}  {e:<8.3f}  {envelope(audio, sr, s, e)}" for w, s, e in long_words]
    out.write_text(header + "# word    start     end       envelope\n" + "\n".join(lines) + "\n")
    print(f"{slug}: {len(long_words)} over-long word(s)")
