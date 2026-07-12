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

Backend:

```bash
cd backend
docker compose up -d postgres redis minio
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
demo@legal.local
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
