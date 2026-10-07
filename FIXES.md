# DocMind fixes

Based on the newer uploaded `docmind(1).zip`.

- Enabled RQ scheduler for delayed retries and bounded worker registry maintenance interval.
- Added Redis reconnect handling, including RQ returning after an internal connection error, plus PostgreSQL pool pre-ping.
- Replaced Redis-only worker liveness with this pod's RQ heartbeat. Configured worker TTL to avoid marking idle workers unhealthy.
- Extended worker termination grace to cover the configured ingestion job timeout.
- Required SeaweedFS credentials using a mounted secret/config file.
- Pinned service and application image tags and httpx.
- Made chunk flushing explicit before the total count; completed-job logs now report total stored chunks, including resumed chunks. The latest ZIP already counted stored chunks correctly through SQLAlchemy autoflush.
- Readiness checks schema and bucket availability; Compose startup initializes its storage backend. Bucket authorization errors are no longer treated as a missing bucket.
- Added Redis AOF and persistent storage to Compose.

## Setup
Extract into a separate folder first. Preserve your original folder as a backup.
Copy `.env.example` to `.env` and set your existing credentials.
Copy `k8s/secrets.env.example` to `k8s/secrets.env` for Kubernetes.
Copy `k8s/s3.json.example` to `k8s/s3.json` and set matching S3 credentials.
For Compose, the S3 credentials matter when `STORAGE_BACKEND=s3`; the default remains local shared-volume storage.
Follow `k8s/README.md` to build and deploy version `0.2.1`.

Private environment files, Git history, caches and macOS metadata are excluded from this deliverable. Source code and sample PDFs remain included.

## Validation
Seven pytest regression cases passed against RQ 1.16.2, fakeredis and a SQLite test database: abandoned-job retry scheduling, fresh/stale/missing heartbeat checks, Redis outage handling/reconnection, resumed chunk counting/idempotent completion, and storage permission errors.
YAML parsing and Python compilation passed. Docker, kubectl and a live cluster are unavailable in this environment, so image builds, Kubernetes admission, real PostgreSQL/Redis recovery, SeaweedFS authentication and scaling still require deployment checks.

Run tests from `backend`:
```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

## Application validation fixes (0.2.1)
- Replaced SQL interpolation with bound document, embedding and limit parameters.
- Validated UUID path/query fields and constrained k to integers 1–50 across all query routes.
- Applied consistent document readiness validation to the retrieval benchmark.
- Separated cosine evidence from RRF ranking; answer prompts/citations exclude weak or unscored evidence.
- Converted all six reproduced failures into passing tests and added boundary/consistency tests. Current result: 43 passed, zero expected failures. See TEST_REPORT.md.
