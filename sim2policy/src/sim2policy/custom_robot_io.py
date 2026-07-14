"""Bounded object-storage/local input and output helpers for custom robot jobs."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal, cast

from sim2policy.custom_robot_contract import (
    ADAPTER_VERSION,
    PREPARATION_PROFILE,
    PREPARATION_PROFILE_VERSION,
    REWARD_VERSION,
    SCHEMA_VERSION,
    SHA256_RE,
    SUPPORTED_ROBOT_TYPES,
    SUPPORTED_SCENES,
    SUPPORTED_TASKS,
    canonical_json,
    preparation_fingerprint,
    sha256_bytes,
    validate_safe_id,
)

RUN_PREFIX = "sim2policy"
MANIFEST_NAME = "input-manifest.json"


class CustomInputError(ValueError):
    """A bounded public category; callers must not add raw XML/path details."""


@dataclass(frozen=True)
class CustomInputDocuments:
    manifest: dict[str, Any]
    robot_xml: str
    setup: dict[str, Any]
    source_prefix: str

    @property
    def fingerprint(self) -> str:
        return str(self.manifest["fingerprint"])


def input_prefix(identity: str, kind: Literal["preparation", "run"]) -> str:
    validate_safe_id(identity, f"{kind} identity")
    if kind == "preparation":
        return f"{RUN_PREFIX}/preparations/{identity}/inputs"
    return f"{RUN_PREFIX}/{identity}/inputs"


def _safe_member(name: object, expected: str) -> str:
    if name != expected or PurePosixPath(str(name)).name != expected:
        raise CustomInputError("input manifest contains an unsupported member path")
    return expected


def _bounded_json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CustomInputError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise CustomInputError(f"{label} must be a JSON object")
    return value


def _validate_input_descriptor(value: object, *, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CustomInputError("input manifest descriptor is invalid")
    required = {"id", "path", "source_digest", "sha256", "size_bytes"}
    if set(value) != required:
        raise CustomInputError("input manifest descriptor fields are invalid")
    validate_safe_id(str(value["id"]), "input identity")
    _safe_member(value["path"], path)
    for field in ("source_digest", "sha256"):
        if not SHA256_RE.fullmatch(str(value[field])):
            raise CustomInputError("input manifest digest is invalid")
    size = value["size_bytes"]
    if (
        isinstance(size, bool)
        or not isinstance(size, int)
        or not 1 <= size <= PREPARATION_PROFILE.max_input_bytes
    ):
        raise CustomInputError("input manifest size is outside the bounded contract")
    return value


def validate_documents(
    manifest_bytes: bytes,
    robot_bytes: bytes,
    setup_bytes: bytes,
    *,
    source_prefix: str,
) -> CustomInputDocuments:
    if len(manifest_bytes) > 64 * 1024:
        raise CustomInputError("input manifest exceeds the bounded contract")
    manifest = _bounded_json(manifest_bytes, "input manifest")
    required = {
        "schema_version",
        "preparation_id",
        "fingerprint",
        "robot",
        "setup",
        "runtime",
        "adapter_version",
        "reward_version",
        "preparation_profile_version",
    }
    if set(manifest) != required:
        raise CustomInputError("input manifest fields are invalid")
    if manifest["schema_version"] != SCHEMA_VERSION:
        raise CustomInputError("input manifest schema version is unsupported")
    validate_safe_id(str(manifest["preparation_id"]), "preparation identity")
    if manifest["adapter_version"] != ADAPTER_VERSION:
        raise CustomInputError("input adapter version is unsupported")
    if manifest["reward_version"] != REWARD_VERSION:
        raise CustomInputError("input reward version is unsupported")
    if manifest["preparation_profile_version"] != PREPARATION_PROFILE_VERSION:
        raise CustomInputError("input preparation profile version is unsupported")
    robot = _validate_input_descriptor(manifest["robot"], path="robot.xml")
    setup_descriptor = _validate_input_descriptor(manifest["setup"], path="normalized-setup.json")
    runtime = manifest["runtime"]
    if not isinstance(runtime, dict) or set(runtime) != {"image_digest"}:
        raise CustomInputError("input runtime identity is invalid")
    runtime_image = runtime["image_digest"]
    if not isinstance(runtime_image, str) or not runtime_image or len(runtime_image) > 256:
        raise CustomInputError("input runtime image identity is invalid")

    for raw, descriptor, label in (
        (robot_bytes, robot, "robot"),
        (setup_bytes, setup_descriptor, "setup"),
    ):
        if len(raw) != descriptor["size_bytes"]:
            raise CustomInputError(f"{label} input size does not match its manifest")
        if len(raw) > PREPARATION_PROFILE.max_input_bytes:
            raise CustomInputError(f"{label} input exceeds the bounded contract")
        if sha256_bytes(raw) != descriptor["sha256"]:
            raise CustomInputError(f"{label} input digest does not match its manifest")

    setup = _bounded_json(setup_bytes, "normalized setup")
    if canonical_json(setup) != setup_bytes:
        raise CustomInputError("normalized setup is not canonically encoded")
    if set(setup) != {
        "schema_version",
        "robot_type",
        "task_template_id",
        "scene_preset_id",
        "objects",
    }:
        raise CustomInputError("normalized setup fields are invalid")
    if setup["schema_version"] != SCHEMA_VERSION:
        raise CustomInputError("normalized setup schema is unsupported")
    if setup["robot_type"] not in SUPPORTED_ROBOT_TYPES:
        raise CustomInputError("normalized setup robot type is unsupported")
    if setup["task_template_id"] not in SUPPORTED_TASKS:
        raise CustomInputError("normalized setup task is unsupported")
    if setup["scene_preset_id"] not in SUPPORTED_SCENES:
        raise CustomInputError("normalized setup scene is unsupported")
    if setup["objects"] != []:
        raise CustomInputError("normalized setup optional objects are unsupported")

    expected_fingerprint = preparation_fingerprint(
        robot_digest=str(robot["source_digest"]),
        setup_digest=str(setup_descriptor["source_digest"]),
        runtime_image_digest=runtime_image,
    )
    if manifest["fingerprint"] != expected_fingerprint:
        raise CustomInputError("input fingerprint does not match its source contract")
    if sha256_bytes(robot_bytes) != robot["source_digest"]:
        raise CustomInputError("robot source digest does not match its exact XML")
    try:
        robot_xml = robot_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CustomInputError("robot input is not valid UTF-8") from exc
    return CustomInputDocuments(manifest, robot_xml, setup, source_prefix)


def load_inputs_from_directory(root: Path) -> CustomInputDocuments:
    root = root.resolve()
    try:
        manifest = (root / MANIFEST_NAME).read_bytes()
        robot = (root / "robot.xml").read_bytes()
        setup = (root / "normalized-setup.json").read_bytes()
    except OSError as exc:
        raise CustomInputError("required custom robot input is unavailable") from exc
    return validate_documents(manifest, robot, setup, source_prefix=str(root))


def _bounded_s3_read(client: Any, bucket: str, key: str, maximum: int) -> bytes:
    try:
        response = client.get_object(Bucket=bucket, Key=key)
        declared = response.get("ContentLength")
        if isinstance(declared, int) and declared > maximum:
            raise CustomInputError("object storage input exceeds the bounded contract")
        raw = response["Body"].read(maximum + 1)
    except CustomInputError:
        raise
    except Exception as exc:
        raise CustomInputError("required custom robot input is unavailable") from exc
    if len(raw) > maximum:
        raise CustomInputError("object storage input exceeds the bounded contract")
    return cast(bytes, raw)


def build_s3_client_from_env() -> tuple[Any, str]:
    import boto3  # type: ignore[import-untyped]

    bucket = os.environ.get("SIM2POLICY_S3_BUCKET", "")
    if not bucket:
        raise CustomInputError("custom robot object storage is not configured")
    return (
        boto3.client(
            "s3",
            endpoint_url=os.environ.get("AWS_ENDPOINT_URL_S3")
            or os.environ.get("SIM2POLICY_S3_ENDPOINT"),
            region_name=os.environ.get("AWS_DEFAULT_REGION") or os.environ.get("AWS_REGION"),
        ),
        bucket,
    )


def load_inputs_from_s3(
    identity: str,
    *,
    kind: Literal["preparation", "run"],
    client: Any | None = None,
    bucket: str | None = None,
) -> CustomInputDocuments:
    prefix = input_prefix(identity, kind)
    if client is None or bucket is None:
        client, bucket = build_s3_client_from_env()
    manifest = _bounded_s3_read(client, bucket, f"{prefix}/{MANIFEST_NAME}", 64 * 1024)
    robot = _bounded_s3_read(
        client, bucket, f"{prefix}/robot.xml", PREPARATION_PROFILE.max_input_bytes
    )
    setup = _bounded_s3_read(
        client,
        bucket,
        f"{prefix}/normalized-setup.json",
        PREPARATION_PROFILE.max_input_bytes,
    )
    return validate_documents(manifest, robot, setup, source_prefix=prefix)


def put_s3_bytes(key: str, data: bytes, *, content_type: str) -> None:
    if not key.startswith(f"{RUN_PREFIX}/") or ".." in PurePosixPath(key).parts:
        raise CustomInputError("output object key is outside the server run prefix")
    client, bucket = build_s3_client_from_env()
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
        Metadata={"sha256": sha256_bytes(data)},
    )


def put_s3_json(key: str, value: dict[str, Any]) -> bytes:
    data = canonical_json(value)
    put_s3_bytes(key, data, content_type="application/json")
    return data
