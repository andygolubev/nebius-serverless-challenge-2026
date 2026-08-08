# site-visit-analytics Specification

## Purpose
Record privacy-preserving visit and page-view analytics for the public SaaS site so operators can
measure traffic and page popularity from the durable database, without collecting raw client
addresses, exposing a read API, or degrading the site when recording fails.

## Requirements

### Requirement: Visits and page views are recorded
The SaaS backend SHALL record one visit row per visitor session and one page-view row per SPA view
opened within that session. A visit row SHALL carry a server-generated visit id, first-seen and
last-seen timestamps, the pseudonymized client address, the raw user agent, the referrer, and a bot
flag. A page-view row SHALL carry its visit id, the view name, an optional entity id, and a
timestamp. Because the frontend keeps all routing in React state and never changes the browser URL,
view attribution SHALL come from a client-sent view name rather than from the request path.

#### Scenario: A first-time visitor opens the showcase
- **WHEN** a browser loads the site and the SPA reports view `showcase`
- **THEN** the backend writes one visit row and one page-view row naming view `showcase`

#### Scenario: A visitor navigates between views
- **WHEN** a visitor with an existing visit id opens `showcase-example` and then `about`
- **THEN** the backend writes two additional page-view rows against the same visit id, writes no
  second visit row, and advances that visit's last-seen timestamp

#### Scenario: A view carrying an entity is recorded with its id
- **WHEN** the SPA reports view `showcase-example` with entity id `g1-rough`
- **THEN** the stored page-view row records both the view name and the entity id

#### Scenario: A returning visitor after the session gap
- **WHEN** a browser presents no visit id, or presents one whose last-seen timestamp is older than
  the configured session gap
- **THEN** the backend starts a new visit rather than extending the expired one

### Requirement: Client address is stored only as a salted hash
The backend SHALL derive the client address from the leftmost entry of the `X-Forwarded-For` header
when present, falling back to the direct peer address, and SHALL store only a salted SHA-256 hash of
that address. The raw address SHALL NOT be written to the database, to application logs, or to any
response body. The salt SHALL be read from configuration and SHALL NOT be committed to the
repository. When no salt is configured, the backend SHALL disable analytics recording entirely
rather than store a weakly pseudonymized or unsalted value.

#### Scenario: Address behind the ingress proxy
- **WHEN** a request arrives with `X-Forwarded-For: 203.0.113.7, 10.42.0.9`
- **THEN** the hash is derived from `203.0.113.7`, not from the proxy address `10.42.0.9` and not
  from the direct peer address

#### Scenario: Raw address never persisted
- **WHEN** any visit row is written
- **THEN** no column of that row contains a parseable IPv4 or IPv6 literal

#### Scenario: Two requests from one address correlate
- **WHEN** two separate visits originate from the same client address with the same configured salt
- **THEN** both visit rows carry an identical address hash

#### Scenario: Salt is absent
- **WHEN** the backend starts with no analytics salt configured
- **THEN** the collect endpoint still answers successfully, no visit or page-view row is written,
  and the disabled state is logged once at startup

### Requirement: Automated traffic is flagged, not discarded
The backend SHALL classify each visit as bot or human from its user agent at write time and SHALL
persist that classification on the visit row. Bot-flagged traffic SHALL still be recorded so that
crawler volume remains measurable and separable from human traffic.

#### Scenario: A crawler is flagged
- **WHEN** a visit arrives with a user agent containing a known crawler token such as `bot`,
  `crawler`, `spider`, or `HeadlessChrome`
- **THEN** the visit row is written with its bot flag set

#### Scenario: An ordinary browser is not flagged
- **WHEN** a visit arrives with a typical desktop or mobile browser user agent
- **THEN** the visit row is written with its bot flag clear

#### Scenario: An absent user agent
- **WHEN** a visit arrives with no user agent header
- **THEN** the visit is recorded with an empty user agent and flagged as a bot

### Requirement: Analytics recording never degrades the site
The analytics collect endpoint SHALL be unauthenticated, write-only, and SHALL return a success
status with an empty body regardless of whether recording succeeded. It SHALL NOT return stored
analytics data. Any storage, validation, or configuration failure SHALL be swallowed and logged
rather than surfaced to the client. The frontend beacon SHALL ignore its own network failures and
SHALL NOT block rendering or user interaction.

#### Scenario: Storage failure during collection
- **WHEN** the analytics store raises while handling a collect request
- **THEN** the endpoint still returns its success status, the page is unaffected, and the failure is
  logged server-side

#### Scenario: Malformed payload
- **WHEN** a collect request arrives with an unknown view name or an oversized field
- **THEN** the endpoint returns its success status and either rejects the row or stores it truncated,
  without raising a client-visible error

#### Scenario: Beacon failure in the browser
- **WHEN** the collect request fails, is blocked by an extension, or times out
- **THEN** the SPA renders and navigates exactly as it would with analytics disabled

#### Scenario: Endpoint does not read back data
- **WHEN** any client calls the collect endpoint
- **THEN** the response body is empty and exposes no counts, identifiers, or stored rows

### Requirement: Bounded retention with permanent rollups
The backend SHALL retain raw visit and page-view rows for a bounded window of 90 days and SHALL
delete rows older than that window on startup and once per day thereafter. Before deletion, each
elapsed day SHALL be aggregated into a compact daily-totals table that is retained indefinitely, so
long-term popularity trends survive pruning. Pruning SHALL be confined to analytics tables.

#### Scenario: Old raw rows are pruned
- **WHEN** the prune task runs with visit and page-view rows older than the retention window present
- **THEN** those rows are deleted and rows inside the window are retained

#### Scenario: Totals outlive the raw rows
- **WHEN** raw rows for a given day are pruned
- **THEN** that day's visit, page-view, unique-visitor, and bot totals remain readable from the
  daily-totals table

#### Scenario: Pruning touches nothing else
- **WHEN** the prune task runs
- **THEN** no user, session, job, artifact, robot, setup, preparation, or training-request row is
  deleted or modified

#### Scenario: Rollup is idempotent
- **WHEN** the prune and rollup task runs more than once for the same day
- **THEN** that day's totals row is replaced rather than duplicated or double-counted

### Requirement: Statistics are readable from the durable database
Recorded analytics SHALL be queryable directly from the SQLite database using SQL, without requiring
a read API, an authenticated session, or a redeploy. The change SHALL document queries covering
visits and unique visitors over a period, page popularity by view, traffic by day, top referrers,
and the human/bot split.

#### Scenario: Popularity is answerable after promotion
- **WHEN** an operator with database access runs the documented queries after a promotion window
- **THEN** the results report visits, unique visitors, per-view page-view counts, per-day totals,
  top referrers, and the human/bot split for that window

#### Scenario: Queries survive a restart
- **WHEN** the backend pod restarts or is redeployed
- **THEN** previously recorded visits, page views, and daily totals remain queryable
