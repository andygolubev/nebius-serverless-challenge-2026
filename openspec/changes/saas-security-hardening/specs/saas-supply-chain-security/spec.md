# saas-supply-chain-security Delta

## ADDED Requirements

### Requirement: Fully pinned dependency lockfile
The backend SHALL install its Python dependencies from a lockfile that pins exact versions of both
direct and transitive packages, and the container image build SHALL install from that lockfile
rather than resolving versions at build time. The lockfile SHALL be regenerated deliberately when
dependencies are updated.

#### Scenario: Reproducible install from the lock
- **WHEN** the container image is built at two different times without changing the lockfile
- **THEN** the same exact package versions (direct and transitive) are installed both times

#### Scenario: Transitive versions are pinned
- **WHEN** the lockfile is inspected
- **THEN** transitive dependencies of `nebius` and `boto3` (for example the gRPC, protobuf,
  cryptography, and urllib3 packages) have exact pinned versions

### Requirement: Vulnerability scan gate in the image build
The image build pipeline SHALL run a dependency/image vulnerability scan (for example `pip-audit`
and/or a container image scanner) and SHALL fail the build when a known-vulnerable package at or
above a defined severity is present, so a vulnerable dependency cannot ship alongside the
cloud credential.

#### Scenario: Vulnerable dependency fails the build
- **WHEN** the pinned dependency set contains a package with a known vulnerability at or above the
  configured severity threshold
- **THEN** the image build fails and the image is not published

#### Scenario: Clean dependency set passes
- **WHEN** the scan finds no vulnerabilities at or above the threshold
- **THEN** the build proceeds and publishes the image
