"""Live preflight probes: read-only, fail-closed, and never value-disclosing."""

# ruff: noqa: E501

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from sim2policy.campaign_infra import (
    EXPECTED_JOB_DISK_GIB,
    InfrastructurePreflight,
    probe_from_environment,
)

PROJECT = "project-e00wkbbppr00tab5fhhmz7"
REVISION = "a" * 40
SECRET_SELECTOR = "mysterybox-e00secret/version-e00secretversion"
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.super-secret-token-value.signature"

CPU_HARDWARE = {
    "platform": "cpu-d3",
    "preset": "8vcpu-32gb",
    "disk_gib": EXPECTED_JOB_DISK_GIB,
    "timeout_minutes": 60,
    "preemptible": False,
}
GPU_HARDWARE = {
    "platform": "gpu-h100-sxm",
    "preset": "1gpu-16vcpu-200gb",
    "disk_gib": EXPECTED_JOB_DISK_GIB,
    "timeout_minutes": 45,
    "preemptible": False,
}


@dataclass
class Completed:
    returncode: int
    stdout: str = ""
    stderr: str = ""


def _tofu_outputs(**overrides: Any) -> str:
    values = {
        "project_id": PROJECT,
        "saas_subnet_id": "vpcsubnet-e00re7tmw1apqd4pmm",
        "registry_fqdn": "cr.eu-north1.nebius.cloud",
        "artifact_bucket": "sim2policy-artifacts",
        "artifact_endpoint": "https://storage.eu-north1.nebius.cloud",
        "artifact_region": "eu-north1",
        "artifact_secret_selector": SECRET_SELECTOR,
        "artifact_access_key_id": "AKIAEXAMPLE1234567890",
        "registry_pull_secret_selector": SECRET_SELECTOR,
    }
    values.update(overrides)
    return json.dumps({name: {"value": value, "sensitive": False} for name, value in values.items()})


def _platforms() -> str:
    return json.dumps(
        {
            "items": [
                {
                    "metadata": {"name": "cpu-d3"},
                    "spec": {"presets": [{"name": "8vcpu-32gb", "resources": {"vcpu_count": 8, "memory_gibibytes": 32}}]},
                },
                {
                    "metadata": {"name": "gpu-h100-sxm"},
                    "spec": {"presets": [{"name": "1gpu-16vcpu-200gb", "resources": {"vcpu_count": 16, "gpu_count": 1}}]},
                },
            ]
        }
    )


def _allowances(*, limits: dict[str, int] | None = None, region: str = "eu-north1") -> str:
    limits = limits or {}
    names = (
        "compute.instance.gpu.h100",
        "compute.instance.non-gpu.vcpu",
        "compute.disk.size.network-ssd",
    )
    items = []
    for name in names:
        spec: dict[str, Any] = {"region": region}
        if name in limits:
            spec["limit"] = limits[name]
        items.append({"metadata": {"name": name}, "spec": spec, "status": {"usage": "2"}})
    return json.dumps({"items": items})


TOFU = ("tofu",)
IAM = ("nebius", "iam", "get-access-token")
PLATFORMS = ("nebius", "compute", "platform", "list")
QUOTAS = ("nebius", "quotas", "quota-allowance", "list")
GH = ("gh", "run", "list")


def _default_script() -> dict[tuple[str, ...], Completed]:
    return {
        TOFU: Completed(0, _tofu_outputs()),
        IAM: Completed(0, TOKEN),
        PLATFORMS: Completed(0, _platforms()),
        QUOTAS: Completed(0, _allowances()),
        GH: Completed(0, json.dumps([{"workflowName": "saas-image", "headBranch": "debug-portal", "status": "completed", "conclusion": "success"}])),
    }


class GitScript:
    """Git needs per-subcommand answers, so it gets its own small dispatcher."""

    def __init__(self, *, branch="debug-portal", head=REVISION, porcelain="") -> None:
        self.branch, self.head, self.porcelain = branch, head, porcelain

    def __call__(self, command) -> Completed:
        if "--abbrev-ref" in command:
            return Completed(0, self.branch + "\n")
        if "rev-parse" in command:
            return Completed(0, self.head + "\n")
        if "status" in command:
            return Completed(0, self.porcelain)
        return Completed(1, "", "unexpected git command")


