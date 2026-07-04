# AI Legal Workspace

CLM-платформа (Contract Lifecycle Management) с AI-агентами для юридических отделов компаний в Узбекистане.

Полное ТЗ: [AI_Legal_Workspace_Development_TZ.md](AI_Legal_Workspace_Development_TZ.md) (Phase 1 MVP: 4 агента, dashboard, workflow, E-IMZO).

## Структура

```
backend/          FastAPI + SQLAlchemy (async) + Alembic + PostgreSQL/pgvector
frontend/         Next.js 14 (появится на Weeks 9-10)
```

## Быстрый старт (backend)

Требования: Python 3.11+, Docker Desktop.

```bash
cd backend

# 1. Инфраструктура (PostgreSQL+pgvector, Redis, MinIO)
docker compose up -d postgres redis minio

# 2. Окружение
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env         # и заполнить SECRET_KEY, ANTHROPIC_API_KEY

# 3. Миграции БД
alembic upgrade head

# 4. Запуск API
uvicorn app.main:app --reload
```

- API: http://localhost:8000, Swagger: http://localhost:8000/docs
- Health-check: `GET /health` (проверяет и подключение к БД)
- MinIO console: http://localhost:9001 (minioadmin/minioadmin)
- Elasticsearch (нужен с Phase 2): `docker compose --profile search up -d`

## Статус разработки (Phase 1)

- [x] Weeks 1-2 — Backend setup, схема БД, Docker
- [x] Weeks 3-4 — Authentication, организации, управление пользователями, аудит-лог, тесты
- [ ] Weeks 5-6 — Contract CRUD API, MinIO, парсинг PDF/DOCX
- [ ] Weeks 7-8 — 4 AI-агента (Analyzer, Law, Risk, Draft) + оркестратор
- [ ] Weeks 9-10 — Dashboard, frontend
- [ ] Weeks 11-12 — Workflow, тесты, документация
