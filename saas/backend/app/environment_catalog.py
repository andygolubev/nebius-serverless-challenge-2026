"""Server-owned task, scene, and primitive-object contracts for robot setup drafts."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .models import (
    CatalogObject,
    CatalogObjectInput,
    EnvironmentCatalog,
    ObjectCatalogEntry,
    ObjectParameter,
    RobotType,
    ScenePreset,
    TaskTemplate,
)

MAX_OBJECTS = 6
ARENA_BOUNDS = {"x": [-10.0, 10.0], "y": [-10.0, 10.0], "z": [0.0, 5.0]}


class BuilderValidationError(ValueError):
    def __init__(self, field: str, message: str) -> None:
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")


TASKS = {
    task.id: task
    for task in [
        TaskTemplate(
            id="stand-balance",
            label="Stand and balance",
            description="Hold a stable upright pose while resisting small disturbances.",
            compatible_robot_types=["quadruped", "biped"],
            contract={"version": "v1", "objective": "upright-stability", "termination": "server-owned"},
        ),
        TaskTemplate(
            id="walk-forward",
            label="Walk forward",
            description="Move forward while maintaining balance and controlled joint motion.",
            compatible_robot_types=["quadruped", "biped"],
            contract={"version": "v1", "objective": "forward-velocity", "termination": "server-owned"},
        ),
        TaskTemplate(
            id="recover-from-fall",
            label="Recover from a fall",
            description="Return to a stable standing pose from a bounded fallen state.",
            compatible_robot_types=["quadruped"],
            contract={"version": "v1", "objective": "upright-recovery", "termination": "server-owned"},
        ),
    ]
}

_COMMON_POSITION = [
    ObjectParameter(name="x", label="Forward position", default=2.0, minimum=-10, maximum=10, unit="m"),
    ObjectParameter(name="y", label="Side position", default=0.0, minimum=-10, maximum=10, unit="m"),
    ObjectParameter(name="z", label="Base height", default=0.0, minimum=0, maximum=5, unit="m"),
    ObjectParameter(name="yaw_degrees", label="Rotation", default=0.0, minimum=-180, maximum=180, unit="deg"),
]


def _dimensions(width: tuple[float, float, float], depth: tuple[float, float, float], height: tuple[float, float, float]) -> list[ObjectParameter]:
    return [
        ObjectParameter(name="width", label="Width", default=width[0], minimum=width[1], maximum=width[2], unit="m"),
        ObjectParameter(name="depth", label="Depth", default=depth[0], minimum=depth[1], maximum=depth[2], unit="m"),
        ObjectParameter(name="height", label="Height", default=height[0], minimum=height[1], maximum=height[2], unit="m"),
    ]


OBJECT_TYPES = {
    entry.id: entry
    for entry in [
        ObjectCatalogEntry(id="box", label="Box", description="A solid platform or obstacle.", parameters=[*_COMMON_POSITION, *_dimensions((1, 0.1, 4), (1, 0.1, 4), (0.3, 0.05, 2))]),
        ObjectCatalogEntry(id="ramp", label="Ramp", description="A bounded incline for ascent and descent.", parameters=[*_COMMON_POSITION, *_dimensions((1.5, 0.5, 4), (3, 0.5, 6), (0.6, 0.1, 2))]),
        ObjectCatalogEntry(id="hurdle", label="Hurdle", description="A narrow obstacle to step or jump over.", parameters=[*_COMMON_POSITION, *_dimensions((2, 0.5, 4), (0.15, 0.05, 0.5), (0.35, 0.05, 1.5))]),
        ObjectCatalogEntry(id="step", label="Step", description="A low raised platform.", parameters=[*_COMMON_POSITION, *_dimensions((2, 0.2, 4), (1, 0.2, 4), (0.2, 0.05, 0.75))]),
    ]
}


def normalize_object(value: CatalogObjectInput, *, source: str, field: str) -> CatalogObject:
    spec = OBJECT_TYPES.get(value.object_type)
    if spec is None:
        raise BuilderValidationError(field, f"unknown catalog object: {value.object_type}")
    normalized: dict[str, float | str] = {"object_type": value.object_type, "source": source}
    for parameter in spec.parameters:
        supplied = getattr(value, parameter.name)
        number = parameter.default if supplied is None else supplied
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            raise BuilderValidationError(field, f"{value.object_type}.{parameter.name} must be a number")
        number = float(number)
        if not parameter.minimum <= number <= parameter.maximum:
            raise BuilderValidationError(
                field,
                f"{value.object_type}.{parameter.name} must be between {parameter.minimum:g} and {parameter.maximum:g}",
            )
        normalized[parameter.name] = number
    return CatalogObject.model_validate(normalized)


def _preset_object(object_type: str, **overrides: float) -> CatalogObject:
    values: dict[str, Any] = {"object_type": object_type, **overrides}
    return normalize_object(CatalogObjectInput.model_validate(values), source="preset", field="scene_preset_id")


SCENES = {
    scene.id: scene
    for scene in [
        ScenePreset(id="flat-arena", label="Flat arena", description="An open, level training surface.", objects=[]),
        ScenePreset(id="ramp-course", label="Ramp course", description="One centered incline with clear approach space.", objects=[_preset_object("ramp", x=3.0)]),
        ScenePreset(id="hurdle-course", label="Hurdle course", description="Three progressively spaced hurdles.", objects=[_preset_object("hurdle", x=2.0), _preset_object("hurdle", x=4.0), _preset_object("hurdle", x=6.0)]),
        ScenePreset(id="step-course", label="Step course", description="Three low platforms for careful foot placement.", objects=[_preset_object("step", x=2.0), _preset_object("step", x=4.0, height=0.3), _preset_object("step", x=6.0, height=0.4)]),
    ]
}


def normalize_setup(robot_id: str, robot_type: RobotType, task_id: str, scene_id: str, objects: list[CatalogObjectInput]) -> tuple[list[CatalogObject], str]:
    task = TASKS.get(task_id)
    if task is None:
        raise BuilderValidationError("task_template_id", f"unknown task template: {task_id}")
    if robot_type not in task.compatible_robot_types:
        raise BuilderValidationError("task_template_id", f"{task_id} is not available for {robot_type} robots")
    scene = SCENES.get(scene_id)
    if scene is None:
        raise BuilderValidationError("scene_preset_id", f"unknown scene preset: {scene_id}")
    if len(scene.objects) + len(objects) > MAX_OBJECTS:
        raise BuilderValidationError("objects", f"a setup may contain at most {MAX_OBJECTS} objects including preset objects")
    normalized = [object_.model_copy(deep=True) for object_ in scene.objects]
    for index, value in enumerate(objects):
        normalized.append(normalize_object(value, source="custom", field=f"objects.{index}"))
    payload = {
        "robot_id": robot_id,
        "robot_type": robot_type,
        "task_template_id": task_id,
        "scene_preset_id": scene_id,
        "objects": [object_.model_dump(mode="json") for object_ in normalized],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return normalized, hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def serialize() -> EnvironmentCatalog:
    return EnvironmentCatalog(
        task_templates=list(TASKS.values()),
        scene_presets=list(SCENES.values()),
        object_types=list(OBJECT_TYPES.values()),
        arena_bounds=ARENA_BOUNDS,
    )
