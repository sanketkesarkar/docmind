import logging
import redis
import os
import time
from redis.exceptions import RedisError
from rq import Worker, Queue
from app.config import settings
from app.db.database import SessionLocal
from app.models.document import Document, Chunk
from app.services.parser import extract_chunks, get_page_count
from app.services.embedder import embed_text
from app.services.storage import local_pdf_path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

redis_conn = redis.from_url(settings.REDIS_URL, socket_connect_timeout=3)
ingestion_queue = Queue("ingestion", connection=redis_conn)


def process_document(document_id: str, storage_key: str):
    with local_pdf_path(storage_key) as file_path:
        _process_document(document_id, file_path)


def _process_document(document_id: str, file_path: str):
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            logger.error(f"Document {document_id} not found")
            return

        # idempotency: skip if already completed
        if doc.status == "completed":
            logger.info(f"Document {document_id} already processed, skipping")
            return

        doc.status = "processing"
        doc.error = None
        db.commit()
        logger.info(f"Processing document {document_id}: {file_path}")

        total_pages = get_page_count(file_path)
        doc.total_pages = total_pages
        db.commit()

        chunk_count = 0
        for chunk_data in extract_chunks(file_path):
            # idempotency: skip duplicate chunks
            existing = db.query(Chunk).filter(
                Chunk.document_id == document_id,
                Chunk.page_number == chunk_data["page_number"],
                Chunk.chunk_index == chunk_data["chunk_index"],
            ).first()
            if existing:
                continue

            embedding = embed_text(chunk_data["content"])
            chunk = Chunk(
                document_id=document_id,
                page_number=chunk_data["page_number"],
                chunk_index=chunk_data["chunk_index"],
                content=chunk_data["content"],
                embedding=embedding,
            )
            db.add(chunk)
            chunk_count += 1

            if chunk_count % 10 == 0:
                db.commit()
                logger.info(f"Document {document_id}: {chunk_count} chunks indexed")

        db.flush()
        doc.total_chunks = db.query(Chunk).filter(Chunk.document_id == document_id).count()
        doc.status = "completed"
        db.commit()
        logger.info(f"Document {document_id} completed: {doc.total_chunks} chunks, {total_pages} pages")

    except Exception as e:
        logger.error(f"Document {document_id} failed: {e}")
        db.rollback()
        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc:
            doc.status = "failed"
            doc.error = str(e)
            db.commit()
        # re-raise so RQ marks the job failed and applies the Retry policy
        raise
    finally:
        db.close()


def run_worker():
    # Reconnect in-process during Redis outages; Kubernetes need not restart us.
    while True:
        try:
            redis_conn.ping()
            worker = Worker([ingestion_queue], connection=redis_conn, name=os.environ.get("HOSTNAME", "docmind-worker"), default_worker_ttl=90, maintenance_interval=60)
            worker.work(with_scheduler=True)
            if worker._stop_requested:
                return
            logger.warning("RQ worker exited unexpectedly; restarting in 5 seconds")
            time.sleep(5)
        except RedisError:
            logger.exception("Redis unavailable; reconnecting in 5 seconds")
            time.sleep(5)


if __name__ == "__main__":
    logger.info("Starting ingestion worker...")
    run_worker()
