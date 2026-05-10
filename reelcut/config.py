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
    word_end_scan_ms: int = 50
    breath_amplitude_ratio: float = 0.15
    failure_tolerance_ratio: float = 0.02
    min_keep_ms: int = 50
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
    initial_prompt: str | None = None
    condition_on_previous_text: bool = False
    min_alignment_confidence: float = 0.1

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

