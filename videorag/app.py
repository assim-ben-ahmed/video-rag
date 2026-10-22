"""Web app: upload a video, follow its processing, then chat with it.

    uvicorn videorag.app:app --port 8000      ->  http://localhost:8000

With PUBLIC_MODE=1 (the Hugging Face Space) uploads are capped in size and duration, videos are processed one at
a time, and each visitor gets a limited number of questions per hour, so a public link cannot drain the API quota.
"""

from __future__ import annotations

import json
import re
import shutil
import threading
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import media
from .answer import MODES, Answerer
from .config import ROOT, settings
from .index import VideoIndex
from .ingest import ingest
from .llm import LLMError, from_settings

ALLOWED = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
DEMO_VIDEO = ROOT / "demo" / "rooftop-bees.mp4"
DEMO_INDEX = ROOT / "demo" / "index"  # prebuilt, so the demo opens instantly
BUSY = ("queued", "audio", "transcribe", "keyframes", "vision", "index")

app = FastAPI(title="Video RAG")
_status: dict[str, dict] = {}
_answerers: dict[str, Answerer] = {}
_lock = threading.Lock()
_ingest_slot = threading.Semaphore(1)  # Whisper + vision on a small CPU: one video at a time
_asked: dict[str, deque] = defaultdict(deque)
_llm = None


def llm():
    global _llm
    if _llm is None:
        _llm = from_settings(settings)
    return _llm


def _dir(video_id: str) -> Path:
    if not re.fullmatch(r"[a-z0-9-]{1,40}", video_id):
        raise HTTPException(404, "Unknown video")
    return settings.videos_dir / video_id


def _video_file(folder: Path) -> Path:
    for p in folder.glob("video.*"):
        return p
    raise HTTPException(404, "Video file missing")


def _set(video_id: str, **kw) -> None:
    with _lock:
        _status.setdefault(video_id, {}).update(kw)


def _run_ingest(video_id: str) -> None:
    folder = _dir(video_id)
    if not _ingest_slot.acquire(blocking=False):
        _set(video_id, stage="queued", message="Waiting for another video to finish processing")
        _ingest_slot.acquire()
    try:
        ingest(
            _video_file(folder), folder, llm(), settings.whisper_model,
            progress=lambda stage, frac, msg: _set(video_id, stage=stage, progress=round(frac, 3), message=msg),
        )
    except Exception as exc:  # surfaced to the UI
        _set(video_id, stage="error", message=str(exc)[:300])
    finally:
        _ingest_slot.release()


def _info(video_id: str) -> dict:
    folder = _dir(video_id)
    manifest_path = folder / "manifest.json"
    if manifest_path.exists():
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
        name_file = folder / "name.txt"
        return {
            "id": video_id, "stage": "ready", "progress": 1.0,
            "name": name_file.read_text(encoding="utf-8") if name_file.exists() else m["video"],
            "duration": m["duration"], "language": m["language"], "keyframes": m["keyframes"],
            "segments": m["segments"],
        }
    if video_id in _status:
        return {"id": video_id, **_status[video_id]}
    if folder.exists():
        return {"id": video_id, "stage": "error", "message": "Processing was interrupted. Upload the video again."}
    raise HTTPException(404, "Unknown video")


def _client(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")


def _check_rate(request: Request) -> None:
    if not settings.questions_per_hour:
        return
    now, window = time.time(), _asked[_client(request)]
    while window and now - window[0] > 3600:
        window.popleft()
    if len(window) >= settings.questions_per_hour:
        wait = int(3600 - (now - window[0])) // 60 + 1
        raise HTTPException(429, f"Question limit reached on this public demo; try again in {wait} min.")
    window.append(now)


# ── API ──────────────────────────────────────────────────────────────────────


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "key_configured": bool(settings.api_key),
        "chat_model": settings.chat_model,
        "public_mode": settings.public_mode,
        "max_upload_mb": settings.max_upload_mb,
        "max_video_seconds": settings.max_video_seconds,
    }


@app.post("/api/videos")
async def upload(file: UploadFile = File(...)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED:
        raise HTTPException(400, f"Unsupported format {ext or '(none)'}; use {', '.join(sorted(ALLOWED))}")
    video_id = uuid.uuid4().hex[:12]
    folder = _dir(video_id)
    folder.mkdir(parents=True)
    limit, size = settings.max_upload_mb * 1024 * 1024, 0
    path = folder / f"video{ext}"
    with open(path, "wb") as out:
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            if size > limit:
                out.close()
                shutil.rmtree(folder, ignore_errors=True)
                raise HTTPException(413, f"Video too large ({settings.max_upload_mb} MB max)")
            out.write(chunk)
    seconds = media.duration(path)
    if seconds <= 0:
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(400, "Could not read this video file")
    if settings.max_video_seconds and seconds > settings.max_video_seconds:
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(413, f"Video too long ({seconds / 60:.1f} min); this demo accepts up to {settings.max_video_seconds // 60} min")
    (folder / "name.txt").write_text(Path(file.filename or "video").name, encoding="utf-8")
    _set(video_id, stage="queued", progress=0.0, message="Queued", name=file.filename)
    threading.Thread(target=_run_ingest, args=(video_id,), daemon=True).start()
    return {"id": video_id}


@app.post("/api/demo")
def demo():
    """Opens the bundled demo: copies the prebuilt index if there is one, otherwise indexes the video once."""
    if not DEMO_VIDEO.exists():
        raise HTTPException(404, "Demo video missing: run python scripts/make_demo_video.py")
    folder = _dir("demo")
    folder.mkdir(parents=True, exist_ok=True)
    if not list(folder.glob("video.*")):
        shutil.copy(DEMO_VIDEO, folder / "video.mp4")
    (folder / "name.txt").write_text("Rooftop Beekeeping (demo)", encoding="utf-8")
    if not (folder / "manifest.json").exists() and (DEMO_INDEX / "manifest.json").exists():
        shutil.copytree(DEMO_INDEX, folder, dirs_exist_ok=True)
    if not (folder / "manifest.json").exists() and _status.get("demo", {}).get("stage") not in BUSY:
        _set("demo", stage="queued", progress=0.0, message="Queued", name="Rooftop Beekeeping (demo)")
        threading.Thread(target=_run_ingest, args=("demo",), daemon=True).start()
    return {"id": "demo"}


@app.get("/api/videos/{video_id}")
def info(video_id: str):
    return _info(video_id)


@app.get("/api/videos/{video_id}/file")
def video_file(video_id: str):
    return FileResponse(_video_file(_dir(video_id)))


@app.get("/api/videos/{video_id}/frames/{name}")
def frame(video_id: str, name: str):
    if not re.fullmatch(r"kf_\d{3}_\d{8}\.jpg", name):
        raise HTTPException(404)
    path = _dir(video_id) / "frames" / name
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path)


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    mode: str = "agentic"


@app.post("/api/videos/{video_id}/ask")
def ask(video_id: str, q: Question, request: Request):
    if q.mode not in MODES:
        raise HTTPException(400, f"mode must be one of {MODES}")
    if _info(video_id).get("stage") != "ready":
        raise HTTPException(409, "The video is still being processed")
    _check_rate(request)
    folder = _dir(video_id)
    if video_id not in _answerers:
        _answerers[video_id] = Answerer(VideoIndex.load(folder), llm(), _video_file(folder), folder, settings.agent_max_steps)
    try:
        return _answerers[video_id].ask(q.question, q.mode).to_dict()
    except LLMError as exc:
        raise HTTPException(502, str(exc)) from exc


app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")
