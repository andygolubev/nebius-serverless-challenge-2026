# Design: Shrink the Admin-Credential Blast Radius

## Context

Audit result: the SaaS control plane (FastAPI + React, single replica, SQLite) exposes a public
endpoint (`sim-policy-trainer-challenge.info`) whose pod mounts a **Nebius admin-role token**
(hostPath `/mnt/cloud-metadata`, [deployment.yaml:88](deploy/manifests/saas/deployment.yaml:88)).
The token can create or delete *any* resource in the tenant.

The application job path is **not** an arbitrary-resource vector: `POST /jobs` validates
environment/algorithm/params against the server catalog ([catalog.py:180](saas/backend/app/catalog.py:180)),
and the SDK submission draws image/command/platform/preset/timeout only from server-side `JobSpec`
with a re-validated run ID ([orchestration.py:137](saas/backend/app/orchestration.py:137),
[nebius_client.py:93](saas/backend/app/nebius_client.py:93)). A tenant can launch only the fixed
presets. This is the property we preserve, not change.

What makes the admin token dangerous is leverage: the whole authenticated surface is reachable by
anyone (open self-registration, [main.py:71](saas/backend/app/main.py:71)); the dependency surface
under the token is unmanaged (direct-only pins in [requirements.txt](saas/backend/requirements.txt),
no lockfile, no CVE scan in [saas-image.yml](.github/workflows/saas-image.yml)); the pod has no
egress restriction (no `NetworkPolicy`); and two latent bugs (space-joined container args, no
security headers on a `localStorage`-token app) are the kind that convert a foothold into token
theft. Existing hardening already in place and kept: read-only rootfs, non-root, all caps dropped
([deployment.yaml:81](deploy/manifests/saas/deployment.yaml:81)), and current, patched direct deps
(h11 0.16.0, starlette 0.41.3, uvicorn 0.34.0, pydantic 2.10.4).

## Goals / Non-Goals

**Goals:**
- Reduce the credential from "can create anything" to "can run the app's jobs and touch its bucket."
- Cap worst-case spend at the cloud, surviving even full token theft.
- Contain and manage the pod so a foothold is hard to escalate and easy to detect.
- Close the two bugs whose exploitation would most directly reach the token.

**Non-Goals:**
- Changing the preset catalog, job lifecycle, per-request job design, or tenant isolation.
- Adding per-tenant job quotas or rate caps on the designed jobs (explicitly out of scope per
  operator direction).
- Re-architecting auth (passwordless email flow stays) or moving the token off `localStorage`.
- Multi-replica concerns (single-replica SQLite deployment is unchanged).

## Decisions

### D1: Custom least-privilege role replaces the admin grant

Define a Nebius custom IAM role bound to the SaaS service account granting only: create/get/list on
Serverless AI jobs in the project (`parent_id`), and read/write on the single artifact bucket. This
is precisely the API surface `SdkJobsClient` and `S3ArtifactReader` use. Codify it in
`sim2policy/infra/nebius/` alongside the existing service-account definition so the grant is
declared, reviewable, and reproducible rather than a console click.

- **This is the fix the operator is "waiting on support" for** — but a *custom role* is typically
  self-serviceable now, independent of whichever default roles support is repairing. Cutover is:
  create role → bind to the SA → verify a job submits → remove the admin binding.
- *Alternative — wait for support to restore default least-privilege roles*: rejected as the sole
  plan; it leaves admin live indefinitely. The custom role can land now; if support later ships a
  suitable managed role, swap the binding.

### D2: Cloud-side spend guardrail

Set a project-level budget/quota limit in Nebius (max concurrent GPU instances or a spend cap on
the project). This is the only control that holds if the token is fully stolen, because it lives on
the cloud, not in the pod. Declare it in infra where the Nebius API/Terraform provider supports it;
otherwise document it as a required console step in the runbook with the specific limits. Independent
of all code changes and deployable first.

### D3: Egress-restricting NetworkPolicy

Add a `NetworkPolicy` selecting the SaaS pod that allows egress only to: the Nebius API endpoints,
the S3 artifact endpoint, and cluster DNS; deny all other egress. A compromised pod then cannot use
the token against arbitrary internal/external services or exfiltrate freely. Ingress stays as-is
(Traefik → pod:8000).

- *Constraint*: requires a CNI that enforces NetworkPolicy. k3s default (flannel) does not; note
  this in the runbook — if the cluster CNI doesn't enforce, this control is documentation-only
  until the CNI supports it, and D1/D2 carry the weight.

### D4: Submission allowlist gates the `nebius` backend (who, not how much)

