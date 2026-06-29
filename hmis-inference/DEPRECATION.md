# API_KEY deprecation timeline

The HMIS inference API was built in two phases:

1. **Phase 1** shipped with a single shared `API_KEY` header used for both
   service-to-service traffic and operator dashboards.
2. **Phase 4** introduced real auth: per-user JWT bearer tokens + a
   `hmis_session` cookie, role-based access control, and a Commissioner
   bootstrap script (`scripts/create_commissioner.py`).

The legacy `X-API-Key` header is still accepted by `AuthMiddleware` so
existing service-to-service callers don't break.

## Deprecation schedule

| Phase | Date | Behaviour |
|-------|------|-----------|
| **Now** (Phase 6) | 2026-06-28 | Both paths work. JWT preferred. |
| **Phase 6 → 6.4** | (4 months from now) | Warnings emitted in `/health` and `/metrics` when a request authenticates via the legacy path. |
| **Phase 6.5** | (5 months from now) | Legacy API_KEY requests return `410 Gone`. |
| **Phase 6.6** | (6 months from now) | API_KEY env var is read once at startup but is no longer honoured — middleware is removed entirely. |

## How to migrate

Service-to-service clients should switch to:

```bash
# 1. Bootstrap the first service account (one per integration):
python scripts/create_user_for_service.py \
    --email ingest-bot@example.invalid \
    --name "CSV Ingest Bot" \
    --role STATE_OFFICER

# 2. Exchange the email + a stored secret for a token pair:
curl -X POST $HOST/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email": "ingest-bot@example.invalid", "password": "<stored secret>"}'
# → access_token + refresh_token

# 3. Use the bearer on every protected request:
curl $HOST/api/v1/ingest/facility_metrics \
  -H "Authorization: Bearer $TOKEN" \
  -d @payload.json
```

Refresh tokens are long-lived (default 7 days) and re-issue access
tokens with a 4-hour lifetime. Store the refresh token in a secret
manager, not in environment files.

## When to keep `API_KEY`

- Staging environments where humans poke at the API by hand —
  `API_KEY = "...something the team memorises ..."`.
- Health checks performed by the load balancer — sent with the request
  URL is more friction than the legacy key. (The pre-Phase-3 setup
  predates JWT, so we kept the path live to avoid breaking alerts.)

Outside of those cases, treat it as a transitional fallback.
