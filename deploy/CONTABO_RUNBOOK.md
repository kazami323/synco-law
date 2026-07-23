# Деплой SynCo: весь стек на Contabo VPS

Всё живёт на одном Contabo VPS (фронт + бэк + данные + Caddy). Ahost остаётся только
как DNS-провайдер и почта.

```text
synco.law / www.synco.law  -> Ahost (лендинг + почта, не трогаем)
app.synco.law              -> Contabo VPS (Next.js фронтенд)      \
api.synco.law              -> Contabo VPS (FastAPI + данные)       > один сервер, Caddy отдаёт оба
```

Caddy на VPS выдаёт HTTPS обоим поддоменам и проксирует: `app` → контейнер фронта (:3000),
`api` → бэкенд (:8000). Браузер ходит в API **напрямую** по `https://api.synco.law`; так как
`app` и `api` — поддомены одного сайта `synco.law` (same-site), httpOnly-куки авторизации
ходят без прокси.

Все данные (Postgres, Redis, MinIO, Elasticsearch, ClamAV) сидят во внутренней Docker-сети
`private` без публикации портов наружу. Снаружи открыт только Caddy (80/443).

**VPS:** Contabo, IP `169.58.51.56`, Ubuntu, доступ по SSH под `root`.

---

## Шаг 1. DNS (делать первым — Caddy без DNS не выпустит HTTPS)

В DNS-панели Ahost для `synco.law` добавь **две A-записи**, обе на IP Contabo:

```text
Type: A    Name: api    Value: 169.58.51.56    TTL: по умолчанию
Type: A    Name: app    Value: 169.58.51.56    TTL: по умолчанию
```

Поддомен/хостинг на Ahost создавать НЕ надо — фронт живёт на Contabo, сюда нужны только
DNS-записи. НЕ трогай `@`, `www`, `MX`, `mail`, `SPF`, `DKIM`, `DMARC` — это почта и лендинг.

Проверь распространение (может занять от минут до часа):

```bash
nslookup api.synco.law
nslookup app.synco.law
```

Оба должны вернуть `169.58.51.56`. Дальше идти можно, пока DNS долетает — Caddy сам возьмёт
сертификаты, как только домены зарезолвятся.

---

## Шаг 2. Подготовка VPS (по SSH под root)

Подключись: `ssh root@169.58.51.56` (Contabo присылает root-пароль на почту).

Выполни блоком:

```bash
# система
apt-get update && apt-get -y upgrade
apt-get install -y git curl ufw

# Elasticsearch не стартует без этого лимита на хосте (bootstrap check) — обязательно
sysctl -w vm.max_map_count=262144
echo 'vm.max_map_count=262144' > /etc/sysctl.d/99-elasticsearch.conf

# 2 ГБ swap как страховка на пики памяти (ClamAV + ES + сборка бэкенда)
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab

# Docker Engine + плагин compose (официальный скрипт)
curl -fsSL https://get.docker.com | sh
docker compose version   # проверка, что плагин есть

# файрвол: наружу только SSH + HTTP + HTTPS
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
```

> Порты Postgres/Redis/MinIO/ES наружу не публикуются (сеть `private`, `internal: true`),
> поэтому снаружи доступен только Caddy — это и есть безопасная схема.

---

## Шаг 3. Код + секреты на VPS

Репозиторий приватный, поэтому нужен доступ. Проще всего — fine-grained **read-only PAT**
на репозиторий `kazami323/synco-law` (github.com → Settings → Developer settings →
Fine-grained tokens, доступ Contents: Read к этому репо).

```bash
cd /root
git clone https://<PAT>@github.com/kazami323/synco-law.git
# репозиторий склонируется в /root/synco-law
```

Файл `deploy/.env.production` **не в git** (там секреты) — его надо перенести отдельно.
Он уже сгенерирован у тебя локально и содержит правильные `API_DOMAIN=api.synco.law`,
`CORS_ORIGINS`, ключи Anthropic/SMTP, пароли БД. Перенеси его с Windows-ПК.

**На Windows-ПК** (PowerShell, из корня проекта `веб сервис для юристов`):

```powershell
scp "deploy/.env.production" root@169.58.51.56:/root/synco-law/deploy/.env.production
```

Проверь на VPS, что ключевые значения на месте (секреты покажет частично):

```bash
grep -E '^(API_DOMAIN|APP_DOMAIN|ENVIRONMENT|CORS_ORIGINS|PUBLIC_APP_URL)=' \
  /root/synco-law/deploy/.env.production
```

Ожидаемо (CORS и PUBLIC_APP_URL уже настроены под фронт на `app.synco.law`):
```dotenv
API_DOMAIN=api.synco.law
APP_DOMAIN=app.synco.law
ENVIRONMENT=staging
PUBLIC_APP_URL=https://app.synco.law
CORS_ORIGINS=["https://app.synco.law","https://synco.law","https://www.synco.law"]
```

---

## Шаг 4. Запуск стека

```bash
cd /root/synco-law/deploy
docker compose --env-file .env.production -f docker-compose.production.yml up -d --build
```

