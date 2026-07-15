# SynCo split deployment

The production topology keeps the public frontend at Ahost and runs the data
services on an OVHcloud VPS:

```text
synco.law       -> Ahost shared hosting / landing
www.synco.law   -> Ahost shared hosting / landing
app.synco.law   -> Ahost Node.js application / Next.js frontend
api.synco.law   -> OVHcloud VPS / FastAPI and private data services
```

The browser calls `api.synco.law` directly. Large uploads and long AI requests
therefore do not pass through the Ahost shared-hosting proxy.

## Recommended OVHcloud VPS

Start with a current `VPS-3` or an equivalent configuration:

- 6 vCores;
- 12 GB RAM;
- 100 GB NVMe;
- Ubuntu 24.04 LTS;
- no Plesk or cPanel.

Use a larger disk or object-storage backup before document volume approaches
the local 100 GB limit. `VPS-4` is the safer next step for a larger production
rollout.

## DNS

Keep the Ahost nameservers and all existing landing and mail records. Create or
update only these endpoints:

```text
app.synco.law  -> Ahost shared-hosting account
api.synco.law  -> A record with the public OVH VPS IPv4 address
```

Do not change `@`, `www`, `MX`, `mail`, SPF, DKIM or DMARC records.

## OVH backend

Install Docker Engine, the Docker Compose plugin and Git on Ubuntu. Clone the
private repository, then create the runtime configuration:

```bash
cd synco-law/deploy
cp .env.production.example .env.production
nano .env.production
docker compose --env-file .env.production -f docker-compose.production.yml up -d --build
```

Set strong unique values for every password and secret. The relevant public
settings must remain:

```dotenv
API_DOMAIN=api.synco.law
PUBLIC_APP_URL=https://app.synco.law
CORS_ORIGINS=["https://app.synco.law"]
COOKIE_SECURE=true
COOKIE_SAMESITE=lax
```

Open only SSH, HTTP and HTTPS in the OVH firewall. PostgreSQL, Redis, MinIO,
Elasticsearch and ClamAV stay inside the private Docker network.

Verify the backend after DNS propagation:

```bash
curl https://api.synco.law/health
docker compose --env-file .env.production -f docker-compose.production.yml ps
```

## Ahost frontend

The Ahost account must provide `Setup Node.js App` or an equivalent persistent
Node.js application feature. Use Node.js 22 or 24. A static-only hosting account
cannot run this Next.js frontend without a separate application process.

Build the Linux-compatible upload archive locally. Docker Desktop must be
running; the package is exported from the same Linux image used in CI:

```powershell
cd frontend
npm run package:ahost
```

The command creates:

```text
frontend/deploy-output/synco-ahost-frontend.tar.gz
```

In cPanel:

1. Create the `app.synco.law` subdomain.
2. Open `Setup Node.js App` and select Node.js 22 or 24.
3. Set the application URL to `app.synco.law`.
4. Set the application root to a new directory such as `app_synco`.
5. Upload and extract the archive into that directory.
6. Set the startup file to `server.js` and `NODE_ENV=production`.
7. Restart the Node.js application.

The API URL is embedded during the build. Rebuild the archive if the API domain
changes.

## Production gates

Production mode requires a real E-IMZO DSV URL, content-bound signature
verification and `ALLOW_STUB_SIGNATURES=false`. Until then, use
`ENVIRONMENT=staging` for a closed pilot and do not present stub signatures as
legally valid electronic signatures.

Before storing customer documents outside Uzbekistan, confirm the applicable
personal-data localisation, cross-border transfer and contractual safeguards
with local counsel. Keep an encrypted backup outside the VPS and test restore
regularly; the provider snapshot alone is not a complete backup strategy.
