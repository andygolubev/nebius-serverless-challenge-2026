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
from typing import Any, Protocol

from . import catalog
from .custom_training import (
    ADAPTER_VERSION,
    PREPARATION_PROFILE,
    REWARD_VERSION,
    TRAINING_PROFILE,
)
from .models import (
    LIFECYCLE,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_FINALIZING,
    STATUS_STARTING,
    STATUS_TRAINING,
    Artifact,
    ArtifactManifest,
    Job,
    PreparationAttempt,
)
from .store import CustomTrainingStore, JobStore

log = logging.getLogger(__name__)
REMOTE_SUBMISSION_ERROR = (
    "The training job could not be submitted. Please try again later."
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class OrchestrationBackend(Protocol):
    name: str
    # Reads report/artifacts.json for a run; None when the backend has no
    # object storage (mock). Lets the API lazily recover manifests published
    # after job completion (e.g. by the finalization pipeline).
    artifact_reader: object | None

    def launch(self, job: Job, store: JobStore) -> None: ...

    def launch_preparation(
        self, attempt: PreparationAttempt, store: CustomTrainingStore
    ) -> None: ...


class MockBackend:
    """Walk a job through the full lifecycle and write placeholder artifacts.

    No Nebius credentials or GPU required. `step_delay` keeps demos fast.
    """

    name = "mock"
    artifact_reader = None

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
        if job.job_kind == "custom-robot":
            artifacts = [
                Artifact(
                    id="video_final",
                    name="Final rollout",
                    kind="video",
                    content_type="video/mp4",
                    key=f"sim2policy/{job.id}/videos/final.mp4",
                ),
                Artifact(
                    id="final_policy",
                    name="Final checkpoint",
                    content_type="application/zip",
                    key=f"sim2policy/{job.id}/checkpoints/final.zip",
                ),
                Artifact(
                    id="resolved_config",
                    name="Resolved configuration",
                    content_type="application/json",
                    key=f"sim2policy/{job.id}/report/resolved-config.json",
                ),
                Artifact(
                    id="policy_bundle",
                    name="Simulator policy bundle",
                    content_type="application/zip",
                    key=f"sim2policy/{job.id}/bundle/policy-bundle.zip",
                ),
            ]
            metrics = {
                "aggregate": {
                    "episodes": 20,
                    "mean_reward": 31.8,
                    "success_rate": 0.75,
                    "fall_rate": 0.1,
                    "task_threshold_achieved": False,
                },
                "simulator_only": True,
                "mock": True,
            }
            store.set_artifacts(
                ArtifactManifest(
                    job_id=job.id,
                    status=STATUS_COMPLETED,
                    metrics=metrics,
                    media=[artifacts[0].key],
                    artifacts=artifacts,
                )
            )
        elif job.gallery_example_id is not None:
            artifacts = [
                Artifact(
                    id="video_final",
                    name="Final rollout",
                    kind="video",
                    content_type="video/mp4",
                    key=f"sim2policy/{job.id}/videos/final.mp4",
                ),
                Artifact(
                    id="final_policy",
                    name="Final checkpoint",
                    content_type="application/zip",
                    key=f"sim2policy/{job.id}/checkpoints/final.zip",
                ),
                Artifact(
                    id="policy_bundle",
                    name="Policy bundle",
                    content_type="application/zip",
                    key=f"sim2policy/{job.id}/bundle/policy-bundle.zip",
                ),
            ]
            store.set_artifacts(
                ArtifactManifest(
                    job_id=job.id,
                    status=STATUS_COMPLETED,
                    metrics={
                        "aggregate": {"episodes": 20, "mean_reward": 1234.5},
                        "success": {
                            "met": True,
                            "criterion": job.resolved_config.get("success", {}).get(
                                "criterion", "accepted example threshold"
                            ),
                        },
                        "benchmark": {
                            "estimated_cost": 0.12,
                            "currency": "USD",
                        },
                        "runtime_seconds": 613.2,
                        "mock": True,
                    },
                    media=[artifacts[0].key],
                    artifacts=artifacts,
                )
            )
        else:
            store.set_artifacts(
                ArtifactManifest(
                    job_id=job.id,
                    status=STATUS_COMPLETED,
                    metrics={"mean_reward": 1234.5, "steps": 100000, "mock": True},
                    media=[f"runs/{job.id}/videos/rollout.mp4"],
                )
            )

    def launch_preparation(
        self, attempt: PreparationAttempt, store: CustomTrainingStore
    ) -> None:
        thread = threading.Thread(
            target=self._prepare, args=(attempt, store), daemon=True
        )
        thread.start()

    def _prepare(self, attempt: PreparationAttempt, store: CustomTrainingStore) -> None:
        for phase in (
            "manifest",
            "compile",
            "rollouts",
            "render",
            "environment-checker",
            "ppo-smoke",
            "finalization",
        ):
            time.sleep(self.step_delay)
            attempt = attempt.model_copy(
                update={
                    "state": "preparing",
                    "phase": phase,
                    "updated_at": _now(),
                }
            )
            store.put_preparation(attempt)
        store.put_preparation(
            attempt.model_copy(
                update={
                    "state": "accepted",
                    "phase": "accepted",
                    "updated_at": _now(),
                    "report_sha256": "0" * 64,
                    "report_ready": True,
                    "can_retry": False,
                }
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
    if state in {
        "QUEUED",
        "QUEUING",
        "PENDING",
        "PROVISIONING",
        "STARTING",
        "CREATING",
    }:
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

    def __init__(
        self,
        settings: Any,
        client: Any,
        artifact_reader: Any,
        poll_interval: float = 10.0,
        finalize_attempts: int = 360,
        *,
        custom_settings: Any | None = None,
        custom_storage: Any | None = None,
    ) -> None:
        self._settings = settings
        self._client = client
        self._artifacts = artifact_reader
        self.artifact_reader = artifact_reader
        self.poll_interval = poll_interval
        self.finalize_attempts = finalize_attempts
        self.custom_settings = custom_settings
        self.custom_storage = custom_storage
        self._active: set[str] = set()
        self._active_lock = threading.Lock()

    def launch(self, job: Job, store: JobStore) -> None:
        self._start(job, self._run, job, store)

    def _start(self, job: Job, target, *args) -> bool:
        with self._active_lock:
            if job.id in self._active:
                return False
            self._active.add(job.id)

        def guarded() -> None:
            try:
                target(*args)
            finally:
                with self._active_lock:
                    self._active.discard(job.id)

        threading.Thread(target=guarded, daemon=True).start()
        return True

    def resume(self, store: JobStore) -> None:
        for job in store.list_active():
            if not job.nebius_job_id:
                self._fail(
                    job,
                    store,
                    "job was interrupted before remote creation",
                    phase="submission",
                )
                continue
            self._start(
                job,
                self._poll,
                job,
                store,
                time.monotonic() + POLL_TIMEOUT_MARGIN_SECONDS,
            )

    def resume_preparations(self, store: CustomTrainingStore) -> None:
        for attempt in store.list_active_preparations():
            if not attempt.nebius_job_id:
                self._fail_preparation(
                    attempt, store, "submission-interrupted", "submission"
                )
                continue
            self._start_preparation(
                attempt,
                self._poll_preparation,
                attempt,
                store,
                time.monotonic() + PREPARATION_PROFILE.timeout_seconds,
            )

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
        if job.job_kind == "custom-robot":
            return self._build_custom_training_submission(job)
        spec = catalog.job_spec(job.environment, job.algorithm)
        if spec is None:
            raise ValueError(
                f"{job.environment}/{job.algorithm} is not available on the nebius backend"
            )
        if job.gallery_example_id is not None:
            example = catalog.GALLERY_EXAMPLES.get(job.gallery_example_id)
            if example is None:
                raise ValueError("gallery example identity is unknown")
            expected = catalog.resolve_gallery(
                job.gallery_example_id,
                {"seed": job.resolved_config.get("params", {}).get("seed", 0)},
                profile_id=str(job.resolved_config.get("profile", "")),
            )
            for field in ("environment", "algorithm", "profile", "acceptance_revision"):
                if job.resolved_config.get(field) != expected.get(field):
                    raise ValueError(
                        "gallery resolved configuration does not match the catalog"
                    )
            if (
                job.environment != example.environment
                or job.algorithm != example.algorithm
            ):
                raise ValueError("gallery job identity does not match its example")
        params = job.resolved_config.get("params", {})
        if not isinstance(params, dict):
            raise ValueError("resolved job parameters are invalid")
        steps = params.get("total_timesteps")
        if isinstance(steps, int) and steps > spec.max_total_timesteps:
            raise ValueError(
                f"total_timesteps {steps} exceeds the {spec.max_total_timesteps} cap"
            )
        s = self._settings
        args = ["-m", spec.module, "--config", spec.config, "--run-id", job.id]
        if job.gallery_example_id is not None:
            args += ["--gallery-example-id", job.gallery_example_id]
        for name in sorted(spec.param_paths):
            if name in params:
                args += ["--set", f"{spec.param_paths[name]}={params[name]}"]
        args += [
            "--set",
            "storage.mode=s3",
            "--set",
            f"storage.bucket={s.s3_bucket}",
            "--set",
            f"storage.endpoint_url={s.s3_endpoint_url}",
            "--set",
            f"storage.region={s.s3_region}",
            "--set",
            f"reporting.hourly_rate={spec.hourly_rate}",
            "--set",
            "reporting.currency=USD",
            "--set",
            f'reporting.rate_date="{spec.rate_date}"',
        ]
        if spec.image_key == "mjx":
            if spec.platform not in {"gpu-h100-sxm", "gpu-l40s-a"}:
                raise ValueError(
                    "MJX catalog job uses an unsupported accelerator platform"
                )
            image = s.mjx_job_image
        elif spec.image_key == "sb3":
            if spec.platform != "cpu-d3" or spec.preset != "8vcpu-32gb":
                raise ValueError("SB3 catalog job uses an unsupported CPU profile")
            if s.job_image is None:
                raise ValueError("immutable SB3 catalog image is not configured")
            image = s.job_image
        else:
            raise ValueError("catalog job has an unsupported runtime image family")
        return JobSubmission(
            name=f"sim2policy-{job.id}",
            image=image,
            command="python",
            args=args,
            platform=spec.platform,
            preset=spec.preset,
            timeout_seconds=parse_duration_seconds(spec.timeout),
            subnet_id=s.subnet_id,
            parent_id=s.project_id,
            registry_secret=s.registry_secret,
            disk_gib=spec.disk_gib,
            env={
                "AWS_ACCESS_KEY_ID": s.aws_access_key_id,
                "SIM2POLICY_RUNTIME_IMAGE": image,
            },
            # Secret access key is resolved by Nebius from MysteryBox inside the
            # job; the plaintext value never enters the submission.
            env_secrets={"AWS_SECRET_ACCESS_KEY": s.s3_secret_selector},
        )

    def _custom_environment(self) -> dict[str, str]:
        settings = self._settings
        return {
            "AWS_ACCESS_KEY_ID": settings.aws_access_key_id,
            "SIM2POLICY_S3_BUCKET": settings.s3_bucket,
            "AWS_ENDPOINT_URL_S3": settings.s3_endpoint_url,
            "AWS_DEFAULT_REGION": settings.s3_region,
        }

    def _build_custom_training_submission(self, job: Job):
        from .nebius_client import JobSubmission

        if self.custom_settings is None or not self.custom_settings.enabled:
            raise ValueError("custom robot training is disabled")
        if not RUN_ID_RE.fullmatch(job.id):
            raise ValueError("custom run identity is invalid")
        resolved = job.resolved_config
        expected = {
            "job_kind": "custom-robot",
            "backend": "sb3",
            "profile": "custom-ppo-quick",
        }
        if any(resolved.get(key) != value for key, value in expected.items()):
            raise ValueError("custom training resolved contract is invalid")
        training = resolved.get("training", {})
        if training.get("version") != TRAINING_PROFILE.version:
            raise ValueError("custom training profile version is invalid")
        if (
            resolved.get("runtime", {}).get("image_digest")
            != self.custom_settings.runtime_image
        ):
            raise ValueError("custom training image provenance is invalid")
        return JobSubmission(
            name=f"sim2policy-custom-{job.id}",
            image=self.custom_settings.runtime_image,
            command="python",
            args=[
                "-m",
                "sim2policy.custom_robot_job",
                "train",
                "--identity",
                job.id,
            ],
            platform=TRAINING_PROFILE.platform,
            preset=TRAINING_PROFILE.preset,
            disk_gib=TRAINING_PROFILE.disk_gib,
            timeout_seconds=TRAINING_PROFILE.timeout_seconds,
            subnet_id=self._settings.subnet_id,
            parent_id=self._settings.project_id,
            registry_secret=self._settings.registry_secret,
            env=self._custom_environment(),
            env_secrets={"AWS_SECRET_ACCESS_KEY": self._settings.s3_secret_selector},
        )

    def build_preparation_submission(self, attempt: PreparationAttempt):
        from .nebius_client import JobSubmission

        if self.custom_settings is None or not self.custom_settings.enabled:
            raise ValueError("custom robot training is disabled")
        if (
            attempt.runtime_image_digest != self.custom_settings.runtime_image
            or attempt.adapter_version != ADAPTER_VERSION
            or attempt.reward_version != REWARD_VERSION
            or attempt.profile_version != PREPARATION_PROFILE.version
        ):
            raise ValueError("custom preparation provenance is invalid")
        return JobSubmission(
            name=f"sim2policy-prepare-{attempt.id}",
            image=self.custom_settings.runtime_image,
            command="python",
            args=[
                "-m",
                "sim2policy.custom_robot_job",
                "prepare",
                "--identity",
                attempt.id,
            ],
            platform=PREPARATION_PROFILE.platform,
            preset=PREPARATION_PROFILE.preset,
            disk_gib=PREPARATION_PROFILE.disk_gib,
            timeout_seconds=PREPARATION_PROFILE.timeout_seconds,
            subnet_id=self._settings.subnet_id,
            parent_id=self._settings.project_id,
            registry_secret=self._settings.registry_secret,
            env=self._custom_environment(),
            env_secrets={"AWS_SECRET_ACCESS_KEY": self._settings.s3_secret_selector},
        )

    def launch_preparation(
        self, attempt: PreparationAttempt, store: CustomTrainingStore
    ) -> None:
        self._start_preparation(attempt, self._run_preparation, attempt, store)

    def _start_preparation(
        self, attempt: PreparationAttempt, target: Any, *args: Any
    ) -> bool:
        key = f"preparation:{attempt.id}"
        with self._active_lock:
            if key in self._active:
                return False
            self._active.add(key)

        def guarded() -> None:
            try:
                target(*args)
            finally:
                with self._active_lock:
                    self._active.discard(key)

        threading.Thread(target=guarded, daemon=True).start()
        return True

    def _fail_preparation(
        self,
        attempt: PreparationAttempt,
        store: CustomTrainingStore,
        reason: str,
        phase: str,
    ) -> None:
        store.put_preparation(
            attempt.model_copy(
                update={
                    "state": "failed",
                    "phase": phase,
                    "failure_phase": phase,
                    "failure_reason": reason[:200],
                    "can_retry": True,
                    "updated_at": _now(),
                }
            )
        )

    def _run_preparation(
        self, attempt: PreparationAttempt, store: CustomTrainingStore
    ) -> None:
        try:
            submission = self.build_preparation_submission(attempt)
            remote_id = self._client.create_job(submission)
        except ValueError as exc:
            self._fail_preparation(attempt, store, str(exc), "submission")
            return
        except Exception as exc:
            log.warning(
                "custom preparation submission failed for %s (%s)",
                attempt.id,
                type(exc).__name__,
            )
            self._fail_preparation(
                attempt, store, "remote-submission-failed", "submission"
            )
            return
        attempt = attempt.model_copy(
            update={
                "state": "preparing",
                "phase": "starting",
                "nebius_job_id": remote_id,
                "updated_at": _now(),
            }
        )
        store.put_preparation(attempt)
        self._poll_preparation(
            attempt,
            store,
            time.monotonic() + submission.timeout_seconds + POLL_TIMEOUT_MARGIN_SECONDS,
        )

    def _poll_preparation(
        self,
        attempt: PreparationAttempt,
        store: CustomTrainingStore,
        deadline: float,
    ) -> None:
        while time.monotonic() <= deadline:
            time.sleep(self.poll_interval)
            try:
                state = map_nebius_state(
                    self._client.get_job_state(attempt.nebius_job_id or "")
                )
            except Exception:
                continue
            if state == STATUS_FAILED:
                self._fail_preparation(attempt, store, "remote-job-failed", "execution")
                return
            if state == STATUS_COMPLETED:
                self._finalize_preparation(attempt, store)
                return
            if state in {STATUS_STARTING, STATUS_TRAINING}:
                attempt = attempt.model_copy(
                    update={
                        "state": "preparing",
                        "phase": "execution",
                        "updated_at": _now(),
                    }
                )
                store.put_preparation(attempt)
        self._fail_preparation(attempt, store, "preparation-timeout", "execution")

    def _finalize_preparation(
        self, attempt: PreparationAttempt, store: CustomTrainingStore
    ) -> None:
        if self.custom_storage is None:
            self._fail_preparation(
                attempt, store, "report-storage-unavailable", "finalization"
            )
            return
        for _ in range(self.custom_settings.preparation_finalize_attempts):
            try:
                report = self.custom_storage.read_preparation_report(attempt.id)
            except Exception:
                report = None
            if report is not None:
                if report.get("fingerprint") != attempt.fingerprint:
                    self._fail_preparation(
                        attempt, store, "report-fingerprint-mismatch", "finalization"
                    )
                    return
                accepted = report.get("status") == "accepted"
                store.put_preparation(
                    attempt.model_copy(
                        update={
                            "state": "accepted" if accepted else "failed",
                            "phase": "accepted"
                            if accepted
                            else str(report.get("failure_phase") or "preparation"),
                            "failure_phase": report.get("failure_phase"),
                            "failure_reason": report.get("failure_reason"),
                            "report_sha256": report.get("report_sha256"),
                            "report_ready": True,
                            "can_retry": not accepted,
                            "updated_at": _now(),
                        }
                    )
                )
                return
            time.sleep(self.poll_interval)
        self._fail_preparation(
            attempt, store, "preparation-report-not-ready", "finalization"
        )

    # -- lifecycle --

    def _fail(
        self, job: Job, store: JobStore, error: str, phase: str = "orchestration"
    ) -> None:
        store.put(
            job.model_copy(
                update={
                    "status": STATUS_FAILED,
                    "phase": phase,
                    "failure_phase": phase,
                    "error": error,
                    "updated_at": _now(),
                }
            )
        )

    def _run(self, job: Job, store: JobStore) -> None:
        try:
            submission = self.build_submission(job)
        except ValueError as e:
            self._fail(job, store, str(e), phase="submission")
            return
        try:
            nebius_job_id = self._client.create_job(submission)
        except Exception as e:
            # Provider exceptions can include request/trace IDs and transport
            # details. Keep them in operator logs, but expose only a stable,
            # retry-safe category to the tenant UI.
            log.warning(
                "nebius job submission failed for job %s (%s)",
                job.id,
                type(e).__name__,
            )
            self._fail(
                job,
                store,
                REMOTE_SUBMISSION_ERROR,
                phase="submission",
            )
            return
        # Record the aijob-* ID before reporting any further status.
        job = job.model_copy(
            update={
                "nebius_job_id": nebius_job_id,
                "status": STATUS_STARTING,
                "updated_at": _now(),
            }
        )
        store.put(job)
        self._poll(
            job,
            store,
            deadline=time.monotonic()
            + submission.timeout_seconds
            + POLL_TIMEOUT_MARGIN_SECONDS,
        )

    def _poll(self, job: Job, store: JobStore, deadline: float) -> None:
        while True:
            if time.monotonic() > deadline:
                self._fail(
                    job,
                    store,
                    "job exceeded its timeout and was marked failed",
                    phase=job.phase or "training",
                )
                return
            time.sleep(self.poll_interval)
            try:
                raw_state = self._client.get_job_state(job.nebius_job_id or "")
            except Exception as e:
                log.warning(
                    "poll failed for job %s (%s); retrying", job.id, type(e).__name__
                )
                continue
            status = map_nebius_state(raw_state)
            if status is None or status == job.status:
                continue
            if status == STATUS_COMPLETED:
                self._complete(job, store, deadline)
                return
            job = job.model_copy(update={"status": status, "updated_at": _now()})
            store.put(job)
            if status == STATUS_FAILED:
                self._fail(job, store, "remote job failed", phase="training")
                return

    def _complete(self, job: Job, store: JobStore, deadline: float) -> None:
        job = job.model_copy(
            update={
                "status": STATUS_FINALIZING,
                "phase": "finalization",
                "artifacts_status": "pending",
                "updated_at": _now(),
            }
        )
        store.put(job)
        for _ in range(self.finalize_attempts):
            if time.monotonic() > deadline:
                break
            try:
                manifest = self._artifacts.read_manifest(job.id, job.id)
            except ValueError as e:
                self._fail(job, store, sanitize_error(e), phase="artifact_validation")
                return
            except Exception:
                log.warning(
                    "artifact read failed for job %s; retrying", job.id, exc_info=True
                )
                manifest = None
            if manifest is not None:
                store.set_artifacts(manifest)
                store.put(
                    job.model_copy(
                        update={
                            "status": STATUS_COMPLETED,
                            "phase": STATUS_COMPLETED,
                            "artifacts_status": "ready",
                            "updated_at": _now(),
                        }
                    )
                )
                return
            time.sleep(self.poll_interval)
        self._fail(
            job,
            store,
            "artifacts did not finalize before timeout",
            phase="finalization",
        )


def build_backend(name: str) -> OrchestrationBackend:
    if name == "mock":
        return MockBackend()
    if name == "nebius":
        # Import here so mock-mode deployments don't need nebius/boto3 configured.
        from .artifacts import RUN_PREFIX, S3ArtifactReader, build_s3_client
        from .custom_storage import CustomRobotStorage
        from .nebius_client import SdkJobsClient
        from .settings import CustomTrainingSettings, NebiusSettings

        settings = NebiusSettings.from_env()  # fails fast on missing configuration
        custom_settings = CustomTrainingSettings.from_env(
            orchestration_backend="nebius"
        )
        s3_client = build_s3_client(settings)
        reader = S3ArtifactReader(s3_client, settings.s3_bucket, RUN_PREFIX)
        return NebiusBackend(
            settings,
            SdkJobsClient(),
            reader,
            custom_settings=custom_settings,
            custom_storage=CustomRobotStorage(s3_client, settings.s3_bucket),
        )
    raise ValueError(f"unknown orchestration backend: {name!r}")
