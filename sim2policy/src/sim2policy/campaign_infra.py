"""Live, non-secret preflight probes for repository, infrastructure, and quota.

`preflight` has to answer a question the persisted campaign state cannot: is the
cloud, right now, able to run the attempt that is about to be paid for. That means
talking to Git, OpenTofu, and the Nebius API — the three places where a stale
assumption turns into a failed or, worse, a silently misconfigured paid job.

Three rules keep that safe:

* **Read-only.** Every command here lists, gets, or resolves. Nothing creates,
  modifies, or deletes, so a probe can never be the thing that spends money.
* **Presence, not payload.** Credential availability is reported as booleans. The
  probe proves a selector or token resolves; it never reads, prints, or persists
  the value, and secret-named OpenTofu outputs are dropped before they reach a
  result dictionary.
* **Informational is never sufficient.** A GitHub Actions result is recorded with
  `informational=True` and is excluded from the pass decision by construction, so
  a third-party runner's green check cannot stand in for Nebius evidence.

A failed probe is a failure, not an exception: `Probe.ok is False` with a redacted
reason. The caller decides what blocks, and the whole set is always collected so a
single handoff shows every problem rather than the first one.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sim2policy.campaign_redaction import (
    SECRET_KEY_RE,
    environment_secret_values,
    redact_text,
    sanitize_exception,
)

#: OpenTofu outputs that must resolve before any paid attempt, and whose values are
#: themselves non-secret (identifiers and endpoints).
REQUIRED_INFRA_OUTPUTS = (
    "project_id",
    "saas_subnet_id",
    "registry_fqdn",
    "artifact_bucket",
    "artifact_endpoint",
    "artifact_region",
)

#: Outputs that must exist for the job to authenticate, and whose values must never
#: leave the probe. Only their presence is reported.
REQUIRED_CREDENTIAL_OUTPUTS = (
    "artifact_secret_selector",
    "artifact_access_key_id",
    "registry_pull_secret_selector",
)

#: Quota allowance that governs each matrix platform.
PLATFORM_QUOTA = {
    "gpu-h100-sxm": "compute.instance.gpu.h100",
    "gpu-l40s-a": "compute.instance.gpu.l40s",
    "cpu-d3": "compute.instance.non-gpu.vcpu",
}
DISK_QUOTA = "compute.disk.size.network-ssd"

#: The runbook's expected job disk. A matrix that drifts from it is a review error.
EXPECTED_JOB_DISK_GIB = 100

_GIB = 1024**3
_MAX_DETAIL_TEXT = 400


@dataclass(frozen=True)
class Probe:
    """One preflight answer: a decision, plus non-secret evidence for the handoff."""

    name: str
    ok: bool
    detail: dict[str, Any] = field(default_factory=dict)
    #: Recorded for the operator, excluded from the pass decision.
    informational: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ok": self.ok,
            "informational": self.informational,
            "detail": self.detail,
        }


class ProbeError(RuntimeError):
    """Raised only for a programming error in probe construction, never for a
    cloud or repository condition — those become `Probe(ok=False)`."""


def _presence(values: Mapping[str, Any], names: Sequence[str]) -> dict[str, bool]:
    """Report whether each named output resolved, without touching its value."""
    return {name: bool(str(values.get(name, "")).strip()) for name in names}


def _drop_secrets(values: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only outputs whose *name* does not announce a credential.

    Applied before any output reaches a probe detail, so a newly added sensitive
    OpenTofu output is excluded by default rather than by remembering to list it.
    """
    return {
        name: value for name, value in values.items() if not SECRET_KEY_RE.search(str(name))
    }


