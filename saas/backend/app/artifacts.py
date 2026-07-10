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
import logging
from typing import Any

from .models import ArtifactManifest
from .settings import NebiusSettings

log = logging.getLogger(__name__)

RUN_PREFIX = "sim2policy"
_MEDIA_SUFFIXES = (".mp4", ".png", ".gif")


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
        return json.loads(obj["Body"].read())

    def read_manifest(self, job_id: str, run_id: str) -> ArtifactManifest | None:
        """Return the manifest for a completed run, or None if not yet written."""
        manifest = self._read_json(self._key(run_id, "report/artifacts.json"))
        if manifest is None:
            return None
        status = self._read_json(self._key(run_id, "metadata/status.json")) or {}
        metrics = self._read_json(self._key(run_id, "report/metrics.json")) or {}
        media = sorted(
            self._key(run_id, rel)
            for rel in manifest.values()
            if isinstance(rel, str) and rel.endswith(_MEDIA_SUFFIXES)
        )
        return ArtifactManifest(
            job_id=job_id,
            status=str(status.get("status", "completed")),
            metrics=metrics if isinstance(metrics, dict) else {},
            media=media,
        )


def _is_missing_key_error(e: Exception) -> bool:
    """True for boto3 NoSuchKey/404 errors, without importing botocore in tests."""
    code = getattr(e, "response", {}).get("Error", {}).get("Code", "") if hasattr(e, "response") else ""
    return code in {"NoSuchKey", "404", "NotFound"} or type(e).__name__ == "NoSuchKey"
