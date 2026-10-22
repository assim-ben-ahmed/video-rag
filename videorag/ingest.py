"""Video → searchable index: audio → Whisper → speech chunks; keyframes → vision descriptions; embed everything."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable

from . import media
from .index import Doc, VideoIndex
from .llm import MistralClient
from .transcribe import chunk, transcribe

Progress = Callable[[str, float, str], None]

CAPTION_PROMPT = (
    "You are indexing a video frame for search. Describe what is shown in 2-4 sentences. "
    "Transcribe every visible word, number, label, price, date and chart value exactly as written. "
    "Mention colours and objects that someone might ask about. No preamble."
)


def _noop(stage: str, fraction: float, message: str) -> None:
    pass


def ingest(
    video: Path,
    workdir: Path,
    llm: MistralClient,
    whisper_model: str = "base",
    progress: Progress = _noop,
) -> VideoIndex:
    """Builds and saves the index for `video` into `workdir`; returns it."""
    t0 = time.perf_counter()
    workdir.mkdir(parents=True, exist_ok=True)
    total = media.duration(video)

    progress("audio", 0.05, "Extracting the audio track")
    wav = media.extract_audio(video, workdir / "audio.wav")

    progress("transcribe", 0.15, f"Transcribing speech locally (Whisper {whisper_model})")
    segments, language = transcribe(wav, whisper_model)
    chunks = chunk(segments)
    wav.unlink(missing_ok=True)

    progress("keyframes", 0.45, "Finding keyframes (one per visual change)")
    frames = media.keyframes(video, workdir / "frames")

    docs = [Doc(f"s{i}", "speech", c.start, c.end, c.text) for i, c in enumerate(chunks)]
    for i, kf in enumerate(frames):
        progress("vision", 0.5 + 0.35 * i / max(1, len(frames)), f"Describing keyframe {i + 1}/{len(frames)}")
        caption = llm.describe_image(kf.path, CAPTION_PROMPT)
        end = frames[i + 1].time if i + 1 < len(frames) else total
        docs.append(Doc(f"v{i}", "screen", kf.time, end, caption, frame=kf.path.name))

    progress("index", 0.9, f"Embedding {len(docs)} passages")
    index = VideoIndex.build(docs, llm.embed)
    index.save(workdir)

    manifest = {
        "video": video.name,
        "duration": round(total, 2),
        "language": language,
        "segments": [s.__dict__ for s in segments],
        "speech_chunks": len(chunks),
        "keyframes": [{"time": f.time, "file": f.path.name} for f in frames],
        "ingest_seconds": round(time.perf_counter() - t0, 1),
    }
    (workdir / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    progress("ready", 1.0, "Ready")
    return index
