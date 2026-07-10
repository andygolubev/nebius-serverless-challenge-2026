# Design: Nebius Job Orchestration for the SaaS Backend

## Context

The SaaS control plane (FastAPI, `saas/backend/app/`) runs on k3s with `SAAS_ORCHESTRATION_BACKEND=mock`. The orchestration seam already exists: `OrchestrationBackend` protocol in `orchestration.py`, selected by env var in `main.py`, with an in-memory `JobStore`. The tenant API is preset-only (`ALLOWED_PRESETS`), so no user code/images ever reach the backend.

Cloud-side, `sim2policy-saas-server` holds only Registry `viewer` + MysteryBox access; `sim2policy-artifacts` has `storage.object-editor` S3 credentials that are not wired into the pod; `sim2policy-saas-ci` only pushes images. Nothing today can create Serverless AI jobs or read the artifact bucket.

`sim2policy/jobs/submit.sh` is the proven reference for job parameters: image, `--container-command python --args "-m sim2policy.train_<backend> …"`, platform/preset, timeout, subnet, `--registry-secret`, and S3 creds with the access key via `--env` and the secret via `--env-secret` (MysteryBox).

## Goals / Non-Goals

**Goals:**
- Real end-to-end flow: `POST /jobs` → SDK creates Serverless AI job → store `aijob-*` ID → poll `JobService.get()` → read manifests/results from S3 → return artifacts to the tenant.
- Keep the tenant-facing API and the mock backend unchanged; the backend swap is configuration only.
- All secrets flow through MysteryBox → Kubernetes Secret → env vars; nothing sensitive in Git.

**Non-Goals:**
- Durable job store (JobStore stays in-memory; single replica). Restart loses in-flight job records — acceptable for this stage.
- Job cancellation endpoint, multi-region, autoscaling, or per-tenant quotas.
- Narrowing the `editor` role — Nebius has no documented job-scoped role today.
- Changing the sim2policy training containers or the demo API.

## Decisions

### 1. Official Python SDK, not CLI subprocess

Use `pip install nebius` and `nebius.api.nebius.ai.v1` (`JobServiceClient`, `CreateJobRequest`, `GetJobRequest`) inside the backend. Alternatives considered:
- **CLI subprocess (`nebius ai job create`)**: works (submit.sh proves it) but requires shipping the CLI in the image, parsing stdout, and shell-quoting job args — fragile and harder to test.
- **Raw gRPC/REST**: no benefit over the maintained SDK.

The SDK authenticates with the backend service account's credentials (service-account key or federated token, per pysdk docs). `submit.sh` remains the behavioral reference — the `NebiusBackend` must produce an equivalent job spec (name `sim2policy-<run-id>`, container command/args, platform, preset, timeout, subnet, restart-policy never, registry secret, S3 env/env-secret).

### 2. Dedicated backend service account with project `editor`

Create (or promote) a dedicated service account for the SaaS backend and grant `editor` on the project. Nebius currently requires at least `editor` to create/cancel Serverless AI jobs ([quickstart](https://docs.nebius.com/serverless/quickstart/jobs)). This is broader than ideal; we accept it, isolate it to its own account (not `sim2policy-saas-server`'s existing credentials, not the CI account), and note it as a revisit point when Nebius ships a job-scoped role.

### 3. S3 (`boto3`) for artifacts, not the management SDK

Artifact reads go through the S3-compatible endpoint with the existing `sim2policy-artifacts` credentials. Env contract:

```
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
AWS_ENDPOINT_URL_S3=https://storage.eu-north1.nebius.cloud
AWS_DEFAULT_REGION=eu-north1
SIM2POLICY_S3_BUCKET=sim2policy-artifacts
```

The backend lists/reads under `sim2policy/<run-id>/` to build `ArtifactManifest`. Media entries are returned as object keys (as the mock does today); presigned URLs are a possible follow-up.

### 4. Same artifact credentials for submitted jobs, via MysteryBox

Job submissions inject `AWS_ACCESS_KEY_ID` as a plain env and `AWS_SECRET_ACCESS_KEY` as a MysteryBox secret reference (SDK equivalent of `--env-secret`), matching submit.sh. The training container therefore writes to `s3://sim2policy-artifacts/sim2policy/<run-id>/` with credentials that never transit the job spec in plaintext.

### 5. Polling model

`NebiusBackend.launch()` starts a daemon poller thread per job (mirroring `MockBackend`'s threading model) that calls `JobService.get()` on an interval (~10s), maps Nebius states to the tenant lifecycle, and exits on terminal state or timeout margin. State mapping (exact Nebius enum names to be confirmed during implementation):

- pending/provisioning → `starting`
- running → `training` (finer-grained `evaluating`/`rendering` can be inferred later from S3 status.json if desired)
- succeeded → read S3 manifest → `completed`
- failed/cancelled/timeout → `failed`

Alternative — a single reconciler loop over all active jobs — is cleaner at scale but unnecessary for single-replica demo volume; per-job threads match the existing code style.

### 6. Configuration and fail-fast

New env vars consumed only by the `nebius` backend: the S3 set above plus `NEBIUS_PROJECT_ID` (parent for jobs), `SIM2POLICY_JOB_IMAGE` (or per-preset images in the catalog), `NEBIUS_SUBNET_ID`, registry-secret and MysteryBox secret identifiers. `build_backend("nebius")` validates all required settings at startup and raises, so a misconfigured pod fails its readiness probe instead of failing on first tenant request. Preset catalog (image, module, config, platform, preset, timeout, step caps) lives server-side next to `ALLOWED_PRESETS`.

## Risks / Trade-offs

- [`editor` is broad — backend compromise could modify project resources] → dedicated SA, key only in MysteryBox/K8s Secret, no interactive use; revisit when a job-scoped role exists.
- [In-memory JobStore loses `aijob-*` IDs on pod restart] → accepted for demo scale; artifacts remain recoverable from S3 by run ID; durable store is a known follow-up.
- [Nebius state enum / SDK surface may differ from assumptions] → confirm against pysdk during implementation; keep the mapping in one function with tests.
- [Polling threads leak if a job never terminates] → poller respects the preset timeout plus a margin, then marks the job `failed`.
- [Secret sprawl across MysteryBox, K8s Secret, job env-secret] → single source (MysteryBox selector); K8s Secret is created out-of-band or via the existing secret-sync path, never committed.

## Migration Plan

1. Cloud IAM: create backend SA, grant `editor`, store its key + reuse artifact S3 creds in MysteryBox.
2. Ship code with `mock` still default; deploy; verify health.
3. Create the K8s Secret from MysteryBox values; flip `SAAS_ORCHESTRATION_BACKEND=nebius` in the deploy overlay.
4. Smoke test one `halfcheetah-demo` job end-to-end (submit → poll → S3 artifacts).
5. Rollback = set the env var back to `mock` (tenant API unchanged).

## Open Questions

- Exact pysdk job-spec field names and status enum values (`nebius.api.nebius.ai.v1`) — verify against the installed SDK version at implementation time.
- Whether MysteryBox secret references in SDK-created jobs use the same selector syntax as the CLI's `--env-secret`.
- Per-preset image/platform matrix: single training image for all presets or per-preset entries in the catalog.
