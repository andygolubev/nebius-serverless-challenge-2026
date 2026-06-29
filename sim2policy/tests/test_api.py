from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sim2policy.api.app import Settings, create_app
from sim2policy.api.orchestration import MockBackend
from sim2policy.config import StorageConfig

ROOT = Path(__file__).parents[1]
CATALOG = ROOT / "configs" / "training_presets.yaml"


def make_client(tmp_path: Path, *, token: str | None = None) -> TestClient:
    settings = Settings(
        backend_name="mock",
        catalog_path=CATALOG,
        runs_root=tmp_path,
        demo_token=token,
        storage=StorageConfig(mode="local"),
    )
    # background=False so a run completes before the request returns -> deterministic.
    app = create_app(settings, backend=MockBackend(background=False))
    return TestClient(app)


def test_health_ok(tmp_path: Path) -> None:
    response = make_client(tmp_path).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "backend": "mock"}


def test_training_options_excludes_disabled(tmp_path: Path) -> None:
    response = make_client(tmp_path).get("/training-options")
    assert response.status_code == 200
    names = {preset["name"] for preset in response.json()["presets"]}
    assert {"halfcheetah-demo", "ant-demo", "ant-quality"} <= names
    assert "go1-mjx-demo" not in names


def test_train_and_status_and_artifacts_flow(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    started = client.post("/train", json={"preset": "ant-demo", "seed": 42})
    assert started.status_code == 202
    body = started.json()
    run_id = body["run_id"]
    assert run_id.startswith("ant-demo-")
    assert body["status"] == "queued"
    assert body["status_url"] == f"/runs/{run_id}"

    status = client.get(f"/runs/{run_id}")
    assert status.status_code == 200
    assert status.json()["status"] == "completed"  # mock ran synchronously
    assert status.json()["preset"] == "ant-demo"

    artifacts = client.get(f"/runs/{run_id}/artifacts").json()
    assert artifacts["status"] == "completed"
    assert "final_policy" in artifacts["artifacts"]
    assert "progression_montage" in artifacts["artifacts"]


def test_unknown_preset_rejected(tmp_path: Path) -> None:
    response = make_client(tmp_path).post("/train", json={"preset": "evil-preset"})
    assert response.status_code == 422


def test_extra_fields_rejected(tmp_path: Path) -> None:
    response = make_client(tmp_path).post(
        "/train",
        json={"preset": "ant-demo", "image": "evil:latest", "command": "rm -rf /"},
    )
    assert response.status_code == 422


def test_out_of_range_seed_rejected(tmp_path: Path) -> None:
    response = make_client(tmp_path).post("/train", json={"preset": "ant-demo", "seed": -5})
    assert response.status_code == 422


def test_unknown_run_returns_404(tmp_path: Path) -> None:
    response = make_client(tmp_path).get("/runs/ant-demo-20260629-missing")
    assert response.status_code == 404


def test_unsafe_run_id_rejected(tmp_path: Path) -> None:
    response = make_client(tmp_path).get("/runs/..%2f..%2fetc")
    assert response.status_code in {400, 404}


def test_demo_token_gate(tmp_path: Path) -> None:
    client = make_client(tmp_path, token="s3cret")
    # health is always open
    assert client.get("/health").status_code == 200
    # protected without token
    assert client.get("/training-options").status_code == 401
    # protected with token
    ok = client.get("/training-options", headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200
