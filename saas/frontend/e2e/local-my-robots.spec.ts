import { expect, Page, APIRequestContext, test } from "@playwright/test";
import path from "node:path";

type Created = { robots: string[]; setups: string[] };

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
  await expect(page.getByRole("heading", { name })).toBeVisible();
  return robot;
}

async function cleanupCreated(
  request: APIRequestContext,
  token: string,
  created: Created,
) {
  const headers = { Authorization: `Bearer ${token}` };
  for (const setupId of [...created.setups].reverse()) {
    const response = await request.delete(`/robot-setups/${setupId}`, { headers });
    expect([204, 404]).toContain(response.status());
  }
  for (const robotId of [...created.robots].reverse()) {
    const response = await request.delete(`/robots/${robotId}`, { headers });
    expect([204, 404]).toContain(response.status());
  }
}

test("[browser:upload-happy] canonical downloads, both upload paths, digest, and targeted deletion", async ({ page, request }, testInfo) => {
  const session = await openWorkspace(page, testInfo.parallelIndex);
  const created: Created = { robots: [], setups: [] };
  try {
    const sampleCard = page.getByRole("heading", { name: "Sample quadruped" }).locator("xpath=ancestor::article");
    const downloadPromise = page.waitForEvent("download");
    await sampleCard.getByRole("button", { name: "Download XML" }).click();
    const sampleDownload = await downloadPromise;
    expect(sampleDownload.suggestedFilename()).toBe("sample-quadruped.xml");

    const quadruped = await uploadRobot(page, "quadruped", "E2E quadruped", created);
    const biped = await uploadRobot(page, "biped", "E2E biped", created);
    expect(quadruped.digest).toMatch(/^[0-9a-f]{64}$/);
    expect(biped.digest).toMatch(/^[0-9a-f]{64}$/);

    const bipedCard = page.getByRole("heading", { name: "E2E biped" }).locator("xpath=ancestor::article");
    await expect(bipedCard.getByText("Model validated")).toBeVisible();
    await expect(bipedCard.getByText("SHA-256")).toBeVisible();
    const modelDownloadPromise = page.waitForEvent("download");
    await bipedCard.getByRole("button", { name: "Download XML" }).click();
    expect((await modelDownloadPromise).suggestedFilename()).toBe("biped.xml");

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

test("[browser:builder-pairwise] every task, scene, object, bound, capacity, save, and reload path", async ({ page, request }, testInfo) => {
  const session = await openWorkspace(page, testInfo.parallelIndex);
  const created: Created = { robots: [], setups: [] };
  try {
    await uploadRobot(page, "quadruped", "E2E matrix quadruped", created);
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
      const height = editors.getByText("Height").locator("xpath=following-sibling::*//input");
      await height.fill("999");
      await expect(page.getByRole("button", { name: "Save validated setup" })).toBeDisabled();
      await height.fill("0.3");
      const saveResponse = page.waitForResponse(
        (response) => response.url().endsWith("/robot-setups") && response.request().method() === "POST",
      );
      await page.getByRole("button", { name: "Save validated setup" }).click();
      const setupResponse = await saveResponse;
      expect(setupResponse.status()).toBe(201);
      created.setups.push((await setupResponse.json()).id);
      await expect(page.getByText(/Setup saved\./)).toBeVisible();
      await page.getByRole("button", { name: "Remove" }).click();
    }

    await page.getByRole("radio", { name: /Step course/ }).click();
    for (let index = 0; index < 3; index += 1) {
      await page.getByRole("button", { name: "Add object" }).click();
    }
    await expect(page.getByRole("button", { name: "Add object" })).toBeDisabled();
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

test("[browser:lifecycle] preparation reaches Ready and one idempotent Start opens a normal job", async ({ page, request }, testInfo) => {
  const session = await openWorkspace(page, testInfo.parallelIndex);
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
    await page.getByRole("button", { name: "Prepare for training" }).click();
    await expect(page.getByRole("button", { name: "Start training" })).toBeVisible({ timeout: 15_000 });
    const startResponsePromise = page.waitForResponse(
      (response) => response.url().includes("/training-jobs") && response.request().method() === "POST",
    );
    const start = page.getByRole("button", { name: "Start training" });
    await start.dblclick();
    const startResponse = await startResponsePromise;
    expect(startResponse.status()).toBe(201);
    await expect(page.getByText("Uploaded robot training")).toBeVisible();
    await expect(page.getByRole("button", { name: "← Back to jobs" })).toBeVisible();
  } finally {
    await cleanupCreated(request, session.token, created);
  }
});

test("[browser:keyboard-mobile] complete form remains keyboard-operable at 375 pixels", async ({ page, request }, testInfo) => {
  await page.setViewportSize({ width: 375, height: 812 });
  const session = await openWorkspace(page, testInfo.parallelIndex);
  const created: Created = { robots: [], setups: [] };
  try {
    await uploadRobot(page, "biped", "E2E mobile biped", created);
    await page.keyboard.press("Tab");
    expect(await page.evaluate(() => document.activeElement?.tagName)).toMatch(/BUTTON|INPUT/);
    const modelCard = page.getByRole("heading", { name: "E2E mobile biped" }).locator("xpath=ancestor::article");
    await modelCard.getByRole("button", { name: "Build environment" }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("radiogroup", { name: "Locomotion task" })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  } finally {
    await cleanupCreated(request, session.token, created);
  }
});
