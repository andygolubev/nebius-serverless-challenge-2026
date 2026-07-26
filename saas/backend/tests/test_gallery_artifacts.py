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


SHOWCASE_METRICS = {
    "aggregate": {"episodes": 20, "mean_reward": 1234.5, "mean_episode_length": 900},
    "benchmark": {"estimated_cost": 0.12, "currency": "USD", "rate_date": "2026-07-26"},
    "checkpoint": "final-000001000000.zip",
    "environment": "Hopper-v5",
    "backend": "sb3",
    "runtime_seconds": 613.2,
    "success": {"met": True, "criterion": "mean_reward >= 1000"},
    "matrix_digest": "a" * 64,
    "resolved_config": {
        "runtime_image": "registry.example/sim2policy-sb3@sha256:" + "b" * 64,
        "training": {"total_steps": 8000000},
        "hardware": {"platform": "cpu-d3", "preset": "8vcpu-32gb"},
    },
    "selected_checkpoint": {"effective_step": 5000000, "sha256": "c" * 64},
    "seed_roles": {"selection": [101, 151, 211, 271, 331], "final": [0, 1, 2, 3, 4]},
    "ranking_explanation": {"kind": "mean_reward", "fields": ["mean_reward"]},
    "acceptance": {
        "hard": {"criteria": {"mean_reward": True}, "passed": True},
        "preferred": {"criteria": {"mean_reward": True}, "passed": True},
    },
    "progression": [
        {"stage": "untrained", "selected": False, "checkpoint": {"effective_step": 0, "sha256": "d" * 64}},
        {"stage": "selected", "selected": True, "checkpoint": {"effective_step": 5000000, "sha256": "c" * 64}},
        {"stage": "final-step", "selected": False, "regression": True, "checkpoint": {"effective_step": 8000000, "sha256": "e" * 64}},
    ],
}

# A completed diagnostic G1 run is useful as a public-gate regression fixture:
# it has complete provenance but must never be promoted because final success is false.
G1_COMPLETED_FAILED_METRICS = {
    **SHOWCASE_METRICS,
    "environment": "G1JoystickRoughTerrain",
    "backend": "mjx",
    "aggregate": {"episodes": 20, "mean_velocity": 0.31, "mean_episode_length": 442},
    "success": {"met": False, "criterion": "velocity >= 0.4 and not fallen"},
    "phase_lineage": {
        "flat": {"environment": "G1JoystickFlatTerrain", "selected_step": 150000000},
        "rough": {"environment": "G1JoystickRoughTerrain", "effective_total_steps": 450000000},
    },
}