class Runner:
    """Full fake environment: git dispatcher plus scripted external commands."""

    def __init__(
        self,
        *,
        git: GitScript | None = None,
        script: dict[tuple[str, ...], Completed] | None = None,
    ) -> None:
        self.git = git or GitScript()
        self.script = _default_script() | (script or {})
        self.calls: list[list[str]] = []

    def __call__(self, command, **_kwargs):
        self.calls.append(list(command))
        if command[0] == "git":
            return self.git(command)
        for prefix, result in self.script.items():
            if tuple(command[: len(prefix)]) == prefix:
                return result
        return Completed(127, "", "not scripted")


def _probe(runner: Runner, tmp_path: Path, **kwargs: Any) -> InfrastructurePreflight:
    return InfrastructurePreflight(
        project_id=PROJECT,
        repo_root=tmp_path,
        runner=runner,
        environment=kwargs.pop("environment", {}),
        **kwargs,
    )


# -- repository ---------------------------------------------------------------


def test_repository_probe_accepts_the_reviewed_branch_and_revision(tmp_path: Path) -> None:
    probe = _probe(Runner(), tmp_path).repository(expected_revision="git:" + REVISION)
    assert probe.ok is True
    assert probe.detail["branch"] == "debug-portal"
    assert probe.detail["tracked_overlap"] == []


def test_repository_probe_rejects_a_tracked_modification(tmp_path: Path) -> None:
    runner = Runner(git=GitScript(porcelain=" M sim2policy/src/sim2policy/run.py\n?? notes.txt\n"))
    probe = _probe(runner, tmp_path).repository(expected_revision=REVISION)
    assert probe.ok is False
    # Untracked campaign state is expected; a tracked edit means the checkout is
    # no longer the revision that was reviewed and built.
    assert probe.detail["tracked_overlap"] == ["sim2policy/src/sim2policy/run.py"]


def test_repository_probe_rejects_main_and_a_drifted_revision(tmp_path: Path) -> None:
    on_main = _probe(Runner(git=GitScript(branch="main")), tmp_path)
    assert on_main.repository(expected_revision=REVISION).ok is False
    drifted = _probe(Runner(git=GitScript(head="b" * 40)), tmp_path)
    result = drifted.repository(expected_revision=REVISION)
    assert result.ok is False and result.detail["revision_matches"] is False


def test_repository_probe_requires_an_expected_revision(tmp_path: Path) -> None:
    assert _probe(Runner(), tmp_path).repository(expected_revision=None).ok is False


# -- infrastructure -----------------------------------------------------------


def test_infrastructure_probe_resolves_required_outputs_without_secret_values(tmp_path: Path) -> None:
    probe = _probe(Runner(), tmp_path).infrastructure()
    assert probe.ok is True
    assert probe.detail["source"] == "opentofu"
    assert probe.detail["outputs"]["registry_fqdn"] == "cr.eu-north1.nebius.cloud"
    serialized = json.dumps(probe.to_dict())
    assert SECRET_SELECTOR not in serialized
    assert "AKIAEXAMPLE1234567890" not in serialized


def test_infrastructure_probe_fails_on_a_missing_output_or_foreign_project(tmp_path: Path) -> None:
    missing = Runner(script={TOFU: Completed(0, _tofu_outputs(artifact_bucket=""))})
    result = _probe(missing, tmp_path).infrastructure()
    assert result.ok is False and result.detail["missing_outputs"] == ["artifact_bucket"]

    foreign = Runner(script={TOFU: Completed(0, _tofu_outputs(project_id="project-someoneelse"))})
    result = _probe(foreign, tmp_path).infrastructure()
    assert result.ok is False and result.detail["project_scope_matches"] is False


