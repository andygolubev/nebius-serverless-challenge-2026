# saas-artifact-access delta

## MODIFIED Requirements

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
