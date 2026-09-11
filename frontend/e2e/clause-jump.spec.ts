import { expect, test } from "@playwright/test";
import { expectOk, makeAccount, registerAndOnboard, uploadContract } from "./helpers";

/**
 * ТЗ-прототип, требование R13 (docs/SVOD_PROTOTYPE_DELTA.md, раздел 4.2):
 * номер пункта в карточке риска — не текст, а интерактивный переход к
 * пункту. Эталон поведения — функция `jumpTo(id)` в
 * design/svod_prototype/svod-app2.html: она переключает вкладку на пункты и
 * открывает именно тот пункт, на который указывает риск.
 *
 * Сейчас frontend/src/components/review/findings.tsx:332 рисует это простым
 * текстом `Пункты: {finding.clause_anchors.join(", ")}` — кликать некуда.
 * Юрист читает «Пункты: 4.2» и идёт искать пункт руками по вкладке «Пункты
 * и нормы». Тест ниже фиксирует ожидаемое поведение и должен падать, пока
 * это не исправлено.
 */

/**
 * Находки Модуля 3 (риски) требуют ANTHROPIC_API_KEY — без него
 * POST /api/contracts/{id}/review отдаёт 503 (backend/app/utils/llm.py:63,
 * правило проекта «без ключа AI-эндпоинты недоступны», см. CLAUDE.md). Ключа
 * нет ни в этом окружении, ни в e2e-джобе CI (.github/workflows/ci.yml) —
 * значит настоящую находку риска через ИИ здесь получить нельзя в принципе.
 *
 * Пункты документа (Модуль 1) от ИИ не зависят — разбивка детерминированная
 * (backend/app/services/clause_splitter.py), поэтому пункты 4.1 и 4.2 ниже
 * настоящие, получены с реального бэкенда. Подменяется сетевым перехватом
 * только ответ /risk-findings — то есть ровно то, что в проде даёт AI-модуль.
 * Поведение под тестом (клик по пункту риска → переход к пункту) остаётся
 * настоящим кодом фронтенда, не мокается.
 */
test("клик по номеру пункта в карточке риска открывает именно этот пункт", async ({ page }) => {
  const account = makeAccount("e2e-cj");
  await registerAndOnboard(page, account);

  const clauseOneText =
    "Поставщик передаёт товар Покупателю в течение 30 дней с даты подписания настоящего договора.";
  const clauseTwoText =
    "Неустойка за просрочку поставки составляет 0,1% от стоимости товара за каждый день просрочки; ответственность Покупателя за просрочку оплаты договором не установлена.";

  const contractId = await uploadContract(
    page,
    account,
    `4.1. ${clauseOneText}\n4.2. ${clauseTwoText}`,
  );

  // Сверка: реальный разбор бэкенда действительно дал пункты 4.1 и 4.2 —
  // иначе дальнейшие проверки ничего не значат.
  const clausesResponse = await page.request.get(`/api/contracts/${contractId}/clauses`);
  await expectOk(clausesResponse);
  const clauseList = (await clausesResponse.json()) as { items: Array<{ anchor: string }> };
  const anchors = clauseList.items.map((item) => item.anchor);
  expect(anchors, "разбивщик должен был выделить пункты 4.1 и 4.2").toEqual(
    expect.arrayContaining(["4.1", "4.2"]),
  );

  await page.route(`**/api/contracts/${contractId}/risk-findings`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: "11111111-1111-1111-1111-111111111111",
          category: "one_sided_liability",
          category_title: "Односторонняя ответственность",
          level: "high",
          level_title: "Высокий",
          description: "Ответственность за просрочку установлена только для Поставщика.",
          consequence: "Покупатель может задерживать оплату без последствий по договору.",
          mitigation: "Добавить симметричную неустойку за просрочку оплаты.",
          clause_anchors: ["4.2"],
          status: "open",
          resolution_note: null,
          resolved_at: null,
          created_at: new Date().toISOString(),
        },
      ]),
    });
  });

  await page.goto(`/contracts/${contractId}/review`);

  // По умолчанию открыта вкладка «Пункты и нормы» с первым пунктом — 4.1.
  await expect(page.getByRole("heading", { level: 3, name: "Пункт 4.1" })).toBeVisible();
  // Пункт 4.2 юрист ещё не открывал — панели с его текстом в DOM пока нет,
  // это не просто «скрыта вкладкой».
  await expect(page.getByRole("heading", { level: 3, name: "Пункт 4.2" })).toHaveCount(0);

  await page.getByRole("tab", { name: "Смысл и риски" }).click();
  await expect(
    page.getByText("Ответственность за просрочку установлена только для Поставщика"),
  ).toBeVisible();

  // Доступное имя и роль — как того требует аудит доступности (нельзя
  // вешать onClick на неинтерактивный элемент, см. docs/AUDIT_2026-08-22.md):
  // это должна быть кнопка или ссылка, а не просто текст со стилями.
  const clauseLink = page
    .getByRole("button", { name: /к пункту 4\.2/i })
    .or(page.getByRole("link", { name: /к пункту 4\.2/i }));
  await expect(
    clauseLink,
    "номер пункта в карточке риска должен быть кликабельным элементом (кнопка или ссылка)",
  ).toBeVisible();

  await clauseLink.click();

  // Клик переключил вкладку обратно на «Пункты и нормы»...
  await expect(page.getByRole("tab", { name: "Пункты и нормы" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  // ...и открыл именно пункт 4.2 — не первый пункт по умолчанию, а тот,
  // на который указывал риск.
  await expect(page.getByRole("heading", { level: 3, name: "Пункт 4.2" })).toBeVisible();
  await expect(page.getByText(clauseTwoText)).toBeVisible();
});
