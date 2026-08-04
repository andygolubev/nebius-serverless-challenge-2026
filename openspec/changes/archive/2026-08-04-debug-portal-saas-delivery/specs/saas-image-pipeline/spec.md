## MODIFIED Requirements

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
