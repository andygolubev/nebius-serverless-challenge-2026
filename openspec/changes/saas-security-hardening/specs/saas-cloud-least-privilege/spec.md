# saas-cloud-least-privilege Delta

## ADDED Requirements

### Requirement: Scoped cloud credential
The SaaS service account SHALL be granted a custom cloud IAM role scoped to only the operations the
application performs: creating, getting, and listing Serverless AI jobs within the configured
project, and reading and writing the configured artifact bucket. The service account SHALL NOT hold
an administrative or broader role in steady state. The scoped grant SHALL be declared in the
project's infrastructure definitions (not applied only by hand), and the cutover from the temporary
admin grant SHALL be staged so a submission is proven under the scoped role before the admin grant
is removed.

#### Scenario: App operates under the scoped role
- **WHEN** the SaaS service account holds only the scoped custom role
- **THEN** job submission, status polling, and artifact reads all succeed without an administrative
  role

#### Scenario: Broad resource creation is denied
- **WHEN** an actor uses the SaaS service-account token to create a cloud resource outside the
  allowed job and bucket operations
- **THEN** the cloud rejects the call because the role does not grant it

#### Scenario: Staged cutover proves the role before admin removal
- **WHEN** the scoped role is bound alongside the existing admin grant
- **THEN** a test job is submitted successfully under the scoped role before the admin grant is
  removed, and the admin grant is removed thereafter

### Requirement: Cloud-side spend guardrail
The project SHALL have a spend or resource guardrail configured at the cloud provider (for example a
project budget limit or a cap on concurrent GPU instances) that bounds worst-case cost independently
of the application. The guardrail SHALL be declared in infrastructure where the provider API allows,
and otherwise recorded as a required operational control with its specific limits in the runbook.

#### Scenario: Runaway creation is bounded at the cloud
- **WHEN** more resources are requested than the project guardrail permits
- **THEN** the cloud provider refuses further creation regardless of the application's own behavior

### Requirement: Pod egress containment
The SaaS pod SHALL be subject to a Kubernetes `NetworkPolicy` that permits egress only to the
Nebius API endpoints, the S3 artifact endpoint, and cluster DNS, and denies other egress. Where the
cluster CNI does not enforce `NetworkPolicy`, this requirement SHALL be recorded as pending on the
CNI and SHALL NOT be treated as an active control.

#### Scenario: Only expected egress is allowed
- **WHEN** the pod attempts an outbound connection to a destination other than the Nebius API, the
  S3 endpoint, or DNS, on a CNI that enforces network policy
- **THEN** the connection is denied

### Requirement: Nebius-backend submission allowlist
Access to the `nebius` orchestration backend SHALL be gated by an operator-managed email allowlist
(`SAAS_ALLOWED_EMAILS`, normalized addresses). A `POST /jobs` request under the `nebius` backend
from a session whose email is not on the allowlist SHALL be rejected with `403` and a neutral
message that does not reveal the allowlist. Login and code verification SHALL remain open to any
email so account-enumeration resistance is preserved. When `SAAS_ORCHESTRATION_BACKEND=nebius` and
the allowlist is empty, the application SHALL fail startup validation. The `mock` backend SHALL
ignore the allowlist. The allowlist SHALL NOT limit, throttle, or alter jobs for allowlisted
tenants; it only gates who may reach the backend.

#### Scenario: Allowlisted tenant submits unchanged
- **WHEN** an allowlisted session posts a job under the `nebius` backend
- **THEN** the job is created and runs exactly as designed, with no added limit or throttle

#### Scenario: Non-allowlisted tenant is refused the backend
- **WHEN** a non-allowlisted session posts a job under the `nebius` backend
- **THEN** the system responds 403 with a neutral message and no Nebius job is created

#### Scenario: Real backend refuses to start unguarded
- **WHEN** the application starts with `SAAS_ORCHESTRATION_BACKEND=nebius` and no allowlist set
- **THEN** startup validation fails and the pod does not become ready

#### Scenario: Mock backend stays open
- **WHEN** the application runs the `mock` backend with `SAAS_ALLOWED_EMAILS` unset
- **THEN** any authenticated tenant can submit, unchanged from today
