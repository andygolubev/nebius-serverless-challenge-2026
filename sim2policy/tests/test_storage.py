from __future__ import annotations

import io
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from sim2policy.checkpoint import CheckpointError, checkpoint_path, write_checkpoint_metadata
from sim2policy.config import StorageConfig, load_config
from sim2policy.storage import ArtifactStore, StorageError

ROOT = Path(__file__).parents[1]


class FakeS3:
    def __init__(self, failures: int = 0) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.metadata: dict[tuple[str, str], dict[str, str]] = {}
        self.events: list[tuple[str, str]] = []
        self.failures = failures

    def _fail(self) -> None:
        if self.failures:
            self.failures -= 1
            raise ConnectionError("temporary")

    def upload_file(
        self,
        filename: str,
        bucket: str,
        key: str,
        *,
        ExtraArgs: dict[str, Any] | None = None,
    ) -> None:
        self._fail()
        self.events.append(("upload", key))
        self.objects[(bucket, key)] = Path(filename).read_bytes()
        self.metadata[(bucket, key)] = dict((ExtraArgs or {}).get("Metadata", {}))

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, **_: Any) -> None:
        self._fail()
        self.events.append(("put", Key))
        self.objects[(Bucket, Key)] = Body

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    def download_file(self, bucket: str, key: str, filename: str) -> None:
        Path(filename).write_bytes(self.objects[(bucket, key)])

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        return {"ContentLength": len(self.objects[(Bucket, Key)])}

    def list_objects_v2(self, *, Bucket: str, Prefix: str, **_: Any) -> dict[str, Any]:
        keys = sorted(
            key for bucket, key in self.objects if bucket == Bucket and key.startswith(Prefix)
        )
        return {"Contents": [{"Key": key} for key in keys], "IsTruncated": False}


def s3_config(retries: int = 2) -> StorageConfig:
    return StorageConfig(mode="s3", bucket="test", prefix="sim2policy", retries=retries)


def make_checkpoint(run_root: Path) -> Path:
    config = load_config(ROOT / "configs/smoke_sb3.yaml")
    checkpoint = checkpoint_path(run_root / "checkpoints", "step", 128)
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_bytes(b"policy")
    write_checkpoint_metadata(checkpoint, config, 128)
    return checkpoint


def test_local_mode_has_no_client(tmp_path: Path) -> None:
    store = ArtifactStore(StorageConfig(), "run-1")
    assert not store.enabled
    assert store.sync_tree(tmp_path) == []


def test_key_mapping_rejects_traversal() -> None:
    store = ArtifactStore(s3_config(), "run-1", client=FakeS3())
    with pytest.raises(StorageError, match="unsafe"):
        store.key_for("../secret")


def test_checkpoint_is_uploaded_before_manifest(tmp_path: Path) -> None:
    client = FakeS3()
    store = ArtifactStore(s3_config(), "run-1", client=client)
    manifest = store.publish_checkpoint(make_checkpoint(tmp_path), tmp_path)
    assert manifest["step"] == 128
    assert [event[0] for event in client.events] == ["upload", "upload", "put"]


def test_runtime_sync_uploads_tensorboard_but_not_checkpoints(tmp_path: Path) -> None:
    client = FakeS3()
    store = ArtifactStore(s3_config(), "run-1", client=client)
    checkpoint = make_checkpoint(tmp_path)
    event = tmp_path / "tensorboard" / "events.out.tfevents.test"
    event.parent.mkdir()
    event.write_bytes(b"events")

    uploaded = store.sync_runtime_artifacts(tmp_path)

    assert uploaded == ["sim2policy/run-1/tensorboard/events.out.tfevents.test"]
    assert ("test", uploaded[0]) in client.objects
    assert all(checkpoint.name not in key for _, key in client.events)


def test_download_tree_restores_selected_run_subtrees(tmp_path: Path) -> None:
    client = FakeS3()
    store = ArtifactStore(s3_config(), "run-1", client=client)
    client.objects[("test", store.key_for("checkpoints/final.zip"))] = b"policy"
    client.objects[("test", store.key_for("tensorboard/events"))] = b"events"
    client.objects[("test", store.key_for("report/ignored.json"))] = b"{}"

    restored = store.download_tree(tmp_path, ("checkpoints", "tensorboard"))

    assert [path.relative_to(tmp_path).as_posix() for path in restored] == [
        "checkpoints/final.zip",
        "tensorboard/events",
    ]
    assert (tmp_path / "checkpoints/final.zip").read_bytes() == b"policy"


def test_retry_and_degraded_state(tmp_path: Path) -> None:
    artifact = tmp_path / "report" / "metrics.json"
    artifact.parent.mkdir()
    artifact.write_text("{}")
    client = FakeS3(failures=1)
    store = ArtifactStore(s3_config(), "run-1", client=client, sleep=lambda _: None)
    assert store.upload_file(artifact, "report/metrics.json").endswith("report/metrics.json")
    assert not store.degraded

    broken = ArtifactStore(
        s3_config(retries=1),
        "run-1",
        client=FakeS3(failures=3),
        sleep=lambda _: None,
    )
    with pytest.raises(StorageError, match="2 attempt"):
        broken.upload_file(artifact, "report/metrics.json")
    assert broken.degraded


def test_publish_and_resume_round_trip(tmp_path: Path) -> None:
    config = load_config(ROOT / "configs/smoke_sb3.yaml")
    client = FakeS3()
    store = ArtifactStore(s3_config(), "run-1", client=client)
    original = make_checkpoint(tmp_path / "source")
    store.publish_checkpoint(original, tmp_path / "source")
    restored = store.resume_latest(tmp_path / "restored", config)
    assert restored.read_bytes() == original.read_bytes()
    incompatible = replace(config, environment="Other-v1")
    with pytest.raises(CheckpointError, match="incompatible"):
        store.resume_latest(tmp_path / "wrong", incompatible)
    transitioned = store.resume_latest(
        tmp_path / "transitioned",
        incompatible,
        allowed_source_environment=config.environment,
    )
    assert transitioned.read_bytes() == original.read_bytes()


def test_interrupted_checkpoint_upload_keeps_old_manifest(tmp_path: Path) -> None:
    client = FakeS3()
    store = ArtifactStore(s3_config(retries=0), "run-1", client=client, sleep=lambda _: None)
    first = make_checkpoint(tmp_path / "first")
    store.publish_checkpoint(first, tmp_path / "first")
    latest_key = store.key_for("checkpoints/latest.json")
    old_manifest = json.loads(client.objects[("test", latest_key)])

    second_root = tmp_path / "second"
    second = make_checkpoint(second_root)
    second.write_bytes(b"different")
    write_checkpoint_metadata(second, load_config(ROOT / "configs/smoke_sb3.yaml"), 128)
    client.failures = 1
    with pytest.raises(StorageError):
        store.publish_checkpoint(second, second_root)
    assert json.loads(client.objects[("test", latest_key)]) == old_manifest


def test_head_object_optional_reports_size_and_absence(tmp_path: Path) -> None:
    """Campaign verification proves objects exist without downloading them."""
    client = FakeS3()
    store = ArtifactStore(s3_config(), "run-1", client=client, sleep=lambda _: None)
    store.put_json("report/metrics.json", {"a": 1})

    head = store.head_object_optional("report/metrics.json")
    assert head is not None
    assert head["size_bytes"] == len(client.objects[("test", store.key_for("report/metrics.json"))])
    assert store.head_object_optional("report/absent.json") is None
