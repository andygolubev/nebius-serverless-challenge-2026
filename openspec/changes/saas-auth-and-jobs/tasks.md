# Tasks: saas-auth-and-jobs

## 1. Backend — email auth

- [ ] 1.1 Add `auth.py`: code generation (6-digit, `secrets`), SHA-256 hashed storage with 10-min expiry, single-use + 5-attempt invalidation, opaque session tokens with 24h TTL (`SAAS_SESSION_TTL_HOURS`)
- [ ] 1.2 Add `email_sender.py`: `EmailSender` protocol, `MockEmailSender` (logs code, loud startup warning), `SmtpEmailSender` (stdlib smtplib, `SAAS_SMTP_*` env vars), selected by `SAAS_EMAIL_BACKEND`
- [ ] 1.3 Extend `store.py` with users, pending codes, sessions, and a per-email rate-limit window (5 requests / 15 min)
- [ ] 1.4 Add routes: `POST /auth/request-code` (neutral response, 422 invalid email, 429 rate limit), `POST /auth/verify` (session issuance, 401 wrong/expired), `POST /auth/logout`, `GET /me`
- [ ] 1.5 Add `require_session` dependency; apply to all `/jobs*` routes; derive tenant from verified email; drop `X-Tenant-Id` handling
- [ ] 1.6 Backend tests: request/verify happy path, expiry, attempt limit, single-use, rate limit, 401 on missing/expired/logged-out session, tenant isolation

## 2. Backend — job customization

- [ ] 2.1 Add `catalog.py`: environments (halfcheetah, ant, go1), per-env algorithms (ppo-sb3, ppo-mjx), typed parameter descriptors (type/default/min/max/choices), and presets as named expansions
- [ ] 2.2 Rework `GET /training-options` to serialize the full catalog (environments, policies, parameter constraints, presets)
- [ ] 2.3 Extend `JobRequest`/`Job` models: environment + policy config or preset; validate against catalog with field-level 422s; persist `resolved_config` (overrides merged over defaults) on the job
- [ ] 2.4 Keep `{"preset": ...}` submissions working via catalog expansion; pass resolved config to the orchestration backend
- [ ] 2.5 Backend tests: valid custom job, out-of-range param 422, unknown env/algorithm 422, preset expansion, resolved config visible in `GET /jobs/{id}`

## 3. Frontend — design system & app shell

- [ ] 3.1 Create `tokens.css`: color tokens (light + dark via `prefers-color-scheme`), type scale, spacing scale, radii/shadows; global styles with WCAG AA contrast
- [ ] 3.2 Split `App.tsx` into views (`Login`, `Composer`, `Dashboard`, `JobDetail`) with a minimal router and shared layout (header, nav, responsive to 375px)
- [ ] 3.3 Add API client: injects `Authorization: Bearer` from localStorage, clears session and routes to login on any 401

## 4. Frontend — screens

- [ ] 4.1 Login screen: email step → code step with resend, inline errors for wrong/expired code and rate limiting
- [ ] 4.2 Job composer: rendered from `/training-options` (env cards with descriptions, algorithm select, parameter inputs with client-side bounds, preset prefill), server 422s shown per-field, submit disabled while invalid
- [ ] 4.3 Jobs dashboard: live-polling list, lifecycle timeline/badges, env+policy summary, relative timestamps, designed empty state linking to composer
- [ ] 4.4 Job detail/results view: resolved configuration, metrics, media links from artifact manifest; loading skeletons and readable error states throughout

## 5. Deploy & docs

- [ ] 5.1 Update deploy manifests: `SAAS_EMAIL_BACKEND` env var, optional SMTP k8s Secret, session TTL; keep `replicas: 1` with a comment on in-process sessions/rate limits
- [ ] 5.2 Update `saas/README.md`: auth flow, new API table (`/auth/*`, `/me`, bearer-token `/jobs*`), catalog-driven submission examples, mock vs smtp email modes
- [ ] 5.3 End-to-end verification: mock mode — request code from UI, read code from server log, log in, compose and submit a custom job, watch lifecycle, open results; verify dark mode and 375px layout
