"""Centralized environment-backed configuration."""

from functools import lru_cache
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


class Settings:
    """Application settings; secrets must be supplied through the environment."""

    def __init__(self) -> None:
        self.google_api_key = os.getenv("GOOGLE_API_KEY", "").strip()
        self.jwt_secret = os.getenv("JWT_SECRET", "").strip()
        self.jwt_algorithm = "HS256"
        self.access_token_minutes = _int_env("ACCESS_TOKEN_MINUTES", 60)
        self.database_path = Path(os.getenv("DATABASE_PATH", str(PROJECT_ROOT / "db" / "users.db")))
        self.chroma_path = Path(os.getenv("CHROMA_PATH", str(PROJECT_ROOT / "db" / "chroma")))
        self.upload_path = Path(os.getenv("UPLOAD_PATH", str(PROJECT_ROOT / "data" / "uploads")))
        self.max_upload_bytes = _int_env("MAX_UPLOAD_MB", 25) * 1024 * 1024
        self.chunk_size = _int_env("CHUNK_SIZE", 900)
        self.chunk_overlap = _int_env("CHUNK_OVERLAP", 120)
        self.retrieval_k = _int_env("RETRIEVAL_K", 5)
        # Use a currently supported Gemini model by default; callers can override it via .env.
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
        self.embedding_model = os.getenv("GOOGLE_EMBEDDING_MODEL", "models/gemini-embedding-001")
        self.api_base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
        if self.chunk_size < 1 or self.chunk_overlap < 0 or self.chunk_overlap >= self.chunk_size:
            raise RuntimeError("CHUNK_SIZE must be positive and CHUNK_OVERLAP must be non-negative and smaller than CHUNK_SIZE")

    def validate_auth(self) -> None:
        if not self.jwt_secret or len(self.jwt_secret) < 32:
            raise RuntimeError("Set JWT_SECRET to a random value of at least 32 characters.")

    def validate_ai(self) -> None:
        if not self.google_api_key:
            raise RuntimeError("Set GOOGLE_API_KEY in your .env file to enable indexing and chat.")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
