import logging
from fastapi import FastAPI
from app.db.database import init_db
from app.api.upload import router as upload_router
from app.api.query import router as query_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = FastAPI(title="DocMind", version="0.1.0")

app.include_router(upload_router, prefix="/api/v1", tags=["documents"])
app.include_router(query_router, prefix="/api/v1", tags=["query"])


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok"}
