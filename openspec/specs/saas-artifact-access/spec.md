# saas-artifact-access Specification

## Purpose
Provide secure, tenant-facing access to durable training artifacts in Nebius Object Storage and
ensure submitted training jobs write to the same per-run S3 prefixes without exposing credentials.

## Requirements

### Requirement: S3 artifact reads

The SaaS backend SHALL read run artifacts (status, metrics, artifact manifests, media references) from the `sim2policy-artifacts` bucket via the S3 API (`boto3`), scoped to the run prefix `sim2policy/<run-id>/`. It SHALL NOT use the Nebius management SDK for object storage access.

When a tenant requests `GET /jobs/{job_id}/artifacts` for a `completed` job whose manifest is not cached, the backend SHALL attempt an on-demand read of `sim2policy/<run-id>/report/artifacts.json` from S3; on success it SHALL cache the manifest durably and return it.

#### Scenario: Completed job returns real artifacts

- **WHEN** a Nebius-backed job reaches `completed` and the tenant requests `GET /jobs/{job_id}/artifacts`
- **THEN** the manifest is built from objects under `s3://sim2policy-artifacts/sim2policy/<run-id>/`, not from in-process placeholders

#### Scenario: Artifacts not yet written

- **WHEN** the tenant requests artifacts before the training run has written its manifest to S3
- **THEN** the API responds `409 artifacts not ready`, as it does today

#### Scenario: Manifest published after job completion

- **WHEN** a job completed without a manifest in S3, the finalization pipeline later publishes `report/artifacts.json`, and the tenant requests `GET /jobs/{job_id}/artifacts`
- **THEN** the API reads the manifest from S3 on demand, caches it, and responds `200` with the manifest on this and subsequent requests

#### Scenario: Lazy read failure degrades to not-ready

- **WHEN** the on-demand S3 manifest read for a `completed` job fails (missing key or transient S3 error)
- **THEN** the API responds `409 artifacts not ready` (never a 5xx caused by the lazy read) and logs the failure

### Requirement: S3 credentials injected from MysteryBox

S3 credentials for the SaaS pod SHALL be sourced from MysteryBox and delivered to the container as environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_ENDPOINT_URL_S3`, `AWS_DEFAULT_REGION`, `SIM2POLICY_S3_BUCKET`). The secret access key SHALL NOT appear in Git, in plain Kubernetes manifests, or in logs.

#### Scenario: Pod receives credentials from a secret

- **WHEN** the SaaS deployment starts in the cluster
- **THEN** the S3 env vars are populated from a Kubernetes Secret whose values originate in MysteryBox, and no manifest in Git contains the secret access key

#### Scenario: Missing credentials fail fast

- **WHEN** the `nebius` backend is selected but the S3 credentials are absent
- **THEN** the service reports a configuration error at startup rather than failing on the first tenant request

### Requirement: Training jobs share the artifact credentials

Each submitted Serverless AI job SHALL receive the same artifact-bucket credentials, with the secret access key injected via MysteryBox secret reference (the SDK equivalent of `--env-secret`), so the training container writes its outputs to `s3://sim2policy-artifacts/sim2policy/<run-id>/`.

#### Scenario: Training output lands under the run prefix

- **WHEN** a submitted training job completes
- **THEN** its checkpoints, manifest, and media exist under the job's `sim2policy/<run-id>/` prefix and are readable by the SaaS backend

#### Scenario: Secret key never passed in plaintext

- **WHEN** the backend constructs the job submission
- **THEN** the AWS secret access key is referenced through MysteryBox, never embedded as a plaintext env value in the job spec or logged
