## Context

The auth API and UI are functioning as designed, but the public deployment pins `SAAS_EMAIL_BACKEND=mock`. A live read-only check on 2026-07-11 confirmed the pod is healthy, emitted the mock-backend startup warning, and recorded a mock delivery after a user request. The existing SMTP adapter is a useful starting point, but it always calls STARTTLS, has no timeout or configuration validation, lets provider exceptions escape, and stores a pending code before delivery succeeds.

The SaaS runs as one FastAPI container in k3s and is reconciled by ArgoCD. The VM can read MysteryBox through its identity, while secret values must not enter Git, container images, command output, OpenTofu state, or the implementation log. Sessions and auth rate limits remain in process and the deployment intentionally has one replica.

The operator has now registered a Mailjet account and can generate an API Key plus Secret Key. Mailjet is therefore the selected production provider. A public DNS check on 2026-07-11 found no SPF record and no Mailjet DKIM record for `sim-policy-trainer-challenge.info`; the domain already has one DMARC record with `p=quarantine`, so implementation must preserve that record rather than publish a second DMARC policy.

## Goals / Non-Goals

**Goals:**

- Deliver login codes from the public site through a real transactional email service.
- Preserve a provider-neutral SMTP boundary while configuring Mailjet as the selected production provider.
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

### 1. Use Mailjet through the provider-neutral SMTP adapter

The production adapter will remain `smtp` and use Mailjet's authenticated SMTP relay. Mailjet documents `in-v3.mailjet.com` as its SMTP hostname, port 587 with TLS/STARTTLS, the Mailjet API Key as the SMTP username, and the Mailjet Secret Key as the SMTP password. The selected application configuration is:

| Setting | Production value |
|---|---|
| `SAAS_EMAIL_BACKEND` | `smtp` |
| `SAAS_SMTP_HOST` | `in-v3.mailjet.com` |
| `SAAS_SMTP_PORT` | `587` |
| `SAAS_SMTP_USER` | Mailjet API Key (secret-backed) |
| `SAAS_SMTP_PASSWORD` | Mailjet Secret Key (secret-backed) |
| `SAAS_SMTP_FROM` | `Sim2Policy <login@sim-policy-trainer-challenge.info>` |
| `SAAS_SMTP_TLS_MODE` | `starttls` |
| `SAAS_SMTP_TIMEOUT_SECONDS` | `10` |

The API Key and Secret Key are SMTP credentials; the Mailjet account email/password must not be used. Both keys are treated as confidential even though Mailjet describes the API Key as the username. Configuration validation will reject unsupported or inconsistent settings at startup. Local and automated-test environments retain `mock` explicitly.

This preserves the existing abstraction and standard-library implementation while making the deployment choice concrete. Mailjet's HTTP API/SDK was considered, but it would add a dependency and provider coupling when the current SMTP adapter already matches Mailjet's supported relay. Personal mailbox SMTP was considered as a quick workaround, but is a poor production default because of account-level sending limits, weaker operational isolation, and deliverability controls.

### 2. Store provider material in MysteryBox and reconcile a dedicated Kubernetes Secret

OpenTofu will manage the MysteryBox secret container and least-privilege read permit. On initial creation it will seed a template version through the provider's write-only `sensitive.secret_version.payload` field, which Nebius documents as omitted from state. The template contains the five fixed Mailjet settings and explicit replacement placeholders for `SAAS_SMTP_USER` and `SAAS_SMTP_PASSWORD`; it is not usable for delivery. An operator will create a new version out of band with the real API/Secret Key values and make that immutable version primary. Real credentials SHALL never appear in Terraform configuration or state. The payload contains the seven `SAAS_SMTP_*` entries shown above; `SAAS_EMAIL_BACKEND=smtp` remains non-secret GitOps configuration. A root-owned, least-privilege reconciliation unit on `saas-server` will resolve the selected version with the VM identity and server-side apply a `saas-smtp` Secret containing only those allowlisted keys. Output will report only the destination and key names.

The Deployment will set `SAAS_EMAIL_BACKEND=smtp` and consume `saas-smtp` as a non-optional `envFrom` reference. Making the reference non-optional prevents a rollout from silently falling back or starting without credentials. Reusing `saas-nebius` was rejected because email credentials have a separate owner, rotation schedule, and failure domain.

### 3. Validate and authenticate the sender in Mailjet before cutover

In Mailjet, the operator will open **Account Settings → Senders & Domains**, add `sim-policy-trainer-challenge.info` as a sending domain, and complete Mailjet's domain-ownership validation using the exact TXT record shown by the dashboard. Domain validation applies to the API Key under which it is performed, so it must be done under the same key used by SMTP.

After ownership validation, the operator will open **Setup SPF/DKIM Authentication** for the domain and publish:

- one SPF TXT record at the zone apex: `v=spf1 include:spf.mailjet.com ~all`; the 2026-07-11 lookup found no existing SPF, but implementation must re-check and merge into a single record if another sender has since added one;
- the exact Mailjet-generated DKIM record, including record type, host/selector (normally under `mailjet._domainkey`), and full public-key value shown in the dashboard; the value must not be shortened or reconstructed from this design;
- no new DMARC record: preserve the existing `_dmarc.sim-policy-trainer-challenge.info` policy and verify that Mailjet-sent mail aligns with it.

