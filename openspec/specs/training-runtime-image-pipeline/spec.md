# training-runtime-image-pipeline Specification

## Purpose
Build, validate, and publish the Sim2Policy training runtime container images (the `sb3` and `mjx`
Dockerfile targets) from GitHub Actions to the Nebius Registry, with an immutable commit-derived
tag published before the moving compatibility tag and least-scope, non-leaking registry
authentication.

## Requirements

### Requirement: SB3 runtime image build
CI SHALL build the `sb3` target from `sim2policy/Dockerfile` using the repository's Sim2Policy source and SHALL fail before registry publication if the image build or configured health/import gate fails.

#### Scenario: Sim2Policy change reaches main
- **WHEN** a push to `main` changes a path under `sim2policy/` or the runtime workflow itself
- **THEN** CI builds and validates the SB3 runtime image

#### Scenario: Image validation fails
- **WHEN** the Docker build or health/import gate exits non-zero
- **THEN** CI fails and does not update any registry tag

### Requirement: Authenticated least-scope publication
CI SHALL authenticate to the existing Nebius registry with the existing `sim2policy-saas-ci` account's masked registry credentials and SHALL pass the token through standard input. The workflow MUST NOT place credential values in source, image layers, command arguments, or logs.

#### Scenario: Registry login and push
- **WHEN** the workflow runs in a trusted push or manual-dispatch context
- **THEN** it authenticates as the existing CI identity and pushes only to the configured Sim2Policy repository

#### Scenario: Untrusted pull request
- **WHEN** the workflow executes for an untrusted pull-request context
- **THEN** it does not receive or use registry credentials and does not push an image

### Requirement: Immutable and compatibility tags
For each successful trusted build, CI SHALL publish an immutable commit-derived tag before updating `sim2policy:sb3-runtime`, SHALL ensure both references identify the same image content, and SHALL report the immutable reference and resulting digest for downstream use.

#### Scenario: Successful publication
- **WHEN** the immutable image push succeeds
- **THEN** CI updates `sb3-runtime` to the same image and reports the commit tag and digest

#### Scenario: Immutable push fails
- **WHEN** publishing the commit-derived tag fails
- **THEN** CI fails without updating `sb3-runtime`

### Requirement: Bounded workflow operation
The runtime workflow SHALL use concurrency cancellation for superseded revisions and SHOULD use BuildKit cache without making correctness depend on cache availability. It SHALL support manual dispatch for recovery after credential or registry outages.

#### Scenario: New revision supersedes an active build
- **WHEN** a newer commit starts in the same workflow concurrency group
- **THEN** the older in-progress build is cancelled and only the current revision may update `sb3-runtime`

#### Scenario: Manual recovery
- **WHEN** an authorized operator dispatches the workflow after a transient outage
- **THEN** the selected revision is rebuilt and published under its immutable tag before the compatibility tag is updated
