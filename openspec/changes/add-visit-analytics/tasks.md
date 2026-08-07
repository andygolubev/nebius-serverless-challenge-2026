## 1. Schema and configuration

- [x] 1.1 Add `analytics_visits`, `analytics_page_views`, and `analytics_daily` to `_SCHEMA` in
      `saas/backend/app/db.py` using `CREATE TABLE IF NOT EXISTS`, with indexes on
      `analytics_visits(last_seen)`, `analytics_visits(ip_hash)`, `analytics_page_views(created_at)`,
      and `analytics_page_views(view)`
- [x] 1.2 Add `AnalyticsSettings` to `saas/backend/app/settings.py` reading `SAAS_ANALYTICS_IP_SALT`
      (optional; absent means disabled), retention days (default 90), and session-gap minutes
      (default 30), following the existing `from_env` dataclass pattern
- [x] 1.3 Verify an existing database file opens cleanly against the new schema and that all prior
      users, sessions, jobs, artifacts, robots, setups, preparation attempts, and training requests
      are unchanged

## 2. Analytics core

- [x] 2.1 Create `saas/backend/app/analytics.py` with `client_address(request)` returning the
      leftmost valid `X-Forwarded-For` entry, falling back to the direct peer address
- [x] 2.2 Add `hash_address(address, salt)` returning hex salted SHA-256; return `None` when the salt
      is absent so callers can fail closed
- [x] 2.3 Add `is_bot(user_agent)` matching known crawler tokens (`bot`, `crawler`, `spider`,
      `slurp`, `HeadlessChrome`, and similar) case-insensitively, treating an empty user agent as a bot
- [x] 2.4 Add field-bounding helpers: user agent and referrer truncated to 512 chars, entity id to
      128, and a view-name validator accepting only the known SPA view names
- [x] 2.5 Add `daily_rollup_and_prune(conn, retention_days, now)` that upserts completed days into
      `analytics_daily` with `INSERT OR REPLACE`, then deletes expired visit and page-view rows in
      bounded `LIMIT` batches

## 3. Analytics store

- [x] 3.1 Add `AnalyticsStore` to `saas/backend/app/store.py` with its own `db.connect` connection
      and `threading.Lock`, matching the existing store discipline
- [x] 3.2 Implement `record(visit_id, view, entity_id, ip_hash, user_agent, referrer, is_bot, now)`:
      insert a new visit when the id is unknown, expired past the session gap, or its stored
      `ip_hash`/`user_agent` do not match; otherwise advance `last_seen`. Always insert the page-view row
- [x] 3.3 Implement `prune(retention_days, now)` delegating to `daily_rollup_and_prune`, asserting it
      touches only analytics tables
- [x] 3.4 Confirm the store never reads or writes tenant, email, or session columns

## 4. Collect endpoint and retention task

- [x] 4.1 Add a `CollectRequest` model (`visit_id: str | None`, `view: str`, `entity_id: str | None`)
      to `saas/backend/app/models.py`
- [x] 4.2 Add `POST /analytics/collect` to `saas/backend/app/main.py` — unauthenticated, no
      `require_session` dependency — returning `Response(status_code=204)` with an empty body on every
      path, including validation failure, missing salt, and storage error
- [x] 4.3 Wrap the whole handler body in a broad `except Exception` that logs and still returns `204`;
      validate `visit_id` against a UUID pattern before use
- [x] 4.4 Instantiate `AnalyticsStore` alongside the other stores and log once at startup when the
      salt is absent and recording is therefore disabled
- [x] 4.5 Add a startup background task that runs the prune immediately, then every 24 hours

## 5. Frontend beacon

- [x] 5.1 Create `saas/frontend/src/analytics.ts` with a `trackView(view, entityId?)` that reads or
      mints a `sessionStorage` visit-id UUID, wrapping storage access in try/catch with an in-memory
      fallback for private-mode browsers
- [x] 5.2 Post to `/analytics/collect` with `keepalive: true`, no auth header, and an empty
      `.catch()` so a blocked or failed request is silent
- [x] 5.3 Add an unauthenticated post helper to `saas/frontend/src/api.ts` that does not trigger the
      `SESSION_EXPIRED_EVENT` path on failure
- [x] 5.4 Call `trackView` from a `useEffect` in `saas/frontend/src/App.tsx` keyed on the existing
      `routeKey`, passing `active.view` and `active.id` when present — this fires exactly once per view
      change, including first load

## 6. Tests

- [x] 6.1 Backend: `X-Forwarded-For` leftmost entry wins over the direct peer; a malformed header
      falls back
- [x] 6.2 Backend: the same address and salt hash identically; no stored row contains a parseable IP
      literal; an absent salt writes no rows
- [x] 6.3 Backend: crawler user agents flag as bots, ordinary browsers do not, and an empty user agent
      flags as a bot
- [x] 6.4 Backend: a new visit id creates one visit; a repeat id adds page views to the same visit and
      advances `last_seen`; an id older than the session gap starts a new visit; a forged id from a
      different address hash starts a new visit
- [x] 6.5 Backend: collect returns `204` with an empty body when the store raises, when the view name
      is unknown, and when fields are oversized
- [x] 6.6 Backend: prune deletes expired rows, preserves in-window rows, leaves that day's totals in
      `analytics_daily`, is idempotent across repeated runs, and modifies no non-analytics table
- [x] 6.7 Frontend: the beacon fires once per view change with the correct view name and entity id,
      and a rejected fetch neither throws nor blocks rendering
- [ ] 6.8 Run the full backend and frontend suites on the approved Nebius builder and confirm the
      existing 565 backend and 53 frontend tests still pass

## 7. Statistics access and deployment

- [x] 7.1 Write `saas/ANALYTICS_QUERIES.md` with runnable SQL for visits and unique visitors over a
      window, page popularity by view, traffic by day, top referrers, human/bot split, and long-term
      trend from `analytics_daily`, plus the `ssh` + `kubectl exec` access recipe
- [x] 7.2 Generate a random salt and add it to the existing Kubernetes Secret out of band — never to
      Git — then confirm no salt value appears in any tracked file
- [x] 7.3 Add `SAAS_ANALYTICS_IP_SALT` to `deploy/manifests/saas/deployment.yaml` sourced from that
      Secret via `secretKeyRef`
- [x] 7.4 Run the changed-source secret scan and `git diff --check` before pushing
- [x] 7.5 After the GitOps roll, load the public site, then verify visit and page-view rows appear and
      that no raw address literal is stored
- [x] 7.6 Confirm every documented query in `ANALYTICS_QUERIES.md` runs against the live database and
      returns sensible results — do this before promoting the site, not after
