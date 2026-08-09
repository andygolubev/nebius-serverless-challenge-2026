"""Deterministic, seed-isolated checkpoint selection for curated runs."""

# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean, pstdev
from typing import Any, Literal

from sim2policy.checkpoint import CheckpointInventory, checkpoint_inventory
from sim2policy.config import RunConfig


class SelectionError(ValueError):
    pass


Role = Literal["selection", "final"]


@dataclass(frozen=True)
class EvaluationEvidence:
    inventory: CheckpointInventory
    role: Role
    seeds: tuple[int, ...]
    episodes: tuple[dict[str, Any], ...]
    runtime_seconds: float
    criterion: str

    def aggregate(self) -> dict[str, float | int]:
        if not self.episodes:
            raise SelectionError("checkpoint evaluation contains no episodes")
        rewards = [float(item["reward"]) for item in self.episodes]
        lengths = [float(item["length"]) for item in self.episodes]
        velocities = [float(item.get("mean_velocity", 0.0)) for item in self.episodes]
        no_fall = [not bool(item.get("fell", False)) for item in self.episodes]
        return {
            "mean_reward": fmean(rewards),
            "std_reward": pstdev(rewards),
            "mean_episode_length": fmean(lengths),
            "mean_velocity": fmean(velocities),
            "min_velocity": min(velocities),
            "no_fall_count": sum(no_fall),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint": self.inventory.to_dict(),
            "role": self.role,
            "seeds": list(self.seeds),
            "episodes": list(self.episodes),
            "aggregate": self.aggregate(),
            "criterion": self.criterion,
            "runtime_seconds": self.runtime_seconds,
        }


def validate_seed_roles(selection_seeds: Iterable[int], final_seeds: Iterable[int]) -> None:
    selection = tuple(selection_seeds)
    final = tuple(final_seeds)
    if not selection or not final or set(selection) & set(final):
        raise SelectionError("selection and final seeds must be nonempty and disjoint")


def evidence_for_selection(
    inventory: CheckpointInventory,
    *,
    selection_seeds: Iterable[int],
    final_seeds: Iterable[int],
    episodes: Iterable[dict[str, Any]],
    runtime_seconds: float,
    criterion: str,
) -> EvaluationEvidence:
    seeds = tuple(selection_seeds)
    validate_seed_roles(seeds, final_seeds)
    values = tuple(dict(item) for item in episodes)
    if any(item.get("seed") not in seeds for item in values):
        raise SelectionError("selection evidence includes a final or undeclared seed")
    return EvaluationEvidence(inventory, "selection", seeds, values, runtime_seconds, criterion)


def evaluate_candidates(
    checkpoints: Iterable[Path],
    config: RunConfig,
    *,
    run_lineage: str,
    selection_seeds: Iterable[int],
    final_seeds: Iterable[int],
    episodes_per_seed: int,
    phase: str = "training",
) -> list[EvaluationEvidence]:
    """Evaluate each retained candidate on only the disjoint selection schedule."""
    selected = tuple(selection_seeds)
    final = tuple(final_seeds)
    validate_seed_roles(selected, final)
    if episodes_per_seed <= 0:
        raise SelectionError("selection episode count must be positive")
    schedule = [seed for seed in selected for _ in range(episodes_per_seed)]
    if config.backend == "sb3":
        from sim2policy.evaluate import evaluate_sb3

        evaluator = evaluate_sb3
    else:
        from sim2policy.train_mjx import evaluate_mjx

        evaluator = evaluate_mjx
    result: list[EvaluationEvidence] = []
    for checkpoint in checkpoints:
        episodes, runtime = evaluator(checkpoint, config, seeds=schedule)
        result.append(
            evidence_for_selection(
                checkpoint_inventory(checkpoint, config, run_lineage=run_lineage, phase=phase),
                selection_seeds=selected,
                final_seeds=final,
                episodes=episodes,
                runtime_seconds=runtime,
                criterion=config.success.kind,
            )
        )
    return result


def evaluate_final_checkpoint(
    checkpoint: Path,
    config: RunConfig,
    *,
    run_lineage: str,
    selection_seeds: Iterable[int],
    final_seeds: Iterable[int],
    episodes_per_seed: int,
    phase: str = "selected",
) -> EvaluationEvidence:
    """Evaluate exactly one selected checkpoint on reserved final acceptance seeds."""
    selected = tuple(selection_seeds)
    final = tuple(final_seeds)
    validate_seed_roles(selected, final)
    if episodes_per_seed <= 0:
        raise SelectionError("final episode count must be positive")
    schedule = [seed for seed in final for _ in range(episodes_per_seed)]
    if config.backend == "sb3":
        from sim2policy.evaluate import evaluate_sb3

        episodes, runtime = evaluate_sb3(checkpoint, config, seeds=schedule)
    else:
        from sim2policy.train_mjx import evaluate_mjx

        episodes, runtime = evaluate_mjx(checkpoint, config, seeds=schedule)
    values = tuple(dict(item) for item in episodes)
    if any(item.get("seed") not in final for item in values):
        raise SelectionError("final evidence includes an undeclared seed")
    return EvaluationEvidence(
        checkpoint_inventory(checkpoint, config, run_lineage=run_lineage, phase=phase),
        "final",
        final,
        values,
        runtime,
        config.success.kind,
    )


