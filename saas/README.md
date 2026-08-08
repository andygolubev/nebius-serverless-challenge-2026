# Sim2Policy SaaS

The tenant-facing control plane. A FastAPI backend serves the public showcase, the authenticated
robot/setup/training API, and the built React frontend from a single container image. Visitors
browse a read-only gallery of curated training runs without an account; signed-in users upload a
bounded MJCF robot, compose a setup from server-owned tasks and scenes, prepare it, and start one
fixed training profile.

Read [ARCHITECTURE.md](../ARCHITECTURE.md) for the design and its rationale. This file is the
API and operations reference.

## Layout

```
saas/
├── backend/            FastAPI app
│   ├── app/            auth, showcase, robots, setups, preparation, training, artifacts, analytics
│   ├── tests/          pytest suite
│   └── validation_suite/  My Robots form-matrix runner
├── frontend/           React + Vite UI (showcase, jobs, results, My Robots)
├── samples/robots/     Original primitive-only quadruped and biped MJCF examples
└── Dockerfile          builds the frontend, serves it from the backend (one image)
```

## Authentication

Passwordless email + one-time code:

1. `POST /auth/request-code {"email": "you@example.com"}` — a 6-digit code is emailed
   (rate limit: 5 requests / 15 min per email). The response is identical whether or not the email
   already has an account.
2. `POST /auth/verify {"email": ..., "code": ...}` — returns `{"token": ...}`. Codes expire after
   10 minutes, are single-use, and die after 5 wrong attempts.
3. Send `Authorization: Bearer <token>` on every authenticated call. Sessions last
   `SAAS_SESSION_TTL_HOURS` (default 24) and are revoked by `POST /auth/logout`.

The tenant is the session's verified email; the old `X-Tenant-Id` header is not accepted.

