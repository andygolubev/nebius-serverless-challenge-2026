from __future__ import annotations

import functools
import hashlib
import json
import shutil
import time
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any

import boto3  # type: ignore[import-untyped]

from sim2policy.checkpoint import (
    CheckpointError,
    load_checkpoint_metadata,
    metadata_path,
    sha256_file,
    validate_checkpoint,
)
from sim2policy.config import RunConfig, StorageConfig, validate_prefix, validate_run_id


class StorageError(RuntimeError):
    """Raised when configured durable storage cannot satisfy an operation."""


class ArtifactStore:
    def __init__(
        self,
        config: StorageConfig,
        run_id: str,
        *,
        client: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self.run_id = validate_run_id(run_id)
        self.prefix = validate_prefix(config.prefix)
        self.sleep = sleep
        self.degraded: list[str] = []
        self.client: Any = client
        if config.mode == "s3" and client is None:
            self.client = boto3.client(
                "s3",
                endpoint_url=config.endpoint_url,
                region_name=config.region,
            )

    @property
    def enabled(self) -> bool:
        return self.config.mode == "s3"

    def key_for(self, relative: str | PurePosixPath) -> str:
        path = PurePosixPath(relative)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise StorageError(f"unsafe artifact path: {relative}")
        return str(PurePosixPath(self.prefix) / self.run_id / path)

    def _attempt(self, description: str, operation: Callable[[], Any]) -> Any:
        attempts = self.config.retries + 1
        for attempt in range(attempts):
            try:
                return operation()
            except Exception as exc:  # boto providers expose several exception families
                if attempt + 1 == attempts:
                    message = (
                        f"{description} failed after {attempts} attempt(s): {type(exc).__name__}"
                    )
                    self.degraded.append(message)
                    raise StorageError(message) from exc
                self.sleep(min(2**attempt, 8))
        raise AssertionError("unreachable")

    def upload_file(self, local: Path, relative: str | PurePosixPath) -> str:
        if not self.enabled:
            return str(local)
        if not local.is_file():
            raise StorageError(f"artifact is not a file: {local}")
        key = self.key_for(relative)
        self._attempt(
            f"upload {relative}",
            lambda: self.client.upload_file(
                str(local),
                self.config.bucket,
                key,
                ExtraArgs={"Metadata": {"sha256": sha256_file(local)}},
            ),
        )
        return key

    def sync_tree(self, run_root: Path, *, required: bool = False) -> list[str]:
        if not self.enabled:
            return []
        uploaded: list[str] = []
        failures: list[str] = []
        for local in sorted(path for path in run_root.rglob("*") if path.is_file()):
            relative = local.relative_to(run_root).as_posix()
            if relative in {
                "checkpoints/latest.json",
                "report/g1-transition.json",
                "report/g1-finalization-input.json",
            }:
                continue
            try:
                uploaded.append(self.upload_file(local, relative))
            except StorageError as exc:
                failures.append(str(exc))
        if failures and required:
            raise StorageError("required final artifacts remain local: " + "; ".join(failures))
        return uploaded

    def sync_runtime_artifacts(self, run_root: Path) -> list[str]:
        """Upload mutable non-checkpoint artifacts during a running job.

        Checkpoints use :meth:`publish_checkpoint` so their latest manifest is only advanced after
        a complete upload. This companion sync makes TensorBoard events and run/report metadata
        observable at the same checkpoint cadence without treating mutable files as checkpoints.
        """
        if not self.enabled:
            return []
        uploaded: list[str] = []
        for local in sorted(path for path in run_root.rglob("*") if path.is_file()):
            relative = local.relative_to(run_root)
            if relative.parts[0] == "checkpoints":
                continue
            uploaded.append(self.upload_file(local, relative.as_posix()))
        return uploaded

    def download_tree(self, run_root: Path, prefixes: tuple[str, ...]) -> list[Path]:
        """Download selected run subtrees while preserving the canonical relative layout."""
        if not self.enabled:
            return []
        run_prefix = PurePosixPath(self.prefix) / self.run_id
        downloaded: list[Path] = []
        for relative_prefix in prefixes:
            safe_prefix = PurePosixPath(relative_prefix)
            if safe_prefix.is_absolute() or any(
                part in {"", ".", ".."} for part in safe_prefix.parts
            ):
                raise StorageError(f"unsafe artifact prefix: {relative_prefix}")
            continuation: str | None = None
            while True:
                request: dict[str, Any] = {
                    "Bucket": self.config.bucket,
                    "Prefix": f"{run_prefix / safe_prefix}",
                }
                if continuation is not None:
                    request["ContinuationToken"] = continuation
                response = self._attempt(
                    f"list {relative_prefix}",
                    functools.partial(self.client.list_objects_v2, **request),
                )
                for item in response.get("Contents", []):
                    key = PurePosixPath(str(item["Key"]))
                    try:
                        relative = key.relative_to(run_prefix)
                    except ValueError as exc:
                        raise StorageError(f"remote key escaped run prefix: {key}") from exc
                    local = run_root.joinpath(*relative.parts)
                    local.parent.mkdir(parents=True, exist_ok=True)
                    self._attempt(
                        f"download {relative}",
                        functools.partial(
                            self.client.download_file,
                            self.config.bucket,
                            str(key),
                            str(local),
                        ),
                    )
                    downloaded.append(local)
                continuation = response.get("NextContinuationToken")
                if not response.get("IsTruncated") or continuation is None:
                    break
        return downloaded

    def publish_checkpoint(self, checkpoint: Path, run_root: Path) -> dict[str, Any]:
        metadata = load_checkpoint_metadata(checkpoint)
        relative_checkpoint = checkpoint.relative_to(run_root).as_posix()
        relative_metadata = metadata_path(checkpoint).relative_to(run_root).as_posix()
        checkpoint_key = self.upload_file(checkpoint, relative_checkpoint)
        metadata_key = self.upload_file(metadata_path(checkpoint), relative_metadata)
        manifest = {
            "schema_version": 1,
            "backend": metadata.backend,
            "environment": metadata.environment,
            "step": metadata.step,
            "sha256": metadata.sha256,
            "checkpoint_key": checkpoint_key,
            "metadata_key": metadata_key,
        }
        if self.enabled:
            body = json.dumps(manifest, sort_keys=True).encode()
            self._attempt(
                "publish latest checkpoint manifest",
                lambda: self.client.put_object(
                    Bucket=self.config.bucket,
                    Key=self.key_for("checkpoints/latest.json"),
                    Body=body,
                    ContentType="application/json",
                ),
            )
        return manifest

    def put_json(self, relative: str | PurePosixPath, payload: dict[str, Any]) -> str:
        """Write a small JSON object directly to durable storage.

        Used for run metadata (status, request, artifact manifest) that must be
        readable mid-run, independently of the local run tree and final sync.
        """
        key = self.key_for(relative)
        if not self.enabled:
            return key
        body = json.dumps(payload, indent=2, sort_keys=True).encode()
        self._attempt(
            f"put {relative}",
            lambda: self.client.put_object(
                Bucket=self.config.bucket,
                Key=key,
                Body=body,
                ContentType="application/json",
            ),
        )
        return key

    def put_immutable_json(
        self, relative: str | PurePosixPath, payload: dict[str, Any]
    ) -> str:
        """Create a JSON object once, accepting only byte-identical replay.

        S3's conditional create is the atomic boundary.  A retry after a lost
        response may observe an existing object, so an identical body is treated
        as idempotent while any difference is an immutable-evidence violation.
        """
        key = self.key_for(relative)
        if not self.enabled:
            return key
        body = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
        try:
            self.client.put_object(
                Bucket=self.config.bucket,
                Key=key,
                Body=body,
                ContentType="application/json",
                Metadata={"sha256": hashlib.sha256(body).hexdigest()},
                IfNoneMatch="*",
            )
        except Exception as exc:
            try:
                existing = self.client.get_object(
                    Bucket=self.config.bucket, Key=key
                )["Body"].read()
            except Exception as read_exc:
                raise StorageError(
                    f"immutable publish {relative} could not be verified"
                ) from read_exc
            if existing != body:
                raise StorageError(
                    f"immutable object already exists with different bytes: {relative}"
                ) from exc
        return key

    def get_json_optional(self, relative: str | PurePosixPath) -> dict[str, Any] | None:
        """Read a JSON object, returning None when it does not yet exist.

        A single attempt is made (no retry): a missing object is an expected
        state for in-progress runs, not a transient failure to retry.
        """
        if not self.enabled:
            return None
        key = self.key_for(relative)
        try:
            response = self.client.get_object(Bucket=self.config.bucket, Key=key)
        except Exception:  # missing key or transient error -> treat as absent
            return None
        result = json.loads(response["Body"].read())
        if not isinstance(result, dict):
            raise StorageError(f"invalid JSON object at {relative}")
        return result

    def head_object_optional(self, relative: str | PurePosixPath) -> dict[str, Any] | None:
        """Return an object's size and upload digest, or None when absent.

        Campaign verification proves that every artifact the manifest declares
        actually exists at its declared size and SHA-256. Doing that with HEAD
        keeps the check cheap and, more importantly, keeps whole run artifacts
        on the cloud side instead of pulling them to the caller.
        """
        if not self.enabled:
            return None
        key = self.key_for(relative)
        try:
            response = self.client.head_object(Bucket=self.config.bucket, Key=key)
        except Exception:  # missing key or transient error -> treat as absent
            return None
        size = response.get("ContentLength")
        metadata = response.get("Metadata")
        sha256 = metadata.get("sha256") if isinstance(metadata, dict) else None
        return {
            "size_bytes": int(size) if size is not None else None,
            "sha256": str(sha256) if sha256 is not None else None,
            "key": key,
        }

    def presigned_url(self, relative: str | PurePosixPath, *, expires: int = 3600) -> str:
        """Return a time-limited GET URL for an object under the run prefix."""
        key = self.key_for(relative)
        if not self.enabled:
            return key
        url = self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.config.bucket, "Key": key},
            ExpiresIn=expires,
        )
        return str(url)

    def _get_json(self, relative: str) -> dict[str, Any]:
        if not self.enabled:
            raise StorageError("remote resume requires S3 storage mode")
        response = self._attempt(
            f"download {relative}",
            lambda: self.client.get_object(
                Bucket=self.config.bucket,
                Key=self.key_for(relative),
            ),
        )
        result = json.loads(response["Body"].read())
        if not isinstance(result, dict):
            raise StorageError(f"invalid JSON object at {relative}")
        return result

    def resume_latest(
        self,
        destination: Path,
        config: RunConfig,
        *,
        allowed_source_environment: str | None = None,
    ) -> Path:
        manifest = self._get_json("checkpoints/latest.json")
        if (
            manifest.get("backend") != config.backend
            or (
                manifest.get("environment") != config.environment
                and manifest.get("environment") != allowed_source_environment
            )
        ):
            raise CheckpointError("latest remote checkpoint is incompatible with selected config")
        checkpoint = destination / Path(str(manifest["checkpoint_key"])).name
        sidecar = metadata_path(checkpoint)
        destination.mkdir(parents=True, exist_ok=True)
        self._attempt(
            "download checkpoint",
            lambda: self.client.download_file(
                self.config.bucket,
                manifest["checkpoint_key"],
                str(checkpoint),
            ),
        )
        self._attempt(
            "download checkpoint metadata",
            lambda: self.client.download_file(
                self.config.bucket,
                manifest["metadata_key"],
                str(sidecar),
            ),
        )
        if sha256_file(checkpoint) != manifest.get("sha256"):
            checkpoint.unlink(missing_ok=True)
            sidecar.unlink(missing_ok=True)
            raise CheckpointError("downloaded checkpoint checksum mismatch")
        return checkpoint

    def resume_named_checkpoint(
        self,
        destination: Path,
        config: RunConfig,
        *,
        checkpoint_name: str,
        expected_sha256: str,
    ) -> Path:
        """Restore one exact, already-selected checkpoint from this run.

        Extensions must never substitute the latest checkpoint for the ranked
        parent.  The campaign records the canonical checkpoint filename and
        digest; both are required here before a child run can resume.
        """
        safe = PurePosixPath(checkpoint_name)
        if safe.is_absolute() or len(safe.parts) != 1 or safe.suffix != ".zip":
            raise CheckpointError("selected checkpoint filename is unsafe")
        checkpoint = destination / safe.name
        sidecar = metadata_path(checkpoint)
        destination.mkdir(parents=True, exist_ok=True)
        source_checkpoint = self.key_for(f"checkpoints/{safe.name}")
        source_sidecar = self.key_for(f"checkpoints/{sidecar.name}")
        self._attempt(
            "download selected checkpoint",
            lambda: self.client.download_file(
                self.config.bucket, source_checkpoint, str(checkpoint)
            ),
        )
        self._attempt(
            "download selected checkpoint metadata",
            lambda: self.client.download_file(self.config.bucket, source_sidecar, str(sidecar)),
        )
        metadata = validate_checkpoint(checkpoint, config)
        if metadata.sha256 != expected_sha256:
            checkpoint.unlink(missing_ok=True)
            sidecar.unlink(missing_ok=True)
            raise CheckpointError("selected remote checkpoint checksum mismatch")
        return checkpoint


def copy_local_artifact(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination
