"""Application tests: real HTTP routing, PDF parsing, SQLAlchemy and RQ.
External services are replaced explicitly; these are not live-cluster tests.
"""
import os
os.environ.setdefault('GEMINI_API_KEY', 'test-only')
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost/test')

import json
import uuid
from unittest.mock import patch, MagicMock

import fakeredis
import fitz
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, TypeDecorator, String
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.database import Base, get_db
from app.models.document import Document, Chunk
from app.api import upload, query
from app.services import vector_store, llm, parser
from app.workers import ingestion
from rq import Queue


class SQLiteUUID(TypeDecorator):
    # PostgreSQL natively accepts UUID strings. SQLite needs an explicit adapter.
    impl = String(32)
    cache_ok = True
    def process_bind_param(self, value, dialect):
        return uuid.UUID(str(value)).hex if value is not None else None
    def process_result_value(self, value, dialect):
        return uuid.UUID(value) if value is not None else None


@pytest.fixture
def application(tmp_path):
    uuid_columns = [Document.__table__.c.id, Chunk.__table__.c.id, Chunk.__table__.c.document_id]
    original_types = [column.type for column in uuid_columns]
    for column in uuid_columns:
        column.type = SQLiteUUID()
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    def database():
        with sessions() as db:
            yield db
    app.dependency_overrides[get_db] = database
    connection = fakeredis.FakeRedis()
    queue = Queue('ingestion', connection=connection)
    with patch.object(upload, 'ingestion_queue', queue), patch.object(ingestion, 'SessionLocal', sessions), patch.object(ingestion.settings, 'STORAGE_BACKEND', 'local'), patch.object(ingestion.settings, 'STORAGE_PATH', str(tmp_path)), patch.object(ingestion, 'embed_text', return_value=None):
        # Startup is deliberately not invoked: migration is a separate deployment step.
        yield TestClient(app, raise_server_exceptions=False), sessions, queue
    app.dependency_overrides.clear()
    engine.dispose()
    for column, original_type in zip(uuid_columns, original_types):
        column.type = original_type


def pdf_bytes():
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 72), 'DocMind supports asynchronous document ingestion. The queue is Redis.')
        return doc.tobytes()


def test_upload_ingest_and_document_status(application):
    client, sessions, queue = application
    response = client.post('/api/v1/upload', files={'file': ('sample.pdf', pdf_bytes(), 'application/pdf')})
    assert response.status_code == 200
    document_id = response.json()['document_id']
    assert client.get('/api/v1/documents/' + document_id).json()['status'] == 'pending'
    job = queue.jobs[0]
    # Invoke the registered RQ job with its queued arguments; no worker fork/service is simulated here.
    ingestion.process_document(uuid.UUID(job.args[0]), job.args[1])
    status = client.get('/api/v1/documents/' + document_id).json()
    assert status['status'] == 'completed'
    assert status['total_pages'] == 1
    assert status['total_chunks'] == 1
    assert len(client.get('/api/v1/documents').json()) == 1


def test_upload_rejects_non_pdf(application):
    client, _, _ = application
    assert client.post('/api/v1/upload', files={'file': ('sample.txt', b'hello')}).status_code == 400


def test_corrupt_pdf_sets_failed_status(application):
    client, _, queue = application
    response = client.post('/api/v1/upload', files={'file': ('bad.pdf', b'not a PDF')})
    job = queue.jobs[0]
    with pytest.raises(Exception):
        ingestion.process_document(uuid.UUID(job.args[0]), job.args[1])
    assert client.get('/api/v1/documents/' + response.json()['document_id']).json()['status'] == 'failed'


@pytest.mark.parametrize('endpoint', ['query', 'query/benchmark', 'query/retrieval-benchmark'])
def test_empty_question_rejected(application, endpoint):
    client, _, _ = application
    assert client.post('/api/v1/' + endpoint, json={'question': '   '}).status_code == 400


def test_query_unknown_and_unready_document(application):
    client, sessions, _ = application
    assert client.post('/api/v1/query', json={'question': 'What?', 'document_id': str(uuid.uuid4())}).status_code == 404
    document_id = uuid.uuid4()
    with sessions() as db:
        db.add(Document(id=document_id, filename='pending.pdf', status='pending'))
        db.commit()
    assert client.post('/api/v1/query', json={'question': 'What?', 'document_id': str(document_id)}).status_code == 400


def test_sse_citations_tokens_and_done(application):
    client, _, _ = application
    chunks = [{'page_number': 2, 'score': 0.03, 'cosine_score': 0.8, 'content': 'Redis'}]
    with patch.object(query, 'embed_text', return_value=[0.0]), patch.object(query, 'hybrid_search', return_value=chunks), patch.object(query, 'stream_answer', return_value=iter(['Redis ', 'queue.'])):
        response = client.post('/api/v1/query', json={'question': 'What queue?'})
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/event-stream')
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    assert events[0]['citations'] == [{'page_number': 2, 'score': 0.03}]
    assert events[0]['abstaining'] is False
    assert ''.join(event['text'] for event in events if event['type'] == 'token') == 'Redis queue.'
    assert events[-1] == {'type': 'done'}


def test_empty_retrieval_abstains_without_llm(application):
    client, _, _ = application
    with patch.object(query, 'embed_text', return_value=[0.0]), patch.object(query, 'hybrid_search', return_value=[]), patch.object(llm.client.models, 'generate_content_stream') as generate:
        response = client.post('/api/v1/query', json={'question': 'Unknown?'})
    assert 'enough information' in response.text
    generate.assert_not_called()


def test_health_and_metrics(application):
    client, _, _ = application
    assert client.get('/healthz').status_code == 200
    assert client.get('/metrics').status_code == 200


