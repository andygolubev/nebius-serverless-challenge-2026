# Sim2Policy SaaS

Tenant-facing control plane for Sim2Policy jobs. A FastAPI backend serves the job API and the
built React frontend from a single container image. Job orchestration is behind a pluggable
interface; the `mock` backend drives the full lifecycle with no Nebius credentials or GPU.

## Layout

```
saas/
├── backend/            FastAPI app (jobs API, tenant scoping, mock orchestrator)
│   └── app/
├── frontend/           React + Vite + TypeScript UI
└── Dockerfile          builds the frontend, serves it from the backend (one image)
```

## Local development

Backend:

```bash
cd saas/backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload           # http://127.0.0.1:8000
```

Frontend (separate shell, proxies API to the backend):

```bash
cd saas/frontend
npm install
npm run dev                              # http://127.0.0.1:5173
```

## API

Tenant identity comes from the `X-Tenant-Id` header (a real deployment authenticates it).

| Method | Path | Purpose |
|--------|------|---------|
| GET  | `/health` | liveness/readiness |
| GET  | `/training-options` | allowlisted presets |
| POST | `/jobs` | submit `{ "preset": "ant-demo", "seed": 42 }` |
| GET  | `/jobs` | list this tenant's jobs |
| GET  | `/jobs/{id}` | job status (404 for another tenant's job) |
| GET  | `/jobs/{id}/artifacts` | result manifest once completed |

Select the backend with `SAAS_ORCHESTRATION_BACKEND` (only `mock` today).

## Container

```bash
docker build -t sim2policy-saas ./saas
docker run -p 8000:8000 sim2policy-saas   # serves API + UI on :8000
```

CI (`.github/workflows/saas-image.yml`) builds this image and pushes it to the Nebius Registry;
ArgoCD on the `saas-server` deploys it (see `deploy/` and `sim2policy/infra/nebius/`).

## Managing the cluster (tunnel-only)

The k3s API and ArgoCD are **not** public. Reach them over SSH:

```bash
# ArgoCD UI
ssh -L 8080:localhost:$(ssh saas-server 'kubectl -n argocd get svc argocd-server -o jsonpath="{.spec.ports[0].port}"') saas-server
# kubectl via the k3s kubeconfig (copied from the server, server URL rewritten to localhost)
ssh -L 6443:localhost:6443 saas-server
```
