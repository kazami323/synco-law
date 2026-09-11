import { expect, type APIResponse, type Page } from "@playwright/test";

/**
 * Общие хелперы для e2e-сценариев. Раньше жили внутри product.spec.ts —
 * вынесены сюда, чтобы другие сценарии (например, клик по пункту из карточки
 * риска) не дублировали регистрацию и загрузку договора и не сталкивались с
 * общим на файл `account`, который годится только для одного теста.
 */

export interface E2eAccount {
  /** Сырой таймстемп-соль прогона — пригождается для заголовков вроде чата. */
  stamp: string;
  email: string;
  username: string;
  password: string;
  organization: string;
  contract: string;
}

/** Договор по умолчанию — как раньше в product.spec.ts, без явной нумерации пунктов. */
export const DEFAULT_CONTRACT_TEXT =
  "ДОГОВОР ПОСТАВКИ\nПоставщик передает товар до 31.12.2026. Оплата в течение 10 дней.";

export function makeAccount(prefix = "e2e"): E2eAccount {
  const stamp = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
  return {
    stamp,
    email: `${prefix}-${stamp}@example.com`,
    username: `${prefix}_${stamp}`.replace(/-/g, "_"),
    password: "E2eSecure2026",
    organization: `E2E Organization ${stamp}`,
    contract: `E2E Contract ${stamp}`,
  };
}

export async function expectOk(response: APIResponse) {
  expect(response.ok(), `${response.status()} ${await response.text()}`).toBeTruthy();
}

export async function registerAndOnboard(page: Page, account: E2eAccount) {
  await page.goto("/register");
  const form = page.locator(".auth-register form");
  await form.locator('input[type="text"]').first().fill("E2E Admin");
  await form.locator('input[type="email"]').fill(account.email);
  await form.locator('input[type="text"]').nth(1).fill(account.username);
  await form.locator('input[type="password"]').fill(account.password);
  await form.locator('button[type="submit"]').click();
  await expect(page).toHaveURL(/\/onboarding$/);

  const createForm = page.locator("form").nth(1);
  await createForm.locator("input").first().fill(account.organization);
  await createForm.locator('input[type="email"]').fill(account.email);
  await createForm.locator('button[type="submit"]').click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
}

export async function uploadContract(
  page: Page,
  account: E2eAccount,
  contractText: string = DEFAULT_CONTRACT_TEXT,
): Promise<string> {
  await page.goto("/contracts");
  await page.getByRole("button", { name: /Создать контракт/ }).first().click();
  await page.getByRole("button", { name: "Далее" }).click();

  const modal = page.locator('[role="dialog"]');
  await modal.locator("input").nth(0).fill(account.contract);
  await modal.locator("input").nth(1).fill("E2E Counterparty");
  await modal.locator("input").nth(2).fill("1000000");
  await page.getByRole("button", { name: "Далее" }).click();
  await modal.locator('input[type="file"]').setInputFiles({
    name: "e2e-contract.txt",
    mimeType: "text/plain",
    buffer: Buffer.from(contractText, "utf8"),
  });
  await modal.getByRole("button", { name: "Создать контракт" }).click();
  await expect(page).toHaveURL(/\/contracts\/[0-9a-f-]+$/);
  const contractId = page.url().split("/").pop();
  expect(contractId).toBeTruthy();
  await expect(page.getByText(account.contract).first()).toBeVisible();
  return contractId!;
}
/**
 * Проходит все пункты документа действием «подтвердить».
 *
 * ТЗ, раздел 4: пока не подтверждён каждый пункт, документ не может перейти
 * в «Подтверждён юристом», и держит это бэкенд —
 * `_ensure_clauses_confirmed` в backend/app/api/workflow.py. Сквозной
 * сценарий обязан пройти этот шаг, иначе согласование упирается в 409.
 */
export async function confirmAllClauses(page: Page, contractId: string) {
  const listed = await page.request.get(`/api/contracts/${contractId}/clauses`);
  await expectOk(listed);
  const { items } = (await listed.json()) as { items: Array<{ id: string }> };
  expect(items.length, "разбор должен был дать хотя бы один пункт").toBeGreaterThan(0);

  for (const clause of items) {
    await expectOk(
      await page.request.post(`/api/clauses/${clause.id}/decision`, {
        data: { action: "confirm" },
      }),
    );
  }
}
