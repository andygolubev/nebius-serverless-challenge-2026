## MODIFIED Requirements

### Requirement: ArgoCD syncs the SaaS app from Git
ArgoCD SHALL manage the SaaS application declaratively from a Git repository using an app-of-apps (or
equivalent root `Application`) pattern, tracking the `main` branch during the temporary
debug deployment workflow, so that a merge to that branch is the only action required to change
what runs on the cluster.

#### Scenario: Git is the source of truth
- **WHEN** a Kubernetes manifest for the SaaS app is changed and merged to `main`
- **THEN** ArgoCD detects the drift and syncs the cluster to match Git within its polling/refresh
  interval

#### Scenario: Manual cluster edits are reconciled
- **WHEN** a resource managed by ArgoCD is edited directly on the cluster
- **THEN** ArgoCD reports the app as OutOfSync and (when auto-sync/self-heal is enabled) restores the
  `main` Git-declared state
