## MODIFIED Requirements

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

## ADDED Requirements

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

