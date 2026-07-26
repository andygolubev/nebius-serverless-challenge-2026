# debug-portal-gitops-source Specification

## Purpose
Temporarily point the repository's GitOps source and write access at the `debug-portal` branch
instead of `main` for a debug deployment workflow, with the live cluster cutover performed as a
separate, independently verified manual step.

## Requirements
### Requirement: Temporary debug-portal GitOps source is explicit
The repository SHALL declare `debug-portal` as the Argo CD source revision for the root bootstrap
and all repository-owned child Applications during the temporary debug deployment workflow.

#### Scenario: Fresh bootstrap uses the debug branch
- **WHEN** the SaaS control plane is bootstrapped with the repository's documented/default Argo CD
  configuration
- **THEN** the root Application resolves `deploy/argocd` from `debug-portal`

#### Scenario: Child Applications remain on the debug branch
- **WHEN** the root Application reconciles its child Application manifests from `debug-portal`
- **THEN** each repository-owned child Application declares `debug-portal` as its source revision

### Requirement: Main-branch writes are temporarily prohibited
The repository agent instructions SHALL prohibit commits and pushes to `main` and permit commits
and pushes only to `debug-portal` for the duration of this temporary workflow.

#### Scenario: Agent prepares a deployment change
- **WHEN** an agent commits or pushes a repository change while the policy is in effect
- **THEN** it uses the `debug-portal` branch and does not update a `main` ref

### Requirement: Live root cutover is manual and verified
The live root Argo CD Application SHALL be manually updated to `debug-portal` only after the
server SSH host key has been independently verified, then refreshed and verified healthy.

#### Scenario: Manual cluster cutover
- **WHEN** the `debug-portal` branch has been pushed and the server's SSH host key is verified
- **THEN** an operator updates the root Application source revision to `debug-portal`, refreshes
  and syncs it, and confirms the root/child Applications and SaaS workload are healthy