def test_infrastructure_probe_falls_back_to_a_recorded_snapshot_and_says_so(tmp_path: Path) -> None:
    snapshot = tmp_path / "infra-outputs.json"
    snapshot.write_text(
        json.dumps(
            {
                "values": {
                    "project_id": PROJECT,
                    "saas_subnet_id": "vpcsubnet-e00re7tmw1apqd4pmm",
                    "registry_fqdn": "cr.eu-north1.nebius.cloud",
                    "artifact_bucket": "sim2policy-artifacts",
                    "artifact_endpoint": "https://storage.eu-north1.nebius.cloud",
                    "artifact_region": "eu-north1",
                },
                "credentials": {
                    "artifact_secret_selector": True,
                    "artifact_access_key_id": True,
                    "registry_pull_secret_selector": True,
                },
            }
        ),
        encoding="utf-8",
    )
    runner = Runner(script={TOFU: Completed(127, "", "tofu: not found")})
    prober = _probe(runner, tmp_path, environment={"SIM2POLICY_INFRA_OUTPUTS": str(snapshot)})
    probe = prober.infrastructure()
    assert probe.ok is True and probe.detail["source"] == "recorded-snapshot"


def test_infrastructure_probe_fails_closed_when_nothing_resolves(tmp_path: Path) -> None:
    runner = Runner(script={TOFU: Completed(127, "", "tofu: not found")})
    probe = _probe(runner, tmp_path).infrastructure()
    assert probe.ok is False and probe.detail["source"] == "unavailable"


# -- credentials --------------------------------------------------------------


def test_credentials_probe_reports_availability_and_discards_the_token(tmp_path: Path) -> None:
    runner = Runner()
    probe = _probe(
        runner,
        tmp_path,
        environment={"NEBIUS_ARTIFACT_SECRET_VERSION": "version-e00artifact"},
    ).credentials()
    assert probe.ok is True
    assert probe.detail["iam_token_available"] is True
    assert probe.detail["unresolved_auth_paths"] == []
    assert probe.detail["job_selectors_present"] == ["NEBIUS_ARTIFACT_SECRET_VERSION"]
    serialized = json.dumps(probe.to_dict())
    assert TOKEN not in serialized and SECRET_SELECTOR not in serialized


def test_credentials_probe_fails_when_the_token_or_a_selector_is_unavailable(tmp_path: Path) -> None:
    no_token = Runner(script={IAM: Completed(1, "", "PermissionDenied")})
    result = _probe(no_token, tmp_path).credentials()
    assert result.ok is False and result.detail["iam_token_available"] is False

    no_selector = Runner(script={TOFU: Completed(0, _tofu_outputs(artifact_secret_selector=""))})
    result = _probe(no_selector, tmp_path).credentials()
    assert result.ok is False
    assert result.detail["unresolved_auth_paths"] == ["artifact_secret_selector"]


# -- preset, quota, disk, timeout --------------------------------------------


def test_preset_quota_probe_accepts_a_declared_cpu_and_gpu_card(tmp_path: Path) -> None:
    prober = _probe(Runner(), tmp_path)
    cpu = prober.preset_and_quota(CPU_HARDWARE)
    assert cpu.ok is True and cpu.detail["quotas"]["compute"]["name"] == "compute.instance.non-gpu.vcpu"
    gpu = prober.preset_and_quota(GPU_HARDWARE)
    assert gpu.ok is True
    # H100 quota is examined only for the GPU card, and vCPU only for the CPU card.
    assert gpu.detail["quotas"]["compute"]["name"] == "compute.instance.gpu.h100"


def test_preset_quota_probe_rejects_an_unavailable_preset(tmp_path: Path) -> None:
    probe = _probe(Runner(), tmp_path).preset_and_quota({**CPU_HARDWARE, "preset": "64vcpu-256gb"})
    assert probe.ok is False and probe.detail["preset_available"] is False


def test_preset_quota_probe_rejects_an_exhausted_published_limit(tmp_path: Path) -> None:
    runner = Runner(
        script={QUOTAS: Completed(0, _allowances(limits={"compute.instance.gpu.h100": 2}))}
    )
    probe = _probe(runner, tmp_path).preset_and_quota(GPU_HARDWARE)
    assert probe.ok is False
    assert probe.detail["quotas"]["compute"]["limit_known"] is True
    assert probe.detail["quotas"]["compute"]["sufficient"] is False


