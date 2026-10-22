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