def test_parser_chunk_boundaries():
    words = [str(i) for i in range(950)]
    chunks = parser._split_text(' '.join(words), 500, 50)
    assert len(chunks) == 3
    assert chunks[0].split()[-50:] == chunks[1].split()[:50]
    assert chunks[-1].split()[-1] == '949'


def test_malformed_document_id_returns_validation_error(application):
    client, _, _ = application
    assert client.get('/api/v1/documents/not-a-uuid').status_code == 422


@pytest.mark.parametrize('k', [0, -1, 1000000])
def test_invalid_retrieval_limit_rejected(application, k):
    client, _, _ = application
    with patch.object(query, 'embed_text', return_value=[0.0]), patch.object(query, 'hybrid_search', return_value=[]):
        assert client.post('/api/v1/query/retrieval-benchmark', json={'question': 'test', 'k': k}).status_code == 422


def test_retrieval_document_filter_is_bound_parameter():
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = []
    untrusted_id = "' OR 1=1 --"
    vector_store._fetch_all_chunks(db, document_id=untrusted_id)
    statement = db.execute.call_args.args[0]
    assert untrusted_id not in str(statement)


def test_unrelated_vector_evidence_abstains():
    unrelated = {'chunk_id': '1', 'page_number': 1, 'content': 'unrelated', 'score': 0.0}
    with patch.object(vector_store, 'similarity_search', return_value=[unrelated]), patch.object(vector_store, '_fetch_all_chunks', return_value=[]):
        chunks = vector_store.hybrid_search(MagicMock(), [0.0], 'unrelated question')
    assert llm.should_abstain(chunks) is True


def test_readiness_returns_503_on_database_outage(application):
    import app.main as main
    client, _, _ = application
    with patch.object(main.engine, 'connect', side_effect=RuntimeError('database offline')):
        response = client.get('/readyz')
    assert response.status_code == 503
    assert response.json()['detail'] == 'Dependencies or migration not ready'


@pytest.mark.parametrize('endpoint', ['query', 'query/benchmark', 'query/retrieval-benchmark'])
@pytest.mark.parametrize('payload', [{'question': 'test', 'document_id': "' OR 1=1 --"}, {'question': 'test', 'k': 51}, {'question': 'test', 'k': 1.5}])
def test_all_query_routes_validate_inputs_before_embedding(application, endpoint, payload):
    client, _, _ = application
    with patch.object(query, 'embed_text') as embed:
        assert client.post('/api/v1/' + endpoint, json=payload).status_code == 422
        embed.assert_not_called()


@pytest.mark.parametrize('endpoint', ['query', 'query/benchmark', 'query/retrieval-benchmark'])
def test_all_query_routes_reject_missing_documents(application, endpoint):
    client, _, _ = application
    with patch.object(query, 'embed_text') as embed:
        assert client.post('/api/v1/' + endpoint, json={'question': 'test', 'document_id': str(uuid.uuid4())}).status_code == 404
        embed.assert_not_called()


def test_vector_search_binds_embedding_document_and_limit():
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = []
    document_id = str(uuid.uuid4())
    vector_store.similarity_search(db, [0.1, 0.2], document_id, k=7)
    statement, parameters = db.execute.call_args.args
    assert document_id not in str(statement)
    assert '[0.1,0.2]' not in str(statement)
    assert parameters == {'embedding': '[0.1,0.2]', 'document_id': document_id, 'limit': 7}
    from sqlalchemy.dialects import postgresql
    assert set(statement.compile(dialect=postgresql.dialect()).params) == {'embedding', 'document_id', 'limit'}


def test_fusion_keeps_cosine_when_bm25_overlaps():
    candidate = {'chunk_id': '1', 'page_number': 1, 'content': 'Redis', 'score': 0.8}
    with patch.object(vector_store, 'similarity_search', return_value=[candidate]), patch.object(vector_store, '_fetch_all_chunks', return_value=[]), patch.object(vector_store, 'bm25_search', return_value=[{**candidate, 'score': 8.0}]):
        chunks = vector_store.hybrid_search(MagicMock(), [0.0], 'Redis')
    assert chunks[0]['cosine_score'] == 0.8
    assert chunks[0]['score'] == round(2 / 61, 6)
    assert llm.should_abstain(chunks) is False


def test_missing_cosine_does_not_use_keyword_or_rrf_score():
    assert llm.should_abstain([{'score': 100, 'cosine_score': None}]) is True


def test_cosine_threshold_boundary():
    with patch.object(llm.settings, 'MIN_COSINE_SIMILARITY', 0.6):
        assert llm.should_abstain([{'cosine_score': 0.599}]) is True
        assert llm.should_abstain([{'cosine_score': 0.6}]) is False


def test_stream_prompt_excludes_weak_evidence():
    chunks = [{'page_number': 1, 'content': 'reliable evidence', 'cosine_score': 0.8}, {'page_number': 2, 'content': 'unrelated evidence', 'cosine_score': 0.0}]
    with patch.object(llm.client.models, 'generate_content_stream', return_value=[]) as generate:
        list(llm.stream_answer('test', chunks))
    assert 'reliable evidence' in generate.call_args.kwargs['contents']
    assert 'unrelated evidence' not in generate.call_args.kwargs['contents']


def test_sse_abstention_has_no_weak_citations(application):
    client, _, _ = application
    chunks = [{'page_number': 9, 'score': 0.02, 'cosine_score': 0.0, 'content': 'irrelevant'}]
    with patch.object(query, 'embed_text', return_value=[0.0]), patch.object(query, 'hybrid_search', return_value=chunks), patch.object(llm.client.models, 'generate_content_stream') as generate:
        response = client.post('/api/v1/query', json={'question': 'test'})
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    assert events[0]['abstaining'] is True
    assert events[0]['citations'] == []
    generate.assert_not_called()
