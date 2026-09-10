# DocMind — RAG Document Intelligence Platform

A production-grade Retrieval-Augmented Generation (RAG) system that lets you upload PDF documents and ask natural-language questions against them. Built with an async ingestion pipeline, hybrid vector + keyword retrieval, and streaming LLM responses with source citations.

---

## Features

- **Async PDF Ingestion** — Upload a PDF and a background worker handles parsing, chunking, and embedding. The API returns immediately; processing happens in a Redis + RQ job queue.
- **Hybrid Retrieval** — Combines pgvector cosine similarity search with BM25 keyword ranking, fused via Reciprocal Rank Fusion (RRF) for more accurate results than either method alone.
- **Streaming Responses** — Answers stream token-by-token via Server-Sent Events (SSE) so users see output immediately.
- **Source Citations** — Every response includes the page numbers the answer was drawn from.
- **Abstention Logic** — If retrieval confidence is below threshold, the system refuses to answer rather than hallucinate.
- **Idempotent Ingestion** — Re-uploading the same document skips already-processed chunks. Safe to retry.

---

## Architecture

```
┌─────────────┐     POST /upload      ┌──────────────────┐
│   Client    │ ──────────────────▶  │   FastAPI Backend │
└─────────────┘                       └────────┬─────────┘
                                               │ enqueue job
                                               ▼
                                       ┌──────────────┐
                                       │  Redis Queue  │
                                       └──────┬───────┘
                                              │ dequeue
                                              ▼
                                       ┌──────────────┐       ┌───────────────────┐
                                       │  RQ Worker   │ ────▶ │  Gemini Embedding │
                                       └──────┬───────┘       │  (3072 dimensions)│
                                              │                └───────────────────┘
                                              ▼
                                       ┌──────────────┐
                                       │  PostgreSQL   │
                                       │  + pgvector   │
                                       └──────────────┘

POST /query
  1. Embed question          →  Gemini embedding API
  2. Vector search           →  pgvector cosine similarity
  3. Keyword search          →  BM25 (rank-bm25)
  4. Fuse rankings           →  Reciprocal Rank Fusion (RRF)
  5. Stream answer           →  Gemini LLM via SSE
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| API | FastAPI + Uvicorn |
| Async Jobs | Redis + RQ |
| Database | PostgreSQL 16 + pgvector |
| Embeddings | Google Gemini (`gemini-embedding-001`, 3072-dim) |
| LLM | Google Gemini (`gemini-2.5-flash`) |
| PDF Parsing | PyMuPDF |
| Keyword Search | BM25 (`rank-bm25`) |
| Containerization | Docker Compose |

---

## Performance (measured with k6 load testing)

| Metric | Value |
|---|---|
| Hybrid search latency p50 | 10ms |
| Hybrid search latency p95 | 18ms |
| Full retrieval pipeline p50 | 205ms |
| Full retrieval pipeline p95 | 325ms |
| Concurrent users | 5 |
| Sustained throughput | 1.6 req/s |

---

## Getting Started

### Prerequisites

- Docker and Docker Compose
- A [Google AI Studio](https://aistudio.google.com) API key (free tier)

### 1. Clone the repo

```bash
git clone https://github.com/sanketkesarkar/docmind.git
cd docmind
```

### 2. Set up environment variables

```bash
cp .env.example .env
```

Open `.env` and add your Gemini API key:

```
GEMINI_API_KEY=your_key_here
```

### 3. Start all services

```bash
docker-compose up --build
```

This starts:
- `postgres` — PostgreSQL with pgvector extension
- `redis` — job queue broker
- `backend` — FastAPI server on port 8000
- `worker` — RQ ingestion worker

### 4. Upload a PDF

```bash
curl -X POST http://localhost:8000/api/v1/upload \
  -F "file=@your_document.pdf"
```

Response:
```json
{ "document_id": "abc123...", "status": "processing" }
```

### 5. Check ingestion status

```bash
curl http://localhost:8000/api/v1/status/<document_id>
```

Wait until `"status": "completed"`.

### 6. Ask a question (streaming)

```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What is this document about?", "document_id": "<document_id>"}' \
  --no-buffer
```

Response streams as Server-Sent Events:
```
data: {"type": "meta", "citations": [{"page_number": 1, "score": 0.0164}], "abstaining": false}
data: {"type": "token", "text": "This document is about..."}
data: {"type": "done"}
```

---

## Project Structure

```
docmind/
├── docker-compose.yml
├── .env.example
├── load_test.js              # k6 load test script
└── backend/
    ├── Dockerfile
    ├── requirements.txt
    └── app/
        ├── main.py
        ├── config.py
        ├── api/
        │   ├── upload.py     # POST /upload, GET /status
        │   └── query.py      # POST /query (SSE streaming)
        ├── models/
        │   └── document.py   # Document + Chunk SQLAlchemy models
        ├── services/
        │   ├── embedder.py   # Gemini embedding with retry
        │   ├── vector_store.py  # pgvector + BM25 + RRF hybrid search
        │   ├── llm.py        # Gemini streaming + abstention
        │   └── parser.py     # PyMuPDF PDF → word chunks
        ├── workers/
        │   └── ingestion.py  # RQ worker job
        └── db/
            └── database.py   # SQLAlchemy session setup
```

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/upload` | Upload a PDF for ingestion |
| `GET` | `/api/v1/status/{id}` | Check ingestion status |
| `POST` | `/api/v1/query` | Ask a question (SSE streaming) |

---

## License

MIT
