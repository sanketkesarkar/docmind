from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    GEMINI_API_KEY: str
    DATABASE_URL: str = "postgresql://docmind:docmind@localhost:5432/docmind"
    REDIS_URL: str = "redis://localhost:6379"

    # Test-only: skip Gemini and return deterministic vectors (for load/scaling tests without API quota)
    # Heuristic evidence threshold; calibrate on a labeled question/document set.
    MIN_COSINE_SIMILARITY: float = Field(default=0.5, ge=-1.0, le=1.0)

    FAKE_EMBEDDINGS: bool = False
    FAKE_EMBED_DELAY_MS: int = 0

    # Run CREATE EXTENSION / create_all when the API boots. Disable on Kubernetes,
    # where the migrate Job does it once instead of every replica racing.
    AUTO_INIT_DB: bool = True

    # Storage: "local" (shared volume, docker-compose dev) or "s3" (MinIO / AWS S3)
    STORAGE_BACKEND: str = "local"
    STORAGE_PATH: str = "/storage"
    S3_ENDPOINT_URL: str = ""
    S3_BUCKET: str = "docmind"
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_REGION: str = "us-east-1"

    class Config:
        env_file = ".env"


settings = Settings()
