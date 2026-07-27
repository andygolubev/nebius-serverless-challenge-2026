"""Run one bounded Nebius smoke job and record its evidence (tasks 7.6 and 7.7).

A smoke is the cheapest question worth asking before a long paid run: does this
exact image, on this exact hardware, complete one update, write a checkpoint,
finalize explicitly, upload durably, and let the controller read the result back?
Everything here is bounded twice over — a tiny step budget *and* a hard provider
timeout — so a hung job costs minutes, not a night.

It deliberately uses the same pieces the campaign uses: `NebiusCliProvider` to
submit and poll, the same `hosted_*` entry points, the same durable prefix
convention, and the same `ArtifactStore` to read the result back from the cloud
rather than from the builder's disk. A smoke that exercised a different path would
prove nothing about the path that spends the money.

Checks recorded for each run:

* `submitted` / `terminal_success` — the job was created and reached success;
* `idempotent_reentry` — resolving the deterministic run name returns the same
  remote job, which is what makes a lost submission response recoverable;
* `checkpoint`, `finalization`, `durable_upload`, `cloud_side_read` — read back
  from durable storage, never from local files;
* `cleanup` — no chargeable resource is left behind afterwards.

Exit 0 only when every check passes. The evidence document is written either way,
because a failed smoke is exactly the record the next operator needs.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from sim2policy.campaign_provider import NebiusCliProvider, ProviderError
from sim2policy.campaign_redaction import sanitize_exception
from sim2policy.campaign_state import CampaignStore, utc_now, validate_run_identity
from sim2policy.config import StorageConfig
from sim2policy.execution_location import require_nebius_execution, write_location_attestation
from sim2policy.storage import ArtifactStore

#: Objects a completed run must have published under its own prefix.
REQUIRED_OBJECTS = (
    "metadata/status.json",
    "report/artifacts.json",
    "report/metrics.json",
    "report/resolved-config.json",
    "report/runtime-versions.json",
)

POLL_SECONDS = 20


def _build_command(args: argparse.Namespace) -> list[str]:
    """The bounded job command, mirroring the campaign's own argument array."""
    storage = [
        "--set", "storage.mode=s3",
        "--set", f"storage.bucket={args.bucket}",
        "--set", f"storage.endpoint_url={args.endpoint}",
        "--set", f"storage.region={args.region}",
    ]
    if args.runtime == "mjx" and args.curriculum:
        return [
            "python", "-m", "sim2policy.hosted_g1_curriculum",
            "--matrix", "configs/showcase_training_matrix.yaml",
            "--flat-config", "configs/g1_flat_mjx.yaml",
            "--rough-config", "configs/g1_mjx.yaml",
            "--run-id", args.run_id,
            "--image-digest", args.image_digest,
            *storage,
        ]
    module = "sim2policy.hosted_sb3" if args.runtime == "sb3" else "sim2policy.hosted_mjx"
    return [
        "python", "-m", module,
        "--config", args.config,
        "--run-id", args.run_id,
        "--gallery-example-id", args.gallery_example_id,
        "--set", f"training.total_steps={args.steps}",
        "--set", f"checkpoint.every_steps={args.checkpoint_every}",
        "--set", "seed=0",
        *storage,
    ]


def _plan(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "image_reference": f"{args.repository}@{args.image_digest}",
        "hardware": {
            "platform": args.platform,
            "preset": args.preset,
            "disk_gib": args.disk_gib,
            "timeout_minutes": args.timeout_minutes,
            "preemptible": False,
        },
        "command": _build_command(args),
        "subnet_id": args.subnet_id,
        "environment": {
            "SIM2POLICY_S3_BUCKET": args.bucket,
            "AWS_ENDPOINT_URL_S3": args.endpoint,
            "AWS_DEFAULT_REGION": args.region,
            "AWS_ACCESS_KEY_ID": args.access_key_id,
        },
        "secret_environment": {"AWS_SECRET_ACCESS_KEY": args.artifact_secret},
        "registry_secret": args.registry_secret,
    }


def _watch(provider: NebiusCliProvider, remote_id: str, deadline: float) -> dict[str, Any]:
    """Poll to a terminal state, or stop at the deadline without guessing."""
    last: dict[str, Any] = {"state": "UNKNOWN", "terminal": None}
    while time.time() < deadline:
        try:
            status = provider.poll(remote_id)
        except ProviderError as exc:
            return {"state": "POLL_FAILED", "terminal": None, "error": sanitize_exception(exc)}
        last = status.to_dict()
        if status.terminal:
            return last
        time.sleep(POLL_SECONDS)
    last["error"] = "smoke watch deadline reached before a terminal state"
    return last


