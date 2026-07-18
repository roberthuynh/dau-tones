import { expect, test, type Page } from "@playwright/test";

async function installOfflineHarness(page: Page, baseURL: string) {
  const localOrigin = new URL(baseURL).origin;
  const externalRequests: string[] = [];

  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.addInitScript(() => {
    const state = window as typeof window & { __dauAudioPlayCount?: number };
    state.__dauAudioPlayCount = 0;
    HTMLMediaElement.prototype.play = async function play() {
      state.__dauAudioPlayCount = (state.__dauAudioPlayCount ?? 0) + 1;
      this.dispatchEvent(new Event("playing"));
    };
    HTMLMediaElement.prototype.pause = function pause() {};
  });
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== localOrigin) {
      externalRequests.push(url.href);
      await route.abort("blockedbyclient");
      return;
    }
    if (url.pathname.startsWith("/api/")) {
      await route.abort("connectionrefused");
      return;
    }
    await route.continue();
  });

  return externalRequests;
}

test("offline learner closes the Tone Shapes and Dialogue Practice loops", async ({ page, baseURL }) => {
  await page.setViewportSize({ width: 1366, height: 768 });
  const externalRequests = await installOfflineHarness(page, baseURL!);

  await page.goto("/");
  await expect(page.getByText("Add an OpenAI key for AI coaching", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "ma", exact: true })).toBeVisible();
  await expect(page.getByText("Northern profile: four acoustic families; the closest exact form remains visible.")).toBeVisible();
  await expect(page.getByRole("navigation", { name: "The six tones of ma" }).getByRole("button")).toHaveCount(6);
  await expect(page.getByRole("button", { name: "Record your tone" })).toBeVisible();
  await expect(page.locator("body")).not.toContainText("Cedar");
  await expect(page.locator("body")).not.toContainText("Cô Linh");

  const skipLink = page.getByRole("link", { name: "Skip to practice" });
  await skipLink.focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#main-content$/);

  await page.getByRole("button", { name: "✓ correct má", exact: true }).click();
  await expect(page.locator(".tone-verdict--correct")).toBeVisible();
  await expect(page.getByRole("heading", { name: /Correct(?: family)? · má · dấu sắc/ })).toBeVisible();
  await expect(page.getByText(/full contour stayed closest to sắc/i)).toBeVisible();

  const signatureDemo = page.getByRole("button", { name: /Phương → phường/ });
  await signatureDemo.focus();
  await page.keyboard.press("Enter");
  await expect(page.locator(".tone-verdict--wrong")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Heard: phường · dấu huyền · falling" })).toBeVisible();
  await expect(page.getByText("Phương, a woman's name", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("urban ward", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Hold your chin steady and carry Phương straight across without letting the ending sink.")).toBeVisible();
  await expect(page.locator(".next-decision")).toContainText("Contrast the level name with phường while that accidental fall is fresh.");

  await page.getByRole("button", { name: "Finish", exact: true }).click();
  const summary = page.getByRole("dialog", { name: "Your tones, in focus." });
  await expect(summary).toBeVisible();
  const downloadPromise = page.waitForEvent("download");
  await summary.getByRole("button", { name: "Share summary card" }).click();
  expect((await downloadPromise).suggestedFilename()).toBe("dau-tone-session.png");
  await page.keyboard.press("Escape");
  await expect(summary).toBeHidden();

  await page.getByRole("button", { name: /2 Dialogue Practice/ }).click();
  await expect(page.getByRole("heading", { name: "Use the tone in a real conversation." })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Dialogue scenes" }).getByRole("button")).toHaveCount(4);
  await page.getByRole("button", { name: /No key or no Vietnamese/ }).click();
  await expect(page.getByRole("heading", { name: "Here is exactly what changed." })).toBeVisible();
  await expect(page.getByText("You said ma (ghost) instead of má (mother). That turns a family dinner into an invitation for a ghost.")).toBeVisible();
  await expect(page.getByText("dấu sắc · mother", { exact: true })).toBeVisible();
  await expect(page.getByText("không dấu · ghost", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: /Your take/ }).click();
  await page.getByRole("button", { name: /Correct take/ }).click();
  await expect.poll(() => page.evaluate(() => (window as typeof window & { __dauAudioPlayCount?: number }).__dauAudioPlayCount ?? 0)).toBeGreaterThanOrEqual(2);

  await page.getByRole("button", { name: /Practice this word in Tone Shapes/ }).click();
  await expect(page.getByRole("heading", { name: "má", exact: true })).toBeVisible();
  await expect(page).toHaveURL(/mode=tones/);
  expect(externalRequests).toEqual([]);
});

test("the six-tone workbench stays usable at every release viewport", async ({ page, baseURL }) => {
  await installOfflineHarness(page, baseURL!);
  const viewports = [
    { width: 1366, height: 768, desktopFit: true },
    { width: 1440, height: 900, desktopFit: true },
    { width: 1920, height: 1080, desktopFit: false },
    { width: 1024, height: 768, desktopFit: false },
    { width: 768, height: 1024, desktopFit: false },
    { width: 390, height: 844, desktopFit: false },
  ];

  for (const viewport of viewports) {
    await page.setViewportSize(viewport);
    await page.goto("/");
    const toneButtons = page.getByRole("navigation", { name: "The six tones of ma" }).getByRole("button");
    await expect(toneButtons).toHaveCount(6);
    await expect(page.getByRole("button", { name: "Record your tone" })).toBeVisible();
    await expect(page.getByRole("button", { name: /Listen \+ watch/ })).toBeVisible();
    await expect(page.getByRole("img", { name: /Cô Dấu demonstrating/ })).toBeVisible();
    await expect(page.locator("body")).toHaveJSProperty("scrollWidth", viewport.width);

    if (viewport.desktopFit) {
      for (const locator of [
        toneButtons.first(),
        toneButtons.last(),
        page.getByRole("button", { name: "Record your tone" }),
        page.getByRole("button", { name: /Listen \+ watch/ }),
        page.getByRole("img", { name: /Cô Dấu demonstrating/ }),
      ]) {
        const box = await locator.boundingBox();
        expect(box, `missing box at ${viewport.width}×${viewport.height}`).not.toBeNull();
        expect(box!.y + box!.height).toBeLessThanOrEqual(viewport.height + 1);
      }
    }
  }
});
