# Деплой SynCo: фронтенд на Ahost, бэкенд на Contabo

Split-топология:

```text
synco.law / www.synco.law  -> Ahost (лендинг + почта, не трогаем)
app.synco.law              -> Ahost «Setup Node.js App» (Next.js фронтенд, server.js)
api.synco.law              -> Contabo VPS (FastAPI + Postgres/Redis/MinIO/ES/ClamAV + Caddy)
```

Браузер ходит в бэкенд **напрямую** по `https://api.synco.law`. Так как `app` и `api` —
поддомены одного сайта `synco.law` (same-site), httpOnly-куки авторизации ходят без
проблем, а прокси не нужен. Большие загрузки и долгие AI-запросы не проходят через
shared-хостинг Ahost.

Все данные (Postgres, Redis, MinIO, Elasticsearch, ClamAV) сидят во внутренней Docker-сети
`private` без публикации портов наружу. Снаружи на VPS открыт только Caddy (80/443).

**VPS:** Contabo, IP `169.58.51.56`, Ubuntu, доступ по SSH под `root`.

---

## Шаг 1. DNS и поддомены (делать первым — Caddy без DNS не выпустит HTTPS)

Два поддомена в cPanel Ahost:

**1. `api.synco.law` → Contabo.** В **Zone Editor** для `synco.law` добавь A-запись:

```text
Type: A    Name: api    Value: 169.58.51.56    TTL: по умолчанию
```

**2. `app.synco.law` → Ahost.** В **Subdomains** создай поддомен `app` (DNS внутри Ahost
поднимется автоматически). Само Node.js-приложение привяжем к нему на Шаге 6.

НЕ трогай записи `@`, `www`, `MX`, `mail`, `SPF`, `DKIM`, `DMARC` — это почта и лендинг.

Проверь распространение api-записи (может занять от минут до часа):

```bash
nslookup api.synco.law
```

Должен вернуть `169.58.51.56`. Дальше идти можно, пока DNS долетает — Caddy сам возьмёт
сертификат, как только домен зарезолвится.

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
grep -E '^(API_DOMAIN|ENVIRONMENT|CORS_ORIGINS|PUBLIC_APP_URL)=' \
  /root/synco-law/deploy/.env.production
```

Ожидаемо (CORS и PUBLIC_APP_URL уже настроены под фронт на `app.synco.law`):
```dotenv
API_DOMAIN=api.synco.law
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

Первый запуск идёт **несколько минут**:
- собирается образ бэкенда (pip install);
- **ClamAV** первым делом качает базы сигнатур (`freshclam`) — это самое долгое,
  до ~5 минут. Бэкенд ждёт, пока ClamAV не станет `healthy` (`CLAMAV_REQUIRED=true`).
  Это нормально, не паникуй.

Следи за состоянием:

```bash
docker compose --env-file .env.production -f docker-compose.production.yml ps
# логи конкретного сервиса, если что-то красное:
docker compose --env-file .env.production -f docker-compose.production.yml logs -f backend
docker compose --env-file .env.production -f docker-compose.production.yml logs -f caddy
```

Ждём, пока `backend` и `caddy` будут `healthy`/`running`, а `postgres/redis/minio/clamav` —
`healthy`.

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

## Шаг 6. Собрать фронтенд и залить на Ahost

### 6.1. Собрать пакет (на Windows-ПК, Docker Desktop должен быть запущен)

Сборка идёт в Linux-образе (тот же, что на Contabo), поэтому нужен запущенный Docker.
API-адрес `https://api.synco.law` вшивается в бандл на этом шаге.

```powershell
cd frontend
npm run package:ahost
```

Результат — архив:

```text
frontend/deploy-output/synco-ahost-frontend.tar.gz
```

### 6.2. Поднять Node.js-приложение в cPanel Ahost

1. Поддомен `app.synco.law` уже создан (Шаг 1).
2. Открой **Setup Node.js App** → Create Application.
3. Node.js version: **22 или 24**.
4. Application mode: **Production**.
5. Application root: новая папка, например `app_synco`.
6. Application URL: `app.synco.law`.
7. Application startup file: `server.js`.
8. Создай приложение, затем через File Manager залей `synco-ahost-frontend.tar.gz`
   в папку `app_synco` и распакуй (Extract) прямо в неё (файлы `server.js`, `.next/`,
   `public/`, `node_modules/` должны лежать в корне `app_synco`).
9. В настройках приложения добавь переменную окружения `NODE_ENV=production`
   (и, для подстраховки серверных вызовов, `BACKEND_URL=https://api.synco.law`).
10. **Restart** приложения.

> `NEXT_PUBLIC_API_URL`/`NEXT_PUBLIC_UPLOAD_API_URL` уже вшиты в сборку (Шаг 6.1) —
> на Ahost их задавать не нужно. Браузер ходит прямо в `api.synco.law`.

### 6.3. Проверка

Открой `https://app.synco.law` и проверь:
1. Логин.
2. Создание контракта из текста.
3. AI-анализ и чат с агентом (Anthropic-ключ уже в `.env.production`).
4. Загрузку PDF/DOCX (идёт напрямую в `api.synco.law`).

Теперь бэкенд не зависит от твоего ПК и cloudflared-туннеля — можно гасить туннель и
uvicorn на ПК. Если раньше фронт крутился на Vercel — со временем его можно отключить.

> Если что-то пересобираешь на фронте — повтори Шаг 6.1 и перезалей архив: API-адрес
> запечён в бандл, живого env для него на Ahost нет.

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
