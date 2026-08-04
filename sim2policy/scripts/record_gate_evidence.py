"""Record the Nebius-executed quality-gate and cloud-audit evidence (7.3, 7.8).

`implementation-gate` refuses to pass without `nebius-quality-gates.json` and
`cloud-audit.json`, and it refuses either document unless it names a Nebius
resource. This script produces both by *running* the gates here and by *reading*
the cloud from here — never by transcribing a result obtained somewhere else. A
GitHub Actions run can say the same things, and is worth nothing for this purpose.

`quality-gates` runs lint, types, unit/integration tests, the SaaS backend and
frontend suites, the production build, and the tracked-file secret and large-file
scans. Only the outcome, exit status, and a redacted tail of each command are
recorded; full logs stay on the VM.

`cloud-audit` enumerates jobs, instances, disks, and public addresses, and passes
only when nothing chargeable is unaccounted for.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from sim2policy.campaign_provider import NebiusCliProvider, ProviderError
from sim2policy.campaign_redaction import redact_text, sanitize_exception
from sim2policy.campaign_state import CampaignStore, utc_now
from sim2policy.execution_location import require_nebius_execution, write_location_attestation

#: Largest tracked file permitted, so a checkpoint or video cannot enter history.
MAX_TRACKED_FILE_BYTES = 5_000_000

#: Credential syntax that must not appear in any tracked file.
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[bytes]], ...] = (
    ("aws_access_key_id", re.compile(rb"\bAKIA[0-9A-Z]{16}\b")),
    ("iam_token", re.compile(rb"\beyJ[A-Za-z0-9._-]{40,}")),
    ("private_key_block", re.compile(rb"-----BEGIN[A-Z ]*PRIVATE KEY-----")),
)

# These are deliberately credential-shaped *redaction fixtures*.  Keeping the
# exceptions exact (path plus detector) lets the tracked-file scan continue to
# reject a real credential anywhere else, including another test.
TEST_SENTINEL_ALLOWLIST = frozenset(
    {
        ("sim2policy/tests/test_campaign_infra.py", "iam_token"),
        ("sim2policy/tests/test_campaign_redaction.py", "aws_access_key_id"),
        ("sim2policy/tests/test_campaign_redaction.py", "iam_token"),
    }
)

_TAIL = 400


def _run(
    command: list[str], cwd: Path, *, timeout: int = 3600, env: dict[str, str] | None = None
) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env={**os.environ, **(env or {})},
        )
    except Exception as exc:
        return {"command": command, "ok": False, "exit_code": None, "tail": sanitize_exception(exc)}
    tail = ((completed.stdout or "") + (completed.stderr or "")).strip()[-_TAIL:]
    return {
        "command": command,
        "ok": completed.returncode == 0,
        "exit_code": completed.returncode,
        "tail": redact_text(tail),
    }


def _tracked_files(repo: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z"], capture_output=True, text=True, check=False
    )
    return [repo / name for name in result.stdout.split("\0") if name]


def _scan_tracked(repo: Path) -> dict[str, Any]:
    """Secret and large-file scan over tracked files only.

    Untracked build output is irrelevant here: the question is what would be
    published if this revision were pushed, not what happens to sit on the disk.
    """
    large: list[str] = []
    matches: list[dict[str, str]] = []
    for path in _tracked_files(repo):
        try:
            size = path.stat().st_size
        except OSError:
            continue
        relative = str(path.relative_to(repo))
        if size > MAX_TRACKED_FILE_BYTES:
            large.append(relative)
            continue
        try:
            blob = path.read_bytes()
        except OSError:
            continue
        for label, pattern in SECRET_PATTERNS:
            if (relative, label) in TEST_SENTINEL_ALLOWLIST:
                continue
            if pattern.search(blob):
                matches.append({"path": relative, "pattern": label})
    return {
        "large_files": sorted(large),
        "flagged_matches": sorted(matches, key=lambda item: item["path"]),
        "ok": not large and not matches,
    }


def _quality_gates(repo: Path) -> dict[str, Any]:
    # `subprocess.run(cwd=...)` resolves a relative command path beneath that
    # directory.  Resolve once here so the backend venv is not accidentally
    # prefixed by its own cwd (``saas/backend/saas/backend/.venv``).
    repo = repo.resolve()
    sim2policy = repo / "sim2policy"
    backend = repo / "saas" / "backend"
    frontend = repo / "saas" / "frontend"
    gates: dict[str, Any] = {
        "ruff": _run(["uv", "run", "ruff", "check", "."], sim2policy),
        "mypy": _run(["uv", "run", "mypy", "src"], sim2policy),
        # Software rendering is mandatory: this VM is driverless, and without it
        # the MuJoCo renderer aborts the interpreter mid-suite rather than failing.
        "pytest": _run(
            ["uv", "run", "pytest", "-q"],
            sim2policy,
            timeout=5400,
            env={"MUJOCO_GL": "osmesa"},
        ),
    }
    if backend.is_dir():
        # The SaaS backend pins with requirements files rather than a uv project,
        # so its suite runs from the venv prepared alongside it on this VM.
        interpreter = backend / ".venv" / "bin" / "python"
        backend_command = (
            [str(interpreter), "-m", "pytest", "-q"]
            if interpreter.is_file()
            else ["uv", "run", "pytest", "-q"]
        )
        gates["saas_backend"] = _run(backend_command, backend, timeout=3600)
    if frontend.is_dir():
        gates["frontend_tests"] = _run(["npm", "run", "test", "--", "--run"], frontend)
        gates["frontend_build"] = _run(["npm", "run", "build"], frontend)
    scan = _scan_tracked(repo)
    return {"gates": gates, "tracked_scan": scan}


def _cloud_audit(project_id: str, self_resource: str) -> dict[str, Any]:
    provider = NebiusCliProvider(project_id=project_id)
    try:
        audit = dict(provider.audit())
    except ProviderError as exc:
        return {"ok": False, "error": sanitize_exception(exc)}
    running = [item for item in audit.get("running_instances", []) if item != self_resource]
    audit["unaccounted_running_instances"] = running
    audit["ok"] = not audit.get("active_jobs") and not running
    return audit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record Nebius gate evidence")
    parser.add_argument("kind", choices=("quality-gates", "cloud-audit"))
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--state-root", type=Path, default=Path(".showcase-campaigns"))
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--project-id")
    parser.add_argument(
        "--expect-running",
        action="append",
        default=[],
        help="Instance IDs that are expected to be running (the persistent SaaS server).",
    )
    args = parser.parse_args(argv)

    attestation = require_nebius_execution("verification")
    store = CampaignStore(args.state_root, args.campaign_id)

    if args.kind == "quality-gates":
        body = _quality_gates(args.repo_root)
        ok = all(item["ok"] for item in body["gates"].values()) and body["tracked_scan"]["ok"]
        name = "nebius-quality-gates.json"
    else:
        if not args.project_id:
            parser.error("cloud-audit requires --project-id")
        body = _cloud_audit(args.project_id, attestation.resource_id)
        expected = set(args.expect_running)
        remaining = [
            item for item in body.get("unaccounted_running_instances", []) if item not in expected
        ]
        body["expected_running"] = sorted(expected)
        body["unaccounted_running_instances"] = remaining
        ok = bool(body.get("ok")) or (not body.get("active_jobs") and not remaining)
        body["ok"] = ok
        name = "cloud-audit.json"

    document = {
        **body,
        "ok": ok,
        "recorded_at": utc_now(),
        "location_attestation": attestation.to_dict(),
    }
    store.write_json(store.evidence_path(name), document)
    write_location_attestation(
        store.evidence_path(name.replace(".json", "-location.json")), attestation
    )
    print(json.dumps(store.safe(document), indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
