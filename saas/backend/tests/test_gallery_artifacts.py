from __future__ import annotations

import hashlib
import io
import json
import stat
import zipfile
from typing import Any

import pytest

from app.artifacts import S3ArtifactReader


def _json(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _checkpoint() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("policy.bin", b"policy")
    return output.getvalue()


def _info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o600) << 16
    return info


def _bundle(*, tamper: bool = False) -> bytes:
    members = {
        "README.md": b"SIMULATOR ONLY",
        "checkpoint/policy.zip": _checkpoint(),
        "checkpoint/policy.zip.json": b"{}\n",
        "resolved-config.json": b"{}\n",
        "evaluation/metrics.json": b"{}\n",
        "runtime/versions.json": b"{}\n",
    }
    descriptors = [
        {
            "path": name,
            "content_type": "application/octet-stream",
            "size_bytes": len(value),
            "sha256": hashlib.sha256(value).hexdigest(),
        }
        for name, value in sorted(members.items())
    ]
    if tamper:
        members["README.md"] = b"changed after manifest"
    manifest = {
        "schema_version": "gallery-policy-bundle-v1",
        "kind": "verified-example-policy-bundle",
        "example_id": "hopper-balance",
        "simulator_only": True,
        "members": descriptors,
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, value in members.items():
            archive.writestr(_info(name), value)
        archive.writestr(_info("manifest.json"), _json(manifest))
    return output.getvalue()


class MemoryS3:
    def __init__(self, *, tamper_bundle: bool = False) -> None:
        self.objects: dict[str, bytes] = {}
        run = "sim2policy/gallery-run"
        artifacts = {
            "final_policy": "checkpoints/final.zip",
            "metrics_json": "report/metrics.json",
            "report_md": "report/report.md",
            "video_final": "videos/final.mp4",
            "resolved_config": "report/resolved-config.json",
            "runtime_versions": "report/runtime-versions.json",
            "policy_bundle": "bundle/policy-bundle.zip",
        }
        values = {
            "final_policy": _checkpoint(),
            "metrics_json": b"{}\n",
            "report_md": b"result\n",
            "video_final": b"mp4-placeholder",
            "resolved_config": _json({"gallery_example_id": "hopper-balance"}),
            "runtime_versions": b"{}\n",
            "policy_bundle": _bundle(tamper=tamper_bundle),
        }
        checksums = {}
        for name, relative in artifacts.items():
            value = values[name]
            self.objects[f"{run}/{relative}"] = value
            checksums[name] = {
                "sha256": hashlib.sha256(value).hexdigest(),
                "size_bytes": len(value),
            }
        self.objects[f"{run}/report/artifacts.json"] = _json(
            {"artifacts": artifacts, "checksums": checksums}
        )
        self.objects[f"{run}/metadata/status.json"] = _json({"status": "completed"})

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        del Bucket
        return {"Body": io.BytesIO(self.objects[Key])}

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        del Bucket
        value = self.objects[Key]
        return {
            "ContentLength": len(value),
            "Metadata": {"sha256": hashlib.sha256(value).hexdigest()},
        }


def test_gallery_completion_requires_outer_and_inner_bundle_integrity() -> None:
    manifest = S3ArtifactReader(MemoryS3(), "bucket").read_manifest(
        "job", "gallery-run"
    )
    assert manifest is not None
    bundle = next(item for item in manifest.artifacts if item.id == "policy_bundle")
    assert bundle.content_type == "application/zip"
    assert bundle.sha256 is not None


def test_gallery_completion_rejects_tampered_bundle_even_with_matching_outer_digest() -> (
    None
):
    with pytest.raises(ValueError, match="member digest"):
        S3ArtifactReader(MemoryS3(tamper_bundle=True), "bucket").read_manifest(
            "job", "gallery-run"
        )
