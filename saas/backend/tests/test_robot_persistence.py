"""Durability, atomic quotas, idempotency, and tenant scoping for custom assets."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor

from app.models import CatalogObject, RobotAsset, RobotSetup, ValidationSummary
from app.store import QuotaExceeded, RobotStore


def _summary() -> ValidationSummary:
    return ValidationSummary(
        body_count=2,
        joint_count=2,
        actuator_count=1,
        geom_count=2,
        joint_names=["free", "hinge"],
        actuator_names=["motor"],
    )


def _robot(index: int, tenant: str = "a@example.com", digest: str | None = None) -> RobotAsset:
    return RobotAsset(
        id=f"robot-{tenant}-{index}",
        tenant_id=tenant,
        name=f"Robot {index}",
        filename=f"robot-{index}.xml",
        robot_type="quadruped",
        digest=digest or f"{index:064x}",
        validation=_summary(),
        validated_at="2026-07-13T00:00:00+00:00",
    )


def _setup(index: int, tenant: str = "a@example.com") -> RobotSetup:
    return RobotSetup(
        id=f"setup-{tenant}-{index}",
        tenant_id=tenant,
        name=f"Setup {index}",
        robot_id="robot-a@example.com-0",
        robot_name="Robot 0",
        robot_type="quadruped",
        task_template_id="walk-forward",
        scene_preset_id="flat-arena",
        objects=[CatalogObject(object_type="box", x=index / 10, y=0, z=0, yaw_degrees=0, width=1, depth=1, height=0.3, source="custom")],
        digest=f"{index:064x}",
        created_at="2026-07-13T00:00:00+00:00",
    )


def test_existing_database_migrates_and_assets_survive_reopen(tmp_path):
    path = str(tmp_path / "old.db")
    connection = sqlite3.connect(path)
    connection.executescript(
        """CREATE TABLE jobs (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, data TEXT NOT NULL);
        INSERT INTO jobs VALUES ('old-job', 'a@example.com', '{}');"""
    )
    connection.close()

    store = RobotStore(path)
    robot, created = store.create_robot(_robot(0), "<mujoco/>")
    assert created
    setup, created = store.create_setup(_setup(0))
    assert created

    reopened = RobotStore(path)
    assert reopened.get_robot("a@example.com", robot.id) == robot
    assert reopened.get_robot_content("a@example.com", robot.id) == (robot, "<mujoco/>")
    assert reopened.get_setup("a@example.com", setup.id) == setup
    assert sqlite3.connect(path).execute("SELECT id FROM jobs").fetchone() == ("old-job",)


def test_duplicate_content_is_idempotent_and_soft_delete_allows_new_version(tmp_path):
    store = RobotStore(str(tmp_path / "saas.db"))
    original, created = store.create_robot(_robot(1), "first")
    assert created
    duplicate, created = store.create_robot(_robot(2, digest=original.digest), "second")
    assert not created
    assert duplicate.id == original.id
    assert store.get_robot_content("a@example.com", original.id) == (original, "first")

    assert store.delete_robot("a@example.com", original.id)
    replacement, created = store.create_robot(_robot(3, digest=original.digest), "third")
    assert created and replacement.id != original.id
    assert store.get_robot("a@example.com", original.id) is None


def test_robot_quota_is_atomic_across_store_instances(tmp_path):
    path = str(tmp_path / "saas.db")
    first = RobotStore(path)
    second = RobotStore(path)
    for index in range(19):
        first.create_robot(_robot(index), str(index))

    def create(store: RobotStore, index: int) -> str:
        try:
            store.create_robot(_robot(index), str(index))
            return "created"
        except QuotaExceeded:
            return "quota"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda args: create(*args), [(first, 100), (second, 101)]))
    assert sorted(results) == ["created", "quota"]
    assert len(first.list_robots("a@example.com")) == 20


def test_setup_quota_is_atomic_and_preserves_existing_rows(tmp_path):
    path = str(tmp_path / "saas.db")
    first = RobotStore(path)
    second = RobotStore(path)
    for index in range(49):
        first.create_setup(_setup(index))

    def create(store: RobotStore, index: int) -> str:
        try:
            store.create_setup(_setup(index))
            return "created"
        except QuotaExceeded:
            return "quota"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda args: create(*args), [(first, 100), (second, 101)]))
    assert sorted(results) == ["created", "quota"]
    assert len(first.list_setups("a@example.com")) == 50


def test_robot_and_setup_reads_and_deletes_are_tenant_scoped(tmp_path):
    store = RobotStore(str(tmp_path / "saas.db"))
    robot, _ = store.create_robot(_robot(0), "xml")
    setup, _ = store.create_setup(_setup(0))
    assert store.get_robot("b@example.com", robot.id) is None
    assert store.get_robot_content("b@example.com", robot.id) is None
    assert not store.delete_robot("b@example.com", robot.id)
    assert store.get_setup("b@example.com", setup.id) is None
    assert not store.delete_setup("b@example.com", setup.id)
    assert store.get_robot("a@example.com", robot.id) is not None
    assert store.get_setup("a@example.com", setup.id) is not None
