# AI Legal Workspace

CLM-платформа (Contract Lifecycle Management) с AI-агентами для юридических отделов компаний в Узбекистане.

## Структура

```text
backend/          FastAPI + SQLAlchemy async + Alembic + PostgreSQL/pgvector
frontend/         Next.js 16 + TypeScript + Tailwind 4
design/           Stitch-экспорт экранов и дизайн-системы
docker-compose.yml full local production-like stack
```

## Быстрый Старт Для Разработки

Backend (инфраструктура поднимается корневым docker-compose — он один
на весь проект, отдельного compose в backend/ больше нет):

```bash
docker compose up -d postgres redis minio
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Проверка:

- Frontend: http://localhost:3000
- API: http://localhost:8000
- Swagger: http://localhost:8000/docs
- Health check: http://localhost:8000/health
- MinIO console: http://localhost:9001 (`minioadmin` / `minioadmin`)

## Production-Like Local Start

Полный локальный запуск из корня проекта:

```bash
docker compose up -d --build
```

Что поднимается:

- PostgreSQL + pgvector
- Redis
- MinIO
- backend с автоматическим `alembic upgrade head`
- frontend production build через `next start`

Проверка состояния:

```bash
docker compose ps
curl http://localhost:8000/health
```

Опционально Elasticsearch для Phase 2:

```bash
docker compose --profile search up -d elasticsearch
```

## Legal RAG: локальная база lex.uz для Law Agent

Law Agent умеет работать через локальную базу НПА: документы lex.uz
скачиваются в Postgres, режутся на статьи и индексируются в Elasticsearch
(если он включен). API-ключ lex.uz для этого не нужен.

```bash
cd backend
.venv\Scripts\activate
alembic upgrade head
python -m scripts.ingest_lexuz
```

По умолчанию импортируются базовые акты для договорной работы:
ГК РУз (части 1 и 2), ТК, НК и закон «О договорно-правовой базе деятельности
хозяйствующих субъектов». Добавить отдельный документ можно так:

```bash
python -m scripts.ingest_lexuz --url https://lex.uz/ru/docs/10872
```

Если Elasticsearch поднят позже, переиндексируйте уже загруженные статьи:

```bash
python -m scripts.reindex_laws
```

Проверка через API после логина и создания организации:

```text
GET /api/legal/search?q=правовая экспертиза хозяйственного договора
GET /api/legal/documents
```

После импорта агент `law` и полный анализ договора автоматически подмешивают
релевантные статьи в промпт и возвращают ссылки на конкретные якоря lex.uz.

Автообновление legal-базы можно включить через env:

```bash
LEGAL_REFRESH_ENABLED=true
LEGAL_REFRESH_INTERVAL_HOURS=168
```

## Backup / Restore / Product Docs

Локальный backup:

```powershell
cd backend
.\scripts\backup.ps1
```

Restore:

```powershell
.\scripts\restore.ps1 -BackupPath .\backups\<timestamp> -RestoreMinio
python -m scripts.reindex_search
python -m scripts.reindex_laws
```

Документы для пилота и production readiness:

- [Privacy Policy](docs/PRIVACY_POLICY.md)
- [Terms of Service](docs/TERMS_OF_SERVICE.md)
- [AI Disclaimer](docs/AI_DISCLAIMER.md)
- [Backup And Restore](docs/BACKUP_RESTORE.md)
- [Security Checklist](docs/SECURITY_CHECKLIST.md)
- [Pilot Plan](docs/PILOT_PLAN.md)

## Demo Seed

Для демо-данных без ручных QA-записей:

```bash
cd backend
.venv\Scripts\activate
python scripts\seed_demo.py
```

Демо-логин:

```text
demo@legal.uz
demo12345
```

Seed идемпотентный: повторный запуск обновляет демо-набор контрактов с префиксом `Demo:` и не плодит дубликаты.

## Environment

Основные переменные лежат в [backend/.env.example](backend/.env.example).

Важные переменные:

- `ENVIRONMENT=development|test|staging|production`
- `SECRET_KEY` должен быть сильным в production
- `DATABASE_URL` не должен указывать на localhost в production
- `CORS_ORIGINS` должен содержать публичный frontend origin
- `ANTHROPIC_API_KEY` нужен для live AI-анализа, чата с агентами и draft generation
- `EMAIL_NOTIFY=false` зарезервирован для email/Telegram уведомлений

Без `ANTHROPIC_API_KEY` backend корректно возвращает `503` на AI-операциях, а workflow, подпись, сроки и уведомления продолжают работать.

## Правовой Движок (ТЗ Заказчика)

Ядро продукта — работа с документом **по пунктам**: см.
[docs/FUNCTIONAL_SPEC.md](docs/FUNCTIONAL_SPEC.md) (каноническое ТЗ) и
[docs/SPEC_GAP_ANALYSIS.md](docs/SPEC_GAP_ANALYSIS.md) (что реализовано).

Маршрут юриста:

1. Создать документ — генерация (тип → шаблон → голосовая или текстовая
   постановка задачи → карточка параметров на подтверждение), загрузка
   DOCX/PDF/скана или копия существующего.
2. Открыть «Правовую проверку» и запустить модули — по отдельности или все сразу:
   - **Модуль 1** — разбивка на разделы/пункты/подпункты и сверка каждого
     пункта с lex.uz: вердикт `соответствует / противоречит / требует внимания /
     норма не найдена`, текст статьи с редакцией на дату проверки и
     формулировка-замена при противоречии;
   - **Модуль 2** — расхождения внутри документа по семи категориям ТЗ, каждое
     с указанием обоих конфликтующих пунктов;
   - **Модуль 3** — риски с позиции представляемой стороны (сторона
     обязательна), шесть категорий, уровень и предложение по устранению.
3. Пройти пункт за пунктом: подтвердить / изменить / комментарий / отложить.
   Счётчик «N из M». Пока не подтверждены все пункты, документ не переходит в
   статус «Подтверждён юристом».
4. Выгрузить DOCX или PDF: чистую версию для контрагента или рабочую с
   замечаниями.

Ключевые эндпоинты:

```text
GET    /api/contracts/{id}/clauses            -> пункты, вердикты, решения, прогресс
POST   /api/contracts/{id}/clauses/rebuild    -> пересобрать пункты из текста
POST   /api/clauses/{id}/decision             -> confirm | edit | comment | defer
GET    /api/clauses/{id}/history              -> история решений по пункту
POST   /api/contracts/{id}/review             -> { modules[], party_side }
GET    /api/contracts/{id}/review             -> сводка по документу
GET    /api/contracts/{id}/logic-findings     -> расхождения (Модуль 2)
GET    /api/contracts/{id}/risk-findings      -> риски (Модуль 3)
PATCH  /api/logic-findings/{id}               -> accepted | rejected | fixed
PATCH  /api/risk-findings/{id}                -> accepted | rejected | fixed
GET/POST /api/contracts/{id}/comments         -> комментарии (в т.ч. наблюдателя)
GET    /api/contracts/{id}/export             -> ?fmt=docx|pdf&mode=clean|working
POST   /api/contracts/{id}/duplicate          -> копия документа
GET    /api/contracts/{id}/versions/{n}/diff  -> ?against=<версия>
POST   /api/contracts/{id}/versions/{n}/restore
GET    /api/templates                         -> база шаблонов
POST   /api/templates/{id}/verify             -> отметка «верифицирован»
POST   /api/contracts/{id}/save-as-template
GET    /api/document-types                    -> каталог типов с обязательными блоками
GET    /api/document-statuses                 -> каталог статусов
GET/PUT  /api/projects/{id}/context           -> общий контекст проекта
GET/POST /api/projects/{id}/members           -> участники проекта
POST   /api/agents/draft/extract-params       -> карточка параметров перед генерацией
```

Голосовая постановка задачи расшифровывается в браузере (Web Speech API,
Chrome и Edge); в остальных браузерах доступен текстовый ввод.

## API Endpoint Summary

```text
POST   /api/contracts/{id}/sign-request       -> { request_id, hash }
POST   /api/contracts/{id}/sign-confirm       -> { signature, timestamp, certificate_thumbprint }
GET    /api/contracts/{id}/deadlines          -> [{ deadline_date, type, days_left }]
POST   /api/contracts/{id}/deadlines          -> create deadline
GET    /api/contracts/upcoming-deadlines      -> nearest deadlines
GET    /api/dashboard/metrics                 -> includes upcoming_deadlines_count
GET    /api/notifications                     -> [{ id, text, read_at }]
GET    /api/notifications/unread-count        -> { count }
PATCH  /api/notifications/{id}/read           -> mark as read
```

## Phase 1 Status

- [x] Weeks 1-2: backend setup, DB schema, Docker
- [x] Weeks 3-4: auth, organizations, users, audit log, tests
- [x] Weeks 5-6: contract CRUD, MinIO, PDF/DOCX parsing, versions, frontend contract pages
- [x] Weeks 7-8: AI agents, orchestrator, analysis, chat, draft generation
- [x] Weeks 9-10: workflow, dashboard, approvals
- [x] Weeks 11-12: E-IMZO stub, deadlines, notifications, dashboard deadline metrics

## Weeks 11-12 Notes

E-IMZO интеграция сделана как заглушка, готовая к замене на реальный REST/SOAP вызов:

- `sign-request` фиксирует хеш контракта в БД;
- `sign-confirm` сохраняет подпись, timestamp, сертификат и thumbprint;
- контракт переводится в `signed`, а история workflow получает шаг `signed`.

Критичные сроки извлекаются из текста договора и могут добавляться вручную. Уведомления создаются для сроков в ближайшие 7 дней и доступны через колокольчик в интерфейсе и страницу `/notifications`.

## E2E Checklist

1. Зарегистрировать пользователя и создать организацию.
2. Создать контракт из текста или файла.
3. При наличии `ANTHROPIC_API_KEY` запустить AI-анализ.
4. Провести согласование: legal approval -> finance approval -> ready to sign.
5. Создать E-IMZO sign request и подтвердить подпись.
6. Проверить статус `signed`, `signature_timestamp` и thumbprint сертификата.
7. Проверить блок критичных сроков на странице контракта.
8. Проверить dashboard `upcoming_deadlines_count`.
9. Проверить колокольчик и страницу `/notifications`.
10. Архивировать контракт и убедиться, что архивный контракт не попадает в upcoming deadlines.

## Production / Deploy Prep Status

- [x] demo seed без ручных QA-записей
- [x] root Docker Compose для полного локального запуска
- [x] health checks для backend, postgres, redis, minio
- [x] env validation для production-переменных
- [x] README “как поднять с нуля”
- [x] моковые QA-данные удалены из локальной БД

## Phase 2 Roadmap

- реальный E-IMZO REST/SOAP API;
- email/Telegram уведомления;
- расширенный поиск по архиву;
- реальные legal sources: lex.uz и дополнительные источники;
- e2e-тесты через Playwright.
