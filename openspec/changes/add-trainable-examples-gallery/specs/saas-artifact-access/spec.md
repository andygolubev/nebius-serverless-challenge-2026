## ADDED Requirements

### Requirement: Policy bundle artifact delivery
The artifact API SHALL represent a finalized `policy-bundle.zip` as a manifest-declared artifact
with an opaque identifier, safe filename, `application/zip` content type, byte size, and SHA-256
digest. Access SHALL reuse the tenant-authorized artifact route: authenticate the session, verify
job ownership, resolve only the cached allowlisted identifier, and stream or redirect to a
short-lived presigned HTTPS URL. A client SHALL NOT provide a bucket key or prefix.

#### Scenario: Owner requests policy bundle metadata
- **WHEN** the owning tenant requests artifacts for a completed gallery job
- **THEN** the structured response includes the bundle's opaque identifier, safe display name,
  size, digest, and tenant-authorized download URL without exposing its object key

#### Scenario: Owner downloads policy bundle
- **WHEN** the owning tenant follows the bundle download URL
- **THEN** the exact validated archive is returned or redirected with `application/zip` and a safe
  attachment filename

#### Scenario: Another tenant requests the bundle
- **WHEN** an authenticated tenant requests a bundle belonging to another tenant
- **THEN** the API returns 404 and reveals neither the job nor artifact existence

#### Scenario: Caller supplies an arbitrary bundle key
- **WHEN** a caller supplies a storage key or identifier not in the owned job's cached manifest
- **THEN** the API returns 404 and performs no S3 read for the caller-supplied value

### Requirement: Policy bundle integrity before exposure
The backend SHALL expose a policy bundle only after validating the archive's outer SHA-256 digest,
bounded safe member list, required common-envelope files, internal manifest schema, and every
declared member digest. Validation failures SHALL be sanitized and SHALL NOT expose a partial or
untrusted archive.

#### Scenario: Bundle validates
- **WHEN** the readable archive matches its outer digest and all required members match the
  internal manifest
- **THEN** it is cached as a validated artifact and may participate in gallery-job completion

#### Scenario: Bundle digest or member is invalid
- **WHEN** an archive is corrupt, missing a required file, contains an unsafe path, or disagrees
  with its declared digest
- **THEN** it is not returned to the tenant and finalization records a sanitized validation failure
