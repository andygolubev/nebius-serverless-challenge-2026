import { expect, Page, test, type APIRequestContext } from "@playwright/test";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

type ResourceIds = { robots: string[]; setups: string[]; preparations: string[]; jobs: string[] };
type CleanupStatus = "clean" | "preserved" | "failed" | "provider-audit-pending";
type CostGateStatus = "not-run-cost-gated" | "passed" | "failed";
type ProviderAudit = {
  schema_version: 1;
  run_id: string;
  audited_saas_resource_ids: string[];
  audited_scopes: string[];
  provider_resources: Array<{ kind: string; id: string; state: string }>;
  remaining_active_resources: Array<{ kind: string; id: string }>;
  cleanup_status: "clean";
};

const token = process.env.SAAS_SMOKE_BEARER_TOKEN ?? "";
const remotePreparation = process.env.SAAS_SMOKE_REMOTE_PREPARATION === "true";
const remoteTraining = process.env.SAAS_SMOKE_REMOTE_TRAINING === "true";
const preserveResources = process.env.SAAS_SMOKE_PRESERVE_RESOURCES === "true";
const runId = process.env.SAAS_SMOKE_RUN_ID ?? "deployed-manual";
const baseUrl = process.env.SAAS_SMOKE_BASE_URL ?? "";
const approvedOrigin = "https://sim-policy-trainer-challenge.info";
const evidenceRoot = path.resolve(process.cwd(), "../../.form-validation-runs");
const requiredAuditScopes = ["ai-jobs", "instances", "disks", "public-ips", "security-rules"];

function sanitizedFailure(error: unknown): string {
  if (error instanceof Error) return error.name;
  return "unknown-error";
}

function expectApprovedOrigin() {
  const parsed = new URL(baseUrl);
  expect(parsed.origin).toBe(approvedOrigin);
  expect(parsed.username).toBe("");
  expect(parsed.password).toBe("");
  expect(parsed.pathname).toBe("/");
  expect(parsed.search).toBe("");
  expect(parsed.hash).toBe("");
}

function expectRepresentativeSetup(setup: Record<string, unknown>) {
  expect(
    {
      robot_type: setup.robot_type,
      task_template_id: setup.task_template_id,
      scene_preset_id: setup.scene_preset_id,
      object_count: Array.isArray(setup.objects) ? setup.objects.length : -1,
    },
    "paid canaries are limited to the fixed quadruped/stand/flat/no-object representative",
  ).toEqual({
    robot_type: "quadruped",
    task_template_id: "stand-balance",
    scene_preset_id: "flat-arena",
    object_count: 0,
  });
}

async function readProviderAudit(requiredIds: string[]): Promise<ProviderAudit> {
  const auditPath = process.env.SAAS_SMOKE_PROVIDER_AUDIT_FILE;
  expect(auditPath, "paid gates require a post-run provider audit JSON file").toBeTruthy();
  const resolvedAuditPath = path.resolve(auditPath!);
  expect(
    resolvedAuditPath.startsWith(`${evidenceRoot}${path.sep}`),
    "the external audit input must stay outside the publishable evidence directory",
  ).toBeFalsy();
  const requestedTimeout = Number(process.env.SAAS_SMOKE_PROVIDER_AUDIT_TIMEOUT_MS ?? 15 * 60_000);
  const timeout = Math.min(Math.max(requestedTimeout || 15 * 60_000, 10_000), 30 * 60_000);
  const deadline = Date.now() + timeout;
  let audit: ProviderAudit | undefined;
  while (Date.now() < deadline) {
    try {
      audit = JSON.parse(await readFile(resolvedAuditPath, "utf-8")) as ProviderAudit;
      if (audit.run_id === runId && requiredIds.every((id) => audit!.audited_saas_resource_ids.includes(id))) {
        break;
      }
    } catch {
      // The operator/provider auditor may write the file after the terminal state.
    }
    await new Promise((resolve) => setTimeout(resolve, 5_000));
  }
  expect(audit, "provider audit did not arrive before the bounded audit timeout").toBeDefined();
  expect(audit!.schema_version).toBe(1);
  expect(audit!.run_id).toBe(runId);
  expect(audit!.cleanup_status).toBe("clean");
  expect(audit!.remaining_active_resources).toEqual([]);
  expect(new Set(audit!.audited_scopes)).toEqual(new Set(requiredAuditScopes));
  expect(requiredIds.every((id) => audit!.audited_saas_resource_ids.includes(id))).toBeTruthy();
  expect(audit!.provider_resources.length, "provider audit must enumerate correlated resources").toBeGreaterThan(0);
  expect(
    audit!.provider_resources.every((resource) =>
      /^(succeeded|failed|cancelled|deleted|stopped|terminal)$/i.test(resource.state),
    ),
    "every correlated provider resource must be terminal, stopped, or deleted",
  ).toBeTruthy();
  return audit!;
}

