# saas-tenant-app Delta

## ADDED Requirements

### Requirement: Security response headers
Every HTTP response from the app (API and static frontend alike) SHALL carry hardening headers: a
`Content-Security-Policy` with a `default-src 'self'` baseline (additional media/connect origins,
such as the S3 artifact origin, configurable at deploy time rather than hardcoded),
`X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, and clickjacking protection
(`frame-ancestors 'none'` and `X-Frame-Options: DENY`). When the deployment terminates TLS,
responses SHALL also carry `Strict-Transport-Security`. The served frontend SHALL function fully
under this policy.

#### Scenario: Headers present on API responses
- **WHEN** any API endpoint responds
- **THEN** the response includes the CSP, nosniff, referrer-policy, and frame-protection headers

#### Scenario: Headers present on the frontend
- **WHEN** the built frontend index or its assets are served
- **THEN** the same headers are present and the app loads and operates without CSP violations

#### Scenario: HSTS in TLS deployments
- **WHEN** the app runs behind the TLS-terminating ingress with HSTS enabled
- **THEN** responses include a `Strict-Transport-Security` header

### Requirement: Backend-access refusal is clearly surfaced
When job submission is refused because the account is not on the `nebius`-backend allowlist (403),
the API SHALL return a neutral message that does not reveal the allowlist, and the web UI SHALL
present that message to the user rather than a generic failure. Allowlisted tenants SHALL see no
change in submission behavior.

#### Scenario: Non-allowlisted refusal in the UI
- **WHEN** a non-allowlisted tenant's submission is refused with 403
- **THEN** the UI shows a message that the account is not enabled for job submission, revealing no
  other account or allowlist information

#### Scenario: Allowlisted submission is unchanged
- **WHEN** an allowlisted tenant submits a job
- **THEN** the UI behaves exactly as before the allowlist existed
