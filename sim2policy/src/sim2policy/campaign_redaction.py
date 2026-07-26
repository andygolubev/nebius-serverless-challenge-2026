"""Redaction by construction for every campaign output, state file, and evidence record.

The campaign persists JSON and prints envelopes on a host that also holds registry
credentials, artifact access keys, and provider tokens. Rather than trusting each
call site to remember, the store and the CLI envelope both funnel through `redact`,
so a value can only reach disk or stdout after passing through here.

Three independent layers, because any one of them alone is escapable:

1. **Key-shaped**: a mapping key that names a credential drops its value entirely.
2. **Value-shaped**: strings matching known credential syntax (bearer tokens, AWS
   key IDs, PEM blocks, presigned-URL signature parameters) are rewritten.
3. **Known-value**: the exact values of credential-named environment variables are
   scrubbed as substrings anywhere they appear. This is the layer that catches a
   provider error message echoing back a real token, which neither of the other
   two would recognize.
"""

from __future__ import annotations

import os
import re
from collections.abc import Collection, Mapping
from typing import Any

REDACTED = "<redacted>"

# A mapping key naming a credential: its value never survives, whatever it holds.
SECRET_KEY_RE = re.compile(
    r"(?i)(secret|token|password|passwd|credential|authorization|bearer"
    r"|api[_-]?key|access[_-]?key|private[_-]?key|signature|session)"
)

# Credential syntax recognizable without knowing the value.
SECRET_VALUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)-----BEGIN[A-Z ]*PRIVATE KEY-----[\s\S]*?-----END[A-Z ]*KEY-----"),
    # Presigned-URL credential parameters; keeps the object path, drops the grant.
    re.compile(r"(?i)([?&](?:X-Amz-Signature|X-Amz-Credential|X-Amz-Security-Token|Signature|sig)=)[^&\s]+"),
    # `nebius` CLI / SDK IAM tokens are long dotted JWTs.
    re.compile(r"\beyJ[A-Za-z0-9._-]{20,}"),
)

# Minimum length before an environment value is treated as a scrubable secret.
# Short values ("1", "true", "us") would otherwise shred unrelated text.
_MIN_KNOWN_VALUE = 8
_MAX_TEXT = 4096


def environment_secret_values(
    environment: Mapping[str, str] | None = None,
) -> frozenset[str]:
    """Exact values of credential-named environment variables, for substring scrubbing.

    Deliberately reads names, not values, to decide what is secret: a value is
    opaque, but `NEBIUS_REGISTRY_PASSWORD` announces itself.
    """
    source = os.environ if environment is None else environment
    return frozenset(
        value
        for name, value in source.items()
        if SECRET_KEY_RE.search(name) and isinstance(value, str) and len(value) >= _MIN_KNOWN_VALUE
    )


def redact_text(value: str, *, extra: Collection[str] = ()) -> str:
    """Scrub credential syntax and known credential values out of one string."""
    if len(value) > _MAX_TEXT:
        value = value[:_MAX_TEXT] + "...<truncated>"
    for known in sorted(set(extra), key=len, reverse=True):
        if known and len(known) >= _MIN_KNOWN_VALUE:
            value = value.replace(known, REDACTED)
    for pattern in SECRET_VALUE_PATTERNS:
        if pattern.groups:
            value = pattern.sub(rf"\g<1>{REDACTED}", value)
        else:
            value = pattern.sub(REDACTED, value)
    return value


def redact(value: Any, *, extra: Collection[str] = ()) -> Any:
    """Recursively redact a JSON-shaped value. Non-JSON leaves become their repr."""
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            name = str(key)
            result[name] = REDACTED if SECRET_KEY_RE.search(name) else redact(item, extra=extra)
        return result
    if isinstance(value, (list, tuple)):
        return [redact(item, extra=extra) for item in value]
    if isinstance(value, str):
        return redact_text(value, extra=extra)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return redact_text(str(value), extra=extra)


def sanitize_exception(exc: BaseException, *, extra: Collection[str] = ()) -> str:
    """Reduce any provider/environment exception to a safe, bounded description.

    Provider SDKs routinely put the failing request — headers included — into the
    exception message, so the message is redacted rather than trusted, and the
    exception type is reported separately because it is always safe.
    """
    return f"{type(exc).__name__}: {redact_text(str(exc), extra=extra)}"
