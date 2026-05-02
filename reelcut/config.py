"""Config loader — YAML schema, validation, and default config generation."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class InputConfig(BaseModel):
    footage: str
    script: str | None = None   # optional — omit for scriptless silence-removal mode
    clips_folder: str | None = None


class CutsConfig(BaseModel):
    min_silence_ms: int = 100
    min_breath_ms: int = 60
    breath_detection: bool = True
    silence_threshold_db: float = -40.0
    vad_threshold: float = 0.5
    speech_pad_ms: int = 80
    # Relative amplitude ceiling for breath classification: a gap is only treated
    # as a breath if its RMS is below this fraction of the track's peak amplitude.
    # Prevents loud noise bursts from being misclassified as breaths.
    breath_amplitude_ratio: float = 0.15
    # Failure tolerance (jumpcutter-style): if fewer than this fraction of samples
    # in a gap exceed the absolute noise floor, classify the whole gap as silence
    # even if a single transient spike raises the RMS. Prevents fragmentation.
    failure_tolerance_ratio: float = 0.02
    # Drop keep segments shorter than this after cuts are applied. Prevents
    # sub-word fragments (clicks, partial phonemes) from becoming isolated clips.
    # Adjacent cuts around a dropped segment are merged into one.
    min_keep_ms: int = 50
    # Minimum phrase length (in words) for duplicate-take detection. Repeated
    # sequences shorter than this are ignored to avoid cutting naturally repeated
    # short phrases (e.g. "you know", "I think"). Set to 0 to disable entirely.
    min_retake_words: int = 0


class OutputConfig(BaseModel):
    format: str = "9:16"
    resolution: list[int] = Field(default=[1080, 1920])
    fps: int = 30
    codec: str = "h264"
    audio_bitrate: str = "128k"
    max_duration_s: int = 90
    location: str = "./output/"
    render_workers: int = 8

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
    font: str = "Montserrat-Bold"
    size: int = 72
    color: str = "#FFFFFF"
    highlight_color: str = "#FFD700"
    position: Literal["top", "center", "bottom"] = "center"
    stroke: bool = True
    stroke_color: str = "#000000"
    stroke_width: int = 3


class WhisperConfig(BaseModel):
    model: str = "medium"
    compute_type: Literal["int8", "float16", "float32"] = "int8"
    language: str = "en"
    beam_size: int = 1  # 1 = greedy (fastest); 5 = default beam search (more accurate)

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


class ReelCutConfig(BaseModel):
    input: InputConfig
    cuts: CutsConfig = Field(default_factory=CutsConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    captions: CaptionsConfig = Field(default_factory=CaptionsConfig)
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


# ---------------------------------------------------------------------------
# Default config
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG = """\
input:
  footage: ./input/                # folder to scan for videos (or single file path)
  # script: ./script.txt           # optional — provide for outtake removal; omit for silence-cut-only mode
  # clips_folder: ./clips/         # optional, for multi-clip

cuts:
  min_silence_ms: 100              # cut gaps longer than this
  min_breath_ms: 60                # cut breaths longer than this
  breath_detection: true
  silence_threshold_db: -40        # -40 catches typical room noise; raise if over-cutting
  vad_threshold: 0.5
  speech_pad_ms: 80                # ms kept before each word on a cut (raise for more breathing room)
  breath_amplitude_ratio: 0.15     # breath RMS must be < 15% of track peak
  failure_tolerance_ratio: 0.02    # allow 2% of samples to spike above noise floor
  min_keep_ms: 50                  # drop keep segments shorter than this (ms)
  min_retake_words: 4              # duplicate-take detection: min words in a repeated phrase (0 = off)

output:
  format: "9:16"
  resolution: [1080, 1920]
  fps: 30
  codec: h264
  audio_bitrate: 128k
  max_duration_s: 90
  location: ./output/
  render_workers: 8                # parallel segment extraction workers

captions:
  enabled: true
  style: word_highlight            # word_highlight | full_line | none
  font: Montserrat-Bold
  size: 72
  color: "#FFFFFF"
  highlight_color: "#FFD700"
  position: center                 # top | center | bottom
  stroke: true
  stroke_color: "#000000"
  stroke_width: 3

whisper:
  model: medium                    # medium (4-5× faster than large-v2, minimal quality loss)
  compute_type: int8               # int8 (CPU) | float16 (GPU)
  language: en
  beam_size: 1                     # 1 = greedy/fastest; 5 = beam search/more accurate
"""


def generate_default_config(dest: str | Path = "config.yaml") -> Path:
    """Write a default config.yaml to dest. Raises if file already exists."""
    dest = Path(dest)
    if dest.exists():
        raise FileExistsError(f"{dest} already exists. Delete it or choose a different path.")
    dest.write_text(_DEFAULT_CONFIG)
    return dest
