# saas-control-plane-infra Specification

## Purpose
Provision the always-on SaaS control plane on Nebius: the `saas-server` VM with a static public IP
and dedicated service account, cloud-init bootstrap of single-node k3s and ArgoCD, a minimal ingress
surface (SSH + HTTPS, plus HTTP only for ACME/redirect; cluster management over an SSH tunnel), and MysteryBox-backed credentials
with least-privilege IAM.

## Requirements

### Requirement: SaaS control-plane VM
The system SHALL provision a single long-lived Nebius CPU compute instance named `saas-server`
through OpenTofu/Terraform in `sim2policy/infra/nebius/`, with a static public IP, a dedicated
service account, and a boot disk based on the `ubuntu24.04-driverless` image family. The instance
platform and preset SHALL be parameterized with defaults of `cpu-e2` / `2vcpu-8gb`.

#### Scenario: Plan provisions the server
- **WHEN** `tofu plan` runs against the Nebius infra with valid `project_id`, `tenant_id`, and
  `subnet_id`
- **THEN** the plan includes exactly one `nebius_compute_v1_instance` named `saas-server` with a
  static public IP, a dedicated service account, and a `cloud_init_user_data` value

#### Scenario: Server is reachable after apply
- **WHEN** `tofu apply` completes and the VM boots
- **THEN** the static public IP is exposed as a Terraform output and SSH with the configured
  `ssh-ed25519` key succeeds

### Requirement: k3s and ArgoCD bootstrap via cloud-init
The `saas-server` cloud-init user data SHALL install a single-node k3s cluster and bootstrap ArgoCD
into it non-interactively on first boot, and SHALL be idempotent so a re-run does not corrupt an
existing cluster.

#### Scenario: Fresh boot installs the stack
- **WHEN** the VM boots for the first time
- **THEN** k3s is installed and `kubectl get nodes` reports the node `Ready`, and the ArgoCD
  namespace and core ArgoCD workloads are created

#### Scenario: Bootstrap is idempotent
- **WHEN** cloud-init or the bootstrap script runs again on an already-provisioned VM
- **THEN** it completes without error and does not delete or duplicate the existing k3s cluster or
  ArgoCD installation

### Requirement: Minimal ingress and tunnel-only cluster management
The `saas-server` SHALL restrict inbound network access to only the necessary ports: SSH (22) and
HTTPS (443), with HTTP (80) permitted only for ACME challenge / redirect to HTTPS. The Kubernetes API
server and the ArgoCD admin interface SHALL NOT be reachable from the public internet; operators
SHALL manage the cluster over an SSH tunnel (services bound to loopback and reached via `ssh -L`).

#### Scenario: Only SSH and HTTPS are reachable
- **WHEN** the server's public IP is port-scanned from the internet
- **THEN** only 22 and 443 (and optionally 80 for ACME/redirect) accept connections, and all other
  ports — including the Kubernetes API and the ArgoCD UI — are refused/filtered

#### Scenario: Cluster is managed via SSH tunnel
- **WHEN** an operator forwards the local port to the cluster API/ArgoCD with
  `ssh -L <local>:localhost:<remote>` and runs `kubectl` / opens ArgoCD against the forwarded port
- **THEN** management succeeds through the tunnel while the same endpoints remain unreachable
  directly from the public IP

### Requirement: MysteryBox-backed credentials and least-privilege IAM
The infra SHALL store the GitHub access token and, when required, the Nebius Registry pull
credential as Nebius MysteryBox secrets, and SHALL grant the `saas-server` service account only the
permissions it needs (registry pull and reading those secrets). Secret values SHALL NOT appear in
Terraform outputs, logs, or committed files.

#### Scenario: Secrets are stored in MysteryBox, not in Git
- **WHEN** the infra is applied
- **THEN** the GitHub token and any registry pull credential exist as MysteryBox secrets referenced
  by selector, and no plaintext secret value is present in any `.tf` file, state output, or repo
  file

#### Scenario: Server identity is least-privilege
- **WHEN** the `saas-server` service account's permissions are reviewed
- **THEN** it holds only registry-pull and secret-read permissions required for delivery, and no
  broad account- or project-admin role