RANKING_FIELDS: dict[str, tuple[str, ...]] = {
    "mean_reward": ("mean_reward", "mean_episode_length", "earlier_checkpoint"),
    "locomotion": (
        "no_fall_count",
        "min_velocity",
        "mean_episode_length",
        "mean_velocity",
        "mean_reward",
        "earlier_checkpoint",
    ),
}


def rank_key(evidence: EvaluationEvidence, kind: str) -> tuple[float, ...]:
    aggregate = evidence.aggregate()
    # The final component is negative effective step: for all other ties the
    # earlier checkpoint wins, so final-step status confers no preference.
    earlier = -float(evidence.inventory.effective_step)
    if kind == "mean_reward":
        return (
            float(aggregate["mean_reward"]),
            float(aggregate["mean_episode_length"]),
            earlier,
        )
    if kind == "locomotion":
        return (
            float(aggregate["no_fall_count"]),
            float(aggregate["min_velocity"]),
            float(aggregate["mean_episode_length"]),
            float(aggregate["mean_velocity"]),
            float(aggregate["mean_reward"]),
            earlier,
        )
    raise SelectionError("unknown ranking kind")


def select_checkpoint(candidates: Iterable[EvaluationEvidence], *, kind: str) -> EvaluationEvidence:
    values = tuple(candidates)
    if not values:
        raise SelectionError("no evaluated checkpoint candidates")
    if any(item.role != "selection" for item in values):
        raise SelectionError("only selection evidence may influence checkpoint selection")
    return max(values, key=lambda item: rank_key(item, kind))


def explain_ranking(
    candidates: Iterable[EvaluationEvidence], selected: EvaluationEvidence, *, kind: str
) -> dict[str, Any]:
    """Structured, honest evidence for why `selected` won checkpoint selection."""
    if kind not in RANKING_FIELDS:
        raise SelectionError("unknown ranking kind")
    ordered = sorted(candidates, key=lambda item: rank_key(item, kind), reverse=True)
    if not ordered or ordered[0] is not selected:
        raise SelectionError("ranking explanation must describe the actual winning candidate")
    runner_up = ordered[1] if len(ordered) > 1 else None

    def _describe(evidence: EvaluationEvidence) -> dict[str, Any]:
        return {
            "effective_step": evidence.inventory.effective_step,
            "sha256": evidence.inventory.sha256,
            "values": list(rank_key(evidence, kind)),
        }

    return {
        "kind": kind,
        "fields": list(RANKING_FIELDS[kind]),
        "candidate_count": len(ordered),
        "selected": _describe(selected),
        "runner_up": None if runner_up is None else _describe(runner_up),
    }


def acceptance_from_aggregate(
    aggregate: Mapping[str, Any], episode_count: int, criteria: Mapping[str, Any]
) -> dict[str, bool]:
    results: dict[str, bool] = {}
    for name, target in criteria.items():
        if name == "episodes":
            results[name] = episode_count == int(target)
        elif name == "required_horizons":
            # Evidence is sampled, not bit-reproducible, so acceptance states a
            # tolerance instead of demanding every sampled episode be perfect.
            results[name] = int(aggregate["no_fall_count"]) >= int(target)
        elif name == "mean_reward":
            results[name] = float(aggregate["mean_reward"]) >= float(target)
        elif name == "mean_episode_length":
            results[name] = float(aggregate["mean_episode_length"]) >= float(target)
        elif name == "min_velocity":
            results[name] = float(aggregate["min_velocity"]) >= float(target)
        elif name == "mean_velocity":
            results[name] = float(aggregate["mean_velocity"]) >= float(target)
        else:
            raise SelectionError(f"unknown acceptance criterion: {name}")
    return results


def acceptance_result(evidence: EvaluationEvidence, criteria: dict[str, Any]) -> dict[str, bool]:
    if evidence.role != "final":
        raise SelectionError("acceptance requires final-seed evidence")
    return acceptance_from_aggregate(evidence.aggregate(), len(evidence.episodes), criteria)
