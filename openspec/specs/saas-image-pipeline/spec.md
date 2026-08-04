# saas-image-pipeline Specification

## Purpose
Build and publish the SaaS application container image to the Nebius Registry from GitHub Actions,
with immutable commit-SHA tags, publish gated on a successful build, and documented, non-leaking
registry authentication.
## Requirements
### Requirement: CI builds and pushes the SaaS image
A GitHub Actions workflow SHALL build the SaaS application container image and push it to the existing Nebius Registry on merges to the default branch, qualifying pushes to the temporary `debug-portal` deployment branch, and on version tags. Images SHALL be tagged with an immutable identifier (the commit SHA) in addition to any moving tag. During the temporary branch policy, only a qualifying `debug-portal` push SHALL advance the GitOps image tag.

#### Scenario: Merge builds and pushes an image
- **WHEN** a commit is merged to the default branch
- **THEN** the workflow builds the SaaS image and pushes it to the Nebius Registry tagged with the commit SHA

#### Scenario: Debug deployment branch advances the GitOps image tag
- **WHEN** a qualifying push reaches `debug-portal`
- **THEN** the workflow builds and publishes the SaaS image, verifies that `debug-portal` still resolves to the build SHA, and commits the resulting immutable image tag to `debug-portal`

#### Scenario: Build failure blocks publish
- **WHEN** the image build or its tests fail
- **THEN** the workflow fails and no image is pushed to the registry

### Requirement: Nebius Registry authentication in CI
The workflow SHALL authenticate to the Nebius Registry using a Nebius service account credential
supplied through GitHub Actions secrets, and the authentication method SHALL be documented so it is
reproducible. Credentials SHALL NOT be printed in workflow logs.

#### Scenario: Docker login succeeds with the CI credential
- **WHEN** the workflow runs `docker login` (or equivalent) against the registry FQDN using the
  configured GitHub Actions secret
- **THEN** authentication succeeds and the subsequent push is authorized

#### Scenario: Credentials are not leaked
- **WHEN** the workflow logs are inspected after a run
- **THEN** no registry password, token, or service-account key value appears in the logs

