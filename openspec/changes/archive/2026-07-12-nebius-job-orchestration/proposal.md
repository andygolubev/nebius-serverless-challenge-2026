# Nebius Job Orchestration for the SaaS Backend

## Why

The SaaS control plane currently runs with `SAAS_ORCHESTRATION_BACKEND=mock`: tenant job submissions never reach Nebius, and artifact manifests are fabricated in-process. The k3s-hosted backend has no credentials capable of creating Serverless AI jobs (`sim2policy-saas-server` only holds Registry `viewer` plus MysteryBox read access) and the `sim2policy-artifacts` S3 credentials are not wired into the SaaS pod. To deliver the real product flow — tenant submits a preset, a GPU training job runs on Nebius, artifacts come back from object storage — the backend needs a real orchestration path and read access to the artifact bucket.

## What Changes

- Add a `nebius` orchestration backend to the SaaS app (`saas/backend/app/orchestration.py`) that creates Serverless AI jobs via the official Nebius Python SDK (`pip install nebius`; `JobServiceClient.create()` / `get()`), stores the returned `aijob-*` resource ID on the job record, and polls job status to drive the tenant-visible lifecycle.
- Provision a dedicated backend service account with `editor` on the project (Nebius currently requires at least `editor` to create/cancel Serverless AI jobs; no narrower job-specific role is documented — see [Serverless AI quickstart](https://docs.nebius.com/serverless/quickstart/jobs)).
- Add `boto3` and read run artifacts (manifests, metrics, media references) directly from `s3://sim2policy-artifacts/sim2policy/<run-id>/` using S3 credentials injected as env vars (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_ENDPOINT_URL_S3`, `AWS_DEFAULT_REGION`, `SIM2POLICY_S3_BUCKET`).
- Pass the same artifact credentials into each submitted training job via MysteryBox `--env-secret` semantics (SDK equivalent), so the training container writes to the shared bucket under the job's run ID.
- Wire secrets into the SaaS pod from MysteryBox — never from Git or a plain Kubernetes manifest — extending the existing deploy manifests (`deploy/manifests/saas/`).
- The mock backend remains the default for local development; the deployed environment switches `SAAS_ORCHESTRATION_BACKEND` to `nebius`.

## Capabilities

### New Capabilities

- `saas-nebius-orchestration`: The SaaS backend submits, tracks, and reflects real Nebius Serverless AI jobs for tenant job requests — SDK-based job creation from allowlisted presets only, `aijob-*` ID persistence, status polling mapped to the tenant-visible lifecycle, and launch-failure handling.
- `saas-artifact-access`: The SaaS backend reads per-run artifacts from the `sim2policy-artifacts` S3 bucket and serves tenant-scoped artifact manifests; credentials are injected from MysteryBox and shared with submitted training jobs so they write to the same run prefix.

### Modified Capabilities

<!-- none: `training-job-orchestration` covers the sim2policy demo API, whose requirements do not change; this change adds the SaaS-side counterpart as new capabilities -->

## Impact

- **Code**: `saas/backend/app/orchestration.py` (new `NebiusBackend`), `saas/backend/app/models.py` (job gains a Nebius job ID field), `saas/backend/app/store.py` (persist the ID), `saas/backend/requirements.txt` (`nebius`, `boto3`).
- **Deploy**: `deploy/manifests/saas/deployment.yaml` gains secret-backed env vars; a Kubernetes Secret sourced from MysteryBox; `SAAS_ORCHESTRATION_BACKEND=nebius` in the deployed overlay.
- **Cloud IAM**: new/updated service account with project `editor` (broader than ideal — accepted risk until Nebius ships a job-scoped role); reuse of the existing `sim2policy-artifacts` S3 credentials via MysteryBox.
- **Dependencies**: [Nebius Python SDK](https://github.com/nebius/pysdk), `boto3`.
- **Reference**: `sim2policy/jobs/submit.sh` stays as the CLI reference for job parameters (image, platform/preset, timeout, subnet, registry secret, S3 env injection); the SDK path must mirror its validation and secret-handling rules.
