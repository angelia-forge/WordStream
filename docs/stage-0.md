# Stage 0 Delivery

## Included

- FastAPI application factory and `/api/v1/health`.
- Environment-based configuration with production safety checks.
- SQLAlchemy engine and request-independent Unit of Work.
- Alembic initial migration and singleton `AppSetting`.
- Settings read/update API.
- UUID request tracing in response headers, errors, and logs.
- Shared-password SessionMiddleware login, CSRF protection, optional API key,
  and per-process login throttling.
- Jinja2 application shell, Tailwind standalone build, HTMX, Alpine.js,
  manifest, and static-only service worker.
- Pinned pre-commit hooks for Ruff, Black, and mypy, plus pytest coverage and
  GitHub Actions.

## Not included

Vocabulary and entry models, imports, study plans, player behavior, learning
events, statistics, and browser E2E workflows belong to later stages.

## Acceptance

```bash
alembic upgrade head
alembic check
pre-commit run --all-files
pytest
```

`GET /api/v1/health` must return `status=ok`, database status `ok`, and the
current Alembic revision. CI must run the same checks on Python 3.11.

## Rollback

Stage 0 contains the first schema only. During local development, rollback is
`alembic downgrade base` or removing the disposable SQLite file. Once user
data exists, restore a database backup instead of assuming arbitrary SQLite
downgrades are lossless.