class InfrastructurePreflight:
    """Read-only probes against Git, OpenTofu, and the Nebius control plane.

    Every external call goes through an injected runner, so the whole class is
    testable without a network and without a repository checkout.
    """

    def __init__(
        self,
        *,
        project_id: str,
        region: str = "eu-north1",
        repo_root: Path,
        infra_dir: Path | None = None,
        runner: Any = subprocess.run,
        environment: Mapping[str, str] | None = None,
        timeout_seconds: int = 120,
        nebius_binary: str = "nebius",
        tofu_binary: str = "tofu",
        git_binary: str = "git",
        gh_binary: str = "gh",
    ) -> None:
        self.project_id = project_id
        self.region = region
        self.repo_root = Path(repo_root)
        self.infra_dir = Path(infra_dir) if infra_dir else self.repo_root / "infra/nebius"
        self._runner = runner
        self._environment = dict(environment or {})
        # Known credential values are scrubbed out of every captured stream, so a
        # provider error echoing a token back cannot reach a probe detail.
        self._secrets = environment_secret_values(self._environment)
        self._timeout = timeout_seconds
        self._nebius = nebius_binary
        self._tofu = tofu_binary
        self._git = git_binary
        self._gh = gh_binary

    # -- command plumbing ----------------------------------------------------

    def _run(self, command: Sequence[str]) -> tuple[int, str, str]:
        """Run one read-only command. stderr is redacted here, not at the call site."""
        try:
            completed = self._runner(
                list(command),
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
            )
        except Exception as exc:  # missing binary, timeout, OS refusal
            return 127, "", sanitize_exception(exc, extra=self._secrets)
        stderr = redact_text(str(completed.stderr or ""), extra=self._secrets)[:_MAX_DETAIL_TEXT]
        return int(completed.returncode), str(completed.stdout or ""), stderr

    def _json(self, command: Sequence[str]) -> tuple[Any, str | None]:
        code, stdout, stderr = self._run(command)
        if code != 0:
            return None, f"exit {code}: {stderr}" if stderr else f"exit {code}"
        if not stdout.strip():
            return None, "empty response"
        try:
            return json.loads(stdout), None
        except json.JSONDecodeError as exc:
            return None, sanitize_exception(exc, extra=self._secrets)

    # -- repository and revision --------------------------------------------

    def repository(
        self, *, expected_branch: str = "main", expected_revision: str | None = None
    ) -> Probe:
        """Prove the checkout is the reviewed branch/revision with no tracked overlap."""
        detail: dict[str, Any] = {"expected_branch": expected_branch}
        code, branch, stderr = self._run(
            [self._git, "-C", str(self.repo_root), "rev-parse", "--abbrev-ref", "HEAD"]
        )
        if code != 0:
            return Probe("repository", False, {**detail, "error": stderr or f"exit {code}"})
        branch = branch.strip()
        detail["branch"] = branch

        _code, head, _stderr = self._run(
            [self._git, "-C", str(self.repo_root), "rev-parse", "HEAD"]
        )
        head = head.strip()
        detail["revision"] = head

        _code, porcelain, _stderr = self._run(
            [self._git, "-C", str(self.repo_root), "status", "--porcelain"]
        )
        # Untracked files are campaign state and evidence; a *tracked* modification
        # means the checkout no longer is the revision that was reviewed and built.
        tracked_overlap = sorted(
            line[3:].strip()
            for line in porcelain.splitlines()
            if line.strip() and not line.startswith("??")
        )
        detail["tracked_overlap"] = tracked_overlap[:20]
        detail["tracked_overlap_count"] = len(tracked_overlap)

        wanted = (expected_revision or "").removeprefix("git:").strip()
        detail["expected_revision"] = wanted or None
        revision_ok = bool(wanted) and head == wanted
        detail["revision_matches"] = revision_ok

        ok = branch == expected_branch and not tracked_overlap and revision_ok
        return Probe("repository", ok, detail)

    # -- OpenTofu infrastructure outputs ------------------------------------

    def _tofu_outputs(self) -> tuple[dict[str, Any] | None, str, str | None]:
        """Resolve outputs live, falling back to a recorded non-secret snapshot.

        The snapshot exists because the state backend's static key is deliberately
        not distributed to every Nebius VM; when it is used the source is recorded
        so no reader can mistake it for a live read.
        """
        payload, error = self._json(
            [self._tofu, f"-chdir={self.infra_dir}", "output", "-json"]
        )
        if isinstance(payload, dict) and payload:
            values = {
                name: item.get("value") if isinstance(item, Mapping) else item
                for name, item in payload.items()
            }
            return values, "opentofu", None
        snapshot = self._environment.get("SIM2POLICY_INFRA_OUTPUTS")
        if snapshot:
            path = Path(snapshot)
            try:
                recorded = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                return None, "unavailable", sanitize_exception(exc, extra=self._secrets)
            if isinstance(recorded, Mapping):
                values = dict(recorded.get("values") or recorded)
                for name, present in (recorded.get("credentials") or {}).items():
                    # A snapshot records credential presence, never the value.
                    values.setdefault(name, "recorded" if present else "")
                return values, "recorded-snapshot", None
        return None, "unavailable", error

    def infrastructure(self) -> Probe:
        """Resolve project, subnet, registry, bucket, endpoint, region, selectors."""
        values, source, error = self._tofu_outputs()
        detail: dict[str, Any] = {"source": source}
        if values is None:
            return Probe("infrastructure", False, {**detail, "error": error or "unresolved"})
        resolved = _drop_secrets(values)
        missing = [name for name in REQUIRED_INFRA_OUTPUTS if not str(values.get(name, "")).strip()]
        detail["outputs"] = {
            name: resolved.get(name) for name in REQUIRED_INFRA_OUTPUTS if name in resolved
        }
        detail["missing_outputs"] = missing
        project = str(values.get("project_id", "")).strip()
        detail["project_scope_matches"] = project == self.project_id
        detail["region_matches"] = str(values.get("artifact_region", "")).strip() == self.region
        ok = (
            not missing
            and detail["project_scope_matches"]
            and detail["region_matches"]
        )
        return Probe("infrastructure", ok, detail)

    # -- credential availability --------------------------------------------

    def credentials(self) -> Probe:
        """Prove every credential path resolves; never read or record a value."""
        values, source, _error = self._tofu_outputs()
        present = _presence(values or {}, REQUIRED_CREDENTIAL_OUTPUTS)
        # `get-access-token` prints a bearer token; the output is deliberately
        # discarded and only the exit status is kept.
        code, _stdout, stderr = self._run([self._nebius, "iam", "get-access-token"])
        iam_ok = code == 0
        # Reported as name lists rather than a name-keyed mapping: redaction drops
        # the value under any credential-shaped key, which would erase the very
        # booleans this probe exists to record.
        detail: dict[str, Any] = {
            "source": source,
            "resolved_auth_paths": sorted(name for name, ok in present.items() if ok),
            "unresolved_auth_paths": sorted(name for name, ok in present.items() if not ok),
            "iam_token_available": iam_ok,
            "job_selectors_present": sorted(
                name
                for name in ("NEBIUS_REGISTRY_SECRET_VERSION", "NEBIUS_ARTIFACT_SECRET_VERSION")
                if self._environment.get(name)
            ),
        }
        if not iam_ok and stderr:
            detail["iam_error"] = stderr
        return Probe("credentials", iam_ok and all(present.values()), detail)

    # -- preset, quota, disk, timeout ---------------------------------------

    def preset_and_quota(self, hardware: Mapping[str, Any]) -> Probe:
        """Check the exact platform/preset/disk/timeout this attempt will request.

        H100 quota is examined only for a GPU card and CPU quota only for a CPU
        card, so an unrelated exhausted quota cannot block the wrong attempt.
        """
        platform = str(hardware.get("platform", ""))
        preset = str(hardware.get("preset", ""))
        disk_gib = int(hardware.get("disk_gib") or 0)
        timeout_minutes = int(hardware.get("timeout_minutes") or 0)
        detail: dict[str, Any] = {
            "platform": platform,
            "preset": preset,
            "region": self.region,
            "disk_gib": disk_gib,
            "timeout_minutes": timeout_minutes,
            "disk_matches_expected": disk_gib == EXPECTED_JOB_DISK_GIB,
            "timeout_declared": timeout_minutes > 0,
            "non_preemptible": hardware.get("preemptible") is False,
        }

        platforms, error = self._json(
            [self._nebius, "compute", "platform", "list",
             "--parent-id", self.project_id, "--format", "json"]
        )
        if not isinstance(platforms, dict):
            return Probe("preset_quota", False, {**detail, "error": error or "no platform list"})
        presets: list[str] = []
        gpu_count = 0
        vcpu_count = 0
        for item in platforms.get("items", []):
            if not isinstance(item, Mapping):
                continue
            if (item.get("metadata") or {}).get("name") != platform:
                continue
            for entry in (item.get("spec") or {}).get("presets", []):
                if not isinstance(entry, Mapping):
                    continue
                presets.append(str(entry.get("name")))
                if entry.get("name") == preset:
                    resources = entry.get("resources") or {}
                    gpu_count = int(resources.get("gpu_count") or 0)
                    vcpu_count = int(resources.get("vcpu_count") or 0)
        detail["preset_available"] = preset in presets
        detail["preset_resources"] = {"gpu_count": gpu_count, "vcpu_count": vcpu_count}

        allowances, quota_error = self._json(
            [self._nebius, "quotas", "quota-allowance", "list",
             "--parent-id", self.project_id, "--format", "json"]
        )
        if not isinstance(allowances, dict):
            return Probe(
                "preset_quota", False, {**detail, "error": quota_error or "no quota allowances"}
            )
        indexed = {
            str((item.get("metadata") or {}).get("name")): item
            for item in allowances.get("items", [])
            if isinstance(item, Mapping)
            and str(((item.get("spec") or {}).get("region")) or "") == self.region
        }
        compute_quota = PLATFORM_QUOTA.get(platform)
        required_compute = gpu_count if gpu_count else vcpu_count
        quotas = {
            "compute": self._quota_headroom(indexed, compute_quota, required_compute),
            "disk": self._quota_headroom(indexed, DISK_QUOTA, disk_gib * _GIB),
        }
        detail["quotas"] = quotas
        ok = (
            detail["preset_available"]
            and detail["disk_matches_expected"]
            and detail["timeout_declared"]
            and detail["non_preemptible"]
            and all(entry["sufficient"] for entry in quotas.values())
        )
        return Probe("preset_quota", ok, detail)

    def _quota_headroom(
        self, allowances: Mapping[str, Any], name: str | None, required: int
    ) -> dict[str, Any]:
        """Decide sufficiency from the declared allowance for one quota.

        A limit the API does not publish is reported as unknown rather than
        assumed: the allowance must still exist for the region, and any limit that
        *is* published must leave room for this attempt.
        """
        if not name:
            return {"name": None, "declared": False, "sufficient": False, "required": required}
        item = allowances.get(name)
        if not isinstance(item, Mapping):
            return {"name": name, "declared": False, "sufficient": False, "required": required}
        status = item.get("status") or {}
        usage = _as_int(status.get("usage")) or 0
        limit = _as_int((item.get("spec") or {}).get("limit") or status.get("limit"))
        sufficient = True if limit is None else usage + required <= limit
        return {
            "name": name,
            "declared": True,
            "required": required,
            "usage": usage,
            "limit": limit,
            "limit_known": limit is not None,
            "sufficient": sufficient,
        }

    # -- informational third-party status -----------------------------------

    def github_status(self, *, limit: int = 5) -> Probe:
        """Repository/deployment health only. Never satisfies a Nebius attestation.

        Returned with `informational=True` and `ok=True` in every case, including
        failure to run `gh` at all, so that no code path can promote a GitHub result
        into a preflight pass or demote the attempt because CI is red.
        """
        payload, error = self._json(
            [self._gh, "run", "list", "--limit", str(limit),
             "--json", "conclusion,status,workflowName,headBranch"]
        )
        detail: dict[str, Any] = {
            "role": "repository health only; cannot satisfy a Nebius attestation",
            "available": payload is not None,
        }
        if payload is None:
            detail["error"] = error or "unavailable"
            return Probe("github_actions", True, detail, informational=True)
        runs = payload.get("items", payload) if isinstance(payload, dict) else payload
        detail["runs"] = [
            {
                "workflow": str(run.get("workflowName", "")),
                "branch": str(run.get("headBranch", "")),
                "status": str(run.get("status", "")),
                "conclusion": str(run.get("conclusion", "")),
            }
            for run in (runs or [])
            if isinstance(run, Mapping)
        ][:limit]
        return Probe("github_actions", True, detail, informational=True)

    # -- full sweep ----------------------------------------------------------

    def collect(
        self,
        *,
        expected_revision: str | None,
        hardware: Mapping[str, Any] | None = None,
        expected_branch: str = "main",
    ) -> list[Probe]:
        """Run every probe, always. One handoff should show every problem at once."""
        probes = [
            self.repository(expected_branch=expected_branch, expected_revision=expected_revision),
            self.infrastructure(),
            self.credentials(),
        ]
        if hardware is not None:
            probes.append(self.preset_and_quota(hardware))
        probes.append(self.github_status())
        return probes


def _as_int(value: Any) -> int | None:
    """Parse a quota number, keeping "absent" distinguishable from zero."""
    if value is None or value == "":
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def probe_from_environment(
    environment: Mapping[str, str],
    *,
    repo_root: Path | None = None,
    runner: Any = subprocess.run,
) -> InfrastructurePreflight | None:
    """Build a live prober only when the runner has declared its Nebius scope.

    Absent an explicit project scope there is nothing safe to probe, and the caller
    treats `None` as "live probes unavailable", which fails preflight closed rather
    than passing it silently.
    """
    project_id = environment.get("SIM2POLICY_NEBIUS_PROJECT_ID", "").strip()
    if not project_id:
        return None
    root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[2]
    return InfrastructurePreflight(
        project_id=project_id,
        region=environment.get("SIM2POLICY_NEBIUS_REGION", "eu-north1"),
        repo_root=root,
        runner=runner,
        environment=environment,
    )
