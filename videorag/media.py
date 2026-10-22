"""Audio extraction, keyframe detection and frame grabbing (OpenCV + the ffmpeg bundled by imageio-ffmpeg)."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import cv2
import imageio_ffmpeg
import numpy as np

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def duration(video: Path) -> float:
    cap = cv2.VideoCapture(str(video))
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        return float(frames / fps) if frames else 0.0
    finally:
        cap.release()


def extract_audio(video: Path, out_wav: Path) -> Path:
    """16 kHz mono WAV, the format Whisper expects."""
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = [FFMPEG, "-y", "-loglevel", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", str(out_wav)]
    subprocess.run(cmd, check=True)
    return out_wav


@dataclass
class Keyframe:
    time: float
    path: Path


def _signature(frame: np.ndarray) -> np.ndarray:
    small = cv2.resize(frame, (64, 36), interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)


def _save(frame: np.ndarray, path: Path, max_width: int = 1024) -> None:
    h, w = frame.shape[:2]
    if w > max_width:
        frame = cv2.resize(frame, (max_width, int(h * max_width / w)), interpolation=cv2.INTER_AREA)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 85])


def keyframes(
    video: Path,
    out_dir: Path,
    step: float = 1.0,
    change: float = 0.015,
    min_gap: float = 2.0,
    max_gap: float = 30.0,
    settle: float = 0.5,
    max_frames: int = 80,
) -> list[Keyframe]:
    """One frame per visual change.

    Frames are sampled every `step` seconds; a new keyframe starts when more than `change` (a fraction) of the
    pixels differ noticeably from the last keyframe, or after `max_gap` seconds without one. Counting changed pixels
    instead of averaging the difference catches slide changes where only one line of text appears. Keyframes are at
    least `min_gap` seconds apart (so camera motion does not fire every sample) and capped at `max_frames`, thinned
    evenly, since each one costs a vision call. The saved image is taken `settle` seconds after the change so fades
    and transitions have finished.
    """
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = (cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / fps
    found: list[Keyframe] = []
    last_sig: np.ndarray | None = None
    last_time = -max_gap
    t = 0.0
    try:
        while t < total:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, frame = cap.read()
            if not ok:
                break
            sig = _signature(frame)
            changed = last_sig is None or float((np.abs(sig - last_sig) > 20).mean()) > change
            is_new = changed and (last_sig is None or t - last_time >= min_gap)
            if is_new or t - last_time >= max_gap:
                shot_t = min(t + settle, max(total - 0.1, t)) if is_new and last_sig is not None else t
                cap.set(cv2.CAP_PROP_POS_MSEC, shot_t * 1000)
                ok2, shot = cap.read()
                frame = shot if ok2 else frame
                path = out_dir / f"kf_{len(found):03d}_{int(t * 1000):08d}.jpg"
                _save(frame, path)
                found.append(Keyframe(time=round(t, 2), path=path))
                last_sig, last_time = _signature(frame), t
            t += step
    finally:
        cap.release()
    if len(found) > max_frames:
        keep = {round(i * (len(found) - 1) / (max_frames - 1)) for i in range(max_frames)}
        for i, kf in enumerate(found):
            if i not in keep:
                kf.path.unlink(missing_ok=True)
        found = [kf for i, kf in enumerate(found) if i in keep]
    return found


def frame_at(video: Path, seconds: float, out_path: Path) -> Path:
    cap = cv2.VideoCapture(str(video))
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, seconds) * 1000)
        ok, frame = cap.read()
        if not ok:
            raise ValueError(f"no frame at {seconds:.1f}s")
        _save(frame, out_path)
        return out_path
    finally:
        cap.release()
