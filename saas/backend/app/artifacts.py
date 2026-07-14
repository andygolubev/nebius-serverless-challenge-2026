"""Read run artifacts from the sim2policy S3 bucket.

The training container owns the layout (see sim2policy/src/sim2policy/runstate.py):

    sim2policy/<run-id>/metadata/status.json
    sim2policy/<run-id>/report/metrics.json
    sim2policy/<run-id>/report/artifacts.json   # logical name -> object key

Reads go through the S3 API (boto3) against the Nebius endpoint — never the
management SDK. A missing manifest is normal mid-run and maps to "not ready".
"""

from __future__ import annotations

import json
import hashlib
import io
import logging
import mimetypes
import re
import stat
import zipfile
from typing import Any

from .models import Artifact, ArtifactManifest
from .settings import NebiusSettings

log = logging.getLogger(__name__)

RUN_PREFIX = "sim2policy"
_MEDIA_SUFFIXES = (".mp4", ".png", ".gif")
_SAFE_REL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_JSON_BYTES = 2 * 1024 * 1024
_REQUIRED_CUSTOM_ARTIFACTS = {
    "final_policy",
    "metrics_json",
    "report_md",
    "reward_curve",
    "video_final",
    "resolved_config",
    "runtime_versions",
    "policy_bundle",
    "bundle_manifest",
    "robot_xml",
    "normalized_setup",
}
_REQUIRED_GALLERY_ARTIFACTS = {
    "final_policy",
    "metrics_json",
    "report_md",
    "video_final",
    "resolved_config",
    "runtime_versions",
    "policy_bundle",
}
_REQUIRED_GALLERY_BUNDLE_MEMBERS = {
    "README.md",
    "checkpoint/policy.zip",
    "checkpoint/policy.zip.json",
    "resolved-config.json",
    "evaluation/metrics.json",
    "runtime/versions.json",
}
_MAX_BUNDLE_BYTES = 512 * 1024 * 1024


def build_s3_client(settings: NebiusSettings):
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        region_name=settings.s3_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )


