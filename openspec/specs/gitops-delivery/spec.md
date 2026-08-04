# gitops-delivery Specification

## Purpose
Deliver the SaaS application to the k3s cluster declaratively with ArgoCD: Git is the source of
truth for what runs, credentials come from MysteryBox-provisioned secrets at runtime, and the
deployed app is exposed through the cluster ingress on the server's public IP — since the
`saas-domain-tls` capability, over HTTPS on the public domain, with HTTP kept only for ACME
challenges and redirect.
## Requirements
### Requirement: ArgoCD syncs the SaaS app from Git
ArgoCD SHALL manage the SaaS application declaratively from a Git repository using an app-of-apps (or equivalent root `Application`) pattern, tracking the `debug-portal` branch during the temporary debug deployment workflow, so that a qualifying GitOps image-tag commit on that branch is the only action required to change what runs on the cluster.

#### Scenario: Git is the source of truth
- **WHEN** a Kubernetes manifest or the immutable SaaS image tag is changed and merged to `debug-portal`
- **THEN** ArgoCD detects the drift and syncs the cluster to match Git within its polling/refresh interval

#### Scenario: Manual cluster edits are reconciled
- **WHEN** a resource managed by ArgoCD is edited directly on the cluster
- **THEN** ArgoCD reports the app as OutOfSync and (when auto-sync/self-heal is enabled) restores the `debug-portal` Git-declared state

### Requirement: Credentials sourced from MysteryBox at runtime
ArgoCD SHALL obtain the GitHub repository token and the Nebius Registry pull credential from the
MysteryBox-provisioned secrets on the cluster, rather than from values committed to Git. The GitHub
token SHALL authorize repository access for ArgoCD; the registry credential SHALL be used as a
Kubernetes `imagePullSecret` only when registry access cannot be granted to the node/service-account
identity directly.

#### Scenario: Private repo access uses the GitHub token
- **WHEN** ArgoCD connects to the application manifests repository
- **THEN** it authenticates using the GitHub token delivered from MysteryBox, and no token value is
  stored in a Git-tracked manifest

#### Scenario: Image pull uses the registry secret when IAM is insufficient
- **WHEN** the k3s node cannot pull from the Nebius Registry using its service-account identity alone
- **THEN** the SaaS Deployment references an `imagePullSecret` populated from the MysteryBox registry
  credential and pods pull the image successfully

### Requirement: Deployed SaaS app is reachable
The GitOps layout SHALL deploy the SaaS app as a Kubernetes `Deployment` plus `Service` and expose
it externally through the k3s ingress on the server's public IP (served over HTTPS on the public
domain per `saas-domain-tls`).

#### Scenario: App answers a health check
- **WHEN** the SaaS app is synced and its pods are Ready
- **THEN** a health endpoint served through the ingress returns a success status

