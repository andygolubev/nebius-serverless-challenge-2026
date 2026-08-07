## Context

The SaaS app is a single FastAPI process serving a React SPA from `saas/backend/static`, behind k3s
Traefik at `sim-policy-trainer-challenge.info`, one replica, with SQLite on a 1 GiB node-local PVC.
Four facts about the current system drive this design:

1. **The SPA never changes the URL.** `App.tsx` holds routing entirely in React state — there is no
   `pushState`, no hash router, no `popstate` listener. A visitor who opens the showcase, reads an
   example, and visits About produces exactly one server request for HTML: `GET /`. Server-side
   request logging therefore cannot answer "what pages were visited," which is half the ask.
2. **The pod sits behind a reverse proxy.** Uvicorn runs with default `forwarded_allow_ips`, and the
   peer address it sees is the Traefik pod IP. Every request would otherwise hash to the same
   handful of cluster addresses, making unique-visitor counts meaningless.
3. **Storage is small and shared.** Analytics competes for the same 1 GiB volume as all job, robot,
   and artifact state, under SQLite WAL. Unbounded growth is an availability risk for the product,
   not just for analytics.
4. **There is no admin role.** Auth is email one-time-code; any address can sign in and every
   endpoint is tenant-scoped. There is no existing notion of a privileged reader.

The operator chose: no read API (SQL over SSH), 90-day retention with permanent rollups, and salted
IP hashes rather than raw addresses.

## Goals / Non-Goals

**Goals:**
- Know how many people visit, how often they return, and which views they open.
- Attribute traffic to a source (referrer) so promotion effectiveness is measurable.
- Separate crawler traffic from human traffic.
- Survive restarts and redeploys; keep long-term trend data forever within bounded disk.
- Be structurally incapable of breaking the public site.

**Non-Goals:**
- Read API, dashboard, or admin UI. Statistics come from SQL over SSH.
- Session recording, funnels, click/scroll tracking, A/B testing, geolocation.
- Cookies, `localStorage` identifiers, cross-site tracking, third-party services.
- Raw IP storage, or any linkage between a visit and an authenticated tenant.
- Exact accuracy. This measures popularity; approximate is fine.

## Decisions

### D1: Client beacon for page views, server headers for identity

The SPA posts `{visit_id?, view, entity_id?}` to `POST /analytics/collect`; the backend derives IP,
user agent, and referrer from request headers and never trusts the client for them.

This split is forced by fact (1) — only the client knows the view — but everything the client could
lie about in a way that corrupts the data is taken server-side instead.

*Alternatives:* pure server-side middleware over `GET /` and API calls — rejected, cannot attribute
views, and API calls are a biased proxy (public showcase browsing makes almost none). Adding a real
URL router to the SPA — rejected as a much larger, riskier change to shipping UI for an analytics
feature. A third-party script — rejected: external dependency, cookie consent obligation, and the
CSP/self-contained posture of this deployment.

### D2: Visit identity via a server-issued id in `sessionStorage`

The first collect call of a browser session returns no body (the endpoint is write-only), so the
visit id is minted **client-side** as a random UUID, stored in `sessionStorage`, and sent with each
call. The server treats an unknown id as a new visit and a known id as a continuation, extending
`last_seen`.

`sessionStorage` (not `localStorage`, not a cookie) is deliberate: it is per-tab and cleared when the
tab closes, so it is not a persistent identifier and triggers no consent banner. Cross-session repeat
visits are still visible in aggregate through the IP hash, which is what "how popular is this"
actually needs.

A client-minted id is untrusted by construction, so the server clamps it: it must match a UUID
pattern, and a visit is only extended when the incoming address hash and user agent also match the
stored row. A forged id from a different client starts a fresh visit instead of corrupting one.

*Alternatives:* a signed server-issued cookie — rejected, drags in consent obligations for a
popularity counter. Deriving identity purely from IP hash + user agent — rejected, collapses everyone
behind one NAT or mobile carrier into a single visitor.

**Session gap:** 30 minutes of inactivity ends a visit, matching the common convention.

### D3: `X-Forwarded-For` leftmost entry, then salted SHA-256

Client address = first entry of `X-Forwarded-For` if present and parseable, else the direct peer.
Stored as `sha256(salt || address)` hex, from `SAAS_ANALYTICS_IP_SALT`.

The leftmost entry is client-controllable in general, but here Traefik is the only ingress path and
appends the real peer; the practical failure mode is a spoofed header inflating unique counts, which
is acceptable for a popularity metric and cannot leak anything.

The salt lives in the existing Kubernetes Secret, never in Git. **Without it, recording is off.** An
unsalted or hardcoded-salt hash of an IPv4 address is trivially reversible by brute force over the
4-billion-address space — it would be pseudonymization in name only. Failing closed is the only
honest option.

Consequence to accept: rotating the salt breaks visitor correlation across the rotation. That is
fine; daily rollups already carry the historical uniques.

*Alternatives:* raw IP — the operator declined. Truncating to /24 — weaker uniqueness and still
personal data. HMAC instead of salted hash — no meaningful advantage here, as there is no forgery
threat against the digest.

### D4: Three tables, additive, no tenant scope

```
analytics_visits(id PK, first_seen, last_seen, ip_hash, user_agent, referrer, is_bot)
analytics_page_views(id PK, visit_id FK, view, entity_id, created_at)
analytics_daily(day PK, visits, page_views, unique_visitors, bot_visits)
```

