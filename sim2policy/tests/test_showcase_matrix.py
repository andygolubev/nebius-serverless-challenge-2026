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
    assert recovery["flat_effective_steps"] == 149_422_080
    assert recovery["pilot"]["effective_steps"] == 46_202_880


@pytest.mark.parametrize(
    ("needle", "replacement"),
    [
        ("preemptible: false", "preemptible: true"),
        ("sb3-{git_sha}", "latest"),
        ("seeds: [101, 151, 211, 271, 331]", "seeds: [0, 1, 2, 3, 4]"),
        ("base_steps: 1000000", "base_steps: 0"),
    ],
)
def test_matrix_rejects_reviewed_contract_mutation(tmp_path: Path, needle: str, replacement: str) -> None:
    path = tmp_path / "matrix.yaml"
    path.write_text(MATRIX.read_text().replace(needle, replacement, 1))
    with pytest.raises(MatrixError):
        load_matrix(path)
