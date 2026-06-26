# DEPLOY.md — HMIS Inference

Concise deployment guide for the HMIS Inference stack (FastAPI + Vite/React
+ Timescale/Postgres + Redis + ChromaDB + Celery). Plus the nginx + certbot
snippet for production TLS termination.

---

## 1. First-time deploy (docker-compose, single host)

The compose file (`hmis-inference/docker-compose.yml`) provisions four
services: `postgres` (Timescale), `redis`, `backend` (uvicorn), `celery-worker`,
and `celery-beat`. ChromaDB is bind-mounted from `./chroma_db/` so its
on-disk seed persists across container rebuilds.

### 1.1 Environment

Copy and fill the env template:

```bash
cd hmis-inference
cp .env.example .env
```

The minimum keys you must set for production:

| Variable | Purpose |
|---|---|
| `GROQ_API_KEY` | Groq LLM API key (https://console.groq.com/keys). Required when `LLM_PROVIDER=groq`. |
| `ALLOWED_ORIGINS` | Comma-separated origins allowed by CORS. Set to your public frontend URL. |
| `API_KEY` | Optional shared secret. When set, gates all `/api/v1/*` endpoints. |
| `DATABASE_URL` | Pre-set to `postgresql://hmis:hmis_password@postgres:5432/hmis` inside compose. |
| `REDIS_URL` | Pre-set to `redis://redis:6379/0` inside compose. |

Everything else has a sensible default in code or compose.

### 1.2 Bring up

```bash
docker compose up -d --build
docker compose logs -f backend
```

On the first boot the backend:

1. Creates the TimescaleDB connection pool.
2. Runs any pending SQL files in `migrations/` (tracked in the
   `schema_migrations` table). The migration runner is idempotent — re-runs
   on every boot but only applies new files.
3. Starts the FastAPI app.

If you see `Applied migration: 001_create_tables.sql`, you're good. If
`ADVISORY: bereits angewendet` (already applied), also good — means this
isn't your first boot.

### 1.3 Frontend

```bash
cd frontend
npm ci
VITE_API_BASE_URL=https://api.your-domain.com npm run build
```

The frontend is served from `frontend/dist/`. Stand up nginx (see §3) in
front of it. If you set `API_KEY` on the backend, also inject it into the
frontend bundle as a build-time env so you can pass it from the SPA:

```bash
VITE_API_KEY=your-shared-secret npm run build
```

The frontend reads the key at build time via `import.meta.env.VITE_API_KEY` and forwards it as `X-API-Key` on every request (see `src/api/client.js`).

---

## 2. Database migrations

`backend.database.Database.run_migrations()` applies any `*.sql` file in
`migrations/` that isn't already in the `schema_migrations` table. New
migrations are picked up automatically on the next backend restart — drop
the file in, redeploy, done.

When authoring a new migration, avoid `CREATE TABLE my_table`; use
`CREATE TABLE IF NOT EXISTS my_table ...` so that replaying on a hot
database never blows up.

---

## 3. Nginx reverse proxy (TLS + WebSocket passthrough)

Put this at `/etc/nginx/sites-available/hmis-inference` (or split into a
conf.d file). Replace `api.your-domain.com` and the certificate paths.

```nginx
server {
    listen 80;
    server_name api.your-domain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.your-domain.com;

    ssl_certificate     /etc/letsencrypt/live/api.your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.your-domain.com/privkey.pem;

    # TLS hardening — adjust to your taste.
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    add_header Strict-Transport-Security "max-age=31536000" always;

    client_max_body_size 25m;

    # ---- API + WebSocket (FastAPI / uvicorn) --------------------------
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 600s;        # tolerate long Groq synthesis
        proxy_send_timeout 600s;
    }

    # WebSocket endpoint — needs the Upgrade headers.
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade    $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host       $host;
        proxy_read_timeout 86400s;   # hold alerts stream open
    }
}
```

Drop the file in, symlink to `sites-enabled`, then:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

Issue/renew Let's Encrypt certs with certbot:

```bash
sudo certbot --nginx -d api.your-domain.com --agree-tos --redirect
sudo certbot renew --dry-run      # sanity-check auto-renewal
```

For the frontend SPA, serve `frontend/dist/` from a second vhost
(`your-domain.com`) with the same TLS treatment, or host it on Vercel /
Netlify and keep only the API on this host.

---

## 4. Scaling notes

- **Stateless API**: run multiple `backend` containers behind nginx. Use
  `--workers N` on the uvicorn line in compose to scale within a container.
- **Celery**: scale `celery-worker` with `--concurrency N` (already exposed)
  and run as many replicas as needed.
- **Postgres**: one writer is fine for the normal analytics workload;
  TimescaleDB chunks by month so `facility_metrics` reads stay fast.
- **Redis**: keep it co-located with the API host for sub-ms latency on
  the alerts pub/sub channel.
- **ChromaDB**: bind-mounted to host path. If you migrate to a multi-host
  setup, replace with an S3/MinIO volume driver or bake the seed into
  the image at build time.

---

## 5. Operational checks

- `GET /health` — returns 200 with `{status, version, llm.{provider,healthy}, auth_enabled}`.
  Treat `llm.healthy=false` as a PagerDuty page if `LLM_PROVIDER=groq`.
- Backend logs go to stdout (`logging`). Pipe them to `journald` /
  Loki / Datadog as you prefer.
- `docker compose exec backend python scripts/seed_data.py` — seeds 5
  Gujarat districts + 15 facilities. Idempotent against duplicates thanks
  to deterministic UUIDs.
- `docker compose exec backend python scripts/train_anomaly_model.py` —
  retrains the isolation forest. The pickled model lives at
  `models/isolation_forest.pkl` (mounted via the Dockerfile `COPY models`).
