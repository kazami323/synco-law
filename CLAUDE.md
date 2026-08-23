# AI Legal Workspace — инструкции для агентов

Веб-сервис для юридических отделов Узбекистана: создание, проверка и
утверждение договоров с опорой на правовую базу lex.uz.

## Каноническое ТЗ

[docs/FUNCTIONAL_SPEC.md](docs/FUNCTIONAL_SPEC.md) — функциональное описание
заказчика. **Это источник истины по продукту.** Код, который расходится с ним,
считается дефектом, если расхождение не зафиксировано в
[docs/SPEC_GAP_ANALYSIS.md](docs/SPEC_GAP_ANALYSIS.md).

Перед любой продуктовой задачей — сверься с этими двумя файлами. После
закрытия пункта ТЗ — обнови gap-анализ.

## Стек

| Слой | Технологии |
|---|---|
| Backend | FastAPI, SQLAlchemy 2 (async), Alembic, PostgreSQL + pgvector, Redis, MinIO, Elasticsearch (опц.) |
| Frontend | Next.js 16, TypeScript, Tailwind 4, дизайн-система LexOS |
| AI | Anthropic API (`claude-opus-4-8`), агенты в `backend/app/agents/` |
| Инфра | docker-compose (корневой, один на проект), GitHub Actions CI |

## Карта кода

```text
backend/app/agents/      AI-агенты + оркестратор анализа
backend/app/api/         FastAPI-роутеры (contracts, projects, agents, workflow, legal, labels…)
backend/app/core/        config, permissions, labels, security, dependencies
backend/app/db/          models.py (SQLAlchemy), schemas.py (Pydantic)
backend/app/services/    доменные сервисы (legal_search, legal_ingest, notifications, deadlines…)
backend/app/utils/       llm, document_parser (вкл. OCR), storage, audit, validators
backend/alembic/         миграции
backend/tests/           pytest
frontend/src/app/        роуты Next.js App Router
frontend/src/components/ UI-компоненты
frontend/src/lib/        api-клиент, типы, права, лейблы
docs/                    ТЗ, gap-анализ, юридические и эксплуатационные документы
```

## Жёсткие правила

1. **Мультитенантность.** Любой запрос к данным фильтруется по
   `organization_id` текущего пользователя. Отсутствие фильтра — критический
   дефект безопасности, а не стилистика.
2. **Права.** Изменение доступа делается в `backend/app/core/permissions.py`,
   зеркало на фронте — `frontend/src/lib/permissions.ts`. Оба должны совпадать.
3. **Миграции.** Изменил `models.py` — добавь миграцию Alembic в том же
   изменении. Нумерация последовательная (`00NN_описание.py`).
4. **Каталог плашек** живёт в `backend/app/core/labels.py` и зеркалится в
   `frontend/src/lib/labels.ts`. Больше нигде состав плашек не хардкодится.
5. **Next.js 16 сломан относительно знаний модели.** Перед фронтенд-кодом
   читай `frontend/node_modules/next/dist/docs/` (см. `frontend/AGENTS.md`).
6. **Язык интерфейса — русский.** Строки в UI, названия статусов, тексты
   ошибок для пользователя — по-русски. Код, коммиты и комментарии — как
   принято в файле рядом.
7. **AI только предлагает.** Ни один AI-вердикт не меняет статус документа
   автоматически и не подменяет решение юриста. Каждое решение юриста
   фиксируется с автором и временем (`audit_log`).
8. **Без `ANTHROPIC_API_KEY`** backend обязан отдавать `503` на AI-операциях,
   а всё остальное — работать. Не ломай этот контракт.
9. **Юридическая ссылка без редакции нормы недействительна.** Любая ссылка на
   статью должна нести редакцию/дату, чтобы результат проверки был
   воспроизводим.

## Проверки перед сдачей работы

```bash
cd backend && pytest -q
cd frontend && npm run lint && npm run build
```

E2E (Playwright): `cd frontend && npm run test:e2e`.

Локальная БД: контейнеры Postgres после `docker start` несколько секунд в
состоянии «starting up» — перед `pytest` дождись `pg_isready`.

## Агенты проекта

В [.claude/agents/](.claude/agents/) лежат специализированные субагенты.
Правила вызова — в [.claude/agents/README.md](.claude/agents/README.md).