Первый запуск идёт **несколько минут** (дольше обычного — собираются оба образа):
- образ бэкенда (pip install);
- образ фронтенда (`npm ci` + `next build` — самое ресурсоёмкое; 8 ГБ RAM + swap хватает);
- **ClamAV** качает базы сигнатур (`freshclam`) — до ~5 минут. Бэкенд ждёт, пока ClamAV
  не станет `healthy` (`CLAMAV_REQUIRED=true`). Это нормально, не паникуй.

Следи за состоянием:

```bash
docker compose --env-file .env.production -f docker-compose.production.yml ps
# логи конкретного сервиса, если что-то красное:
docker compose --env-file .env.production -f docker-compose.production.yml logs -f backend
docker compose --env-file .env.production -f docker-compose.production.yml logs -f frontend
docker compose --env-file .env.production -f docker-compose.production.yml logs -f caddy
```

Ждём, пока `backend`, `frontend`, `caddy` будут `healthy`/`running`, а
`postgres/redis/minio/clamav` — `healthy`.

---

## Шаг 5. Проверка бэкенда

```bash
# здоровье через Caddy + HTTPS (после того как DNS долетел и Caddy взял сертификат)
curl https://api.synco.law/health
# если сертификат ещё выпускается — проверь локально на VPS:
curl http://127.0.0.1:8000/health   # так не выйдет: backend не публикует порт наружу
# поэтому health изнутри контейнера:
docker compose --env-file .env.production -f docker-compose.production.yml exec backend \
  python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/health').read())"
```

Swagger должен открываться: `https://api.synco.law/docs`.

Если `https://api.synco.law/health` не отвечает — почти всегда это DNS ещё не долетел
или порт 80 закрыт (Caddy берёт сертификат по HTTP-01, порт 80 обязателен). Проверь
`docker compose ... logs caddy` — там будет видно про ACME/сертификат.

---

## Шаг 6. Проверка фронтенда и полный прогон

Фронтенд собирается и поднимается автоматически на Шаге 4 (сервис `frontend` в стеке),
Caddy отдаёт его на `app.synco.law`. Отдельно ничего собирать/заливать не нужно.

Открой `https://app.synco.law` и проверь end-to-end:
1. Логин / регистрация.
2. Создание контракта из текста.
3. AI-анализ и чат с агентом (Anthropic-ключ уже в `.env.production`).
4. Загрузку PDF/DOCX (идёт напрямую в `api.synco.law`).

Если фронт не открывается:

```bash
# жив ли контейнер фронта и что в логах сборки/старта
docker compose --env-file .env.production -f docker-compose.production.yml ps frontend
docker compose --env-file .env.production -f docker-compose.production.yml logs --tail=50 frontend
# сертификат app.synco.law (нужен DNS + порт 80)
docker compose --env-file .env.production -f docker-compose.production.yml logs caddy | grep -i app.synco.law
```

Теперь весь стек не зависит от твоего ПК и cloudflared-туннеля — их можно гасить.
Если раньше фронт крутился на Vercel, со временем его можно отключить.

> Обновление фронта после правок кода — обычным `git pull` + `up -d --build` (Шаг
> «Эксплуатация»): `next build` пересоберётся на VPS. `NEXT_PUBLIC_API_URL` подставляется
> из `API_DOMAIN` в момент сборки образа.

---

## Шаг 7. Наполнить правовую базу lex.uz (RAG) — рекомендуется

БД стартует пустой; Law-агент точнее с загруженными НПА. Запусти внутри контейнера
(тянет с lex.uz, идёт несколько минут, автоматически индексирует в Elasticsearch):

```bash
cd /root/synco-law/deploy
docker compose --env-file .env.production -f docker-compose.production.yml exec backend \
  python -m scripts.ingest_lexuz
```

Проверка после логина и создания организации:
`GET https://api.synco.law/api/legal/documents`.

---

## Эксплуатация

Обновить бэкенд после `git pull`:

```bash
cd /root/synco-law
git pull
cd deploy
docker compose --env-file .env.production -f docker-compose.production.yml up -d --build
```

Рестарт / остановка / логи:

```bash
docker compose --env-file .env.production -f docker-compose.production.yml restart backend
docker compose --env-file .env.production -f docker-compose.production.yml down       # стоп (данные в volume целы)
docker compose --env-file .env.production -f docker-compose.production.yml logs -f
```

Бэкап Postgres (регулярно, вне VPS):

```bash
docker compose --env-file .env.production -f docker-compose.production.yml exec -T postgres \
  pg_dump -U legal_user legal_workspace | gzip > backup-$(date +%F).sql.gz
```

---

## Известное ограничение: скачивание исходного файла контракта

`presigned_download_url` (backend/app/utils/storage.py) генерирует ссылку на
внутренний хост `minio:9000`, который браузер не резолвит. Поэтому кнопка
«скачать исходный PDF/DOCX» в этой топологии **не работает** (то же ломалось и через туннель).

Всё остальное — текст контракта, анализ, чат, workflow, подпись-заглушка, уведомления —
работает без MinIO наружу.

Рекомендуемое решение (без выставления MinIO в интернет): отдавать файл **потоком через
сам бэкенд** — эндпоинт `GET /api/contracts/{id}/download` стримит байты из MinIO, браузер
общается только с `api.synco.law`. Это правка ~на 15 строк в `backend/app/api/contracts.py`.
Скажи — сделаю.
