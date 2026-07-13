import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CatalogObject, EnvironmentCatalog, Robot, RobotSample, RobotSetup } from "../api";
import { MyRobots } from "./MyRobots";

function json(value: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } }));
}

const validation = {
  body_count: 8,
  joint_count: 8,
  actuator_count: 7,
  geom_count: 8,
  joint_names: ["root", "hip"],
  actuator_names: ["hip_motor"],
};

const samples: RobotSample[] = [
  { id: "sample-quadruped", name: "Sample quadruped", filename: "sample-quadruped.xml", description: "Four-legged sample", robot_type: "quadruped", digest: "a".repeat(64), validation },
  { id: "sample-biped", name: "Sample biped", filename: "sample-biped.xml", description: "Two-legged sample", robot_type: "biped", digest: "b".repeat(64), validation },
];

const biped: Robot = {
  id: "robot-biped",
  name: "Warehouse biped",
  filename: "warehouse.xml",
  robot_type: "biped",
  digest: "c".repeat(64),
  validation,
  validated_at: "2026-07-13T00:00:00Z",
  readiness: "validated",
  trainable: false,
  reason: "custom-training-not-enabled",
};

const parameter = (name: "x" | "y" | "z" | "yaw_degrees" | "width" | "depth" | "height", label: string, defaultValue: number, minimum: number, maximum: number, unit = "m") => ({ name, label, default: defaultValue, minimum, maximum, unit });
const flatObject = (object_type: CatalogObject["object_type"], source: CatalogObject["source"] = "preset"): CatalogObject => ({ object_type, x: 2, y: 0, z: 0, yaw_degrees: 0, width: 1, depth: 1, height: 0.3, source });

