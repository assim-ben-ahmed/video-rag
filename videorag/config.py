"""Settings, read from environment variables (a local .env file is loaded if present)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    api_key: str = os.getenv("MISTRAL_API_KEY", "")
    chat_model: str = os.getenv("CHAT_MODEL", "ministral-14b-latest")
    vision_model: str = os.getenv("VISION_MODEL", "ministral-14b-latest")
    embed_model: str = os.getenv("EMBED_MODEL", "mistral-embed")
    whisper_model: str = os.getenv("WHISPER_MODEL", "small")
    data_dir: Path = Path(os.getenv("DATA_DIR", ROOT / "data"))
    agent_max_steps: int = int(os.getenv("AGENT_MAX_STEPS", "5"))

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def videos_dir(self) -> Path:
        return self.data_dir / "videos"


settings = Settings()
