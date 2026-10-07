import logging
import redis
from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from app.config import settings
from app.db.database import init_db, engine
from app.services.storage import ensure_bucket, _s3_client
from app.api.upload import router as upload_router
from app.api.query import router as query_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = FastAPI(title="DocMind", version="0.1.0")

app.include_router(upload_router, prefix="/api/v1", tags=["documents"])
app.include_router(query_router, prefix="/api/v1", tags=["query"])

try:
    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
except ImportError:
    logging.getLogger(__name__).warning("prometheus_fastapi_instrumentator not installed; /metrics disabled")


@app.on_event("startup")
def on_startup():
    if settings.AUTO_INIT_DB:
        init_db()
        ensure_bucket()


@app.get("/health")
@app.get("/healthz")
def health():
    """Liveness: the process is up. No dependency checks, so a DB blip doesn't restart pods."""
    return {"status": "ok"}


@app.get("/readyz")
def ready():
    """Readiness: only receive traffic when Postgres and Redis are reachable."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1 FROM documents LIMIT 1"))
        redis.from_url(settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2).ping()
        if settings.STORAGE_BACKEND == "s3":
            _s3_client().head_bucket(Bucket=settings.S3_BUCKET)
    except Exception as e:
        raise HTTPException(status_code=503, detail="Dependencies or migration not ready")
    return {"status": "ready"}
