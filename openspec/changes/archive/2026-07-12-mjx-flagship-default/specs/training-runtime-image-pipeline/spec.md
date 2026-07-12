## ADDED Requirements

### Requirement: MJX runtime image build
CI SHALL build the `mjx` target from `sim2policy/Dockerfile` using the repository's Sim2Policy source and SHALL fail before registry publication if the image build or its MJX import gate (JAX, MuJoCo, MuJoCo Playground, sim2policy) fails.

#### Scenario: Sim2Policy change reaches main
- **WHEN** a push to `main` changes a path under `sim2policy/` or the runtime workflow itself
- **THEN** CI builds and validates the MJX runtime image alongside the SB3 runtime image

#### Scenario: MJX validation fails
- **WHEN** the MJX Docker build or import gate exits non-zero
- **THEN** CI fails the MJX leg and does not update any MJX registry tag

### Requirement: MJX immutable and compatibility tags
For each successful trusted build, CI SHALL publish an immutable commit-derived MJX tag (`sim2policy:mjx-<commit>`) before updating `sim2policy:mjx-runtime`, SHALL ensure both references identify the same image content, and SHALL report the immutable reference and resulting digest for downstream use.

#### Scenario: Successful MJX publication
- **WHEN** the immutable MJX image push succeeds
- **THEN** CI updates `mjx-runtime` to the same image and reports the commit tag and digest

#### Scenario: MJX immutable push fails
- **WHEN** publishing the commit-derived MJX tag fails
- **THEN** CI fails without updating `mjx-runtime`

### Requirement: Sampled MJX accelerator telemetry
MJX training SHALL sample accelerator utilization throughout setup, compilation/training, and artifact publication, SHALL record aggregate utilization and phase timing in the runtime artifact, and SHALL preserve compatibility with existing start/end telemetry consumers.

#### Scenario: Short GPU work occurs between endpoint snapshots
- **WHEN** accelerator work occurs after the start snapshot and before the end snapshot
- **THEN** the runtime artifact reports the sampled activity, including non-zero maximum utilization and peak memory, instead of representing the end snapshot as whole-run utilization

## MODIFIED Requirements

### Requirement: Immutable and compatibility tags
For each successful trusted build, CI SHALL publish an immutable commit-derived tag that identifies the runtime target (`sim2policy:sb3-<commit>`) before updating `sim2policy:sb3-runtime`, SHALL ensure both references identify the same image content, and SHALL report the immutable reference and resulting digest for downstream use.

#### Scenario: Successful publication
- **WHEN** the immutable image push succeeds
- **THEN** CI updates `sb3-runtime` to the same image and reports the commit tag and digest

#### Scenario: Immutable push fails
- **WHEN** publishing the commit-derived tag fails
- **THEN** CI fails without updating `sb3-runtime`
