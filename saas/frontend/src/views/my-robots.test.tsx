import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Robot, RobotSetup } from "../api";
import {
  biped,
  catalog,
  controlInventory,
  flatObject,
  quadruped,
  samples,
  setupFixture,
} from "../test-fixtures/myRobotsMatrix";
import { MyRobots } from "./MyRobots";

function json(value: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } }));
}

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
  it("[component:catalog-completeness] keeps the catalog and control inventory complete", () => {
    expect(catalog.task_templates.map((task) => task.id)).toEqual([
      "stand-balance",
      "walk-forward",
      "recover-from-fall",
    ]);
    expect(catalog.scene_presets.map((scene) => scene.id)).toEqual([
      "flat-arena",
      "ramp-course",
      "hurdle-course",
      "step-course",
    ]);
    expect(catalog.object_types.map((object) => object.id)).toEqual([
      "box",
      "ramp",
      "hurdle",
      "step",
    ]);
    expect(catalog.object_types.every((object) => object.parameters.length === 7)).toBe(true);
    expect(catalog.object_types.flatMap((object) => object.parameters)).toHaveLength(28);
    expect(Object.keys(controlInventory)).toHaveLength(32);
    expect(Object.values(controlInventory).every((caseIds) => caseIds.length > 0)).toBe(true);
  });

  it("[component:upload-required] validates required fields, extension, and both declared type paths", async () => {
    const fetch = workspaceFetch({ upload: biped });
    vi.stubGlobal("fetch", fetch);
    render(<MyRobots />);
    await screen.findByText("Sample quadruped");
    fireEvent.click(screen.getByRole("button", { name: "Validate model" }));
    expect(screen.getByText("Give this robot a recognizable name.")).toBeVisible();
    expect(screen.getByText("Choose one MJCF .xml file.")).toBeVisible();

    const bipedRadio = screen.getByRole("radio", { name: "Biped" });
    fireEvent.click(bipedRadio);
    expect(bipedRadio).toBeChecked();
    fireEvent.change(screen.getByLabelText("Robot name"), { target: { value: "Radio biped" } });
    fireEvent.change(screen.getByLabelText("MJCF XML"), {
      target: { files: [new File(["bad"], "robot.txt", { type: "text/plain" })] },
    });
    fireEvent.click(screen.getByRole("button", { name: "Validate model" }));
    expect(screen.getByText("The file must end in .xml.")).toBeVisible();

    fireEvent.change(screen.getByLabelText("MJCF XML"), {
      target: { files: [new File(["<mujoco/>"], "robot.xml", { type: "application/xml" })] },
    });
    fireEvent.click(screen.getByRole("button", { name: "Validate model" }));
    await screen.findByText("Warehouse biped");
    const upload = fetch.mock.calls.find(([, init]) => init?.method === "POST")?.[1]?.body;
    expect(upload).toBeInstanceOf(FormData);
    expect((upload as FormData).get("robot_type")).toBe("biped");
  });

  it("[component:model-download] downloads samples and models and cancels deletion safely", async () => {
    const fetch = workspaceFetch({ robots: [biped] });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    vi.stubGlobal("fetch", fetch);
    render(<MyRobots />);
    const sampleHeading = await screen.findByText("Sample quadruped");
    const sampleCard = sampleHeading.closest("article")!;
    fireEvent.click(within(sampleCard).getByRole("button", { name: "Download XML" }));
    const modelHeading = await screen.findByText(biped.name);
    const modelCard = modelHeading.closest("article")!;
    fireEvent.click(within(modelCard).getByRole("button", { name: "Download XML" }));
    await waitFor(() => expect(click).toHaveBeenCalledTimes(2));
    fireEvent.click(within(modelCard).getByRole("button", { name: "Delete model" }));
    expect(within(modelCard).getByText("Delete this version?")).toBeVisible();
    fireEvent.click(within(modelCard).getByRole("button", { name: "Cancel" }));
    expect(screen.getByText(biped.name)).toBeVisible();
    expect(fetch.mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(false);
  });

  it("[component:choice-inventory] renders every compatible task, scene, object, parameter, and close action", async () => {
    vi.stubGlobal("fetch", workspaceFetch({ robots: [quadruped] }));
    render(<MyRobots />);
    fireEvent.click(await screen.findByRole("button", { name: "Build environment" }));
    for (const task of catalog.task_templates) {
      expect(screen.getByRole("radio", { name: new RegExp(task.label) })).toBeVisible();
    }
    for (const scene of catalog.scene_presets) {
      expect(screen.getByRole("radio", { name: new RegExp(scene.label) })).toBeVisible();
    }
    const objectType = screen.getByLabelText("Object type");
    expect(within(objectType).getAllByRole("option")).toHaveLength(4);
    for (const object of catalog.object_types) {
      fireEvent.change(objectType, { target: { value: object.id } });
      fireEvent.click(screen.getByRole("button", { name: "Add object" }));
      expect(screen.getAllByRole("spinbutton")).toHaveLength(7);
      for (const parameter of object.parameters) {
        expect(screen.getByLabelText(new RegExp(parameter.label))).toBeVisible();
      }
      fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    }
    fireEvent.click(screen.getByRole("button", { name: "Close builder" }));
    expect(screen.queryByRole("heading", { name: `Set up ${quadruped.name}` })).not.toBeInTheDocument();
  });

  it.each(catalog.scene_presets)(
    "[component:capacity-$id] disables Add object at the exact six-object total for $label",
    async (scene) => {
      vi.stubGlobal("fetch", workspaceFetch({ robots: [quadruped] }));
      render(<MyRobots />);
      fireEvent.click(await screen.findByRole("button", { name: "Build environment" }));
      fireEvent.click(screen.getByRole("radio", { name: new RegExp(scene.label) }));
      const add = screen.getByRole("button", { name: "Add object" });
      const available = catalog.max_objects - scene.objects.length;
      for (let index = 0; index < available; index += 1) fireEvent.click(add);
      expect(add).toBeDisabled();
      expect(screen.getByText(new RegExp(`· ${catalog.max_objects} objects$`))).toBeVisible();
      fireEvent.click(screen.getAllByRole("button", { name: "Remove" })[0]);
      expect(add).toBeEnabled();
    },
  );

  it.each(catalog.object_types)(
    "[component:parameter-$id] enforces empty, minimum, maximum, and out-of-range values for $label",
    async (object) => {
      vi.stubGlobal("fetch", workspaceFetch({ robots: [biped] }));
      render(<MyRobots />);
      fireEvent.click(await screen.findByRole("button", { name: "Build environment" }));
      fireEvent.change(screen.getByLabelText("Object type"), { target: { value: object.id } });
      fireEvent.click(screen.getByRole("button", { name: "Add object" }));
      const save = screen.getByRole("button", { name: "Save validated setup" });
      for (const parameter of object.parameters) {
        const input = screen.getByLabelText(new RegExp(parameter.label));
        fireEvent.change(input, { target: { value: String(parameter.minimum) } });
        expect(input).toHaveAttribute("aria-invalid", "false");
        fireEvent.change(input, { target: { value: String(parameter.maximum) } });
        expect(input).toHaveAttribute("aria-invalid", "false");
        fireEvent.change(input, { target: { value: "" } });
        expect(input).toHaveAttribute("aria-invalid", "true");
        expect(save).toBeDisabled();
        fireEvent.change(input, { target: { value: String(parameter.maximum + 1) } });
        expect(input).toHaveAttribute("aria-invalid", "true");
        fireEvent.change(input, { target: { value: String(parameter.default) } });
      }
      expect(save).toBeEnabled();
    },
  );

  it("[component:setup-errors] preserves builder state on a field-level save error", async () => {
    const fetch = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input) === "/robot-setups" && init?.method === "POST") {
        return json({ detail: { field: "objects.0", message: "server rejected object" } }, 422);
      }
      return workspaceFetch({ robots: [biped] })(input, init);
    });
    vi.stubGlobal("fetch", fetch);
    render(<MyRobots />);
    fireEvent.click(await screen.findByRole("button", { name: "Build environment" }));
    fireEvent.change(screen.getByLabelText("Setup name"), { target: { value: "Preserved setup" } });
    fireEvent.click(screen.getByRole("button", { name: "Add object" }));
    fireEvent.click(screen.getByRole("button", { name: "Save validated setup" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("server rejected object");
    expect(screen.getByDisplayValue("Preserved setup")).toBeVisible();
    expect(screen.getAllByRole("spinbutton")).toHaveLength(7);
  });

  it("[component:setup-delete] cancels then confirms setup deletion without changing another row", async () => {
    const target = setupFixture({ id: "setup-target", name: "Delete target" });
    const retained = setupFixture({ id: "setup-retained", name: "Keep me" });
    const fetch = workspaceFetch({ robots: [biped], setups: [target, retained] });
    vi.stubGlobal("fetch", fetch);
    render(<MyRobots />);
    const targetCard = (await screen.findByText(target.name)).closest("article")!;
    fireEvent.click(within(targetCard).getByRole("button", { name: "Delete setup" }));
    fireEvent.click(within(targetCard).getByRole("button", { name: "Cancel" }));
    expect(screen.getByText(target.name)).toBeVisible();
    fireEvent.click(within(targetCard).getByRole("button", { name: "Delete setup" }));
    fireEvent.click(within(targetCard).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(screen.queryByText(target.name)).not.toBeInTheDocument());
    expect(screen.getByText(retained.name)).toBeVisible();
  });

  it("[component:lifecycle-preparing] renders a disabled preparing action", async () => {
    const preparing = setupFixture({
      id: "setup-preparing",
      reason: "preparing",
      training_readiness: "preparing",
      can_prepare: false,
      current_preparation: {
        id: "preparing-1",
        setup_id: "setup-preparing",
        robot_id: biped.id,
        fingerprint: "f".repeat(64),
        state: "preparing",
        phase: "compile",
        created_at: "2026-07-13T00:00:00Z",
        updated_at: "2026-07-13T00:00:00Z",
        failure_phase: null,
        failure_reason: null,
        report_sha256: null,
        report_ready: false,
        can_retry: false,
      },
    });
    vi.stubGlobal("fetch", workspaceFetch({ robots: [biped], setups: [preparing] }));
    render(<MyRobots />);
    expect(await screen.findByText("Preparing · Compile")).toBeVisible();
    expect(screen.getByRole("button", { name: "Preparing…" })).toBeDisabled();
  });

  it.each<{
    caseId: string;
    setup: RobotSetup;
    action: string;
    status: number;
    message: string;
  }>([
    {
      caseId: "component:lifecycle-quota",
      setup: setupFixture(),
      action: "Prepare for training",
      status: 429,
      message: "Preparation capacity is in use",
    },
    {
      caseId: "component:lifecycle-stale",
      setup: setupFixture({ trainable: true, reason: "ready", training_readiness: "ready", can_prepare: false, can_start_training: true }),
      action: "Start training",
      status: 409,
      message: "Prepare the current setup again",
    },
  ])("[$caseId] shows sanitized lifecycle errors", async ({ setup, action, status, message }) => {
    const fetch = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path === "/robot-samples") return json(samples);
      if (path === "/environment-catalog") return json(catalog);
      if (path === "/robots") return json([biped]);
      if (path === "/robot-setups") return json([setup]);
      if (path === `/robot-setups/${setup.id}`) return json(setup);
      if (init?.method === "POST") return json({ detail: { message } }, status);
      throw new Error(`unhandled ${init?.method ?? "GET"} ${path}`);
    });
    vi.stubGlobal("fetch", fetch);
    render(<MyRobots />);
    fireEvent.click(await screen.findByRole("button", { name: action }));
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
  });

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
    expect(within(card).getByText("Model validated")).toBeVisible();
    expect(within(card).getByText(/Model file and structure validated/)).toBeVisible();
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
      readiness: "validated", trainable: false, reason: "optional-objects-not-supported",
      training_readiness: "ineligible", can_prepare: false, can_start_training: false,
      current_preparation: null,
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
    expect(await screen.findByText(/Setup saved\./)).toBeVisible();
    expect(screen.getAllByText("Setup validated").length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "Prepare for training" })).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "See a verified example" }).length).toBeGreaterThan(0);
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

  it("prepares an eligible setup and starts its fixed training job", async () => {
    const base: RobotSetup = {
      id: "setup-trainable", name: "Trainable biped", robot_id: biped.id, robot_name: biped.name,
      robot_type: "biped", task_template_id: "walk-forward", scene_preset_id: "flat-arena",
      objects: [], digest: "e".repeat(64), created_at: "2026-07-13T00:00:00Z",
      readiness: "validated", trainable: false, reason: "not-prepared",
      training_readiness: "not_prepared", can_prepare: true, can_start_training: false,
      current_preparation: null,
    };
    const preparing: RobotSetup = {
      ...base,
      reason: "preparing",
      training_readiness: "preparing",
      can_prepare: false,
      current_preparation: {
        id: "prepare-1", setup_id: base.id, robot_id: biped.id, fingerprint: "f".repeat(64),
        state: "preparing", phase: "compile", created_at: base.created_at, updated_at: base.created_at,
        failure_phase: null, failure_reason: null, report_sha256: null, report_ready: false, can_retry: false,
      },
    };
    let setup = base;
    const fetch = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path === "/robot-samples") return json(samples);
      if (path === "/environment-catalog") return json(catalog);
      if (path === "/robots") return json([biped]);
      if (path === "/robot-setups") return json([setup]);
      if (path === `/robot-setups/${base.id}`) return json(setup);
      if (path.endsWith("/preparations") && init?.method === "POST") {
        setup = preparing;
        return json(preparing.current_preparation, 201);
      }
      if (path.endsWith("/training-jobs") && init?.method === "POST") {
        return json({ id: "custom-job-1" }, 201);
      }
      throw new Error(`unhandled ${init?.method ?? "GET"} ${path}`);
    });
    vi.stubGlobal("fetch", fetch);
    const onJobStarted = vi.fn();
    const view = render(<MyRobots onJobStarted={onJobStarted} />);
    fireEvent.click(await screen.findByRole("button", { name: "Prepare for training" }));
    expect(await screen.findByText(/Preparing · Compile/)).toBeVisible();
    expect(fetch).toHaveBeenCalledWith(
      `/robot-setups/${base.id}/preparations`,
      expect.objectContaining({ method: "POST" }),
    );

    view.unmount();
    setup = {
      ...preparing,
      trainable: true,
      reason: "ready",
      training_readiness: "ready",
      can_start_training: true,
      current_preparation: {
        ...preparing.current_preparation!,
        state: "accepted",
        phase: "accepted",
        report_sha256: "a".repeat(64),
        report_ready: true,
      },
    };
    render(<MyRobots onJobStarted={onJobStarted} />);
    const start = await screen.findByRole("button", { name: "Start training" });
    fireEvent.click(start);
    fireEvent.click(start);
    await waitFor(() => expect(onJobStarted).toHaveBeenCalledWith("custom-job-1"));
    const startCalls = fetch.mock.calls.filter(([path]) => String(path).endsWith("/training-jobs"));
    expect(startCalls).toHaveLength(1);
    const startCall = startCalls[0];
    expect(String(startCall?.[1]?.body)).toContain("idempotency_key");
  });

  it("hands a validation-only setup to the gallery without creating a job or changing the saved setup", async () => {
    const validationOnly: RobotSetup = {
      id: "setup-validation-only", name: "Saved validation", robot_id: biped.id, robot_name: biped.name,
      robot_type: "biped", task_template_id: "walk-forward", scene_preset_id: "flat-arena",
      objects: [], digest: "7".repeat(64), created_at: "2026-07-13T00:00:00Z",
      readiness: "validated", trainable: false, reason: "custom-training-not-enabled",
      training_readiness: "ineligible", can_prepare: false, can_start_training: false,
      current_preparation: null,
    };
    const fetch = workspaceFetch({ robots: [biped], setups: [validationOnly] });
    vi.stubGlobal("fetch", fetch);
    const onBrowseExamples = vi.fn();
    render(<MyRobots onBrowseExamples={onBrowseExamples} />);

    const setupName = await screen.findByText(validationOnly.name);
    const card = setupName.closest("article")!;
    expect(within(card).getByText("Setup validated")).toBeVisible();
    expect(within(card).getByText(/no accepted custom training adapter and production job specification/i)).toBeVisible();
    expect(within(card).getByText(/No training job was created/)).toBeVisible();
    expect(within(card).queryByRole("button", { name: /GPU validation/i })).not.toBeInTheDocument();
    expect(within(card).queryByRole("button", { name: "Start training" })).not.toBeInTheDocument();
    expect(within(card).queryByRole("button", { name: "Prepare for training" })).not.toBeInTheDocument();

    // The handoff is reference evidence, not an alternative training action: showcase
    // examples are read-only, so no wording here may offer to train one.
    expect(within(card).queryByRole("button", { name: /^Train a verified example$/ })).not.toBeInTheDocument();
    fireEvent.click(within(card).getByRole("button", { name: "See a verified example" }));
    expect(onBrowseExamples).toHaveBeenCalledOnce();
    expect(screen.getByText(validationOnly.name)).toBeVisible();
    expect(fetch.mock.calls.some(([path]) => String(path).includes("training-jobs"))).toBe(false);
    expect(fetch.mock.calls.some(([path]) => String(path) === "/jobs")).toBe(false);
  });

  it("shows a sanitized preparation failure and submits an explicit retry", async () => {
    const failed: RobotSetup = {
      id: "setup-failed", name: "Retry biped", robot_id: biped.id, robot_name: biped.name,
      robot_type: "biped", task_template_id: "stand-balance", scene_preset_id: "ramp-course",
      objects: [], digest: "9".repeat(64), created_at: "2026-07-13T00:00:00Z",
      readiness: "validated", trainable: false, reason: "preparation-failed",
      training_readiness: "preparation_failed", can_prepare: true, can_start_training: false,
      current_preparation: {
        id: "prepare-failed", setup_id: "setup-failed", robot_id: biped.id,
        fingerprint: "8".repeat(64), state: "failed", phase: "rollout",
        created_at: "2026-07-13T00:00:00Z", updated_at: "2026-07-13T00:01:00Z",
        failure_phase: "rollout", failure_reason: "state-runaway", report_sha256: null,
        report_ready: false, can_retry: true,
      },
    };
    const retryAttempt = {
      ...failed.current_preparation!, id: "prepare-retry", state: "queued" as const,
      phase: "queued", failure_phase: null, failure_reason: null, can_retry: false,
    };
    const fetch = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path === "/robot-samples") return json(samples);
      if (path === "/environment-catalog") return json(catalog);
      if (path === "/robots") return json([biped]);
      if (path === "/robot-setups") return json([failed]);
      if (path === `/robot-setups/${failed.id}`) return json(failed);
      if (path.endsWith("/preparations") && init?.method === "POST") return json(retryAttempt, 201);
      throw new Error(`unhandled ${init?.method ?? "GET"} ${path}`);
    });
    vi.stubGlobal("fetch", fetch);
    render(<MyRobots />);
    expect(await screen.findByText(/Preparation failed · State Runaway/)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Retry preparation" }));
    await waitFor(() => {
      const call = fetch.mock.calls.find(([path]) => String(path).endsWith("/preparations"));
      expect(String(call?.[1]?.body)).toBe(JSON.stringify({ retry: true }));
    });
  });
});
