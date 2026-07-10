# saas-email-auth

## ADDED Requirements

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
The system SHALL deliver codes through a pluggable email adapter selected by configuration. A `mock` adapter SHALL be the default for local/demo use and SHALL log the code and expose it via a dev-only endpoint or log line (never in the API response of `/auth/request-code` when a real adapter is configured). An `smtp` adapter SHALL send real email using credentials from environment variables.

#### Scenario: Mock mode for local demo
- **WHEN** the server runs with the mock email adapter
- **THEN** a requested code is observable by the operator (server log) so the flow is demoable without email credentials

#### Scenario: SMTP mode
- **WHEN** the server runs with the smtp adapter configured via environment variables
- **THEN** the code is sent as an email to the requesting address and is not logged in plaintext
