# Design: saas-auth-and-jobs

## Context

The SaaS control plane ([saas/backend/app/main.py](../../saas/backend/app/main.py)) is a FastAPI app with an in-memory `JobStore`, a pluggable orchestration backend (only `mock` today), tenant identity from a raw `X-Tenant-Id` header, and preset-only job submission (`ALLOWED_PRESETS`). The frontend ([saas/frontend/src/App.tsx](../../saas/frontend/src/App.tsx)) is a single inline-styled React component. Both ship in one container image deployed by ArgoCD behind Traefik with TLS already configured. Constraint from the project: no arbitrary user code/images — everything user-configurable must stay allowlisted and bounded.

## Goals / Non-Goals

**Goals:**
- Real (if lightweight) authentication: email + one-time code → bearer session; tenant = verified email.
- User-configurable jobs: environment + policy algorithm + bounded hyperparameters, validated server-side from a single catalog.
- A designed, responsive, themable frontend that demos well.
- Stay credential-free locally: mock email adapter and mock orchestrator remain the default.

**Non-Goals:**
- OAuth/OIDC, passwords, MFA, or account management (profile, deletion).
- Persistent database — the in-memory store pattern is kept (extended), matching the current demo scope.
- Arbitrary user code, custom images, or free-form environment variables into training jobs.
- Billing, quotas beyond simple rate limits, or admin UI.

## Decisions

### D1: Passwordless OTP over email, sessions as opaque bearer tokens
Codes: 6-digit random (`secrets`), stored as SHA-256 hashes with expiry (10 min), max 5 verify attempts, single-use. Sessions: opaque random tokens (not JWT) stored server-side with a 24h TTL — revocation (`/auth/logout`) is trivial and there's no key management. *Alternative considered:* signed JWTs — rejected because server-side sessions are simpler, the store is already in-process, and instant revocation matters more than statelessness at this scale.

### D2: Auth as a FastAPI dependency, not middleware
A `require_session` dependency resolves `Authorization: Bearer <token>` → `User(email, tenant_id)` and is added to every job route. `/health`, `/auth/*`, and static files stay open. *Alternative:* ASGI middleware — rejected; dependencies keep per-route opt-in explicit and testable.

### D3: Email adapter interface mirroring the orchestration backend pattern
`EmailSender` protocol with `MockEmailSender` (logs the code at INFO; default) and `SmtpEmailSender` (stdlib `smtplib`, config from `SAAS_SMTP_HOST/PORT/USER/PASSWORD/FROM`). Selected by `SAAS_EMAIL_BACKEND` (`mock`|`smtp`), same shape as `SAAS_ORCHESTRATION_BACKEND`. No new dependencies.

### D4: Server-side catalog drives both validation and UI
A `catalog.py` module declares environments (`halfcheetah`, `ant`, `go1`), per-environment compatible algorithms (`ppo-sb3`, `ppo-mjx`), and parameters as typed descriptors (`name, type, default, min, max, choices`). `GET /training-options` serializes it; `POST /jobs` validates against it and merges overrides over defaults into a `resolved_config` stored on the job. Presets become named expansions over the same catalog, so `{"preset": ...}` keeps working. *Alternative:* pure Pydantic models with hardcoded bounds — rejected because the frontend needs the same constraints to render the form; one catalog avoids drift.

### D5: Frontend rebuilt with vanilla CSS design tokens, no UI framework
Keep React + Vite; add a `tokens.css` (color/space/type scales, light + dark via `prefers-color-scheme`), split `App.tsx` into views (`Login`, `Composer`, `Dashboard`, `JobDetail`) with a tiny fetch client that injects the bearer token and redirects to login on 401. Session token in `localStorage`. *Alternative:* Tailwind or a component library — rejected to keep the build dependency-free and the image small; the surface is four screens.

### D6: Rate limiting in-process
Per-email sliding window (5 code requests / 15 min) kept in the store. Good enough for a single-replica demo; noted as a risk for multi-replica.

## Risks / Trade-offs

- [In-memory store loses users/sessions/jobs on restart] → acceptable for the demo stage; the store interface keeps a future DB swap localized. Users just re-login.
- [Single-replica assumption (sessions, rate limits in-process)] → deployment keeps `replicas: 1`; documented in saas/README.
- [SMTP credentials in env vars] → delivered via k8s Secret in the deploy manifests; mock mode means no secret is required for CI/local.
- [Mock adapter logs codes — a real deployment misconfigured to `mock` leaks codes to logs] → startup log warns loudly when `SAAS_EMAIL_BACKEND=mock`; deploy manifests set `smtp` explicitly.
- [Breaking change: header-based clients stop working] → only the bundled frontend and demo scripts use the API; both are updated in this change.

## Migration Plan

1. Ship backend auth + catalog with the frontend rebuild in one image (single deployable, no cross-version window).
2. Deploy manifests add `SAAS_EMAIL_BACKEND` and optional SMTP secret; default stays `mock` until SMTP credentials exist.
3. Rollback = redeploy previous image tag via ArgoCD; no data migration (in-memory store).

## Open Questions

- Which SMTP provider for the live deployment (or keep mock for the challenge demo)? Defaulting to mock until decided.
- Session lifetime: 24h chosen; adjust via `SAAS_SESSION_TTL_HOURS` if the demo needs longer.