def test_preset_quota_probe_requires_the_allowance_to_exist_in_region(tmp_path: Path) -> None:
    runner = Runner(script={QUOTAS: Completed(0, _allowances(region="us-central1"))})
    probe = _probe(runner, tmp_path).preset_and_quota(GPU_HARDWARE)
    assert probe.ok is False and probe.detail["quotas"]["compute"]["declared"] is False


def test_preset_quota_probe_rejects_wrong_disk_timeout_or_preemptible(tmp_path: Path) -> None:
    prober = _probe(Runner(), tmp_path)
    assert prober.preset_and_quota({**CPU_HARDWARE, "disk_gib": 40}).ok is False
    assert prober.preset_and_quota({**CPU_HARDWARE, "timeout_minutes": 0}).ok is False
    assert prober.preset_and_quota({**CPU_HARDWARE, "preemptible": True}).ok is False


def test_preset_quota_probe_fails_closed_when_the_control_plane_is_unreachable(tmp_path: Path) -> None:
    runner = Runner(script={PLATFORMS: Completed(1, "", "Unavailable")})
    probe = _probe(runner, tmp_path).preset_and_quota(CPU_HARDWARE)
    assert probe.ok is False and "error" in probe.detail


# -- informational GitHub status ---------------------------------------------


def test_github_status_is_informational_and_never_decides(tmp_path: Path) -> None:
    failing = Runner(
        script={
            GH: Completed(
                0,
                json.dumps([{"workflowName": "saas-image", "headBranch": "debug-portal", "status": "completed", "conclusion": "failure"}]),
            )
        }
    )
    probe = _probe(failing, tmp_path).github_status()
    # A red third-party run is recorded but cannot fail a Nebius preflight, just as
    # a green one cannot pass it.
    assert probe.informational is True and probe.ok is True
    assert probe.detail["runs"][0]["conclusion"] == "failure"

    unavailable = _probe(Runner(script={GH: Completed(127, "", "gh: not found")}), tmp_path)
    result = unavailable.github_status()
    assert result.informational is True and result.ok is True and result.detail["available"] is False


def test_collect_returns_every_probe_and_marks_only_github_informational(tmp_path: Path) -> None:
    probes = _probe(Runner(), tmp_path).collect(
        expected_revision=REVISION, hardware=GPU_HARDWARE
    )
    names = [probe.name for probe in probes]
    assert names == ["repository", "infrastructure", "credentials", "preset_quota", "github_actions"]
    assert [probe.name for probe in probes if probe.informational] == ["github_actions"]
    assert all(probe.ok for probe in probes)


def test_probes_never_create_or_modify_a_resource(tmp_path: Path) -> None:
    runner = Runner()
    _probe(runner, tmp_path).collect(expected_revision=REVISION, hardware=GPU_HARDWARE)
    forbidden = {"create", "delete", "update", "start", "stop", "apply", "destroy", "push"}
    for call in runner.calls:
        assert forbidden.isdisjoint(call), call


# -- construction -------------------------------------------------------------


def test_probe_from_environment_requires_a_declared_project_scope() -> None:
    assert probe_from_environment({}) is None
    prober = probe_from_environment({"SIM2POLICY_NEBIUS_PROJECT_ID": PROJECT})
    assert isinstance(prober, InfrastructurePreflight) and prober.project_id == PROJECT


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_a_probe_never_echoes_a_sentinel_credential(tmp_path: Path, stream: str) -> None:
    sentinel = "SENTINEL-" + "z" * 40
    runner = Runner(
        script={
            PLATFORMS: Completed(
                1, sentinel if stream == "stdout" else "", sentinel if stream == "stderr" else ""
            )
        }
    )
    prober = InfrastructurePreflight(
        project_id=PROJECT,
        repo_root=tmp_path,
        runner=runner,
        environment={"NEBIUS_REGISTRY_PASSWORD": sentinel},
    )
    probe = prober.preset_and_quota(CPU_HARDWARE)
    assert probe.ok is False
    assert sentinel not in json.dumps(probe.to_dict())