async function requireCheapGate() {
  const cheapGatePath = process.env.SAAS_SMOKE_CHEAP_GATE_FILE;
  expect(cheapGatePath, "paid gates require the sanitized result from a clean no-cost run").toBeTruthy();
  const result = JSON.parse(await readFile(cheapGatePath!, "utf-8")) as {
    schema_version?: number;
    run_id?: string;
    base_url?: string;
    cost_gates?: Record<string, string>;
    cleanup?: { status?: string };
    diagnostic?: string;
  };
  expect(result.schema_version).toBe(1);
  expect(result.run_id).toBe(runId);
  expect(result.base_url).toBe(baseUrl);
  expect(result.cleanup?.status).toBe("clean");
  expect(result.cost_gates).toEqual({
    remote_preparation: "not-run-cost-gated",
    remote_training: "not-run-cost-gated",
  });
  expect(result.diagnostic).toBeUndefined();
}

async function openWorkspace(page: Page, email: string) {
  await page.addInitScript(
    (session) => {
      localStorage.setItem("sim2policy.session", session.token);
      localStorage.setItem("sim2policy.email", session.email);
    },
    { token, email },
  );
  await page.goto("/");
  await page.getByRole("button", { name: "My Robots", exact: true }).click();
  await expect(page.getByRole("heading", { name: "My Robots" })).toBeVisible();
}

async function writeOutcome(
  created: ResourceIds,
  deleted: ResourceIds,
  cleanup: CleanupStatus,
  options: {
    filename?: string;
    costGates?: { remote_preparation: CostGateStatus; remote_training: CostGateStatus };
    diagnostic?: string;
    providerAudit?: ProviderAudit;
    retained?: ResourceIds;
  } = {},
) {
  const output = path.join(evidenceRoot, options.filename ?? "deployed-result.json");
  await mkdir(evidenceRoot, { recursive: true });
  await writeFile(
    output,
    `${JSON.stringify(
      {
        schema_version: 1,
        run_id: runId,
        base_url: process.env.SAAS_SMOKE_BASE_URL,
        cost_gates: options.costGates ?? {
          remote_preparation: "not-run-cost-gated",
          remote_training: "not-run-cost-gated",
        },
        resources: {
          created,
          deleted,
          retained: options.retained ?? { robots: [], setups: [], preparations: [], jobs: [] },
        },
        cleanup: { status: cleanup },
        diagnostic: options.diagnostic,
        provider_audit: options.providerAudit
          ? {
              status: options.providerAudit.cleanup_status,
              audited_scopes: options.providerAudit.audited_scopes,
              correlated_resource_count: options.providerAudit.provider_resources.length,
              remaining_active_count: options.providerAudit.remaining_active_resources.length,
            }
          : { status: remotePreparation || remoteTraining ? "pending" : "not-applicable-no-cost" },
      },
      null,
      2,
    )}\n`,
    "utf-8",
  );
}

