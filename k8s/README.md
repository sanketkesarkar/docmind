# DocMind on Kubernetes (kind / k3d / any cluster)

## 1. Build the image and create a cluster
```bash
docker build -t docmind-backend:0.2.1 ../backend
kind create cluster --name docmind
kind load docker-image docmind-backend:0.2.1 --name docmind
```

## 2. Ingress controller and metrics-server (needed for the ingress and the HPA)
```bash
kubectl apply -f https://kind.sigs.k8s.io/examples/ingress/deploy-ingress-nginx.yaml
# kind also needs metrics-server with --kubelet-insecure-tls for the HPA to report CPU
```

## 3. Secrets and deploy
```bash
cp secrets.env.example secrets.env   # fill in GEMINI_API_KEY and passwords
cp s3.json.example s3.json          # set credentials to match S3_ACCESS_KEY / S3_SECRET_KEY
kubectl apply -k .
kubectl -n docmind get pods -w
```
The `docmind-migrate` Job creates the pgvector extension, tables and the storage bucket.
The API pods stay NotReady (`/readyz`) until the schema, Redis and the S3 bucket are ready.

## 4. Try it
```bash
kubectl -n docmind port-forward svc/docmind-api 8000:80
curl localhost:8000/readyz
curl -F file=@../test.pdf localhost:8000/api/v1/upload
```

## 5. Worker autoscaling with KEDA
```bash
helm repo add kedacore https://kedacore.github.io/charts
helm install keda kedacore/keda -n keda --create-namespace
```
Then `kubectl apply -k keda` (kept separate so the base deploy works without KEDA's CRDs).
While KEDA owns the worker Deployment, don't also attach an HPA to it.
Upload several PDFs and watch `kubectl -n docmind get pods -w`.

## 6. Load test
Point `../load_test.js` at the port-forward or ingress and run it with 1 API replica, then with the HPA active.

## 7. Verify (what to record for your resume)
- **Scaling:** upload ~20 PDFs; `kubectl -n docmind get pods -w` should show workers rising toward 10, then falling after the cooldown.
- **Worker crash:** `kubectl -n docmind delete pod -l app=docmind-worker` mid-ingestion; after RQ detects the abandoned job and schedules its retry, the document should reach `completed` with no duplicate chunks.
- **Redis restart:** `kubectl -n docmind delete pod redis-0` with jobs queued; the queue must survive (AOF on the PVC).
- **Rolling update:** `kubectl -n docmind rollout restart deploy/docmind-api` during a k6 run; record the observed failure rate; zero failures must be measured, not assumed.

## Operational details
- The worker runs RQ's scheduler so interval-based retries execute. Abandoned jobs are recovered by RQ registry maintenance; detection is not instantaneous.
- Worker heartbeat probes inspect the current pod's registration. Redis outages are handled by reconnection rather than liveness restarts.
- The 1,860-second termination grace covers the 1,800-second job timeout. Force deletion bypasses that grace.
- SeaweedFS requires a non-anonymous identity from `s3.json`. The example includes Admin for bucket initialization; use separate provisioning/application identities for production.
- Redis AOF persists the queue in Compose and Kubernetes. `appendfsync everysec` can lose roughly the last second of writes on abrupt failure; this is not a zero-loss guarantee.
- Version tags are fixed but not digest pins. Set a new application image tag for each release. The upstream versions are reproducible baselines, not a claim that they are the newest.
- Existing completed migration Jobs must be deleted/recreated before applying a changed Job template.
- After editing secrets, restart API, worker and SeaweedFS pods; secret names intentionally do not have generated suffixes.
- These are single-node PostgreSQL/Redis/SeaweedFS examples, not highly available production services.
