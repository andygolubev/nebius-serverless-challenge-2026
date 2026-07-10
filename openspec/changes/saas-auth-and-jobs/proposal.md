# Proposal: saas-auth-and-jobs

## Why

The SaaS control plane currently trusts a raw `X-Tenant-Id` header (anyone can impersonate any tenant) and only accepts fixed presets, and the frontend is an unstyled prototype. To demo a credible multi-tenant product, users need real sign-in (email + one-time code) and meaningful control over what they train (policy and environment configuration), wrapped in a polished UI.

## What Changes

- Add passwordless email authentication: user submits their email, receives a short-lived one-time code by email, and exchanges it for a session token. All job endpoints require the session; the tenant is derived from the verified email. **BREAKING**: `X-Tenant-Id` header is no longer accepted as identity.
- Add job customization: instead of only a preset name, a job submission carries a policy configuration (algorithm choice and safe hyperparameter overrides) and an environment selection (which robot/task, seed, episode/timestep budget) validated against server-side allowlists and bounds.
- Redesign the frontend as a beautiful, cohesive product UI: login screen (email → code entry), job composer (environment + policy configuration form), live jobs dashboard with status timeline, and results/artifacts view. Responsive, light/dark aware, consistent design tokens.
- Add an email delivery adapter with a dev/mock mode (code logged/exposed for local demo) and an SMTP/provider mode for real deployments.

## Capabilities

### New Capabilities
- `saas-email-auth`: passwordless email + one-time-code authentication, session issuance/expiry, and tenant scoping derived from the verified email.
- `saas-job-customization`: job submission with user-selected environment and policy configuration, validated against server-defined allowlists and safe bounds.
- `saas-web-ui`: the styled web application — login flow, job composer, jobs dashboard, and results views with a consistent design system.

### Modified Capabilities

<!-- none: existing specs (training-demo-api, training-presets, ...) cover the sim2policy demo API, not the SaaS server; SaaS behavior is introduced as new capabilities -->

## Impact

- `saas/backend/app/` — new auth module (code issuance, verification, sessions), email adapter, extended `JobRequest`/validation in `models.py` and `main.py`, store extended for users/sessions.
- `saas/frontend/` — full UI rebuild (login, composer, dashboard, results); adds styling infrastructure.
- API surface — new `/auth/request-code`, `/auth/verify`, `/auth/logout`, `/me` endpoints; existing `/jobs*` endpoints now require a bearer session token (**BREAKING** for header-based clients).
- Deployment — new environment variables for email delivery (SMTP/provider credentials) and session secret; mock mode keeps local/demo runs credential-free.
