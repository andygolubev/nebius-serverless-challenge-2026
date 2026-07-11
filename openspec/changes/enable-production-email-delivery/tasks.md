## 1. Provider and sender prerequisites

- [ ] 1.1 In Mailjet, add `sim-policy-trainer-challenge.info` as a sending domain under the API Key that will perform SMTP delivery and publish the exact Mailjet domain-validation TXT record
- [ ] 1.2 Publish or merge the single apex SPF TXT record `v=spf1 include:spf.mailjet.com ~all`, publish Mailjet's exact generated DKIM record, preserve the existing DMARC record, and wait until Mailjet reports domain/SPF/DKIM validation as successful
- [x] 1.3 Select `Sim2Policy <login@sim-policy-trainer-challenge.info>` as the From identity; generate the Mailjet API/Secret Key pair and place it only in the approved external-secret workflow without pasting either value into chat, shell history, Git, logs, or OpenTofu

## 2. Backend delivery hardening

- [x] 2.1 Add validated SMTP configuration with Mailjet production defaults (`in-v3.mailjet.com`, port 587, STARTTLS, 10-second timeout), API Key username, Secret Key password, validated From address, and explicit mock mode for local/tests
- [x] 2.2 Add a typed delivery error that normalizes connection, timeout, TLS, authentication, recipient, and provider rejection failures without retaining provider response text or credentials
- [x] 2.3 Update code issuance so a failed send deletes the new pending code but still consumes the request-rate-limit attempt
- [x] 2.4 Map delivery failures in `POST /auth/request-code` to sanitized `503 Service Unavailable` responses with bounded completion and no code, recipient, or infrastructure disclosure
- [x] 2.5 Add sanitized delivery event/category/latency logging and configuration-readiness evidence without logging codes, full recipient addresses, credentials, or provider responses

## 3. Automated verification

- [x] 3.1 Add unit tests for valid SMTP configuration and fail-fast rejection of missing fields, invalid numeric values, sender format, and unsupported TLS modes
- [x] 3.2 Add scripted SMTP/fake-sender tests for secure successful delivery, timeout, connection, authentication, and message rejection paths
- [x] 3.3 Add auth API tests proving success remains `200`, delivery failures return sanitized `503`, failed codes cannot verify, and repeated failures remain rate-limited
- [x] 3.4 Add log-capture tests proving real-delivery success and failure logs omit plaintext codes, recipients, credentials, and raw provider responses
- [x] 3.5 Run the complete SaaS backend suite and frontend build/tests, then record commands and non-secret results in `IMPLEMENTATION_LOG.MD`

## 4. External-secret infrastructure

- [x] 4.1 Add an OpenTofu-managed MysteryBox secret container with a write-only seven-key placeholder template and a resource-scoped payload-viewer permit for the SaaS VM identity, with no real credential or payload value stored in state
- [x] 4.2 Add selector-only inputs/outputs and a root-owned `saas-smtp` reconciliation service that fetches one pinned MysteryBox version and applies only the seven allowlisted Mailjet `SAAS_SMTP_*` keys to the `saas` namespace with values suppressed from output
- [x] 4.3 Document creation and rotation of SMTP payload versions, selector updates, reconciliation, expected-key inspection, credential revocation, and rollback in the Nebius infrastructure README
- [x] 4.4 Validate OpenTofu formatting/configuration and rendered cloud-init; verify secret values and provider tokens are absent from the plan, repository diff, and logs
- [x] 4.5 Apply the secret container/permit and install or update the reconciliation service on the live SaaS server without restarting unrelated workloads; reconcile `saas-smtp` and inspect key names only

## 5. GitOps production cutover

- [x] 5.1 Change the production Deployment to `SAAS_EMAIL_BACKEND=smtp`, consume `saas-smtp` as a non-optional Secret, and retain explicit mock configuration only in local/test overlays
- [x] 5.2 Add a manifest/deployment assertion that fails when the public deployment selects `mock` or omits the required SMTP Secret reference
- [x] 5.3 Update `saas/README.md` with the exact Mailjet SMTP mapping, sender/domain validation, SPF/DKIM and existing-DMARC handling, `503` behavior, safe diagnostics, Secret Key reset/rotation, quota monitoring, and rollback guidance
- [x] 5.4 Run manifest rendering/schema checks and verify rendered production configuration contains secret references and non-secret settings only
- [ ] 5.5 Deploy through the existing CI/ArgoCD path and verify the application is Synced/Healthy, the single pod is Ready, and the active backend reports `smtp` without printing any secret value

## 6. Live acceptance and handoff

- [ ] 6.1 Request one code from the public UI, confirm Mailjet acceptance and receipt at a representative mailbox, complete one-time sign-in, and verify resend/rate-limit behavior with bounded requests
- [ ] 6.2 Confirm SPF and DKIM pass and DMARC alignment is reported for the received message; record results without copying message identifiers, addresses, codes, or provider tokens
- [ ] 6.3 Exercise a controlled invalid/unavailable SMTP configuration, verify bounded sanitized `503` behavior and unusable failed code, then restore the validated secret version and confirm recovery
- [ ] 6.4 Audit pod/provider/system logs and repository changes for leaked codes, email addresses, credentials, secret selectors, or raw SMTP responses; rotate credentials if any exposure occurred
- [ ] 6.5 Record the immutable image revision, non-secret deployment results, rollback point, blockers, and next safe action in `IMPLEMENTATION_LOG.MD`, and confirm no temporary cloud resources remain
