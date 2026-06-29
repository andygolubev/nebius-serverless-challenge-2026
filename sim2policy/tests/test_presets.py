from __future__ import annotations

from pathlib import Path

import pytest

from sim2policy.api.presets import PresetCatalog, PresetError, default_catalog_path

ROOT = Path(__file__).parents[1]
CATALOG = ROOT / "configs" / "training_presets.yaml"


def catalog() -> PresetCatalog:
    return PresetCatalog.load(CATALOG)


def test_default_catalog_path_points_at_repo() -> None:
    assert default_catalog_path() == CATALOG


def test_enabled_presets_exclude_feature_flagged() -> None:
    names = catalog().names()
    assert "halfcheetah-demo" in names
    assert "ant-demo" in names
    assert "ant-quality" in names
    assert "go1-mjx-demo" not in names  # feature-flagged off


def test_disabled_preset_is_rejected() -> None:
    with pytest.raises(PresetError):
        catalog().get("go1-mjx-demo")


def test_unknown_preset_is_rejected() -> None:
    with pytest.raises(PresetError):
        catalog().resolve("not-a-preset")


def test_resolution_produces_run_config() -> None:
    resolved = catalog().resolve("ant-demo", {"seed": 7})
    assert resolved.backend == "sb3"
    assert resolved.config.backend == "sb3"
    assert resolved.config.environment == "Ant-v5"
    assert resolved.config.seed == 7
    assert resolved.config_path == "configs/ant_sb3.yaml"
    assert resolved.max_duration == "3h"


def test_safe_param_defaults_applied() -> None:
    resolved = catalog().resolve("ant-demo")
    assert resolved.safe_params["seed"] == 0
    assert resolved.safe_params["render_progress_video"] is True


def test_out_of_range_seed_rejected() -> None:
    with pytest.raises(PresetError):
        catalog().resolve("ant-demo", {"seed": -1})


def test_unknown_safe_param_rejected() -> None:
    with pytest.raises(PresetError):
        catalog().resolve("ant-demo", {"environment": "Humanoid-v5"})


def test_limits_cap_total_steps(tmp_path: Path) -> None:
    # Build a catalog whose override exceeds the declared max, and confirm capping.
    custom = tmp_path / "configs"
    custom.mkdir()
    (custom / "training_presets.yaml").write_text(
        """
version: 1
presets:
  capped:
    backend: sb3
    environment: Ant-v5
    base_config: configs/ant_sb3.yaml
    overrides:
      training.total_steps: 9000000
    limits:
      max_total_steps: 1000000
      max_duration: "1h"
    safe_params:
      seed: {type: int, min: 0, max: 100, default: 0}
""",
        encoding="utf-8",
    )
    # base config referenced relative to project root (tmp_path).
    (custom / "ant_sb3.yaml").write_text(
        (ROOT / "configs" / "ant_sb3.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    resolved = PresetCatalog.load(custom / "training_presets.yaml").resolve("capped")
    assert resolved.config.training.total_steps == 1000000


def test_malformed_catalog_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "presets.yaml"
    bad.write_text("version: 1\n", encoding="utf-8")  # no presets mapping
    with pytest.raises(PresetError):
        PresetCatalog.load(bad)
