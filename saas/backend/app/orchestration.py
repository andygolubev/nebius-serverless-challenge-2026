"""Pluggable job orchestration: `mock` (local lifecycle simulation, the default)
and `nebius` (real Serverless AI jobs via the official SDK). The tenant-facing
API is identical for both.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from datetime import datetime, timezone
from typing import Protocol

from . import catalog
from .models import (
    LIFECYCLE,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_STARTING,
    STATUS_TRAINING,
    ArtifactManifest,
    Job,
)
from .store import JobStore

log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class OrchestrationBackend(Protocol):
    name: str

    def launch(self, job: Job, store: JobStore) -> None: ...


class MockBackend:
    """Walk a job through the full lifecycle and write placeholder artifacts.

    No Nebius credentials or GPU required. `step_delay` keeps demos fast.
    """

    name = "mock"

    def __init__(self, step_delay: float = 0.5) -> None:
        self.step_delay = step_delay

    def launch(self, job: Job, store: JobStore) -> None:
        thread = threading.Thread(target=self._run, args=(job, store), daemon=True)
        thread.start()

    def _run(self, job: Job, store: JobStore) -> None:
        for status in LIFECYCLE:
            time.sleep(self.step_delay)
            job = job.model_copy(update={"status": status, "updated_at": _now()})
            store.put(job)
        store.set_artifacts(
            ArtifactManifest(
                job_id=job.id,
                status=STATUS_COMPLETED,
                metrics={"mean_reward": 1234.5, "steps": 100000, "mock": True},
                media=[f"runs/{job.id}/videos/rollout.mp4"],
            )
        )


# Same safe pattern jobs/submit.sh enforces; job IDs are server-generated hex,
# but we re-validate at the trust boundary anyway.
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

_DURATION_RE = re.compile(r"(\d+)([hms])")
# Extra time we allow a job beyond its Nebius timeout before declaring it stuck.
POLL_TIMEOUT_MARGIN_SECONDS = 30 * 60


def parse_duration_seconds(duration: str) -> int:
    """Parse a Nebius duration such as `1h`, `2h30m`, or `45m` into seconds."""
    parts = _DURATION_RE.findall(duration)
    if not parts or "".join(f"{n}{u}" for n, u in parts) != duration:
        raise ValueError(f"invalid Nebius duration: {duration!r}")
    return sum(int(n) * {"h": 3600, "m": 60, "s": 1}[u] for n, u in parts)


def map_nebius_state(raw: str) -> str | None:
    """Map a raw Nebius job state name onto the tenant lifecycle.

    Returns None for terminal-success (caller finishes via S3 artifacts) — kept in
    one place so pysdk enum renames only ever touch this function.
    """
    state = raw.rsplit("_", 1)[-1].upper()  # tolerate JOB_STATE_RUNNING style
    if state in {"QUEUED", "QUEUING", "PENDING", "PROVISIONING", "STARTING", "CREATING"}:
        return STATUS_STARTING
    if state in {"RUNNING", "ACTIVE"}:
        return STATUS_TRAINING
    if state in {"SUCCEEDED", "SUCCESS", "COMPLETED", "FINISHED", "DONE"}:
        return STATUS_COMPLETED
    if state in {"FAILED", "ERROR", "CANCELLED", "CANCELED", "TIMEOUT", "EXPIRED"}:
        return STATUS_FAILED
    return None  # unknown/transitional: keep the current status


def sanitize_error(exc: Exception, secrets: tuple[str, ...] = ()) -> str:
    """One-line failure summary safe to show a tenant: no secrets, no stack trace."""
    message = str(exc).splitlines()[0] if str(exc) else ""
    for secret in secrets:
        if secret:
            message = message.replace(secret, "***")
    summary = f"{type(exc).__name__}: {message}" if message else type(exc).__name__
    return summary[:200]


class NebiusBackend:
    """Submit tenant jobs as Nebius Serverless AI jobs and poll them to completion.

    One daemon thread per job (matching MockBackend's model): submit via the SDK,
    record the `aijob-*` ID, poll `JobService.get()`, and on success read the run's
    artifacts from S3.
    """

    name = "nebius"

    def __init__(self, settings, client, artifact_reader, poll_interval: float = 10.0) -> None:
        self._settings = settings
        self._client = client
        self._artifacts = artifact_reader
        self.poll_interval = poll_interval

    def launch(self, job: Job, store: JobStore) -> None:
        thread = threading.Thread(target=self._run, args=(job, store), daemon=True)
        thread.start()

    # -- submission --

    def build_submission(self, job: Job):
        """Build the job spec from the server-side catalog only.

        Tenant input never reaches this directly: `resolved_config` is already
        catalog-validated, and only params named in the spec's `param_paths`
        become `--set` overrides.
        """
        from .nebius_client import JobSubmission

        if not RUN_ID_RE.match(job.id):
            raise ValueError(f"run id contains unsafe characters: {job.id!r}")
        spec = catalog.job_spec(job.environment, job.algorithm)
        if spec is None:
            raise ValueError(
                f"{job.environment}/{job.algorithm} is not available on the nebius backend"
            )
        params = job.resolved_config.get("params", {})
        steps = params.get("total_timesteps")
        if isinstance(steps, int) and steps > spec.max_total_timesteps:
            raise ValueError(
                f"total_timesteps {steps} exceeds the {spec.max_total_timesteps} cap"
            )
        s = self._settings
        args = ["-m", spec.module, "--config", spec.config, "--run-id", job.id]
        for name in sorted(spec.param_paths):
            if name in params:
                args += ["--set", f"{spec.param_paths[name]}={params[name]}"]
        args += [
            "--set", "storage.mode=s3",
            "--set", f"storage.bucket={s.s3_bucket}",
            "--set", f"storage.endpoint_url={s.s3_endpoint_url}",
            "--set", f"storage.region={s.s3_region}",
        ]
        return JobSubmission(
            name=f"sim2policy-{job.id}",
            image=s.job_image,
            command="python",
            args=args,
            platform=spec.platform,
            preset=spec.preset,
            timeout_seconds=parse_duration_seconds(spec.timeout),
            subnet_id=s.subnet_id,
            parent_id=s.project_id,
            registry_secret=s.registry_secret,
            env={"AWS_ACCESS_KEY_ID": s.aws_access_key_id},
            # Secret access key is resolved by Nebius from MysteryBox inside the
            # job; the plaintext value never enters the submission.
            env_secrets={"AWS_SECRET_ACCESS_KEY": s.s3_secret_selector},
        )

    # -- lifecycle --

    def _fail(self, job: Job, store: JobStore, error: str) -> None:
        store.put(job.model_copy(update={"status": STATUS_FAILED, "error": error, "updated_at": _now()}))

    def _run(self, job: Job, store: JobStore) -> None:
        try:
            submission = self.build_submission(job)
        except ValueError as e:
            self._fail(job, store, str(e))
            return
        try:
            nebius_job_id = self._client.create_job(submission)
        except Exception as e:
            log.exception("nebius job submission failed for job %s", job.id)
            self._fail(job, store, sanitize_error(e, (self._settings.aws_secret_access_key,)))
            return
        # Record the aijob-* ID before reporting any further status.
        job = job.model_copy(update={"nebius_job_id": nebius_job_id, "status": STATUS_STARTING, "updated_at": _now()})
        store.put(job)
        self._poll(job, store, deadline=time.monotonic() + submission.timeout_seconds + POLL_TIMEOUT_MARGIN_SECONDS)

    def _poll(self, job: Job, store: JobStore, deadline: float) -> None:
        while True:
            if time.monotonic() > deadline:
                self._fail(job, store, "job exceeded its timeout and was marked failed")
                return
            time.sleep(self.poll_interval)
            try:
                raw_state = self._client.get_job_state(job.nebius_job_id or "")
            except Exception as e:
                log.warning("poll failed for job %s (%s); retrying", job.id, type(e).__name__)
                continue
            status = map_nebius_state(raw_state)
            if status is None or status == job.status:
                continue
            if status == STATUS_COMPLETED:
                self._complete(job, store)
                return
            job = job.model_copy(update={"status": status, "updated_at": _now()})
            store.put(job)
            if status == STATUS_FAILED:
                return

    def _complete(self, job: Job, store: JobStore) -> None:
        try:
            manifest = self._artifacts.read_manifest(job.id, job.id)
        except Exception as e:
            log.exception("artifact read failed for job %s", job.id)
            manifest = None
        if manifest is not None:
            store.set_artifacts(manifest)
        # Artifacts may lag the job state briefly; /jobs/{id}/artifacts keeps
        # returning 409 until the manifest exists in S3.
        store.put(job.model_copy(update={"status": STATUS_COMPLETED, "updated_at": _now()}))


def build_backend(name: str) -> OrchestrationBackend:
    if name == "mock":
        return MockBackend()
    if name == "nebius":
        # Import here so mock-mode deployments don't need nebius/boto3 configured.
        from .artifacts import RUN_PREFIX, S3ArtifactReader, build_s3_client
        from .nebius_client import SdkJobsClient
        from .settings import NebiusSettings

        settings = NebiusSettings.from_env()  # fails fast on missing configuration
        reader = S3ArtifactReader(build_s3_client(settings), settings.s3_bucket, RUN_PREFIX)
        return NebiusBackend(settings, SdkJobsClient(), reader)
    raise ValueError(f"unknown orchestration backend: {name!r}")
