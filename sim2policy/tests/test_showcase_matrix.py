from __future__ import annotations

# ruff: noqa: E501, I001

from pathlib import Path

import pytest

from sim2policy.showcase_matrix import MatrixError, load_matrix


MATRIX = Path(__file__).parents[1] / "configs" / "showcase_training_matrix.yaml"


def test_reviewed_matrix_is_normalized_and_stable() -> None:
    first = load_matrix(MATRIX)
    second = load_matrix(MATRIX)
    assert first.digest == second.digest
    assert tuple(first.examples) == ("reacher", "halfcheetah", "ant", "hopper", "walker2d", "go1", "g1")
    assert first.card("g1")["base_steps"] == 450_000_000
    recovery = first.card("g1")["curriculum"]
    assert recovery["flat_environment"] == "G1ForwardFlatTerrain"
    assert recovery["rough_environment"] == "G1ForwardRoughTerrain"
    assert recovery["flat_command"] == [1.0, 0.0, 0.0]
    assert recovery["rough_command"] == [0.8, 0.0, 0.0]
    assert recovery["flat_effective_steps"] == 199_229_440
    assert recovery["full"]["rough_effective_steps"] == 250_511_360
    assert recovery["authorization"] == {
        "mode": "user_reviewed_rough_08_full_v2",
        "campaign_id": "gallery-g1-rough08-full-20260803-01",
        "allowed_jobs": 1,
        "retries_allowed": 0,
        "extensions_allowed": False,
        "runtime_overrides_allowed": False,
        "superseded_sweep_run_id": "sweep-g1-c1a522b-20260802-01",
        "superseded_sweep_job_id": "aijob-e00c8fwyh15gy7qggk",
        "superseded_result_campaign_id": "gallery-g1-direct-full-20260803-01",
        "superseded_result_job_id": "aijob-e00pc60w55v89z6t5v",
        "pilot_required": False,
    }
    assert (
        recovery["diagnostic"]["source_run_id"]
        == "showcase-gallery-g1-20260801-16-g1-s0-flat"
    )
    assert recovery["pilot"]["effective_steps"] == 46_202_880


@pytest.mark.parametrize(
    ("needle", "replacement"),
    [
        ("preemptible: false", "preemptible: true"),
        ("sb3-{git_sha}", "latest"),
        ("seeds: [101, 151, 211, 271, 331]", "seeds: [0, 1, 2, 3, 4]"),
        (
            "source_run_id: showcase-gallery-g1-20260801-16-g1-s0-flat",
            "source_run_id: gallery-g1-20260801-16-flat",
        ),
        ("mode: user_reviewed_rough_08_full_v2", "mode: generic-direct-full"),
        ("campaign_id: gallery-g1-rough08-full-20260803-01", "campaign_id: another-campaign"),
        ("allowed_jobs: 1", "allowed_jobs: 2"),
        ("retries_allowed: 0", "retries_allowed: 1"),
        ("rough_effective_steps: 250511360", "rough_effective_steps: 250000000"),
        ("base_steps: 1000000", "base_steps: 0"),
    ],
)
def test_matrix_rejects_reviewed_contract_mutation(tmp_path: Path, needle: str, replacement: str) -> None:
    path = tmp_path / "matrix.yaml"
    path.write_text(MATRIX.read_text().replace(needle, replacement, 1))
    with pytest.raises(MatrixError):
        load_matrix(path)
