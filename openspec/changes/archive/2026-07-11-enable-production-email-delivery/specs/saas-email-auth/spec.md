## MODIFIED Requirements

### Requirement: Email delivery adapter
The system SHALL deliver codes through a pluggable email adapter selected by configuration. A `mock` adapter SHALL be available only for local, test, or explicitly operator-controlled demo use and SHALL log the code for the operator; a production deployment SHALL select a real adapter. The `smtp` adapter SHALL send real email using authenticated provider settings sourced from secret-backed environment variables, SHALL use the configured secure transport and bounded timeout, and SHALL validate required configuration when the application starts. When a real adapter is configured, the system SHALL NOT expose the code, recipient address, provider credentials, or provider response text in the API response or application logs.

#### Scenario: Mock mode for local demo
- **WHEN** the server runs with the mock email adapter in a local, test, or explicitly operator-controlled demo environment
- **THEN** a requested code is observable by the operator so the flow is demoable without email credentials

#### Scenario: Production rejects mock delivery
- **WHEN** the public production deployment configuration is evaluated
- **THEN** it selects a real email adapter and an automated deployment check fails if the active backend is `mock`

#### Scenario: SMTP mode accepts a message
- **WHEN** the server runs with valid SMTP settings and the provider accepts a code message
- **THEN** the endpoint responds successfully and neither the plaintext code nor recipient address is written to application logs

#### Scenario: SMTP configuration is incomplete
- **WHEN** the SMTP adapter is selected without all required settings or with an invalid port, timeout, sender, or TLS mode
- **THEN** the application fails configuration validation instead of starting in mock mode or accepting auth requests

## ADDED Requirements

### Requirement: Honest email delivery failure
The system SHALL count provider acceptance of the message as part of a successful code request. If SMTP connection, timeout, TLS, authentication, or provider acceptance fails, the system SHALL remove the newly created pending code, preserve abuse rate limiting, and respond with a sanitized retryable `503` without leaking infrastructure or recipient details.

#### Scenario: Provider is unavailable
- **WHEN** the email provider cannot be reached before the configured timeout
- **THEN** `/auth/request-code` responds `503`, the request completes within a bounded time, and the generated code cannot be verified

#### Scenario: Provider rejects authentication or message
- **WHEN** the provider rejects SMTP authentication, sender policy, recipient, or the message
- **THEN** `/auth/request-code` responds `503` with a generic retry message and logs only a sanitized failure category

#### Scenario: Delivery fails repeatedly
- **WHEN** repeated code requests encounter provider failures
- **THEN** the existing per-email request rate limit still applies and prevents unbounded delivery attempts

### Requirement: Production sender authenticity and secret handling
The public production deployment SHALL use a project-controlled From address on a provider-verified domain with SPF, DKIM, and DMARC records, and SHALL obtain SMTP settings from a dedicated Kubernetes Secret reconciled from a versioned external secret. Credential values SHALL NOT be stored in Git, container images, OpenTofu state, application logs, or operational documentation.

#### Scenario: Production cutover prerequisites
- **WHEN** production is switched from mock to SMTP delivery
- **THEN** the provider reports the sender domain verified, SPF and DKIM pass, a DMARC record exists, and the required Kubernetes Secret is present before the application rolls out

#### Scenario: Credential rotation
- **WHEN** an operator selects a new external secret version and reconciles the Kubernetes Secret
- **THEN** the application restarts with the new credential, sends a bounded acceptance message successfully, and the old credential can be revoked without publishing either value

#### Scenario: Rebuild from declared infrastructure
- **WHEN** the SaaS server is rebuilt from the declared infrastructure and supplied an existing valid secret-version selector
- **THEN** its identity reconciles the dedicated SMTP Secret and the production deployment becomes ready without manually copying credentials into Git or the image
