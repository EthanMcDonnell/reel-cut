"""Regenerate tests/fixtures/edl/<slug>.gaps.txt from the real clip audio.

Run from the repo root, with the clips present under assets/<slug>/:

    .venv/bin/python tests/fixtures/edl/regen_gaps.py [wav-cache-dir]

Every tests/fixtures/retake/<slug>.txt whose clip is still in assets/ gets a gap
fixture; the rest are skipped, so an archived clip keeps the fixture it shipped with.
Passing a cache dir reuses extracted WAVs across runs.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "tests")
from test_real_clips import load_clip_words  # noqa: E402

from reelcut.audio import extract_audio, normalize_audio
from reelcut.config import load_config
from reelcut.gap_detector import detect_gaps

TMP = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp())
cuts = load_config("config.yaml").cuts

for fx in sorted(Path("tests/fixtures/retake").glob("*.txt")):
    slug = fx.stem
    clips = sorted(Path(f"assets/{slug}").glob("*.MOV")) if Path(f"assets/{slug}").is_dir() else []
    if not clips:
        print(f"{slug}: no clip in assets/ — skipped")
        continue
    wav = TMP / f"{slug}.wav"
    if not wav.exists():
        extract_audio(clips[0], wav)
        normalize_audio(wav)

    words = load_clip_words(fx)
    gaps = detect_gaps(words, wav, cuts)

    lines = [
        f"# Inter-word gaps for {slug}, as detect_gaps() computed them on the real clip audio.",
        "#",
        "# assets/ is gitignored, so the audio cannot travel with the test. speech_end is the",
        "# only field that needs the waveform (it is where _find_trailing_speech_end found the",
        "# word's real end, past a truncated alignment), so the gaps are pinned instead of the wav.",
        "#",
        "# Regenerate with the clip present in assets/<slug>/:",
        "#   .venv/bin/python tests/fixtures/edl/regen_gaps.py <tmpdir>",
        "#",
        "# start      end        effective  speech_end  type      cut",
    ]
    for g in gaps:
        lines.append(
            f"{g.start:<10.3f} {g.end:<10.3f} {g.effective_start:<10.3f} {g.speech_end:<11.3f} "
            f"{g.gap_type:<9} {'cut' if g.cut else 'keep'}"
        )
    out = Path("tests/fixtures/edl") / f"{slug}.gaps.txt"
    out.write_text("\n".join(lines) + "\n")
    print(f"{slug}: {len(gaps)} gaps → {out}")
