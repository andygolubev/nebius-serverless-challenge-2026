## MODIFIED Requirements

### Requirement: CI builds and pushes the SaaS image
A GitHub Actions workflow SHALL build the SaaS application container image and push it to the existing Nebius Registry on merges to the default branch, qualifying pushes to `main`, and on version tags. Images SHALL be tagged with an immutable identifier (the commit SHA) in addition to any moving tag. Only a qualifying `main` push SHALL advance the GitOps image tag.

#### Scenario: Merge builds and pushes an image
- **WHEN** a commit is merged to the default branch
- **THEN** the workflow builds the SaaS image and pushes it to the Nebius Registry tagged with the commit SHA

#### Scenario: Main advances the GitOps image tag
- **WHEN** a qualifying push reaches `main`
- **THEN** the workflow builds and publishes the SaaS image, verifies that `main` still resolves to the build SHA, and commits the resulting immutable image tag to `main`

#### Scenario: Build failure blocks publish
- **WHEN** the image build or its tests fail
- **THEN** the workflow fails and no image is pushed to the registry
