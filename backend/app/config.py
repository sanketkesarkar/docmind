from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    GEMINI_API_KEY: str
    DATABASE_URL: str = "postgresql://docmind:docmind@localhost:5432/docmind"
    REDIS_URL: str = "redis://localhost:6379"
    STORAGE_PATH: str = "/storage"

    class Config:
        env_file = ".env"


settings = Settings()
