# Production deployment

Нужны VPS с Docker, DNS-запись `API_DOMAIN` на IP VPS и реальные секреты.

```bash
cd deploy
cp .env.production.example .env.production
# заполнить .env.production без тестовых значений
docker compose --env-file .env.production -f docker-compose.production.yml up -d --build
```

После запуска:

```bash
curl https://$API_DOMAIN/health
docker compose --env-file .env.production -f docker-compose.production.yml ps
```

В Vercel установить `BACKEND_URL=https://$API_DOMAIN` и убрать временный
Cloudflare URL. PostgreSQL, Redis, MinIO, Elasticsearch и ClamAV не публикуют
порты наружу; доступен только Caddy на 80/443.

E-IMZO включается только после получения DSV URL и проверки реального формата
его ответа. Production-конфигурация не запустится со stub-подписями или без
обязательной антивирусной проверки.