const catalog: EnvironmentCatalog = {
  task_templates: [
    { id: "stand-balance", label: "Stand and balance", description: "Stay upright", compatible_robot_types: ["quadruped", "biped"], contract: { version: "v1" } },
    { id: "walk-forward", label: "Walk forward", description: "Move ahead", compatible_robot_types: ["quadruped", "biped"], contract: { version: "v1" } },
    { id: "recover-from-fall", label: "Recover from a fall", description: "Stand back up", compatible_robot_types: ["quadruped"], contract: { version: "v1" } },
  ],
  scene_presets: [
    { id: "flat-arena", label: "Flat arena", description: "Open terrain", objects: [] },
    { id: "ramp-course", label: "Ramp course", description: "One ramp", objects: [flatObject("ramp")] },
    { id: "hurdle-course", label: "Hurdle course", description: "Three hurdles", objects: [flatObject("hurdle"), flatObject("hurdle"), flatObject("hurdle")] },
    { id: "step-course", label: "Step course", description: "Three steps", objects: [flatObject("step"), flatObject("step"), flatObject("step")] },
  ],
  object_types: ["box", "ramp", "hurdle", "step"].map((id) => ({
    id: id as "box" | "ramp" | "hurdle" | "step",
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

function workspaceFetch({ robots = [], setups = [], upload, createSetup }: { robots?: Robot[]; setups?: RobotSetup[]; upload?: Robot; createSetup?: RobotSetup } = {}) {
  return vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    const method = init?.method ?? "GET";
    if (path === "/robot-samples") return json(samples);
    if (path === "/environment-catalog") return json(catalog);
    if (path === "/robots" && method === "GET") return json(robots);
    if (path === "/robots" && method === "POST") return json(upload ?? biped, 201);
    if (path === "/robot-setups" && method === "GET") return json(setups);
    if (path === "/robot-setups" && method === "POST") return json(createSetup, 201);
    if (method === "DELETE") return Promise.resolve(new Response(null, { status: 204 }));
    if (path.startsWith("/robot-samples/") || path.endsWith("/content")) {
      return Promise.resolve(new Response("<mujoco/>", { status: 200, headers: { "Content-Type": "application/xml" } }));
    }
    throw new Error(`unhandled request ${method} ${path}`);
  });
}

beforeEach(() => {
  localStorage.setItem("sim2policy.session", "test-token");
  vi.stubGlobal("URL", { ...URL, createObjectURL: vi.fn(() => "blob:test"), revokeObjectURL: vi.fn() });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("My Robots workspace", () => {
  it("discovers both samples and keeps a server field error beside the upload", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input) === "/robots" && init?.method === "POST") {
        return json({ detail: { field: "file", message: "DTD and entity declarations are not supported" } }, 422);
      }
      return workspaceFetch()(input, init);
    }));
    render(<MyRobots />);
    expect(await screen.findByText("Sample quadruped")).toBeVisible();
    expect(screen.getByText("Sample biped")).toBeVisible();
    fireEvent.change(screen.getByLabelText("Robot name"), { target: { value: "Unsafe model" } });
    fireEvent.change(screen.getByLabelText("MJCF XML"), { target: { files: [new File(["<!DOCTYPE x>"], "unsafe.xml", { type: "application/xml" })] } });
    fireEvent.click(screen.getByRole("button", { name: "Validate model" }));
    expect(await screen.findByText("DTD and entity declarations are not supported")).toBeVisible();
    expect(screen.getByDisplayValue("Unsafe model")).toBeVisible();
  });

  it("uploads a valid model without forcing a JSON content type, shows readiness, and deletes it", async () => {
    const uploaded = { ...biped, name: "Inspection biped" };
    const fetch = workspaceFetch({ upload: uploaded });
    vi.stubGlobal("fetch", fetch);
    render(<MyRobots />);
    await screen.findByText("Sample quadruped");
    fireEvent.change(screen.getByLabelText("Robot name"), { target: { value: uploaded.name } });
    fireEvent.change(screen.getByLabelText("MJCF XML"), { target: { files: [new File(["<mujoco/>"], "inspection.xml", { type: "application/xml" })] } });
    fireEvent.click(screen.getByRole("button", { name: "Validate model" }));
    const name = await screen.findByText(uploaded.name);
    const card = name.closest("article")!;
    expect(within(card).getByText("Validated model")).toBeVisible();
    expect(within(card).getByText(/Custom GPU training is not enabled yet/)).toBeVisible();
    const uploadCall = fetch.mock.calls.find(([, init]) => init?.method === "POST")!;
    expect(uploadCall[1]?.body).toBeInstanceOf(FormData);
    expect((uploadCall[1]?.headers as Headers).has("Content-Type")).toBe(false);

    fireEvent.click(within(card).getByRole("button", { name: "Delete model" }));
    fireEvent.click(within(card).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(screen.queryByText(uploaded.name)).not.toBeInTheDocument());
  });

  it("filters tasks by robot type, enforces object bounds, and saves a normalized setup", async () => {
    const saved: RobotSetup = {
      id: "setup-1", name: "Warehouse biped setup", robot_id: biped.id, robot_name: biped.name,
      robot_type: "biped", task_template_id: "stand-balance", scene_preset_id: "flat-arena",
      objects: [flatObject("box", "custom")], digest: "d".repeat(64), created_at: "2026-07-13T00:00:00Z",
      readiness: "validated", trainable: false, reason: "custom-training-not-enabled",
    };
    vi.stubGlobal("fetch", workspaceFetch({ robots: [biped], createSetup: saved }));
    render(<MyRobots />);
    const build = await screen.findByRole("button", { name: "Build environment" });
    build.focus();
    expect(build).toHaveFocus();
    fireEvent.click(build);
    expect(screen.getByRole("radiogroup", { name: "Locomotion task" })).toBeVisible();
    expect(screen.getByRole("radio", { name: /Stand and balance/ })).toBeVisible();
    expect(screen.queryByRole("radio", { name: /Recover from a fall/ })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/object file/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/url/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Add object" }));
    const height = screen.getByLabelText(/Height/);
    fireEvent.change(height, { target: { value: "3" } });
    expect(screen.getByRole("button", { name: "Save validated setup" })).toBeDisabled();
    fireEvent.change(height, { target: { value: "0.3" } });
    const save = screen.getByRole("button", { name: "Save validated setup" });
    expect(save).toBeEnabled();
    save.focus();
    expect(save).toHaveFocus();
    fireEvent.click(save);
    expect(await screen.findByRole("status")).toHaveTextContent("Setup saved");
    expect(screen.getAllByText("Validated setup").length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: "Training coming after GPU validation" })[0]).toBeDisabled();
  });

  it("renders the full workflow at a 375px viewport using native keyboard controls", async () => {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 375 });
    window.dispatchEvent(new Event("resize"));
    vi.stubGlobal("fetch", workspaceFetch({ robots: [biped] }));
    const { container } = render(<MyRobots />);
    await screen.findByText("Warehouse biped");
    fireEvent.click(screen.getByRole("button", { name: "Build environment" }));
    const choices = screen.getAllByRole("radio");
    expect(choices.every((choice) => choice.tagName === "BUTTON" || choice.tagName === "INPUT")).toBe(true);
    expect(container.querySelectorAll('input[type="file"]')).toHaveLength(1);
    expect(
      Array.from(container.querySelectorAll<HTMLElement>("[style]")).every((element) => !element.style.width.endsWith("px")),
    ).toBe(true);
  });
});
