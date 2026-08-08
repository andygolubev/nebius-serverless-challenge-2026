# gitops-delivery Specification

## Purpose
Deliver the SaaS application to the k3s cluster declaratively with ArgoCD: Git is the source of
truth for what runs, credentials come from MysteryBox-provisioned secrets at runtime, and the
deployed app is exposed through the cluster ingress over HTTPS on the public domain, with HTTP kept
only for ACME challenges and redirect (see `saas-domain-tls`).

## Requirements
### Requirement: ArgoCD syncs the SaaS app from Git
ArgoCD SHALL manage the SaaS application declaratively from a Git repository using an app-of-apps
(or equivalent root `Application`) pattern, so that a qualifying GitOps image-tag commit is the only
action required to change what runs on the cluster.

#### Scenario: Git is the source of truth
- **WHEN** a Kubernetes manifest or the immutable SaaS image tag is changed and merged to the
  deployment branch
- **THEN** ArgoCD detects the drift and syncs the cluster to match Git within its polling/refresh
  interval

#### Scenario: Manual cluster edits are reconciled
- **WHEN** a resource managed by ArgoCD is edited directly on the cluster
- **THEN** ArgoCD reports the app as OutOfSync and (when auto-sync/self-heal is enabled) restores the
  Git-declared state

### Requirement: Main is the declared source revision
The repository SHALL declare `main` as the ArgoCD source revision for the root bootstrap and for
every repository-owned child `Application`, and the OpenTofu bootstrap default SHALL match, so a
server recreated from declared infrastructure does not track a different branch.

#### Scenario: Fresh bootstrap uses the main branch
- **WHEN** the SaaS control plane is bootstrapped with the repository's documented/default ArgoCD
  configuration
- **THEN** the root Application resolves `deploy/argocd` from `main`

#### Scenario: Child Applications remain on the main branch
- **WHEN** the root Application reconciles its child Application manifests
- **THEN** each repository-owned child Application declares `main` as its source revision

### Requirement: Credentials sourced from MysteryBox at runtime
ArgoCD SHALL obtain the GitHub repository token and the Nebius Registry pull credential from the
MysteryBox-provisioned secrets on the cluster, rather than from values committed to Git. The GitHub
token SHALL authorize repository access for ArgoCD; the registry credential SHALL be used as a
Kubernetes `imagePullSecret` because the node identity cannot authenticate to the registry directly.

#### Scenario: Private repo access uses the GitHub token
- **WHEN** ArgoCD connects to the application manifests repository
- **THEN** it authenticates using the GitHub token delivered from MysteryBox, and no token value is
  stored in a Git-tracked manifest

#### Scenario: Image pull uses the registry secret
- **WHEN** the k3s node pulls the SaaS image from the Nebius Registry
- **THEN** the SaaS Deployment references an `imagePullSecret` populated from the MysteryBox registry
  credential and pods pull the image successfully

### Requirement: Deployed SaaS app is reachable
The GitOps layout SHALL deploy the SaaS app as a Kubernetes `Deployment` plus `Service` and expose
it externally through the k3s ingress, served over HTTPS on the public domain per `saas-domain-tls`.

#### Scenario: App answers a health check
- **WHEN** the SaaS app is synced and its pods are Ready
- **THEN** a health endpoint served through the ingress returns a success status

### Requirement: Deployment is verified, not inferred
A deployment SHALL be confirmed through the workflow run, the GitOps image-tag commit, the ArgoCD
sync result, the rolled pod, and the public endpoint. A push alone SHALL NOT be treated as evidence
that a change is live.

#### Scenario: Operator confirms a rollout
- **WHEN** an image-tag commit reaches the deployment branch
- **THEN** the operator confirms the Application is Synced and Healthy, the pod runs the expected
  immutable image, and the public endpoint serves it

#### Scenario: A live image override masks the Git tag
- **WHEN** the live `saas` Application carries a `kustomize.images` override in its own spec
- **THEN** that override takes precedence over the committed tag and the deployment is investigated
  at the Application before the image workflow
