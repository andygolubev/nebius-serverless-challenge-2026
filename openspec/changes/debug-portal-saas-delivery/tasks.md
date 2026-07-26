## 1. Debug-portal image delivery

- [x] 1.1 Update the SaaS image workflow to build relevant `debug-portal` pushes and advance only that branch's GitOps image tag.
- [x] 1.2 Update the GitOps workflow assertion for the temporary deployment-branch contract.

## 2. Verification and delivery

- [x] 2.1 Run the workflow assertion, YAML validation, strict OpenSpec validation, and whitespace checks.
- [x] 2.2 Record local verification, commit the change, and push only `debug-portal`.
- [x] 2.3 Verify the GitHub Actions run publishes the immutable image and the bot GitOps commit updates `debug-portal`.

## 3. Live Argo CD cutover

- [x] 3.1 Independently verify the SaaS server's changed SSH host key and repair local trust.
- [x] 3.2 Repoint, refresh, and sync the live root Argo CD Application to `debug-portal`.
- [x] 3.3 Verify root/child Application sync and health, the SaaS workload image and readiness, and public health.