async function writeProviderAuditRequest(gate: "preparation" | "training", resourceIds: string[]) {
  await mkdir(evidenceRoot, { recursive: true });
  await writeFile(
    path.join(evidenceRoot, `provider-audit-request-${gate}.json`),
    `${JSON.stringify(
      {
        schema_version: 1,
        run_id: runId,
        gate,
        audited_saas_resource_ids: resourceIds,
        required_scopes: requiredAuditScopes,
        required_result: "zero active resources created by this run",
      },
      null,
      2,
    )}\n`,
    "utf-8",
  );
}

async function deleteAndVerify(
  request: APIRequestContext,
  headers: Record<string, string>,
  kind: "robots" | "robot-setups",
  id: string,
): Promise<boolean> {
  try {
    const response = await request.delete(`/${kind}/${id}`, { headers });
    if (![204, 404].includes(response.status())) return false;
    return (await request.get(`/${kind}/${id}`, { headers })).status() === 404;
  } catch {
    return false;
  }
}

test("[deployed:no-cost-smoke] validates every deployed form choice with exact-ID cleanup", async ({ page, request }) => {
  test.skip(remotePreparation || remoteTraining, "paid canary invocation runs only the explicit cost-gated case");
  expectApprovedOrigin();
  expect(token, "SAAS_SMOKE_BEARER_TOKEN must be supplied through a masked environment secret").not.toBe("");
  expect(remotePreparation, "the no-cost smoke refuses remote preparation").toBeFalsy();
  expect(remoteTraining, "the no-cost smoke refuses remote training").toBeFalsy();
  const headers = { Authorization: `Bearer ${token}` };
  const me = await request.get("/me", { headers });
  expect(me.status()).toBe(200);
  const email = (await me.json()).email as string;
  const created: ResourceIds = { robots: [], setups: [], preparations: [], jobs: [] };
  const deleted: ResourceIds = { robots: [], setups: [], preparations: [], jobs: [] };
  const remoteMutations: string[] = [];
  page.on("request", (browserRequest) => {
    if (
      browserRequest.method() === "POST" &&
      /\/(preparations|training-jobs)$/.test(new URL(browserRequest.url()).pathname)
    ) {
      remoteMutations.push(new URL(browserRequest.url()).pathname);
    }
  });
  let cleanup: "clean" | "preserved" | "failed" = preserveResources ? "preserved" : "failed";
  try {
    const catalogResponse = await request.get("/environment-catalog", { headers });
    expect(catalogResponse.status()).toBe(200);
    const catalog = await catalogResponse.json();
    expect(catalog.task_templates.map((item: { id: string }) => item.id)).toEqual([
      "stand-balance",
      "walk-forward",
      "recover-from-fall",
    ]);
    expect(catalog.scene_presets).toHaveLength(4);
    expect(catalog.object_types).toHaveLength(4);
    expect(catalog.object_types.flatMap((item: { parameters: unknown[] }) => item.parameters)).toHaveLength(28);
    const existingRobots = await request.get("/robots", { headers });
    const existingSetups = await request.get("/robot-setups", { headers });
    expect(existingRobots.status()).toBe(200);
    expect(existingSetups.status()).toBe(200);
    expect((await existingRobots.json()).length, "tenant needs room for two smoke models").toBeLessThanOrEqual(18);
    expect((await existingSetups.json()).length, "tenant needs room for one smoke setup").toBeLessThan(catalog.max_setups);

    const samplesResponse = await request.get("/robot-samples", { headers });
    expect(samplesResponse.status()).toBe(200);
    const samples = await samplesResponse.json();
    await openWorkspace(page, email);
    const runPrefix = `Codex form smoke ${Date.now().toString(36)}`;
    for (const type of ["quadruped", "biped"] as const) {
      const sample = samples.find((item: { robot_type: string }) => item.robot_type === type);
      if (!sample) throw new Error(`deployed sample catalog is missing ${type}`);
      const raw = await request.get(`/robot-samples/${sample.id}`, { headers });
      expect(raw.status()).toBe(200);
      await page.getByLabel("Robot name").fill(`${runPrefix} ${type}`);
      await page.getByRole("radio", { name: type === "biped" ? "Biped" : "Quadruped" }).check({ force: true });
      await page.getByLabel("MJCF XML").setInputFiles({
        name: sample.filename,
        mimeType: "application/xml",
        buffer: await raw.body(),
      });
      const uploadResponse = page.waitForResponse(
        (response) => response.url().endsWith("/robots") && response.request().method() === "POST",
      );
      await page.getByRole("button", { name: "Validate model" }).click();
      const response = await uploadResponse;
      expect(response.status()).toBe(201);
      const robot = await response.json();
      created.robots.push(robot.id);
      expect(robot.digest).toBe(sample.digest);
      await expect(page.getByRole("heading", { name: `${runPrefix} ${type}` })).toBeVisible();
    }

    const bipedCard = page
      .getByRole("heading", { name: `${runPrefix} biped` })
      .locator("xpath=ancestor::article");
    await bipedCard.getByRole("button", { name: "Build environment" }).click();
    await expect(page.getByRole("radiogroup", { name: "Locomotion task" }).getByRole("radio")).toHaveCount(2);
    await expect(page.getByRole("radio", { name: /Recover from a fall/ })).toHaveCount(0);
    await page.getByRole("button", { name: "Close builder" }).click();

    const quadrupedCard = page
      .getByRole("heading", { name: `${runPrefix} quadruped` })
      .locator("xpath=ancestor::article");
    await quadrupedCard.getByRole("button", { name: "Build environment" }).click();
    await expect(page.getByRole("radiogroup", { name: "Locomotion task" }).getByRole("radio")).toHaveCount(3);
    await expect(page.getByRole("radiogroup", { name: "Scene preset" }).getByRole("radio")).toHaveCount(4);
    await expect(page.getByLabel("Object type").getByRole("option")).toHaveCount(4);
    for (const scene of catalog.scene_presets) {
      await page.getByRole("radio", { name: new RegExp(scene.label) }).click();
    }
    for (const object of catalog.object_types) {
      await page.getByLabel("Object type").selectOption(object.id);
      await page.getByRole("button", { name: "Add object" }).click();
      const editor = page.locator(".object-editor");
      await expect(editor.locator('input[type="number"]')).toHaveCount(7);
      for (const parameter of object.parameters) {
        const input = editor.getByRole("spinbutton", { name: new RegExp(`^${parameter.label} `) });
        await input.fill("");
        await expect(input).toHaveAttribute("aria-invalid", "true");
        await input.fill(String(parameter.minimum));
        await expect(input).toHaveAttribute("aria-invalid", "false");
        await input.fill(String(parameter.maximum));
        await expect(input).toHaveAttribute("aria-invalid", "false");
        await input.fill(String(parameter.minimum - 1));
        await expect(page.getByRole("button", { name: "Save validated setup" })).toBeDisabled();
        await input.fill(String(parameter.maximum + 1));
        await expect(page.getByRole("button", { name: "Save validated setup" })).toBeDisabled();
        await input.fill(String(parameter.default));
        await expect(input).toHaveAttribute("aria-invalid", "false");
      }
      await page.getByRole("button", { name: "Remove" }).click();
    }

    await page.getByRole("radio", { name: /Walk forward/ }).click();
    await page.getByRole("radio", { name: /Flat arena/ }).click();
    await page.getByLabel("Setup name").fill(`${runPrefix} setup`);
    const setupResponsePromise = page.waitForResponse(
      (response) => response.url().endsWith("/robot-setups") && response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Save validated setup" }).click();
    const setupResponse = await setupResponsePromise;
    expect(setupResponse.status()).toBe(201);
    const setup = await setupResponse.json();
    created.setups.push(setup.id);
    expect(setup.reason).toBe("not-prepared");
    expect(setup.training_readiness).toBe("not_prepared");
    expect(setup.objects).toEqual([]);
    expect(setup.digest).toMatch(/^[0-9a-f]{64}$/);
    await page.reload();
    await page.getByRole("button", { name: "My Robots", exact: true }).click();
    await expect(page.getByRole("heading", { name: `${runPrefix} setup` })).toBeVisible();
    await expect(page.getByText("Preparation required before training").first()).toBeVisible();
    expect(remotePreparation).toBeFalsy();
    await expect(page.getByRole("button", { name: "Prepare for training" })).toBeVisible();

    const setupCard = page
      .getByRole("heading", { name: `${runPrefix} setup` })
      .locator("xpath=ancestor::article");
    await setupCard.getByRole("button", { name: "Delete setup" }).click();
    if (preserveResources) {
      await setupCard.getByRole("button", { name: "Cancel" }).click();
    } else {
      const setupDeleteResponse = page.waitForResponse(
        (response) => response.url().endsWith(`/robot-setups/${setup.id}`) && response.request().method() === "DELETE",
      );
      await setupCard.getByRole("button", { name: "Delete", exact: true }).click();
      expect((await setupDeleteResponse).status()).toBe(204);
      await expect(page.getByRole("heading", { name: `${runPrefix} setup` })).toHaveCount(0);
      expect((await request.get(`/robot-setups/${setup.id}`, { headers })).status()).toBe(404);
      deleted.setups.push(setup.id);
    }

    const bipedCardAfterReload = page
      .getByRole("heading", { name: `${runPrefix} biped` })
      .locator("xpath=ancestor::article");
    const bipedId = created.robots[1];
    await bipedCardAfterReload.getByRole("button", { name: "Delete model" }).click();
    if (preserveResources) {
      await bipedCardAfterReload.getByRole("button", { name: "Cancel" }).click();
    } else {
      const robotDeleteResponse = page.waitForResponse(
        (response) => response.url().endsWith(`/robots/${bipedId}`) && response.request().method() === "DELETE",
      );
      await bipedCardAfterReload.getByRole("button", { name: "Delete", exact: true }).click();
      expect((await robotDeleteResponse).status()).toBe(204);
      await expect(page.getByRole("heading", { name: `${runPrefix} biped` })).toHaveCount(0);
      expect((await request.get(`/robots/${bipedId}`, { headers })).status()).toBe(404);
      deleted.robots.push(bipedId);
    }
  } finally {
    try {
      if (!preserveResources) {
        for (const setupId of [...created.setups].reverse()) {
          if (!deleted.setups.includes(setupId) && await deleteAndVerify(request, headers, "robot-setups", setupId)) {
            deleted.setups.push(setupId);
          }
        }
        for (const robotId of [...created.robots].reverse()) {
          if (!deleted.robots.includes(robotId) && await deleteAndVerify(request, headers, "robots", robotId)) {
            deleted.robots.push(robotId);
          }
        }
        cleanup =
          deleted.setups.length === created.setups.length &&
          deleted.robots.length === created.robots.length &&
          remoteMutations.length === 0
            ? "clean"
            : "failed";
      }
    } finally {
      if (remoteMutations.length > 0) cleanup = "failed";
      await writeOutcome(created, deleted, cleanup, {
        diagnostic: remoteMutations.length === 0 ? undefined : "unexpected-remote-mutation",
        retained: preserveResources ? created : undefined,
      });
    }
  }
  expect(remoteMutations).toEqual([]);
  expect(cleanup).not.toBe("failed");
});

test("[deployed:remote-preparation] runs one bounded preparation and requires provider audit", async ({ page, request }) => {
  test.setTimeout(45 * 60_000);
  test.skip(!remotePreparation, "not-run-cost-gated");
  expectApprovedOrigin();
  await requireCheapGate();
  expect(token).not.toBe("");
  const setupId = process.env.SAAS_SMOKE_RETAINED_SETUP_ID ?? "";
  expect(setupId, "remote preparation requires one operator-retained eligible setup").not.toBe("");
  const headers = { Authorization: `Bearer ${token}` };
  const created: ResourceIds = { robots: [], setups: [], preparations: [], jobs: [] };
  const deleted: ResourceIds = { robots: [], setups: [], preparations: [], jobs: [] };
  let preparationId = "";
  let passed = false;
  let diagnostic: string | undefined;
  let providerAudit: ProviderAudit | undefined;
  let auditFailure: unknown;
  try {
    const setupResponse = await request.get(`/robot-setups/${setupId}`, { headers });
    expect(setupResponse.status()).toBe(200);
    const setup = await setupResponse.json();
    expectRepresentativeSetup(setup);
    expect(setup.can_prepare, "retained canary setup must be eligible and not already preparing").toBeTruthy();
    expect(setup.latest_training_job, "representative setup must not already own a paid job").toBeNull();
    const me = await request.get("/me", { headers });
    expect(me.status()).toBe(200);
    await openWorkspace(page, (await me.json()).email);
    const card = page.getByRole("heading", { name: setup.name }).locator("xpath=ancestor::article");
    const prepareResponsePromise = page.waitForResponse(
      (response) => response.url().endsWith(`/robot-setups/${setupId}/preparations`) && response.request().method() === "POST",
    );
    await card.getByRole("button", { name: /Prepare for training|Retry preparation/ }).click();
    const prepareResponse = await prepareResponsePromise;
    expect(prepareResponse.status()).toBe(201);
    const attempt = await prepareResponse.json();
    preparationId = attempt.id;
    created.preparations.push(preparationId);
    await writeProviderAuditRequest("preparation", [preparationId]);

    const deadline = Date.now() + 12 * 60_000;
    let terminal = attempt;
    while (!new Set(["accepted", "failed"]).has(terminal.state) && Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 10_000));
      const latest = await request.get(`/robot-setups/${setupId}/preparations/latest`, { headers });
      expect(latest.status()).toBe(200);
      terminal = await latest.json();
    }
    expect(["accepted", "failed"]).toContain(terminal.state);
    expect(terminal.state, `preparation failed in sanitized phase ${terminal.failure_phase ?? "unknown"}`).toBe("accepted");
    expect(terminal.report_ready).toBeTruthy();
    passed = true;
  } catch (error) {
    diagnostic = sanitizedFailure(error);
  } finally {
    if (preparationId) {
      try {
        providerAudit = await readProviderAudit([preparationId]);
      } catch (error) {
        auditFailure = error;
      }
    }
    await writeOutcome(created, deleted, passed && providerAudit ? "clean" : "provider-audit-pending", {
      filename: "deployed-remote-preparation.json",
      costGates: {
        remote_preparation: passed && providerAudit ? "passed" : "failed",
        remote_training: "not-run-cost-gated",
      },
      diagnostic: diagnostic ?? (auditFailure ? sanitizedFailure(auditFailure) : undefined),
      providerAudit,
      retained: providerAudit ? created : undefined,
    });
  }
  expect(auditFailure, "provider audit and cleanup must complete before the gate passes").toBeUndefined();
  expect(diagnostic, "remote preparation must reach accepted with a ready report").toBeUndefined();
});

