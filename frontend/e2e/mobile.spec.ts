import { expect, test } from "@playwright/test";

test("authentication pages fit a mobile viewport", async ({ page }) => {
  await page.goto("/register");
  await expect(page.locator(".auth-register form")).toBeVisible();

  const viewport = page.viewportSize();
  expect(viewport).not.toBeNull();
  const bodyWidth = await page.locator("body").evaluate((element) => element.scrollWidth);
  expect(bodyWidth).toBeLessThanOrEqual(viewport!.width + 1);

  await page.goto("/login");
  await expect(page.locator(".auth-login form")).toBeVisible();
  await expect(page.getByRole("link", { name: /Забыли пароль/ })).toBeVisible();
});
