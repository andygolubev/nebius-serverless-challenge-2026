import { expect, Page, test } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

type Created = { robots: string[]; setups: string[]; jobs: string[] };

const token = process.env.SAAS_SMOKE_BEARER_TOKEN ?? "";
const remotePreparation = process.env.SAAS_SMOKE_REMOTE_PREPARATION === "true";
const remoteTraining = process.env.SAAS_SMOKE_REMOTE_TRAINING === "true";
const preserveResources = process.env.SAAS_SMOKE_PRESERVE_RESOURCES === "true";

async function openWorkspace(page: Page, email: string) {
  await page.addInitScript(
    (session) => {
      localStorage.setItem("sim2policy.session", session.token);
      localStorage.setItem("sim2policy.email", session.email);
    },
    { token, email },
  );
  await page.goto("/");
  await page.getByRole("button", { name: "My Robots" }).click();
  await expect(page.getByRole("heading", { name: "My Robots" })).toBeVisible();
}

async function writeOutcome(
  created: Created,
  deleted: Created,
  cleanup: "clean" | "preserved" | "failed",
) {
  const output = path.resolve(process.cwd(), "../../.form-validation-runs/deployed-result.json");
  await mkdir(path.dirname(output), { recursive: true });
  await writeFile(
    output,
    `${JSON.stringify(
      {
        schema_version: 1,
        run_id: process.env.SAAS_SMOKE_RUN_ID ?? "deployed-manual",
        base_url: process.env.SAAS_SMOKE_BASE_URL,
        cost_gates: {
          remote_preparation: remotePreparation ? "requested" : "not-run-cost-gated",
          remote_training: remoteTraining ? "requested" : "not-run-cost-gated",
        },
        resources: { created, deleted },
        cleanup: { status: cleanup },
      },
      null,
      2,
    )}\n`,
    "utf-8",
  );
}

test("[deployed:no-cost-smoke] validates every deployed form choice with exact-ID cleanup", async ({ page, request }) => {
  test.skip(remotePreparation || remoteTraining, "paid canary invocation runs only the explicit cost-gated case");
  expect(token, "SAAS_SMOKE_BEARER_TOKEN must be supplied through a masked environment secret").not.toBe("");
  expect(remotePreparation, "the no-cost smoke refuses remote preparation").toBeFalsy();
  expect(remoteTraining, "the no-cost smoke refuses remote training").toBeFalsy();
  const headers = { Authorization: `Bearer ${token}` };
  const me = await request.get("/me", { headers });
  expect(me.status()).toBe(200);
  const email = (await me.json()).email as string;
  const created: Created = { robots: [], setups: [], jobs: [] };
  const deleted: Created = { robots: [], setups: [], jobs: [] };
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

    const samplesResponse = await request.get("/robot-samples", { headers });
    expect(samplesResponse.status()).toBe(200);
    const samples = await samplesResponse.json();
    await openWorkspace(page, email);
    const runPrefix = `Codex form smoke ${Date.now().toString(36)}`;
    for (const type of ["quadruped", "biped"] as const) {
      const sample = samples.find((item: { robot_type: string }) => item.robot_type === type);
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
      const first = editor.locator('input[type="number"]').first();
      const maximum = Number(await first.getAttribute("max"));
      await first.fill(String(maximum + 1));
      await expect(page.getByRole("button", { name: "Save validated setup" })).toBeDisabled();
      await first.fill(String(object.parameters[0].default));
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
    await page.reload();
    await page.getByRole("button", { name: "My Robots" }).click();
    await expect(page.getByRole("heading", { name: `${runPrefix} setup` })).toBeVisible();
    expect(remotePreparation).toBeFalsy();
    await expect(page.getByRole("button", { name: "Prepare for training" })).toBeVisible();
  } finally {
    if (!preserveResources) {
      for (const setupId of [...created.setups].reverse()) {
        const response = await request.delete(`/robot-setups/${setupId}`, { headers });
        if ([204, 404].includes(response.status())) deleted.setups.push(setupId);
      }
      for (const robotId of [...created.robots].reverse()) {
        const response = await request.delete(`/robots/${robotId}`, { headers });
        if ([204, 404].includes(response.status())) deleted.robots.push(robotId);
      }
      cleanup =
        deleted.setups.length === created.setups.length &&
        deleted.robots.length === created.robots.length
          ? "clean"
          : "failed";
    }
    await writeOutcome(created, deleted, cleanup);
  }
  expect(cleanup).not.toBe("failed");
});

test("[deployed:remote-cost-gates] remote work is never implicit", async ({ page, request }) => {
  test.skip(!remotePreparation && !remoteTraining, "not-run-cost-gated");
  expect(token).not.toBe("");
  if (remoteTraining) {
    expect(remotePreparation, "remote training requires SAAS_SMOKE_REMOTE_PREPARATION=true").toBeTruthy();
  }
  // The no-cost suite creates and removes its own resources. Paid canaries require an
  // operator-owned retained setup and a separate provider audit, so this test refuses
  // to infer those authorities from the browser session alone.
  expect(process.env.SAAS_SMOKE_RETAINED_SETUP_ID).toBeTruthy();
  expect(process.env.SAAS_SMOKE_PROVIDER_AUDIT_RUNBOOK_ACK).toBe("true");
  const headers = { Authorization: `Bearer ${token}` };
  const setupId = process.env.SAAS_SMOKE_RETAINED_SETUP_ID!;
  const setupResponse = await request.get(`/robot-setups/${setupId}`, { headers });
  expect(setupResponse.status()).toBe(200);
  const me = await request.get("/me", { headers });
  await openWorkspace(page, (await me.json()).email);
  const setup = await setupResponse.json();
  const card = page.getByRole("heading", { name: setup.name }).locator("xpath=ancestor::article");
  const prepareResponse = page.waitForResponse(
    (response) => response.url().includes("/preparations") && response.request().method() === "POST",
  );
  await card.getByRole("button", { name: /Prepare for training|Retry preparation/ }).click();
  expect((await prepareResponse).status()).toBe(201);
  await expect(card.getByRole("button", { name: "Start training" })).toBeVisible({ timeout: 12 * 60_000 });
  if (remoteTraining) {
    const startResponse = page.waitForResponse(
      (response) => response.url().includes("/training-jobs") && response.request().method() === "POST",
    );
    await card.getByRole("button", { name: "Start training" }).click();
    expect((await startResponse).status()).toBe(201);
    await expect(page.getByText("Uploaded robot training")).toBeVisible();
  }
});
