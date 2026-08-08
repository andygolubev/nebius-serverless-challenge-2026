"""Fixed-prefix S3 publication and finalization for custom robot inputs."""

from __future__ import annotations

import hashlib
import json
import re
from contextlib import suppress
from typing import Any

from .custom_training import SCHEMA_VERSION, canonical_json

MAX_INPUT_BYTES = 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024
MAX_REPORT_BYTES = 256 * 1024
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class CustomStorageError(RuntimeError):
    pass


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class CustomRobotStorage:
    def __init__(self, client: Any, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    def _put_verified(
        self, key: str, value: bytes, content_type: str, maximum: int
    ) -> None:
        if not value or len(value) > maximum:
            raise CustomStorageError(
                "custom robot input size is outside the fixed contract"
            )
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=value,
                ContentType=content_type,
                Metadata={"sha256": _sha(value)},
            )
            result = self._client.head_object(Bucket=self._bucket, Key=key)
        except Exception as exc:
            raise CustomStorageError("custom robot input publication failed") from exc
        if result.get("ContentLength") != len(value):
            raise CustomStorageError(
                "custom robot input publication verification failed"
            )
        expected_digest = _sha(value)
        remote_digest = (result.get("Metadata") or {}).get("sha256")
        if remote_digest is None:
            # Nebius Object Storage may omit user metadata even for put_object.
            # Re-read this already bounded input and verify its content instead.
            try:
                response = self._client.get_object(Bucket=self._bucket, Key=key)
                uploaded = response["Body"].read(maximum + 1)
            except Exception as exc:
                raise CustomStorageError(
                    "custom robot input publication verification failed"
                ) from exc
            if len(uploaded) != len(value) or _sha(uploaded) != expected_digest:
                raise CustomStorageError(
                    "custom robot input publication verification failed"
                )
        elif remote_digest != expected_digest:
            raise CustomStorageError(
                "custom robot input publication digest verification failed"
            )

    def publish_preparation_inputs(
        self,
        preparation_id: str,
        *,
        robot: bytes,
        setup: bytes,
        manifest: bytes,
    ) -> None:
        self._publish_inputs(
            preparation_id,
            "preparation",
            f"sim2policy/preparations/{preparation_id}/inputs",
            robot,
            setup,
            manifest,
        )

    def snapshot_training_inputs(
        self,
        run_id: str,
        *,
        robot: bytes,
        setup: bytes,
        manifest: bytes,
    ) -> None:
        self._publish_inputs(
            run_id,
            "run",
            f"sim2policy/{run_id}/inputs",
            robot,
            setup,
            manifest,
        )

    def _publish_inputs(
        self,
        identity: str,
        identity_kind: str,
        prefix: str,
        robot: bytes,
        setup: bytes,
        manifest: bytes,
    ) -> None:
        if not _SAFE_ID.fullmatch(identity):
            raise CustomStorageError(f"{identity_kind} identity is invalid")
        members = (
            ("robot.xml", robot, "application/xml", MAX_INPUT_BYTES),
            ("normalized-setup.json", setup, "application/json", MAX_INPUT_BYTES),
            ("input-manifest.json", manifest, "application/json", MAX_MANIFEST_BYTES),
        )
        try:
            for name, value, content_type, maximum in members:
                self._put_verified(f"{prefix}/{name}", value, content_type, maximum)
        except Exception:
            for name, *_ in members:
                with suppress(Exception):
                    self._client.delete_object(
                        Bucket=self._bucket, Key=f"{prefix}/{name}"
                    )
            raise

    def read_preparation_report(self, preparation_id: str) -> dict[str, Any] | None:
        if not _SAFE_ID.fullmatch(preparation_id):
            raise CustomStorageError("preparation identity is invalid")
        key = f"sim2policy/preparations/{preparation_id}/report/preparation.json"
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            raw = response["Body"].read(MAX_REPORT_BYTES + 1)
        except Exception as exc:
            code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
            if code in {"NoSuchKey", "404", "NotFound"}:
                return None
            raise CustomStorageError("preparation report read failed") from exc
        if len(raw) > MAX_REPORT_BYTES:
            raise CustomStorageError("preparation report exceeds the fixed contract")
        declared = response.get("ContentLength")
        if isinstance(declared, int) and declared != len(raw):
            raise CustomStorageError("preparation report size is invalid")
        object_digest = (response.get("Metadata") or {}).get("sha256")
        if object_digest is not None and object_digest != _sha(raw):
            raise CustomStorageError("preparation report object digest is invalid")
        try:
            report = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CustomStorageError("preparation report is invalid") from exc
        if not isinstance(report, dict):
            raise CustomStorageError("preparation report is invalid")
        required = {
            "schema_version",
            "preparation_id",
            "fingerprint",
            "status",
            "failure_phase",
            "failure_reason",
            "phases",
            "compiled",
            "schemas",
            "versions",
            "report_sha256",
        }
        if set(report) != required:
            raise CustomStorageError("preparation report fields are invalid")
        if (
            report["schema_version"] != SCHEMA_VERSION
            or report["preparation_id"] != preparation_id
            or report["status"] not in {"accepted", "failed"}
            or not isinstance(report["phases"], list)
            or len(report["phases"]) > 16
            or not isinstance(report["compiled"], dict)
            or not isinstance(report["schemas"], dict)
            or not isinstance(report["versions"], dict)
        ):
            raise CustomStorageError("preparation report contract is invalid")
        fingerprint = report["fingerprint"]
        if not isinstance(fingerprint, str) or not re.fullmatch(
            r"[0-9a-f]{64}", fingerprint
        ):
            raise CustomStorageError("preparation report fingerprint is invalid")
        reported_hash = report.get("report_sha256")
        unsigned = dict(report)
        unsigned.pop("report_sha256", None)
        if reported_hash != _sha(canonical_json(unsigned)):
            raise CustomStorageError("preparation report digest is invalid")
        return report