Indexes on `analytics_visits(last_seen)`, `analytics_visits(ip_hash)`,
`analytics_page_views(created_at)`, and `analytics_page_views(view)` — matching the four documented
query shapes and the prune scan.

Columns are typed and separate rather than the JSON `data TEXT` blob used by `JobStore` and
`RobotStore`. Those stores round-trip whole Pydantic models by primary key; analytics is
aggregated with `GROUP BY` and `COUNT`, which JSON blobs make slow and awkward. Deviating from the
house pattern is justified by the opposite access shape.

No tenant column. These rows describe anonymous public traffic, and the moment a tenant id appears
next to an IP hash the table stops being anonymous analytics and starts being a per-user activity
log — a materially different privacy proposition than what was asked for.

Bounds at write time: user agent truncated to 512 chars, referrer to 512, view name validated against
the known `Route["view"]` set, entity id to 128 chars. This caps row size and keeps a hostile client
from filling the volume with one field.

### D5: Retention — prune on startup, then daily

An `asyncio` background task on the existing startup hook rolls up completed days into
`analytics_daily` (via `INSERT OR REPLACE`, so re-running is idempotent), deletes visit and page-view
rows older than 90 days, and then sleeps 24 h. Running on startup as well as on the timer means a pod
that restarts more often than daily still prunes.

`analytics_daily` is roughly 40 bytes/day — about 15 KB/decade — so keeping it forever is free. Raw
rows at a generous 500 page views/day for 90 days land near 10 MB, comfortably inside the volume.

Deletes run in bounded batches with `LIMIT`, so a large first prune cannot hold SQLite's single write
lock long enough to stall live requests.

*Alternative:* prune inline on each write — rejected, puts a scan in the request path.

### D6: Write path swallows everything

The route is wrapped so that any exception — storage, validation, missing salt — is logged and
answered `204`. The frontend beacon uses `keepalive: true` and an empty `.catch()`.

This is the load-bearing safety property of the whole change: analytics is a nice-to-have bolted onto
a working product, and it must not be able to take that product down. `204` with an empty body also
enforces write-only-ness structurally — there is no shape of response for data to leak through.

### D7: Statistics by SQL over SSH, with a cookbook

Per the operator's choice, no read endpoint ships. `saas/ANALYTICS_QUERIES.md` documents ready-to-run
queries for: visits and unique visitors over a window, page popularity by view, traffic by day, top
referrers, human/bot split, and long-term trend from `analytics_daily`.

Access is `ssh saas-server@195.242.13.73` then `sudo kubectl exec` into the pod against
`$SAAS_DB_PATH`. Queries are read-only `SELECT`s.

Accepted trade-off: the SaaS server has been intermittently unreachable over SSH (it timed out during
the GitOps cutover). If that recurs while stats are wanted, the fallback is reading the PVC from the
node directly — no redeploy needed, since the data is already durable either way.

## Risks / Trade-offs

- **Beacon blocked by ad blockers / DNT** → Undercounts privacy-conscious visitors. Mitigated by
  hosting the endpoint first-party on the app's own origin under a neutral path, with no third-party
  script; unfixable in general, and acceptable for a popularity signal.
- **Salt missing in production silently disables recording** → Zero rows during the promotion window,
  the one window that matters. Mitigated by a startup log line and by a deploy task that verifies
  rows appear immediately after cutover, before promotion begins.
- **Spoofed `X-Forwarded-For` inflates unique visitors** → Popularity looks better than it is.
  Accepted; no security consequence, and Traefik is the only real ingress path.
- **Crawler flood after promotion fills the window** → Bot rows are flagged, so every documented
  query can filter them; the 90-day prune plus per-field truncation bounds the disk cost.
- **A client-minted visit id is untrusted** → Mitigated by UUID-shape validation plus the address-hash
  and user-agent match before extending a visit; worst case is a slightly inflated visit count.
- **SQLite write contention** → Analytics adds a write per page view on the single writer.
  Small relative to existing job traffic, and the store keeps the same lock discipline as the other
  stores; prune batches keep the long-running delete off the critical path.
- **`sessionStorage` unavailable (private mode, storage disabled)** → Every page view becomes its own
  visit, inflating visit counts. Mitigated by wrapping access in try/catch and falling back to an
  in-memory id for the page lifetime.

## Migration Plan

1. Ship backend + frontend behind the salt check. With no `SAAS_ANALYTICS_IP_SALT`, the deployed code
   is inert — the collect route answers `204` and writes nothing.
2. Add the salt to the existing Kubernetes Secret out of band (never in Git), then set the env var in
   `deployment.yaml` and let GitOps roll it.
3. Verify: load the public site, then confirm rows exist and contain no raw address literal.
4. Only then promote the site.

**Rollback:** unset `SAAS_ANALYTICS_IP_SALT` to stop recording without a code change; revert the
image tag for a full rollback. The tables are additive and created by `CREATE TABLE IF NOT EXISTS`,
so an older image ignores them and no existing data is touched in either direction.

## Open Questions

- Should the public Terms page mention analytics? Salted-hash storage with no cookie and no
  cross-site identifier is pseudonymous and arguably needs no notice, and the operator declined the
  Terms edit. Worth revisiting if raw IPs or persistent identifiers are ever introduced.
- Is 90 days the right window? Chosen to cover a promotion plus its tail. Daily rollups make the raw
  window cheap to shorten later without losing trend data.