Mailjet must show the sender domain, SPF, and DKIM as validated/OK before GitOps cutover. The visible From address will be `Sim2Policy <login@sim-policy-trainer-challenge.info>`, which is covered by the validated domain. If replies need handling later, that address can be backed by a mailbox or a separate Reply-To; receiving email is not required for OTP delivery.

Using an unverified or unrelated From address was rejected because providers may refuse it and recipients are more likely to classify it as spoofed or spam.

### 4. Treat provider acceptance as part of request success

`EmailSender.send_code` will raise a typed, sanitized delivery error for SMTP connection, TLS, authentication, timeout, and recipient/provider rejection failures. `AuthService.request_code` will delete the newly stored pending code if delivery does not complete. The attempt remains rate-limited even on provider failure to avoid turning outages into an unbounded abuse path.

The API will translate the typed error to `503 Service Unavailable` with a generic retry message and may include `Retry-After`; it will never return provider text, hostnames, usernames, recipient details, passwords, or the one-time code. Successful provider acceptance remains `200`. Persisting the code only after sending was considered, but creates a small race where a very fast recipient can submit a code before it exists; write-then-delete gives consistent verification semantics.

### 5. Bound delivery and expose sanitized readiness evidence

SMTP connection and I/O use an explicit short timeout. Startup validates the selected backend and required non-secret shape (required fields, valid port/timeout, sender format, allowed TLS mode). The health response may identify the configured backend and configuration readiness, but will not make a live SMTP connection on every probe. Delivery logs use event/result/category and latency only; recipient addresses are omitted or irreversibly minimized, and codes/provider responses are never logged.

Provider dashboards and a bounded live test supply external acceptance evidence. Automated tests will use fakes and a local scripted SMTP double; they will not need real credentials or send public email.

## Risks / Trade-offs

- [SMTP provider outage or throttling blocks sign-in] → Return bounded `503`, preserve request rate limiting, monitor categorized failures, and document rollback to a previously validated provider configuration.
- [Mailjet domain validation or DNS authentication takes up to 48 hours to propagate] → Publish Mailjet's exact validation and DKIM values plus the single SPF record before changing GitOps to `smtp`; wait for Mailjet to show the domain, SPF, and DKIM as valid, then test representative Gmail and another mailbox.
- [Mailjet's free daily/monthly quota is exhausted] → Treat Mailjet quota rejection as a sanitized `503`, retain application rate limits, monitor Mailjet usage, and upgrade or switch SMTP providers before expected traffic exceeds the free allowance.
- [Secret reconciliation or rotation causes a bad rollout] → Validate required keys without printing values, keep the old MysteryBox version available, restart one replica only after reconciliation, and roll back the selector/config if acceptance fails.
- [Synchronous SMTP adds request latency] → Enforce a short timeout and measure delivery latency; asynchronous queuing is deferred until traffic justifies its added persistence and retry complexity.
- [A provider accepts mail but a recipient filters it] → Use SPF, DKIM, DMARC, a stable project-owned From address, and provider delivery events; document that `200` means provider acceptance rather than guaranteed inbox placement.
- [Mock mode is accidentally redeployed publicly] → Pin `smtp` in the production manifest and add a deploy/test assertion that the live backend is not `mock`.

## Migration Plan

1. In Mailjet, add and validate `sim-policy-trainer-challenge.info` under the same API Key that will send mail; publish the dashboard-provided ownership and DKIM records, publish or merge `v=spf1 include:spf.mailjet.com ~all`, preserve the existing DMARC record, and wait for Mailjet to show the domain/SPF/DKIM as valid.
2. Generate or retrieve the Mailjet API Key and generate its Secret Key once. Store the API Key as `SAAS_SMTP_USER` and Secret Key as `SAAS_SMTP_PASSWORD` directly in the approved external-secret workflow; never paste them into chat, shell history, Git, the design, or the implementation log.
3. Add the MysteryBox secret container and read permit, create the credential payload version out of band with the selected Mailjet settings, and install/verify the `saas-smtp` reconciliation unit without exposing values.
4. Implement and locally test configuration validation, timeouts, typed failures, pending-code cleanup, sanitized logs, and API `503` behavior while production remains in mock mode.
5. Reconcile `saas-smtp`, verify only expected key names and a successful bounded Mailjet SMTP handshake/test message, then change GitOps to `SAAS_EMAIL_BACKEND=smtp` with the required Secret reference.
6. Confirm ArgoCD is Synced/Healthy, request one code from the public UI, verify receipt and one-time sign-in, inspect Mailjet acceptance plus SPF/DKIM/DMARC results, and confirm no code or credential appears in application logs.
7. Record non-secret results and cleanup in `IMPLEMENTATION_LOG.MD`. If either Mailjet key was exposed, reset the Secret Key immediately and update MysteryBox/Kubernetes before resuming delivery.

Rollback: revert the Deployment to the last validated email configuration and prior MysteryBox version, then restart the single pod and re-run health checks. `mock` may be used only for an explicitly operator-controlled maintenance/demo window because public users cannot retrieve its codes; the UI must not be left presenting mock delivery as real email.

## Open Questions

- None at the architecture level. Mailjet is selected, `sim-policy-trainer-challenge.info` is the sender domain, and `login@sim-policy-trainer-challenge.info` is the From address. Production cutover remains operationally blocked until Mailjet shows domain ownership, SPF, and DKIM as valid and the API/Secret Key pair is stored in MysteryBox.
