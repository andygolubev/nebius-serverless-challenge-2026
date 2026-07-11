## 1. Provider and State Discovery

- [x] 1.1 Initialize `sim2policy/infra/nebius` with OpenTofu 1.12.3 and the configured remote backend, then capture the Nebius provider 0.6.22 schemas for service-account credentials, access bindings, and MysteryBox delivery without exposing state credentials
- [x] 1.2 Inspect current remote-state resource addresses and the existing project, subnet, artifact access key/secret version, registry pull secret version, registry, and `sim2policy-saas-ci` resources; decide which values are managed, imported, or supplied as explicit inputs
- [x] 1.3 Confirm the SDK's renewable file-bearer path for the VM metadata token and record that no orchestrator private credential is created or retained in OpenTofu state

## 2. Orchestrator Identity and Access

- [x] 2.1 Add the dedicated `sim2policy-saas-orchestrator` service account resource without modifying the SaaS server, CI, or artifact identities
- [x] 2.2 Add an isolated project-level `editor` access binding/permit for the orchestrator account and annotate it as a revisit point for a future job-scoped Nebius role
- [x] 2.3 Attach the orchestrator service account to the SaaS VM and give it the existing VM registry/MysteryBox reader grants
- [x] 2.4 Add the orchestrator service-account ID output and remove credentials-file plumbing from the pod contract

## 3. Deployment Output Contract

- [x] 3.1 Add or normalize outputs for project ID, current subnet ID, artifact bucket/endpoint/region/access-key ID, versioned artifact selector, versioned registry pull selector when enabled, and the SB3 job image reference
- [x] 3.2 Add a machine-readable `saas-nebius` source-contract output or helper that composes only selectors and non-secret values needed by `deploy/manifests/saas/deployment.yaml`
- [x] 3.3 Update input examples and validations so rebuilt resource IDs and secret versions come from managed resources or gitignored variables rather than copied README literals

## 4. Identity-Based Kubernetes Secret Sync

- [x] 4.1 Implement a root-owned idempotent sync script that authenticates through VM metadata, resolves only the configured MysteryBox versions, and applies the complete `saas-nebius` Secret after k3s is ready
- [x] 4.2 Ensure the script uses protected temporary files or pipes, installs cleanup traps, suppresses secret-bearing output and response bodies, and fails non-zero on partial lookup or apply failure
- [x] 4.3 Install and wire the sync script through cloud-init and a rerunnable systemd unit without embedding secret payloads in OpenTofu template arguments or process arguments
- [x] 4.4 Add a safe verification command/test that checks the Secret's namespace, key names, and reconciliation result without decoding or printing values

## 5. SB3 Runtime Image CI

- [x] 5.1 Add a focused GitHub Actions workflow triggered by trusted `main` pushes affecting `sim2policy/**`, workflow changes, and manual dispatch, with concurrency cancellation for superseded revisions
- [x] 5.2 Build the `sb3` target from `sim2policy/Dockerfile` with Buildx caching and run the image's bounded health/import validation before authentication or publication
- [x] 5.3 Authenticate with the existing `sim2policy-saas-ci` registry token through `docker login --password-stdin`, ensuring untrusted pull-request jobs cannot receive credentials or push
- [x] 5.4 Push a commit-derived immutable tag first, then update `sim2policy:sb3-runtime` to the identical image, and emit the immutable reference and registry digest in the workflow summary
- [x] 5.5 Validate workflow syntax and perform a trusted build/push; verify the immutable tag and `sb3-runtime` resolve to the same digest without printing credentials

## 6. OpenTofu Verification and Apply

- [x] 6.1 Run `tofu fmt -check`, `tofu validate`, provider-schema assertions, and cloud-init/shell static checks with OpenTofu 1.12.3 and Nebius provider 0.6.22
- [x] 6.2 Generate and review a plan against `backend.hcl`; confirm only intended resources/outputs/bootstrap data change, no unrelated replacement occurs, and no credential payload appears
- [x] 6.3 Apply the reviewed plan, record non-secret resource IDs and selectors, and verify the orchestrator identity, isolated `editor` grant, MysteryBox credential version, and output contract
- [x] 6.4 Run the k3s reconciliation unit and verify `saas-nebius` has the complete expected key set without exposing values in commands, logs, `kubectl describe`, or the implementation log

## 7. Documentation and Handoff

- [x] 7.1 Replace the manual "Serverless job orchestration for the SaaS backend" procedure in `sim2policy/infra/nebius/README.md` with output-driven apply, sync, rotation, rollback, and break-glass instructions
- [x] 7.2 Update `sim2policy/jobs/README.md` and infrastructure examples to use the rebuilt subnet/output contract and remove stale pre-rebuild identifiers
- [x] 7.3 Document the isolated `editor` exception, immutable image reference/digest workflow, required GitHub secrets, and the future migration to a job-scoped role
- [x] 7.4 Record commands, redacted observed results, blockers, cleanup/audit status, and the next safe action in `IMPLEMENTATION_LOG.MD`, then hand the published runtime image to `nebius-job-orchestration` task 6.3 for the bounded end-to-end smoke test
