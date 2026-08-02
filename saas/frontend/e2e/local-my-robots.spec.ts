import { createHash } from "node:crypto";
import { expect, Page, APIRequestContext, Download, test } from "@playwright/test";
import path from "node:path";

type Created = { robots: string[]; setups: string[] };
const localApiBaseUrl = "http://127.0.0.1:8000";

function workerSession(parallelIndex: number) {
  return {
    token: `form-validation-worker-${parallelIndex}`,
    email: `form-validation-worker-${parallelIndex}@example.test`,
  };
}

async function openWorkspace(page: Page, parallelIndex: number) {
  const current = workerSession(parallelIndex);
  await page.addInitScript((session) => {
    localStorage.setItem("sim2policy.session", session.token);
    localStorage.setItem("sim2policy.email", session.email);
  }, current);
  await page.goto("/");
  await page.getByRole("button", { name: "My Robots" }).click();
  await expect(page.getByRole("heading", { name: "My Robots" })).toBeVisible();
  return current;
}

async function uploadRobot(
  page: Page,
  type: "quadruped" | "biped",
  name: string,
  created: Created,
) {
  const samplePath = path.resolve(
    process.cwd(),
    `../samples/robots/sample-${type}.xml`,
  );
  await page.getByLabel("Robot name").fill(name);
  await page.getByRole("radio", { name: type === "biped" ? "Biped" : "Quadruped" }).check({ force: true });
  await page.getByLabel("MJCF XML").setInputFiles(samplePath);
  const responsePromise = page.waitForResponse(
    (response) => response.url().endsWith("/robots") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Validate model" }).click();
  const response = await responsePromise;
  expect(response.status()).toBe(201);
  const robot = await response.json();
  created.robots.push(robot.id);
  await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
  return robot;
}

async function cleanupCreated(
  request: APIRequestContext,
  token: string,
  created: Created,
) {
  const headers = { Authorization: `Bearer ${token}` };
  for (const setupId of [...created.setups].reverse()) {
    const response = await request.delete(`${localApiBaseUrl}/robot-setups/${setupId}`, { headers });
    expect([204, 404]).toContain(response.status());
  }
  for (const robotId of [...created.robots].reverse()) {
    const response = await request.delete(`${localApiBaseUrl}/robots/${robotId}`, { headers });
    expect([204, 404]).toContain(response.status());
  }
}

async function downloadSha256(download: Download) {
  const stream = await download.createReadStream();
  const hash = createHash("sha256");
  for await (const chunk of stream) hash.update(chunk);
  return hash.digest("hex");
}

async function setHarnessModes(
  request: APIRequestContext,
  token: string,
  modes: { preparation?: "success" | "fail-once" | "hold"; training?: "success" | "fail-once" },
) {
  const response = await request.post(`${localApiBaseUrl}/_validation/modes`, {
    headers: { Authorization: `Bearer ${token}` },
    data: modes,
  });
  expect(response.status()).toBe(200);
}

async function saveOpenBuilder(
  page: Page,
  created: Created,
  options: { name: string; task?: string; scene?: string },
) {
  await page.getByLabel("Setup name").fill(options.name);
  if (options.task) await page.getByRole("radio", { name: new RegExp(options.task) }).click();
  if (options.scene) await page.getByRole("radio", { name: new RegExp(options.scene) }).click();
  const responsePromise = page.waitForResponse(
    (response) => response.url().endsWith("/robot-setups") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Save validated setup" }).click();
  const response = await responsePromise;
  expect(response.status()).toBe(201);
  const setup = await response.json();
  created.setups.push(setup.id);
  return setup;
}

test("[browser:upload-happy] canonical downloads, both upload paths, digest, and targeted deletion", async ({ page, request }) => {
  const session = await openWorkspace(page, 0);
  const created: Created = { robots: [], setups: [] };
  try {
    const sampleCard = page.getByRole("heading", { name: "Sample quadruped" }).locator("xpath=ancestor::article");
    const downloadPromise = page.waitForEvent("download");
    await sampleCard.getByRole("button", { name: "Download XML" }).click();
    const sampleDownload = await downloadPromise;
    expect(sampleDownload.suggestedFilename()).toBe("sample-quadruped.xml");
    const samples = await request.get(`${localApiBaseUrl}/robot-samples`, {
      headers: { Authorization: `Bearer ${session.token}` },
    });
    expect(samples.status()).toBe(200);
    const sampleMetadata = (await samples.json()).find(
      (sample: { id: string }) => sample.id === "sample-quadruped",
    );
    expect(sampleMetadata).toBeTruthy();
    expect(await downloadSha256(sampleDownload)).toBe(sampleMetadata.digest);

    const quadruped = await uploadRobot(page, "quadruped", "E2E quadruped", created);
    const biped = await uploadRobot(page, "biped", "E2E biped", created);
    expect(quadruped.digest).toMatch(/^[0-9a-f]{64}$/);
    expect(biped.digest).toMatch(/^[0-9a-f]{64}$/);

    const bipedCard = page.getByRole("heading", { name: "E2E biped" }).locator("xpath=ancestor::article");
    await expect(bipedCard.getByText("Model validated")).toBeVisible();
    await expect(bipedCard.getByText("SHA-256")).toBeVisible();
    const modelDownloadPromise = page.waitForEvent("download");
    await bipedCard.getByRole("button", { name: "Download XML" }).click();
    const modelDownload = await modelDownloadPromise;
    expect(modelDownload.suggestedFilename()).toBe("sample-biped.xml");
    expect(await downloadSha256(modelDownload)).toBe(biped.digest);
    await bipedCard.getByRole("button", { name: "Build environment" }).click();
    await expect(page.getByRole("radiogroup", { name: "Locomotion task" }).getByRole("radio")).toHaveCount(2);
    await expect(page.getByRole("radio", { name: /Recover from a fall/ })).toHaveCount(0);
    await page.getByRole("button", { name: "Close builder" }).click();

    await bipedCard.getByRole("button", { name: "Delete model" }).click();
    await bipedCard.getByRole("button", { name: "Cancel" }).click();
    await expect(page.getByRole("heading", { name: "E2E biped" })).toBeVisible();
    await bipedCard.getByRole("button", { name: "Delete model" }).click();
    await bipedCard.getByRole("button", { name: "Delete" }).click();
    await expect(page.getByRole("heading", { name: "E2E biped" })).toHaveCount(0);
    created.robots = created.robots.filter((id) => id !== biped.id);
  } finally {
    await cleanupCreated(request, session.token, created);
  }
});

test("[browser:builder-pairwise] every task, scene, object, bound, capacity, save, and reload path", async ({ page, request }) => {
  test.setTimeout(120_000);
  const session = await openWorkspace(page, 1);
  const created: Created = { robots: [], setups: [] };
  try {
    const quadruped = await uploadRobot(page, "quadruped", "E2E matrix quadruped", created);
    const catalogResponse = await request.get("/environment-catalog", {
      headers: { Authorization: `Bearer ${session.token}` },
    });
    expect(catalogResponse.status()).toBe(200);
    const catalog = await catalogResponse.json();
    const modelCard = page.getByRole("heading", { name: "E2E matrix quadruped" }).locator("xpath=ancestor::article");
    await modelCard.getByRole("button", { name: "Build environment" }).click();
    for (const label of ["Stand and balance", "Walk forward", "Recover from a fall"]) {
      await expect(page.getByRole("radio", { name: new RegExp(label) })).toBeVisible();
    }
    const rows = [
      ["Recover from a fall", "Flat arena", "box"],
      ["Walk forward", "Ramp course", "ramp"],
      ["Stand and balance", "Hurdle course", "hurdle"],
      ["Walk forward", "Step course", "step"],
    ] as const;
    for (const [task, scene, objectType] of rows) {
      await page.getByRole("radio", { name: new RegExp(task) }).click();
      await page.getByRole("radio", { name: new RegExp(scene) }).click();
      await page.getByLabel("Object type").selectOption(objectType);
      await page.getByRole("button", { name: "Add object" }).click();
      const editors = page.locator(".object-editor");
      await expect(editors).toHaveCount(1);
      const numbers = editors.locator('input[type="number"]');
      await expect(numbers).toHaveCount(7);
      const object = catalog.object_types.find((item: { id: string }) => item.id === objectType);
      if (!object) throw new Error(`catalog object ${objectType} is missing`);
      for (const parameter of object.parameters) {
        const input = editors.getByRole("spinbutton", { name: new RegExp(`^${parameter.label} `) });
        await input.fill(String(parameter.minimum));
        await expect(input).toHaveAttribute("aria-invalid", "false");
        await input.fill(String(parameter.maximum));
        await input.fill("");
        await expect(input).toHaveAttribute("aria-invalid", "true");
        await input.fill(String(parameter.maximum + 1));
        await expect(page.getByRole("button", { name: "Save validated setup" })).toBeDisabled();
        await input.fill(String(parameter.default));
      }
      const saveResponse = page.waitForResponse(
        (response) => response.url().endsWith("/robot-setups") && response.request().method() === "POST",
      );
      await page.getByRole("button", { name: "Save validated setup" }).click();
      const setupResponse = await saveResponse;
      expect(setupResponse.status()).toBe(201);
      const setup = await setupResponse.json();
      created.setups.push(setup.id);
      const taskId =
        task === "Recover from a fall"
          ? "recover-from-fall"
          : task === "Walk forward"
            ? "walk-forward"
            : "stand-balance";
      const sceneId =
        scene === "Flat arena"
          ? "flat-arena"
          : scene === "Ramp course"
            ? "ramp-course"
            : scene === "Hurdle course"
              ? "hurdle-course"
              : "step-course";
      expect(setup.task_template_id).toBe(taskId);
      expect(setup.scene_preset_id).toBe(sceneId);
      const expectedObject = Object.fromEntries(
        object.parameters.map((parameter: { name: string; default: number }) => [parameter.name, parameter.default]),
      );
      expect(setupResponse.request().postDataJSON()).toEqual({
        name: "E2E matrix quadruped setup",
        robot_id: quadruped.id,
        task_template_id: taskId,
        scene_preset_id: sceneId,
        objects: [{ object_type: objectType, ...expectedObject }],
      });
      expect(setup.objects.filter((item: { source: string }) => item.source === "custom")).toEqual([
        { object_type: objectType, source: "custom", ...expectedObject },
      ]);
      await expect(page.getByText(/Setup saved\./)).toBeVisible();
      const preset = catalog.scene_presets.find((item: { label: string }) => item.label === scene);
      if (!preset) throw new Error(`catalog scene ${scene} is missing`);
      const available = catalog.max_objects - preset.objects.length;
      for (let index = 1; index < available; index += 1) {
        await page.getByRole("button", { name: "Add object" }).click();
      }
      await expect(page.getByRole("button", { name: "Add object" })).toBeDisabled();
      const removeButtons = page.getByRole("button", { name: "Remove" });
      while ((await removeButtons.count()) > 0) await removeButtons.first().click();
    }
    await page.getByRole("button", { name: "Close builder" }).click();
    await uploadRobot(page, "biped", "E2E matrix biped", created);
    const bipedCard = page.getByRole("heading", { name: "E2E matrix biped" }).locator("xpath=ancestor::article");
    await bipedCard.getByRole("button", { name: "Build environment" }).click();
    for (const [task, scene] of [
      ["Stand and balance", "Flat arena"],
      ["Walk forward", "Ramp course"],
    ] as const) {
      await saveOpenBuilder(page, created, {
        name: `E2E biped ${task}`,
        task,
        scene,
      });
    }
    await page.reload();
    await page.getByRole("button", { name: "My Robots" }).click();
    for (const setupId of created.setups) {
      const response = await request.get(`/robot-setups/${setupId}`, {
        headers: { Authorization: `Bearer ${session.token}` },
      });
      expect(response.status()).toBe(200);
    }
  } finally {
    await cleanupCreated(request, session.token, created);
  }
});

test("[browser:lifecycle] controlled success, failure, retry, stale, quota, and idempotent training paths", async ({ page, request }) => {
  test.setTimeout(120_000);
  const session = await openWorkspace(page, 2);
  const created: Created = { robots: [], setups: [] };
  try {
    await uploadRobot(page, "biped", "E2E lifecycle biped", created);
    const modelCard = page.getByRole("heading", { name: "E2E lifecycle biped" }).locator("xpath=ancestor::article");
    await modelCard.getByRole("button", { name: "Build environment" }).click();
    await page.getByRole("radio", { name: /Walk forward/ }).click();
    await page.getByRole("radio", { name: /Flat arena/ }).click();
    const setupResponsePromise = page.waitForResponse(
      (response) => response.url().endsWith("/robot-setups") && response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Save validated setup" }).click();
    const setupResponse = await setupResponsePromise;
    created.setups.push((await setupResponse.json()).id);
    const builder = page.locator(".builder");
    await builder.getByRole("button", { name: "Prepare for training" }).click();
    await expect(builder.getByRole("button", { name: "Start training" })).toBeVisible({ timeout: 15_000 });
    const startResponsePromise = page.waitForResponse(
      (response) => response.url().includes("/training-jobs") && response.request().method() === "POST",
    );
    const start = builder.getByRole("button", { name: "Start training" });
    await start.click();
    const startResponse = await startResponsePromise;
    expect(startResponse.status()).toBe(201);
    const startedJob = await startResponse.json();
    const repeatedStart = await request.post(
      `${localApiBaseUrl}/robot-setups/${created.setups[0]}/training-jobs`,
      {
        headers: { Authorization: `Bearer ${session.token}` },
        data: startResponse.request().postDataJSON(),
      },
    );
    expect(repeatedStart.status()).toBe(201);
    expect((await repeatedStart.json()).id).toBe(startedJob.id);
    await expect(page.getByText("Uploaded robot training")).toBeVisible();
    await expect(page.getByRole("button", { name: "← Back to jobs" })).toBeVisible();
    let terminalStatus = "";
    for (let attempt = 0; attempt < 24; attempt += 1) {
      const jobResponse = await request.get(`${localApiBaseUrl}/jobs/${startedJob.id}`, {
        headers: { Authorization: `Bearer ${session.token}` },
      });
      expect(jobResponse.status()).toBe(200);
      terminalStatus = (await jobResponse.json()).status;
      if (["completed", "failed"].includes(terminalStatus)) break;
      await page.waitForTimeout(250);
    }
    expect(terminalStatus).toBe("completed");
    const artifactsResponse = await request.get(
      `${localApiBaseUrl}/jobs/${startedJob.id}/artifacts`,
      { headers: { Authorization: `Bearer ${session.token}` } },
    );
    expect(artifactsResponse.status()).toBe(200);
    const artifacts = await artifactsResponse.json();
    expect(artifacts.status).toBe("completed");
    expect(artifacts.metrics).toBeTruthy();

    await page.getByRole("button", { name: "My Robots" }).click();
    const setupCard = page.getByRole("heading", { name: "E2E lifecycle biped setup" }).locator("xpath=ancestor::article");
    await expect(setupCard.getByRole("button", { name: "View completed result" })).toBeVisible();
    await expect(setupCard.getByRole("button", { name: "Start training" })).toHaveCount(0);
    await setupCard.getByRole("button", { name: "Train again" }).click();
    await setupCard.getByRole("button", { name: "Cancel" }).click();
    await expect(setupCard.getByRole("button", { name: "Train again" })).toBeVisible();

    const reusableModelCard = page
      .getByRole("heading", { name: "E2E lifecycle biped" })
      .locator("xpath=ancestor::article");
    await reusableModelCard.getByRole("button", { name: "Build environment" }).click();
    const failedSetup = await saveOpenBuilder(page, created, {
      name: "E2E failed preparation",
      task: "Walk forward",
      scene: "Ramp course",
    });
    await setHarnessModes(request, session.token, { preparation: "fail-once" });
    const failedBuilder = page.locator(".builder");
    await failedBuilder.getByRole("button", { name: "Prepare for training" }).click();
    const failedReadiness = failedBuilder.locator(".setup-training-actions").getByRole("status");
    await expect(failedReadiness).toContainText("Preparation failed");
    await expect(failedReadiness).toContainText("Render Probe Failed");
    await failedBuilder.getByRole("button", { name: "Retry preparation" }).click();
    await expect(failedBuilder.getByRole("button", { name: "Start training" })).toBeVisible({ timeout: 15_000 });

    const staleResponse = await request.post(
      `${localApiBaseUrl}/_validation/robot-setups/${failedSetup.id}/stale-preparation`,
      { headers: { Authorization: `Bearer ${session.token}` } },
    );
    expect(staleResponse.status()).toBe(200);
    await page.reload();
    await page.getByRole("button", { name: "My Robots" }).click();
    const staleCard = page
      .getByRole("heading", { name: "E2E failed preparation" })
      .locator("xpath=ancestor::article");
    await expect(staleCard.getByRole("status")).toContainText("Preparation required");
    await expect(staleCard.getByRole("button", { name: "Prepare for training" })).toBeEnabled();
    const staleStart = await request.post(
      `${localApiBaseUrl}/robot-setups/${failedSetup.id}/training-jobs`,
      {
        headers: { Authorization: `Bearer ${session.token}` },
        data: { idempotency_key: "browser-stale-start" },
      },
    );
    expect(staleStart.status()).toBe(409);

    const freshPreparationResponse = page.waitForResponse(
      (response) => response.url().endsWith(`/robot-setups/${failedSetup.id}/preparations`)
        && response.request().method() === "POST",
    );
    await staleCard.getByRole("button", { name: "Prepare for training" }).click();
    expect((await freshPreparationResponse).status()).toBe(201);
    let freshPreparationState = "queued";
    for (let poll = 0; poll < 60; poll += 1) {
      const latest = await request.get(
        `${localApiBaseUrl}/robot-setups/${failedSetup.id}/preparations/latest`,
        { headers: { Authorization: `Bearer ${session.token}` } },
      );
      expect(latest.status()).toBe(200);
      freshPreparationState = (await latest.json()).state;
      if (["accepted", "failed"].includes(freshPreparationState)) break;
      await page.waitForTimeout(250);
    }
    expect(freshPreparationState).toBe("accepted");
    const refreshedSetupResponse = await request.get(
      `${localApiBaseUrl}/robot-setups/${failedSetup.id}`,
      { headers: { Authorization: `Bearer ${session.token}` } },
    );
    expect(refreshedSetupResponse.status()).toBe(200);
    const refreshedSetup = await refreshedSetupResponse.json();
    expect(refreshedSetup.training_readiness).toBe("ready");
    expect(refreshedSetup.can_start_training).toBeTruthy();
    await page.reload();
    await page.getByRole("button", { name: "My Robots" }).click();
    await expect(staleCard.getByRole("button", { name: "Start training" })).toBeVisible();
    await setHarnessModes(request, session.token, { training: "fail-once" });
    await staleCard.getByRole("button", { name: "Start training" }).click();
    await expect(page.getByRole("alert").getByRole("heading", { name: "Failed during submission" })).toBeVisible();
    await expect(page.getByRole("alert")).toContainText("mock training submission failed");

    await page.getByRole("button", { name: "My Robots" }).click();
    const quotaModelCard = page
      .getByRole("heading", { name: "E2E lifecycle biped" })
      .locator("xpath=ancestor::article");
    await quotaModelCard.getByRole("button", { name: "Build environment" }).click();
    const firstQuotaSetup = await saveOpenBuilder(page, created, {
      name: "E2E held preparation",
      task: "Stand and balance",
      scene: "Flat arena",
    });
    const secondQuotaSetup = await saveOpenBuilder(page, created, {
      name: "E2E quota preparation",
      task: "Walk forward",
      scene: "Hurdle course",
    });
    await setHarnessModes(request, session.token, { preparation: "hold" });
    const heldCard = page
      .getByRole("heading", { name: firstQuotaSetup.name })
      .locator("xpath=ancestor::article");
    await heldCard.getByRole("button", { name: "Prepare for training" }).click();
    await expect(heldCard.getByRole("button", { name: "Preparing…" })).toBeDisabled();
    const quotaCard = page
      .getByRole("heading", { name: secondQuotaSetup.name })
      .locator("xpath=ancestor::article");
    await quotaCard.getByRole("button", { name: "Prepare for training" }).click();
    await expect(quotaCard.getByRole("alert")).toContainText("preparation capacity is currently in use");
  } finally {
    await cleanupCreated(request, session.token, created);
  }
});

test("[browser:keyboard-mobile] complete form remains keyboard-operable at 375 pixels", async ({ page, request }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  const session = await openWorkspace(page, 3);
  const created: Created = { robots: [], setups: [] };
  try {
    await uploadRobot(page, "biped", "E2E mobile biped", created);
    await page.keyboard.press("Tab");
    expect(await page.evaluate(() => document.activeElement?.tagName)).toMatch(/BUTTON|INPUT/);
    const modelCard = page.getByRole("heading", { name: "E2E mobile biped" }).locator("xpath=ancestor::article");
    await modelCard.getByRole("button", { name: "Build environment" }).focus();
    await page.keyboard.press("Enter");
    const builder = page.locator(".builder");
    await expect(builder.getByRole("radiogroup", { name: "Locomotion task" })).toBeVisible();
    await builder.getByLabel("Setup name").focus();
    await page.keyboard.press(process.platform === "darwin" ? "Meta+A" : "Control+A");
    await page.keyboard.type("E2E keyboard setup");
    const task = builder.getByRole("radio", { name: /Walk forward/ });
    await task.focus();
    await page.keyboard.press("Space");
    await expect(task).toHaveAttribute("aria-checked", "true");
    const scene = builder.getByRole("radio", { name: /Step course/ });
    await scene.focus();
    await page.keyboard.press("Space");
    await expect(scene).toHaveAttribute("aria-checked", "true");
    const objectType = builder.getByLabel("Object type");
    await objectType.focus();
    await page.keyboard.press("End");
    await expect(objectType).toHaveValue("step");
    await builder.getByRole("button", { name: "Add object" }).focus();
    await page.keyboard.press("Enter");
    const height = builder.getByRole("spinbutton", { name: /^Height / });
    await height.focus();
    await page.keyboard.press(process.platform === "darwin" ? "Meta+A" : "Control+A");
    await page.keyboard.type("999");
    await expect(height).toHaveAttribute("aria-invalid", "true");
    await expect(builder.getByRole("button", { name: "Save validated setup" })).toBeDisabled();
    await page.keyboard.press(process.platform === "darwin" ? "Meta+A" : "Control+A");
    await page.keyboard.type("0.2");
    await expect(height).toHaveAttribute("aria-invalid", "false");
    const setupResponsePromise = page.waitForResponse(
      (response) => response.url().endsWith("/robot-setups") && response.request().method() === "POST",
    );
    await builder.getByRole("button", { name: "Save validated setup" }).focus();
    await page.keyboard.press("Enter");
    const setupResponse = await setupResponsePromise;
    expect(setupResponse.status()).toBe(201);
    created.setups.push((await setupResponse.json()).id);
    await expect(builder.locator(".alert-success")).toContainText("Setup saved");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  } finally {
    await cleanupCreated(request, session.token, created);
  }
});
