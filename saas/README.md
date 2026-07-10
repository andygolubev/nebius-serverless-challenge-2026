# Sim2Policy SaaS

Tenant-facing control plane for Sim2Policy jobs. A FastAPI backend serves the auth + job API and
the built React frontend from a single container image. Users sign in with an email one-time code,
then compose training jobs (environment + policy + bounded hyperparameters) validated against a
server-side catalog. Job orchestration is behind a pluggable interface; the `mock` backend drives
the full lifecycle with no Nebius credentials or GPU.

## Layout

```
saas/
├── backend/            FastAPI app (email-code auth, catalog, jobs API, mock orchestrator)
│   ├── app/
│   └── tests/          pytest suite (auth + job validation)
├── frontend/           React + Vite + TypeScript UI (login, composer, dashboard, results)
└── Dockerfile          builds the frontend, serves it from the backend (one image)
```

## Authentication

Passwordless email + one-time code:

1. `POST /auth/request-code {"email": "you@example.com"}` — a 6-digit code is emailed
   (rate limit: 5 requests / 15 min per email).
2. `POST /auth/verify {"email": ..., "code": ...}` — returns `{"token": ...}`. Codes expire
   after 10 minutes, are single-use, and die after 5 wrong attempts.
3. Send `Authorization: Bearer <token>` on every job call. Sessions last
   `SAAS_SESSION_TTL_HOURS` (default 24) and are revoked by `POST /auth/logout`.

Email delivery is selected by `SAAS_EMAIL_BACKEND`:

- `mock` (default) — the code is written to the server log; perfect for local demos, never for
  real deployments.
- `smtp` — real email via `SAAS_SMTP_HOST`, `SAAS_SMTP_PORT` (587), `SAAS_SMTP_USER`,
  `SAAS_SMTP_PASSWORD`, `SAAS_SMTP_FROM`.

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

The tenant is the session's verified email; the old `X-Tenant-Id` header is no longer accepted.

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET  | `/health` | — | liveness/readiness |
| POST | `/auth/request-code` | — | email a one-time code (429 when rate-limited) |
| POST | `/auth/verify` | — | exchange email+code for a session token |
| POST | `/auth/logout` | bearer | revoke the session |
| GET  | `/me` | bearer | authenticated email |
| GET  | `/training-options` | — | catalog: environments, algorithms, parameter bounds, presets |
| POST | `/jobs` | bearer | submit a job (see below) |
| GET  | `/jobs` | bearer | list this tenant's jobs |
| GET  | `/jobs/{id}` | bearer | job status + resolved config (404 for another tenant's job) |
| GET  | `/jobs/{id}/artifacts` | bearer | result manifest once completed |

Submit either a custom configuration or a preset shortcut — both are validated against the
catalog in `app/catalog.py` (allowlisted environments/algorithms, bounded parameters; no custom
code, images, or environment variables):

```bash
# custom
curl -X POST /jobs -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"environment": "ant", "algorithm": "ppo-sb3", "params": {"learning_rate": 0.001, "seed": 42}}'
# preset
curl -X POST /jobs -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"preset": "ant-demo", "seed": 42}'
```

The response carries `resolved_config` — user overrides merged over catalog defaults — so a job
always shows exactly what ran. Validation failures return 422 with `{"field", "message"}`.

Select the orchestration backend with `SAAS_ORCHESTRATION_BACKEND` (only `mock` today).

Run the backend tests:

```bash
cd saas/backend
pip install -r requirements-dev.txt
python -m pytest tests
```

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
