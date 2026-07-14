## ADDED Requirements

### Requirement: Custom input and result prefixes are server-scoped
The SaaS backend and trusted runtime SHALL read/write custom preparation inputs only beneath `sim2policy/preparations/<preparation-id>/` and custom training snapshots/results only beneath `sim2policy/<run-id>/`, where both identities are generated and ownership-resolved by the server. Tenant APIs SHALL expose opaque attempt/job/artifact identifiers and SHALL never accept or return a bare input/result key as an authority to read storage.

#### Scenario: Runtime receives a custom input reference
- **WHEN** a typed preparation or training job resolves its inputs
- **THEN** the prefix is reconstructed from the server identity, checked for safe containment, and matched to the expected manifest before any object is trusted

#### Scenario: Caller supplies a storage key
- **WHEN** a tenant attempts to request, prepare, train, or download using an arbitrary bucket key or prefix
- **THEN** the API rejects or ignores the field and performs no caller-directed S3 access

### Requirement: Custom job finalization requires the complete result set
For a custom-robot Job, artifact finalization SHALL require a valid manifest entry and readable in-prefix object for evaluation metrics and episodes, human summary/reward curve, final rollout MP4, final checkpoint, resolved configuration/runtime metadata, exact input snapshots, and simulator policy bundle. Every entry SHALL have a safe identifier/name, expected kind/content type, byte size, and integrity metadata. The Job SHALL not become completed while any required object is missing or invalid.

#### Scenario: Complete custom manifest is read
- **WHEN** all required custom artifacts exist beneath the owned run prefix and validate
- **THEN** the backend caches their structured metadata, completes the Job, and exposes normal tenant-authorized player/download controls

#### Scenario: Manifest points outside the run
- **WHEN** a custom manifest entry references the preparation prefix, another run, an absolute URL, or a traversing key instead of its approved run snapshot/artifact
- **THEN** finalization rejects the entry and exposes no access URL

### Requirement: Policy bundle is delivered through normal tenant authorization
The custom policy bundle SHALL be a manifest-declared artifact available only through the existing owned Job artifact-access mechanism, with a safe filename, archive content type, byte size, checksum, and short-lived/streamed access. Cross-tenant requests SHALL return 404, and deleted source robot/setup state SHALL not alter ownership of the historical Job artifact.

#### Scenario: Owner downloads a bundle
- **WHEN** the Job owner requests the manifest-declared policy bundle
- **THEN** the backend streams or redirects to exactly that object using a safe filename and appropriate content disposition

#### Scenario: Another tenant requests a bundle
- **WHEN** another authenticated tenant uses the custom Job or artifact identifier
- **THEN** the API returns 404 without revealing whether the bundle exists

