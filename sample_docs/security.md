# Security — AgentDesk Pro (local demo)

## Summary
This document describes the security steps implemented for the local demo (phase 7): secrets handling, PII redaction, RBAC, and HTTPS demonstration.

## 1. Secrets
- `.env` (in project root) holds local secrets (Postgres credentials and demo tokens).
- `.env` is listed in `.gitignore` — do not commit secrets.
- `docker-compose.yml` references `.env` variables (e.g. `${POSTGRES_PASSWORD}`).
- Python scripts load environment values via `os.getenv(...)`. For local convenience they also call `dotenv.load_dotenv()` if `python-dotenv` is available.

## 2. PII Redaction (ingestion)
- Implemented in `services/ingestion/ingest_token_chunks.py`:
  - replaces `user@example.com` patterns with `[EMAIL]`
  - replaces US-style phone numbers `XXX-XXX-XXXX` with `[PHONE]`
- This is a simple, conservative approach (regex-based). For production, consider:
  - stronger patterns (SSNs, postal identifiers)
  - higher-accuracy ML PII detectors
  - configurable redaction policies and audit logs

## 3. RBAC (token-based)
- Token-based RBAC is implemented as a minimal dev solution:
  - `ADMIN_TOKEN` and `USER_TOKEN` in `.env`
  - FastAPI dependency `get_current_role` checks `Authorization: Bearer <token>`
  - `/execute_tool` requires `admin` to run (example to prevent accidental destructive actions)
- This is for demo only. Production should use OAuth2 / JWT / Identity Provider + TLS.

## 4. HTTPS (local)
- For demos, you can generate a self-signed cert:

openssl req -x509 -newkey rsa:4096 -days 365 -nodes -keyout key.pem -out cert.pem -subj "/CN=localhost"

- Run uvicorn with `--ssl-keyfile` and `--ssl-certfile`. Browsers will display a warning — OK for local demos.
- In production, use a real CA (Let's Encrypt / cloud provider certificates).

## 5. Runbook (quick)
- Set `.env` (example values are present in repo root)
- `docker-compose up -d` (starts Postgres, Qdrant, Redis, Prometheus, Grafana)
- `python services/ingestion/ingest_token_chunks.py` (ingest & redact)
- `uvicorn services.api.main:app --host 0.0.0.0 --port 8000 --reload`
- Test RBAC:
- Admin: `Authorization: Bearer admin123`
- User: `Authorization: Bearer user123`

## 6. Next steps (production-minded)
- Move secrets to a secret manager (HashiCorp Vault, AWS Secrets Manager, GCP Secret Manager).
- Replace token-based RBAC with OAuth2 / OpenID Connect / JWT + RBAC.
- Add audit logging and retention policy for PII.
- Harden DB network rules and enable TLS to DB (if supported).

