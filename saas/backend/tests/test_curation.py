"""The typed curated-evidence allowlist and its fail-closed normalizers."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from app.curation import (
    CANONICAL_ENVIRONMENTS,
    HISTORICAL_BASELINES,
    CurationError,
    curate,
    normalize_success,
    validate_run_identity,
)

DIGEST = "c" * 64


def _metrics(**overrides: Any) -> dict[str, Any]:
    base = {
        "environment": "Hopper-v5",
        "backend": "sb3",
        "matrix_digest": "a" * 64,
        "runtime_seconds": 613.2,
        "benchmark": {"estimated_cost": 0.12, "currency": "USD", "rate_date": "2026-07-26"},
        "success": {"met": True, "criterion": "mean_reward >= 1000"},
        "aggregate": {"mean_reward": 1234.5, "mean_episode_length": 900, "episodes": 20},
        "resolved_config": {
            "runtime_image": "registry.example/sim2policy-sb3@sha256:" + "b" * 64,
            "training": {"total_steps": 8_000_000},
            "hardware": {"platform": "cpu-d3", "preset": "8vcpu-32gb"},
        },
        "selected_checkpoint": {"effective_step": 5_000_000, "sha256": DIGEST},
        "seed_roles": {"selection": [101, 151, 211, 271, 331], "final": [0, 1, 2, 3, 4]},
        "ranking_explanation": {"kind": "mean_reward", "fields": ["mean_reward"]},
        "acceptance": {
            "hard": {"criteria": {"mean_reward": True}, "passed": True},
            "preferred": {"criteria": {"mean_reward": True}, "passed": True},
        },
        "versions": {"mujoco": "3.3.7"},
        "progression": [
            {"stage": "untrained", "selected": False, "checkpoint": {"effective_step": 0, "sha256": "d" * 64}},
            {"stage": "selected", "selected": True, "checkpoint": {"effective_step": 5_000_000, "sha256": DIGEST}},
            {"stage": "final-step", "selected": False, "regression": True,
             "checkpoint": {"effective_step": 8_000_000, "sha256": "e" * 64}},
        ],
    }
    result = copy.deepcopy(base)
    result.update(overrides)
    return result


# -- success normalization (6.3) --------------------------------------------


def test_success_normalizes_only_the_recognized_shape() -> None:
    assert normalize_success(_metrics())["met"] is True
    assert normalize_success({}) is None
    assert normalize_success({"success": True}) is None
    assert normalize_success({"success": {"met": "yes", "criterion": "x"}}) is None
    # An extra key means an unrecognized legacy shape, not a richer known one.
    assert normalize_success({"success": {"met": True, "criterion": "x", "extra": 1}}) is None


def test_success_contradicting_its_own_threshold_is_refused() -> None:
    """A run claiming success while its own numbers disagree is not evidence."""
    contradictory = _metrics(aggregate={"mean_reward": 12.0, "mean_episode_length": 5, "episodes": 20})
    assert normalize_success(contradictory) is None
    with pytest.raises(CurationError, match="normalized unambiguously"):
        curate("hopper-balance", contradictory)


def test_a_criterion_that_does_not_parse_is_accepted_without_cross_checking() -> None:
    locomotion = _metrics(
        environment="Go1JoystickFlatTerrain",
        backend="mjx",
        success={"met": True, "criterion": "velocity >= 0.5 and not fallen"},
        aggregate={"mean_velocity": 0.96, "mean_episode_length": 1000, "episodes": 20},
    )
    assert normalize_success(locomotion)["met"] is True
    assert curate("go1-walker", locomotion).primary_metric == pytest.approx(0.96)


# -- canonical identity (6.2) -----------------------------------------------


def test_every_example_has_an_exact_canonical_identity() -> None:
    assert CANONICAL_ENVIRONMENTS["g1-rough-terrain"] == "G1JoystickRoughTerrain"
    assert CANONICAL_ENVIRONMENTS["walker2d-stride"] == "Walker2d-v5"
    assert len(CANONICAL_ENVIRONMENTS) == 7


def test_a_run_may_not_choose_its_own_environment_identity() -> None:
    with pytest.raises(CurationError, match="canonical identity"):
        curate("hopper-balance", _metrics(environment="Hopper"))
    with pytest.raises(CurationError, match="canonical identity"):
        curate("hopper-balance", _metrics(environment="Walker2d-v5"))


def test_g1_records_both_curriculum_phases_but_scores_only_rough_terrain() -> None:
    metrics = _metrics(
        environment="G1JoystickRoughTerrain",
        backend="mjx",
        success={"met": True, "criterion": "velocity >= 0.4 and not fallen"},
        aggregate={"mean_velocity": 0.62, "mean_episode_length": 1000, "episodes": 20},
        phase_lineage={
            "flat": {"environment": "G1JoystickFlatTerrain", "effective_steps": 100_000_000, "outcome": "passed"},
            "rough": {"environment": "G1JoystickRoughTerrain", "effective_steps": 25_000_000, "outcome": "trained"},
        },
    )
    evidence = curate("g1-rough-terrain", metrics)
    assert [phase.environment for phase in evidence.phases] == [
        "G1JoystickFlatTerrain",
        "G1JoystickRoughTerrain",
    ]
    # Public success describes the final task only.
    assert evidence.environment == "G1JoystickRoughTerrain"


def test_an_unrecognized_phase_identity_is_refused() -> None:
    metrics = _metrics(
        environment="G1JoystickRoughTerrain",
        backend="mjx",
        success={"met": True, "criterion": "velocity >= 0.4 and not fallen"},
        aggregate={"mean_velocity": 0.62, "mean_episode_length": 1000, "episodes": 20},
        phase_lineage={"flat": {"environment": "SomeOtherRobotFlat"}},
    )
    with pytest.raises(CurationError, match="unrecognized environment"):
        curate("g1-rough-terrain", metrics)


# -- rejection rules (6.5) ---------------------------------------------------


def test_a_run_below_its_gate_is_diagnostic_evidence_not_a_published_example() -> None:
    failed = _metrics(
        aggregate={"mean_reward": 12.0, "mean_episode_length": 5, "episodes": 20},
        success={"met": False, "criterion": "mean_reward >= 1000"},
    )
    with pytest.raises(CurationError, match="did not meet its task gate"):
        curate("hopper-balance", failed)


def test_a_mutable_image_tag_is_refused() -> None:
    metrics = _metrics()
    metrics["resolved_config"]["runtime_image"] = "registry.example/sim2policy:sb3-runtime"
    with pytest.raises(CurationError, match="immutable digest"):
        curate("hopper-balance", metrics)


def test_missing_measured_evidence_is_refused() -> None:
    with pytest.raises(CurationError, match="measured cost"):
        curate("hopper-balance", _metrics(benchmark={"currency": "USD"}))
    with pytest.raises(CurationError, match="measured runtime"):
        curate("hopper-balance", _metrics(runtime_seconds=None))
    with pytest.raises(CurationError, match="matrix digest"):
        curate("hopper-balance", _metrics(matrix_digest="not-a-digest"))


def test_progression_must_link_to_the_selected_checkpoint() -> None:
    metrics = _metrics()
    metrics["progression"][1]["checkpoint"]["sha256"] = "9" * 64
    with pytest.raises(CurationError, match="link to the selected checkpoint"):
        curate("hopper-balance", metrics)


def test_progression_must_identify_a_selected_policy() -> None:
    metrics = _metrics()
    for entry in metrics["progression"]:
        entry["selected"] = False
    with pytest.raises(CurationError, match="identify the selected policy"):
        curate("hopper-balance", metrics)


def test_overlapping_seed_roles_are_refused() -> None:
    metrics = _metrics(seed_roles={"selection": [0, 101], "final": [0, 1]})
    with pytest.raises(CurationError, match="overlap"):
        curate("hopper-balance", metrics)


def test_tenant_shaped_and_placeholder_pins_are_refused() -> None:
    with pytest.raises(CurationError, match="tenant job space"):
        validate_run_identity("0123456789abcdef0123456789abcdef")
    with pytest.raises(CurationError, match="placeholder"):
        validate_run_identity("pending-curated-run-hopper-balance")
    with pytest.raises(CurationError, match="safe path segment"):
        validate_run_identity("gallery/../escape")


def test_a_pin_claimed_by_another_example_is_refused() -> None:
    pins = {"hopper-balance": "shared-run", "ant-explorer": "shared-run"}
    with pytest.raises(CurationError, match="claimed by another example"):
        validate_run_identity("shared-run", known_pins=pins, example_id="hopper-balance")


# -- promotion mode (6.5, 6.6) ----------------------------------------------


def test_promotion_additionally_requires_preferred_quality_and_cleanup_proof() -> None:
    metrics = _metrics()
    # Serving is fine; promotion is not, without cleanup proof.
    curate("hopper-balance", metrics, run_id="gallery-run")
    with pytest.raises(CurationError, match="cleanup proof"):
        curate("hopper-balance", metrics, run_id="gallery-run", promotion=True)

    evidence = curate(
        "hopper-balance", metrics, run_id="gallery-run", promotion=True, cleanup_state="PASS"
    )
    assert evidence.acceptance.preferred_passed is True

    marginal = _metrics()
    marginal["acceptance"]["preferred"]["passed"] = False
    with pytest.raises(CurationError, match="preferred quality target"):
        curate("hopper-balance", marginal, run_id="gallery-run", promotion=True, cleanup_state="PASS")


def test_historical_baselines_are_recorded_but_are_not_pins() -> None:
    """Reaching for a baseline instead of a fresh result must be a reviewed decision."""
    assert "go1-walker" in HISTORICAL_BASELINES
    assert HISTORICAL_BASELINES["go1-walker"]["label"] == "go1-mjx-quality-100m"
    # A baseline label is not a run identity and cannot be pinned by accident.
    for entry in HISTORICAL_BASELINES.values():
        assert "run_id" not in entry


# -- allowlist (6.1) ---------------------------------------------------------


def test_public_serialization_carries_only_allowlisted_fields() -> None:
    metrics = _metrics()
    metrics["tenant_id"] = "tenant-should-never-surface"
    metrics["job_id"] = "0123456789abcdef0123456789abcdef"
    metrics["storage"] = {"bucket": "private-bucket", "access_key": "AKIAEXAMPLE"}
    public = curate("hopper-balance", metrics).to_public_dict()
    encoded = repr(public)
    for forbidden in ("tenant_id", "job_id", "private-bucket", "AKIAEXAMPLE", "storage"):
        assert forbidden not in encoded
    assert public["selected_checkpoint"]["sha256"] == DIGEST
    assert public["measured_cost"] == pytest.approx(0.12)
    assert public["acceptance"]["hard_passed"] is True
