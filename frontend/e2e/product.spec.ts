import { expect, test } from "@playwright/test";
import {
  confirmAllClauses,
  expectOk,
  makeAccount,
  registerAndOnboard,
  uploadContract,
} from "./helpers";

test("registration to archive product journey", async ({ page }) => {
  const account = makeAccount("e2e");
  await registerAndOnboard(page, account);
  const contractId = await uploadContract(page, account);

  await page.goto("/analysis");
  await expect(page.getByRole("heading", { name: /Аналитика|Анализ/i })).toBeVisible();

  const storedChat = await page.request.post("/api/agents/sessions/", {
    data: {
      agent: "law",
      title: `E2E legal chat ${account.stamp}`,
      contract_id: contractId,
      messages: [
        { role: "user", content: "Какие нормы применимы?", agent: "law" },
        { role: "assistant", content: "Тест сохранения истории.", agent: "law" },
      ],
    },
  });
  await expectOk(storedChat);

  await page.goto("/agents/chat/law");
  await expect(page.getByText(`E2E legal chat ${account.stamp}`)).toBeVisible();

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

  // Гейт ТЗ (раздел 4): пока пункты не пройдены, «Юридически согласован»
  // недоступен — и запрещает это бэкенд, а не интерфейс.
  const blocked = await page.request.post(
    `/api/contracts/${contractId}/workflow/approve_legal`,
    { data: { comment: "E2E до подтверждения пунктов" } },
  );
  expect(blocked.status(), await blocked.text()).toBe(409);

  await confirmAllClauses(page, contractId);

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
