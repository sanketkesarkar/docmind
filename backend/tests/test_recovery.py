import os
os.environ.setdefault('GEMINI_API_KEY', 'test-only')
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost/test')

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import fakeredis
import pytest
from redis.exceptions import ConnectionError
from rq import Queue, Retry
from rq.registry import StartedJobRegistry, ScheduledJobRegistry
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.models.document import Document, Chunk
from app.workers import healthcheck, ingestion
from app.services import storage
from botocore.exceptions import ClientError


def test_abandoned_job_is_scheduled_for_retry():
    connection = fakeredis.FakeRedis()
    queue = Queue('ingestion', connection=connection)
    job = queue.enqueue('app.workers.ingestion.process_document', 'doc', 'doc.pdf', retry=Retry(max=3, interval=[10, 30, 60]))
    queue.remove(job)
    started = StartedJobRegistry('ingestion', connection=connection)
    connection.zadd(started.key, {job.id: 1})
    started.cleanup()
    job.refresh()
    assert job.retries_left == 2
    assert job.id in ScheduledJobRegistry('ingestion', connection=connection).get_job_ids()


@pytest.mark.parametrize('age,expected', [(20, True), (150, False)])
def test_probe_checks_own_worker_heartbeat(age, expected):
    worker = SimpleNamespace(last_heartbeat=datetime.now(timezone.utc) - timedelta(seconds=age))
    with patch.object(healthcheck.Worker, 'find_by_key', return_value=worker):
        assert healthcheck.healthy() is expected


def test_probe_missing_worker_and_redis_outage():
    with patch.object(healthcheck.Worker, 'find_by_key', return_value=None):
        assert healthcheck.healthy() is False
    with patch.object(healthcheck.Worker, 'find_by_key', side_effect=ConnectionError):
        assert healthcheck.healthy() is True


def test_worker_reconnects_and_enables_scheduler():
    with patch.object(ingestion.redis_conn, 'ping', side_effect=[ConnectionError, True]), patch.object(ingestion.time, 'sleep') as sleep, patch.object(ingestion, 'Worker') as worker:
        worker.return_value._stop_requested = True
        ingestion.run_worker()
        sleep.assert_called_once_with(5)
        worker.return_value.work.assert_called_once_with(with_scheduler=True)


def test_resume_counts_existing_and_new_chunks():
    import uuid
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    document_id = uuid.uuid4()
    with sessions() as db:
        db.add(Document(id=document_id, filename='test.pdf', status='processing'))
        db.add(Chunk(document_id=document_id, page_number=1, chunk_index=0, content='existing'))
        db.commit()
    chunks = [{'page_number': 1, 'chunk_index': i, 'content': str(i)} for i in range(3)]
    with patch.object(ingestion, 'SessionLocal', sessions), patch.object(ingestion, 'get_page_count', return_value=1), patch.object(ingestion, 'extract_chunks', return_value=chunks), patch.object(ingestion, 'embed_text', return_value=None):
        ingestion._process_document(document_id, 'unused.pdf')
        ingestion._process_document(document_id, 'unused.pdf')
    with sessions() as db:
        assert db.get(Document, document_id).total_chunks == 3
        assert db.query(Chunk).count() == 3
        assert db.get(Document, document_id).status == 'completed'


def test_bucket_permission_error_does_not_create():
    error = ClientError({'Error': {'Code': '403'}}, 'HeadBucket')
    with patch.object(storage.settings, 'STORAGE_BACKEND', 's3'), patch.object(storage, '_s3_client') as client:
        client.return_value.head_bucket.side_effect = error
        with pytest.raises(ClientError):
            storage.ensure_bucket()
        client.return_value.create_bucket.assert_not_called()
