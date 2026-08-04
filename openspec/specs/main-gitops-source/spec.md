# main-gitops-source Specification

## Purpose
Point the repository's GitOps source and write access at the `main` branch, with the live cluster
cutover performed as a separate, independently verified manual step.

## Requirements
### Requirement: Main GitOps source is explicit
The repository SHALL declare `main` as the Argo CD source revision for the root bootstrap
and all repository-owned child Applications.

#### Scenario: Fresh bootstrap uses the main branch
- **WHEN** the SaaS control plane is bootstrapped with the repository's documented/default Argo CD
  configuration
- **THEN** the root Application resolves `deploy/argocd` from `main`

#### Scenario: Child Applications remain on the main branch
- **WHEN** the root Application reconciles its child Application manifests from `main`
- **THEN** each repository-owned child Application declares `main` as its source revision

### Requirement: Main is the development and deployment branch
The repository agent instructions SHALL permit commits and pushes only to `main`.

#### Scenario: Agent prepares a deployment change
- **WHEN** an agent commits or pushes a repository change while the policy is in effect
- **THEN** it updates the `main` branch and does not update any other branch ref

### Requirement: Live root cutover is manual and verified
The live root Argo CD Application SHALL be manually updated to `main` only after the
server SSH host key has been independently verified, then refreshed and verified healthy.

#### Scenario: Manual cluster cutover
- **WHEN** the `main` branch has been pushed and the server's SSH host key is verified
- **THEN** an operator updates the root Application source revision to `main`, refreshes
  and syncs it, and confirms the root/child Applications and SaaS workload are healthy
