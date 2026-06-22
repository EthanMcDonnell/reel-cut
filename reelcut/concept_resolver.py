"""Concept-image resolver — maps a concept keyword to a sticker PNG.

Concepts are small "reaction" gags (bug → 🐛, handcuffs → arrest, money → 💰) placed
on the timeline by the LLM in images.json (type: "concept", name: "<concept>"). The
available concepts and their art live in `assets/_concepts/concepts.yaml`:

    bug:        {emoji: "1F41B"}                  # downloaded from OpenMoji, cached
    handcuffs:  {emoji: "1F46E", file: cuffs.png} # local file wins when present

`file` is a PNG in the same dir (hand-picked, highest quality); `emoji` is an OpenMoji
colour codepoint fetched from GitHub and cached under ~/.cache/reelcut/concepts/.
"""
from __future__ import annotations

import urllib.request
from pathlib import Path

import yaml

_OPENMOJI_BASE = "https://raw.githubusercontent.com/hfg-gmuend/openmoji/master/color/618x618"
_CACHE_DIR = Path.home() / ".cache" / "reelcut" / "concepts"
_DEFAULT_DIR = Path("assets/_concepts")


def load_concepts(concepts_dir: Path | None = None) -> dict[str, dict]:
    """Return {concept_name: {emoji?, file?}} from concepts.yaml. Missing file → {}."""
    d = Path(concepts_dir) if concepts_dir else _DEFAULT_DIR
    path = d / "concepts.yaml"
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text()) or {}
    return {k: (v or {}) for k, v in raw.items()}


def resolve_concept(name: str, concepts_dir: Path | None = None) -> Path | None:
    """Resolve a concept name to a local PNG path. Local `file` wins; else OpenMoji emoji.

    Returns None if the concept is unknown or its art can't be resolved.
    """
    d = Path(concepts_dir) if concepts_dir else _DEFAULT_DIR
    entry = load_concepts(d).get(name)
    if not entry:
        return None

    file = entry.get("file")
    if file:
        p = d / file
        if p.exists():
            return p

    emoji = entry.get("emoji")
    if emoji:
        return _ensure_emoji(str(emoji).upper())

    return None


def _ensure_emoji(code: str) -> Path | None:
    """Download an OpenMoji colour PNG by hex codepoint (cached). Returns None on error."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    png = _CACHE_DIR / f"{code}.png"
    if png.exists():
        return png
    try:
        with urllib.request.urlopen(f"{_OPENMOJI_BASE}/{code}.png", timeout=10) as r:
            png.write_bytes(r.read())
        return png
    except Exception:
        return None
