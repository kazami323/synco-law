# Production deployment on Ahost VDS

Основной домен `synco.law` и `www.synco.law` остаются на shared-хостинге
Ahost для лендинга. Приложение и API работают на отдельном VDS:

```text
synco.law       -> shared hosting / landing
www.synco.law   -> shared hosting / landing
app.synco.law   -> VDS / Next.js
api.synco.law   -> VDS / FastAPI
```

Для полного стека нужны минимум 8 ГБ RAM, лучше 12 ГБ. На Ahost разумная
стартовая конфигурация — VDS Cloud 200 (4 CPU, 200 ГБ SSD) с дополнительными
8 ГБ RAM, если поддержка подтверждает добавление памяти к тарифу. Панели
cPanel/Plesk на VDS не нужны.

## DNS

В cPanel откройте `Zone Editor` для `synco.law` и добавьте две записи:

```text
A  app  <PUBLIC_VDS_IP>
A  api  <PUBLIC_VDS_IP>
```

Записи `@`, `www`, `MX`, `mail`, SPF, DKIM и DMARC не изменяйте: лендинг и
почта должны продолжить работать на shared-хостинге.

## First start

На VDS нужны Ubuntu 24.04 LTS, Docker Engine, Docker Compose plugin, Git и
доступ к приватному GitHub-репозиторию. После клонирования проекта:

```bash
cd deploy
cp .env.production.example .env.production
# заполнить .env.production реальными секретами и Anthropic API key
docker compose --env-file .env.production -f docker-compose.production.yml up -d --build
```

После запуска:

```bash
curl https://api.synco.law/health
curl -I https://app.synco.law/login
docker compose --env-file .env.production -f docker-compose.production.yml ps
```

Frontend обращается к backend через внутреннюю Docker-сеть. PostgreSQL,
Redis, MinIO, Elasticsearch и ClamAV не публикуют порты наружу; доступен
только Caddy на 80/443. Vercel и Cloudflare Tunnel после миграции не нужны.

E-IMZO включается только после получения DSV URL и проверки реального формата
его ответа. Production-конфигурация не запустится со stub-подписями или без
обязательной антивирусной проверки.

Для закрытого тестового пилота до подключения E-IMZO используйте
`ENVIRONMENT=staging` и `ALLOW_STUB_SIGNATURES=true`, сохранив
`COOKIE_SECURE=true` и обязательный ClamAV. Такой режим нельзя выдавать за
юридически значимую электронную подпись.
