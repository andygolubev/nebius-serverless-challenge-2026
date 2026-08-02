import {
  CatalogObject,
  EnvironmentCatalog,
  Robot,
  RobotSample,
  RobotSetup,
  RobotType,
} from "../api";

export const validation = {
  body_count: 8,
  joint_count: 8,
  actuator_count: 7,
  geom_count: 8,
  joint_names: ["root", "hip"],
  actuator_names: ["hip_motor"],
};

export const samples: RobotSample[] = [
  {
    id: "sample-quadruped",
    name: "Sample quadruped",
    filename: "sample-quadruped.xml",
    description: "Four-legged sample",
    robot_type: "quadruped",
    digest: "a".repeat(64),
    validation,
  },
  {
    id: "sample-biped",
    name: "Sample biped",
    filename: "sample-biped.xml",
    description: "Two-legged sample",
    robot_type: "biped",
    digest: "b".repeat(64),
    validation,
  },
];

export function robotFixture(type: RobotType, overrides: Partial<Robot> = {}): Robot {
  const label = type === "biped" ? "Warehouse biped" : "Survey quadruped";
  return {
    id: `robot-${type}`,
    name: label,
    filename: `${type}.xml`,
    robot_type: type,
    digest: (type === "biped" ? "c" : "q").repeat(64),
    validation,
    validated_at: "2026-07-13T00:00:00Z",
    readiness: "validated",
    trainable: false,
    reason: "custom-training-not-enabled",
    ...overrides,
  };
}

export const biped = robotFixture("biped");
export const quadruped = robotFixture("quadruped");

const parameter = (
  name: "x" | "y" | "z" | "yaw_degrees" | "width" | "depth" | "height",
  label: string,
  defaultValue: number,
  minimum: number,
  maximum: number,
  unit = "m",
) => ({ name, label, default: defaultValue, minimum, maximum, unit });

export const flatObject = (
  object_type: CatalogObject["object_type"],
  source: CatalogObject["source"] = "preset",
): CatalogObject => ({
  object_type,
  x: 2,
  y: 0,
  z: 0,
  yaw_degrees: 0,
  width: 1,
  depth: 1,
  height: 0.3,
  source,
});

export const catalog: EnvironmentCatalog = {
  task_templates: [
    {
      id: "stand-balance",
      label: "Stand and balance",
      description: "Stay upright",
      compatible_robot_types: ["quadruped", "biped"],
      contract: { version: "v1" },
    },
    {
      id: "walk-forward",
      label: "Walk forward",
      description: "Move ahead",
      compatible_robot_types: ["quadruped", "biped"],
      contract: { version: "v1" },
    },
    {
      id: "recover-from-fall",
      label: "Recover from a fall",
      description: "Stand back up",
      compatible_robot_types: ["quadruped"],
      contract: { version: "v1" },
    },
  ],
  scene_presets: [
    { id: "flat-arena", label: "Flat arena", description: "Open terrain", objects: [] },
    {
      id: "ramp-course",
      label: "Ramp course",
      description: "One ramp",
      objects: [flatObject("ramp")],
    },
    {
      id: "hurdle-course",
      label: "Hurdle course",
      description: "Three hurdles",
      objects: [flatObject("hurdle"), flatObject("hurdle"), flatObject("hurdle")],
    },
    {
      id: "step-course",
      label: "Step course",
      description: "Three steps",
      objects: [flatObject("step"), flatObject("step"), flatObject("step")],
    },
  ],
  object_types: (["box", "ramp", "hurdle", "step"] as const).map((id) => ({
    id,
    label: id[0].toUpperCase() + id.slice(1),
    description: `${id} primitive`,
    parameters: [
      parameter("x", "Forward position", 2, -10, 10),
      parameter("y", "Side position", 0, -10, 10),
      parameter("z", "Base height", 0, 0, 5),
      parameter("yaw_degrees", "Rotation", 0, -180, 180, "deg"),
      parameter("width", "Width", 1, 0.1, 4),
      parameter("depth", "Depth", 1, 0.1, 4),
      parameter("height", "Height", 0.3, 0.05, 2),
    ],
  })),
  max_objects: 6,
  max_setups: 50,
  arena_bounds: { x: [-10, 10], y: [-10, 10], z: [0, 5] },
};

export const controlInventory = {
  "sample-download": ["browser:sample-download"],
  "upload-name": ["component:upload-required", "browser:upload-happy"],
  "upload-robot-type": ["component:upload-types", "browser:upload-happy"],
  "upload-file": ["component:upload-required", "browser:upload-happy"],
  "upload-submit": ["component:upload-errors", "browser:upload-happy"],
  "upload-errors": ["component:upload-errors"],
  "model-statistics": ["component:model-card", "browser:upload-happy"],
  "model-digest": ["component:model-card", "browser:upload-happy"],
  "model-download": ["component:model-download", "browser:model-download"],
  "model-delete-cancel": ["component:model-delete", "browser:model-delete"],
  "build-environment": ["component:builder-open", "browser:builder-pairwise"],
  "builder-close": ["component:builder-close"],
  "setup-name": ["component:builder-name", "browser:builder-pairwise"],
  "task-choice": ["component:task-matrix", "browser:builder-pairwise"],
  "scene-choice": ["component:scene-matrix", "browser:builder-pairwise"],
  "object-type": ["component:object-matrix", "browser:builder-pairwise"],
  "object-add": ["component:object-matrix", "browser:builder-pairwise"],
  "object-remove": ["component:object-remove", "browser:builder-pairwise"],
  "object-parameters": ["component:parameter-matrix", "browser:builder-bounds"],
  "builder-review": ["component:builder-review", "browser:builder-pairwise"],
  "setup-save": ["component:setup-save", "browser:builder-pairwise"],
  "setup-errors": ["component:setup-errors", "browser:builder-bounds"],
  "setup-reload": ["component:setup-persistence", "browser:setup-reload"],
  "setup-delete-cancel": ["component:setup-delete", "browser:setup-delete"],
  prepare: ["component:lifecycle-prepare", "browser:lifecycle"],
  preparing: ["component:lifecycle-preparing", "browser:lifecycle"],
  retry: ["component:lifecycle-retry", "browser:lifecycle"],
  "start-training": ["component:lifecycle-start", "browser:lifecycle"],
  stale: ["component:lifecycle-stale", "browser:lifecycle"],
  quota: ["component:lifecycle-quota", "browser:lifecycle"],
  "verified-example": ["component:verified-example"],
  "keyboard-mobile": ["component:keyboard-mobile", "browser:keyboard-mobile"],
} as const;

export function setupFixture(overrides: Partial<RobotSetup> = {}): RobotSetup {
  return {
    id: "setup-1",
    name: "Warehouse biped setup",
    robot_id: biped.id,
    robot_name: biped.name,
    robot_type: "biped",
    task_template_id: "stand-balance",
    scene_preset_id: "flat-arena",
    objects: [],
    digest: "d".repeat(64),
    created_at: "2026-07-13T00:00:00Z",
    readiness: "validated",
    trainable: false,
    reason: "not-prepared",
    training_readiness: "not_prepared",
    can_prepare: true,
    can_start_training: false,
    current_preparation: null,
    ...overrides,
  };
}
