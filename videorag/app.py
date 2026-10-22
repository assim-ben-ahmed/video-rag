"""Web app: upload a video, follow its processing, then chat with it.

    uvicorn videorag.app:app --port 8000      ->  http://localhost:8000
"""

from __future__ import annotations

import json
import re
import shutil
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .answer import MODES, Answerer
from .config import ROOT, settings
from .index import VideoIndex
from .ingest import ingest
from .llm import LLMError, from_settings

ALLOWED = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
MAX_BYTES = 500 * 1024 * 1024
DEMO_VIDEO = ROOT / "demo" / "rooftop-bees.mp4"

app = FastAPI(title="Video RAG")
_status: dict[str, dict] = {}
_answerers: dict[str, Answerer] = {}
_lock = threading.Lock()
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
    try:
        ingest(
            _video_file(folder), folder, llm(), settings.whisper_model,
            progress=lambda stage, frac, msg: _set(video_id, stage=stage, progress=round(frac, 3), message=msg),
        )
    except Exception as exc:  # surfaced to the UI
        _set(video_id, stage="error", message=str(exc)[:300])


def _info(video_id: str) -> dict:
    folder = _dir(video_id)
    manifest_path = folder / "manifest.json"
    if manifest_path.exists():
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
        return {
            "id": video_id, "stage": "ready", "progress": 1.0, "name": (folder / "name.txt").read_text(encoding="utf-8") if (folder / "name.txt").exists() else m["video"],
            "duration": m["duration"], "language": m["language"], "keyframes": m["keyframes"],
            "segments": m["segments"],
        }
    if video_id in _status:
        return {"id": video_id, **_status[video_id]}
    if folder.exists():
        return {"id": video_id, "stage": "error", "message": "Processing was interrupted. Upload the video again."}
    raise HTTPException(404, "Unknown video")


# ── API ──────────────────────────────────────────────────────────────────────


@app.get("/api/health")
def health():
    return {"ok": True, "key_configured": bool(settings.api_key), "chat_model": settings.chat_model}


@app.post("/api/videos")
async def upload(file: UploadFile = File(...)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED:
        raise HTTPException(400, f"Unsupported format {ext or '(none)'}; use {', '.join(sorted(ALLOWED))}")
    video_id = uuid.uuid4().hex[:12]
    folder = _dir(video_id)
    folder.mkdir(parents=True)
    size = 0
    with open(folder / f"video{ext}", "wb") as out:
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            if size > MAX_BYTES:
                out.close()
                shutil.rmtree(folder, ignore_errors=True)
                raise HTTPException(413, "Video too large (500 MB max)")
            out.write(chunk)
    (folder / "name.txt").write_text(Path(file.filename or "video").name, encoding="utf-8")
    _set(video_id, stage="queued", progress=0.0, message="Queued", name=file.filename)
    threading.Thread(target=_run_ingest, args=(video_id,), daemon=True).start()
    return {"id": video_id}


@app.post("/api/demo")
def demo():
    """Indexes the bundled demo video once, then reuses it."""
    if not DEMO_VIDEO.exists():
        raise HTTPException(404, "Demo video missing: run python scripts/make_demo_video.py")
    folder = _dir("demo")
    folder.mkdir(parents=True, exist_ok=True)
    if not list(folder.glob("video.*")):
        shutil.copy(DEMO_VIDEO, folder / "video.mp4")
    (folder / "name.txt").write_text("Rooftop Beekeeping (demo)", encoding="utf-8")
    if not (folder / "manifest.json").exists() and _status.get("demo", {}).get("stage") not in ("queued", "audio", "transcribe", "keyframes", "vision", "index"):
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
def ask(video_id: str, q: Question):
    if q.mode not in MODES:
        raise HTTPException(400, f"mode must be one of {MODES}")
    if _info(video_id).get("stage") != "ready":
        raise HTTPException(409, "The video is still being processed")
    folder = _dir(video_id)
    if video_id not in _answerers:
        _answerers[video_id] = Answerer(VideoIndex.load(folder), llm(), _video_file(folder), folder, settings.agent_max_steps)
    try:
        return _answerers[video_id].ask(q.question, q.mode).to_dict()
    except LLMError as exc:
        raise HTTPException(502, str(exc)) from exc


app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")
