## Why

The public SaaS currently claims that a login code was sent while the production deployment uses the `mock` email backend, which only writes the code to a pod log. Real users therefore cannot complete sign-in, and delivery failures would not yet have the timeout, rollback, observability, and operational safeguards expected of a public authentication path.

## What Changes

- Configure the public deployment to send login codes through an authenticated transactional SMTP provider instead of the mock logger.
- Provision SMTP settings and credentials through Nebius MysteryBox and reconcile them into a Kubernetes Secret without storing secret values in Git, images, logs, or OpenTofu state.
- Authenticate the sender domain with the provider-required SPF and DKIM records and publish a DMARC policy so receiving systems can validate Sim2Policy mail.
- Harden SMTP delivery with explicit connection timeouts, configurable STARTTLS/TLS behavior, startup configuration validation, and sanitized operational logging.
- Make `/auth/request-code` return a retryable service error when the provider rejects or cannot accept the message, and ensure a failed delivery cannot leave a usable pending code.
- Add automated tests and a bounded live acceptance procedure covering successful receipt, provider failure, secret rotation, rollout, and rollback to a prior working configuration.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `saas-email-auth`: Require production email delivery to use a correctly configured real adapter, define honest failure behavior, and add delivery security and operational requirements.

## Impact

- Backend: `saas/backend/app/email_sender.py`, auth request handling, configuration validation, health/diagnostic behavior, and auth tests.
- GitOps: `deploy/manifests/saas/deployment.yaml` and related configuration for the SMTP Secret reference and production backend selection.
- Infrastructure/operations: a Nebius MysteryBox SMTP secret and the existing server-side secret reconciliation flow; sender-domain DNS records managed with the chosen mail provider and DNS host.
- API: successful `POST /auth/request-code` remains `200`; transient delivery failures become a sanitized retryable `503` instead of a false success or an unhandled provider exception.
- Documentation and verification: provider setup, secret rotation, deliverability checks, rollback, and monitoring guidance in `saas/README.md` and `IMPLEMENTATION_LOG.MD`.
