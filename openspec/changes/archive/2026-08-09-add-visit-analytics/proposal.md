## Why

The public showcase is about to be promoted, and today the deployment keeps no record of who
reaches it. There is no way to answer "did the promotion work?" — no visitor count, no page
popularity, no referrer breakdown. Traffic that arrives during the promotion window is unrecoverable
once it has passed, so the recording path has to exist before promotion, not after.

## What Changes

- Record one **visit** row per new visitor session: first-seen and last-seen timestamps, a salted
  hash of the client IP, user agent, referrer, and a bot flag.
- Record one **page view** row per SPA view opened, linked to its visit: view name, optional entity
  id (e.g. the showcase example being read), and timestamp.
- Add a public, unauthenticated `POST /analytics/collect` write-only endpoint. It accepts a small
  view-name payload, derives IP/user-agent/referrer server-side from request headers, and returns
  `204` regardless of outcome so analytics can never break a page.
- Add a lightweight frontend beacon that posts on first load and on every SPA view change. The SPA
  keeps all routing in React state and never changes the URL, so server request logs alone cannot
  attribute page views — a client beacon is the only way to know which view was opened.
- Classify obvious crawler user agents as bots at write time and store the flag, so post-promotion
  counts can separate real visitors from crawler traffic.
- Retain raw rows for 90 days, roll each day up into a small permanent daily-totals table, and prune
  on startup plus once a day. The SQLite database shares a 1 GiB node-local PVC with all job and
  robot state, so unbounded analytics growth would risk the whole app.
- Ship a documented SQL cookbook so statistics can be read over SSH against the live database
  without an API or a redeploy.

Not included: no read API, no admin UI, no dashboard, no third-party analytics service, no cookies,
no cross-site identifiers, no raw IP storage.

## Capabilities

### New Capabilities
- `site-visit-analytics`: first-party recording of visits and SPA page views, the pseudonymization
  and bot-classification rules applied at write time, the durability and retention/rollup contract,
  and the requirement that analytics failure never degrades the user-facing site.

### Modified Capabilities
- `saas-data-persistence`: adds visit, page-view, and daily-rollup tables to the durable SQLite
  schema, and introduces the project's first *bounded-retention* state — every existing table is
  retained indefinitely by contract, so the requirement that analytics rows are deliberately pruned
  must be stated rather than left to contradict the retention rule.

## Impact

- **Backend** (`saas/backend/app/`): new `analytics.py` (hashing, bot classification, retention);
  new `AnalyticsStore` in `store.py`; three tables plus indexes in `db.py`; the collect route and a
  daily prune task in `main.py`; new `AnalyticsSettings` in `settings.py`.
- **Frontend** (`saas/frontend/src/`): a beacon module plus a `useEffect` in `App.tsx` keyed on the
  existing `routeKey`, which already changes exactly once per view. `api.ts` gains one unauthenticated
  post helper.
- **Deployment** (`deploy/manifests/saas/deployment.yaml`): one new env var
  `SAAS_ANALYTICS_IP_SALT`, sourced from the existing Kubernetes Secret, never from Git. A missing
  salt disables recording rather than storing anything weakly hashed.
- **Client IP**: the pod sits behind Traefik, so `request.client.host` is the Traefik pod address.
  The real client address must come from the `X-Forwarded-For` chain, which affects correctness of
  every unique-visitor number this change produces.
- **Privacy**: no raw IP is ever written to disk or logs. The stored value is a salted SHA-256 hash,
  which distinguishes repeat visitors without being reversible to an address.
- **Tests**: new backend tests for hashing, bot classification, retention, and the write path; new
  frontend tests asserting the beacon fires per view change and that its failure is silent.
