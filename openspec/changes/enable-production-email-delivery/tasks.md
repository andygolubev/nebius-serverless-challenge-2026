## 1. Provider and sender prerequisites

- [ ] 1.1 Select a transactional SMTP provider and project-owned From address; record only non-secret host/port/TLS and ownership decisions in `IMPLEMENTATION_LOG.MD`
- [ ] 1.2 Publish the provider-required SPF and DKIM records plus a DMARC monitoring record, then verify the sender domain in the provider without recording verification tokens in Git or logs
- [ ] 1.3 Create a dedicated least-privilege SMTP credential and keep its value only in the approved external-secret workflow

## 2. Backend delivery hardening

- [ ] 2.1 Add validated SMTP configuration for required host, port, username, password, From address, allowed TLS mode, and bounded timeout while retaining explicit mock mode for local/tests
- [ ] 2.2 Add a typed delivery error that normalizes connection, timeout, TLS, authentication, recipient, and provider rejection failures without retaining provider response text or credentials
- [ ] 2.3 Update code issuance so a failed send deletes the new pending code but still consumes the request-rate-limit attempt
- [ ] 2.4 Map delivery failures in `POST /auth/request-code` to sanitized `503 Service Unavailable` responses with bounded completion and no code, recipient, or infrastructure disclosure
- [ ] 2.5 Add sanitized delivery event/category/latency logging and configuration-readiness evidence without logging codes, full recipient addresses, credentials, or provider responses

## 3. Automated verification

- [ ] 3.1 Add unit tests for valid SMTP configuration and fail-fast rejection of missing fields, invalid numeric values, sender format, and unsupported TLS modes
- [ ] 3.2 Add scripted SMTP/fake-sender tests for secure successful delivery, timeout, connection, authentication, and message rejection paths
- [ ] 3.3 Add auth API tests proving success remains `200`, delivery failures return sanitized `503`, failed codes cannot verify, and repeated failures remain rate-limited
- [ ] 3.4 Add log-capture tests proving real-delivery success and failure logs omit plaintext codes, recipients, credentials, and raw provider responses
- [ ] 3.5 Run the complete SaaS backend suite and frontend build/tests, then record commands and non-secret results in `IMPLEMENTATION_LOG.MD`

## 4. External-secret infrastructure

- [ ] 4.1 Add an OpenTofu-managed MysteryBox secret container for SMTP credentials and a resource-scoped payload-viewer permit for the SaaS VM identity, with no payload managed in state
- [ ] 4.2 Add selector-only inputs/outputs and a root-owned `saas-smtp` reconciliation service that fetches one pinned MysteryBox version and applies only expected `SAAS_SMTP_*` keys to the `saas` namespace with values suppressed from output
- [ ] 4.3 Document creation and rotation of SMTP payload versions, selector updates, reconciliation, expected-key inspection, credential revocation, and rollback in the Nebius infrastructure README
- [ ] 4.4 Validate OpenTofu formatting/configuration and rendered cloud-init; verify secret values and provider tokens are absent from the plan, repository diff, and logs
- [ ] 4.5 Apply the secret container/permit and install or update the reconciliation service on the live SaaS server without restarting unrelated workloads; reconcile `saas-smtp` and inspect key names only

## 5. GitOps production cutover

- [ ] 5.1 Change the production Deployment to `SAAS_EMAIL_BACKEND=smtp`, consume `saas-smtp` as a non-optional Secret, and retain explicit mock configuration only in local/test overlays
- [ ] 5.2 Add a manifest/deployment assertion that fails when the public deployment selects `mock` or omits the required SMTP Secret reference
- [ ] 5.3 Update `saas/README.md` with configuration fields, provider-neutral setup, DNS authentication, `503` behavior, safe diagnostics, rotation, and rollback guidance
- [ ] 5.4 Run manifest rendering/schema checks and verify rendered production configuration contains secret references and non-secret settings only
- [ ] 5.5 Deploy through the existing CI/ArgoCD path and verify the application is Synced/Healthy, the single pod is Ready, and the active backend reports `smtp` without printing any secret value

## 6. Live acceptance and handoff

- [ ] 6.1 Request one code from the public UI, confirm provider acceptance and receipt at a representative mailbox, complete one-time sign-in, and verify resend/rate-limit behavior with bounded requests
- [ ] 6.2 Confirm SPF and DKIM pass and DMARC alignment is reported for the received message; record results without copying message identifiers, addresses, codes, or provider tokens
- [ ] 6.3 Exercise a controlled invalid/unavailable SMTP configuration, verify bounded sanitized `503` behavior and unusable failed code, then restore the validated secret version and confirm recovery
- [ ] 6.4 Audit pod/provider/system logs and repository changes for leaked codes, email addresses, credentials, secret selectors, or raw SMTP responses; rotate credentials if any exposure occurred
- [ ] 6.5 Record the immutable image revision, non-secret deployment results, rollback point, blockers, and next safe action in `IMPLEMENTATION_LOG.MD`, and confirm no temporary cloud resources remain