class S3ArtifactReader:
    """Builds tenant-facing ArtifactManifests from a run's S3 prefix.

    `client` is any boto3-compatible S3 client (tests pass a stub).
    """

    def __init__(self, client: Any, bucket: str, prefix: str = RUN_PREFIX) -> None:
        self._client = client
        self._bucket = bucket
        self._prefix = prefix

    def _key(self, run_id: str, rel: str) -> str:
        return f"{self._prefix}/{run_id}/{rel}"

    def _read_json(self, key: str) -> dict[str, Any] | None:
        try:
            obj = self._client.get_object(Bucket=self._bucket, Key=key)
        except Exception as e:  # boto3 raises client-specific subclasses
            if _is_missing_key_error(e):
                return None
            raise
        raw = obj["Body"].read(_MAX_JSON_BYTES + 1)
        if len(raw) > _MAX_JSON_BYTES:
            raise ValueError("artifact JSON exceeds the fixed bound")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("artifact JSON must be an object")
        return value

    def read_manifest(self, job_id: str, run_id: str) -> ArtifactManifest | None:
        """Return the manifest for a completed run, or None if not yet written."""
        manifest = self._read_json(self._key(run_id, "report/artifacts.json"))
        if manifest is None:
            return None
        # RunState.write_manifest() wraps the logical-name mapping under
        # "artifacts". Accept the old flat shape as well for compatibility
        # with manifests published before that envelope was introduced.
        artifact_map = manifest.get("artifacts")
        if not isinstance(artifact_map, dict):
            artifact_map = manifest
        checksums = manifest.get("checksums")
        is_custom = {"robot_xml", "normalized_setup"} <= set(artifact_map)
        is_gallery = "policy_bundle" in artifact_map and not is_custom
        if (is_custom or is_gallery) and checksums is None:
            raise ValueError("policy bundle artifact checksum manifest is missing")
        if checksums is not None:
            if not isinstance(checksums, dict) or set(checksums) != set(artifact_map):
                raise ValueError("artifact checksum manifest does not match artifacts")
            if is_custom and set(artifact_map) != _REQUIRED_CUSTOM_ARTIFACTS:
                raise ValueError("custom run artifact manifest is incomplete")
            if is_gallery and not _REQUIRED_GALLERY_ARTIFACTS <= set(artifact_map):
                raise ValueError("gallery run artifact manifest is incomplete")
        status = self._read_json(self._key(run_id, "metadata/status.json")) or {}
        metrics = self._read_json(self._key(run_id, "report/metrics.json")) or {}
        artifacts = []
        for logical_name, rel in sorted(artifact_map.items()):
            if (
                not isinstance(rel, str)
                or not _SAFE_REL.fullmatch(rel)
                or ".." in rel.split("/")
            ):
                raise ValueError("artifact manifest contains an unsafe path")
            key = self._key(run_id, rel)
            size_bytes = None
            digest = None
            if isinstance(checksums, dict):
                descriptor = checksums.get(logical_name)
                if not isinstance(descriptor, dict) or set(descriptor) != {
                    "sha256",
                    "size_bytes",
                }:
                    raise ValueError("artifact checksum descriptor is invalid")
                digest = descriptor["sha256"]
                size_bytes = descriptor["size_bytes"]
                if (
                    not isinstance(digest, str)
                    or not _SHA256.fullmatch(digest)
                    or isinstance(size_bytes, bool)
                    or not isinstance(size_bytes, int)
                    or size_bytes < 1
                ):
                    raise ValueError("artifact checksum descriptor is invalid")
                head = self._client.head_object(Bucket=self._bucket, Key=key)
                remote_digest = (head.get("Metadata") or {}).get("sha256")
                if head.get("ContentLength") != size_bytes or remote_digest != digest:
                    raise ValueError("artifact object does not match its checksum")
                if is_gallery and logical_name == "policy_bundle":
                    expected_example = (
                        self._read_json(
                            self._key(run_id, "report/resolved-config.json")
                        )
                        or {}
                    )
                    self._validate_gallery_bundle(
                        key,
                        digest=digest,
                        size_bytes=size_bytes,
                        expected_example_id=str(
                            expected_example.get("gallery_example_id", "")
                        ),
                    )
            content_type = mimetypes.guess_type(rel)[0] or "application/octet-stream"
            artifacts.append(
                Artifact(
                    id=str(logical_name),
                    name=_label(str(logical_name)),
                    kind=(
                        "video"
                        if rel.endswith(".mp4")
                        else "image"
                        if rel.endswith((".png", ".gif"))
                        else "file"
                    ),
                    content_type=content_type,
                    size_bytes=size_bytes,
                    sha256=digest,
                    key=key,
                )
            )
        media = sorted(a.key for a in artifacts if a.key.endswith(_MEDIA_SUFFIXES))
        return ArtifactManifest(
            job_id=job_id,
            status=str(status.get("status", "completed")),
            metrics=metrics if isinstance(metrics, dict) else {},
            media=media,
            artifacts=artifacts,
        )

    def _validate_gallery_bundle(
        self,
        key: str,
        *,
        digest: str,
        size_bytes: int,
        expected_example_id: str,
    ) -> None:
        if not expected_example_id or size_bytes > _MAX_BUNDLE_BYTES:
            raise ValueError("gallery policy bundle provenance is invalid")
        obj = self._client.get_object(Bucket=self._bucket, Key=key)
        raw = obj["Body"].read(_MAX_BUNDLE_BYTES + 1)
        if len(raw) != size_bytes or hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("gallery policy bundle object is invalid")
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            names = [item.filename for item in infos]
            if len(names) != len(set(names)) or set(names) != {
                *_REQUIRED_GALLERY_BUNDLE_MEMBERS,
                "manifest.json",
            }:
                raise ValueError("gallery policy bundle layout is invalid")
            total_size = 0
            for info in infos:
                name = info.filename
                parts = name.split("/")
                if name.startswith("/") or name.endswith("/") or ".." in parts:
                    raise ValueError("gallery policy bundle path is invalid")
                mode = (info.external_attr >> 16) & 0xFFFF
                if mode and not stat.S_ISREG(mode):
                    raise ValueError("gallery policy bundle member type is invalid")
                if not 0 < info.file_size <= _MAX_BUNDLE_BYTES:
                    raise ValueError("gallery policy bundle member size is invalid")
                total_size += info.file_size
            if total_size > _MAX_BUNDLE_BYTES:
                raise ValueError("gallery policy bundle expanded size is invalid")
            manifest = json.loads(archive.read("manifest.json"))
            if (
                not isinstance(manifest, dict)
                or manifest.get("schema_version") != "gallery-policy-bundle-v1"
                or manifest.get("kind") != "verified-example-policy-bundle"
                or manifest.get("simulator_only") is not True
                or manifest.get("example_id") != expected_example_id
            ):
                raise ValueError("gallery policy bundle provenance is invalid")
            descriptors = {
                item.get("path"): item
                for item in manifest.get("members", [])
                if isinstance(item, dict)
            }
            if set(descriptors) != _REQUIRED_GALLERY_BUNDLE_MEMBERS:
                raise ValueError("gallery policy bundle manifest is incomplete")
            for name in _REQUIRED_GALLERY_BUNDLE_MEMBERS:
                value = archive.read(name)
                descriptor = descriptors[name]
                if (
                    descriptor.get("size_bytes") != len(value)
                    or descriptor.get("sha256") != hashlib.sha256(value).hexdigest()
                ):
                    raise ValueError("gallery policy bundle member digest is invalid")
            if not zipfile.is_zipfile(
                io.BytesIO(archive.read("checkpoint/policy.zip"))
            ):
                raise ValueError("gallery policy bundle checkpoint is invalid")

    def presigned_url(
        self,
        key: str,
        *,
        content_type: str | None = None,
        download_name: str | None = None,
    ) -> str:
        params = {"Bucket": self._bucket, "Key": key}
        if content_type:
            params["ResponseContentType"] = content_type
        if download_name:
            params["ResponseContentDisposition"] = (
                f'attachment; filename="{download_name}"'
            )
        return self._client.generate_presigned_url(
            "get_object", Params=params, ExpiresIn=300
        )


def _label(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").strip().title()


def _is_missing_key_error(e: Exception) -> bool:
    """True for boto3 NoSuchKey/404 errors, without importing botocore in tests."""
    code = (
        getattr(e, "response", {}).get("Error", {}).get("Code", "")
        if hasattr(e, "response")
        else ""
    )
    return code in {"NoSuchKey", "404", "NotFound"} or type(e).__name__ == "NoSuchKey"
