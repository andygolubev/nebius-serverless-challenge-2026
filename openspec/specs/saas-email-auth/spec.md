# saas-email-auth Specification

## Purpose
Authenticate SaaS users without passwords: a user submits their email, receives a short-lived
one-time code, and exchanges it for a revocable bearer session. The tenant identity for all job
APIs is the session's verified email.

## Requirements

### Requirement: Email code request
The system SHALL let a user request a one-time login code by submitting their email address to `POST /auth/request-code`. The system SHALL generate a random numeric code (at least 6 digits), store it hashed with an expiry of at most 10 minutes, and deliver it via the configured email adapter. The response SHALL NOT reveal the code and SHALL be identical whether or not the email already has an account (account enumeration resistance).

#### Scenario: Code requested for a valid email
- **WHEN** a user submits `{"email": "user@example.com"}` to `/auth/request-code`
- **THEN** the system responds 200 with a neutral acknowledgement and sends a one-time code to that email

#### Scenario: Invalid email format
- **WHEN** a user submits a syntactically invalid email address
- **THEN** the system responds 422 without generating or sending a code

#### Scenario: Rate limiting repeated requests
- **WHEN** the same email requests more than 5 codes within 15 minutes
- **THEN** the system responds 429 and does not send another code

### Requirement: Code verification and session issuance
The system SHALL exchange a valid email + code pair at `POST /auth/verify` for a bearer session token. Codes SHALL be single-use, SHALL expire, and verification SHALL allow at most 5 failed attempts per code before invalidating it. On first successful verification for an email, the system SHALL create a tenant account keyed by the normalized (lowercased, trimmed) email.

#### Scenario: Successful verification
- **WHEN** a user submits the email and the correct, unexpired code
- **THEN** the system responds 200 with a session token and the code becomes unusable

#### Scenario: Wrong or expired code
- **WHEN** a user submits an incorrect or expired code
- **THEN** the system responds 401 and no session is created

#### Scenario: Too many failed attempts
- **WHEN** a 6th verification attempt is made against the same code after 5 failures
- **THEN** the system responds 401 and the code is invalidated even if the 6th attempt is correct

### Requirement: Session-scoped API access
All job endpoints (`/jobs*`, `/training-options` job submission) SHALL require a valid `Authorization: Bearer <token>` session. The tenant identity SHALL be derived from the session's verified email; the `X-Tenant-Id` header SHALL be ignored. Sessions SHALL expire after a configurable lifetime (default 24 hours) and be revocable via `POST /auth/logout`. `GET /me` SHALL return the authenticated user's email.

#### Scenario: Authenticated job access
- **WHEN** a request to `/jobs` carries a valid session token
- **THEN** the system serves only jobs belonging to that session's tenant

#### Scenario: Missing or invalid token
- **WHEN** a request to `/jobs` has no token, an invalid token, or an expired session
- **THEN** the system responds 401

#### Scenario: Logout revokes the session
- **WHEN** a user calls `/auth/logout` and then reuses the same token
- **THEN** the subsequent request responds 401

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
