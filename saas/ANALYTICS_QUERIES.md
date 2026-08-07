# Site visit analytics queries

Connect to the production database without copying it locally:

```sh
ssh -i ssh-keys/saas-server-key -o IdentitiesOnly=yes saas-server@sim-policy-trainer-challenge.info
sudo kubectl -n saas exec deploy/saas -- sqlite3 /data/saas.db
```

All queries below are read-only. Replace the two ISO date placeholders with the inclusive UTC window you need.

```sql
-- Visits and distinct pseudonymous visitors (excluding bots).
SELECT COUNT(*) AS visits, COUNT(DISTINCT ip_hash) AS unique_visitors
FROM analytics_visits
WHERE is_bot = 0 AND datetime(first_seen, 'unixepoch') >= '2026-08-01'
  AND datetime(first_seen, 'unixepoch') < '2026-09-01';

-- Page popularity.
SELECT view, COUNT(*) AS page_views
FROM analytics_page_views
WHERE datetime(created_at, 'unixepoch') >= '2026-08-01'
  AND datetime(created_at, 'unixepoch') < '2026-09-01'
GROUP BY view ORDER BY page_views DESC;

-- Daily traffic (raw window).
SELECT date(first_seen, 'unixepoch') AS day, COUNT(*) AS visits,
       COUNT(DISTINCT ip_hash) AS unique_visitors
FROM analytics_visits WHERE is_bot = 0 GROUP BY day ORDER BY day;

-- Top referrers and human/bot split.
SELECT referrer, COUNT(*) AS visits FROM analytics_visits
WHERE is_bot = 0 GROUP BY referrer ORDER BY visits DESC LIMIT 20;
SELECT is_bot, COUNT(*) AS visits FROM analytics_visits GROUP BY is_bot;

-- Permanent long-term daily trend.
SELECT day, visits, page_views, unique_visitors, bot_visits
FROM analytics_daily ORDER BY day;
```
