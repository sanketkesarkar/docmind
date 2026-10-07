"""One-shot setup: enable pgvector, create tables, make sure the storage bucket exists.

Runs as a Kubernetes Job (python -m app.migrate) before the API/worker start.
"""
import logging

from app.db.database import init_db
from app.services.storage import ensure_bucket

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    init_db()
    logger.info("Database initialised")
    ensure_bucket()
    logger.info("Storage ready")