class MemoryS3:
    def __init__(
        self,
        *,
        tamper_bundle: bool = False,
        omit_checksum_metadata: bool = False,
        run: str = "sim2policy/gallery-run",
        metrics: dict[str, Any] | None = None,
        drop: tuple[str, ...] = (),
        out_of_prefix: str | None = None,
    ) -> None:
        self.objects: dict[str, bytes] = {}
        self.omit_checksum_metadata = omit_checksum_metadata
        self.presigned: list[dict[str, Any]] = []
        artifacts = {
            "final_policy": "checkpoints/final.zip",
            "metrics_json": "report/metrics.json",
            "report_md": "report/report.md",
            "video_final": "videos/final.mp4",
            "video_selected": "videos/selected.mp4",
            "video_final_step": "videos/final-step.mp4",
            "resolved_config": "report/resolved-config.json",
            "runtime_versions": "report/runtime-versions.json",
            "policy_bundle": "bundle/policy-bundle.zip",
        }
        for name in drop:
            artifacts.pop(name, None)
        if out_of_prefix is not None:
            artifacts[out_of_prefix] = "../other-run/steal.json"
        # `metrics_json` *is* report/metrics.json, so its content must be set here
        # rather than written separately, or the object and its checksum disagree.
        values = {
            "final_policy": _checkpoint(),
            "metrics_json": _json(SHOWCASE_METRICS if metrics is None else metrics),
            "report_md": b"result\n",
            "video_final": b"mp4-placeholder",
            "video_selected": b"mp4-selected-placeholder",
            "video_final_step": b"mp4-final-step-placeholder",
            "resolved_config": _json({"gallery_example_id": "hopper-balance"}),
            "runtime_versions": b"{}\n",
            "policy_bundle": _bundle(tamper=tamper_bundle),
        }
        checksums = {}
        for name, relative in artifacts.items():
            value = values.get(name, b"{}\n")
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

    def generate_presigned_url(self, _operation, *, Params, ExpiresIn) -> str:
        self.presigned.append({"params": Params, "expires_in": ExpiresIn})
        return f"https://objects.example/{Params['Key']}?signed=1"

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        del Bucket
        value = self.objects[Key]
        return {
            "ContentLength": len(value),
            "Metadata": (
                {}
                if self.omit_checksum_metadata
                else {"sha256": hashlib.sha256(value).hexdigest()}
            ),
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


def test_gallery_completion_streams_digest_when_object_store_omits_metadata() -> None:
    manifest = S3ArtifactReader(
        MemoryS3(omit_checksum_metadata=True), "bucket"
    ).read_manifest("job", "gallery-run")
    assert manifest is not None
    assert {item.id for item in manifest.artifacts} >= {
        "final_policy",
        "policy_bundle",
        "video_final",
    }


# -- public showcase delivery ----------------------------------------------------------


def _showcase_service(client: MemoryS3, store, *, enabled: bool = True):
    """A ShowcaseService over an in-memory run, as the API wires it in production."""
    from app.settings import ShowcaseSettings
    from app.showcase import ShowcaseService

    class Backend:
        artifact_reader = S3ArtifactReader(client, "bucket")

    return ShowcaseService(store, Backend(), ShowcaseSettings(enabled=enabled))


def test_showcase_manifest_read_reuses_the_tenant_validation(store) -> None:
    reader = S3ArtifactReader(MemoryS3(), "bucket")
    manifest = reader.read_showcase_manifest("gallery-run")
    assert manifest is not None
    # The pinned run identity doubles as the cache key.
    assert manifest.job_id == "gallery-run"
    assert {item.id for item in manifest.artifacts} >= {"video_final", "policy_bundle"}


def test_published_entry_exposes_allowlisted_artifacts_with_opaque_urls(
    store, pinned
) -> None:
    service = _showcase_service(MemoryS3(), store)
    detail = service.detail("hopper-balance")
    assert detail is not None
    ids = {item["id"] for item in detail["artifacts"]}
    assert ids == {
        "final_policy",
        "metrics_json",
        "report_md",
        "video_final",
        "video_selected",
        "video_final_step",
        "resolved_config",
        "runtime_versions",
        "policy_bundle",
    }
    for item in detail["artifacts"]:
        # Opaque route URLs, never a presigned URL or a bucket key.
        assert item["url"] == f"/showcase/hopper-balance/artifacts/{item['id']}"
        assert "signed" not in item["url"]
        assert "bucket" not in item["url"]
    video = next(item for item in detail["artifacts"] if item["id"] == "video_final")
    assert video["kind"] == "video"
    assert video["content_type"] == "video/mp4"


def test_presigned_delivery_is_short_lived_and_single_object(store, pinned) -> None:
    client = MemoryS3()
    service = _showcase_service(client, store)
    artifact = service.artifact("hopper-balance", "video_final")
    assert artifact is not None
    url = service.presigned(artifact, download=False)
    assert url is not None and url.startswith("https://objects.example/")
    call = client.presigned[-1]
    assert call["expires_in"] <= 300
    # Exactly one validated in-prefix object; no list or sibling access.
    assert call["params"]["Key"] == "sim2policy/gallery-run/videos/final.mp4"
    assert call["params"]["ResponseContentType"] == "video/mp4"

    download = service.presigned(artifact, download=True)
    assert download is not None
    assert 'filename="final.mp4"' in client.presigned[-1]["params"][
        "ResponseContentDisposition"
    ]


def test_artifact_absent_from_the_manifest_is_refused(store, pinned) -> None:
    service = _showcase_service(MemoryS3(), store)
    # Not in the public allowlist at all.
    assert service.artifact("hopper-balance", "backend_comparison") is None
    # Allowlisted but not published by this run.
    assert service.artifact("hopper-balance", "demo_recording") is None
    # A traversing or bogus identifier.
    assert service.artifact("hopper-balance", "../../etc/passwd") is None


def test_entry_is_withheld_when_a_required_artifact_is_missing(store, pinned) -> None:
    service = _showcase_service(MemoryS3(drop=("video_final",)), store)
    assert service.detail("hopper-balance") is None
    assert service.entries() == []


def test_entry_is_withheld_when_the_manifest_leaves_the_prefix(store, pinned) -> None:
    service = _showcase_service(MemoryS3(out_of_prefix="resolved_config"), store)
    assert service.detail("hopper-balance") is None


def test_entry_is_withheld_when_a_member_digest_disagrees(store, pinned) -> None:
    service = _showcase_service(MemoryS3(tamper_bundle=True), store)
    assert service.detail("hopper-balance") is None


def test_entry_is_withheld_when_the_declaration_disagrees_with_the_run(
    store, pinned
) -> None:
    """A stale card cannot advertise a configuration its pinned run did not execute."""
    metrics = {**SHOWCASE_METRICS, "environment": "halfcheetah"}
    service = _showcase_service(MemoryS3(metrics=metrics), store)
    assert service.detail("hopper-balance") is None

    backend_mismatch = {**SHOWCASE_METRICS, "backend": "mjx"}
    assert _showcase_service(MemoryS3(metrics=backend_mismatch), store).detail(
        "hopper-balance"
    ) is None


def test_evaluation_state_is_separate_from_infrastructure_completion(
    store, pinned
) -> None:
    metrics = {
        **SHOWCASE_METRICS,
        "aggregate": {"mean_reward": 3.0},
        "success": {"met": False, "criterion": "mean_reward >= 1000"},
    }
    service = _showcase_service(MemoryS3(metrics=metrics), store)
    # A completed infrastructure run that misses acceptance remains unpublished.
    assert service.detail("hopper-balance") is None


def test_disabled_showcase_publishes_nothing(store, pinned) -> None:
    service = _showcase_service(MemoryS3(), store, enabled=False)
    assert service.entries() == []
    assert service.detail("hopper-balance") is None