def _cloud_checks(store: ArtifactStore) -> dict[str, Any]:
    """Read the run back from durable storage, the way the campaign verifier does."""
    present = {name: store.get_json_optional(name) is not None for name in REQUIRED_OBJECTS}
    status = store.get_json_optional("metadata/status.json") or {}
    artifacts = store.get_json_optional("report/artifacts.json") or {}
    metrics = store.get_json_optional("report/metrics.json") or {}
    names = set((artifacts.get("artifacts") or {}).keys())
    return {
        "objects_present": present,
        "durable_upload": all(present.values()),
        "cloud_side_read": bool(status) and bool(metrics),
        "run_status": str(status.get("status", "")),
        "finalization": str(status.get("status", "")) == "completed",
        "checkpoint": bool((metrics.get("selected_checkpoint") or {}).get("sha256")),
        "artifact_names": sorted(names),
        "has_final_policy": "final_policy" in names,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one bounded Nebius smoke job")
    parser.add_argument("--runtime", required=True, choices=("sb3", "mjx"))
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--state-root", type=Path, default=Path(".showcase-campaigns"))
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--image-digest", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--config", default="configs/reacher_sb3.yaml")
    parser.add_argument("--gallery-example-id", default="reacher-target")
    parser.add_argument("--curriculum", action="store_true")
    parser.add_argument("--steps", type=int, default=4096)
    parser.add_argument("--checkpoint-every", type=int, default=2048)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--preset", required=True)
    parser.add_argument("--disk-gib", type=int, default=100)
    parser.add_argument("--timeout-minutes", type=int, required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--region", default="eu-north1")
    parser.add_argument("--prefix", default="sim2policy")
    parser.add_argument("--subnet-id", required=True)
    parser.add_argument("--access-key-id", required=True)
    parser.add_argument("--artifact-secret", required=True, help="MysteryBox selector, not a value")
    parser.add_argument("--registry-secret", required=True, help="MysteryBox selector, not a value")
    parser.add_argument(
        "--watch-minutes",
        type=int,
        default=None,
        help="Controller-side deadline; defaults to the job timeout plus five minutes.",
    )
    args = parser.parse_args(argv)

    attestation = require_nebius_execution("smoke")
    validate_run_identity(args.run_id)
    campaign = CampaignStore(args.state_root, args.campaign_id)
    provider = NebiusCliProvider(project_id=args.project_id)
    plan = _plan(args)
    idempotency_key = f"smoke-{args.run_id}"

    checks: dict[str, Any] = {}
    remote_id: str | None = None
    error: str | None = None

    # A smoke re-run must adopt the existing job rather than create a second one.
    try:
        existing = provider.find_by_name(args.run_id)
    except ProviderError as exc:
        existing, error = None, sanitize_exception(exc)
    if existing is not None:
        remote_id = existing.remote_id
        checks["submitted"] = True
        checks["adopted_existing"] = True
    else:
        try:
            remote_id = provider.submit(plan, idempotency_key=idempotency_key)
            checks["submitted"] = True
        except ProviderError as exc:
            checks["submitted"] = False
            error = sanitize_exception(exc)

    status: dict[str, Any] = {}
    if remote_id:
        watch_minutes = args.watch_minutes or (args.timeout_minutes + 5)
        status = _watch(provider, remote_id, time.time() + watch_minutes * 60)
        checks["terminal_success"] = str(status.get("state", "")).upper() in {
            "COMPLETED",
            "SUCCEEDED",
        }
        # Resolving the deterministic name again must return the same job: this is
        # what makes a lost submission response recoverable instead of duplicated.
        try:
            again = provider.find_by_name(args.run_id)
            checks["idempotent_reentry"] = again is not None and again.remote_id == remote_id
        except ProviderError:
            checks["idempotent_reentry"] = False

    cloud: dict[str, Any] = {}
    if checks.get("terminal_success"):
        store = ArtifactStore(
            StorageConfig(
                mode="s3",
                bucket=args.bucket,
                prefix=args.prefix,
                endpoint_url=args.endpoint,
                region=args.region,
            ),
            args.run_id,
        )
        cloud = _cloud_checks(store)
        for name in ("durable_upload", "cloud_side_read", "finalization", "checkpoint"):
            checks[name] = bool(cloud.get(name))

    # Nothing chargeable may survive the smoke. AI jobs are ephemeral, so this
    # asserts the absence of any active job or running instance we did not expect.
    try:
        audit = provider.audit()
        running = [
            item for item in audit.get("running_instances", []) if item != attestation.resource_id
        ]
        checks["cleanup"] = not audit.get("active_jobs") and not running
    except ProviderError as exc:
        audit, checks["cleanup"] = {"error": sanitize_exception(exc)}, False

    document = {
        "runtime": args.runtime,
        "run_id": args.run_id,
        "remote_id": remote_id,
        "image_digest": args.image_digest,
        "durable_prefix": f"{args.prefix}/{args.run_id}/",
        "bounded": {
            "steps": args.steps,
            "checkpoint_every_steps": args.checkpoint_every,
            "timeout_minutes": args.timeout_minutes,
        },
        "hardware": plan["hardware"],
        "provider_status": status,
        "cloud_evidence": cloud,
        "cloud_audit": audit if isinstance(audit, dict) else {},
        "checks": dict(sorted(checks.items())),
        "failed_checks": sorted(name for name, ok in checks.items() if not ok),
        "error": error,
        "recorded_at": utc_now(),
        "location_attestation": attestation.to_dict(),
        "ok": bool(checks) and all(checks.values()),
    }
    campaign.write_json(campaign.evidence_path(f"{args.runtime}-smoke.json"), document)
    write_location_attestation(
        campaign.evidence_path(f"{args.runtime}-smoke-location.json"), attestation
    )
    print(json.dumps(campaign.safe(document), indent=2, sort_keys=True))
    return 0 if document["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
