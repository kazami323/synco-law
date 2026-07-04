# AI Legal Workspace

CLM-платформа (Contract Lifecycle Management) с AI-агентами для юридических отделов компаний в Узбекистане.

## Структура

```text
backend/          FastAPI + SQLAlchemy async + Alembic + PostgreSQL/pgvector
frontend/         Next.js 16 + TypeScript + Tailwind 4
design/           Stitch-экспорт экранов и дизайн-системы
```

## Быстрый Старт С Нуля

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

## Environment

Основные переменные лежат в [backend/.env.example](backend/.env.example).

Live AI-анализ, чат с агентами и draft generation требуют `ANTHROPIC_API_KEY` в `backend/.env` и перезапуска backend. Без ключа backend корректно возвращает `503`, а workflow, подпись, сроки и уведомления продолжают работать.

`EMAIL_NOTIFY=false` зарезервирован для следующего этапа. Сейчас уведомления пишутся в таблицу `notifications`; email/Telegram-доставка подключается поверх того же сервиса уведомлений.

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

## Production / Deploy Prep

Следующий рабочий блок:

- нормальный seed/demo режим без ручных QA-записей в БД;
- docker compose для полного локального запуска;
- health checks для backend, postgres, redis, minio;
- env validation для обязательных production-переменных;
- README “как поднять с нуля” для dev и production-like режима;
- отсутствие моковых QA-данных в боевой БД.

## Phase 2 Roadmap

- реальный E-IMZO REST/SOAP API;
- email/Telegram уведомления;
- расширенный поиск по архиву;
- реальные legal sources: lex.uz и дополнительные источники;
- e2e-тесты через Playwright.
