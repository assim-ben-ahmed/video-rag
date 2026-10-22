"""API input validation (no API key needed: these paths never reach the model)."""

from fastapi.testclient import TestClient

from videorag.app import app

client = TestClient(app)


def test_health():
    body = client.get("/api/health").json()
    assert body["ok"] is True and "key_configured" in body


def test_rejects_non_video_upload():
    r = client.post("/api/videos", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert r.status_code == 400


def test_unknown_or_malicious_ids_are_404():
    assert client.get("/api/videos/does-not-exist").status_code == 404
    assert client.get("/api/videos/..%2F..%2Fetc").status_code == 404
    assert client.get("/api/videos/demo/frames/..%2F..%2F.env").status_code == 404


def test_ask_validates_mode():
    r = client.post("/api/videos/abc/ask", json={"question": "hi", "mode": "magic"})
    assert r.status_code == 400


def test_frontend_is_served():
    r = client.get("/")
    assert r.status_code == 200 and "Video RAG" in r.text


# ── public-mode limits ───────────────────────────────────────────────────────

from dataclasses import replace  # noqa: E402

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

import videorag.app as app_module  # noqa: E402


def test_too_long_video_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "settings", replace(app_module.settings, data_dir=tmp_path, max_video_seconds=2))
    path = tmp_path / "long.mp4"
    out = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (64, 64))
    for _ in range(50):  # 5 s
        out.write(np.zeros((64, 64, 3), np.uint8))
    out.release()
    r = client.post("/api/videos", files={"file": ("long.mp4", path.read_bytes(), "video/mp4")})
    assert r.status_code == 413 and "too long" in r.json()["detail"]
    assert not any((tmp_path / "videos").iterdir())  # nothing left behind


class _Req:
    def __init__(self, ip):
        self.headers, self.client = {"x-forwarded-for": ip}, None


def test_questions_are_rate_limited_per_visitor(monkeypatch):
    monkeypatch.setattr(app_module, "settings", replace(app_module.settings, questions_per_hour=2))
    app_module._asked.clear()
    app_module._check_rate(_Req("1.1.1.1"))
    app_module._check_rate(_Req("1.1.1.1"))
    with pytest.raises(HTTPException) as exc:
        app_module._check_rate(_Req("1.1.1.1"))
    assert exc.value.status_code == 429
    app_module._check_rate(_Req("2.2.2.2"))  # other visitors are not affected
