import { expect, test, type APIResponse, type Page } from "@playwright/test";

const stamp = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
const account = {
  email: `e2e-${stamp}@example.com`,
  username: `e2e_${stamp.replace(/-/g, "_")}`,
  password: "E2eSecure2026",
  organization: `E2E Organization ${stamp}`,
  contract: `E2E Contract ${stamp}`,
};

async function expectOk(response: APIResponse) {
  expect(response.ok(), `${response.status()} ${await response.text()}`).toBeTruthy();
}

async function registerAndOnboard(page: Page) {
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

async function uploadContract(page: Page): Promise<string> {
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
    buffer: Buffer.from(
      "ДОГОВОР ПОСТАВКИ\nПоставщик передает товар до 31.12.2026. Оплата в течение 10 дней.",
      "utf8",
    ),
  });
  await modal.getByRole("button", { name: "Создать контракт" }).click();
  await expect(page).toHaveURL(/\/contracts\/[0-9a-f-]+$/);
  const contractId = page.url().split("/").pop();
  expect(contractId).toBeTruthy();
  await expect(page.getByText(account.contract).first()).toBeVisible();
  return contractId!;
}

test("registration to archive product journey", async ({ page }) => {
  await registerAndOnboard(page);
  const contractId = await uploadContract(page);

  await page.goto("/analysis");
  await expect(page.getByRole("heading", { name: /Аналитика|Анализ/i })).toBeVisible();

  const storedChat = await page.request.post("/api/agents/sessions/", {
    data: {
      agent: "law",
      title: `E2E legal chat ${stamp}`,
      contract_id: contractId,
      messages: [
        { role: "user", content: "Какие нормы применимы?", agent: "law" },
        { role: "assistant", content: "Тест сохранения истории.", agent: "law" },
      ],
    },
  });
  await expectOk(storedChat);

  await page.goto("/agents/chat/law");
  await expect(page.getByText(`E2E legal chat ${stamp}`)).toBeVisible();

  if (process.env.E2E_LIVE_AI === "1") {
    const live = await page.request.post("/api/agents/chat", {
      data: {
        agent: "law",
        contract_id: contractId,
        messages: [{ role: "user", content: "Как регулируется срок оплаты по договору поставки?" }],
      },
      timeout: 120_000,
    });
    await expectOk(live);
    expect(JSON.stringify(await live.json())).toMatch(/lex\.uz/i);
  }

  for (const action of ["approve_legal", "approve_finance", "finalize"]) {
    await expectOk(
      await page.request.post(`/api/contracts/${contractId}/workflow/${action}`, {
        data: { comment: `E2E ${action}` },
      }),
    );
  }

  await page.goto("/workflow");
  await expect(page.getByText(account.contract)).toBeVisible();

  const signRequest = await page.request.post(`/api/contracts/${contractId}/sign-request`);
  await expectOk(signRequest);
  const { request_id } = await signRequest.json();
  await expectOk(
    await page.request.post(`/api/contracts/${contractId}/sign-confirm`, {
      data: { request_id },
    }),
  );
  await expectOk(await page.request.delete(`/api/contracts/${contractId}`));

  await page.goto("/archive");
  await page.locator('input[placeholder*="поисковый"]').fill(account.contract);
  await expect(page.getByText(account.contract)).toBeVisible();
});
