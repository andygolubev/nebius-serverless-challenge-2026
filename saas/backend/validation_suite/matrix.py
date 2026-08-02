"""Canonical, catalog-derived scenario inventory for the My Robots workflow.

The catalog supplies values and numeric bounds. Independent constants below assert the
accepted public contract so a server bug cannot silently redefine the expected matrix.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence, TypeVar

from app import environment_catalog

EXPECTED_ROBOT_TYPES = ("quadruped", "biped")
EXPECTED_COMPATIBILITY = {
    "quadruped": ("stand-balance", "walk-forward", "recover-from-fall"),
    "biped": ("stand-balance", "walk-forward"),
}
EXPECTED_SCENE_OBJECT_COUNTS = {
    "flat-arena": 0,
    "ramp-course": 1,
    "hurdle-course": 3,
    "step-course": 3,
}
EXPECTED_OBJECT_TYPES = ("box", "ramp", "hurdle", "step")
EXPECTED_PARAMETER_NAMES = (
    "x",
    "y",
    "z",
    "yaw_degrees",
    "width",
    "depth",
    "height",
)
EXPECTED_ELIGIBLE_TASKS = frozenset({"stand-balance", "walk-forward"})
EXPECTED_ELIGIBLE_SCENES = frozenset({"flat-arena", "ramp-course"})
EXPECTED_MAX_OBJECTS = 6

# Every visible control/state is mapped to a durable scenario family. Frontend tests
# assert the same keys so a new control cannot land without coverage in both layers.
CONTROL_INVENTORY: Mapping[str, tuple[str, ...]] = {
    "sample-download": ("browser:sample-download",),
    "upload-name": ("component:upload-required", "browser:upload-happy"),
    "upload-robot-type": ("component:upload-types", "browser:upload-happy"),
    "upload-file": ("component:upload-required", "browser:upload-happy"),
    "upload-submit": ("component:upload-errors", "browser:upload-happy"),
    "upload-errors": ("component:upload-errors",),
    "model-statistics": ("component:model-card", "browser:upload-happy"),
    "model-digest": ("component:model-card", "browser:upload-happy"),
    "model-download": ("component:model-download", "browser:model-download"),
    "model-delete-cancel": ("component:model-delete", "browser:model-delete"),
    "build-environment": ("component:builder-open", "browser:builder-pairwise"),
    "builder-close": ("component:builder-close",),
    "setup-name": ("component:builder-name", "browser:builder-pairwise"),
    "task-choice": ("component:task-matrix", "browser:builder-pairwise"),
    "scene-choice": ("component:scene-matrix", "browser:builder-pairwise"),
    "object-type": ("component:object-matrix", "browser:builder-pairwise"),
    "object-add": ("component:object-matrix", "browser:builder-pairwise"),
    "object-remove": ("component:object-remove", "browser:builder-pairwise"),
    "object-parameters": ("component:parameter-matrix", "browser:builder-bounds"),
    "builder-review": ("component:builder-review", "browser:builder-pairwise"),
    "setup-save": ("component:setup-save", "browser:builder-pairwise"),
    "setup-errors": ("component:setup-errors", "browser:builder-bounds"),
    "setup-reload": ("component:setup-persistence", "browser:setup-reload"),
    "setup-delete-cancel": ("component:setup-delete", "browser:setup-delete"),
    "prepare": ("component:lifecycle-prepare", "browser:lifecycle"),
    "preparing": ("component:lifecycle-preparing", "browser:lifecycle"),
    "retry": ("component:lifecycle-retry", "browser:lifecycle"),
    "start-training": ("component:lifecycle-start", "browser:lifecycle"),
    "stale": ("component:lifecycle-stale", "browser:lifecycle"),
    "quota": ("component:lifecycle-quota", "browser:lifecycle"),
    "verified-example": ("component:verified-example",),
    "keyboard-mobile": ("component:keyboard-mobile", "browser:keyboard-mobile"),
}


@dataclass(frozen=True)
class SetupCase:
    case_id: str
    robot_type: str
    task_id: str
    scene_id: str
    object_type: str | None
    expected_reason: str


@dataclass(frozen=True)
class ObjectParameterCase:
    case_id: str
    object_type: str
    parameter: str
    variant: str
    value: float
    valid: bool


@dataclass(frozen=True)
class CapacityCase:
    case_id: str
    scene_id: str
    optional_count: int
    valid: bool


def _catalog_payload() -> dict[str, Any]:
    return environment_catalog.serialize().model_dump(mode="json")


def catalog_fingerprint(payload: Mapping[str, Any] | None = None) -> str:
    canonical = json.dumps(
        dict(payload or _catalog_payload()),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def assert_current_contract(payload: Mapping[str, Any] | None = None) -> None:
    catalog = dict(payload or _catalog_payload())
    tasks = {item["id"]: tuple(item["compatible_robot_types"]) for item in catalog["task_templates"]}
    actual_compatibility = {
        robot_type: tuple(task_id for task_id, types in tasks.items() if robot_type in types)
        for robot_type in EXPECTED_ROBOT_TYPES
    }
    if actual_compatibility != EXPECTED_COMPATIBILITY:
        raise AssertionError(
            f"task compatibility drift: expected {EXPECTED_COMPATIBILITY}, got {actual_compatibility}"
        )
    scenes = {item["id"]: len(item["objects"]) for item in catalog["scene_presets"]}
    if scenes != EXPECTED_SCENE_OBJECT_COUNTS:
        raise AssertionError(
            f"scene catalog drift: expected {EXPECTED_SCENE_OBJECT_COUNTS}, got {scenes}"
        )
    objects = tuple(item["id"] for item in catalog["object_types"])
    if objects != EXPECTED_OBJECT_TYPES:
        raise AssertionError(
            f"object catalog drift: expected {EXPECTED_OBJECT_TYPES}, got {objects}"
        )
    for item in catalog["object_types"]:
        names = tuple(parameter["name"] for parameter in item["parameters"])
        if names != EXPECTED_PARAMETER_NAMES:
            raise AssertionError(
                f"parameter drift for {item['id']}: expected {EXPECTED_PARAMETER_NAMES}, got {names}"
            )
    if catalog["max_objects"] != EXPECTED_MAX_OBJECTS:
        raise AssertionError(
            f"max_objects drift: expected {EXPECTED_MAX_OBJECTS}, got {catalog['max_objects']}"
        )


def _reason(task_id: str, scene_id: str, object_type: str | None) -> str:
    if task_id not in EXPECTED_ELIGIBLE_TASKS:
        return "unsupported-task"
    if scene_id not in EXPECTED_ELIGIBLE_SCENES:
        return "unsupported-scene"
    if object_type is not None:
        return "optional-objects-not-supported"
    return "not-prepared"


def positive_setup_cases() -> tuple[SetupCase, ...]:
    payload = _catalog_payload()
    assert_current_contract(payload)
    task_ids = {
        robot_type: [
            task["id"]
            for task in payload["task_templates"]
            if robot_type in task["compatible_robot_types"]
        ]
        for robot_type in EXPECTED_ROBOT_TYPES
    }
    scene_ids = [scene["id"] for scene in payload["scene_presets"]]
    object_ids = [item["id"] for item in payload["object_types"]]
    cases: list[SetupCase] = []
    for robot_type in EXPECTED_ROBOT_TYPES:
        for task_id in task_ids[robot_type]:
            for scene_id in scene_ids:
                base = f"api:setup:{robot_type}:{task_id}:{scene_id}"
                cases.append(
                    SetupCase(
                        case_id=f"{base}:none",
                        robot_type=robot_type,
                        task_id=task_id,
                        scene_id=scene_id,
                        object_type=None,
                        expected_reason=_reason(task_id, scene_id, None),
                    )
                )
                for object_type in object_ids:
                    cases.append(
                        SetupCase(
                            case_id=f"{base}:{object_type}",
                            robot_type=robot_type,
                            task_id=task_id,
                            scene_id=scene_id,
                            object_type=object_type,
                            expected_reason=_reason(task_id, scene_id, object_type),
                        )
                    )
    if len(cases) != 100:
        raise AssertionError(f"expected 100 positive setup cases, got {len(cases)}")
    if sum(case.expected_reason == "not-prepared" for case in cases) != 8:
        raise AssertionError("expected exactly eight V1-eligible cases")
    return tuple(cases)


def object_parameter_cases() -> tuple[ObjectParameterCase, ...]:
    payload = _catalog_payload()
    assert_current_contract(payload)
    cases: list[ObjectParameterCase] = []
    for object_type in payload["object_types"]:
        for parameter in object_type["parameters"]:
            minimum = float(parameter["minimum"])
            maximum = float(parameter["maximum"])
            default = float(parameter["default"])
            epsilon = max((maximum - minimum) / 1000, 0.001)
            for variant, value, valid in (
                ("default", default, True),
                ("minimum", minimum, True),
                ("maximum", maximum, True),
                ("below", minimum - epsilon, False),
                ("above", maximum + epsilon, False),
            ):
                cases.append(
                    ObjectParameterCase(
                        case_id=(
                            f"api:parameter:{object_type['id']}:{parameter['name']}:{variant}"
                        ),
                        object_type=object_type["id"],
                        parameter=parameter["name"],
                        variant=variant,
                        value=value,
                        valid=valid,
                    )
                )
    if len(cases) != 140:
        raise AssertionError(f"expected 140 parameter cases, got {len(cases)}")
    return tuple(cases)


def capacity_cases() -> tuple[CapacityCase, ...]:
    payload = _catalog_payload()
    assert_current_contract(payload)
    cases: list[CapacityCase] = []
    for scene in payload["scene_presets"]:
        exact = payload["max_objects"] - len(scene["objects"])
        cases.extend(
            (
                CapacityCase(
                    case_id=f"api:capacity:{scene['id']}:exact",
                    scene_id=scene["id"],
                    optional_count=exact,
                    valid=True,
                ),
                CapacityCase(
                    case_id=f"api:capacity:{scene['id']}:over",
                    scene_id=scene["id"],
                    optional_count=exact + 1,
                    valid=False,
                ),
            )
        )
    return tuple(cases)


def expected_case_ids() -> tuple[str, ...]:
    uploads = tuple(
        f"api:upload:{sample}:{declared}"
        for sample in ("sample-quadruped", "sample-biped")
        for declared in EXPECTED_ROBOT_TYPES
    )
    controls = tuple(
        sorted({case_id for values in CONTROL_INVENTORY.values() for case_id in values})
    )
    identifiers = (
        uploads
        + tuple(case.case_id for case in positive_setup_cases())
        + tuple(case.case_id for case in object_parameter_cases())
        + tuple(case.case_id for case in capacity_cases())
        + controls
    )
    if len(identifiers) != len(set(identifiers)):
        duplicates = sorted(item for item in set(identifiers) if identifiers.count(item) > 1)
        raise AssertionError(f"duplicate validation case IDs: {duplicates}")
    return identifiers


T = TypeVar("T")


def select_shard(
    cases: Sequence[T],
    *,
    index: int,
    total: int,
    case_id=lambda item: item.case_id,
) -> tuple[T, ...]:
    if total < 1 or not 0 <= index < total:
        raise ValueError("shard index must satisfy 0 <= index < total")
    return tuple(
        item
        for item in cases
        if int(hashlib.sha256(case_id(item).encode("utf-8")).hexdigest(), 16) % total
        == index
    )


def manifest() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "catalog_fingerprint": catalog_fingerprint(),
        "counts": {
            "positive_setups": len(positive_setup_cases()),
            "eligible_setups": sum(
                case.expected_reason == "not-prepared" for case in positive_setup_cases()
            ),
            "object_parameters": len(EXPECTED_OBJECT_TYPES) * len(EXPECTED_PARAMETER_NAMES),
            "parameter_cases": len(object_parameter_cases()),
            "capacity_cases": len(capacity_cases()),
            "controls": len(CONTROL_INVENTORY),
        },
        "case_ids": list(expected_case_ids()),
        "controls": {key: list(value) for key, value in CONTROL_INVENTORY.items()},
    }


def _main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    rendered = json.dumps(manifest(), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
