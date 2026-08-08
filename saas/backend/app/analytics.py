"""Small, isolated helpers for anonymous site-visit analytics."""

from __future__ import annotations

import hashlib
import ipaddress
import sqlite3
from datetime import UTC, datetime

from fastapi import Request

KNOWN_VIEWS = {
    "showcase",
    "showcase-example",
    "about",
    "terms",
    "login",
    "dashboard",
    "robots",
    "job",
}
_BOT_TOKENS = ("bot", "crawler", "spider", "slurp", "headlesschrome", "bingpreview")


def client_address(request: Request) -> str | None:
    """Return the first valid forwarded address, otherwise the direct peer."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        candidate = forwarded.split(",", 1)[0].strip()
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            pass
    return request.client.host if request.client is not None else None


def hash_address(address: str | None, salt: str | None) -> str | None:
    if not address or not salt:
        return None
    return hashlib.sha256((salt + address).encode("utf-8")).hexdigest()


def is_bot(user_agent: str) -> bool:
    lowered = user_agent.lower()
    return not lowered or any(token in lowered for token in _BOT_TOKENS)


def bounded_user_agent(value: str | None) -> str:
    return (value or "")[:512]


def bounded_referrer(value: str | None) -> str:
    return (value or "")[:512]


def bounded_entity_id(value: str | None) -> str | None:
    return None if value is None else value[:128]


def valid_view(value: str) -> bool:
    return value in KNOWN_VIEWS


def daily_rollup_and_prune(conn: sqlite3.Connection, retention_days: int, now: float) -> None:
    """Idempotently roll up elapsed UTC days and prune raw analytics in small batches."""
    today = datetime.fromtimestamp(now, UTC).date().isoformat()
    completed_days = conn.execute(
        "SELECT DISTINCT date(first_seen, 'unixepoch') FROM analytics_visits "
        "WHERE date(first_seen, 'unixepoch') < ?",
        (today,),
    ).fetchall()
    for (day,) in completed_days:
        conn.execute(
            """INSERT OR REPLACE INTO analytics_daily
               (day, visits, page_views, unique_visitors, bot_visits)
               VALUES (?,
                   (SELECT COUNT(*) FROM analytics_visits WHERE date(first_seen, 'unixepoch') = ?),
                   (SELECT COUNT(*) FROM analytics_page_views WHERE date(created_at, 'unixepoch') = ?),
                   (SELECT COUNT(DISTINCT ip_hash) FROM analytics_visits WHERE date(first_seen, 'unixepoch') = ?),
                   (SELECT COUNT(*) FROM analytics_visits WHERE date(first_seen, 'unixepoch') = ? AND is_bot = 1))""",
            (day, day, day, day, day),
        )
    cutoff = now - retention_days * 24 * 60 * 60
    for statement in (
        (
            "DELETE FROM analytics_page_views WHERE id IN "
            "(SELECT id FROM analytics_page_views WHERE created_at < ? LIMIT 500)"
        ),
        (
            "DELETE FROM analytics_visits WHERE id IN "
            "(SELECT id FROM analytics_visits WHERE last_seen < ? LIMIT 500)"
        ),
    ):
        while conn.execute(statement, (cutoff,)).rowcount:
            pass
