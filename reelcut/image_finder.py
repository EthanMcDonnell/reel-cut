"""Auto-image keyword detection — matches transcript words to gilbarbara/logos shortnames."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .config import ImagesConfig
from .transcriber import WordTimestamp


@dataclass
class ImageCue:
    keyword: str      # matched logo shortname
    start: float      # output timeline start (seconds)
    end: float        # output timeline end (seconds)
    image_path: str   # absolute path to resolved PNG
    type: str = "logo"  # "logo" | "person" | "screenshot" | "concept" | "figure"
    kind: str = ""    # type=figure only: "chart" | "diagram"


def detect_image_cues(
    words: list[WordTimestamp],
    config: ImagesConfig,
    reset_boundaries: list[float] | None = None,
) -> list[ImageCue]:
    """Scan output-timeline words against logos manifest; return first-occurrence cues.

    Each matched shortname is emitted at most once *per section* — by default the whole
    video is one section, so a logo fires once. `reset_boundaries` (output-timeline
    seconds, e.g. heading-card edges) clear the seen set as the timeline crosses each
    boundary, so a brand re-mentioned in a later section fires its logo again there.
    Handles possessives ("Anthropic's"), possessive-plurals ("Anthropics'"), and plain
    plurals ("APIs") by trying slug variants before giving up.
    """
    from .image_resolver import load_manifest, normalize_slug, resolve_logo

    try:
        manifest = load_manifest()
    except RuntimeError as exc:
        from rich.console import Console
        Console().print(f"  [yellow]auto-image: {exc} — skipping[/yellow]")
        return []

    # Build candidate slug set
    if config.auto_detect:
        candidate_slugs: set[str] = set(manifest.keys())
    else:
        candidate_slugs = set()
    candidate_slugs.update(config.keywords)

    exclude = set(config.exclude)

    explicit_keywords = set(config.keywords)
    seen: set[str] = set()
    cues: list[ImageCue] = []

    boundaries = sorted(t for t in (reset_boundaries or []) if t > 0)
    bi = 0

    for word in words:
        # Crossing one or more section boundaries clears the seen set so logos re-fire.
        crossed = False
        while bi < len(boundaries) and word.start >= boundaries[bi]:
            bi += 1
            crossed = True
        if crossed:
            seen.clear()

        variants = _slug_variants(word.word, normalize_slug)

        # Whisper capitalises proper nouns — a lowercase word is almost certainly a
        # common English word, not a brand. Skip unless it's an explicit keyword.
        is_capitalized = bool(word.word) and word.word[0].isupper()
        if config.require_capitalized and not is_capitalized:
            if not any(s in explicit_keywords for s in variants):
                continue

        matched_slug = None
        for slug in variants:
            if not slug or slug in seen or slug in exclude:
                continue
            if slug in candidate_slugs:
                matched_slug = slug
                break

        if matched_slug is None:
            continue

        seen.add(matched_slug)
        png = resolve_logo(matched_slug, manifest)
        if png is None:
            continue

        cues.append(ImageCue(
            keyword=matched_slug,
            start=word.start,
            end=word.start + config.display_duration_s,
            image_path=str(png),
        ))

    return cues


def _slug_variants(word: str, normalize_slug) -> list[str]:
    """Return candidate slugs to try for a transcript word, most to least specific.

    Handles:
    - Possessive apostrophe-s: "Anthropic's" → tries "anthropics", then "anthropic"
    - Possessive-plural:      "Anthropics'" → tries "anthropics", then "anthropic"
    - Plain plural-s:         "APIs"        → tries "apis", then "api"
    """
    # Strip possessive markers before normalising:
    # "Anthropic's" → "Anthropic",  "Anthropics'" → "Anthropics"
    apostrophe_re = re.compile(r"['’]s$|s['’]$|['’]$", re.IGNORECASE)
    stripped = apostrophe_re.sub("", word)

    variants: list[str] = []

    def _add(s: str) -> None:
        if s and s not in variants:
            variants.append(s)

    slug_raw = normalize_slug(word)
    slug_stripped = normalize_slug(stripped)

    _add(slug_raw)
    _add(slug_stripped)

    # Also try removing a trailing 's' for plurals not caught by apostrophe stripping
    for base in (slug_raw, slug_stripped):
        if base and base.endswith("s") and len(base) > 3:
            _add(base[:-1])

    # Map bare product names to their namespaced slug (e.g. "onedrive" →
    # "microsoft-onedrive"). Appended last so an exact slug always wins first.
    from .image_resolver import LOGO_ALIASES
    for v in list(variants):
        if v in LOGO_ALIASES:
            _add(LOGO_ALIASES[v])

    return variants