test("[deployed:remote-training] runs one fixed job with fresh idempotency and requires provider audit", async ({ page, request }) => {
  test.setTimeout(90 * 60_000);
  test.skip(!remoteTraining, "not-run-cost-gated");
  expectApprovedOrigin();
  await requireCheapGate();
  expect(remotePreparation, "remote training requires the preparation gate in the same bounded run").toBeTruthy();
  expect(token).not.toBe("");
  const setupId = process.env.SAAS_SMOKE_RETAINED_SETUP_ID ?? "";
  expect(setupId, "remote training requires the prepared operator-retained setup").not.toBe("");
  const headers = { Authorization: `Bearer ${token}` };
  const created: ResourceIds = { robots: [], setups: [], preparations: [], jobs: [] };
  const deleted: ResourceIds = { robots: [], setups: [], preparations: [], jobs: [] };
  let preparationId = "";
  let preparationReady = false;
  let passed = false;
  let diagnostic: string | undefined;
  let providerAudit: ProviderAudit | undefined;
  let auditFailure: unknown;
  try {
    const setupResponse = await request.get(`/robot-setups/${setupId}`, { headers });
    expect(setupResponse.status()).toBe(200);
    const setup = await setupResponse.json();
    expectRepresentativeSetup(setup);
    expect(setup.can_start_training, "training gate requires the current accepted preparation").toBeTruthy();
    expect(setup.latest_training_job, "training gate permits only one new representative job").toBeNull();
    preparationReady = true;
    preparationId = setup.current_preparation?.id ?? "";
    expect(preparationId).not.toBe("");
    created.preparations.push(preparationId);
    const me = await request.get("/me", { headers });
    expect(me.status()).toBe(200);
    await openWorkspace(page, (await me.json()).email);
    const card = page.getByRole("heading", { name: setup.name }).locator("xpath=ancestor::article");
    const startResponsePromise = page.waitForResponse(
      (response) => response.url().endsWith(`/robot-setups/${setupId}/training-jobs`) && response.request().method() === "POST",
    );
    await card.getByRole("button", { name: "Start training" }).click();
    const startResponse = await startResponsePromise;
    expect(startResponse.status()).toBe(201);
    const requestBody = startResponse.request().postDataJSON() as { idempotency_key?: string };
    expect(requestBody.idempotency_key).toMatch(/^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$/);
    const job = await startResponse.json();
    created.jobs.push(job.id);
    await writeProviderAuditRequest("training", [preparationId, job.id]);
    await expect(page.getByText("Uploaded robot training")).toBeVisible();

    const deadline = Date.now() + 60 * 60_000;
    let terminal = job;
    while (!new Set(["completed", "failed"]).has(terminal.status) && Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 15_000));
      const latest = await request.get(`/jobs/${job.id}`, { headers });
      expect(latest.status()).toBe(200);
      terminal = await latest.json();
    }
    expect(["completed", "failed"]).toContain(terminal.status);
    if (terminal.status === "completed") {
      const artifacts = await request.get(`/jobs/${job.id}/artifacts`, { headers });
      expect(artifacts.status()).toBe(200);
      expect((await artifacts.json()).artifacts.length).toBeGreaterThan(0);
    }
    expect(terminal.status, `training failed in sanitized phase ${terminal.failure_phase ?? "unknown"}`).toBe("completed");
    passed = true;
  } catch (error) {
    diagnostic = sanitizedFailure(error);
  } finally {
    if (preparationId && created.jobs.length === 1) {
      try {
        providerAudit = await readProviderAudit([preparationId, created.jobs[0]]);
      } catch (error) {
        auditFailure = error;
      }
    }
    await writeOutcome(created, deleted, passed && providerAudit ? "clean" : "provider-audit-pending", {
      filename: "deployed-remote-training.json",
      costGates: {
        remote_preparation: preparationReady ? "passed" : "failed",
        remote_training: passed && providerAudit ? "passed" : "failed",
      },
      diagnostic: diagnostic ?? (auditFailure ? sanitizedFailure(auditFailure) : undefined),
      providerAudit,
      retained: providerAudit ? created : undefined,
    });
  }
  expect(auditFailure, "provider audit and cleanup must complete before the gate passes").toBeUndefined();
  expect(diagnostic, "remote training must complete with validated artifacts").toBeUndefined();
});
