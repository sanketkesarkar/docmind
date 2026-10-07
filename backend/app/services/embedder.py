import hashlib
import random
import time
from google import genai
from google.genai import types
from app.config import settings

client = genai.Client(
    api_key=settings.GEMINI_API_KEY,
    http_options={"api_version": "v1"},
)

EMBEDDING_MODEL = "gemini-embedding-001"
MAX_RETRIES = 3
RETRY_DELAY = 2


def _fake_embedding(text: str) -> list[float]:
    if settings.FAKE_EMBED_DELAY_MS:
        time.sleep(settings.FAKE_EMBED_DELAY_MS / 1000)
    rng = random.Random(hashlib.sha256(text.encode()).digest())
    return [rng.uniform(-1, 1) for _ in range(3072)]


def embed_text(text: str) -> list[float]:
    if settings.FAKE_EMBEDDINGS:
        return _fake_embedding(text)
    for attempt in range(MAX_RETRIES):
        try:
            result = client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=text,
                config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT", output_dimensionality=3072),
            )
            return result.embeddings[0].values
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
            else:
                raise RuntimeError(f"Embedding failed after {MAX_RETRIES} attempts: {e}")
