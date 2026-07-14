from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

import sim2policy.policy_bundle as policy_bundle
from sim2policy.checkpoint import write_checkpoint_metadata
from sim2policy.config import load_config
from sim2policy.policy_bundle import (
    REQUIRED_MEMBERS,
    build_gallery_policy_bundle,
    inspect_gallery_policy_bundle,
)

ROOT = Path(__file__).parents[1]


def _checkpoint(root: Path) -> Path:
    checkpoint = root / "final.zip"
    with zipfile.ZipFile(checkpoint, "w") as archive:
        archive.writestr("policy.bin", b"deterministic-policy")
    write_checkpoint_metadata(checkpoint, load_config(ROOT / "configs/smoke_sb3.yaml"), 128)
    return checkpoint


def _build(output: Path, checkpoint: Path) -> dict:
    return build_gallery_policy_bundle(
        output,
        run_id="gallery-run-safe",
        example_id="hopper-balance",
        backend="sb3",
        environment="Hopper-v5",
        checkpoint=checkpoint,
        resolved_config={"backend": "sb3", "environment": "Hopper-v5"},
        evaluation={"success": {"met": True}, "aggregate": {"mean_reward": 1200}},
        versions={"mujoco": "3.3.7", "stable_baselines3": "2.7.1"},
        runtime_image="registry.example/sim2policy:sb3-abcdef0",
    )


def test_gallery_bundle_is_byte_identical_and_every_member_is_checksummed(
    tmp_path: Path,
) -> None:
    checkpoint = _checkpoint(tmp_path)
    first, second = tmp_path / "first.zip", tmp_path / "second.zip"
    manifest = _build(first, checkpoint)
    _build(second, checkpoint)
    assert first.read_bytes() == second.read_bytes()
    assert inspect_gallery_policy_bundle(first, expected_example_id="hopper-balance") == manifest
    with zipfile.ZipFile(first) as archive:
        assert set(archive.namelist()) == {*REQUIRED_MEMBERS, "manifest.json"}
        for descriptor in manifest["members"]:
            value = archive.read(descriptor["path"])
            assert descriptor["size_bytes"] == len(value)
            assert descriptor["sha256"] == hashlib.sha256(value).hexdigest()
        assert "SIMULATOR ONLY" in archive.read("README.md").decode()
        assert not any("video" in name or "log" in name for name in archive.namelist())


def test_gallery_bundle_rejects_missing_metadata_wrong_identity_and_tampering(
    tmp_path: Path,
) -> None:
    checkpoint = _checkpoint(tmp_path)
    output = tmp_path / "bundle.zip"
    _build(output, checkpoint)
    with pytest.raises(ValueError, match="identity"):
        inspect_gallery_policy_bundle(output, expected_example_id="other-example")

    metadata = checkpoint.with_suffix(".zip.json")
    metadata.unlink()
    with pytest.raises(ValueError, match="checkpoint"):
        _build(tmp_path / "missing-metadata.zip", checkpoint)

    corrupt = tmp_path / "corrupt.zip"
    corrupt.write_bytes(b"not-a-checkpoint")
    corrupt.with_suffix(".zip.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="checkpoint"):
        _build(tmp_path / "corrupt-bundle.zip", corrupt)

    hostile = tmp_path / "hostile.zip"
    with zipfile.ZipFile(hostile, "w") as archive:
        archive.writestr("../escape", b"no")
    with pytest.raises(ValueError, match="layout|unsafe"):
        inspect_gallery_policy_bundle(hostile)

    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(output) as source, zipfile.ZipFile(tampered, "w") as target:
        for info in source.infolist():
            value = source.read(info.filename)
            target.writestr(info, b"changed" if info.filename == "README.md" else value)
    with pytest.raises(ValueError, match="digest"):
        inspect_gallery_policy_bundle(tampered)


def test_manifest_contains_compatible_loader_and_safe_run_identity(
    tmp_path: Path,
) -> None:
    manifest = _build(tmp_path / "bundle.zip", _checkpoint(tmp_path))
    encoded = json.dumps(manifest)
    assert manifest["compatibility"]["loader"] == "stable_baselines3.PPO.load"
    assert "sim2policy.policy_bundle evaluate" in manifest["compatibility"]["evaluation_command"]
    assert "tenant" not in encoded
    assert manifest["run_id"] == "gallery-run-safe"
    with pytest.raises(ValueError, match="run identity"):
        build_gallery_policy_bundle(
            tmp_path / "unsafe.zip",
            run_id="../unsafe",
            example_id="hopper-balance",
            backend="sb3",
            environment="Hopper-v5",
            checkpoint=_checkpoint(tmp_path),
            resolved_config={},
            evaluation={},
            versions={},
            runtime_image="registry.example/sim2policy:sb3-abcdef0",
        )


def test_gallery_bundle_enforces_member_archive_and_manifest_bounds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkpoint = _checkpoint(tmp_path)
    monkeypatch.setattr(policy_bundle, "MAX_MEMBER_BYTES", 4)
    with pytest.raises(ValueError, match="member size"):
        _build(tmp_path / "member-too-large.zip", checkpoint)

    monkeypatch.setattr(policy_bundle, "MAX_MEMBER_BYTES", 480 * 1024 * 1024)
    bundle = tmp_path / "bounded.zip"
    _build(bundle, checkpoint)
    monkeypatch.setattr(policy_bundle, "MAX_BUNDLE_BYTES", bundle.stat().st_size - 1)
    with pytest.raises(ValueError, match="bundle size"):
        inspect_gallery_policy_bundle(bundle)

    monkeypatch.setattr(policy_bundle, "MAX_BUNDLE_BYTES", 512 * 1024 * 1024)
    monkeypatch.setattr(policy_bundle, "MAX_MANIFEST_BYTES", 1)
    with pytest.raises(ValueError, match="manifest size"):
        inspect_gallery_policy_bundle(bundle)
