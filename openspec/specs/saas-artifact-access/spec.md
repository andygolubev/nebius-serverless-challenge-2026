# saas-artifact-access Specification

## Purpose
Provide secure, tenant-facing access to durable training artifacts in Nebius Object Storage and
ensure submitted training jobs write to the same per-run S3 prefixes without exposing credentials.
## Requirements
### Requirement: S3 artifact reads
The SaaS backend SHALL read status, metrics, manifests, and media metadata from the configured artifact bucket through the S3 API, scoped to `sim2policy/<run-id>/`. A job SHALL NOT be considered `completed` until its required finalized artifact set is readable and valid. `GET /jobs/{job_id}/artifacts` SHALL return structured readiness and artifact metadata rather than raw object keys; transient absence during finalization SHALL remain distinguishable from terminal artifact failure.

#### Scenario: Finalized job returns structured artifacts
- **WHEN** a tenant requests artifacts for a finalized job they own
- **THEN** the API returns metrics plus artifact identifiers, names, kinds, content types, sizes when known, and tenant-authorized access URLs without returning bucket credentials or bare object keys as browser links

#### Scenario: Artifacts are still finalizing
- **WHEN** remote training succeeded but the required artifact set is not yet complete
- **THEN** the API returns a structured not-ready response and the job remains non-terminal

#### Scenario: Lazy recovery after publication
- **WHEN** finalization publishes a valid manifest after an earlier transient read failure
- **THEN** reconciliation reads and validates it, caches the manifest durably, and allows the job to become `completed`

#### Scenario: Invalid finalized manifest fails safely
- **WHEN** a manifest references a missing, unsafe, or out-of-prefix object
- **THEN** the backend refuses to expose the reference and records a sanitized artifact-validation failure

#### Scenario: Completed job returns real artifacts
- **WHEN** a finalized Nebius-backed job's owner requests its artifacts
- **THEN** the response is derived from validated objects under the run prefix and contains structured artifact metadata rather than in-process placeholders

#### Scenario: Artifacts not yet written
- **WHEN** required finalized artifacts are not yet readable
- **THEN** the artifact API returns structured not-ready state and the job remains non-terminal

#### Scenario: Manifest published after job completion
- **WHEN** a historical completed job has no cached manifest and finalization later publishes `report/artifacts.json`
- **THEN** an owner request reads, validates, and durably caches the manifest before returning structured artifacts

#### Scenario: Lazy read failure degrades to not-ready
- **WHEN** an on-demand historical manifest read encounters a missing key or transient S3 error
- **THEN** the API reports artifacts not ready without leaking the storage error or returning an unhandled 5xx

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

### Requirement: Tenant-authorized artifact delivery
The backend SHALL expose an opaque artifact access URL for each manifest-declared artifact. Every access SHALL authenticate the session, verify ownership of the job, resolve an allowlisted artifact identifier against the cached manifest, and either stream the object with HTTP range support or redirect to a short-lived presigned HTTPS URL. Callers SHALL NOT supply arbitrary bucket keys or prefixes.

#### Scenario: Owner plays a video
- **WHEN** the owning tenant requests an MP4 artifact through its access URL
- **THEN** the response supports browser playback and byte-range seeking with the correct `video/mp4` content type

#### Scenario: Owner downloads an artifact
- **WHEN** the owning tenant invokes the artifact download action
- **THEN** the backend returns or redirects to the exact manifest-declared object with a safe filename and appropriate content-disposition

#### Scenario: Another tenant is denied
- **WHEN** an authenticated tenant requests an artifact belonging to another tenant
- **THEN** the API returns 404 without revealing whether the job or artifact exists

#### Scenario: Arbitrary object key is rejected
- **WHEN** a caller supplies an object key or artifact identifier not present in the owned job's validated manifest
- **THEN** the API returns 404 and performs no S3 read for the caller-supplied key
