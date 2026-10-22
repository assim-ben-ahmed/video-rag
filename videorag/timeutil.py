"""Timestamps: seconds <-> "mm:ss", and citations found in answers."""

from __future__ import annotations

import re

CITATION = re.compile(r"\[(\d{1,2}):(\d{2})(?:\s*[–-]\s*(\d{1,2}):(\d{2}))?\]")


def fmt(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def fmt_span(start: float, end: float | None = None) -> str:
    if end is None or int(round(end)) <= int(round(start)):
        return f"[{fmt(start)}]"
    return f"[{fmt(start)}–{fmt(end)}]"


def parse(value: str | float | int) -> float:
    """Accepts 83, 83.5, "83", "1:23" or "01:23"."""
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().strip("[]")
    if ":" in text:
        minutes, secs = text.split(":", 1)
        return int(minutes) * 60 + float(secs)
    return float(text)


def citations(answer: str) -> list[tuple[float, float]]:
    """Every [mm:ss] or [mm:ss–mm:ss] in an answer, as (start, end) seconds."""
    spans = []
    for m in CITATION.finditer(answer):
        start = int(m.group(1)) * 60 + int(m.group(2))
        end = int(m.group(3)) * 60 + int(m.group(4)) if m.group(3) else start
        spans.append((float(start), float(end)))
    return spans
