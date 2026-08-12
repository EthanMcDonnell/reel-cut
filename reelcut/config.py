"""Config loader — YAML schema, validation, and default config generation."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class CutsConfig(BaseModel):
    min_silence_ms: int = 100
    min_breath_ms: int = 60
    breath_detection: bool = True
    silence_threshold_db: float = -40.0
    vad_threshold: float = 0.5
    speech_pad_ms: int = 80
    word_end_scan_ms: int = 50
    breath_amplitude_ratio: float = 0.15
    failure_tolerance_ratio: float = 0.02
    min_keep_ms: int = 50
    repetition_detection: bool = False
    min_retake_words: int = 3
    max_retake_gap_s: float = 20.0
    min_match_ratio: float = 0.5
    max_retake_bridge_s: float = 1.0   # bridge sub-second gaps between consecutive retake
                                       # ranges of the same cluster (failed-take fragments
                                       # stranded by n-gram anchor misalignment)
    max_retake_span_s: float = 60.0    # max duration of a single retake cut (the failed
                                       # take's own length); decoupled from max_retake_gap_s,
                                       # which bounds only the silence between takes
    min_reword_overlap: float = 0.6    # sentence-overlap retake pass: a sentence is a failed
                                       # take if a later sentence repeats at least this fraction
                                       # of its (stopword-filtered) content words. Catches
                                       # REWORDED takes the literal n-gram matcher misses.
    min_reword_content_words: int = 3  # min stopword-filtered content words a sentence needs
                                       # before the overlap pass will consider it (guards short
                                       # sentences whose few common words overlap coincidentally)
    detect_aborted_restarts: bool = True  # third retake pass: cut a short opener that trails off
                                          # ('...') and is immediately re-said from the same prefix
                                          # ("It's called Amazon… It's called Magic Pocket…") — too
                                          # short to seed the n-gram pass, too little content overlap
                                          # for the reworded pass
    mid_sentence_cut_floor_ms: int = 3000
    sentence_pause_s: float = 0.4           # sentence-boundary recovery: when Whisper omits a full
                                            # stop, a capitalised next word preceded by a pause >= this
                                            # is treated as a sentence end. Drives caption line breaks
                                            # and EDL cut permission. Lower = more boundaries (riskier
                                            # false splits at mid-sentence proper nouns); higher = fewer.
    min_word_confidence: float = 0.5        # gap cut hard floor: if either adjacent word's alignment
                                            # confidence is below this, the gap is never cut regardless
                                            # of duration.
    min_retrans_word_confidence: float = 0.35  # retranscription acceptance floor: words returned by a
                                               # retranscription window are dropped if their confidence
                                               # is below this. Lower than min_word_confidence because
                                               # retranscribed clips are short and Whisper confidence
                                               # scores are systematically lower on short audio.
    retrans_rescue_floor: float = 0.05        # rescue floor: a retranscribed word below
                                               # min_retrans_word_confidence is kept if the original
                                               # pass found the same word at or above this confidence.
                                               # Two passes agreeing on a word is corroborating evidence
                                               # even when both scores are low (e.g. sub-clip boundaries).
    retrans_regression_margin: float = 0.20   # regression guard: when both passes return the same word
                                               # count, a retranscribed word whose confidence falls this
                                               # far below the original at the same position is reverted
                                               # to the original word. Short sub-clips lack the context
                                               # Whisper needs, so it can turn a confident word into a
                                               # different, weaker one. Raise to trust retranscription
                                               # more; lower to revert more aggressively.
    low_confidence_threshold: float = 0.8
    low_confidence_min_gap_ms: int = 500
    preserve_start_s: float = 0.0
    preserve_end_s: float = 0.0


class ZoomConfig(BaseModel):
    # Per-hook centered crop-zoom, deterministically seeded by output filename. A subtle
    # per-variant fingerprint experiment — NOT a proven Instagram dedup lever (SSCD sees
    # through it). `min`/`max` are the fraction of frame kept (0.96 = zoom in 4%).
    enabled: bool = False
    min: float = 0.96
    max: float = 1.0


class FlipConfig(BaseModel):
    # Horizontally mirrors the camera image. The flip is applied to the footage BEFORE the
    # caption / title-card / image overlay is composited, so burned-in text is never mirrored —
    # only what the camera saw (which does mirror anything physically in shot: on-screen text
    # behind you, a logo on a shirt, which hand you gesture with).
    #
    # `mode` — which hooks get a flipped render:
    #   "off"       no flipping (default)
    #   "alternate" every second hook (hooks 2, 4, 6…) — 3 hooks → the middle one flipped
    #   "all"       every hook
    # `apply` — what a flipped render does to the output set:
    #   "in_place"  the hook's one video IS the flipped one (3 hooks → 3 videos)
    #   "duplicate" the hook also gets an extra flipped file (3 hooks + mode:all → 6 videos)
    #
    # NOT a proven Instagram dedup lever: SSCD is explicitly trained on horizontal flips, so a
    # mirrored copy still matches its original (INSTAGRAM_DEDUP_EVASION_PLAN.md, technique #4).
    mode: Literal["off", "alternate", "all"] = "off"
    apply: Literal["in_place", "duplicate"] = "duplicate"
    suffix: str = "-flipped"   # appended to the filename of *duplicate* flipped outputs only

    @field_validator("mode", mode="before")
    @classmethod
    def _yaml_off_is_false(cls, v):
        return "off" if v is False else v  # bare `mode: off` parses as the YAML boolean False


class EncodeVariationConfig(BaseModel):
    # Per-hook encoder settings, deterministically seeded by output filename, so the three
    # hooks are distinct *files* (different bitstream, different hash). Tier 0 render
    # hygiene from INSTAGRAM_DEDUP_EVASION_PLAN.md: this defeats naive file/perceptual-hash
    # clustering only. It is NOT a content-matching lever — measured jitter/crop results in
    # that doc show SSCD and audio fingerprinting are unaffected by this class of change.
    # Kept because it is free and touches nothing but the encoder.
    enabled: bool = True
    crf_jitter: int = 1          # libx264: +/- CRF steps around the x264 default (23)
    bitrate_jitter: float = 0.08  # videotoolbox: +/- fraction of the 8000k base bitrate


class OutputConfig(BaseModel):
    format: str = "9:16"
    resolution: list[int] = Field(default=[1080, 1920])
    fps: int = 30
    codec: str = "h264"
    audio_bitrate: str = "128k"
    max_duration_s: int = 90
    location: str = "./output/"
    render_workers: int = 8
    zoom: ZoomConfig = Field(default_factory=ZoomConfig)
    encode_variation: EncodeVariationConfig = Field(default_factory=EncodeVariationConfig)
    flip: FlipConfig = Field(default_factory=FlipConfig)

    @field_validator("resolution")
    @classmethod
    def must_be_two_ints(cls, v: list[int]) -> list[int]:
        if len(v) != 2:
            raise ValueError("resolution must be a list of exactly 2 integers [width, height]")
        if any(x < 320 for x in v):
            raise ValueError("resolution width and height must each be at least 320 pixels")
        return v


class CaptionsConfig(BaseModel):
    enabled: bool = True
    style: Literal["word_highlight", "full_line", "none"] = "word_highlight"
    font: str = "Inter"
    size: int = 72
    color: str = "#FFFFFF"
    highlight_color: str = "#FFD700"
    position: Literal["top", "center", "bottom"] = "center"
    stroke: bool = True
    stroke_color: str = "#000000"
    stroke_width: int = 8            # thick black outline (CapCut/Reels look)
    margin_pct: float = 8.0  # % of video width kept free on each side (left + right)
    words_per_line: int = 7  # max words shown on screen at once
    line_spacing: int = 10           # px between wrapped rows
    shadow: bool = True              # soft blurred drop shadow behind text (for depth)
    shadow_color: str = "#000000"
    shadow_offset: int = 5           # vertical drop of the soft shadow (px)
    shadow_blur: int = 8             # gaussian blur radius of the soft shadow (px)
    shadow_opacity: float = 0.5      # 0-1 opacity of the soft shadow
    grace_s: float = 0.3             # seconds a caption line stays visible after its last word ends


class ImagesConfig(BaseModel):
    enabled: bool = False
    auto_detect: bool = True           # match all transcript words against logos manifest
    require_capitalized: bool = True   # only auto-detect words Whisper capitalized (proper-noun signal)
    keywords: list[str] = []           # explicit logo slugs to always match regardless of capitalization
    exclude: list[str] = []            # logo slugs to never match
    position: Literal["top", "center", "bottom"] = "top"
    logo_overlay_size_pct: float = 25.0  # logo width as % of video width
    overlay_size_pct: float = 50.0     # person/screenshot/concept width as % of video width
    figure_overlay_size_pct: float = 66.0  # figure (article chart/diagram) card width as % of video width
    display_duration_s: float = 2.0
    fade_duration_s: float = 0.25
    start_delay_s: float = 0.1         # image overlays won't appear before this time so they flash on rather than look frozen from frame 0
    margin_pct: float = 5.0            # % of video height from edge to logo
    corner_drop_pct: float = 6.0       # extra % of video height to lower displaced (corner) images



class HeadingsConfig(BaseModel):
    enabled: bool = True
    default_end_s: float = 3.0               # end time (s) written into the auto-created headings.json stub; -1 = until end of video
    full_video: bool = False                 # render-hooks: keep the hook's title card up for the whole video (hook + body) instead of just the hook
    font: str = "PlayfairDisplay"            # bundled in reelcut/fonts/
    subtitle_font: str = "PlayfairDisplay-Italic"
    title_size: int = 96
    subtitle_size: int = 46
    margin_pct: float = 8.0                   # % of video width kept free on each side; title wraps/shrinks to fit
    color: str = "#F3C84E"                   # warm gold (sampled from reference)
    subtitle_color: str = "#FFFFFF"
    position: Literal["top", "upper-third", "center"] = "upper-third"
    shadow: bool = True                      # soft blurred drop shadow for legibility
    shadow_blur: int = 10
    shadow_opacity: float = 0.55
    scrim: bool = True                       # dark gradient behind text (per-heading overridable)
    scrim_strength: int = 150                # max scrim darkness at the very top (0-255 alpha)


class WhisperConfig(BaseModel):
    model: str = "medium"
    compute_type: Literal["int8", "float16", "float32"] = "int8"
    language: str = "en"
    beam_size: int = 1  # 1 = greedy (fastest); 5 = default beam search (more accurate)
    initial_prompt: str | None = None
    condition_on_previous_text: bool = False
    min_alignment_confidence: float = 0.1
    no_speech_threshold: float = 0.6
    retranscribe_no_speech_threshold: float = 0.3
    wide_word_threshold_s: float = 1.5
    retranscribe_low_conf_gap_ms: int = 1000
    retranscribe_large_gap_ms: int = 1500
    retranscribe_low_conf_gap_floor_ms: int = 350  # a low-conf word preceded by a gap this
                                                    # large extends its window back across the gap
                                                    # (catches dropped speech below the large-gap floor)
    retranscribe_merge_gap_s: float = 1.0  # bridge gaps between adjacent retranscription windows
    compression_ratio_threshold: float | None = 2.4
    retranscribe_compression_ratio_threshold: float | None = 2.4

    @field_validator("compute_type")
    @classmethod
    def float16_requires_gpu(cls, v: str) -> str:
        if v == "float16":
            try:
                import torch
                if not torch.cuda.is_available():
                    raise ValueError(
                        "compute_type 'float16' requires a CUDA GPU, but none is available. "
                        "Use 'int8' or 'float32' instead."
                    )
            except ImportError:
                raise ValueError(
                    "compute_type 'float16' requires torch with CUDA support."
                )
        return v


class AssetsConfig(BaseModel):
    location: str = "./assets"


class AudioTrack(BaseModel):
    """A background track — a source file plus its playback tuning, not its use in any one video."""
    path: str = ""              # audio file; omit to auto-discover from assets/audio/<name>.*
    source_start: float = 0.0   # seconds into the source file to begin playback (skip an intro)
    gain_db: float = 0.0        # baseline manual trim on top of auto-leveling (0 = none)
    slow_pct: float = 0.0       # slow the track down by this % (10 = 10% slower). 0 = original
                                # speed. Pitch drops with the tempo. Max ~50 (atempo floor).


class AudioConfig(BaseModel):
    enabled: bool = True
    default: str = ""         # track name mixed under every video unless overridden in
                              # assets/<slug>/audio.json. "" = no music.
    tracks: dict[str, AudioTrack] = Field(default_factory=dict)  # per-track tuning, keyed by name;
                              # files are auto-discovered from assets/audio/ (stem = name), so add
                              # an entry only to set source_start/gain_db (or an explicit path).
    ducking_lufs: float = 18.0  # how far (LUFS) music sits below the measured voice loudness.
                                # Higher = quieter music. ~18 keeps speech clearly dominant.

    @field_validator("tracks", mode="before")
    @classmethod
    def _empty_tracks(cls, v):
        return v or {}  # `tracks:` with only commented-out entries parses to None


class ReelCutConfig(BaseModel):
    cuts: CutsConfig = Field(default_factory=CutsConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    assets: AssetsConfig = Field(default_factory=AssetsConfig)
    captions: CaptionsConfig = Field(default_factory=CaptionsConfig)
    images: ImagesConfig = Field(default_factory=ImagesConfig)
    headings: HeadingsConfig = Field(default_factory=HeadingsConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    whisper: WhisperConfig = Field(default_factory=WhisperConfig)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load_config(path: str | Path) -> ReelCutConfig:
    """Load and validate a YAML config file. Raises with clear messages on error."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open() as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"Config file must be a YAML mapping, got {type(raw).__name__}")

    try:
        return ReelCutConfig.model_validate(raw)
    except Exception as exc:
        raise ValueError(f"Invalid config ({path}):\n{exc}") from exc

