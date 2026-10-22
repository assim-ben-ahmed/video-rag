"""Small Mistral REST client: chat (with tools), image description and embeddings.

Every response is cached on disk by a hash of the request, so re-running an evaluation or re-opening a video
costs nothing. Rate limits (429) and server errors are retried with backoff.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx
import numpy as np

log = logging.getLogger(__name__)
API = "https://api.mistral.ai/v1"


class LLMError(RuntimeError):
    pass


class MistralClient:
    def __init__(
        self,
        api_key: str,
        chat_model: str,
        vision_model: str,
        embed_model: str,
        cache_dir: Path | None = None,
        timeout: float = 90.0,
        max_retries: int = 6,
    ):
        if not api_key:
            raise LLMError("MISTRAL_API_KEY is not set. Copy .env.example to .env and add your key.")
        self.chat_model, self.vision_model, self.embed_model = chat_model, vision_model, embed_model
        self.cache_dir = cache_dir
        self.max_retries = max_retries
        self.stats = {"api_calls": 0, "cache_hits": 0}
        self._http = httpx.Client(
            base_url=API, timeout=timeout, headers={"Authorization": f"Bearer {api_key}"}
        )

    # ── transport ───────────────────────────────────────────────────────────

    def _cache_path(self, payload: dict) -> Path | None:
        if not self.cache_dir:
            return None
        key = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        return self.cache_dir / key[:2] / f"{key}.json"

    def _post(self, path: str, payload: dict) -> dict:
        cached = self._cache_path({"path": path, **payload})
        if cached and cached.exists():
            self.stats["cache_hits"] += 1
            return json.loads(cached.read_text(encoding="utf-8"))

        delay = 2.0
        for attempt in range(self.max_retries):
            try:
                resp = self._http.post(path, json=payload)
            except httpx.TransportError as exc:
                log.warning("network error (%s), retrying in %.0fs", exc, delay)
                time.sleep(delay)
                delay *= 2
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                wait = float(resp.headers.get("retry-after", delay))
                log.warning("Mistral %s, retrying in %.0fs", resp.status_code, wait)
                time.sleep(wait)
                delay = min(delay * 2, 60)
                continue
            if resp.status_code >= 400:
                raise LLMError(f"Mistral {resp.status_code}: {resp.text[:300]}")
            self.stats["api_calls"] += 1
            data = resp.json()
            if cached:
                cached.parent.mkdir(parents=True, exist_ok=True)
                cached.write_text(json.dumps(data), encoding="utf-8")
            return data
        raise LLMError(f"Mistral still failing after {self.max_retries} attempts ({path})")

    # ── API ─────────────────────────────────────────────────────────────────

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str = "auto",
        temperature: float = 0.0,
        max_tokens: int = 700,
    ) -> dict:
        """Returns the assistant message: {"role", "content", "tool_calls"?}."""
        payload: dict[str, Any] = {
            "model": self.chat_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice
        return self._post("/chat/completions", payload)["choices"][0]["message"]

    def describe_image(self, image_path: Path, prompt: str, max_tokens: int = 300) -> str:
        b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
        payload = {
            "model": self.vision_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": f"data:image/jpeg;base64,{b64}"},
                    ],
                }
            ],
            "temperature": 0.0,
            "max_tokens": max_tokens,
        }
        return (self._post("/chat/completions", payload)["choices"][0]["message"]["content"] or "").strip()

    def embed(self, texts: list[str], batch: int = 32) -> np.ndarray:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), batch):
            data = self._post("/embeddings", {"model": self.embed_model, "input": texts[i : i + batch]})
            vectors.extend(item["embedding"] for item in sorted(data["data"], key=lambda d: d["index"]))
        arr = np.asarray(vectors, dtype=np.float32)
        return arr / np.clip(np.linalg.norm(arr, axis=1, keepdims=True), 1e-9, None)


def from_settings(s) -> MistralClient:
    return MistralClient(s.api_key, s.chat_model, s.vision_model, s.embed_model, cache_dir=s.cache_dir)
