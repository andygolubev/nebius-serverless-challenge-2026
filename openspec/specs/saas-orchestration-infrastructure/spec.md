## ADDED Requirements

### Requirement: Dedicated orchestration identity
The OpenTofu stack SHALL create a dedicated `sim2policy-saas-orchestrator` service account and SHALL grant project-level `editor` only to that account for Serverless AI job creation and cancellation. The grant MUST be documented as temporary until Nebius offers a job-scoped role and MUST NOT broaden the SaaS server, CI, or artifact identities.

#### Scenario: Fresh infrastructure apply
- **WHEN** the Nebius stack is applied to the configured project
- **THEN** the dedicated orchestrator service account exists with the project `editor` grant and unrelated service-account grants remain unchanged

#### Scenario: Future role narrowing
- **WHEN** a Nebius job-scoped role becomes available
- **THEN** the isolated access binding can be replaced without changing the SaaS server, CI, or artifact identities

### Requirement: Metadata-based orchestrator authentication
The stack SHALL attach the dedicated orchestrator service account to the SaaS VM, mount the VM-managed instance-metadata token file read-only into the SaaS pod, and authenticate the Nebius SDK with a renewable file bearer without a private SDK credential.

#### Scenario: Backend starts on the SaaS VM
- **WHEN** the Nebius backend constructs the SDK with the mounted metadata token file
- **THEN** the SDK uses renewable tokens for the VM's attached orchestrator identity

#### Scenario: Deployment configuration is generated
- **WHEN** `saas-nebius` is reconciled
- **THEN** it contains no orchestrator private key, credentials JSON, or credentials-file setting

### Requirement: Complete machine-readable deployment contract
The stack SHALL output the orchestrator service-account ID and every value required to construct `saas-nebius`: versioned artifact secret selector, artifact access key ID, artifact endpoint, region and bucket, project ID, subnet ID, registry pull selector when required, and SB3 job image reference. Secret-bearing outputs SHALL contain selectors only, and selector outputs consumed as immutable references MUST identify a specific MysteryBox version.

#### Scenario: Generate configuration after apply
- **WHEN** an operator or reconciliation script reads `tofu output -json`
- **THEN** it can construct the complete `saas-nebius` key set without hand-copying cloud resource IDs or resolving secret values in the operator shell

#### Scenario: Infrastructure rebuild changes an ID
- **WHEN** the subnet, registry, access key, or secret version changes through managed infrastructure
- **THEN** the corresponding output changes and downstream reconciliation uses the new value without a documentation edit

### Requirement: Identity-based Kubernetes Secret reconciliation
The infrastructure SHALL provide an idempotent mechanism on the k3s server that uses the VM identity to resolve configured MysteryBox versions and create or update the `saas-nebius` Kubernetes Secret. The mechanism MUST avoid secret values in Git, OpenTofu template arguments, process arguments, logs, and operator shell history, and MUST remove temporary secret material on success or failure.

#### Scenario: Initial server bootstrap
- **WHEN** k3s becomes ready and the secret-sync unit runs with valid selectors
- **THEN** namespace `saas` contains `saas-nebius` with the complete backend environment contract and no resolved value is logged

#### Scenario: Secret rotation
- **WHEN** an input selector is updated to a new MysteryBox version and reconciliation is rerun
- **THEN** `saas-nebius` is updated idempotently to the selected version without requiring an operator to read the value

#### Scenario: MysteryBox lookup failure
- **WHEN** VM authentication or a MysteryBox lookup fails
- **THEN** reconciliation exits non-zero, does not print the response payload, and does not leave temporary credential files behind

### Requirement: Safe infrastructure verification
The change SHALL be verified with OpenTofu formatting and validation, provider-schema inspection, and a reviewed plan against the configured remote backend before apply. Verification MUST confirm that unrelated resources are not replaced and that secret payloads do not appear in plan or state.

#### Scenario: Reviewed plan is safe
- **WHEN** the plan contains only the intended identity, access, secret-delivery, output, and bootstrap changes
- **THEN** implementation may proceed to apply and record non-secret results in the implementation log

#### Scenario: Plan proposes unrelated replacement
- **WHEN** the plan proposes replacement or deletion outside the intended resources
- **THEN** apply is blocked until the cause is resolved or the user explicitly expands scope