## API

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET  | `/health` | — | liveness/readiness; reports orchestration, email, custom-training, showcase state |
| POST | `/analytics/collect` | — | write-only visit beacon; always `204` |
| GET  | `/showcase` | — | published curated examples with their measured evidence |
| GET  | `/showcase/{example_id}` | — | one published example's detail |
| GET  | `/showcase/{example_id}/artifacts/{artifact_id}` | — | play or download a published artifact |
| GET  | `/training-options` | — | showcase display metadata (legacy clients; prefer `/showcase`) |
| POST | `/auth/request-code` | — | email a one-time code (429 when rate-limited) |
| POST | `/auth/verify` | — | exchange email+code for a session token |
| POST | `/auth/logout` | bearer | revoke the session |
| GET  | `/me` | bearer | authenticated email |
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
| GET  | `/robot-setups/{id}/preparations/latest` | bearer | inspect live preparation phase/result |
| POST | `/robot-setups/{id}/training-jobs` | bearer | start the fixed custom PPO profile from Ready |
| GET  | `/jobs` | bearer | list this tenant's jobs |
| GET  | `/jobs/{id}` | bearer | job status + resolved config (404 for another tenant's job) |
| GET  | `/jobs/{id}/artifacts` | bearer | result manifest once completed |
| GET  | `/jobs/{id}/artifacts/{artifact_id}` | bearer | play or download one owned artifact |
| POST | `/jobs` | bearer | **410 Gone** — see below |

Validation failures return 422 with `{"field", "message"}`. Cross-tenant identifiers return 404
without revealing whether the resource exists.

For production-safe bearer-token examples covering the showcase, robot upload, setup composition,
preparation polling, training, and artifacts, see [API_RUNBOOK.md](API_RUNBOOK.md). Never record a
real bearer token in Git, command examples, issue text, or `IMPLEMENTATION_LOG.MD`.

### There is exactly one way to create a job

`POST /jobs` returns **410 Gone**. The verified examples are a read-only showcase of runs that were
already performed, so there is nothing there to submit; the endpoint is retained only to answer an
old client honestly rather than 404-ing it. No branch of that handler can create a SaaS job record
or a remote resource.

Training starts from an owner's own accepted setup:

```
POST /robots                                 → validated robot version
POST /robot-setups                           → normalized setup draft
POST /robot-setups/{id}/preparations         → bounded cpu-d3 compatibility job
POST /robot-setups/{id}/training-jobs        → one custom-ppo-quick job
```

That last call accepts the setup identity plus idempotency metadata and nothing else. Backend,
algorithm, hardware, image, command, PPO settings, task, scene, and object overrides are all
rejected with 422.

## Bring Your Robot

An MJCF robot is not a complete reinforcement-learning environment. It describes bodies, joints,
actuators, and geometry, but not the accepted observation/action mapping, reward, termination,
evaluation rule, or job specification. The product therefore separates three concepts:

- **Robot model** — one owned, immutable, structurally validated MJCF XML version.
- **Task template** — a server-owned objective: `stand-balance`, `walk-forward`, or the
  quadruped-only `recover-from-fall`. No tenant reward or termination code.
- **Scene** — one server-owned preset (`flat-arena`, `ramp-course`, `hurdle-course`, or
  `step-course`) plus bounded primitive catalog objects (`box`, `ramp`, `hurdle`, `step`).

### Upload

`POST /robots` accepts multipart `name`, `robot_type` (`quadruped` or `biped`), and `file`. The
filename must be a safe `.xml` name and the file at most 1 MiB of UTF-8. Validation rejects
DTD/entities before parsing, then archives, includes, plugins, meshes, textures, height fields,
external paths/URLs, file references, unknown elements, and non-primitive geometry. A model must
have exactly one floating root, at least one actuated hinge, unique names, and valid actuator joint
references. Limits: 64 bodies, 64 joints, 64 actuators, 128 geoms, XML depth 16.

Download `sample-quadruped.xml` or `sample-biped.xml` in **My Robots** to exercise the exact same
public validator. A successful response carries a SHA-256 digest and a deterministic structural
summary; re-uploading identical content for the same tenant and declared type returns the active
version. Tenants keep at most 20 active robot versions. Deletion is soft.

Robot upload alone is structural validation only:

```json
{"readiness": "validated", "trainable": false, "reason": "custom-training-not-enabled"}
```

Training readiness is a property of a *setup*, not of a robot.

### Compose

The environment builder resolves omitted object values from the published catalog, admits at most
six objects **including preset composition**, enforces ±10 m arena position bounds plus per-object
dimension and rotation bounds, and persists canonical JSON plus a digest. A tenant keeps at most 50
active setup drafts. It accepts no object file, mesh, scene XML or package, remote URL, Python
environment, reward function, or executable task definition. These choices keep validation
deterministic and avoid parser, units, collision, licensing, storage, and code-execution ambiguity
while still covering realistic balance, walking, recovery, ramp, hurdle, box, and step workflows.

### Prepare and train

Every catalog-valid setup is admissible: biped Stand Balance/Walk Forward, quadruped Stand
Balance/Walk Forward/Recover From Fall, all four scene presets, and any bounded Box/Ramp/Hurdle/Step
combination within the six-object total. A setup whose robot type, task compatibility, or scene
falls outside the contract reports `training_readiness: ineligible` with a stable reason.

The user clicks **Prepare for training**. A bounded `cpu-d3` worker uses the immutable generic SB3
image to verify exact S3 inputs, compile the robot in a server-owned scene, run deterministic
rollout and render gates, check the Gymnasium/SB3 contract, and smoke-test PPO save/reload. An
accepted fingerprint enables **Start training**. `training_readiness` moves through `not_prepared`,
`preparing`, `ready`, and `preparation_failed`; a failed attempt can be retried for the same
fingerprint. Preparation means technical compatibility, not that the policy will reach the task
threshold.

Frozen shapes:

| Profile | Version | Platform / preset | Disk | Cap | Budget |
| --- | --- | --- | --- | --- | --- |
| Preparation | `custom-prepare-v1` | `cpu-d3` / `4vcpu-16gb` | 50 GiB | 10 min | 2,048-step PPO smoke |
| Training | `custom-ppo-quick-v2` | `cpu-d3` / `16vcpu-64gb` | 100 GiB | 3 h | 3M steps, 16 subprocess envs |

The eight historical anchor combinations measured about 3m42s–3m57s end to end for preparation.
Training v2 normalises observations and rewards and publishes the best checkpoint rather than the
last. The v1 shape (eight serial environments, 100k steps) finished in minutes but produced 100%
fall rates even for the bundled sample robots on flat ground; v2 trades that speed for an attempt
that can actually converge. It is still not a promise that a given robot reaches its threshold —
evaluation reports the outcome honestly either way.

A completed custom job publishes evaluation, task metrics, reward curve, rollout MP4, checkpoint,
resolved configuration, exact inputs, and a checksummed policy bundle. The bundle is simulator-only
and is not directly deployable to physical hardware. There is one runtime image for all robots — no
API or runtime path builds Docker per upload. Custom setups never appear in `/training-options` and
cannot be sent to `POST /jobs`.

## Verified examples showcase

The default landing surface is a server-driven, read-only gallery of curated runs that already
happened: G1 Rough Terrain, Go1 Walker, Ant Explorer, HalfCheetah Sprint, Hopper Balance, Walker2D
Stride, and Reacher Target, in that order. Each card explains the task, expected visible result,
primary success metric, runtime, and server-selected hardware; detail adds measured duration and
cost bound to the exact acceptance revision, structured evaluation, progression media, artifacts,
and the policy bundle.

An entry is published only when its pinned curated run's manifest, provenance, evaluation, selected
checkpoint, media, and bundle all validate, and its recorded canonical environment and backend match
the server-owned declaration. One operator-reviewed exception exists: the G1 entry is published as a
verified *recording* with `evaluation.success: false` and its actual measured result, never as an
accepted locomotion result. Anonymous visitors can play media and download bundles through the
public showcase artifact route; the bucket stays private and no route accepts a bucket key.

**No showcase route can start training.** There is no run, re-run, fork, or queue control anywhere
in the gallery — the only call to action is to sign in and train your own robot.

## Persistence

Users, sessions, jobs, artifact manifests, immutable robot XML and metadata, normalized setup
drafts, preparation attempts, and visit analytics are stored in SQLite at `SAAS_DB_PATH` (default
`saas.db` in the working directory — no setup needed locally). In the cluster the path points at a
PersistentVolumeClaim (`/data/saas.db`), so logins and job history survive pod restarts and
redeploys. Pending one-time codes and rate-limit counters are intentionally in-memory only; a
restart just means re-requesting a code.

Every table except analytics is retained indefinitely. Analytics rows are pruned on a 90-day window
with permanent daily rollups; that pruning touches no tenant, job, artifact, or robot row.

## Visit analytics

`POST /analytics/collect` is unauthenticated, write-only, and always answers `204` with an empty
body — analytics can never break a page. The frontend beacon fires on first load and on every SPA
view change (the SPA keeps routing in React state and never changes the URL, so server logs alone
cannot attribute page views), and ignores its own failures.

The backend derives the client address from the leftmost `X-Forwarded-For` entry and stores only a
salted SHA-256 hash from `SAAS_ANALYTICS_IP_SALT`. **With no salt configured, recording is disabled
entirely** rather than storing a weakly pseudonymized value. No raw address reaches the database,
logs, or any response, and no analytics row carries a tenant identity. Crawler user agents are
flagged, not discarded, so bot volume stays measurable and separable.

There is no read API or dashboard. Statistics are read as SQL over SSH against the live database —
see [ANALYTICS_QUERIES.md](ANALYTICS_QUERIES.md) for the query cookbook.

## Email delivery

Selected by `SAAS_EMAIL_BACKEND`:

- `mock` (default) — the code is written to the server log; fine for local demos, never for real
  deployments.
- `smtp` — real email through Mailjet in production: `SAAS_SMTP_HOST=in-v3.mailjet.com`,
  `SAAS_SMTP_PORT=587`, `SAAS_SMTP_TLS_MODE=starttls`, `SAAS_SMTP_TIMEOUT_SECONDS=10`;
  `SAAS_SMTP_USER` is the Mailjet API Key, `SAAS_SMTP_PASSWORD` is the Mailjet Secret Key, and
  `SAAS_SMTP_FROM` is the validated sender.

The public deployment requires a non-optional `saas-smtp` Kubernetes Secret reconciled from a pinned
MysteryBox version; it never falls back to mock, and missing or invalid SMTP configuration prevents
startup. A connection, TLS, authentication, recipient, quota, or provider failure returns a
sanitized `503` with `Retry-After`, deletes the unusable pending code, and still consumes the abuse
rate-limit attempt. Real-delivery logs contain only result category and latency — never the code,
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

Monitor Mailjet's daily/monthly quota and delivery dashboard. To rotate: create a new Mailjet Secret
Key and version, update the pinned version ID, reconcile, restart the Deployment, verify one bounded
login, then revoke the old key. To roll back: restore the prior validated MysteryBox version,
reconcile, and restart. Mock mode is acceptable only for local or explicitly controlled demos; do
not leave the public UI claiming that mock delivery sent email.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `SAAS_DB_PATH` | `saas.db` | SQLite file; `/data/saas.db` in the cluster |
| `SAAS_SESSION_TTL_HOURS` | `24` | Bearer session lifetime |
| `SAAS_EMAIL_BACKEND` | `mock` | `mock` or `smtp` |
| `SAAS_SMTP_*` | — | Seven keys from the `saas-smtp` Secret |
| `SAAS_ORCHESTRATION_BACKEND` | `mock` | `mock` or `nebius` |
| `SAAS_SHOWCASE_ENABLED` | `true` | Publish the public showcase |
| `SAAS_ANALYTICS_IP_SALT` | — | Absent ⇒ analytics recording disabled |
| `SAAS_ANALYTICS_RETENTION_DAYS` | `90` | Raw-row retention window |
| `SAAS_ANALYTICS_SESSION_GAP_MINUTES` | `30` | Inactivity that ends a visit |
| `CUSTOM_ROBOT_TRAINING_ENABLED` | `false` | Enable the custom preparation/training path |
| `CUSTOM_ROBOT_SB3_IMAGE` | — | Immutable generic SB3 runtime reference |
| `NEBIUS_*`, `AWS_*`, `SIM2POLICY_*` | — | Orchestration and artifact contract from `saas-nebius` |

In the cluster the whole `NEBIUS_*`/`AWS_*`/`SIM2POLICY_*`/`CUSTOM_ROBOT_*` contract arrives through
the `saas-nebius` Secret as `envFrom`. `SAAS_ORCHESTRATION_BACKEND` deliberately has no explicit
`env` entry, because an explicit `env` would override `envFrom`; without the Secret the app falls
back to `mock`, so the manifest syncs safely in any order and no credential lives in Git.

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

Backend tests:

```bash
cd saas/backend
pip install -r requirements-dev.txt
python -m pytest tests
```

## My Robots form validation

The fast gate runs the exhaustive API and component matrices plus the isolated local browser suite;
it uses temporary databases, mock delivery and orchestration, and creates no cloud jobs:

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
fingerprint; screenshots and traces are failure-only, and publication is blocked when the evidence
scan finds credentials, authorization headers, login codes, private MJCF content, storage keys, or
an unscannable artifact. See [backend/validation_suite/README.md](backend/validation_suite/README.md).

The deployed no-cost smoke is manual (`saas-form-smoke.yml`). It accepts only the approved HTTPS
origin and a masked existing test-tenant session secret, serializes all dispatches against the one
test tenant, preflights `/me`, model/setup quota headroom, and the catalog, uploads only canonical
public samples, and deletes only the exact robot and setup IDs it created. The runner verifies
deletion with an exact-ID lookup and fails if it observes any preparation or training POST. Set
`preserve_resources` only for short-lived operator inspection, and delete the recorded IDs
afterwards. Never paste a bearer token into a command, workflow input, issue, or report. The
evidence scan runs even after a test failure; GitHub uploads evidence only when that scan succeeds.

Remote preparation and remote training are separate paid gates and default to `not-run-cost-gated`.
Do not enable them from the no-cost workflow. They have separate stable IDs and flags; training also
requires preparation in the same bounded run. A paid canary requires `SAAS_SMOKE_CHEAP_GATE_FILE` to
reference the sanitized result from a same-run no-cost gate with clean cleanup and both paid paths
marked `not-run-cost-gated`; a stale, preserved, or failed result is rejected before remote
mutation. It also requires one retained eligible setup, bounded polling, a fresh idempotency key,
and the provider audit and cleanup procedure in [API_RUNBOOK.md](API_RUNBOOK.md). The runner writes
a gitignored `provider-audit-request-*.json`, then waits for the external provider auditor to write
the configured audit result. It will not report the gate clean unless that result correlates the
exact SaaS preparation/job IDs, covers AI jobs, instances, disks, public IPs, and security rules,
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
ArgoCD on the `saas-server` deploys it. See [`deploy/`](../deploy/README.md) and
[`sim2policy/infra/nebius/`](../sim2policy/infra/nebius/README.md).

## Managing the cluster (tunnel-only)

The k3s API and ArgoCD are **not** public. Reach them over SSH:

```bash
ssh -L 8080:localhost:$(ssh saas-server 'kubectl -n argocd get svc argocd-server -o jsonpath="{.spec.ports[0].port}"') saas-server
```

```bash
ssh -L 6443:localhost:6443 saas-server
```

The second forwards the k3s API for a local `kubectl` using a copied kubeconfig whose server URL is
rewritten to localhost. On the box itself, `kubectl` requires `sudo`.
