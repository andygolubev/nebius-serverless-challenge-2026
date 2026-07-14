## ADDED Requirements

### Requirement: Self-contained simulator policy bundle
Every completed custom-robot Job SHALL expose a single downloadable archive containing the load-tested final SB3 checkpoint, exact validated `robot.xml`, canonical `normalized-setup.json`, resolved task/scene/adapter/reward/profile configuration, ordered observation/action schemas and normalization, runtime/version metadata, evaluation summary, a checksummed internal manifest, and a README. The bundle SHALL contain only fixed safe relative paths and SHALL NOT contain credentials, tenant identifiers, absolute paths, arbitrary uploaded extras, or external references.

#### Scenario: Bundle is finalized
- **WHEN** a custom training run reaches artifact finalization
- **THEN** the service builds the fixed-layout archive, verifies every internal digest and allowed path, and lists it in the run artifact manifest

#### Scenario: Bundle contains the exact prepared inputs
- **WHEN** a user compares the bundle robot/setup digests to the accepted preparation and resolved Job configuration
- **THEN** all digests and schema/profile versions match exactly

#### Scenario: Unsafe bundle path is generated
- **WHEN** any proposed archive member is absolute, traverses a parent, is outside the fixed layout, or has an unapproved type
- **THEN** bundle validation fails and the Job cannot become completed

### Requirement: Bundle load verification
The finalization workflow SHALL extract the bundle in a bounded temporary location, verify its manifest, reconstruct the generic environment in the same immutable runtime, load the checkpoint into the recorded observation/action schemas, and complete a bounded deterministic inference smoke test before publishing the bundle as ready.

#### Scenario: Policy dimensions do not match metadata
- **WHEN** the checkpoint action or observation dimension differs from the bundle schemas
- **THEN** the load smoke test fails and the Job remains non-completed or fails finalization

#### Scenario: Bundle passes offline load test
- **WHEN** the archive verifies, the environment compiles, the checkpoint loads, and bounded inference remains finite
- **THEN** the bundle is marked ready and receives size, content type, and checksum metadata in the artifact manifest

### Requirement: Simulator-only disclosure
The archive README, artifact metadata, API response, and result UI SHALL state that the policy bundle is for the pinned simulator contract and is not directly deployable to a physical robot. They SHALL explain that real deployment requires independent control-rate, sensor/actuator mapping, safety, calibration, latency, dynamics-transfer, and hardware validation work.

#### Scenario: User views or downloads a bundle
- **WHEN** a completed custom result exposes the policy bundle
- **THEN** the simulator-only notice is visible before download and included inside the archive

#### Scenario: Evaluation succeeds in simulation
- **WHEN** a custom policy meets its simulation task threshold
- **THEN** neither the UI nor bundle describes it as production-ready, hardware-safe, or physically deployable

