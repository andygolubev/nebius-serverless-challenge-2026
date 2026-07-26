"""Sentinel-secret redaction across every persisted and printed campaign surface."""

from __future__ import annotations

# ruff: noqa: E501

import json
from pathlib import Path

from sim2policy.campaign_redaction import (
    REDACTED,
    environment_secret_values,
    redact,
    redact_text,
    sanitize_exception,
)
from sim2policy.campaign_state import CampaignStore

# Deliberately long and distinctive so a partial leak is still detectable.
SENTINEL_TOKEN = "SENTINEL-TOKEN-b3f1a9c7d5e2f8a1c4b7"
SENTINEL_KEY = "SENTINEL-ACCESSKEY-9f2e4d6a8c0b1e3f5a7d"
SENTINELS = (SENTINEL_TOKEN, SENTINEL_KEY)


def _environment() -> dict[str, str]:
    return {
        "NEBIUS_REGISTRY_PASSWORD": SENTINEL_TOKEN,
        "AWS_SECRET_ACCESS_KEY": SENTINEL_KEY,
        "SIM2POLICY_NEBIUS_REGION": "eu-north1",
    }


def test_credential_named_keys_drop_their_value_whatever_it_holds() -> None:
    result = redact({"access_key": "anything", "region": "eu-north1", "nested": {"token": "x"}})
    assert result["access_key"] == REDACTED
    assert result["nested"]["token"] == REDACTED
    assert result["region"] == "eu-north1"


def test_credential_shaped_values_are_rewritten_without_knowing_them() -> None:
    assert REDACTED in redact_text("Authorization: Bearer abcdefghijklmnop")
    assert REDACTED in redact_text("key AKIAIOSFODNN7EXAMPLE here")
    assert REDACTED in redact_text("token eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9abcdefg")
    signed = redact_text("https://objects.example/run/final.zip?X-Amz-Signature=deadbeefcafe&x=1")
    assert "X-Amz-Signature=" + REDACTED in signed
    # The object path survives; only the grant is removed.
    assert "run/final.zip" in signed


def test_known_environment_values_are_scrubbed_anywhere_they_appear() -> None:
    """The layer that catches a provider error echoing back a real token."""
    secrets = environment_secret_values(_environment())
    assert SENTINEL_TOKEN in secrets and SENTINEL_KEY in secrets
    # A plain value with no credential syntax and no credential-named key.
    leaked = f"provider rejected request using {SENTINEL_TOKEN} at endpoint"
    assert SENTINEL_TOKEN not in redact_text(leaked, extra=secrets)
    assert REDACTED in redact_text(leaked, extra=secrets)


def test_short_environment_values_never_shred_unrelated_text() -> None:
    secrets = environment_secret_values({"MY_TOKEN": "ab"})
    assert redact_text("stable text about ab", extra=secrets) == "stable text about ab"


def test_sanitize_exception_keeps_the_type_and_redacts_the_message() -> None:
    secrets = environment_secret_values(_environment())
    result = sanitize_exception(RuntimeError(f"denied for {SENTINEL_KEY}"), extra=secrets)
    assert result.startswith("RuntimeError:")
    assert SENTINEL_KEY not in result


def test_no_sentinel_reaches_state_journal_plans_audits_or_handoff(tmp_path: Path) -> None:
    """Every file the store writes is redacted on the way out, not by the caller."""
    store = CampaignStore(tmp_path, "gallery-result-test", environment=_environment())
    hostile = {
        "registry_password": SENTINEL_TOKEN,
        "note": f"provider said {SENTINEL_KEY} was invalid",
        "nested": [{"authorization": f"Bearer {SENTINEL_TOKEN}"}],
    }
    store.write(hostile)
    store.journal(hostile)
    store.write_json(store.plan_path("reacher:0:base"), hostile)
    store.write_json(store.audit_path("cloud.json"), hostile)
    store.write_text(store.handoff_path, f"holder used {SENTINEL_TOKEN} and {SENTINEL_KEY}")

    written = list(tmp_path.rglob("*"))
    assert written, "the store wrote nothing to inspect"
    for path in written:
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8")
        for sentinel in SENTINELS:
            assert sentinel not in content, f"{sentinel} leaked into {path.name}"


def test_redacted_state_is_still_valid_json_with_its_safe_fields_intact(tmp_path: Path) -> None:
    store = CampaignStore(tmp_path, "gallery-result-test", environment=_environment())
    store.write({"campaign_id": "gallery-result-test", "token": SENTINEL_TOKEN, "state": "PLANNED"})
    value = json.loads(store.state_path.read_text(encoding="utf-8"))
    assert value["campaign_id"] == "gallery-result-test"
    assert value["state"] == "PLANNED"
    assert value["token"] == REDACTED
