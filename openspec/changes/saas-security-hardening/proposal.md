# Shrink the Admin-Credential Blast Radius of the SaaS Control Plane

## Why

The SaaS pod holds a **Nebius service-account token with an admin role** on the cloud parent (a
workaround until Nebius support restores least-privilege), and the app is exposed on the public
internet. A code audit confirmed the tenant job-submission path is tightly constrained — tenant
input never controls the image, command, resource type, quantity, or timeout, only the fixed
server-side presets — so **no application request can create an arbitrary cloud resource today**.

The real exposure is blast radius: the admin token can create or delete *any* resource, so any
future code-execution or file-read bug (including one in an unmanaged dependency) becomes a full
cloud takeover and unlimited GPU spend. This change removes that leverage without touching the
designed jobs: scope the credential, cap spend at the cloud, contain the pod, manage the
dependency surface, and blunt the two bugs that would matter most (token theft via XSS, arg
injection into the training command).

## What Changes

- **Least-privilege cloud credential**: replace the admin role on the SaaS service account with a
  custom role scoped to exactly what the app needs — create/get/list Serverless AI jobs in the one
  project and read/write the one artifact bucket — codified in the Nebius infra.
- **Cloud-side spend guardrail**: a project budget/quota limit in Nebius, documented and (where the
  API allows) declared in infra, so runaway spend is capped even if the token is fully stolen.
- **Pod egress containment**: a Kubernetes `NetworkPolicy` restricting the SaaS pod's egress to the
  Nebius API, the S3 endpoint, and DNS, so a compromised pod cannot freely reach the cloud API
  surface or exfiltrate.
- **Submission allowlist (who, not how much)**: an operator-managed email allowlist gating access
  to the `nebius` backend, so the internet-facing authenticated surface behind the admin token is
  not open to anonymous self-registration. **This does not limit the designed jobs** — allowlisted
  tenants submit exactly as today.
- **Supply-chain management**: a dependency lockfile (pinned direct *and* transitive versions) and
  a CVE-scan gate in the image build, so a transitive RCE cannot silently ride in next to the admin
  token.
- **Defense-in-depth on the two highest-value bugs**:
  - pass the Serverless AI container command as a real argument list rather than a space-joined
    string, removing a latent arg-injection foothold;
  - security response headers (CSP, `nosniff`, `frame-ancestors`, `Referrer-Policy`, HSTS) to
    blunt XSS-based theft of the `localStorage` session token.
- **No changes** to the preset catalog, job lifecycle, tenant isolation, or the tenant-facing API
  shape.

## Capabilities

### New Capabilities

- `saas-cloud-least-privilege`: scope the cloud credential to the app's actual needs, cap spend at
  the project, contain pod egress, and gate `nebius`-backend access to an allowlist — bounding what
  any compromise can do.
- `saas-supply-chain-security`: pin and lock all dependency versions and fail the image build on
  known-vulnerable packages.

### Modified Capabilities

- `saas-nebius-orchestration`: the SDK adapter SHALL pass the container command as a discrete
  argument list (not a space-joined string), and job submission SHALL require the credential to be
  the scoped role.
- `saas-tenant-app`: all HTTP responses SHALL carry security hardening headers, and the served
  frontend SHALL operate under the resulting Content-Security-Policy.

## Impact

- **Cloud infra** (`sim2policy/infra/nebius/`): new custom IAM role definition and binding
  replacing the admin grant; project budget/quota resource or documented console guardrail.
- **Deploy** (`deploy/manifests/saas/`): new `NetworkPolicy`; env wiring for the submission
  allowlist; security-headers behaviour verified against the built frontend.
- **Backend** (`saas/backend/app/`): `nebius_client.py` (args as list), `main.py` (allowlist check
  on `POST /jobs` for the `nebius` backend, security-headers middleware), `settings.py`
  (allowlist config, startup validation).
- **Build/CI** (`saas/backend/`, `.github/workflows/saas-image.yml`): dependency lockfile;
  `pip-audit`/Trivy scan step gating the image.
- **Frontend** (`saas/frontend/src/`): surface a clear message when a non-allowlisted account is
  refused the `nebius` backend (403); no API-shape change.
- **Ops** (`saas/API_RUNBOOK.md`): security-operations section — managing the allowlist, the budget
  guardrail, and cutting over from the admin role to the scoped role.
- **Explicitly not affected**: the preset catalog and per-request job design (image, command,
  platform, timeout, step caps), tenant isolation, and the mock backend.