`SAAS_ALLOWED_EMAILS` (normalized, comma-separated) is read at startup. Enforced only in `POST
/jobs` and only when the backend is `nebius`: a session whose email is not allowlisted gets `403`
with a neutral message; login stays open so enumeration resistance is preserved. Allowlisted
tenants submit exactly as today — no quota, no throttle, no change to the job.

- Fail-safe: with `SAAS_ORCHESTRATION_BACKEND=nebius` and an empty allowlist, startup fails
  (same `SettingsError` fast-fail as `NebiusSettings.from_env`), so a real-backend pod never serves
  the admin-token-backed path to the anonymous internet. The `mock` backend ignores the allowlist.
- *Alternative — gate login*: rejected; breaks enumeration resistance and the mock demo.
- This deliberately limits *who reaches the credential*, not *how much anyone runs* — distinct from
  the quota approach that was ruled out.

### D5: Dependency lockfile + CVE-scan gate

Generate a fully pinned lockfile (direct and transitive) with `uv`/`pip-compile` and install from it
in the Dockerfile, so `grpcio`/`protobuf`/`cryptography`/`urllib3` under the `nebius`/`boto3`
dependencies stop floating. Add a `pip-audit` (and/or Trivy image scan) step to
`saas-image.yml` that fails the build on known-vulnerable packages. This closes the "transitive RCE
rides in next to the admin token" path and makes the surface auditable.

### D6: Container args as a list

`SdkJobsClient.create_job` currently sends `args=" ".join(submission.args)`
([nebius_client.py:120](saas/backend/app/nebius_client.py:120)). Pass the discrete list the SDK
accepts instead. Not exploitable today (values are catalog-bounded numbers, executed in the training
container not the SaaS pod), but it removes a latent arg-injection foothold if a string-valued
param path is ever added. Verify the SDK's `JobSpec.args` field type and adjust the fake client in
tests to assert a list.

### D7: Security response headers

One Starlette middleware adds to every response: `Content-Security-Policy` (`default-src 'self'`
baseline; media/connect origins extended via config for the S3 artifact origin),
`X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `frame-ancestors 'none'` +
`X-Frame-Options: DENY`, and `Strict-Transport-Security` when behind TLS. This raises the cost of
turning an XSS into session-token theft. The built frontend must pass under the CSP (fix inline
styles/scripts rather than loosen the policy).

## Risks / Trade-offs

- [Custom role missing a permission the SDK needs] → Mitigation: stage the cutover — bind the new
  role *alongside* admin, submit a test job, confirm success, then remove admin; roll back the
  binding if a call 403s.
- [k3s CNI doesn't enforce NetworkPolicy] → Mitigation: document the dependency; D1 (scope) and D2
  (budget) are the load-bearing controls and don't depend on the CNI.
- [Allowlist locks out a legitimate new user] → Mitigation: allowlist is an env value under GitOps;
  adding an address is a one-line change. Neutral 403 avoids leaking the list.
- [CSP breaks a frontend asset] → Mitigation: verify against the built bundle in staging; extend
  origins via config, never disable CSP.
- [Lockfile drift blocks routine updates] → Mitigation: regenerate the lock on dependency bumps;
  the CVE gate flags when an update is *required*.
- [Residual: an allowlisted account compromise still reaches the scoped credential] → Accepted:
  the scoped role (D1) and budget cap (D2) bound the damage to the app's own job/bucket surface.

## Migration Plan

1. **Cloud first, independent of the image**: set the project budget guardrail (D2); create and
   bind the custom role alongside admin (D1).
2. Land backend changes behind config: args-as-list (D6), security headers (D7), allowlist check
   (D4, active only under the `nebius` backend). Add lockfile + CVE gate to the build (D5).
3. Add the `NetworkPolicy` (D3) and `SAAS_ALLOWED_EMAILS` to the deploy manifests; roll the image.
4. Verify: test job submits under the scoped role; non-allowlisted account gets 403; headers present
   on `/` and API; CVE gate green; frontend works under CSP.
5. **Remove the admin binding** once the scoped role is proven.
6. Rollback: re-add the admin binding (D1) and/or revert the image; all backend changes are additive
   and config-gated.

## Open Questions

- Does the Nebius Terraform/API surface expose a project budget or GPU-count quota as a declarable
  resource, or is D2 console-only for now? (Determines infra vs. runbook for the guardrail.)
- Does the target cluster's CNI enforce `NetworkPolicy` (D3), or is it documentation-only until the
  CNI is upgraded?
- Exact permission set for the custom role — confirm the minimal `ai.jobs`/storage actions against
  the SDK calls during the staged cutover.
