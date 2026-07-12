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

## Persistence

Users, sessions, jobs, and artifact manifests are stored in SQLite at `SAAS_DB_PATH`
(default `saas.db` in the working directory — no setup needed locally). In the cluster the
path points at a PersistentVolumeClaim (`/data/saas.db`), so logins and job history survive
pod restarts and redeploys. Pending one-time codes and rate-limit counters are intentionally
in-memory only; a restart just means re-requesting a code.

Email delivery is selected by `SAAS_EMAIL_BACKEND`:

- `mock` (default) — the code is written to the server log; perfect for local demos, never for
  real deployments.
- `smtp` — real email through Mailjet in production. `SAAS_SMTP_HOST=in-v3.mailjet.com`,
  `SAAS_SMTP_PORT=587`, `SAAS_SMTP_TLS_MODE=starttls`, and
  `SAAS_SMTP_TIMEOUT_SECONDS=10`; `SAAS_SMTP_USER` is the Mailjet API Key,
  `SAAS_SMTP_PASSWORD` is the Mailjet Secret Key, and `SAAS_SMTP_FROM` is the validated sender.

The public deployment requires a non-optional `saas-smtp` Kubernetes Secret reconciled from a
pinned MysteryBox version; it never falls back to mock. Missing/invalid SMTP configuration prevents
startup. A connection, TLS, authentication, recipient, quota, or provider failure returns a
sanitized `503` with `Retry-After`, deletes the unusable pending code, and still consumes the abuse
rate-limit attempt. Real-delivery logs contain only result category and latency, never the code,
recipient, provider response, API Key, or Secret Key.

### Mailjet production setup

1. In Mailjet **Senders & Domains**, validate `sim-policy-trainer-challenge.info` under the same API
   Key used for SMTP.
2. Publish the exact ownership and DKIM records shown by Mailjet. Publish one apex SPF TXT record
   `v=spf1 include:spf.mailjet.com ~all`, merging the include into an existing SPF record if one
   exists. Preserve the existing DMARC record; do not publish a second one.
3. Wait for Mailjet to report the domain, SPF, and DKIM as valid. Use
   `Sim2Policy <login@sim-policy-trainer-challenge.info>` as the From identity.
4. In the Nebius Console, create a new immutable version in `sim2policy-saas-smtp`, copy all seven
   template keys, replace only `SAAS_SMTP_USER` and `SAAS_SMTP_PASSWORD`, and make it primary.
   Never put either real value in Git, `.tfvars`, a plan, a command, or documentation.
5. Set only the non-secret `saas_smtp_secret_version_id` in gitignored `saas.auto.tfvars`, apply the
   stack, run `saas-smtp-sync.service`, and inspect Kubernetes key names only as documented in
   `sim2policy/infra/nebius/README.md`.

Monitor Mailjet's daily/monthly quota and delivery dashboard. To rotate, create a new Mailjet Secret
Key/version, update the pinned version ID, reconcile, restart the Deployment, verify one bounded
login, and then revoke the old key. To roll back, restore the prior validated MysteryBox version,
reconcile, and restart. Mock mode is acceptable only for local or explicitly controlled demos; do
not leave the public UI claiming that mock delivery sent email.

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
For production-safe bearer-token examples covering catalog discovery, parameterized submissions,
polling, and artifacts, see [API_RUNBOOK.md](API_RUNBOOK.md).

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
