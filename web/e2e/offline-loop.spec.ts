import { Buffer } from "node:buffer";
import { expect, test } from "@playwright/test";

function silentWav(): Buffer {
  const sampleBytes = 1_600;
  const wav = Buffer.alloc(44 + sampleBytes);
  wav.write("RIFF", 0);
  wav.writeUInt32LE(wav.length - 8, 4);
  wav.write("WAVE", 8);
  wav.write("fmt ", 12);
  wav.writeUInt32LE(16, 16);
  wav.writeUInt16LE(1, 20);
  wav.writeUInt16LE(1, 22);
  wav.writeUInt32LE(8_000, 24);
  wav.writeUInt32LE(16_000, 28);
  wav.writeUInt16LE(2, 32);
  wav.writeUInt16LE(16, 34);
  wav.write("data", 36);
  wav.writeUInt32LE(sampleBytes, 40);
  return wav;
}

test("offline learner closes the word and Echo loops without external requests", async ({ page, baseURL }) => {
  const localOrigin = new URL(baseURL!).origin;
  const externalRequests: string[] = [];
  let correctSpeechRequests = 0;

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
    if (url.pathname === "/api/echo/speak" && route.request().method() === "POST") {
      correctSpeechRequests += 1;
      await route.fulfill({ status: 200, contentType: "audio/wav", body: silentWav() });
      return;
    }
    if (url.pathname.startsWith("/api/")) {
      await route.abort("connectionrefused");
      return;
    }
    await route.continue();
  });

  await page.goto("/");
  await expect(page.getByText("demo mode", { exact: true })).toBeVisible();
  await expect(page.locator(".stage-actions--desktop").getByText(/Thầy Minh · Hà Nội/)).toBeVisible();
  await expect(page.locator("body")).not.toContainText("Cedar");
  await expect(page.getByRole("img", { name: "Illustration of Phương, a woman's name" })).toBeVisible();
  await expect(page.locator(".co-dau__mouth")).toHaveAttribute("data-vowel-shape", "rounded");
  await expect(page.locator(".co-dau__arrow")).toBeVisible();

  const skipLink = page.getByRole("link", { name: "Skip to practice" });
  await skipLink.focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#main-content$/);

  const signatureDemo = page.getByRole("button", { name: "Phương → phường" });
  await signatureDemo.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "You meant Phương, the name. You said phường, an urban ward." })).toBeVisible();
  await expect(page.getByText("Hold your chin steady and carry Phương straight across without letting the ending sink.")).toBeVisible();
  const nextDecision = page.locator(".next-decision");
  await expect(nextDecision).toContainText("phường");
  await expect(nextDecision).toContainText("Contrast the level name with phường while that accidental fall is fresh.");

  await page.getByRole("button", { name: "Finish session" }).click();
  const summary = page.getByRole("dialog", { name: "Your tones, in focus." });
  await expect(summary).toBeVisible();
  const downloadPromise = page.waitForEvent("download");
  await summary.getByRole("button", { name: "Share summary card" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("dau-tone-session.png");
  await page.keyboard.press("Escape");
  await expect(summary).toBeHidden();

  const echoTab = page.getByRole("button", { name: "Echo sentences" });
  await echoTab.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Tones carry the stakes." })).toBeVisible();
  await page.getByRole("button", { name: "Try “a ghost at dinner”" }).click();
  await expect(page.getByText("You said ma, a ghost, instead of má, mother. You invited a ghost to dinner.")).toBeVisible();
  await expect(page.locator(".echo-token--tone_only")).toContainText("ma");

  const shadowButton = page.getByRole("button", { name: "Hear it correctly, then shadow" });
  await shadowButton.focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => correctSpeechRequests).toBe(1);
  await expect.poll(() => page.evaluate(() => (window as typeof window & { __dauAudioPlayCount?: number }).__dauAudioPlayCount ?? 0)).toBeGreaterThan(0);
  await expect(page.locator(".co-dau--playing")).toBeVisible();
  expect(externalRequests).toEqual([]);
});
