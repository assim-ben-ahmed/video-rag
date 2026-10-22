"""Local speech-to-text with faster-whisper, then time-aligned chunks for retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Segment:
    start: float
    end: float
    text: str


def transcribe(audio: Path, model_size: str = "base") -> tuple[list[Segment], str]:
    """Returns the Whisper segments and the detected language. Runs on CPU (int8)."""
    from faster_whisper import WhisperModel  # heavy import, only when needed

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(audio), vad_filter=True, beam_size=5)
    out = [Segment(round(s.start, 2), round(s.end, 2), s.text.strip()) for s in segments if s.text.strip()]
    return out, info.language


def chunk(segments: list[Segment], target: float = 15.0, overlap: int = 1) -> list[Segment]:
    """Groups consecutive segments into ~`target`-second chunks.

    The last `overlap` segment(s) of a chunk are repeated at the start of the next one, so a sentence that
    straddles a boundary can still be retrieved whole.
    """
    chunks: list[Segment] = []
    current: list[Segment] = []
    for seg in segments:
        current.append(seg)
        if current[-1].end - current[0].start >= target:
            chunks.append(_merge(current))
            current = current[-overlap:] if overlap else []
    if current and (not chunks or current[-1].end > chunks[-1].end):
        chunks.append(_merge(current))
    return chunks


def _merge(segs: list[Segment]) -> Segment:
    return Segment(segs[0].start, segs[-1].end, " ".join(s.text for s in segs))
