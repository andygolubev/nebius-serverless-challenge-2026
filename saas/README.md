# Sim2Policy SaaS

Tenant-facing control plane for Sim2Policy jobs. A FastAPI backend serves the auth + job API and
the built React frontend from a single container image. Users sign in with an email one-time code,
then compose training jobs (environment + policy + bounded hyperparameters) validated against a
server-side catalog. Job orchestration is behind a pluggable interface; the `mock` backend drives
the full lifecycle with no Nebius credentials or GPU.

## Layout

```
saas/
├── backend/            FastAPI app (auth, jobs, robot/setup validation, orchestration)
│   ├── app/
│   └── tests/          pytest suite (auth + job validation)
├── frontend/           React + Vite UI (jobs, compact results, My Robots workspace)
├── samples/robots/     Original primitive-only quadruped and biped MJCF examples
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

Users, sessions, jobs, artifact manifests, immutable robot XML/metadata, and normalized robot setup
drafts are stored in SQLite at `SAAS_DB_PATH`
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
| GET  | `/robot-samples` | bearer | list the two canonical upload-compatible MJCF examples |
| GET  | `/robot-samples/{id}` | bearer | download the exact canonical sample XML |
| POST | `/robots` | bearer | upload and validate one bounded multipart MJCF file |
| GET  | `/robots` | bearer | list active tenant robot versions |
| GET  | `/robots/{id}` | bearer | inspect one owned active robot version |
| GET  | `/robots/{id}/content` | bearer | download the immutable owned XML |
| DELETE | `/robots/{id}` | bearer | soft-delete an owned robot version |
| GET  | `/environment-catalog` | bearer | task, scene, object, default, and bound contracts |
| POST | `/robot-setups` | bearer | save an immutable normalized environment draft |
| GET  | `/robot-setups` | bearer | list active tenant setup drafts |
| GET  | `/robot-setups/{id}` | bearer | inspect one owned active setup |
| DELETE | `/robot-setups/{id}` | bearer | soft-delete an owned setup |
| POST | `/robot-setups/{id}/preparations` | bearer | prepare an eligible exact setup fingerprint |
| GET | `/robot-setups/{id}/preparations/latest` | bearer | inspect live preparation phase/result |
| POST | `/robot-setups/{id}/training-jobs` | bearer | start the fixed custom PPO profile from Ready |

Submit either a custom configuration or a preset shortcut — both are validated against the
catalog in `app/catalog.py` (allowlisted environments/algorithms, bounded parameters; no custom
code, images, or environment variables):

```bash
# custom
curl -X POST /jobs -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"environment": "go1", "algorithm": "ppo-mjx", "params": {"learning_rate": 0.001, "seed": 42}}'
# preset
curl -X POST /jobs -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"preset": "go1-mjx-quick", "seed": 42}'
```

The response carries `resolved_config` — user overrides merged over catalog defaults — so a job
always shows exactly what ran. Validation failures return 422 with `{"field", "message"}`.

Select `mock` or `nebius` with `SAAS_ORCHESTRATION_BACKEND`; production uses the bounded Nebius
adapter.

## Bring Your Robot beta contract

An MJCF robot is not a complete reinforcement-learning environment. It describes bodies, joints,
actuators, and geometry, but not the accepted observation/action mapping, reward, termination,
evaluation rule, or production job specification. The beta therefore separates three concepts:

- **Robot model:** one owned, immutable, structurally validated MJCF XML version.
- **Task template:** a server-owned objective (`stand-balance`, `walk-forward`, or the
  quadruped-only `recover-from-fall`) with no tenant reward or termination code.
- **Scene:** one server-owned preset (`flat-arena`, `ramp-course`, `hurdle-course`, or
  `step-course`) plus bounded primitive catalog objects (`box`, `ramp`, `hurdle`, `step`).

`POST /robots` accepts multipart fields `name`, `robot_type` (`quadruped` or `biped`), and `file`.
The filename must be a safe `.xml` name and the file must be at most 1 MiB of UTF-8. Validation
rejects DTD/entities before parsing; archives, includes, plugins, meshes, textures, height fields,
external paths/URLs, file references, unknown elements, and non-primitive geometry. A model must
have exactly one floating root, at least one actuated hinge, unique names, and valid actuator joint
references. Limits are 64 bodies, 64 joints, 64 actuators, 128 geoms, and XML depth 16.

Download `sample-quadruped.xml` or `sample-biped.xml` in **My Robots** to exercise the exact same
public validator. A successful response contains a SHA-256 digest and deterministic structural
summary. Re-uploading identical content for the same tenant and declared type returns the active
version. Tenants can keep at most 20 active robot versions; deletion is soft and all reads/downloads
remain owner-scoped with cross-tenant identifiers returning 404.

The environment builder resolves all omitted object values from the published catalog, admits at
most six total objects including preset composition, enforces the declared ±10 m arena position
bounds plus per-object dimension/rotation bounds, and persists canonical JSON plus a digest. A
tenant can keep at most 50 active setup drafts. It accepts no object file, mesh, scene XML/package,
remote URL, Python environment, reward function, or executable task definition. These choices keep
validation deterministic and avoid parser, units, collision, licensing, storage, and code-execution
ambiguity while still covering realistic balance, walking, recovery, ramp, hurdle, box, and step
workflows.

Robot upload still deliberately returns structural validation only:

```json
{"readiness":"validated","trainable":false,"reason":"custom-training-not-enabled"}
```

A saved setup additionally derives `training_readiness`. Training V2 admits every catalog-valid
setup: biped Stand Balance/Walk Forward, quadruped Stand Balance/Walk Forward/Recover From Fall,
all four scene presets, and bounded Box/Ramp/Hurdle/Step objects within the six-object total. The user first
clicks **Prepare for training**. A bounded `cpu-d3` worker uses the immutable generic SB3 image to
verify exact S3 inputs, compile the robot in a server-owned scene, run deterministic rollout/render
gates, and smoke-test PPO save/reload. An accepted fingerprint enables **Start training**, which
creates a normal Job with the fixed `custom-ppo-quick` CPU profile. Preparation means technical
compatibility, not that the policy will reach the task threshold.

The frozen preparation shape is `cpu-d3` / `4vcpu-16gb`, 50 GiB, with a ten-minute cap; the eight
historical V1 anchor combinations measured about 3m42s–3m57s end to end. `custom-ppo-quick` uses
`cpu-d3` / `8vcpu-32gb`, 100 GiB, eight vector environments, 100k steps, and a one-hour cap; the
same matrix measured about 3m31s–3m49s and roughly $0.01 per attempt at the 2026-07-14 list rate.
These are observed bounds for the exact immutable profile, not a promise that 100k steps converges.

The completed custom Job publishes evaluation, task metrics, reward curve, rollout MP4,
checkpoint, resolved configuration, exact inputs, and a checksummed policy bundle. The bundle is
simulator-only and is not directly deployable to physical hardware. There is one runtime image for
all robots—no API/runtime path builds Docker per upload. Custom setups never appear in
`/training-options` and cannot be sent to generic `POST /jobs`.

## Verified examples gallery

The default **New job** surface is a server-driven gallery with exactly seven stable examples:
Go1 Walker, Ant Explorer, HalfCheetah Sprint, Hopper Balance, Walker2D Stride, G1 Rough Terrain,
and Reacher Target. Each card explains the task, expected visible result, primary success metric,
accepted runtime, server-selected hardware, and measured duration/cost bound for that exact
acceptance revision. Go1 Quick is recommended; Standard and Quality are secondary sizes on the
same card. The only general user override is a bounded reproducibility seed.

`POST /jobs` accepts `gallery_example_id`, optional catalog-declared `gallery_profile_id`, and
bounded `params`. It rejects caller-selected algorithms, compute, images, commands, code,
environment variables, secrets, or storage paths. SB3 examples use the immutable generic SB3
runtime on `cpu-d3`; Go1/G1 use the immutable MJX runtime on the accelerator profile frozen by
acceptance. A gallery job is not completed until its final video, metrics, checkpoint, resolved
configuration, runtime versions, and deterministic checksummed `policy-bundle.zip` are readable.
The bundle is the normal post-training download, but it remains simulator-only rather than a
physical-robot deployment artifact.

Run the backend tests:

```bash
cd saas/backend
pip install -r requirements-dev.txt
python -m pytest tests
```

### My Robots form validation

The fast gate runs the exhaustive API and component matrices plus the isolated local browser
suite; it uses temporary databases, mock delivery/orchestration, and does not create cloud jobs:

```bash
cd saas/backend
python -m pytest tests/test_my_robots_matrix.py tests/test_validation_suite.py -q
cd ../frontend
npm test -- --testTimeout=10000
npm run test:e2e
npm run build
```

CI shards these layers independently and merges JUnit evidence under the gitignored
`.form-validation-runs/` directory. The generated report records stable case IDs and a catalog
fingerprint; screenshots/traces are failure-only and publication is blocked when the evidence scan
finds credentials, authorization headers, login codes, private MJCF content, storage keys, or an
unscannable artifact.

The deployed no-cost smoke is manual (`saas-form-smoke.yml`). It accepts only the approved HTTPS
origin and a masked existing test-tenant session secret, serializes all dispatches against the one
test tenant, preflights `/me`, model/setup quota headroom, and the catalog, uploads only canonical
public samples, and deletes only the exact robot/setup IDs it created. The runner verifies deletion
with an exact-ID lookup and fails if it observes any preparation or training POST. Set
`preserve_resources` only for short-lived operator inspection and delete the recorded IDs afterward.
Never paste a bearer token into a command, workflow input, issue, or report. The evidence scan runs
even after a test failure; GitHub uploads evidence only when that scan succeeds.

Remote preparation and remote training are separate paid gates and default to
`not-run-cost-gated`. Do not enable them from the no-cost workflow. The preparation and training
tests have separate stable IDs and flags; training also requires preparation in the same bounded
run. A paid canary requires `SAAS_SMOKE_CHEAP_GATE_FILE` to reference the sanitized result from a
same-run no-cost gate with clean cleanup and both paid paths marked `not-run-cost-gated`; a stale,
preserved, or failed result is rejected before remote mutation. It also requires one retained
eligible setup, bounded polling, a fresh idempotency key, and the provider audit/cleanup procedure
in `saas/API_RUNBOOK.md`. The runner
writes a gitignored `provider-audit-request-*.json`, then waits for the external provider auditor to
write the configured audit result. It will not report the gate clean unless the result correlates
the exact SaaS preparation/job IDs, covers AI jobs, instances, disks, public IPs, and security rules,
enumerates only terminal/stopped/deleted provider resources, and reports zero remaining active
resources. A boolean acknowledgement is deliberately insufficient.

The sanitized provider audit result has this shape (placeholder values only):

```json
{
  "schema_version": 1,
  "run_id": "operator-supplied-run-id",
  "audited_saas_resource_ids": ["preparation-or-job-id"],
  "audited_scopes": ["ai-jobs", "instances", "disks", "public-ips", "security-rules"],
  "provider_resources": [{"kind": "ai-job", "id": "provider-resource-id", "state": "terminal"}],
  "remaining_active_resources": [],
  "cleanup_status": "clean"
}
```

The audit file must contain summarized identities and states, never a raw provider response. If it
is absent, stale, incomplete, or reports an active resource, the paid test writes
`provider-audit-pending` and fails. The default no-cost result always records both paid paths as
`not-run-cost-gated`; it never counts them as passed.

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
