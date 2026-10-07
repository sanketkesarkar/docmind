# Application test report — 0.2.1

Tested October 6, 2026 (America/New_York).

**Result: 43 tests passed; zero failures, zero expected failures.** The six failing cases from the prior report now pass. All four reported issues were addressed.

## Changes verified
- SQL uses bound parameters for document IDs, embedding literals and limits. Tests capture execution parameters and compile the vector query using SQLAlchemy's PostgreSQL dialect. No user ID is inserted into SQL.
- UUID validation rejects malformed document IDs with HTTP 422 before database access. Query k is an integer bounded to 1–50. Tests verify all three query routes reject invalid IDs, excessive limits and fractional limits before calling the embedding provider.
- Every query route validates existence and completion of a supplied document before retrieval; this now includes the retrieval benchmark.
- RRF ranking scores and cosine evidence scores are separate. BM25 overlap preserves cosine scores. A zero-similarity top-ranked vector result now abstains. Missing cosine scores cannot qualify as evidence. Boundary tests exercise the configurable threshold.
- Streaming prompts and citation metadata exclude weak evidence; abstention avoids the generation call.

## Other passing checks
- FastAPI HTTP routing for upload, status/listing, queries, health and metrics.
- Generated PDF parsed by PyMuPDF, queued using RQ/fakeredis, then processed into SQLite with local storage. Verified pending → completed and page/chunk totals; job invoked directly rather than executed by a forked worker.
- Non-PDF rejection and corrupt PDF marked failed.
- Empty questions, missing documents and unready documents rejected.
- SSE citation metadata, tokens, final done event and empty-result abstention.
- Database outage produces readiness HTTP 503.
- Chunk splitting/overlap, resumed chunk totals and completed-job idempotency.
- Abandoned RQ jobs scheduled for retry, worker heartbeat checks, Redis reconnection/scheduler activation and storage permission handling.

## Limits
SQLite with a test UUID adapter replaces PostgreSQL. Null embeddings are used for ingestion tests; real pgvector operations and vector persistence are untested. fakeredis replaces Redis; real network interruption, worker forks, scheduler processes and AOF durability are untested. Query embeddings/retrieval/generation are mocked where external dependencies are needed. S3 permission behavior is mocked.

Docker, Podman, Redis/PostgreSQL servers and kubectl are unavailable here. Container builds, Kubernetes admission, HPA/KEDA, rollouts, pod recovery, SeaweedFS authentication, live Gemini/model availability, semantic accuracy and latency remain unverified.

The default cosine threshold 0.5 is a configurable heuristic, not a measured confidence probability. Calibrate on labeled questions/documents. Keyword-only candidates outside the vector candidate set are conservatively excluded from answer evidence, which can reduce recall. Retrieval benchmark scores still measure RRF rank.

Python compilation and YAML parsing passed. The suite emitted 33 deprecation warnings, not test failures.

## Repeat
From `backend`:
```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q --disable-warnings
```
