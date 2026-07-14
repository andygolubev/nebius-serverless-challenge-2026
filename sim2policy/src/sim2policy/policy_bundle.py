"""Deterministic, bounded policy bundles for server-owned gallery examples."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import stat
import zipfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from sim2policy.checkpoint import metadata_path

SCHEMA_VERSION = "gallery-policy-bundle-v1"
MAX_BUNDLE_BYTES = 512 * 1024 * 1024
MAX_MEMBER_BYTES = 480 * 1024 * 1024
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
_ZIP_TIMESTAMP = (2026, 1, 1, 0, 0, 0)

REQUIRED_MEMBERS = frozenset(
    {
        "README.md",
        "checkpoint/policy.zip",
        "checkpoint/policy.zip.json",
        "resolved-config.json",
        "evaluation/metrics.json",
        "runtime/versions.json",
    }
)


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _descriptor(path: str, source: Path | bytes, content_type: str) -> dict[str, Any]:
    if isinstance(source, Path):
        size = source.stat().st_size
        digest = _sha256_file(source)
    else:
        size = len(source)
        digest = hashlib.sha256(source).hexdigest()
    if not 0 < size <= MAX_MEMBER_BYTES:
        raise ValueError(f"policy bundle member size is invalid: {path}")
    return {
        "path": path,
        "content_type": content_type,
        "size_bytes": size,
        "sha256": digest,
    }


def _zip_info(path: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(path, date_time=_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o600) << 16
    return info


def _write_member(archive: zipfile.ZipFile, path: str, source: Path | bytes) -> None:
    with archive.open(_zip_info(path), "w", force_zip64=True) as destination:
        if isinstance(source, Path):
            with source.open("rb") as handle:
                shutil.copyfileobj(handle, destination, length=1024 * 1024)
        else:
            destination.write(source)


def build_gallery_policy_bundle(
    output: Path,
    *,
    run_id: str,
    example_id: str,
    backend: str,
    environment: str,
    checkpoint: Path,
    resolved_config: Mapping[str, Any],
    evaluation: Mapping[str, Any],
    versions: Mapping[str, Any],
    runtime_image: str,
) -> dict[str, Any]:
    """Write a byte-stable policy archive and validate it before returning."""
    checkpoint_metadata = metadata_path(checkpoint)
    if (
        not checkpoint.is_file()
        or checkpoint.suffix != ".zip"
        or not zipfile.is_zipfile(checkpoint)
        or not checkpoint_metadata.is_file()
    ):
        raise ValueError("gallery checkpoint must be a readable zip file")
    if (
        not run_id
        or len(run_id) > 128
        or any(
            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
            for character in run_id
        )
    ):
        raise ValueError("gallery run identity is invalid")
    if backend not in {"sb3", "mjx"}:
        raise ValueError("gallery policy backend is invalid")
    readme = (
        "# Sim2Policy verified example\n\n"
        f"Example: `{example_id}`  \nSimulator environment: `{environment}`  \n"
        f"Policy backend: `{backend}`\n\n"
        "SIMULATOR ONLY. This archive is not directly deployable to a physical robot. "
        "It contains the exact simulator checkpoint, resolved configuration, evaluation, "
        "and runtime versions needed to reproduce or inspect this training result.\n"
    ).encode()
    members: dict[str, tuple[Path | bytes, str]] = {
        "README.md": (readme, "text/markdown"),
        "checkpoint/policy.zip": (checkpoint, "application/zip"),
        "checkpoint/policy.zip.json": (checkpoint_metadata, "application/json"),
        "evaluation/metrics.json": (canonical_json(dict(evaluation)), "application/json"),
        "resolved-config.json": (canonical_json(dict(resolved_config)), "application/json"),
        "runtime/versions.json": (canonical_json(dict(versions)), "application/json"),
    }
    descriptors = [
        _descriptor(path, source, content_type)
        for path, (source, content_type) in sorted(members.items())
    ]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "kind": "verified-example-policy-bundle",
        "run_id": run_id,
        "example_id": example_id,
        "backend": backend,
        "environment": environment,
        "simulator_only": True,
        "runtime_image": runtime_image,
        "compatibility": {
            "loader": (
                "stable_baselines3.PPO.load"
                if backend == "sb3"
                else "brax.training.agents.ppo.checkpoint.load_policy"
            ),
            "evaluation_command": (
                "python -m sim2policy.policy_bundle evaluate policy-bundle.zip "
                "--run-id local-evaluation"
            ),
        },
        "members": descriptors,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", allowZip64=True) as archive:
        for path, (source, _) in sorted(members.items()):
            _write_member(archive, path, source)
        _write_member(archive, "manifest.json", canonical_json(manifest))
    inspect_gallery_policy_bundle(output, expected_example_id=example_id)
    return manifest


def _safe_member(name: str) -> bool:
    path = PurePosixPath(name)
    return (
        bool(name)
        and not path.is_absolute()
        and ".." not in path.parts
        and "." not in path.parts
        and not name.endswith("/")
    )


def inspect_gallery_policy_bundle(
    path: Path, *, expected_example_id: str | None = None
) -> dict[str, Any]:
    """Validate layout, bounds, provenance, member types, and every digest."""
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_BUNDLE_BYTES:
        raise ValueError("policy bundle size is invalid")
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = [item.filename for item in infos]
        if len(names) != len(set(names)):
            raise ValueError("policy bundle contains duplicate members")
        if set(names) != {*REQUIRED_MEMBERS, "manifest.json"}:
            raise ValueError("policy bundle layout is invalid")
        total_size = 0
        for info in infos:
            if not _safe_member(info.filename):
                raise ValueError("policy bundle contains an unsafe member")
            member_mode = (info.external_attr >> 16) & 0xFFFF
            if member_mode and not stat.S_ISREG(member_mode):
                raise ValueError("policy bundle contains an unsupported member type")
            if not 0 < info.file_size <= MAX_MEMBER_BYTES:
                raise ValueError("policy bundle member size is invalid")
            total_size += info.file_size
        if total_size > MAX_BUNDLE_BYTES:
            raise ValueError("policy bundle expanded size is invalid")
        manifest_info = archive.getinfo("manifest.json")
        if manifest_info.file_size > MAX_MANIFEST_BYTES:
            raise ValueError("policy bundle manifest size is invalid")
        manifest = json.loads(archive.read("manifest.json"))
        if not isinstance(manifest, dict):
            raise ValueError("policy bundle manifest is invalid")
        if (
            manifest.get("schema_version") != SCHEMA_VERSION
            or manifest.get("kind") != "verified-example-policy-bundle"
            or manifest.get("simulator_only") is not True
        ):
            raise ValueError("policy bundle provenance is invalid")
        if expected_example_id is not None and manifest.get("example_id") != expected_example_id:
            raise ValueError("policy bundle example identity is invalid")
        raw_descriptors = manifest.get("members")
        if not isinstance(raw_descriptors, list):
            raise ValueError("policy bundle manifest is incomplete")
        descriptors = {item.get("path"): item for item in raw_descriptors if isinstance(item, dict)}
        if set(descriptors) != set(REQUIRED_MEMBERS):
            raise ValueError("policy bundle manifest is incomplete")
        for name in REQUIRED_MEMBERS:
            descriptor = descriptors[name]
            if set(descriptor) != {"path", "content_type", "size_bytes", "sha256"}:
                raise ValueError("policy bundle member descriptor is invalid")
            digest = hashlib.sha256()
            size = 0
            with archive.open(name) as member:
                while chunk := member.read(1024 * 1024):
                    size += len(chunk)
                    digest.update(chunk)
            if descriptor["size_bytes"] != size or descriptor["sha256"] != digest.hexdigest():
                raise ValueError("policy bundle member digest is invalid")
        if not zipfile.is_zipfile(io.BytesIO(archive.read("checkpoint/policy.zip"))):
            raise ValueError("policy bundle checkpoint is invalid")
    return manifest


def evaluate_gallery_policy_bundle(path: Path, *, run_id: str, runs_root: Path) -> None:
    """Evaluate the bundled native checkpoint with its exact resolved config."""
    import tempfile

    from sim2policy.config import load_config, validate_run_id
    from sim2policy.evaluate import evaluate

    inspect_gallery_policy_bundle(path)
    validate_run_id(run_id)
    with tempfile.TemporaryDirectory(prefix="sim2policy-gallery-bundle-") as temporary:
        root = Path(temporary)
        with zipfile.ZipFile(path) as archive:
            checkpoint = root / "policy.zip"
            checkpoint.write_bytes(archive.read("checkpoint/policy.zip"))
            metadata_path(checkpoint).write_bytes(archive.read("checkpoint/policy.zip.json"))
            resolved = json.loads(archive.read("resolved-config.json"))
        resolved.pop("gallery_example_id", None)
        resolved.pop("runtime_image", None)
        config_path = root / "resolved-config.json"
        config_path.write_bytes(canonical_json(resolved))
        config = load_config(config_path)
        output = runs_root / run_id
        (output / "report").mkdir(parents=True, exist_ok=True)
        evaluate(checkpoint, config, run_id, output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect or evaluate a gallery policy bundle")
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("bundle", type=Path)
    inspect_parser.add_argument("--example-id")
    evaluate_parser = subparsers.add_parser("evaluate")
    evaluate_parser.add_argument("bundle", type=Path)
    evaluate_parser.add_argument("--run-id", required=True)
    evaluate_parser.add_argument("--runs-root", type=Path, default=Path("runs"))
    args = parser.parse_args()
    if args.command == "inspect":
        manifest = inspect_gallery_policy_bundle(args.bundle, expected_example_id=args.example_id)
        print(json.dumps(manifest, indent=2, sort_keys=True))
    else:
        evaluate_gallery_policy_bundle(args.bundle, run_id=args.run_id, runs_root=args.runs_root)


if __name__ == "__main__":
    main()
