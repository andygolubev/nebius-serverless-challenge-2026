# saas-email-auth Specification (delta)

## MODIFIED Requirements

### Requirement: Session-scoped API access
All job endpoints (`/jobs*`, `/training-options` job submission) SHALL require a valid `Authorization: Bearer <token>` session. The tenant identity SHALL be derived from the session's verified email; the `X-Tenant-Id` header SHALL be ignored. Sessions SHALL expire after a configurable lifetime (default 24 hours) and be revocable via `POST /auth/logout`. `GET /me` SHALL return the authenticated user's email. Sessions and tenant accounts SHALL be stored durably so that a valid, unexpired session token issued before a backend restart remains valid after it.

#### Scenario: Authenticated job access
- **WHEN** a request to `/jobs` carries a valid session token
- **THEN** the system serves only jobs belonging to that session's tenant

#### Scenario: Missing or invalid token
- **WHEN** a request to `/jobs` has no token, an invalid token, or an expired session
- **THEN** the system responds 401

#### Scenario: Logout revokes the session
- **WHEN** a user calls `/auth/logout` and then reuses the same token
- **THEN** the subsequent request responds 401

#### Scenario: Session survives a backend restart
- **WHEN** a user holds a valid, unexpired session token and the backend restarts
- **THEN** requests with that token continue to succeed without re-authentication
