"""Nebius provider boundary for the campaign: submit, poll, audit, clean up.

Kept separate from the state machine so every transition is testable without a
network, and so the one place that can spend money is small enough to read.

Two rules shape the whole module:

* **Argument arrays, never shell strings.** Nothing here is interpolated into a
  shell, so a value carrying a quote or a semicolon cannot become a command.
* **Secret selectors, never secret values.** Registry and artifact credentials are
  passed to the provider by reference (MysteryBox version IDs, existing service
  account bindings). This process never reads, prints, or persists the values.

`BlockedProvider` is the default. A partially prepared campaign must not be able
to spend money by accident, so dispatch is opt-in and gated on the recorded
implementation evidence rather than available by default.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from sim2policy.campaign_redaction import sanitize_exception

# Provider states that mean the job still holds the active slot.
ACTIVE_PROVIDER_STATES = frozenset(
    {"PROVISIONING", "STARTING", "RUNNING", "QUEUED", "CREATING", "DELETING"}
)
TERMINAL_SUCCESS_STATES = frozenset({"COMPLETED", "SUCCEEDED"})
TERMINAL_FAILURE_STATES = frozenset({"FAILED", "ERROR", "CANCELLED", "CANCELED"})


class ProviderError(RuntimeError):
    """Raised when a provider call fails or returns something unparseable."""


@dataclass(frozen=True)
class JobStatus:
    remote_id: str
    state: str
    #: `None` when the provider reports a state this runner does not classify.
    #: An unknown state is never guessed into success or failure.
    terminal: bool | None
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def active(self) -> bool:
        return self.state.upper() in ACTIVE_PROVIDER_STATES

    @property
    def succeeded(self) -> bool:
        return self.state.upper() in TERMINAL_SUCCESS_STATES

    @property
    def failed(self) -> bool:
        return self.state.upper() in TERMINAL_FAILURE_STATES

    def to_dict(self) -> dict[str, Any]:
        return {
            "remote_id": self.remote_id,
            "state": self.state,
            "terminal": self.terminal,
            **self.detail,
        }


def classify(state: str) -> bool | None:
    upper = state.upper()
    if upper in TERMINAL_SUCCESS_STATES or upper in TERMINAL_FAILURE_STATES:
        return True
    if upper in ACTIVE_PROVIDER_STATES:
        return False
    return None


class JobProvider(Protocol):
    """What the campaign needs from a compute provider, and nothing more."""

    def submit(self, plan: Mapping[str, Any], *, idempotency_key: str) -> str: ...

    def poll(self, remote_id: str) -> JobStatus: ...

    def find_by_name(self, name: str) -> JobStatus | None: ...

    def audit(self) -> dict[str, Any]: ...


class BlockedProvider:
    """Default adapter: records intent, refuses to spend.

    Used until `implementation-gate` has recorded real Nebius build, test, and
    smoke evidence. Every method raises rather than returning a plausible value,
    so a caller cannot mistake a block for a successful no-op.
    """

    reason = "PROVIDER_DISPATCH_NOT_AUTHORIZED"

    def submit(self, plan: Mapping[str, Any], *, idempotency_key: str) -> str:
        raise ProviderError(self.reason)

    def poll(self, remote_id: str) -> JobStatus:
        raise ProviderError(self.reason)

    def find_by_name(self, name: str) -> JobStatus | None:
        raise ProviderError(self.reason)

    def audit(self) -> dict[str, Any]:
        raise ProviderError(self.reason)


class NebiusCliProvider:
    """Drives Serverless AI jobs through the authenticated `nebius` CLI.

    The CLI is used rather than the SDK because the orchestration VM already
    authenticates it with the VM-managed renewable identity token, so no long-lived
    credential has to exist in this process for it to work.
    """

    def __init__(
        self,
        *,
        project_id: str,
        runner: Any = subprocess.run,
        binary: str = "nebius",
        timeout_seconds: int = 120,
    ) -> None:
        self._project_id = project_id
        self._runner = runner
        self._binary = binary
        self._timeout = timeout_seconds

    def _invoke(self, arguments: Sequence[str]) -> dict[str, Any]:
        command = [self._binary, *arguments, "--format", "json"]
        try:
            completed = self._runner(
                command, capture_output=True, text=True, timeout=self._timeout, check=False
            )
        except Exception as exc:  # subprocess/OS failures carry environment detail
            raise ProviderError(sanitize_exception(exc)) from None
        if completed.returncode != 0:
            # stderr may echo request headers; report only the exit status and a
            # redacted, bounded excerpt.
            raise ProviderError(
                f"provider command failed (exit {completed.returncode}): "
                f"{sanitize_exception(RuntimeError(completed.stderr or ''))}"
            )
        if not (completed.stdout or "").strip():
            return {}
        try:
            value = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ProviderError(sanitize_exception(exc)) from None
        return value if isinstance(value, dict) else {"items": value}

    def submit(self, plan: Mapping[str, Any], *, idempotency_key: str) -> str:
        """Create exactly one AI job from an already-reviewed, normalized plan.

        Every value comes from the campaign matrix by way of the confirmed plan;
        this method adds no defaults and accepts no override.
        """
        hardware = plan["hardware"]
        arguments = [
            "ai", "job", "create",
            "--parent-id", self._project_id,
            "--name", str(plan["run_id"]),
            "--spec.image.name", str(plan["image_reference"]),
            "--spec.resources.platform", str(hardware["platform"]),
            "--spec.resources.preset", str(hardware["preset"]),
            "--spec.disk.type", "NETWORK_SSD",
            "--spec.disk.size-gibibytes", str(hardware["disk_gib"]),
            "--timeout", f"{int(hardware['timeout_minutes'])}m",
            "--idempotency-key", idempotency_key,
        ]
        for value in plan["command"]:
            arguments += ["--spec.command", str(value)]
        for selector in plan.get("secret_selectors", []):
            # Version IDs only. The payload is resolved by the provider at use time.
            arguments += ["--spec.secret-version-id", str(selector)]
        result = self._invoke(arguments)
        remote_id = result.get("metadata", {}).get("id") or result.get("id")
        if not isinstance(remote_id, str) or not remote_id:
            raise ProviderError("provider returned no remote job identity")
        return remote_id

    def poll(self, remote_id: str) -> JobStatus:
        result = self._invoke(["ai", "job", "get", "--id", remote_id])
        state = str(result.get("status", {}).get("state") or result.get("state") or "UNKNOWN")
        return JobStatus(
            remote_id=remote_id,
            state=state,
            terminal=classify(state),
            detail={"effective_steps": result.get("status", {}).get("effective_steps")},
        )

    def find_by_name(self, name: str) -> JobStatus | None:
        """Resolve an already-created job by its deterministic name.

        Recovering a submission whose response was lost depends on the run name
        being deterministic, which is why plans derive it rather than randomize it.
        """
        result = self._invoke(["ai", "job", "list", "--parent-id", self._project_id])
        for item in result.get("items", []):
            if not isinstance(item, dict):
                continue
            metadata = item.get("metadata", {})
            if metadata.get("name") == name:
                state = str(item.get("status", {}).get("state") or "UNKNOWN")
                return JobStatus(
                    remote_id=str(metadata.get("id", "")),
                    state=state,
                    terminal=classify(state),
                )
        return None

    def audit(self) -> dict[str, Any]:
        """Enumerate every chargeable resource class the cleanup checklist names."""
        jobs = self._invoke(["ai", "job", "list", "--parent-id", self._project_id])
        instances = self._invoke(["compute", "instance", "list", "--parent-id", self._project_id])
        disks = self._invoke(["compute", "disk", "list", "--parent-id", self._project_id])
        addresses = self._invoke(["vpc", "allocation", "list", "--parent-id", self._project_id])
        active_jobs = [
            str(item.get("metadata", {}).get("id", ""))
            for item in jobs.get("items", [])
            if isinstance(item, dict)
            and str(item.get("status", {}).get("state", "")).upper() in ACTIVE_PROVIDER_STATES
        ]
        running_instances = [
            str(item.get("metadata", {}).get("id", ""))
            for item in instances.get("items", [])
            if isinstance(item, dict)
            and str(item.get("status", {}).get("state", "")).upper() == "RUNNING"
        ]
        return {
            "active_jobs": active_jobs,
            "running_instances": running_instances,
            "disk_count": len(disks.get("items", [])),
            "public_address_count": len(addresses.get("items", [])),
        }
