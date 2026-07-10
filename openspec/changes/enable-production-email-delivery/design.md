## Context

The auth API and UI are functioning as designed, but the public deployment pins `SAAS_EMAIL_BACKEND=mock`. A live read-only check on 2026-07-11 confirmed the pod is healthy, emitted the mock-backend startup warning, and recorded a mock delivery after a user request. The existing SMTP adapter is a useful starting point, but it always calls STARTTLS, has no timeout or configuration validation, lets provider exceptions escape, and stores a pending code before delivery succeeds.

The SaaS runs as one FastAPI container in k3s and is reconciled by ArgoCD. The VM can read MysteryBox through its identity, while secret values must not enter Git, container images, command output, OpenTofu state, or the implementation log. Sessions and auth rate limits remain in process and the deployment intentionally has one replica.

## Goals / Non-Goals

**Goals:**

- Deliver login codes from the public site through a real transactional email service.
- Preserve a provider-neutral SMTP boundary so a provider can be selected or replaced without application changes.
- Prevent false-success responses and unusable pending codes when delivery fails.
- Bound network calls, validate configuration early, and expose only sanitized operational evidence.
- Make credential provisioning, rotation, live verification, and rollback reproducible without disclosing secrets.
- Improve inbox placement by authenticating the sender domain.

**Non-Goals:**

- Replacing one-time-code authentication, changing session persistence, or adding social login.
- Building a general notification, marketing email, bounce-processing, or email-template platform.
- Committing a specific vendor's credentials or coupling the application to a proprietary provider API.
- Guaranteeing placement in every recipient's inbox; the system can prove provider acceptance and test representative delivery, not control recipient filtering.

## Decisions

### 1. Use an authenticated transactional provider through SMTP

The production adapter will remain `smtp` and target a transactional email provider over authenticated SMTP. Configuration will include host, port, username, password, envelope/header sender, TLS mode, and connection timeout. `starttls` on port 587 is the deployment default; the adapter will reject unsupported or internally inconsistent settings at startup. Local and automated-test environments retain `mock` explicitly.

This preserves the existing abstraction and standard-library implementation. A provider-specific HTTP SDK was considered, but it would add a dependency and lock the auth path to one vendor without solving the current deployment problem. Personal mailbox SMTP was considered as a quick workaround, but is a poor production default because of account-level sending limits, weaker operational isolation, and deliverability controls.

### 2. Store provider material in MysteryBox and reconcile a dedicated Kubernetes Secret

OpenTofu will manage the MysteryBox secret container and least-privilege read permit, but not the credential payload. An operator will create/rotate payload versions out of band. A root-owned, least-privilege reconciliation unit on `saas-server` will resolve the selected version with the VM identity and server-side apply a `saas-smtp` Secret containing the `SAAS_SMTP_*` keys. Output will report only the destination and key names.

The Deployment will set `SAAS_EMAIL_BACKEND=smtp` and consume `saas-smtp` as a non-optional `envFrom` reference. Making the reference non-optional prevents a rollout from silently falling back or starting without credentials. Reusing `saas-nebius` was rejected because email credentials have a separate owner, rotation schedule, and failure domain.

### 3. Authenticate a project-owned sender domain before cutover

The operator will choose a project-owned From address and complete the provider's domain verification. Provider-issued DKIM records and the authorized SPF include will be published, with a DMARC record beginning in monitoring mode and tightened after observing legitimate traffic. The visible From address must be within the verified domain and match provider policy.

Using an unverified or unrelated From address was rejected because providers may refuse it and recipients are more likely to classify it as spoofed or spam.

### 4. Treat provider acceptance as part of request success

`EmailSender.send_code` will raise a typed, sanitized delivery error for SMTP connection, TLS, authentication, timeout, and recipient/provider rejection failures. `AuthService.request_code` will delete the newly stored pending code if delivery does not complete. The attempt remains rate-limited even on provider failure to avoid turning outages into an unbounded abuse path.

The API will translate the typed error to `503 Service Unavailable` with a generic retry message and may include `Retry-After`; it will never return provider text, hostnames, usernames, recipient details, passwords, or the one-time code. Successful provider acceptance remains `200`. Persisting the code only after sending was considered, but creates a small race where a very fast recipient can submit a code before it exists; write-then-delete gives consistent verification semantics.

### 5. Bound delivery and expose sanitized readiness evidence

SMTP connection and I/O use an explicit short timeout. Startup validates the selected backend and required non-secret shape (required fields, valid port/timeout, sender format, allowed TLS mode). The health response may identify the configured backend and configuration readiness, but will not make a live SMTP connection on every probe. Delivery logs use event/result/category and latency only; recipient addresses are omitted or irreversibly minimized, and codes/provider responses are never logged.

Provider dashboards and a bounded live test supply external acceptance evidence. Automated tests will use fakes and a local scripted SMTP double; they will not need real credentials or send public email.

## Risks / Trade-offs

- [SMTP provider outage or throttling blocks sign-in] → Return bounded `503`, preserve request rate limiting, monitor categorized failures, and document rollback to a previously validated provider configuration.
- [DNS authentication takes time to propagate] → Create and verify DNS records before changing GitOps to `smtp`; test representative Gmail and another mailbox after the provider reports verification.
- [Secret reconciliation or rotation causes a bad rollout] → Validate required keys without printing values, keep the old MysteryBox version available, restart one replica only after reconciliation, and roll back the selector/config if acceptance fails.
- [Synchronous SMTP adds request latency] → Enforce a short timeout and measure delivery latency; asynchronous queuing is deferred until traffic justifies its added persistence and retry complexity.
- [A provider accepts mail but a recipient filters it] → Use SPF, DKIM, DMARC, a stable project-owned From address, and provider delivery events; document that `200` means provider acceptance rather than guaranteed inbox placement.
- [Mock mode is accidentally redeployed publicly] → Pin `smtp` in the production manifest and add a deploy/test assertion that the live backend is not `mock`.

## Migration Plan

1. Select a transactional provider, create a least-privilege SMTP credential, choose the sender address, and publish/verify the required SPF, DKIM, and DMARC DNS records.
2. Add the MysteryBox secret container and read permit, create the credential payload version out of band, and install/verify the `saas-smtp` reconciliation unit without exposing values.
3. Implement and locally test configuration validation, timeouts, typed failures, pending-code cleanup, sanitized logs, and API `503` behavior while production remains in mock mode.
4. Reconcile `saas-smtp`, verify only expected key names and a successful bounded SMTP handshake/test message, then change GitOps to `SAAS_EMAIL_BACKEND=smtp` with the required Secret reference.
5. Confirm ArgoCD is Synced/Healthy, request one code from the public UI, verify receipt and one-time sign-in, inspect provider acceptance/authentication results, and confirm no code or credential appears in application logs.
6. Record non-secret results and cleanup in `IMPLEMENTATION_LOG.MD`. Rotate any credential exposed during testing.

Rollback: revert the Deployment to the last validated email configuration and prior MysteryBox version, then restart the single pod and re-run health checks. `mock` may be used only for an explicitly operator-controlled maintenance/demo window because public users cannot retrieve its codes; the UI must not be left presenting mock delivery as real email.

## Open Questions

- Which transactional provider account and project-owned sender domain/address will the operator supply? The implementation remains provider-neutral, but production cutover cannot complete until these external inputs and DNS control are available.

