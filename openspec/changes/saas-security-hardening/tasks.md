# Tasks: Shrink the Admin-Credential Blast Radius

## 1. Cloud guardrails (deployable first, no image change)

- [ ] 1.1 Set a project-level spend/resource guardrail in Nebius (budget limit and/or concurrent
      GPU-instance cap); record the exact limits and where they are set
- [ ] 1.2 Declare the guardrail in `sim2policy/infra/nebius/` if the provider API/Terraform supports
      it; otherwise document it as a required console control in `saas/API_RUNBOOK.md`
- [ ] 1.3 Define a custom least-privilege IAM role (create/get/list Serverless AI jobs in the
      project + read/write the artifact bucket) in `sim2policy/infra/nebius/` and bind it to the
      SaaS service account **alongside** the existing admin grant

## 2. Cutover to the scoped role

- [ ] 2.1 With both roles bound, submit a real test job and confirm submission, polling, and
      artifact read all succeed under the scoped role (identify any missing permission and add it)
- [ ] 2.2 Remove the admin role binding from the SaaS service account; re-verify a job end-to-end
- [ ] 2.3 Document the staged-cutover and rollback procedure in `saas/API_RUNBOOK.md`

## 3. Dependency supply chain

- [ ] 3.1 Generate a fully pinned lockfile (direct + transitive) for the backend with `uv` or
      `pip-compile`; commit it
- [ ] 3.2 Update `saas/Dockerfile` to install from the lockfile instead of resolving at build time
- [ ] 3.3 Add a vulnerability-scan step (`pip-audit` and/or Trivy image scan) to
      `.github/workflows/saas-image.yml` that fails the build at or above a defined severity;
      verify a clean set passes and a seeded vulnerable pin fails

## 4. Backend defense-in-depth

- [ ] 4.1 Change `SdkJobsClient.create_job` to pass the container command as the SDK's argument
      list rather than `" ".join(...)`; confirm the SDK `JobSpec.args` field type and update the
      fake client / tests to assert a list is passed
- [ ] 4.2 Add `SAAS_ALLOWED_EMAILS` parsing + startup validation in `settings.py`/`main.py`: fail
      startup when `SAAS_ORCHESTRATION_BACKEND=nebius` and the allowlist is empty; ignore under
      `mock`
- [ ] 4.3 Enforce the allowlist in `POST /jobs` only under the `nebius` backend → neutral 403;
      allowlisted tenants unchanged; add tests for allowlisted pass, non-allowlisted 403, and
      startup fail-fast
- [ ] 4.4 Add a security-headers middleware (CSP `default-src 'self'` + configurable media/connect
      origins, `nosniff`, `Referrer-Policy: no-referrer`, `frame-ancestors 'none'`/`X-Frame-Options:
      DENY`, HSTS when behind TLS); assert headers on API and static responses in tests

## 5. Deploy and frontend

- [ ] 5.1 Add a `NetworkPolicy` in `deploy/manifests/saas/` allowing egress only to the Nebius API,
      the S3 endpoint, and DNS; note in the runbook whether the cluster CNI enforces it
- [ ] 5.2 Wire `SAAS_ALLOWED_EMAILS` and any CSP media/connect origins into the deploy manifests
- [ ] 5.3 Handle the 403 not-allowlisted response in `api.ts`/the composer view with a clear
      user-facing message distinct from generic errors
- [ ] 5.4 Build the frontend and confirm it operates under the CSP (fix inline styles/scripts or
      extend configured origins rather than loosening the policy)

## 6. Verify on the deployed server

- [ ] 6.1 Confirm a job submits and completes under the scoped role with admin removed
- [ ] 6.2 Confirm a non-allowlisted account gets 403, security headers are present on `/` and API
      responses, the CVE gate is green, and existing UI flows work under CSP
